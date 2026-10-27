"""Rutas, idioma, avisos y utilidades compartidas por todos los módulos (Linux y Windows)."""
import base64
import json
import locale
import os
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
HOME = Path.home()
RAIZ = Path(__file__).resolve().parent.parent          # carpeta del repositorio / instalación
if WINDOWS:
    # %APPDATA%\akari (ajustes) y %LOCALAPPDATA%\akari (datos y caché), como cualquier app de Windows
    _ROAMING = Path(os.environ.get("APPDATA") or HOME / "AppData" / "Roaming")
    _LOCAL = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local")
    CONFIG = _ROAMING / "akari"
    DATOS = _LOCAL / "akari"
    CACHE = DATOS / "cache"
else:
    CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "akari"
    CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "akari"
    DATOS = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / "akari"
ICONO = RAIZ / "iconos" / "akari.png"
# en Windows, los programas de consola que lanza el servicio no abren una ventana negra
SIN_VENTANA = {"creationflags": 0x08000000} if WINDOWS else {}      # CREATE_NO_WINDOW


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
    if WINDOWS:
        # el idioma de la interfaz de Windows ("es-MX", "en-US"…); getlocale() da "Spanish_Spain"
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                return "es" if buf.value.lower().startswith("es") else "en"
        except (OSError, AttributeError):
            pass
    try:
        return "es" if (locale.getlocale()[0] or "").lower().startswith("es") else "en"
    except ValueError:
        return "en"


IDIOMA = idioma()


def t(es, en):
    """Texto en el idioma del usuario: t("Hola", "Hello")."""
    return es if IDIOMA == "es" else en


# ---------------------------------------------------------------- avisos

# Aviso nativo de Windows (WinRT desde Windows PowerShell 5.1, que viene en todo Windows 10/11).
# El texto va por variables de entorno, nunca dentro del código. Con la app instalada se usa su
# AppUserModelID (el aviso dice "akari"); si no, el de PowerShell.
TOAST = r"""
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('<toast><visual><binding template="ToastGeneric"><text></text><text></text></binding></visual></toast>')
if ($env:AKARI_URGENTE -eq '1') { $x.DocumentElement.SetAttribute('scenario', 'reminder') }
$t = $x.GetElementsByTagName('text')
[void]$t.Item(0).AppendChild($x.CreateTextNode($env:AKARI_TITULO))
[void]$t.Item(1).AppendChild($x.CreateTextNode($env:AKARI_CUERPO))
$app = if ($env:AKARI_APP_ID) { $env:AKARI_APP_ID } else { '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe' }
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def powershell(script, timeout=30, env=None):
    """Ejecuta un script de Windows PowerShell sin ventana; devuelve su salida o None si falla."""
    codificado = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", codificado], capture_output=True, timeout=timeout, env=env, **SIN_VENTANA)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def notificar(titulo, cuerpo="", urgente=False):
    if ajustes().get("avisos") is False:
        return
    if WINDOWS:
        import threading
        env = {**os.environ, "AKARI_TITULO": titulo, "AKARI_CUERPO": cuerpo, "AKARI_URGENTE": "1" if urgente else "0"}
        threading.Thread(target=powershell, args=(TOAST, 20, env), daemon=True).start()
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
        r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, **SIN_VENTANA, **kw)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def abrir(destino):
    """Abre un enlace, archivo o carpeta con la app predeterminada del sistema."""
    try:
        if WINDOWS:
            os.startfile(str(destino))
        else:
            orden = ["xdg-open"] if tiene("xdg-open") else ["gio", "open"]
            subprocess.Popen(orden + [str(destino)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        return True
    except OSError:
        return False
