"""Modelos de IA para las funciones de akari que piensan (asistente, mirar la pantalla, resumir…).

Dos caminos, a elección del usuario:
  * una clave de API: Anthropic, OpenAI, Google Gemini u OpenRouter. Se guarda en
    ~/.config/akari/claves.json (solo legible por el usuario) y nunca sale en /api/estado;
  * modelos locales con Ollama (gratis, sin internet): akari mira la RAM y la tarjeta de video
    y recomienda qué modelos van a andar bien en este equipo, con botón para descargarlos.

Si no hay ninguno, `listo` es False y cada función con IA le pide al usuario agregar una API o
un modelo local. Todo pasa por `preguntar()`, que habla con cualquiera de los dos caminos.
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .comun import CONFIG, WINDOWS, abrir, correr, escribir_json, leer_json, notificar, t, tiene

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
AJUSTES = CONFIG / "modelos.json"
CLAVES = CONFIG / "claves.json"

# Proveedores con clave. Todos menos Anthropic entienden el formato de OpenAI (/chat/completions).
PROVEEDORES = {
    "anthropic": {"nombre": "Anthropic (Claude)", "base": "https://api.anthropic.com/v1",
                  "web": "https://console.anthropic.com/settings/keys", "prefiere": ["haiku", "sonnet"]},
    "openai": {"nombre": "OpenAI", "base": "https://api.openai.com/v1",
               "web": "https://platform.openai.com/api-keys", "prefiere": ["mini", "gpt-"]},
    "gemini": {"nombre": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "web": "https://aistudio.google.com/apikey", "prefiere": ["flash", "gemini"]},
    "openrouter": {"nombre": "OpenRouter", "base": "https://openrouter.ai/api/v1",
                   "web": "https://openrouter.ai/keys", "prefiere": [":free", "mini", "flash"]},
    # Groq: rápido y barato; también transcribe audio (Whisper), ver audio.py
    "groq": {"nombre": "Groq", "base": "https://api.groq.com/openai/v1",
             "web": "https://console.groq.com/keys", "prefiere": ["llama-3.1-8b", "llama-3.3", "qwen"]},
}

# Modelos locales que recomendamos, de menor a mayor. gb = lo que pesa la descarga (≈ lo que ocupa
# en memoria). vision = puede mirar imágenes (capturas de pantalla, la cámara).
CATALOGO = [
    {"id": "gemma3:1b", "gb": 0.8, "vision": False,
     "nota": ("Muy liviano: para equipos con poca memoria; respuestas simples.",
              "Very light: for low-memory computers; simple answers.")},
    {"id": "qwen3:4b-instruct", "gb": 2.5, "vision": False,
     "nota": ("El mejor equilibrio: rápido, buen español y sabe usar herramientas.",
              "Best balance: fast, multilingual and good with tools.")},
    {"id": "gemma3:4b", "gb": 3.3, "vision": True,
     "nota": ("Conversa y también mira imágenes.", "Chats and can also look at images.")},
    {"id": "qwen3-vl:4b-instruct", "gb": 3.3, "vision": True,
     "nota": ("Para mirar la pantalla y la cámara: lee texto en imágenes.",
              "For looking at the screen and camera: reads text in images.")},
    {"id": "qwen3:8b", "gb": 5.2, "vision": False,
     "nota": ("Más listo, algo más lento.", "Smarter, a bit slower.")},
    {"id": "qwen3-vl:8b-instruct", "gb": 6.1, "vision": True,
     "nota": ("Visión más precisa.", "More accurate vision.")},
    {"id": "qwen3:14b", "gb": 9.3, "vision": False,
     "nota": ("Para equipos potentes: respuestas más completas.", "For powerful computers: fuller answers.")},
]
# Modelos de embeddings (chicos, solo para buscar por significado en el cerebro). embeddinggemma entiende
# más de 100 idiomas (bien en español); nomic-embed-text es más liviano, sobre todo en inglés.
CATALOGO_EMBED = [
    {"id": "embeddinggemma:300m", "gb": 0.6,
     "nota": ("Para buscar en tu cerebro por significado: multilingüe, buen español.",
              "To search your brain by meaning: multilingual.")},
    {"id": "nomic-embed-text", "gb": 0.3,
     "nota": ("Para buscar en tu cerebro: más liviano, mejor en inglés.", "To search your brain: lighter, best in English.")},
]
# un modelo cabe en la tarjeta de video si hay este margen sobre su tamaño (contexto, caché)
MARGEN_GPU = 1.25
MARGEN_RAM = 2.0       # en RAM además corren el sistema y las apps


# ---------------------------------------------------------------- red

def _pedir(url, datos=None, cabeceras=None, timeout=20):
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json", **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _error(e):
    """Mensaje corto y legible de un error de red (sin la clave)."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            detalle = json.loads(e.read() or b"{}")
            detalle = detalle.get("error", detalle)
            detalle = detalle.get("message", "") if isinstance(detalle, dict) else str(detalle)
        except ValueError:
            detalle = ""
        if e.code in (401, 403):
            return t("La clave no es válida o no tiene permiso.", "The key is invalid or has no permission.")
        if e.code == 429:
            return t("Se acabó el saldo o el límite de la API por ahora.", "API credit or rate limit reached for now.")
        return f"HTTP {e.code} {detalle}"[:200]
    if isinstance(e, urllib.error.URLError):
        return t("Sin conexión con el servicio.", "Can't reach the service.")
    return str(e)[:200]


def _cabeceras(proveedor, clave):
    if proveedor == "anthropic":
        return {"x-api-key": clave, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {clave}"}


# ---------------------------------------------------------------- equipo

def _ram_gb():
    if WINDOWS:
        import ctypes

        class Estado(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        e = Estado()
        e.dwLength = ctypes.sizeof(Estado)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)):
            return round(e.ullTotalPhys / 2**30, 1)
        return 0
    try:
        with open("/proc/meminfo") as f:
            for linea in f:
                if linea.startswith("MemTotal:"):
                    return round(int(linea.split()[1]) / 2**20, 1)
    except OSError:
        pass
    try:            # macOS y otros
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (ValueError, OSError, AttributeError):
        return 0


def _gpu():
    """{nombre, vram_gb} de la tarjeta NVIDIA (nvidia-smi) o AMD (sysfs); {} si no hay o no se sabe."""
    if tiene("nvidia-smi"):
        ok, salida = correr(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], 10)
        if ok and salida:
            nombre, _, mib = salida.splitlines()[0].rpartition(",")
            try:
                return {"nombre": nombre.strip(), "vram_gb": round(int(mib) / 1024, 1)}
            except ValueError:
                pass
    if not WINDOWS:
        import glob
        for archivo in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):     # AMD (amdgpu)
            try:
                gb = int(open(archivo).read()) / 2**30
            except (OSError, ValueError):
                continue
            if gb >= 2:     # las integradas reservan poco y comparten la RAM
                return {"nombre": "AMD", "vram_gb": round(gb, 1)}
    return {}


def equipo():
    return {"ram_gb": _ram_gb(), "gpu": _gpu()}


def cabe(gb, eq):
    """'gpu' (rápido), 'cpu' (anda, más lento) o 'no'."""
    vram = (eq.get("gpu") or {}).get("vram_gb", 0)
    if vram and vram >= gb * MARGEN_GPU:
        return "gpu"
    if eq.get("ram_gb", 0) >= gb * MARGEN_RAM + 2:
        return "cpu"
    return "no"


# ---------------------------------------------------------------- monitor

class MonitorModelos:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.equipo = equipo()
        self.ollama = {"estado": "no_instalado", "modelos": []}
        self.descarga = None            # {"modelo", "pct", "error"?}
        self.proveedores = {}           # id -> {"modelos": [...], "error": str}
        self._vision = {}               # "nombre@digest" -> bool
        self.estado = {}
        self._ultimo = None
        self.calcular()

    # ajustes: {"modo": "local"|"api"|None, "proveedor", "modelo", "vision", "local": {"texto", "vision"}}
    def ajustes(self):
        return leer_json(AJUSTES)

    def claves(self):
        return leer_json(CLAVES)

    def _guardar_claves(self, claves):
        escribir_json(CLAVES, claves)
        if not WINDOWS:         # en Windows %APPDATA% ya es solo del usuario
            os.chmod(CLAVES, 0o600)

    def paso(self):
        self.leer_ollama()
        self.calcular()

    def leer_ollama(self):
        try:
            datos = _pedir(f"{OLLAMA}/api/tags", timeout=3)
            modelos = []
            for m in datos.get("models", []):
                cap = self._capacidades(m["name"], m.get("digest", ""))
                modelos.append({"nombre": m["name"], "gb": round(m.get("size", 0) / 2**30, 1), "vision": "vision" in cap,
                                "embeddings": "embedding" in cap or es_embebedor(m["name"])})
            self.ollama = {"estado": "activo", "modelos": modelos}
        except (OSError, ValueError):
            self.ollama = {"estado": "apagado" if tiene("ollama") else "no_instalado", "modelos": []}

    def _capacidades(self, nombre, digest):
        """Lo que sabe hacer el modelo instalado (vision, embedding…): /api/show, una vez por versión."""
        clave = f"{nombre}@{digest}"
        if clave not in self._vision:
            try:
                info = _pedir(f"{OLLAMA}/api/show", {"model": nombre}, timeout=5)
                self._vision[clave] = list(info.get("capabilities", []))
            except (OSError, ValueError):
                return []
        return self._vision[clave]

    # ------------------------------------------------------------ elegido
    def _instalado(self, modelo):
        nombres = {m["nombre"] for m in self.ollama["modelos"]}
        return modelo in nombres or f"{modelo}:latest" in nombres

    def elegido(self, vision=False):
        """(camino, modelo) con el que se pregunta, o (None, motivo) si no hay ninguno listo."""
        a = self.ajustes()
        modo = a.get("modo")
        if modo == "api":
            prov = a.get("proveedor")
            if prov in PROVEEDORES and self.claves().get(prov):
                modelo = a.get("vision" if vision else "modelo") or a.get("modelo")
                if modelo:
                    return prov, modelo
            return None, t("Falta la clave de API.", "The API key is missing.")
        if modo == "local":
            if self.ollama["estado"] != "activo":
                return None, t("Ollama no está corriendo.", "Ollama isn't running.")
            local = a.get("local", {})
            modelo = local.get("vision") if vision else local.get("texto")
            if vision and not modelo:
                return None, t("Elige un modelo local que mire imágenes.", "Choose a local model that can see images.")
            modelo = modelo or local.get("vision")
            if modelo and self._instalado(modelo):
                return "ollama", modelo
            return None, t("Descarga un modelo local.", "Download a local model.")
        return None, t("Agrega una clave de API o usa un modelo local.", "Add an API key or use a local model.")

    # ------------------------------------------------------------ estado
    def calcular(self):
        a, claves = self.ajustes(), self.claves()
        local = a.get("local", {})
        recomendados = []
        for m in CATALOGO:
            recomendados.append({"id": m["id"], "gb": m["gb"], "vision": m["vision"], "nota": t(*m["nota"]),
                                 "cabe": cabe(m["gb"], self.equipo), "instalado": self._instalado(m["id"]),
                                 "en_uso": m["id"] in (local.get("texto"), local.get("vision"))})
        # el «mejor» de cada tipo es el más grande que corre en la tarjeta (o en la CPU si no hay tarjeta)
        for vision in (False, True):
            del_tipo = [r for r in recomendados if r["vision"] == vision]
            mejor = [r for r in del_tipo if r["cabe"] == "gpu"] or [r for r in del_tipo if r["cabe"] == "cpu"]
            if mejor:
                # en CPU, el más chico que sirve: un modelo grande en CPU tarda demasiado
                elegido = mejor[-1] if mejor[0]["cabe"] == "gpu" else mejor[min(1, len(mejor) - 1)]
                elegido["sugerido"] = "vision" if vision else "texto"
        # el chico busca y el otro conversa: lo que conviene para «buscar y abrir archivos» en este equipo
        embed = []
        for m in CATALOGO_EMBED:
            embed.append({"id": m["id"], "gb": m["gb"], "nota": t(*m["nota"]), "cabe": cabe(m["gb"], self.equipo),
                          "instalado": self._instalado(m["id"])})
        sugerido_embed = next((e for e in embed if e["instalado"]), None) or \
            (embed[0] if self.equipo.get("ram_gb", 0) >= 6 or not self.equipo.get("ram_gb") else embed[1])
        sugerido_embed["sugerido"] = True
        conversa = next((r["id"] for r in recomendados if r.get("sugerido") == "texto"), None)
        if a.get("modo") == "api" and a.get("modelo"):
            conversa = a["modelo"]
        elif a.get("modo") == "local" and local.get("texto"):
            conversa = local["texto"]
        proveedores = []
        for ident, p in PROVEEDORES.items():
            clave = claves.get(ident) or ""
            info = self.proveedores.get(ident, {})
            proveedores.append({"id": ident, "nombre": p["nombre"], "web": p["web"], "clave": bool(clave),
                                "final": clave[-4:] if clave else "", "modelos": info.get("modelos", [])[:80],
                                "error": info.get("error", "")})
        texto, por_que = self.elegido()
        vision, por_que_v = self.elegido(vision=True)
        estado = {
            "listo": texto is not None, "motivo": "" if texto else por_que,
            "vision_lista": vision is not None, "motivo_vision": "" if vision else por_que_v,
            "modo": a.get("modo"), "proveedor": a.get("proveedor"), "modelo": a.get("modelo"),
            "modelo_vision": a.get("vision"), "local": local,
            "texto": f"{texto} · {por_que}" if texto else None,
            "equipo": self.equipo, "ollama": {**self.ollama, "descarga": dict(self.descarga) if self.descarga else None},
            "recomendados": recomendados, "proveedores": proveedores,
            "embeddings": embed, "para_archivos": {"buscar": sugerido_embed["id"], "conversar": conversa},
        }
        if estado != self._ultimo:
            self._ultimo = estado
            self.estado = estado
            self.al_cambiar()

    # ------------------------------------------------------------ acciones
    def accion(self, datos):
        accion = str(datos.get("accion"))
        if accion == "clave":
            return self._clave(str(datos.get("proveedor")), str(datos.get("clave") or "").strip())
        if accion == "borrar_clave":
            claves = self.claves()
            claves.pop(str(datos.get("proveedor")), None)
            self._guardar_claves(claves)
            a = self.ajustes()
            if a.get("modo") == "api" and a.get("proveedor") == datos.get("proveedor"):
                a["modo"] = None
                escribir_json(AJUSTES, a)
        elif accion == "usar":
            return self._usar(datos)
        elif accion == "descargar":
            modelo = str(datos.get("modelo") or "")
            if not re.fullmatch(r"[\w.\-/]+(:[\w.\-]+)?", modelo):
                return False, "?"
            if self.descarga and not self.descarga.get("error") and self.descarga.get("pct", 0) < 100:
                return False, t("Ya hay una descarga en curso.", "A download is already running.")
            threading.Thread(target=self._descargar, args=(modelo, bool(datos.get("usar"))), daemon=True).start()
        elif accion == "borrar_modelo":
            try:
                req = urllib.request.Request(f"{OLLAMA}/api/delete", method="DELETE",
                                             data=json.dumps({"model": str(datos.get("modelo"))}).encode())
                urllib.request.urlopen(req, timeout=20).read()
            except OSError as e:
                return False, _error(e)
            self.leer_ollama()
        elif accion == "arrancar_ollama":
            return self._arrancar_ollama()
        elif accion == "instalar_ollama":
            return self._instalar_ollama()
        elif accion == "probar":
            try:
                return True, preguntar(self, t("Responde solo: ¡Hola! Estoy listo.", "Reply only: Hi! I'm ready."))
            except ErrorIA as e:
                return False, str(e)
        else:
            return False, "?"
        self.calcular()
        return True, ""

    def _clave(self, proveedor, clave):
        if proveedor not in PROVEEDORES or not (8 <= len(clave) <= 300) or any(c.isspace() for c in clave):
            return False, t("Esa clave no parece válida.", "That key doesn't look valid.")
        try:
            modelos = listar_modelos(proveedor, clave)
        except (OSError, ValueError) as e:
            return False, _error(e)
        claves = self.claves()
        claves[proveedor] = clave
        self._guardar_claves(claves)
        self.proveedores[proveedor] = {"modelos": modelos}
        a = self.ajustes()
        if a.get("modo") != "local" or not self.elegido()[0]:      # la primera clave se usa sola
            a.update(modo="api", proveedor=proveedor, modelo=sugerir(proveedor, modelos), vision=None)
            escribir_json(AJUSTES, a)
        self.calcular()
        return True, t("Clave guardada.", "Key saved.")

    def _usar(self, datos):
        a = self.ajustes()
        modo = datos.get("modo")
        if modo == "api":
            prov = datos.get("proveedor") or a.get("proveedor")
            if prov not in PROVEEDORES or not self.claves().get(prov):
                return False, t("Primero guarda la clave.", "Save the key first.")
            otro = prov != a.get("proveedor")
            if otro:
                a.update(modelo=None, vision=None)
            a.update(modo="api", proveedor=prov)
            modelo = datos.get("modelo")
            if modelo:
                a["vision" if datos.get("tipo") == "vision" else "modelo"] = str(modelo)[:120]
            elif not a.get("modelo"):
                if prov not in self.proveedores:
                    self._refrescar(prov)
                a["modelo"] = sugerir(prov, self.proveedores.get(prov, {}).get("modelos", []))
        elif modo == "local":
            a["modo"] = "local"
            if datos.get("modelo"):
                local = a.setdefault("local", {})
                local["vision" if datos.get("tipo") == "vision" else "texto"] = str(datos["modelo"])[:120]
        elif modo is None:
            a["modo"] = None
        else:
            return False, "?"
        escribir_json(AJUSTES, a)
        self.calcular()
        return True, ""

    def _refrescar(self, proveedor):
        try:
            self.proveedores[proveedor] = {"modelos": listar_modelos(proveedor, self.claves()[proveedor])}
        except (OSError, ValueError, KeyError) as e:
            self.proveedores[proveedor] = {"modelos": [], "error": _error(e)}

    def refrescar_proveedores(self):
        """Al arrancar: la lista de modelos de cada clave guardada (en un hilo, puede tardar)."""
        for prov in list(self.claves()):
            if prov in PROVEEDORES:
                self._refrescar(prov)
        self.calcular()

    def _descargar(self, modelo, usar):
        self.descarga = {"modelo": modelo, "pct": 0}
        self.calcular()
        if self.ollama["estado"] != "activo":
            self._arrancar_ollama()
        try:
            req = urllib.request.Request(f"{OLLAMA}/api/pull", data=json.dumps({"model": modelo}).encode(),
                                         headers={"Content-Type": "application/json"})
            ultimo = 0
            with urllib.request.urlopen(req, timeout=60) as r:
                for linea in r:
                    paso = json.loads(linea or b"{}")
                    if paso.get("error"):
                        raise ValueError(paso["error"])
                    if paso.get("total"):
                        self.descarga["pct"] = int(paso.get("completed", 0) * 100 / paso["total"])
                    if time.time() - ultimo > 1:        # no avisar a las cápsulas en cada línea
                        ultimo = time.time()
                        self.calcular()
            self.descarga = {"modelo": modelo, "pct": 100}
            notificar(t("Modelo descargado", "Model downloaded"), modelo)
            self.leer_ollama()
            if usar and not es_embebedor(modelo):         # uno de embeddings nunca pasa a ser el de conversar
                es_vision = any(m["id"] == modelo and m["vision"] for m in CATALOGO)
                self._usar({"modo": "local", "modelo": modelo, "tipo": "vision" if es_vision else "texto"})
        except (OSError, ValueError) as e:
            self.descarga = {"modelo": modelo, "pct": 0, "error": _error(e)}
        self.calcular()

    def _arrancar_ollama(self):
        if not tiene("ollama"):
            return False, t("Ollama no está instalado.", "Ollama isn't installed.")
        try:
            extra = {"creationflags": 0x08000008} if WINDOWS else {"start_new_session": True}   # sin ventana, suelto
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
        except OSError as e:
            return False, str(e)
        for _ in range(20):
            time.sleep(0.5)
            self.leer_ollama()
            if self.ollama["estado"] == "activo":
                break
        self.calcular()
        return self.ollama["estado"] == "activo", ""

    def _instalar_ollama(self):
        if WINDOWS and tiene("winget"):
            ok, salida = correr(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                                 "--accept-package-agreements", "--accept-source-agreements"], timeout=900)
            self.leer_ollama()
            self.calcular()
            return ok, "" if ok else salida[-300:]
        # Linux: el script oficial pide contraseña de administrador; mejor que el usuario vea la página
        abrir("https://ollama.com/download")
        return True, t("Se abrió la página de descarga de Ollama.", "Opened the Ollama download page.")


# ---------------------------------------------------------------- API

def listar_modelos(proveedor, clave):
    base = PROVEEDORES[proveedor]["base"]
    datos = _pedir(f"{base}/models", cabeceras=_cabeceras(proveedor, clave), timeout=15)
    ids = [m.get("id", "") for m in datos.get("data", [])]
    if proveedor == "gemini":
        ids = [i.split("/", 1)[-1] for i in ids if "gemini" in i and "embedding" not in i]
    elif proveedor == "openai":
        ids = [i for i in ids if re.match(r"(gpt-|o\d|chatgpt)", i) and not re.search(
            r"audio|realtime|transcribe|tts|image|search|embedding", i)]
    elif proveedor == "groq":
        ids = [i for i in ids if not re.search(r"whisper|tts|guard|distil", i)]
    return sorted(set(i for i in ids if i), reverse=True)


def sugerir(proveedor, modelos):
    """El modelo económico de cada proveedor (el más nuevo que coincide con su preferencia)."""
    for patron in PROVEEDORES[proveedor]["prefiere"]:
        for m in modelos:
            if patron in m:
                return m
    return modelos[0] if modelos else None


class ErrorIA(Exception):
    pass


def preguntar(monitor, texto, sistema=None, imagen=None, historial=None, timeout=120):
    """Una respuesta del modelo elegido. imagen = bytes PNG/JPEG (usa el modelo de visión).
    historial = [{"rol": "usuario"|"asistente", "texto"}] de la conversación previa."""
    camino, modelo = monitor.elegido(vision=imagen is not None)
    if camino is None:
        raise ErrorIA(modelo)
    mensajes = [{"role": "user" if h["rol"] == "usuario" else "assistant", "content": h["texto"]}
                for h in (historial or [])]
    try:
        if camino == "anthropic":
            contenido = [{"type": "text", "text": texto}]
            if imagen is not None:
                contenido.insert(0, {"type": "image", "source": {"type": "base64", "media_type": _mime(imagen),
                                                                 "data": base64.b64encode(imagen).decode()}})
            cuerpo = {"model": modelo, "max_tokens": 1500, "messages": mensajes + [{"role": "user", "content": contenido}]}
            if sistema:
                cuerpo["system"] = sistema
            r = _pedir(f"{PROVEEDORES[camino]['base']}/messages", cuerpo,
                       _cabeceras(camino, monitor.claves()[camino]), timeout)
            return "".join(b.get("text", "") for b in r.get("content", [])).strip()
        # formato OpenAI: OpenAI, Gemini, OpenRouter y Ollama (/v1)
        contenido = texto
        if imagen is not None:
            url = f"data:{_mime(imagen)};base64,{base64.b64encode(imagen).decode()}"
            contenido = [{"type": "text", "text": texto}, {"type": "image_url", "image_url": {"url": url}}]
        cuerpo = {"model": modelo, "messages": ([{"role": "system", "content": sistema}] if sistema else [])
                  + mensajes + [{"role": "user", "content": contenido}]}
        if camino == "ollama":
            base, cab = f"{OLLAMA}/v1", {}
        else:
            base, cab = PROVEEDORES[camino]["base"], _cabeceras(camino, monitor.claves()[camino])
        r = _pedir(f"{base}/chat/completions", cuerpo, cab, timeout)
        texto = (r.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()     # qwen3 piensa en voz alta
    except (OSError, ValueError) as e:
        raise ErrorIA(_error(e)) from None


def es_embebedor(nombre):
    n = nombre.lower()
    return "embed" in n or any(n.split(":")[0] == m["id"].split(":")[0] for m in CATALOGO_EMBED) or "minilm" in n or "bge-" in n


def embebedores_instalados(monitor=None):
    """Los modelos de embeddings que tiene Ollama ([] si Ollama no está corriendo)."""
    if monitor is not None and monitor.ollama.get("estado") == "activo":
        return [m["nombre"] for m in monitor.ollama["modelos"] if m.get("embeddings")]
    try:
        datos = _pedir(f"{OLLAMA}/api/tags", timeout=3)
    except (OSError, ValueError):
        return []
    return [m["name"] for m in datos.get("models", []) if es_embebedor(m["name"])]


def embeber(textos, modelo, timeout=120):
    """Vectores de `textos` con un modelo de embeddings local de Ollama (nunca por API: es todo el índice)."""
    r = _pedir(f"{OLLAMA}/api/embed", {"model": modelo, "input": list(textos), "truncate": True}, timeout=timeout)
    vectores = r.get("embeddings")
    if not isinstance(vectores, list) or len(vectores) != len(textos):
        raise ValueError(r.get("error") or "embed")
    return vectores


def _mime(datos):
    return "image/png" if datos[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


if __name__ == "__main__":       # python -m akari.modelos: lo que recomienda para este equipo
    m = MonitorModelos(lambda: None)
    m.paso()
    print(json.dumps({k: m.estado[k] for k in ("equipo", "ollama", "recomendados", "listo", "motivo")},
                     indent=2, ensure_ascii=False), file=sys.stdout)
