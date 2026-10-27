"""Audio y video → Markdown: la transcripción queda en un .md junto al original (Linux y Windows).

Dos caminos, como los modelos de IA:
  * en el equipo, con faster-whisper (entorno «voz» de extras.py, se instala con un botón):
    large-v3-turbo en una tarjeta NVIDIA (int8_float16), si no small en la CPU (int8). El modelo
    corre en un proceso aparte (recursos/transcribir.py) que termina con cada archivo: no ocupa
    memoria mientras no hay nada que transcribir;
  * con la clave de Groq u OpenAI que el usuario guardó en «Modelos de IA» (Whisper por API).

Whisper inventa en los silencios y en la música: `limpiar()` quita los segmentos dudosos (mucha
probabilidad de silencio, poca confianza o texto muy repetitivo), las frases típicas de subtítulos
(«gracias por ver», «suscríbete»), el eco del initial_prompt y los bucles.

Reuniones (solo Linux, con pw-record o parecord): graba el micrófono y lo que suena en el equipo,
los mezcla con ffmpeg y lo transcribe al parar.
"""
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from . import extras
from .comun import CACHE, CONFIG, DATOS, RAIZ, SIN_VENTANA, WINDOWS, abrir, escribir_json, leer_json, notificar, t, tiene
from .documentos import a_ruta, carpeta_documentos, destino_para, elegir_archivos, nombre_seguro

HISTORIAL = CONFIG / "audio.json"
SUBIDOS = CACHE / "audio"
GRABACIONES = CACHE / "reuniones"
MODELOS_WHISPER = DATOS / "whisper"
SCRIPT = RAIZ / "akari" / "recursos" / "transcribir.py"
ENTORNO, PARTE = "voz", "transcribir"
MAX_HISTORIAL = 30
LIMITE_API = 24 * 2**20                 # OpenAI y Groq aceptan hasta 25 MB por archivo
TROZO_API = 20 * 60                     # si no cabe ni comprimido, en trozos de 20 min
FORMATOS_API = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".oga", ".opus", ".wav", ".webm", ".flac"}

AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".flac", ".aac", ".wma", ".amr", ".mpga", ".mpeg"}
VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".3gp", ".wmv"}
EXTENSIONES = AUDIO | VIDEO

# Whisper por API: Groq (más rápido y barato) primero
APIS = {"groq": ("https://api.groq.com/openai/v1", "whisper-large-v3-turbo"),
        "openai": ("https://api.openai.com/v1", "whisper-1")}


def es_audio(ruta):
    return Path(str(ruta)).suffix.lower() in EXTENSIONES


def nvidia():
    """Nombre de la tarjeta NVIDIA (para usar CUDA) o ""."""
    if not tiene("nvidia-smi"):
        return ""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True,
                           text=True, timeout=10, **SIN_VENTANA)
        return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def paquetes(gpu):
    base = ["faster-whisper>=1.1", "av<19"]    # PyAV 19 quitó un argumento que faster-whisper 1.2 usa
    # ctranslate2 4.5+ usa CUDA 12 + cuDNN 9, que pip trae sin instalar nada en el sistema
    return base + (["nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*"] if gpu else [])


def ffmpeg():
    encontrado = shutil.which("ffmpeg")
    if not encontrado and WINDOWS:
        enlace = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if enlace.exists():
            return str(enlace)
    return encontrado


def prompt_inicial():
    # da puntuación y el estilo del idioma; su eco se filtra en limpiar()
    return t("Hola. Esta es una conversación en español, con buena puntuación.",
             "Hello. This is a conversation in English, with proper punctuation.")


# ---------------------------------------------------------------- limpieza

FRASES_FALSAS = [
    # siempre inventadas (créditos de subtítulos que Whisper aprendió de YouTube)
    (r"subt[ií]tulos? (realizados? )?(por|de) la comunidad de amara", True),
    (r"amara\.? ?org", True),
    (r"subt[ií]tulos? (por|realizados por|hechos por)\b", True),
    (r"^(por favor,? )?suscr[ií]bete( al canal)?", True),
    (r"dale (a )?like y suscr[ií]bete", True),
    (r"(please )?(like and )?subscribe( to (my|the|our) channel)?$", True),
    (r"subtitles by the amara", True),
    (r"transcribed by|transcription by", True),
    # inventadas casi siempre, pero también se dicen de verdad: solo si el segmento es dudoso o el último
    (r"^(muchas )?gracias por (ver|mirar|su atenci[oó]n|escuchar|vernos)( (el|este) (video|v[ií]deo))?$", False),
    (r"^thank(s| you) (so much )?for watching( this video)?$", False),
    (r"^thank(s| you) for listening$", False),
    (r"^(muchas )?gracias$", False),
    (r"^thank you$", False),
    (r"^nos vemos en (el )?pr[oó]ximo (video|v[ií]deo)$", False),
    (r"^see you (in the )?next (video|time)$", False),
]


def normalizar(texto):
    texto = unicodedata.normalize("NFKC", texto or "").lower()
    texto = re.sub(r"[¡!¿?.,;:…\"'«»()\[\]\-–—♪♫*]+", " ", texto)
    return " ".join(texto.split())


def sin_repeticiones(texto):
    """«no sé no sé no sé no sé no sé» → «no sé»: una frase repetida 3+ veces seguidas queda una."""
    return re.sub(r"\b(.{2,80}?)(?:[\s,.]+\1\b){2,}", r"\1", texto, flags=re.I)


def dudoso(s):
    return s.get("no_speech_prob", 0) > 0.4 or s.get("avg_logprob", 0) < -0.8


def limpiar(segmentos, prompt=""):
    """Quita lo que Whisper suele inventar. segmentos: [{inicio, fin, texto, no_speech_prob,
    avg_logprob, compression_ratio}] (los tres últimos pueden faltar)."""
    eco = normalizar(prompt)
    salida, anterior = [], None
    for i, s in enumerate(segmentos):
        texto = sin_repeticiones((s.get("texto") or "").strip())
        norma = normalizar(texto)
        if not norma:
            continue
        nsp, alp, cr = s.get("no_speech_prob", 0), s.get("avg_logprob", 0), s.get("compression_ratio", 1)
        # 1. lo que el propio Whisper marca como silencio o como poco probable
        if cr > 2.4 or (nsp > 0.6 and alp < -0.5) or alp < -1.2 or nsp > 0.9:
            continue
        # 2. frases de subtítulos de YouTube
        ultimo = i >= len(segmentos) - 2
        if any(re.search(patron, norma) and (siempre or ultimo or dudoso(s)) for patron, siempre in FRASES_FALSAS):
            continue
        # 3. el eco de las instrucciones (initial_prompt)
        if eco and len(norma) >= 8 and (norma in eco or SequenceMatcher(None, norma, eco).ratio() > 0.75):
            continue
        # 4. bucles: el mismo segmento una y otra vez (se deja el primero)
        if anterior is not None and (norma == anterior or SequenceMatcher(None, norma, anterior).ratio() > 0.9):
            continue
        anterior = norma
        salida.append({**s, "texto": texto})
    return salida


# ---------------------------------------------------------------- markdown

def reloj(seg):
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parrafos(segmentos, pausa=2.0, largo=60.0):
    """Une los segmentos en párrafos: uno nuevo tras una pausa o cada ~minuto."""
    grupos = []
    for s in segmentos:
        if grupos and s["inicio"] - grupos[-1]["fin"] < pausa and s["fin"] - grupos[-1]["inicio"] < largo:
            grupos[-1]["texto"] += " " + s["texto"]
            grupos[-1]["fin"] = s["fin"]
        else:
            grupos.append({"inicio": s["inicio"], "fin": s["fin"], "texto": s["texto"]})
    return grupos


def a_markdown(nombre, segmentos, via, duracion=None):
    duracion = duracion or (segmentos[-1]["fin"] if segmentos else 0)
    cabeza = (f"# {Path(nombre).stem}\n\n> {t('Transcripción de', 'Transcript of')} `{nombre}` · {reloj(duracion)} · "
              f"{time.strftime('%Y-%m-%d')} · {via}\n\n")
    if not segmentos:
        return cabeza + t("_(No se oye a nadie hablar.)_\n", "_(No speech found.)_\n")
    return cabeza + "\n\n".join(f"**[{reloj(p['inicio'])}]** {p['texto']}" for p in parrafos(segmentos)) + "\n"


# ---------------------------------------------------------------- API

def _multipart(campos, nombre, datos):
    limite = "akari" + uuid.uuid4().hex
    cuerpo = b""
    for k, v in campos.items():
        cuerpo += f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    cuerpo += (f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
               f"Content-Type: application/octet-stream\r\n\r\n").encode() + datos + f"\r\n--{limite}--\r\n".encode()
    return cuerpo, f"multipart/form-data; boundary={limite}"


def transcribir_api(proveedor, clave, archivo, prompt="", idioma=""):
    """[{inicio, fin, texto, …}] de un archivo de hasta 25 MB con Whisper por API."""
    base, modelo = APIS[proveedor]
    campos = {"model": modelo, "response_format": "verbose_json", "temperature": "0"}
    if prompt:
        campos["prompt"] = prompt
    if idioma:
        campos["language"] = idioma
    cuerpo, tipo = _multipart(campos, Path(archivo).name, Path(archivo).read_bytes())
    req = urllib.request.Request(f"{base}/audio/transcriptions", data=cuerpo,
                                 headers={"Content-Type": tipo, "Authorization": f"Bearer {clave}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        datos = json.loads(r.read() or b"{}")
    segs = datos.get("segments") or []
    if not segs and datos.get("text"):
        segs = [{"start": 0, "end": datos.get("duration") or 0, "text": datos["text"]}]
    return [{"inicio": s.get("start", 0), "fin": s.get("end", 0), "texto": (s.get("text") or "").strip(),
             "no_speech_prob": s.get("no_speech_prob", 0), "avg_logprob": s.get("avg_logprob", 0),
             "compression_ratio": s.get("compression_ratio", 1)} for s in segs]


def preparar_para_api(archivo, tmp):
    """Lista de (archivo, desfase en s) que la API acepta: el original si se puede; si no, el audio
    en Opus mono (≈11 MB por hora) y, si aun así no cabe, en trozos."""
    archivo = Path(archivo)
    if archivo.suffix.lower() in FORMATOS_API and archivo.stat().st_size <= LIMITE_API:
        return [(archivo, 0)]
    exe = ffmpeg()
    if not exe:
        raise RuntimeError(t("Para videos o audios grandes por API hace falta ffmpeg.",
                             "Videos or large audio files need ffmpeg to use the API."))
    comprimido = Path(tmp) / "audio.ogg"
    _ffmpeg([exe, "-y", "-i", str(archivo), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k",
             str(comprimido)])
    if comprimido.stat().st_size <= LIMITE_API:
        return [(comprimido, 0)]
    _ffmpeg([exe, "-y", "-i", str(comprimido), "-f", "segment", "-segment_time", str(TROZO_API), "-c", "copy",
             str(Path(tmp) / "trozo%03d.ogg")])
    return [(p, i * TROZO_API) for i, p in enumerate(sorted(Path(tmp).glob("trozo*.ogg")))]


def _ffmpeg(orden):
    r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                       **SIN_VENTANA)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + ((r.stderr or "").strip().splitlines() or ["?"])[-1][:200])


# ---------------------------------------------------------------- reuniones (Linux)

def grabadora():
    """Con qué se graba el micrófono y lo que suena: 'parecord', 'pw-record' o None."""
    if WINDOWS:
        return None
    return "parecord" if tiene("parecord") else "pw-record" if tiene("pw-record") else None


def ordenes_grabar(cual, carpeta):
    """Dos grabaciones a la vez: el micrófono y el monitor de la salida de sonido."""
    mic, sistema = carpeta / "microfono.wav", carpeta / "sistema.wav"
    if cual == "parecord":
        comun = ["parecord", "--file-format=wav", "--rate=16000", "--channels=1"]
        return [comun + ["--device=@DEFAULT_SOURCE@", str(mic)], comun + ["--device=@DEFAULT_MONITOR@", str(sistema)]]
    comun = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
    return [comun + [str(mic)], comun + ["-P", "{ stream.capture.sink=true }", str(sistema)]]


# ---------------------------------------------------------------- transcriptor

class Transcriptor:
    def __init__(self, al_cambiar, modelos):
        self.al_cambiar = al_cambiar
        self.modelos = modelos              # MonitorModelos: claves de API y preguntar() para resumir
        self.lock = threading.Lock()
        self.cola = queue.Queue()
        self.gpu = nvidia()
        self.instalacion = ""
        self.eligiendo = False
        self.grabacion = None               # {"desde", "carpeta", "procesos"}
        self.proceso = None
        self.trabajos = leer_json(HISTORIAL, [])
        if not isinstance(self.trabajos, list):
            self.trabajos = []
        for tr in self.trabajos:
            if tr.get("estado") not in ("listo", "error"):
                tr.update(estado="error", mensaje=t("Se interrumpió (akari se reinició).", "Interrupted (akari restarted)."))
            if tr.get("resumen") == "haciendo":
                tr["resumen"] = None
        threading.Thread(target=self._trabajar, daemon=True).start()

    # ------------------------------------------------------------ ajustes y estado
    def ajustes(self):
        a = leer_json(CONFIG / "audio-ajustes.json")
        return {"modo": a.get("modo") if a.get("modo") in ("auto", "local", "api") else "auto",
                "resumir": bool(a.get("resumir"))}

    def api(self):
        claves = self.modelos.claves()
        return next((p for p in APIS if claves.get(p)), None)

    def modelo_local(self):
        return ("large-v3-turbo", "cuda", "int8_float16") if self.gpu else ("small", "cpu", "int8")

    def camino(self):
        """'local', el proveedor de la API, o None si no hay ninguno."""
        a, local, api = self.ajustes(), extras.python_de(ENTORNO, PARTE) is not None, self.api()
        if a["modo"] == "local":
            return "local" if local else None
        if a["modo"] == "api":
            return api
        return "local" if local else api

    @property
    def estado(self):
        a, api = self.ajustes(), self.api()
        with self.lock:
            trabajos = [dict(x) for x in self.trabajos[:MAX_HISTORIAL]]
        return {
            "listo_local": extras.python_de(ENTORNO, PARTE) is not None,
            "instalando": extras.instalando(ENTORNO),
            "error_instalacion": self.instalacion,
            "gpu": self.gpu, "modelo_local": self.modelo_local()[0],
            "api": api, "api_nombre": {"groq": "Groq", "openai": "OpenAI"}.get(api, ""),
            "modo": a["modo"], "resumir": a["resumir"], "usa": self.camino(),
            "ia_lista": bool(self.modelos.estado.get("listo")),
            "ffmpeg": ffmpeg() is not None, "eligiendo": self.eligiendo,
            "grabacion": {"disponible": grabadora() is not None,
                          "desde": self.grabacion["desde"] if self.grabacion else None},
            "trabajos": trabajos,
        }

    def _cambio(self):
        with self.lock:
            escribir_json(HISTORIAL, self.trabajos[:MAX_HISTORIAL])
        self.al_cambiar()

    def _buscar(self, ident):
        return next((x for x in self.trabajos if x["id"] == ident), None)

    def _encolar(self, origen, nombre, subido=False):
        tr = {"id": uuid.uuid4().hex[:8], "origen": str(origen), "nombre": nombre, "salida": "", "subido": subido,
              "estado": "cola", "pct": None, "mensaje": "", "via": "", "resumen": None, "fecha": time.time()}
        with self.lock:
            self.trabajos.insert(0, tr)
            self.trabajos = self.trabajos[:MAX_HISTORIAL]
        self._cambio()
        self.cola.put(tr["id"])

    # ------------------------------------------------------------ acciones
    def accion(self, datos):
        accion = str(datos.get("accion"))
        if accion == "instalar":
            threading.Thread(target=self._instalar, daemon=True).start()
            return True, ""
        if accion == "convertir":
            rutas = datos.get("rutas") if isinstance(datos.get("rutas"), list) else []
            return self.agregar(rutas[:50])
        if accion == "elegir":
            threading.Thread(target=self._elegir, daemon=True).start()
            return True, ""
        if accion == "ajustes":
            a = leer_json(CONFIG / "audio-ajustes.json")
            if datos.get("modo") in ("auto", "local", "api"):
                a["modo"] = datos["modo"]
            if isinstance(datos.get("resumir"), bool):
                a["resumir"] = datos["resumir"]
            escribir_json(CONFIG / "audio-ajustes.json", a)
            self.al_cambiar()
            return True, ""
        if accion == "abrir":
            tr = self._buscar(str(datos.get("id")))
            if not tr or not tr.get("salida"):
                return False, "?"
            ruta = Path(tr["salida"])
            return abrir(ruta.parent if datos.get("carpeta") else ruta), ""
        if accion == "resumir":
            return self.resumir(str(datos.get("id")))
        if accion == "limpiar":
            with self.lock:
                self.trabajos = [x for x in self.trabajos if x["estado"] not in ("listo", "error")]
            self._cambio()
            return True, ""
        if accion == "grabar":
            return self.grabar()
        if accion == "parar":
            return self.parar()
        return False, "?"

    def _instalar(self):
        self.instalacion = ""
        self.al_cambiar()
        ok, mensaje = extras.instalar(ENTORNO, paquetes(bool(self.gpu)), parte=PARTE)
        self.instalacion = "" if ok else mensaje
        if ok:
            notificar(t("Transcripción lista", "Transcription ready"),
                      t("Ya puedes soltar audios y videos.", "You can drop audio and video files now."))
        self.al_cambiar()

    def agregar(self, rutas):
        nuevos = 0
        for texto in rutas:
            archivo = a_ruta(texto)
            if archivo.is_file() and es_audio(archivo):
                self._encolar(archivo, archivo.name)
                nuevos += 1
        if nuevos:
            return True, ""
        return False, t("Acepta audio (mp3, m4a, wav, ogg…) o video (mp4, mkv, mov…).",
                        "Accepts audio (mp3, m4a, wav, ogg…) or video (mp4, mkv, mov…).")

    def subir(self, nombre, contenido):
        nombre = nombre_seguro(nombre)
        if not es_audio(nombre):
            return False, t("No es un audio ni un video.", "Not an audio or video file.")
        carpeta = SUBIDOS / uuid.uuid4().hex[:8]
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(contenido)
        self._encolar(carpeta / nombre, nombre, subido=True)
        return True, ""

    def _elegir(self):
        if self.eligiendo:
            return
        self.eligiendo = True
        self.al_cambiar()
        try:
            rutas = elegir_archivos(t("Elegir audio o video", "Choose audio or video"), EXTENSIONES)
            if rutas is None:
                notificar("akari", t("No hay selector de archivos: instala zenity o kdialog.", "No file picker: install zenity or kdialog."))
            elif rutas:
                self.agregar(rutas)
        finally:
            self.eligiendo = False
            self.al_cambiar()

    # ------------------------------------------------------------ resumen
    def resumir(self, ident):
        tr = self._buscar(ident)
        if not tr or tr["estado"] != "listo" or not Path(tr["salida"]).exists():
            return False, "?"
        if not self.modelos.estado.get("listo"):
            return False, t("Agrega una clave de API o usa un modelo local.", "Add an API key or use a local model.")
        tr["resumen"] = "haciendo"
        self._cambio()
        threading.Thread(target=self._resumir, args=(tr,), daemon=True).start()
        return True, ""

    def _resumir(self, tr):
        from .modelos import ErrorIA, preguntar
        ruta = Path(tr["salida"])
        try:
            texto = ruta.read_text(encoding="utf-8")
            # cabecera («# nombre» y la línea «> Transcripción de…»), un resumen anterior si hay, y el texto
            cabeza, _, resto = texto.partition("\n\n> ")
            linea, _, resto = resto.partition("\n\n")
            resto = re.sub(r"^## (Resumen|Summary)\n.*?\n## (Transcripción|Transcript)\n\n", "", resto, flags=re.S)
            cuerpo = re.sub(r"\*\*\[[\d:]+\]\*\* ", "", resto)
            limite = 12000 if self.modelos.ajustes().get("modo") == "local" else 120000
            recorte = cuerpo[:limite]
            pedido = t("Resume esta transcripción en español. Primero un resumen de 3 a 6 frases; después una "
                       "lista «Notas» con los puntos clave, decisiones y tareas (si las hay). Solo Markdown, sin "
                       "títulos de nivel 1.\n\n", "Summarize this transcript. First a 3–6 sentence summary, then a "
                       "«Notes» list with key points, decisions and to-dos (if any). Markdown only, no level-1 "
                       "headings.\n\n") + recorte
            resumen = preguntar(self.modelos, pedido, sistema=t("Resumes con precisión y sin inventar.",
                                                                   "You summarize accurately without inventing."),
                                timeout=600)
            if len(cuerpo) > limite:
                resumen += t("\n\n_(Resumen de la primera parte: la transcripción es muy larga para este modelo.)_",
                             "\n\n_(Summary of the first part: the transcript is too long for this model.)_")
            # el resumen va arriba, después de la cabecera (si ya había uno, se reemplaza)
            nuevo = (f"{cabeza}\n\n> {linea}\n\n## {t('Resumen', 'Summary')}\n\n{resumen.strip()}\n\n"
                     f"## {t('Transcripción', 'Transcript')}\n\n{resto}")
            ruta.write_text(nuevo, encoding="utf-8")
            tr["resumen"] = "listo"
        except (OSError, ErrorIA) as e:
            tr["resumen"] = "error: " + str(e)[:160]
        self._cambio()

    # ------------------------------------------------------------ reuniones
    def grabar(self):
        cual = grabadora()
        if not cual:
            return False, t("Grabar reuniones necesita pw-record o parecord (Linux).",
                            "Recording meetings needs pw-record or parecord (Linux).")
        if self.grabacion:
            return False, t("Ya se está grabando.", "Already recording.")
        carpeta = GRABACIONES / time.strftime("%Y-%m-%d %H.%M.%S")
        carpeta.mkdir(parents=True, exist_ok=True)
        procesos = []
        try:
            for orden in ordenes_grabar(cual, carpeta):
                procesos.append(subprocess.Popen(orden, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError as e:
            for p in procesos:
                p.terminate()
            return False, str(e)
        self.grabacion = {"desde": time.time(), "carpeta": carpeta, "procesos": procesos}
        self.al_cambiar()
        return True, ""

    def parar(self):
        g, self.grabacion = self.grabacion, None
        if not g:
            return False, "?"
        for p in g["procesos"]:
            p.send_signal(signal.SIGINT)        # así cierran bien la cabecera del WAV
        for p in g["procesos"]:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        self.al_cambiar()
        threading.Thread(target=self._guardar_reunion, args=(g,), daemon=True).start()
        return True, ""

    def _guardar_reunion(self, g):
        carpeta = g["carpeta"]
        pistas = [p for p in (carpeta / "microfono.wav", carpeta / "sistema.wav") if p.exists() and p.stat().st_size > 1024]
        if not pistas:
            notificar(t("No se grabó nada", "Nothing was recorded"), "")
            return
        nombre = t("Reunión ", "Meeting ") + time.strftime("%Y-%m-%d %H.%M", time.localtime(g["desde"]))
        destino = carpeta_documentos() / t("Reuniones", "Meetings")
        destino.mkdir(parents=True, exist_ok=True)
        exe = ffmpeg()
        if exe and len(pistas) == 2:
            final = destino_para(nombre, ".ogg", destino)
            try:
                _ffmpeg([exe, "-y", "-i", str(pistas[0]), "-i", str(pistas[1]), "-filter_complex",
                         "amix=inputs=2:duration=longest:normalize=0", "-ac", "1", "-c:a", "libopus", "-b:a", "32k",
                         str(final)])
            except RuntimeError:
                final = None
        else:
            final = None
        if final is None:           # sin ffmpeg: solo el micrófono, tal cual
            final = destino_para(nombre, ".wav", destino)
            shutil.move(str(pistas[0]), str(final))
        shutil.rmtree(carpeta, ignore_errors=True)
        self._encolar(final, final.name)

    # ------------------------------------------------------------ trabajo
    def _local(self, tr, origen):
        python = extras.python_de(ENTORNO, PARTE)
        modelo, dispositivo, computo = self.modelo_local()
        env = dict(os.environ)
        if dispositivo == "cuda" and not WINDOWS:
            libs = [str(p) for p in (extras.sitio(ENTORNO) / "nvidia").glob("*/lib")]
            env["LD_LIBRARY_PATH"] = os.pathsep.join(libs + [env.get("LD_LIBRARY_PATH", "")]).strip(os.pathsep)
        env["PYTHONIOENCODING"] = "utf-8"
        prompt = prompt_inicial()
        orden = [str(python), str(SCRIPT), str(origen), "--modelo", modelo, "--dispositivo", dispositivo,
                 "--computo", computo, "--carpeta", str(MODELOS_WHISPER), "--prompt", prompt]
        segmentos, idioma = [], ""
        tr.update(estado="transcribiendo", via=f"faster-whisper {modelo}", mensaje="")
        self._cambio()
        self.proceso = subprocess.Popen(orden, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                        text=True, encoding="utf-8", errors="replace", **SIN_VENTANA)
        ultimo = 0
        for linea in self.proceso.stdout:
            try:
                ev = json.loads(linea)
            except ValueError:
                continue
            if ev.get("reinicio"):
                segmentos = []
                tr["via"] = "faster-whisper small (CPU)"
            if "seg" in ev:
                segmentos.append(ev["seg"])
                tr["pct"] = ev.get("pct")
                if time.time() - ultimo > 1:
                    ultimo = time.time()
                    self.al_cambiar()
            if ev.get("fin"):
                idioma = ev.get("idioma") or ""
        error = self.proceso.stderr.read()
        codigo = self.proceso.wait()
        self.proceso = None
        if codigo != 0:
            raise RuntimeError((error.strip().splitlines() or [t("falló la transcripción", "transcription failed")])[-1][:200])
        return segmentos, prompt, idioma

    def _api(self, tr, origen, proveedor):
        clave = self.modelos.claves().get(proveedor)
        tr.update(estado="transcribiendo", via=f"Whisper · {'Groq' if proveedor == 'groq' else 'OpenAI'}", pct=None)
        self._cambio()
        segmentos = []
        with tempfile.TemporaryDirectory(prefix="akari-") as tmp:
            partes = preparar_para_api(origen, tmp)
            for i, (archivo, desfase) in enumerate(partes):
                try:
                    trozo = transcribir_api(proveedor, clave, archivo)
                except urllib.error.HTTPError as e:
                    from .modelos import _error
                    raise RuntimeError(_error(e)) from None
                except urllib.error.URLError:
                    raise RuntimeError(t("Sin conexión con el servicio.", "Can't reach the service.")) from None
                segmentos += [{**s, "inicio": s["inicio"] + desfase, "fin": s["fin"] + desfase} for s in trozo]
                tr["pct"] = int((i + 1) * 100 / len(partes))
                self.al_cambiar()
        return segmentos, "", ""

    def _trabajar(self):
        while True:
            ident = self.cola.get()
            with self.lock:
                tr = self._buscar(ident)
            if not tr:
                continue
            origen = Path(tr["origen"])
            camino = self.camino()
            try:
                if camino is None:
                    raise RuntimeError(t("Instala la transcripción o agrega una clave de Groq u OpenAI.",
                                         "Install transcription or add a Groq or OpenAI key."))
                segmentos, prompt, _ = self._local(tr, origen) if camino == "local" else self._api(tr, origen, camino)
                limpios = limpiar(segmentos, prompt)
                salida = destino_para(Path(tr["nombre"]).stem, ".md", None if tr.get("subido") else origen.parent)
                salida.write_text(a_markdown(tr["nombre"], limpios, tr["via"]), encoding="utf-8")
                quitados = len(segmentos) - len(limpios)
                duracion = reloj(limpios[-1]["fin"]) if limpios else "0:00"
                tr.update(estado="listo", salida=str(salida), pct=100,
                          mensaje=duracion + (t(f" · {quitados} frases dudosas quitadas", f" · {quitados} doubtful lines removed") if quitados else ""))
                notificar(t("Transcripción lista", "Transcript ready"), f"{tr['nombre']} → {salida.name}")
            except Exception as e:      # noqa: BLE001 — queda en el historial, no tumba el hilo
                tr.update(estado="error", mensaje=str(e)[:200])
                notificar(t("No se pudo transcribir", "Couldn't transcribe"), f"{tr['nombre']}: {e}")
            if tr.get("subido"):
                shutil.rmtree(origen.parent, ignore_errors=True)
            self._cambio()
            if tr["estado"] == "listo" and self.ajustes()["resumir"] and self.modelos.estado.get("listo"):
                self.resumir(tr["id"])
