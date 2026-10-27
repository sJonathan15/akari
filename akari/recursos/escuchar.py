"""Escucha el micrófono y avisa cuando alguien dice «akari …». Corre con el Python del entorno «voz».

  python escuchar.py --vosk <modelo> --idioma es [--whisper small] [--archivo prueba.wav]
  (el audio llega por stdin en s16le mono 16 kHz desde pw-record/parecord, o con sounddevice
  en Windows; --archivo lee un WAV, para pruebas)

1. Vosk con una gramática cerrada marca candidatos casi sin gastar CPU. «akari» no está en su
   vocabulario, así que la gramática son palabras que sí están y suenan igual («a cari», «aka ri»,
   «a curry»…). Sola da muchos falsos positivos (cualquier «a ver», «acá», «caries»…), así que:
2. el trozo (lo que se dijo un poco antes + hasta que se calla) se confirma con faster-whisper:
   solo si Whisper también oye «akari» se toma como orden. El modelo de Whisper se carga en el
   primer candidato y se suelta tras un minuto sin uso.
3. Umbral de ruido adaptativo: el piso de ruido se sigue con una media lenta cuando nadie habla,
   y «hablando» es estar varias veces por encima de ese piso.

Si solo se dijo «akari», la orden es lo siguiente que se diga. Mientras existe el archivo --control
(akari está hablando) no se escucha, para no oírse a sí mismo.

Por stdout, una línea JSON por evento: {"fase": "escuchando"|"oyendo"|"confirmando"},
{"orden": "texto"}, {"descartado": "…"} y {"error": "…"}.
"""
import argparse
import array
import json
import math
import os
import re
import sys
import threading
import time
import wave
from collections import deque

TASA = 16000
TROZO = 1600                    # 0,1 s
ANTES = 40                      # trozos que se guardan de antes del candidato (4 s)
SILENCIO_FIN = 9                # 0,9 s callado = terminó de hablar
MAX_ORDEN = 120                 # 12 s como mucho
# lo que Vosk sí conoce y suena como «akari» (cualquiera de estas = candidato)
GRAMATICA = {"es": ["a cari", "aca ri", "a cary", "akira", "cari", "oye a cari"],
             "en": ["a kari", "a cari", "aka ri", "a curry", "a carry", "hey a kari"]}
PALABRA = re.compile(r"\b(o[iy]e,?\s+)?(a\s?k[aá]\s?r[iy]|acar[iy]|a\s?car[iy]|hakar[iy]|akar[iy]|ak[aá]ri)\b[,.:;!¡?¿]*\s*", re.I)


def emitir(**datos):
    sys.stdout.write(json.dumps(datos, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def rms(trozo):
    muestras = array.array("h", trozo)
    if not muestras:
        return 0.0
    return math.sqrt(sum(m * m for m in muestras) / len(muestras))


class Ruido:
    """Piso de ruido adaptativo."""

    def __init__(self):
        self.piso = 200.0

    def habla(self, nivel):
        sobre = nivel > max(self.piso * 3.0, 350)
        if not sobre:       # solo aprende del ruido, no de la voz
            self.piso = 0.97 * self.piso + 0.03 * max(nivel, 50)
        return sobre


class Whisper:
    def __init__(self, modelo, idioma, carpeta):
        self.nombre, self.idioma, self.carpeta = modelo, idioma, carpeta
        self.m, self.usado = None, 0
        threading.Thread(target=self._soltar, daemon=True).start()

    def _soltar(self):
        while True:
            time.sleep(10)
            if self.m is not None and time.time() - self.usado > 60:
                self.m = None

    def texto(self, pcm):
        import numpy as np
        from faster_whisper import WhisperModel
        if self.m is None:
            self.m = WhisperModel(self.nombre, device="cpu", compute_type="int8", download_root=self.carpeta)
        self.usado = time.time()
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segs, _ = self.m.transcribe(audio, language=self.idioma, beam_size=3, vad_filter=False,
                                    condition_on_previous_text=False, hotwords="akari", temperature=0)
        return " ".join(s.text.strip() for s in segs).strip()


def orden_de(texto):
    """El texto después de la palabra clave, o None si la palabra no está."""
    m = PALABRA.search(texto or "")
    if not m:
        return None
    return texto[m.end():].strip(" ,.") or ""


def fuente(args):
    """Generador de trozos de 0,1 s (bytes s16le)."""
    if args.archivo:
        with wave.open(args.archivo, "rb") as w:
            while True:
                datos = w.readframes(TROZO)
                if not datos:
                    break
                yield datos
        for _ in range(SILENCIO_FIN + 2):        # un poco de silencio al final
            yield b"\x00\x00" * TROZO
        return
    if sys.platform == "win32":
        import queue
        import sounddevice as sd
        cola = queue.Queue()
        with sd.RawInputStream(samplerate=TASA, channels=1, dtype="int16", blocksize=TROZO,
                               callback=lambda datos, *_: cola.put(bytes(datos))):
            while True:
                yield cola.get()
    entrada = sys.stdin.buffer
    while True:
        datos = entrada.read(TROZO * 2)
        if not datos:
            return
        yield datos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vosk", required=True)
    p.add_argument("--idioma", default="es")
    p.add_argument("--whisper", default="small")
    p.add_argument("--carpeta", default=None)
    p.add_argument("--archivo", default="")
    p.add_argument("--control", default="", help="archivo que, si existe, pausa la escucha (mientras akari habla)")
    args = p.parse_args()

    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    gramatica = GRAMATICA.get(args.idioma, GRAMATICA["en"])
    vosk = KaldiRecognizer(Model(args.vosk), TASA, json.dumps(gramatica + ["[unk]"], ensure_ascii=False))
    whisper = Whisper(args.whisper, args.idioma, args.carpeta)
    ruido = Ruido()
    previo = deque(maxlen=ANTES)
    emitir(fase="escuchando")

    candidato, grabado, callado, hablo = False, [], 0, False
    esperando = 0           # trozos que quedan para decir la orden tras un «akari» a secas
    for trozo in fuente(args):
        if args.control and os.path.exists(args.control):      # akari está hablando
            previo.clear()
            candidato, grabado, esperando = False, [], 0
            continue
        habla = ruido.habla(rms(trozo))
        if not candidato:
            previo.append(trozo)
            if esperando:
                esperando -= 1
                if habla:           # empezó a decir la orden: se graba hasta que se calle
                    candidato, grabado, callado, hablo = True, list(previo)[-3:], 0, True
                    esperando = -1
                elif not esperando:
                    emitir(fase="escuchando")
                continue
            if vosk.AcceptWaveform(trozo):
                oido = json.loads(vosk.Result()).get("text", "")
            else:
                oido = json.loads(vosk.PartialResult()).get("partial", "")
            if oido and oido.replace("[unk]", "").strip():
                candidato, grabado, callado, hablo = True, list(previo), 0, habla
                vosk.Reset()
                emitir(fase="oyendo")
            continue
        grabado.append(trozo)
        hablo = hablo or habla
        callado = 0 if habla else callado + 1
        if (callado >= SILENCIO_FIN and len(grabado) > 8) or len(grabado) >= ANTES + MAX_ORDEN:
            emitir(fase="confirmando")
            try:
                texto = whisper.texto(b"".join(grabado))
            except Exception as e:      # noqa: BLE001
                emitir(error=str(e)[:200])
                texto = ""
            seguida = esperando == -1           # esta era la orden que siguió a un «akari» a secas
            orden = texto.strip(" ,.") if seguida else orden_de(texto)
            esperando = 0
            candidato, grabado = False, []
            previo.clear()
            if orden is None or (seguida and not orden):
                emitir(descartado=texto)        # Vosk creyó oír «akari» y Whisper no (o no dijo nada)
                emitir(fase="escuchando")
            elif orden == "":
                esperando = 60                  # «akari» a secas: 6 s para decir qué
                emitir(fase="oyendo")
            else:
                emitir(orden=orden)
                emitir(fase="escuchando")

if __name__ == "__main__":
    main()
