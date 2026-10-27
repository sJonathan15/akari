"""Lee en voz alta el texto que llega por stdin con Piper. Corre con el Python del entorno «voz».

  echo "Hola" | python hablar.py --modelo es_MX-ald-medium.onnx [--control <archivo>]

El audio va a un WAV temporal que se borra al terminar. Se reproduce con pw-play, paplay o aplay
en Linux y con winsound en Windows. Mientras habla existe el archivo --control (el que escucha
no se oye a sí mismo).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def sintetizar(modelo, texto, archivo):
    from piper import PiperVoice
    voz = PiperVoice.load(modelo)
    with wave.open(archivo, "wb") as w:
        if hasattr(voz, "synthesize_wav"):        # piper-tts 1.3+
            voz.synthesize_wav(texto, w)
        else:
            voz.synthesize(texto, w)


def reproducir(archivo):
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(archivo, winsound.SND_FILENAME)
        return
    for orden in (["pw-play"], ["paplay"], ["aplay", "-q"]):
        if shutil.which(orden[0]):
            subprocess.run(orden + [archivo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise SystemExit("no hay pw-play, paplay ni aplay")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", required=True)
    p.add_argument("--control", default="")
    args = p.parse_args()
    texto = sys.stdin.read().strip()
    if not texto:
        return
    with tempfile.TemporaryDirectory(prefix="akari-") as tmp:
        archivo = str(Path(tmp) / "voz.wav")
        sintetizar(args.modelo, texto, archivo)
        if args.control:
            Path(args.control).touch()
        try:
            reproducir(archivo)
        finally:
            if args.control:
                Path(args.control).unlink(missing_ok=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
