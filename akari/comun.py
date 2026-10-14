"""Rutas, idioma, avisos y utilidades compartidas por todos los módulos."""
import json
import locale
import os
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()
RAIZ = Path(__file__).resolve().parent.parent          # carpeta del repositorio / instalación
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "akari"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "akari"
DATOS = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / "akari"
ICONO = RAIZ / "iconos" / "akari.png"


# ---------------------------------------------------------------- archivos

def leer_json(ruta, defecto=None):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if defecto is None else defecto


def escribir_json(ruta, datos, respaldo=False):
    """Escritura atómica. Con respaldo=True guarda una sola copia del original (.bak-akari)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if respaldo and ruta.exists():
        copia = ruta.with_name(ruta.name + ".bak-akari")
        if not copia.exists():
            shutil.copy2(ruta, copia)
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def ajustes():
    """~/.config/akari/ajustes.json (lo que el usuario cambia a mano o desde las cápsulas)."""
    return leer_json(CONFIG / "ajustes.json")


# ---------------------------------------------------------------- idioma

def idioma():
    """'es' o 'en': primero ajustes.json, luego las variables de idioma del sistema."""
    elegido = ajustes().get("idioma")
    if elegido in ("es", "en"):
        return elegido
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(var, "")
        if valor:
            return "es" if valor.lower().startswith("es") else "en"
    try:
        return "es" if (locale.getlocale()[0] or "").lower().startswith("es") else "en"
    except ValueError:
        return "en"


IDIOMA = idioma()


def t(es, en):
    """Texto en el idioma del usuario: t("Hola", "Hello")."""
    return es if IDIOMA == "es" else en


# ---------------------------------------------------------------- avisos

def notificar(titulo, cuerpo="", urgente=False):
    if ajustes().get("avisos") is False:
        return
    orden = ["notify-send", "-a", "akari", "-i", str(ICONO), titulo, cuerpo]
    if urgente:
        orden[1:1] = ["-u", "critical"]
    try:
        subprocess.Popen(orden, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def tiene(binario):
    return shutil.which(binario) is not None


def correr(orden, timeout=30, **kw):
    """(ok, salida) sin lanzar excepciones."""
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
