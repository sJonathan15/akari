"""Transcribe un audio o video con faster-whisper. Corre con el Python del entorno «voz» (extras.py),
en su propio proceso: el modelo ocupa memoria solo mientras hay algo que transcribir.

  python transcribir.py <archivo> --modelo large-v3-turbo --dispositivo cuda --computo int8_float16 \
                        --carpeta <modelos> [--idioma es] [--prompt "…"]

Escribe una línea JSON por evento: {"aviso"}, {"seg": {inicio, fin, texto, no_speech_prob,
avg_logprob, compression_ratio}, "pct"} y al final {"fin": true, "idioma", "duracion"}.
"""
import argparse
import glob
import json
import os
import sys


def emitir(**datos):
    sys.stdout.write(json.dumps(datos, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def bibliotecas_cuda():
    """En Windows, las DLL de CUDA que trae pip (nvidia-cublas-cu12, nvidia-cudnn-cu12). En Linux
    las pone el servicio en LD_LIBRARY_PATH antes de lanzar este proceso."""
    if sys.platform != "win32":
        return
    import site
    for base in site.getsitepackages():
        for carpeta in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            os.add_dll_directory(carpeta)
            os.environ["PATH"] = carpeta + os.pathsep + os.environ.get("PATH", "")


def transcribir(args, modelo, dispositivo, computo):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device=dispositivo, compute_type=computo, download_root=args.carpeta)
    # vad_filter quita los silencios (donde Whisper más inventa) y sin condition_on_previous_text
    # un error no se repite en bucle por el resto del audio
    segmentos, info = m.transcribe(args.archivo, language=args.idioma or None, initial_prompt=args.prompt or None,
                                   vad_filter=True, condition_on_previous_text=False, beam_size=5, temperature=0)
    duracion = info.duration or 0
    hubo = False
    for s in segmentos:
        hubo = True
        emitir(seg={"inicio": round(s.start, 2), "fin": round(s.end, 2), "texto": s.text.strip(),
                    "no_speech_prob": round(s.no_speech_prob, 3), "avg_logprob": round(s.avg_logprob, 3),
                    "compression_ratio": round(s.compression_ratio, 2)},
               pct=min(99, int(s.end * 100 / duracion)) if duracion else None)
    return info, hubo


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archivo")
    p.add_argument("--modelo", default="small")
    p.add_argument("--dispositivo", default="cpu")
    p.add_argument("--computo", default="int8")
    p.add_argument("--carpeta", default=None)
    p.add_argument("--idioma", default="")
    p.add_argument("--prompt", default="")
    args = p.parse_args()
    if args.dispositivo == "cuda":
        bibliotecas_cuda()
    try:
        info, _ = transcribir(args, args.modelo, args.dispositivo, args.computo)
    except Exception as e:      # noqa: BLE001
        # sin CUDA/cuDNN utilizables la tarjeta falla al cargar o en el primer trozo: se sigue en la CPU
        if args.dispositivo != "cuda":
            raise
        emitir(aviso=f"GPU: {str(e)[:160]}", reinicio=True)
        info, _ = transcribir(args, "small", "cpu", "int8")
    emitir(fin=True, idioma=info.language, duracion=round(info.duration or 0, 1))


if __name__ == "__main__":
    main()
