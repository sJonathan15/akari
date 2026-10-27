"""Recorrido de bienvenida: se aprende usándolo, sin videos ni documentos (uno solo para Linux y Windows).

La primera vez que arranca akari (y al actualizar a una versión con pasos nuevos, solo esos) se activa.
El estado vive aquí, en el servicio: cada paso dice qué grupo y pieza abrir; esa cápsula (QML) o
burbuja (web) se abre sola y muestra arriba una tarjeta («2 de 9», título, 1–2 frases, Anterior /
Siguiente / Saltar) y resalta el control del que se habla. Se repite con `akari recorrido`, desde el
panel («Ver recorrido») o desde la bandeja (POST /api/recorrido {"accion": "reiniciar"}).

GET  /api/recorrido                         el estado (también va en /api/estado → "recorrido")
POST /api/recorrido {accion: siguiente|anterior|saltar|reiniciar|ir|voz|cerrar_primeros, paso?, activo?}

Además, la lista «Primeros pasos» (modelo elegido, una conversión, una pregunta, cerebro creado) que
el panel muestra hasta que esté completa o se cierre.
"""
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from . import VERSION, grupos
from .comun import CONFIG, DATOS, WINDOWS, buscar, escribir_json, leer_json, powershell, t, tiene

ESTADO = CONFIG / "recorrido.json"
VOCES = DATOS / "voces"            # modelos de Piper (*.onnx) para «Leérmelo en voz alta»


def _version(texto):
    try:
        return tuple(int(x) for x in str(texto).split("."))
    except ValueError:
        return (0,)


# grupo/pieza = qué se abre; resalta = selector CSS (web) o clave (QML) del control del que se habla;
# desde = versión de akari que trajo el paso (al actualizar se muestran solo los nuevos);
# requiere = pieza que tiene que existir (si no, el paso no se muestra).
PASOS = [
    {"id": "bienvenida", "grupo": "ia", "pieza": "uso", "resalta": "", "desde": "0.1.0",
     "titulo": ("Hola, soy akari", "Hi, I'm akari"),
     "texto": ("Unas cápsulas que te ayudan con tu IA, tus aparatos y tus archivos. Todo lo que ves se queda en tu equipo.",
               "Capsules that help with your AI, your devices and your files. Everything you see stays on your computer.")},
    {"id": "mover", "grupo": "equipo", "pieza": "dispositivos", "resalta": "cabecera", "desde": "0.1.0",
     "titulo": ("Ponlas donde quieras", "Put them anywhere"),
     "texto": ("Arrástralas desde la cabecera; contra un borde se vuelven pestaña. Doble clic las devuelve a su sitio, y puedes ocultar las que no uses.",
               "Drag them by the header; against a side edge they become a tab. Double-click puts them back, and you can hide the ones you don't use.")},
    {"id": "ia", "grupo": "ia", "pieza": "uso", "resalta": "#limites", "desde": "0.1.0",
     "titulo": ("Tus límites de IA", "Your AI limits"),
     "texto": ("Cuánto te queda de Claude Code y Codex, y la ventana de 5 horas: cuándo se renueva y si a este ritmo se acaba antes.",
               "How much Claude Code and Codex you have left, and the 5-hour window: when it renews and whether you'll run out first."),
     "sin_ia": ("No encontré Claude Code ni Codex: es opcional. Si un día los usas, aquí verás cuánto te queda.",
                "Neither Claude Code nor Codex found: it's optional. If you use them one day, your limits show up here.")},
    {"id": "modelos", "grupo": "ia", "pieza": "modelos", "resalta": "#modelos-ia .sub-pestanas", "desde": "0.1.0",
     "titulo": ("Elige con qué piensa akari", "Choose what akari thinks with"),
     "texto": ("Un modelo en tu equipo (gratis, sin internet) o una clave de API. Puedes dejarlo para después.",
               "A model on your computer (free, offline) or an API key. You can leave it for later.")},
    {"id": "dispositivos", "grupo": "equipo", "pieza": "dispositivos", "resalta": "#d-lista", "desde": "0.1.0",
     "titulo": ("Tus aparatos", "Your devices"),
     "texto": ("La batería del ratón, los audífonos, el teclado y el celular. Te aviso cuando se esté acabando.",
               "Battery for your mouse, headphones, keyboard and phone. I'll warn you when it's running low.")},
    {"id": "habilidades", "grupo": "ia", "pieza": "habilidades", "resalta": "#hab-contenido .rejilla", "desde": "0.1.0",
     "titulo": ("Habilidades y herramientas", "Skills and tools"),
     "texto": ("Cosas nuevas que tu IA aprende a hacer (leer PDF, hacer presentaciones…). Instala una recomendada con un clic, si quieres.",
               "New things your AI learns to do (read PDFs, make slides…). Install a recommended one with one click, if you like.")},
    {"id": "documentos", "grupo": "archivos", "pieza": "documentos", "resalta": ".doc-soltar", "desde": "0.1.0",
     "titulo": ("Documentos a Markdown", "Documents to Markdown"),
     "texto": ("Suelta aquí un PDF para probar: sale un .md junto al original, listo para tu IA.",
               "Drop a PDF here to try it: a .md appears next to the original, ready for your AI.")},
    {"id": "asistente", "grupo": "ia", "pieza": "asistente", "resalta": "", "desde": "0.1.0", "requiere": "asistente",
     "titulo": ("Tu asistente", "Your assistant"),
     "texto": ("Pruébalo con «¿qué hora es?» o «abre la calculadora».", "Try “what time is it?” or “open the calculator”.")},
    {"id": "cerebro", "grupo": "archivos", "pieza": "cerebro", "resalta": "[data-cer=\"crear\"]", "desde": "0.1.0",
     "titulo": ("Tu cerebro: no mueve, renombra ni cambia tus archivos", "Your brain never moves, renames or changes your files"),
     "texto": ("Solo arma un mapa de tu computadora y una memoria de lo que haces con la IA, para que tu IA te entienda.",
               "It only builds a map of your computer and a memory of what you do with AI, so your AI understands you."),
     "listo": ("Tu cerebro ya está creado: búscalo aquí o pregúntale a tu IA «¿dónde dejé…?».",
               "Your brain is ready: search here or ask your AI “where did I leave…?”.")},
    {"id": "listo", "grupo": "ia", "pieza": "uso", "resalta": "", "desde": "0.1.0",
     "titulo": ("¡Listo!", "All set!"),
     "texto": ("Repite este recorrido desde el panel («Ver recorrido») o con «akari recorrido». Las actualizaciones llegan solas.",
               "Replay this tour from the panel (“See tour”) or with “akari recorrido”. Updates arrive on their own.")},
]


def _piezas():
    return set(grupos.GRUPO_DE)


class Recorrido:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        d = leer_json(ESTADO)
        if not d:                           # primera vez después de instalar
            d = {"activo": True, "paso": PASOS[0]["id"], "solo": None, "visto": VERSION, "hechos": {}}
            escribir_json(ESTADO, d)
        elif _version(d.get("visto", "0")) < _version(VERSION):
            nuevos = [p["id"] for p in PASOS if _version(p["desde"]) > _version(d.get("visto", "0"))]
            d["visto"] = VERSION
            if nuevos:                      # al actualizar: solo los pasos nuevos
                d.update(activo=True, paso=nuevos[0], solo=nuevos)
            escribir_json(ESTADO, d)
        self.d = d

    def _guardar(self):
        escribir_json(ESTADO, self.d)
        self.al_cambiar()

    def pasos(self):
        hay = _piezas()
        lista = [p for p in PASOS if not p.get("requiere") or p["requiere"] in hay]
        if self.d.get("solo"):
            lista = [p for p in lista if p["id"] in self.d["solo"]] or lista
        return lista

    def _indice(self):
        ids = [p["id"] for p in self.pasos()]
        return ids.index(self.d.get("paso")) if self.d.get("paso") in ids else 0

    # ------------------------------------------------------------ estado
    def estado(self, e=None):
        """e = el resto de /api/estado (para los textos que dependen de lo que hay y los primeros pasos)."""
        e = e or {}
        lista = self.pasos()
        salida = {"activo": bool(self.d.get("activo")), "voz": bool(self.d.get("voz")), "voz_disponible": voz_disponible(),
                  "primeros": self.primeros(e)}
        if not salida["activo"] or not lista:
            salida["activo"] = False
            return salida
        i = self._indice()
        p = lista[i]
        texto = p["texto"]
        if p["id"] == "ia" and e.get("ia") is not None and not ((e.get("ia") or {}).get("claude") or (e.get("ia") or {}).get("codex")):
            texto = p["sin_ia"]
        if p["id"] == "cerebro" and (e.get("cerebro") or {}).get("configurado"):
            texto = p["listo"]
        salida.update(n=i + 1, total=len(lista), paso={
            "id": p["id"], "grupo": p["grupo"], "pieza": p["pieza"], "resalta": p["resalta"],
            "titulo": t(*p["titulo"]), "texto": t(*texto), "acciones": self._acciones(p["id"], e)})
        return salida

    def _acciones(self, ident, e):
        """Botones propios del paso: {texto, ruta, cuerpo} (se manda tal cual) o {texto, pieza} (abre otra)."""
        if ident == "modelos":
            M = e.get("modelos") or {}
            if M.get("listo"):
                return []
            sugerido = next((r["id"] for r in M.get("recomendados", []) if r.get("sugerido") == "texto"), None)
            acciones = []
            if sugerido and (M.get("ollama") or {}).get("estado") == "activo":
                acciones.append({"texto": t(f"En mi equipo (gratis): {sugerido}", f"On my computer (free): {sugerido}"),
                                 "ruta": "/api/modelos", "cuerpo": {"accion": "descargar", "modelo": sugerido, "usar": True},
                                 "principal": True})
            elif (M.get("ollama") or {}).get("estado") == "no_instalado":
                acciones.append({"texto": t("En mi equipo (gratis): instalar Ollama", "On my computer (free): install Ollama"),
                                 "ruta": "/api/modelos", "cuerpo": {"accion": "instalar_ollama"}, "principal": True})
            acciones.append({"texto": t("Pegar una clave", "Paste a key"), "pieza": "modelos", "pestana": "api"})
            return acciones
        if ident == "habilidades":
            H = e.get("habilidades") or {}
            libre = next((r for r in H.get("recomendadas", []) if r.get("agentes") and not r.get("instalada_en")), None)
            if libre:
                return [{"texto": t(f"Instalar «{libre['nombre']}»", f"Install “{libre['nombre']}”"), "ruta": "/api/habilidades",
                         "cuerpo": {"id": libre["id"], "accion": "instalar"}, "principal": True}]
        if ident == "cerebro" and not (e.get("cerebro") or {}).get("configurado"):
            return [{"texto": t("Crear mi cerebro", "Create my brain"), "pulsar": "[data-cer=\"crear\"]", "principal": True,
                     "ruta": "/api/cerebro", "cuerpo": {"accion": "configurar", "carpetas": [str(Path.home())]}}]
        return []

    def primeros(self, e):
        """«Primeros pasos»: lo que ya hizo (o None si se cerró o está todo hecho)."""
        if self.d.get("primeros_cerrado"):
            return None
        docs = (e.get("documentos") or {}).get("trabajos", []) + (e.get("audio") or {}).get("trabajos", [])
        hechos = dict(self.d.get("hechos") or {})
        lista = [
            {"id": "modelo", "texto": t("Elegir un modelo de IA", "Choose an AI model"), "pieza": "modelos",
             "hecho": bool((e.get("modelos") or {}).get("listo"))},
            {"id": "conversion", "texto": t("Convertir un documento o un audio", "Convert a document or an audio"),
             "pieza": "documentos", "hecho": any(x.get("estado") == "listo" for x in docs) or bool(hechos.get("conversion"))},
            {"id": "pregunta", "texto": t("Hacer una pregunta", "Ask a question"),
             "pieza": "asistente" if "asistente" in _piezas() else "cerebro", "hecho": bool(hechos.get("pregunta"))},
            {"id": "cerebro", "texto": t("Crear tu cerebro", "Create your brain"), "pieza": "cerebro",
             "hecho": bool((e.get("cerebro") or {}).get("configurado"))},
        ]
        if lista[1]["hecho"] and not hechos.get("conversion"):       # que no se olvide al vaciar la lista
            self.d.setdefault("hechos", {})["conversion"] = True
            escribir_json(ESTADO, self.d)
        return None if all(x["hecho"] for x in lista) else lista

    def marcar(self, cual):
        """Lo que no se ve en el estado (p. ej. «hizo una pregunta»): lo anotan el asistente y el cerebro."""
        if not (self.d.get("hechos") or {}).get(cual):
            self.d.setdefault("hechos", {})[cual] = True
            self._guardar()

    # ------------------------------------------------------------ acciones
    def accion(self, datos):
        accion = str(datos.get("accion"))
        lista = self.pasos()
        i = self._indice()
        if accion == "siguiente":
            if i + 1 >= len(lista):
                self.d.update(activo=False, solo=None)
            else:
                self.d["paso"] = lista[i + 1]["id"]
        elif accion == "anterior":
            self.d["paso"] = lista[max(0, i - 1)]["id"]
        elif accion == "saltar":
            self.d.update(activo=False, solo=None)
        elif accion == "reiniciar":
            self.d.update(activo=True, solo=None, paso=PASOS[0]["id"])
        elif accion == "ir" and datos.get("paso") in [p["id"] for p in lista]:
            self.d.update(activo=True, paso=datos["paso"])
        elif accion == "voz":
            self.d["voz"] = bool(datos.get("activo"))
        elif accion == "cerrar_primeros":
            self.d["primeros_cerrado"] = True
        else:
            return False, "?"
        self._guardar()
        if self.d.get("voz") and self.d.get("activo") and accion in ("siguiente", "anterior", "reiniciar", "ir", "voz"):
            p = next((x for x in self.pasos() if x["id"] == self.d["paso"]), None)
            if p:
                leer_en_voz_alta(f"{t(*p['titulo'])}. {t(*p['texto'])}")
        return True, ""


# ---------------------------------------------------------------- voz (Piper, opcional)

def _voz():
    """(programa piper, modelo .onnx) si hay voz instalada; si no, None."""
    piper = buscar("piper")
    if not piper or not VOCES.is_dir():
        return None
    idioma = t("es", "en")
    modelos = sorted(VOCES.glob("*.onnx"))
    elegido = next((m for m in modelos if m.name.startswith(idioma)), modelos[0] if modelos else None)
    return (piper, elegido) if elegido else None


def voz_disponible():
    return _voz() is not None


def leer_en_voz_alta(texto):
    voz = _voz()
    if not voz:
        return False

    def trabajo():
        with tempfile.TemporaryDirectory(prefix="akari-voz-") as tmp:
            wav = os.path.join(tmp, "paso.wav")
            try:
                subprocess.run([voz[0], "--model", str(voz[1]), "--output_file", wav], input=texto.encode("utf-8"),
                               capture_output=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired):
                return
            if not os.path.exists(wav):
                return
            if WINDOWS:
                powershell("(New-Object Media.SoundPlayer $env:AKARI_WAV).PlaySync()", 120, {**os.environ, "AKARI_WAV": wav})
                return
            for reproductor in ("pw-play", "paplay", "aplay"):
                if tiene(reproductor):
                    subprocess.run([reproductor, wav], capture_output=True, timeout=120)
                    return
    threading.Thread(target=trabajo, daemon=True).start()
    return True
