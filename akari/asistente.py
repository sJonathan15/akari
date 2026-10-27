"""El asistente de akari: se le escribe (o se le habla, ver voz.py) y hace cosas en el equipo.

«Quién» responde y «dónde»:
  * Local + segundo plano: un bucle corto de herramientas (acciones.py) con el modelo de
    «Modelos de IA» (Ollama con /api/chat y tools; Anthropic, OpenAI, Gemini, OpenRouter o Groq con
    su tool use). «Abre X», la música y la hora se resuelven antes, sin gastar tokens. Tras una
    herramienta que tarda (mirar la pantalla o la cámara, generar una imagen) el turno termina con
    su resultado tal cual: los modelos chicos, si siguen, inventan lo que «vieron».
  * Claude + segundo plano: `claude -p` con solo herramientas de lectura (--permission-mode
    dontAsk) y --resume si la última pregunta fue hace menos de 10 minutos.
  * Terminal: abre una terminal con `claude "<texto>"` (o `ollama run` si es local con Ollama).
"""
import json
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import acciones, cerebro, memoria
from .comun import CONFIG, HOME, IDIOMA, SIN_VENTANA, WINDOWS, buscar, entorno_completo, escribir_json, leer_json, t, terminal
from .modelos import OLLAMA, PROVEEDORES, ErrorIA, _cabeceras, _error, _pedir, preguntar

AJUSTES = CONFIG / "asistente.json"
HISTORIAL = CONFIG / "asistente-historial.json"
MAX_HISTORIAL = 40
MAX_VUELTAS = 5                 # llamadas al modelo por pregunta
CONTEXTO = 30 * 60              # se le pasan al modelo las preguntas de la última media hora
RESUMIR_CLAUDE = 10 * 60        # --resume si la última pregunta a Claude fue hace menos de esto
OCULTAR = 0.8                   # segundos que se esconden las cápsulas antes de la captura
REGISTRAR = 5 * 60              # la charla va a la bitácora del cerebro tras estos segundos sin preguntas
LECTURA_CLAUDE = "Read,Glob,Grep,LS,WebSearch,WebFetch"
DIAS = {"es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
        "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}[IDIOMA]

# ---------------------------------------------------------------- herramientas para el modelo

def _h(nombre, descripcion, propiedades=None, requeridas=()):
    return {"name": nombre, "description": descripcion,
            "parameters": {"type": "object", "properties": propiedades or {}, "required": list(requeridas)}}


TEXTO = {"type": "string"}
HERRAMIENTAS = [
    _h("abrir_app", "Abre una aplicación instalada por su nombre (p. ej. Firefox, Spotify, Archivos).",
       {"nombre": TEXTO}, ["nombre"]),
    _h("abrir_enlace", "Abre una página web en el navegador.", {"url": TEXTO}, ["url"]),
    _h("abrir_carpeta", "Abre una carpeta (o un documento) del usuario: «descargas», «documentos» o una ruta.",
       {"ruta": TEXTO}, ["ruta"]),
    _h("listar_archivos", "Lista lo que hay en una carpeta del usuario.", {"ruta": TEXTO}, ["ruta"]),
    _h("leer_archivo", "Lee un archivo de texto del usuario (hasta 20 000 caracteres).", {"ruta": TEXTO}, ["ruta"]),
    _h("musica", "Controla la música que suena en el equipo o dice qué suena.",
       {"accion": {"type": "string", "enum": ["alternar", "reproducir", "pausar", "siguiente", "anterior", "que_suena"]}},
       ["accion"]),
    _h("mirar_pantalla", "Mira la pantalla del usuario y responde una pregunta sobre lo que se ve.",
       {"pregunta": TEXTO}, ["pregunta"]),
    _h("mirar_camara", "Saca UNA foto con la cámara y responde sobre ella. Solo si el usuario lo pide explícitamente.",
       {"pregunta": TEXTO}, ["pregunta"]),
    _h("generar_imagen", "Genera una imagen a partir de una descripción y la abre.", {"descripcion": TEXTO}, ["descripcion"]),
    _h("buscar_web", "Abre una búsqueda: web, youtube, musica (Spotify), repos (GitHub) o mapas. Úsala para recomendar "
       "música, sitios o repositorios sin inventar enlaces.",
       {"donde": {"type": "string", "enum": list(acciones.BUSCADORES)}, "consulta": TEXTO}, ["donde", "consulta"]),
    _h("anotar", "Guarda una nota en la carpeta de notas del usuario.", {"texto": TEXTO, "titulo": TEXTO}, ["texto"]),
    _h("buscar_notas", "Busca en las notas del usuario (Markdown, p. ej. Obsidian).", {"consulta": TEXTO}, ["consulta"]),
    _h("leer_nota", "Lee una nota de la carpeta de notas (ruta relativa a esa carpeta).", {"ruta": TEXTO}, ["ruta"]),
]
# las del cerebro, solo si el usuario ya lo creó («anotar» ya la tiene el asistente, en su carpeta de notas)
DEL_CEREBRO = {h["nombre"]: {"name": h["nombre"], "description": h["descripcion"], "parameters": h["parametros"]}
               for h in cerebro.HERRAMIENTAS if h["nombre"] != "anotar"}
FINALES = {"mirar_pantalla", "mirar_camara", "generar_imagen"}     # su resultado es la respuesta


def herramientas():
    return HERRAMIENTAS + (list(DEL_CEREBRO.values()) if cerebro.configurado() else [])
CAMARA = re.compile(r"c[aá]mara|camera|webcam|foto|photo|selfie", re.I)

# ---------------------------------------------------------------- atajos (0 tokens)

ABRIR = re.compile(r"^(?:oye\s+akari[, ]*)?(?:abre|abrir|ábreme|abreme|lanza|inicia|ejecuta|open|launch|start|run)\s+"
                   r"(?:la\s+app\s+(?:de\s+)?|el\s+programa\s+|la\s+aplicaci[oó]n\s+(?:de\s+)?|the\s+app\s+)?(.+?)[.!?]*$", re.I)
MUSICA = [
    (r"^(pausa|pon pausa|pausa la m[uú]sica|para la m[uú]sica|det[eé]n la m[uú]sica|pause|pause the music|stop the music)$", "pausar"),
    (r"^(reproduce|sigue|contin[uú]a|play|resume|pon la m[uú]sica|reanuda)( la m[uú]sica| the music)?$", "reproducir"),
    (r"^(siguiente|la siguiente|pasa la canci[oó]n|siguiente canci[oó]n|next|next song|skip)$", "siguiente"),
    (r"^(anterior|la anterior|canci[oó]n anterior|previous|previous song)$", "anterior"),
    (r"^(qu[eé] (canci[oó]n )?(suena|est[aá] sonando)|what'?s playing|what song is this)$", "que_suena"),
]
HORA = re.compile(r"^(qu[eé] hora es|me dices la hora|what time is it|what'?s the time)$", re.I)


def limpio(texto):
    return re.sub(r"[¿?¡!.,]+", "", " ".join(str(texto).split())).strip().lower()


def atajo(texto):
    """(respuesta, herramienta) si la orden se resuelve sin modelo; None si hay que preguntarle."""
    simple = re.sub(r"^(oye\s+)?akari[, ]*", "", limpio(texto))
    if HORA.match(simple):
        ahora = datetime.now()
        return t(f"Son las {ahora:%H:%M}.", f"It's {ahora:%H:%M}."), "hora"
    for patron, accion in MUSICA:
        if re.match(patron, simple):
            return acciones.musica(accion)[1], "musica"
    m = ABRIR.match(" ".join(str(texto).split()))
    if m:
        cosa = m.group(1).strip().strip("«»\"'")
        if re.match(r"^(https?://|www\.)\S+$|^[\w-]+\.(com|org|net|io|dev|es|mx|ar|co|cl|pe|app)(/\S*)?$", cosa, re.I):
            return acciones.abrir_enlace(cosa)[1], "abrir_enlace"
        if acciones.carpeta_conocida(cosa) or cosa.startswith(("~", "/")) or re.match(r"^[A-Za-z]:\\", cosa):
            return acciones.abrir_ruta(cosa)[1], "abrir_carpeta"
        ok, mensaje = acciones.abrir_app(cosa)
        if ok:
            return mensaje, "abrir_app"
    return None


# ---------------------------------------------------------------- modelo con herramientas

def _neutras_a_openai(herramientas):
    return [{"type": "function", "function": h} for h in herramientas]


def _neutras_a_anthropic(herramientas):
    return [{"name": h["name"], "description": h["description"], "input_schema": h["parameters"]} for h in herramientas]


def llamar_modelo(monitor, sistema, mensajes, herramientas, timeout=120):
    """Una vuelta del modelo. mensajes: formato del proveedor (se va armando con agregar_*).
    Devuelve (texto, llamadas=[{"id", "nombre", "args"}], mensaje_del_asistente)."""
    camino, modelo = monitor.elegido()
    if camino is None:
        raise ErrorIA(modelo)
    try:
        if camino == "ollama":
            cuerpo = {"model": modelo, "messages": [{"role": "system", "content": sistema}] + mensajes, "stream": False,
                      "think": False, "options": {"temperature": 0.3}}
            if herramientas:
                cuerpo["tools"] = _neutras_a_openai(herramientas)
            r = _pedir(f"{OLLAMA}/api/chat", cuerpo, timeout=timeout)
            m = r.get("message") or {}
            llamadas = [{"id": str(i), "nombre": c["function"]["name"], "args": _args(c["function"].get("arguments"))}
                        for i, c in enumerate(m.get("tool_calls") or [])]
            return _sin_pensar(m.get("content") or ""), llamadas, {"role": "assistant", "content": m.get("content") or "",
                                                                     **({"tool_calls": m["tool_calls"]} if m.get("tool_calls") else {})}
        if camino == "anthropic":
            cuerpo = {"model": modelo, "max_tokens": 1024, "system": sistema, "messages": mensajes}
            if herramientas:
                cuerpo["tools"] = _neutras_a_anthropic(herramientas)
            r = _pedir(f"{PROVEEDORES[camino]['base']}/messages", cuerpo, _cabeceras(camino, monitor.claves()[camino]), timeout)
            bloques = r.get("content") or []
            texto = "".join(b.get("text", "") for b in bloques if b.get("type") == "text")
            llamadas = [{"id": b["id"], "nombre": b["name"], "args": b.get("input") or {}} for b in bloques if b.get("type") == "tool_use"]
            return texto.strip(), llamadas, {"role": "assistant", "content": bloques}
        # formato OpenAI: OpenAI, Gemini, OpenRouter, Groq
        cuerpo = {"model": modelo, "messages": [{"role": "system", "content": sistema}] + mensajes}
        if herramientas:
            cuerpo["tools"] = _neutras_a_openai(herramientas)
        r = _pedir(f"{PROVEEDORES[camino]['base']}/chat/completions", cuerpo, _cabeceras(camino, monitor.claves()[camino]), timeout)
        m = ((r.get("choices") or [{}])[0]).get("message") or {}
        llamadas = [{"id": c.get("id") or str(i), "nombre": c["function"]["name"], "args": _args(c["function"].get("arguments"))}
                    for i, c in enumerate(m.get("tool_calls") or [])]
        crudo = {"role": "assistant", "content": m.get("content") or ""}
        if m.get("tool_calls"):
            crudo["tool_calls"] = m["tool_calls"]
        return _sin_pensar(m.get("content") or ""), llamadas, crudo
    except urllib.error.HTTPError as e:
        texto = _error(e)
        if e.code == 400 and herramientas and re.search(r"tool|function", texto, re.I):
            # el modelo no sabe usar herramientas (p. ej. gemma3:1b): se pregunta sin ellas
            return llamar_modelo(monitor, sistema, mensajes, [], timeout)
        raise ErrorIA(texto) from None
    except (OSError, ValueError) as e:
        raise ErrorIA(_error(e)) from None


def _args(valor):
    if isinstance(valor, dict):
        return valor
    try:
        datos = json.loads(valor or "{}")
        return datos if isinstance(datos, dict) else {}
    except ValueError:
        return {}


def _sin_pensar(texto):
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()


def mensaje_usuario(camino, texto):
    return {"role": "user", "content": texto}


def resultados(camino, llamadas, salidas):
    """Los mensajes con lo que devolvieron las herramientas, en el formato del proveedor."""
    if camino == "anthropic":
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": ll["id"], "content": s}
                                             for ll, s in zip(llamadas, salidas)]}]
    if camino == "ollama":
        return [{"role": "tool", "content": s, "tool_name": ll["nombre"]} for ll, s in zip(llamadas, salidas)]
    return [{"role": "tool", "tool_call_id": ll["id"], "content": s} for ll, s in zip(llamadas, salidas)]


# ---------------------------------------------------------------- asistente

def comillas(texto):
    """Texto como un solo argumento de la terminal (bash o PowerShell)."""
    if WINDOWS:
        return "'" + texto.replace("'", "''") + "'"
    return shlex.quote(texto)


class Asistente:
    def __init__(self, al_cambiar, modelos):
        self.al_cambiar = al_cambiar
        self.modelos = modelos
        self.voz = None                 # voz.Voz (la pone el servicio)
        self.pensando = False
        self.ocultar = False            # las cápsulas se esconden (antes de mirar la pantalla)
        self.lock = threading.Lock()
        self.historial = leer_json(HISTORIAL, [])
        if not isinstance(self.historial, list):
            self.historial = []
        self.claude = leer_json(CONFIG / "asistente-claude.json")      # {"sesion", "t"}
        self._registro = None           # threading.Timer que manda la charla al cerebro

    # ------------------------------------------------------------ ajustes y estado
    def ajustes(self):
        a = leer_json(AJUSTES)
        return {"donde": a.get("donde") if a.get("donde") in ("terminal", "fondo") else "fondo",
                "quien": a.get("quien") if a.get("quien") in ("claude", "local") else "local",
                "palabra_clave": bool(a.get("palabra_clave")), "voz_alta": bool(a.get("voz_alta")),
                "notas": a.get("notas") if isinstance(a.get("notas"), str) and Path(a.get("notas")).is_dir() else ""}

    def guardar_ajustes(self, cambios):
        a = leer_json(AJUSTES)
        for clave, valores in (("donde", ("terminal", "fondo")), ("quien", ("claude", "local"))):
            if cambios.get(clave) in valores:
                a[clave] = cambios[clave]
        for clave in ("palabra_clave", "voz_alta"):
            if isinstance(cambios.get(clave), bool):
                a[clave] = cambios[clave]
        if "notas" in cambios:
            a["notas"] = str(cambios["notas"] or "")
        escribir_json(AJUSTES, a)
        if self.voz:
            self.voz.revisar()
        self.al_cambiar()

    @property
    def estado(self):
        a = self.ajustes()
        voz = self.voz.estado if self.voz else {"instalada": False}
        hablando, oyendo = voz.get("hablando"), voz.get("escuchando")
        listo = self.modelos.estado.get("listo") if a["quien"] == "local" else bool(buscar("claude"))
        return {
            "estado": "pensando" if self.pensando else "hablando" if hablando else voz.get("fase") or ("escuchando" if oyendo else "pausa"),
            "ajustes": a, "listo": bool(listo),
            "motivo": "" if listo else (self.modelos.estado.get("motivo") if a["quien"] == "local"
                                        else t("No encontré Claude Code en este equipo.", "Claude Code wasn't found on this computer.")),
            "claude": bool(buscar("claude")), "ocultar": self.ocultar, "voz": voz,
            "historial": self.historial[:MAX_HISTORIAL],
        }

    def _anotar(self, entrada):
        with self.lock:
            self.historial.insert(0, entrada)
            self.historial = self.historial[:MAX_HISTORIAL]
            escribir_json(HISTORIAL, self.historial)
        self.al_cambiar()

    # ------------------------------------------------------------ acciones
    def accion(self, datos):
        accion = str(datos.get("accion"))
        if accion == "preguntar":
            texto = " ".join(str(datos.get("texto") or "").split())[:4000]
            if not texto:
                return False, "?"
            return self.preguntar(texto)
        if accion == "ajustes":
            self.guardar_ajustes(datos)
            return True, ""
        if accion == "elegir_notas":
            threading.Thread(target=self._elegir_notas, daemon=True).start()
            return True, ""
        if accion == "borrar":
            with self.lock:
                self.historial = []
                escribir_json(HISTORIAL, [])
            self.claude = {}
            escribir_json(CONFIG / "asistente-claude.json", {})
            self.al_cambiar()
            return True, ""
        if accion == "callar" and self.voz:
            self.voz.callar()
            return True, ""
        if self.voz and accion in ("instalar_voz",):
            return self.voz.instalar()
        return False, "?"

    def _elegir_notas(self):
        carpeta = elegir_carpeta(t("Carpeta de notas (p. ej. tu bóveda de Obsidian)", "Notes folder (e.g. your Obsidian vault)"))
        if carpeta:
            self.guardar_ajustes({"notas": carpeta})

    def preguntar(self, texto, por_voz=False):
        if self.pensando:
            return False, t("Espera, todavía estoy con lo anterior.", "Hold on, I'm still on the last one.")
        self.pensando = True
        self.al_cambiar()
        threading.Thread(target=self._responder, args=(texto, por_voz), daemon=True).start()
        return True, ""

    def _responder(self, texto, por_voz):
        a = self.ajustes()
        entrada = {"t": time.time(), "pregunta": texto, "respuesta": "", "quien": a["quien"], "via": "voz" if por_voz else "texto",
                   "herramientas": [], "error": False}
        try:
            rapido = atajo(texto) if a["quien"] == "local" or a["donde"] == "fondo" else None
            if rapido:
                entrada.update(respuesta=rapido[0], quien="akari", herramientas=[rapido[1]])
            elif a["donde"] == "terminal":
                entrada["respuesta"] = self._terminal(texto, a["quien"])
            elif a["quien"] == "claude":
                entrada["respuesta"] = self._claude(texto)
            else:
                entrada["respuesta"], entrada["herramientas"] = self._local(texto, a)
        except ErrorIA as e:
            entrada.update(respuesta=str(e), error=True)
        except Exception as e:      # noqa: BLE001 — el asistente no se cae por una pregunta
            entrada.update(respuesta=t("Algo falló: ", "Something failed: ") + str(e)[:200], error=True)
        finally:
            self.pensando = False
            self.ocultar = False
        self._anotar(entrada)
        self._registrar_luego()
        if a["voz_alta"] and self.voz and entrada["respuesta"]:
            self.voz.decir(entrada["respuesta"])

    def _registrar_luego(self):
        if self._registro:
            self._registro.cancel()
        self._registro = threading.Timer(REGISTRAR, self._registrar)
        self._registro.daemon = True
        self._registro.start()

    def _registrar(self):
        """La charla de ahora (preguntas con menos de CONTEXTO entre una y otra) como una sesión del cerebro."""
        if not cerebro.configurado():
            return
        with self.lock:
            charla = []
            for h in self.historial:
                if charla and charla[-1]["t"] - h["t"] > CONTEXTO:
                    break
                charla.append(h)
        charla = [h for h in reversed(charla) if not h.get("error")]
        if not charla:
            return
        mensajes = []
        for h in charla:
            mensajes += [{"rol": "usuario", "texto": h["pregunta"]}, {"rol": "asistente", "texto": h["respuesta"]}]
        try:        # mismo id mientras dure la charla: se reemplaza, no se repite
            memoria.registrar_asistente(int(charla[0]["t"]), mensajes, monitor_modelos=self.modelos)
        except Exception:       # noqa: BLE001 — la bitácora no tumba al asistente
            pass

    # ------------------------------------------------------------ caminos
    def _terminal(self, texto, quien):
        if quien == "local":
            camino, modelo = self.modelos.elegido()
            if camino == "ollama" and buscar("ollama"):
                ok = terminal(f"ollama run {comillas(modelo)} {comillas(texto)}", "akari")
                return t("Lo abrí en una terminal con Ollama.", "Opened it in a terminal with Ollama.") if ok else \
                    t("No encontré una terminal.", "No terminal found.")
            return self._local(texto, self.ajustes())[0]         # con una API no hay terminal: se responde aquí
        if not buscar("claude"):
            raise ErrorIA(t("No encontré Claude Code en este equipo.", "Claude Code wasn't found on this computer."))
        ok = terminal(f"claude {comillas(texto)}", "Claude Code")
        return t("Abrí Claude Code en una terminal.", "Opened Claude Code in a terminal.") if ok else \
            t("No encontré una terminal.", "No terminal found.")

    def _claude(self, texto):
        exe = buscar("claude")
        if not exe:
            raise ErrorIA(t("No encontré Claude Code en este equipo.", "Claude Code wasn't found on this computer."))
        orden = [exe, "-p", "--output-format", "json", "--permission-mode", "dontAsk", "--allowedTools", LECTURA_CLAUDE,
                 "--append-system-prompt", t("Respondes desde una burbuja del escritorio: sé breve (1 a 4 frases) y no "
                                             "modifiques archivos.", "You answer from a desktop bubble: be brief (1-4 "
                                             "sentences) and don't modify files.")]
        if self.claude.get("sesion") and time.time() - self.claude.get("t", 0) < RESUMIR_CLAUDE:
            orden += ["--resume", self.claude["sesion"]]
        try:
            # la pregunta va por stdin: así un texto que empieza con «-» no se confunde con una opción
            r = subprocess.run(orden, input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600, cwd=str(HOME), env=entorno_completo(), **SIN_VENTANA)
        except subprocess.TimeoutExpired:
            raise ErrorIA(t("Claude tardó demasiado.", "Claude took too long.")) from None
        try:
            datos = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise ErrorIA(((r.stderr or r.stdout).strip().splitlines() or [t("Claude no respondió.", "Claude didn't answer.")])[-1][:200]) from None
        if datos.get("session_id"):
            self.claude = {"sesion": datos["session_id"], "t": time.time()}
            escribir_json(CONFIG / "asistente-claude.json", self.claude)
        if datos.get("is_error"):
            raise ErrorIA(str(datos.get("result") or "Claude: error")[:300])
        return str(datos.get("result") or "").strip()

    def sistema(self, a):
        ahora = datetime.now()
        return t(
            f"Eres akari, un asistente de escritorio en {'Windows' if WINDOWS else 'Linux'}. Responde en español, breve (1 a 3 "
            f"frases) y sin tablas. Ahora es {DIAS[ahora.weekday()]} {ahora:%d/%m/%Y}, {ahora:%H:%M} (hora del equipo): "
            "usa esta hora, nunca otra. Usa las herramientas cuando hagan falta y nunca inventes lo que devolverían; si "
            "algo no se puede, dilo. "
            + ("La carpeta de notas está elegida." if a["notas"] else "Todavía no hay carpeta de notas elegida.")
            + (" Para encontrar archivos del usuario usa buscar_archivo antes que listar carpetas." if cerebro.configurado() else ""),
            f"You are akari, a desktop assistant on {'Windows' if WINDOWS else 'Linux'}. Answer in English, briefly (1-3 "
            f"sentences), no tables. It is now {DIAS[ahora.weekday()]} {ahora:%Y-%m-%d}, {ahora:%H:%M} (computer time): use "
            "this time, never another. Use the tools when needed and never make up what they would return; if something "
            "can't be done, say so. " + ("A notes folder is set." if a["notas"] else "No notes folder is set yet.")
            + (" To find the user's files use buscar_archivo before listing folders." if cerebro.configurado() else ""))

    def _contexto(self, camino):
        """Las preguntas recientes (para que entienda «y la otra», «ábrela»…)."""
        recientes = [h for h in self.historial[:6] if time.time() - h["t"] < CONTEXTO and not h.get("error")]
        mensajes = []
        for h in reversed(recientes):
            mensajes += [mensaje_usuario(camino, h["pregunta"]), {"role": "assistant", "content": h["respuesta"]}]
        return mensajes

    def _local(self, texto, a):
        camino, modelo = self.modelos.elegido()
        if camino is None:
            raise ErrorIA(t("Agrega una clave de API o usa un modelo local.", "Add an API key or use a local model."))
        mensajes = self._contexto(camino) + [mensaje_usuario(camino, texto)]
        usadas = []
        for _ in range(MAX_VUELTAS):
            respuesta, llamadas, crudo = llamar_modelo(self.modelos, self.sistema(a), mensajes, herramientas())
            if not llamadas:
                return respuesta or t("No sé qué responder.", "I don't know what to say."), usadas
            mensajes.append(crudo)
            salidas = []
            for ll in llamadas[:4]:
                usadas.append(ll["nombre"])
                salida, final = self.ejecutar(ll["nombre"], ll["args"], texto, a)
                if final:
                    return salida, usadas      # mirar la pantalla y compañía: se corta aquí
                salidas.append(salida)
            mensajes += resultados(camino, llamadas[:4], salidas)
        return t("Me enredé con tantos pasos. ¿Me lo pides de otra forma?", "I got tangled in too many steps. Ask me another way?"), usadas

    # ------------------------------------------------------------ herramientas
    def ejecutar(self, nombre, args, pregunta, a):
        """(texto para el modelo o para el usuario, final). final=True corta el turno con ese texto."""
        texto = lambda clave: str(args.get(clave) or "").strip()     # noqa: E731
        if nombre == "abrir_app":
            return acciones.abrir_app(texto("nombre"))[1], False
        if nombre == "abrir_enlace":
            return acciones.abrir_enlace(texto("url"))[1], False
        if nombre == "abrir_carpeta":
            return acciones.abrir_ruta(texto("ruta"))[1], False
        if nombre == "listar_archivos":
            return acciones.listar(texto("ruta")), False
        if nombre == "leer_archivo":
            return acciones.leer(texto("ruta")), False
        if nombre == "musica":
            accion = texto("accion")
            return acciones.musica(accion if accion in acciones.TECLAS or accion == "que_suena" else "alternar")[1], False
        if nombre == "buscar_web":
            return acciones.buscar_web(texto("donde"), texto("consulta"))[1], False
        if nombre == "anotar":
            return acciones.anotar(a["notas"], texto("texto"), texto("titulo"))[1], False
        if nombre == "buscar_notas":
            return acciones.buscar_notas(a["notas"], texto("consulta")), False
        if nombre == "leer_nota":
            if not a["notas"]:
                return t("No hay carpeta de notas.", "No notes folder."), False
            return acciones.leer(texto("ruta"), base=Path(a["notas"])), False
        if nombre == "mirar_pantalla":
            return self.mirar_pantalla(texto("pregunta") or pregunta), True
        if nombre == "mirar_camara":
            if not CAMARA.search(pregunta):
                return t("Solo miro la cámara si me lo pides.", "I only use the camera when you ask."), False
            return self.mirar_camara(texto("pregunta") or pregunta), True
        if nombre == "generar_imagen":
            return generar_imagen(self.modelos, texto("descripcion") or pregunta), True
        if nombre in DEL_CEREBRO:
            return cerebro.usar_herramienta(nombre, args, self.modelos), False
        return "?", False

    def _ver(self, imagen, pregunta, que):
        if not self.modelos.estado.get("vision_lista"):
            return t("Para mirar la pantalla o la cámara elige un modelo que vea imágenes en «Modelos de IA».",
                     "To look at the screen or camera, choose a model that sees images in “AI models”.")
        visto = preguntar(self.modelos, pregunta, imagen=imagen,
                          sistema=t(f"Miras {que} del usuario. Responde en español, breve y solo con lo que se ve.",
                                    f"You are looking at the user's {que}. Answer briefly, only with what is visible."))
        return visto

    def mirar_pantalla(self, pregunta):
        self.ocultar = True             # las cápsulas se esconden para no salir en la captura
        self.al_cambiar()
        time.sleep(OCULTAR)
        try:
            imagen = acciones.capturar_pantalla()
        finally:
            self.ocultar = False
            self.al_cambiar()
        if not imagen:
            return t("No pude capturar la pantalla (instala grim, spectacle o gnome-screenshot).",
                     "I couldn't take a screenshot (install grim, spectacle or gnome-screenshot).")
        return self._ver(imagen, pregunta, t("la pantalla", "screen"))     # la imagen no se guarda en ningún lado

    def mirar_camara(self, pregunta):
        imagen, motivo = acciones.foto_camara()
        if not imagen:
            return motivo
        return self._ver(imagen, pregunta, t("la cámara", "camera"))


# ---------------------------------------------------------------- imágenes y carpetas

def generar_imagen(monitor, descripcion):
    """Con la clave de OpenAI (gpt-image-1); la imagen queda en Imágenes/akari y se abre."""
    clave = monitor.claves().get("openai")
    if not clave:
        return t("Para generar imágenes hace falta una clave de OpenAI en «Modelos de IA».",
                 "Generating images needs an OpenAI key in “AI models”.")
    import base64
    try:
        r = _pedir("https://api.openai.com/v1/images/generations",
                   {"model": "gpt-image-1", "prompt": descripcion[:3000], "size": "1024x1024", "n": 1},
                   _cabeceras("openai", clave), timeout=180)
        datos = base64.b64decode(r["data"][0]["b64_json"])
    except (OSError, ValueError, KeyError, IndexError) as e:
        return t("No se pudo generar la imagen: ", "Couldn't generate the image: ") + _error(e)
    carpeta = (acciones.carpeta_conocida("imagenes") or HOME / "Pictures") / "akari"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w -]+", "", descripcion)[:40].strip() or "imagen"
    archivo = carpeta / f"{nombre} {time.strftime('%Y-%m-%d %H.%M.%S')}.png"
    archivo.write_bytes(datos)
    acciones.abrir(archivo)
    return t(f"Listo: la guardé en Imágenes/akari/{archivo.name} y la abrí.", f"Done: saved it to Pictures/akari/{archivo.name} and opened it.")


def elegir_carpeta(titulo):
    from .comun import correr, powershell, tiene
    import os
    if WINDOWS:
        script = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  "$d.Description = $env:AKARI_TITULO; [Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                  "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }")
        return (powershell(script, 3600, {**os.environ, "AKARI_TITULO": titulo}) or "").strip()
    kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if tiene("kdialog") and (kde or not tiene("zenity")):
        ok, salida = correr(["kdialog", "--title", titulo, "--getexistingdirectory", str(HOME)], 3600)
    elif tiene("zenity"):
        ok, salida = correr(["zenity", "--file-selection", "--directory", f"--title={titulo}", f"--filename={HOME}/"], 3600)
    else:
        return ""
    return salida.strip() if ok else ""
