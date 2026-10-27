"""Voz del asistente (opcional: sin ella, el asistente funciona escribiendo).

Se instala con un botón en el entorno «voz» de extras.py (el mismo de la transcripción): Vosk para
la palabra clave, faster-whisper para confirmarla, Piper para hablar (y sounddevice en Windows).
Los modelos de Vosk y la voz de Piper se descargan a los datos de akari.

Micrófono: pw-record o parecord en Linux (su audio entra por stdin a recursos/escuchar.py) y
sounddevice en Windows. Mientras akari habla, el que escucha se pausa (archivo de control).
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from . import extras
from .comun import CACHE, DATOS, IDIOMA, RAIZ, SIN_VENTANA, WINDOWS, notificar, t, tiene

ENTORNO, PARTE = "voz", "asistente"
CARPETA = DATOS / "voz"
CONTROL = CACHE / "hablando"                # existe mientras akari habla
ESCUCHAR = RAIZ / "akari" / "recursos" / "escuchar.py"
HABLAR = RAIZ / "akari" / "recursos" / "hablar.py"
VOSK = {"es": "vosk-model-small-es-0.42", "en": "vosk-model-small-en-us-0.15"}
PIPER = {"es": "es/es_MX/ald/medium/es_MX-ald-medium", "en": "en/en_US/lessac/medium/en_US-lessac-medium"}
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
VOSK_BASE = "https://alphacephei.com/vosk/models/"


def paquetes():
    return ["vosk", "piper-tts", "faster-whisper>=1.1", "av<19", "numpy"] + (["sounddevice"] if WINDOWS else [])


def microfono():
    """Orden que deja el audio del micrófono en stdout (s16le mono 16 kHz); [] en Windows (sounddevice)."""
    if WINDOWS:
        return []
    if tiene("parecord"):
        return ["parecord", "--raw", "--format=s16le", "--rate=16000", "--channels=1"]
    if tiene("pw-record"):
        return ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
    return None


def modelo_vosk():
    return CARPETA / VOSK[IDIOMA]


def modelo_piper():
    return CARPETA / (PIPER[IDIOMA].rsplit("/", 1)[-1] + ".onnx")


def para_decir(texto):
    """Sin Markdown ni enlaces: lo que se lee en voz alta."""
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"https?://\S+", t("(enlace)", "(link)"), texto)
    texto = re.sub(r"[*_`#>|]+", "", texto)
    return " ".join(texto.split())[:1200]


def _bajar(url, destino):
    tmp = destino.with_name(destino.name + ".parcial")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, destino)


class Voz:
    def __init__(self, al_cambiar, asistente):
        self.al_cambiar = al_cambiar
        self.asistente = asistente
        self.instalando = False
        self.error = ""
        self.escucha = None             # proceso de escuchar.py (y el del micrófono)
        self.mic = None
        self.fase = None                # "escuchando" | "oyendo" | "confirmando"
        self.hablante = None
        self.ultimo_descarte = ""
        CONTROL.unlink(missing_ok=True)

    def instalada(self):
        return extras.python_de(ENTORNO, PARTE) is not None and modelo_vosk().is_dir() and modelo_piper().exists()

    @property
    def estado(self):
        return {"instalada": self.instalada(), "instalando": self.instalando or extras.instalando(ENTORNO),
                "error": self.error, "microfono": microfono() is not None,
                "escuchando": self.escucha is not None and self.escucha.poll() is None,
                "fase": self.fase if self.escucha is not None else None,
                "hablando": self.hablante is not None and self.hablante.poll() is None}

    # ------------------------------------------------------------ instalar
    def instalar(self):
        if self.instalando:
            return False, t("Ya se está instalando.", "Already installing.")
        threading.Thread(target=self._instalar, daemon=True).start()
        return True, ""

    def _instalar(self):
        self.instalando, self.error = True, ""
        self.al_cambiar()
        try:
            ok, mensaje = extras.instalar(ENTORNO, paquetes(), parte=PARTE)
            if not ok:
                raise RuntimeError(mensaje)
            CARPETA.mkdir(parents=True, exist_ok=True)
            if not modelo_vosk().is_dir():
                zip_ = CARPETA / (VOSK[IDIOMA] + ".zip")
                _bajar(VOSK_BASE + VOSK[IDIOMA] + ".zip", zip_)
                with zipfile.ZipFile(zip_) as z:
                    z.extractall(CARPETA)
                zip_.unlink(missing_ok=True)
            if not modelo_piper().exists():
                _bajar(PIPER_BASE + PIPER[IDIOMA] + ".onnx.json", Path(str(modelo_piper()) + ".json"))
                _bajar(PIPER_BASE + PIPER[IDIOMA] + ".onnx", modelo_piper())
            notificar(t("Voz lista", "Voice ready"), t("Ya puedes hablarle a akari.", "You can talk to akari now."))
        except (OSError, RuntimeError, zipfile.BadZipFile) as e:
            self.error = str(e)[:200]
        self.instalando = False
        self.revisar()
        self.al_cambiar()

    # ------------------------------------------------------------ escuchar
    def revisar(self):
        """Prende o apaga la escucha según el interruptor «Escuchar palabra clave»."""
        quiere = self.asistente.ajustes()["palabra_clave"] and self.instalada()
        vivo = self.escucha is not None and self.escucha.poll() is None
        if quiere and not vivo:
            self._escuchar()
        elif not quiere and vivo:
            self._parar()

    def _escuchar(self):
        fuente = microfono()
        if fuente is None:
            self.error = t("Falta pw-record o parecord para el micrófono.", "pw-record or parecord is needed for the microphone.")
            return
        python = extras.python_de(ENTORNO, PARTE)
        orden = [str(python), str(ESCUCHAR), "--vosk", str(modelo_vosk()), "--idioma", IDIOMA,
                 "--carpeta", str(DATOS / "whisper"), "--control", str(CONTROL)]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            if fuente:
                self.mic = subprocess.Popen(fuente, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self.escucha = subprocess.Popen(orden, stdin=self.mic.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                text=True, encoding="utf-8", errors="replace", env=env)
                self.mic.stdout.close()         # que el micrófono se entere si escuchar.py termina
            else:
                self.escucha = subprocess.Popen(orden, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                text=True, encoding="utf-8", errors="replace", env=env, **SIN_VENTANA)
        except OSError as e:
            self.error = str(e)[:200]
            self._parar()
            return
        self.error = ""
        threading.Thread(target=self._leer, args=(self.escucha,), daemon=True).start()
        self.al_cambiar()

    def _leer(self, proceso):
        for linea in proceso.stdout:
            try:
                ev = json.loads(linea)
            except ValueError:
                continue
            if ev.get("fase"):
                self.fase = ev["fase"]
                self.al_cambiar()
            if ev.get("orden"):
                self.asistente.preguntar(ev["orden"], por_voz=True)
            if "descartado" in ev:
                self.ultimo_descarte = ev["descartado"]
            if ev.get("error"):
                self.error = ev["error"]
        if proceso is self.escucha:     # terminó solo (sin micrófono, sin modelo…)
            self.escucha, self.fase = None, None
            self.al_cambiar()

    def _parar(self):
        for p in (self.escucha, self.mic):
            if p and p.poll() is None:
                p.terminate()
        self.escucha, self.mic, self.fase = None, None, None
        self.al_cambiar()

    # ------------------------------------------------------------ hablar
    def decir(self, texto):
        if not self.instalada():
            return
        texto = para_decir(texto)
        if not texto:
            return
        self.callar()
        python = extras.python_de(ENTORNO, PARTE)
        try:
            self.hablante = subprocess.Popen([str(python), str(HABLAR), "--modelo", str(modelo_piper()), "--control", str(CONTROL)],
                                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             text=True, encoding="utf-8", **SIN_VENTANA)
            self.hablante.stdin.write(texto)
            self.hablante.stdin.close()
        except OSError:
            self.hablante = None
            return
        self.al_cambiar()
        threading.Thread(target=self._esperar_voz, args=(self.hablante,), daemon=True).start()

    def _esperar_voz(self, proceso):
        proceso.wait()
        CONTROL.unlink(missing_ok=True)
        time.sleep(0.1)
        self.al_cambiar()

    def callar(self):
        if self.hablante and self.hablante.poll() is None:
            self.hablante.kill()
            CONTROL.unlink(missing_ok=True)
            self.al_cambiar()
