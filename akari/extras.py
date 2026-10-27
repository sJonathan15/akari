"""Paquetes de Python opcionales (conversor de documentos, transcripción…), cada uno en su propio
entorno dentro de los datos de akari: no tocan el Python del sistema ni piden contraseña.

Se instalan con uv si está (rápido, y trae su propio Python aunque el del sistema no tenga venv),
si no con `python -m venv` + pip. En Windows, si no hay ninguno de los dos, instala uv con winget.
"""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .comun import DATOS, HOME, SIN_VENTANA, WINDOWS, t

CARPETA = DATOS / "extras"
_instalando = {}            # nombre -> True mientras se instala
_cerrojo = threading.Lock()


def sitio(nombre):
    """La carpeta site-packages del entorno (para encontrar bibliotecas que trae, como CUDA)."""
    entorno = CARPETA / nombre
    if WINDOWS:
        return entorno / "Lib" / "site-packages"
    return next(iter(sorted((entorno / "lib").glob("python3*/site-packages"))), entorno / "lib")


def _python(entorno):
    return entorno / ("Scripts/python.exe" if WINDOWS else "bin/python")


def _marca(nombre, parte):
    return CARPETA / nombre / (f".listo-{parte}" if parte else ".listo")


def python_de(nombre, parte=None):
    """El Python del entorno `nombre` si ya está instalado y completo. Un entorno puede tener varias
    partes que se instalan por separado (p. ej. «voz»: transcribir y, aparte, el asistente)."""
    py = _python(CARPETA / nombre)
    return py if py.exists() and _marca(nombre, parte).exists() else None


def instalando(nombre):
    return bool(_instalando.get(nombre))


def _uv():
    for candidato in (shutil.which("uv"), HOME / ".local" / "bin" / ("uv.exe" if WINDOWS else "uv"),
                      HOME / ".cargo" / "bin" / ("uv.exe" if WINDOWS else "uv")):
        if candidato and Path(candidato).exists():
            return str(candidato)
    if WINDOWS:
        # winget deja uv en su carpeta de enlaces, que el servicio todavía no tiene en el PATH
        enlace = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "uv.exe"
        if enlace.exists():
            return str(enlace)
    return None


def _correr(orden, timeout=1800):
    r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, **SIN_VENTANA)
    if r.returncode != 0:
        ultima = ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1]
        raise RuntimeError(ultima[:240])


def instalar(nombre, paquetes, python="3.12", parte=None):
    """Crea (o completa) el entorno `nombre` con `paquetes`. Devuelve (ok, mensaje). Bloquea: usar en un hilo."""
    with _cerrojo:
        if _instalando.get(nombre):
            return False, t("Ya se está instalando.", "Already installing.")
        _instalando[nombre] = True
    entorno = CARPETA / nombre
    try:
        _marca(nombre, parte).unlink(missing_ok=True)
        uv = _uv()
        if not uv and WINDOWS and shutil.which("winget"):
            _correr(["winget", "install", "-e", "--id", "astral-sh.uv", "--silent",
                     "--accept-package-agreements", "--accept-source-agreements"], 600)
            uv = _uv()
        if uv:
            _correr([uv, "venv", "--allow-existing", "--python", python, str(entorno)])
            _correr([uv, "pip", "install", "--python", str(_python(entorno)), *paquetes])
        else:
            _correr([sys.executable, "-m", "venv", str(entorno)], 300)
            _correr([str(_python(entorno)), "-m", "pip", "install", "--upgrade", *paquetes])
        _marca(nombre, parte).write_text(" ".join(paquetes))
        return True, ""
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        mensaje = str(e)
        if "No module named venv" in mensaje or "ensurepip" in mensaje:
            mensaje = t("Falta uv o python3-venv para instalarlo.", "uv or python3-venv is needed to install it.")
        return False, mensaje
    finally:
        _instalando.pop(nombre, None)
