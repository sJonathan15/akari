"""Lo que el asistente puede hacer en el equipo: solo cosas inofensivas y en Linux y Windows.

Abrir apps (por nombre: .desktop y Flatpak en Linux, menú Inicio en Windows), abrir enlaces y
carpetas, listar y leer archivos (nunca claves, .ssh, .env ni credenciales), controlar la música
(MPRIS con playerctl en Linux, teclas multimedia en Windows), mirar la pantalla o la cámara (la
imagen va al modelo y nunca se guarda), generar una imagen (si hay una API que lo permita),
buscar en la web y notas en una carpeta de Markdown (sirve una bóveda de Obsidian).
"""
import configparser
import difflib
import glob
import os
import re
import subprocess
import tempfile
import time
import unicodedata
import urllib.parse
from pathlib import Path

from .comun import HOME, SIN_VENTANA, WINDOWS, abrir, buscar, correr, entorno_completo, powershell, t, tiene

MAX_LECTURA = 20000
# nunca se listan ni se leen (en cualquier parte de la ruta)
PROHIBIDO = re.compile(
    r"(^|[\\/])(\.ssh|\.gnupg|\.password-store|\.aws|\.azure|\.kube|\.docker|keyrings?|\.pki|\.mozilla|"
    r"\.netrc|\.git-credentials|\.pypirc|\.npmrc|credentials?(\.[^\\/]*)?|secrets?(\.[^\\/]*)?|\.env[^\\/]*|"
    r"[^\\/]*(id_rsa|id_ed25519|id_ecdsa)[^\\/]*|[^\\/]*\.(pem|key|p12|pfx|kdbx|keystore|jks|asc|gpg)|"
    r"[^\\/]*(token|password|contraseña|clave|apikey|api_key)[^\\/]*|claves\.json|\.claude\.json|auth\.json)"
    r"($|[\\/])", re.I)
# archivos que se pueden abrir con su app (nada que se ejecute: .sh, .desktop, .exe, .bat…)
ABRIBLES = {".pdf", ".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp3", ".ogg", ".flac", ".wav",
            ".m4a", ".mp4", ".mkv", ".webm", ".mov", ".docx", ".doc", ".odt", ".xlsx", ".ods", ".pptx", ".odp", ".csv",
            ".html", ".epub"}


def sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- apps

def _apps_linux():
    """{nombre visible: (id, ruta .desktop)} de las apps instaladas (también Flatpak y Snap)."""
    datos = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    carpetas = [Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / "applications"]
    carpetas += [Path(d) / "applications" for d in datos if d]
    carpetas += [Path("/var/lib/flatpak/exports/share/applications"), HOME / ".local/share/flatpak/exports/share/applications",
                 Path("/var/lib/snapd/desktop/applications")]
    apps = {}
    for carpeta in carpetas:
        for ruta in sorted(glob.glob(str(carpeta / "*.desktop"))):
            ident = Path(ruta).stem
            if any(ident == a[0] for a in apps.values()):
                continue        # el de ~/.local tapa al del sistema
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(ruta, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("NoDisplay", "false").lower() == "true" or e.get("Hidden", "false").lower() == "true" \
                    or e.get("Type", "Application") != "Application":
                continue
            for clave in ("Name", "Name[es]", "GenericName", "GenericName[es]"):
                if e.get(clave):
                    apps.setdefault(e[clave], (ident, ruta))
            apps.setdefault(ident.split(".")[-1], (ident, ruta))
    return apps


def _apps_windows():
    """{nombre: AppID} del menú Inicio (Get-StartApps trae también las de la Tienda)."""
    salida = powershell("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                        "Get-StartApps | ForEach-Object { $_.Name + \"`t\" + $_.AppID }", 30) or ""
    apps = {}
    for linea in salida.splitlines():
        nombre, _, ident = linea.partition("\t")
        if nombre.strip() and ident.strip():
            apps[nombre.strip()] = ident.strip()
    return apps


_cache_apps = {"t": 0, "apps": {}}


def apps():
    if time.time() - _cache_apps["t"] > 120:
        _cache_apps.update(t=time.time(), apps=_apps_windows() if WINDOWS else _apps_linux())
    return _cache_apps["apps"]


def buscar_app(nombre, lista=None):
    """El nombre de la app que mejor coincide con lo pedido, o None."""
    lista = apps() if lista is None else lista
    pedido = sin_acentos(nombre).strip(" .")
    if not pedido:
        return None
    normal = {sin_acentos(k): k for k in lista}
    if pedido in normal:
        return normal[pedido]
    # primero la palabra entera («code» → Visual Studio Code), después el comienzo («fire» → Firefox)
    for coincide in (lambda k: re.search(rf"\b{re.escape(pedido)}\b", k), lambda k: k.startswith(pedido)):
        candidatas = sorted((k for k in normal if coincide(k)), key=len)
        if candidatas:
            return normal[candidatas[0]]
    parecidos = difflib.get_close_matches(pedido, list(normal), n=1, cutoff=0.75)
    return normal[parecidos[0]] if parecidos else None


def abrir_app(nombre):
    lista = apps()
    elegida = buscar_app(nombre, lista)
    if not elegida:
        return False, t(f"No encontré la app «{nombre}».", f"I couldn't find the app “{nombre}”.")
    if WINDOWS:
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{lista[elegida]}"], **SIN_VENTANA)
        except OSError as e:
            return False, str(e)
        return True, t(f"Abriendo {elegida}.", f"Opening {elegida}.")
    ident, ruta = lista[elegida]
    for orden in (["gio", "launch", ruta], ["gtk-launch", ident], ["kioclient", "exec", ruta], ["dex", ruta]):
        if tiene(orden[0]):
            try:
                subprocess.Popen(orden, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                                 env=entorno_completo())
                return True, t(f"Abriendo {elegida}.", f"Opening {elegida}.")
            except OSError:
                continue
    # sin ninguna de esas: la línea Exec= sin los %U, %f…
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.read(ruta, encoding="utf-8")
    exec_ = re.sub(r"\s%[a-zA-Z]", "", cp["Desktop Entry"].get("Exec", "")).strip()
    if not exec_:
        return False, "?"
    import shlex
    subprocess.Popen(shlex.split(exec_), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True, t(f"Abriendo {elegida}.", f"Opening {elegida}.")


# ---------------------------------------------------------------- enlaces, carpetas y archivos

CARPETAS = {"descargas": "DOWNLOAD", "downloads": "DOWNLOAD", "documentos": "DOCUMENTS", "documents": "DOCUMENTS",
            "escritorio": "DESKTOP", "desktop": "DESKTOP", "musica": "MUSIC", "music": "MUSIC", "imagenes": "PICTURES",
            "fotos": "PICTURES", "pictures": "PICTURES", "videos": "VIDEOS", "inicio": "HOME", "home": "HOME",
            "carpeta personal": "HOME"}
NOMBRES_WIN = {"DOWNLOAD": "Downloads", "DOCUMENTS": "Documents", "DESKTOP": "Desktop", "MUSIC": "Music",
               "PICTURES": "Pictures", "VIDEOS": "Videos"}


def carpeta_conocida(nombre):
    """Ruta de «descargas», «documentos»… o None."""
    clave = CARPETAS.get(sin_acentos(nombre).strip(" ./").removeprefix("la carpeta ").removeprefix("carpeta de ").removeprefix("mis "))
    if not clave:
        return None
    if clave == "HOME":
        return HOME
    if not WINDOWS and tiene("xdg-user-dir"):
        ok, ruta = correr(["xdg-user-dir", clave], 5)
        if ok and ruta and Path(ruta) != HOME:
            return Path(ruta)
    return HOME / NOMBRES_WIN[clave]


def permitido(ruta):
    """¿Se puede listar o leer? Solo dentro de la carpeta personal (o una bóveda elegida) y nada secreto."""
    try:
        ruta = Path(ruta).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    if PROHIBIDO.search(str(ruta)):
        return False
    return ruta == HOME or HOME in ruta.parents


def ruta_de(texto, base=None):
    texto = str(texto or "").strip().strip("\"'")
    conocida = carpeta_conocida(texto)
    if conocida:
        return conocida
    ruta = Path(texto).expanduser()
    if not ruta.is_absolute():
        ruta = (base or HOME) / ruta
    return ruta


def abrir_enlace(url):
    url = str(url or "").strip()
    if re.match(r"^(www\.)?[\w-]+(\.[\w-]+)+(/\S*)?$", url):
        url = "https://" + url
    if not re.match(r"^https?://\S+$", url):
        return False, t("Solo abro enlaces web (http/https).", "I only open web links (http/https).")
    return abrir(url), t("Abrí el enlace.", "Opened the link.")


def abrir_ruta(texto):
    ruta = ruta_de(texto)
    if not ruta.exists():
        return False, t(f"No existe {ruta}.", f"{ruta} doesn't exist.")
    if not permitido(ruta):
        return False, t("Esa carpeta no la abro.", "I won't open that one.")
    if ruta.is_file() and ruta.suffix.lower() not in ABRIBLES:
        return False, t("Ese tipo de archivo no lo abro (podría ejecutar algo).", "I won't open that file type (it could run something).")
    return abrir(ruta), t(f"Abrí {ruta.name or ruta}.", f"Opened {ruta.name or ruta}.")


def listar(texto):
    ruta = ruta_de(texto or "~")
    if not ruta.is_dir():
        return t(f"No existe la carpeta {ruta}.", f"No folder {ruta}.")
    if not permitido(ruta):
        return t("Esa carpeta es privada.", "That folder is private.")
    entradas = []
    for e in sorted(ruta.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if e.name.startswith(".") or PROHIBIDO.search(e.name):
            continue
        entradas.append(e.name + ("/" if e.is_dir() else ""))
        if len(entradas) >= 200:
            entradas.append("…")
            break
    return f"{ruta}:\n" + ("\n".join(entradas) or t("(vacía)", "(empty)"))


def leer(texto, base=None):
    ruta = ruta_de(texto, base)
    if not ruta.is_file():
        return t(f"No existe el archivo {ruta}.", f"No file {ruta}.")
    if not permitido(ruta) and not (base and Path(base).resolve() in ruta.resolve().parents):
        return t("Ese archivo es privado: no lo leo.", "That file is private: I won't read it.")
    if PROHIBIDO.search(str(ruta)):
        return t("Ese archivo es privado: no lo leo.", "That file is private: I won't read it.")
    try:
        datos = ruta.read_bytes()[:MAX_LECTURA]
    except OSError as e:
        return str(e)
    if b"\x00" in datos[:2000]:
        return t("Es un archivo binario: no lo puedo leer como texto.", "It's a binary file: I can't read it as text.")
    texto = datos.decode("utf-8", errors="replace")
    return texto + ("\n[…]" if ruta.stat().st_size > MAX_LECTURA else "")


# ---------------------------------------------------------------- música

TECLAS = {"reproducir": 0xB3, "pausar": 0xB3, "alternar": 0xB3, "siguiente": 0xB0, "anterior": 0xB1}


def musica(accion):
    """accion: alternar | reproducir | pausar | siguiente | anterior | que_suena."""
    if WINDOWS:
        if accion == "que_suena":
            return False, t("En Windows no puedo ver qué suena.", "On Windows I can't see what's playing.")
        import ctypes
        tecla = TECLAS.get(accion, 0xB3)
        ctypes.windll.user32.keybd_event(tecla, 0, 0, 0)
        ctypes.windll.user32.keybd_event(tecla, 0, 2, 0)        # KEYEVENTF_KEYUP
        return True, {"siguiente": t("Siguiente canción.", "Next song."), "anterior": t("Canción anterior.", "Previous song.")}.get(
            accion, t("Listo.", "Done."))
    if not tiene("playerctl"):
        return False, t("Para controlar la música instala playerctl.", "Install playerctl to control music.")
    if accion == "que_suena":
        ok, salida = correr(["playerctl", "metadata", "--format", "{{artist}} — {{title}} ({{playerName}}, {{status}})"], 5)
        return ok, salida if ok and salida.strip(" —()") else t("No suena nada.", "Nothing is playing.")
    orden = {"reproducir": "play", "pausar": "pause", "alternar": "play-pause", "siguiente": "next", "anterior": "previous"}[accion]
    ok, salida = correr(["playerctl", orden], 5)
    if not ok:
        return False, t("No hay ningún reproductor abierto.", "No player is open.")
    return True, {"siguiente": t("Siguiente canción.", "Next song."), "anterior": t("Canción anterior.", "Previous song."),
                  "pausar": t("En pausa.", "Paused."), "reproducir": t("Reproduciendo.", "Playing.")}.get(accion, t("Listo.", "Done."))


# ---------------------------------------------------------------- pantalla y cámara

CAPTURA_WINDOWS = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$r = [System.Windows.Forms.SystemInformation]::VirtualScreen
$b = New-Object System.Drawing.Bitmap $r.Width, $r.Height
$g = [System.Drawing.Graphics]::FromImage($b)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $b.Size)
$b.Save($env:AKARI_ARCHIVO, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $b.Dispose()
"""


def _portal(archivo):
    """Captura con el portal de escritorio (GNOME/otros en Wayland), vía gdbus. Devuelve la ruta que
    dejó el portal o None. El portal guarda la imagen en Imágenes: se borra después de leerla."""
    if not tiene("gdbus"):
        return None
    monitor = subprocess.Popen(["gdbus", "monitor", "--session", "--dest", "org.freedesktop.portal.Desktop"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        ok, _ = correr(["gdbus", "call", "--session", "--dest", "org.freedesktop.portal.Desktop", "--object-path",
                        "/org/freedesktop/portal/desktop", "--method", "org.freedesktop.portal.Screenshot.Screenshot",
                        "", "{'interactive': <false>}"], 10)
        if not ok:
            return None
        fin = time.time() + 10
        while time.time() < fin:
            linea = monitor.stdout.readline()
            m = re.search(r"'uri': <'file://([^']+)'>", linea)
            if m:
                return urllib.parse.unquote(m.group(1))
            if "Response" in linea and "uint32 0" not in linea:
                return None
    finally:
        monitor.kill()
    return None


def capturar_pantalla():
    """PNG de toda la pantalla (bytes) o None. El archivo temporal se borra enseguida."""
    with tempfile.TemporaryDirectory(prefix="akari-") as tmp:
        archivo = str(Path(tmp) / "pantalla.png")
        if WINDOWS:
            powershell(CAPTURA_WINDOWS, 20, {**os.environ, "AKARI_ARCHIVO": archivo})
        else:
            wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
            escritorio = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            opciones = []
            if wayland and "KDE" in escritorio:
                opciones.append(["spectacle", "-b", "-n", "-f", "-o", archivo])
            if wayland and "GNOME" not in escritorio and "KDE" not in escritorio:
                opciones.append(["grim", archivo])
            if not wayland:
                opciones += [["maim", archivo], ["scrot", "-o", archivo], ["import", "-window", "root", archivo]]
            opciones += [["spectacle", "-b", "-n", "-f", "-o", archivo], ["gnome-screenshot", "-f", archivo], ["grim", archivo]]
            for orden in opciones:
                if tiene(orden[0]) and correr(orden, 15)[0] and Path(archivo).exists():
                    break
            else:
                ruta = _portal(archivo) if wayland else None
                if ruta and Path(ruta).exists():
                    datos = Path(ruta).read_bytes()
                    Path(ruta).unlink(missing_ok=True)
                    return datos
        try:
            return Path(archivo).read_bytes()
        except OSError:
            return None


def _camara_windows(ffmpeg):
    ok, salida = correr([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], 15)
    m = re.search(r'"([^"]+)"\s*\(video\)', salida)
    return ["-f", "dshow", "-i", f"video={m.group(1)}"] if m else None


def foto_camara():
    """Una foto JPEG (bytes) de la cámara con ffmpeg, sin guardarla en ningún lado; o (None, motivo)."""
    ffmpeg = buscar("ffmpeg")
    if not ffmpeg:
        return None, t("Para la cámara hace falta ffmpeg.", "The camera needs ffmpeg.")
    if WINDOWS:
        entrada = _camara_windows(ffmpeg)
    else:
        dispositivos = sorted(glob.glob("/dev/video*"))
        entrada = ["-f", "v4l2", "-i", dispositivos[0]] if dispositivos else None
    if not entrada:
        return None, t("No encontré una cámara.", "No camera found.")
    try:
        # unos cuadros de calentamiento: el primero suele salir negro o sin exposición
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", *entrada, "-vf", "select=gte(n\\,10)",
                            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                           capture_output=True, timeout=20, **SIN_VENTANA)
    except (OSError, subprocess.TimeoutExpired):
        return None, t("La cámara no respondió.", "The camera didn't respond.")
    return (r.stdout, "") if r.returncode == 0 and r.stdout else (None, t("La cámara está ocupada o no responde.", "The camera is busy or not responding."))


# ---------------------------------------------------------------- web

BUSCADORES = {"web": "https://duckduckgo.com/?q={}", "youtube": "https://www.youtube.com/results?search_query={}",
              "musica": "https://open.spotify.com/search/{}", "repos": "https://github.com/search?type=repositories&q={}",
              "mapas": "https://www.openstreetmap.org/search?query={}"}


def buscar_web(donde, consulta):
    plantilla = BUSCADORES.get(donde, BUSCADORES["web"])
    url = plantilla.format(urllib.parse.quote(str(consulta or "")[:300]))
    return abrir(url), t("Abrí la búsqueda.", "Opened the search.")


# ---------------------------------------------------------------- notas

def anotar(carpeta, texto, titulo=""):
    """Agrega una nota al archivo del día de akari dentro de la carpeta elegida (nunca toca las notas
    del usuario: escribe solo en <carpeta>/akari/AAAA-MM-DD.md)."""
    if not carpeta or not Path(carpeta).is_dir():
        return False, t("Primero elige la carpeta de notas en el asistente.", "First choose the notes folder in the assistant.")
    destino = Path(carpeta) / "akari"
    destino.mkdir(exist_ok=True)
    archivo = destino / (time.strftime("%Y-%m-%d") + ".md")
    nuevo = not archivo.exists()
    with open(archivo, "a", encoding="utf-8") as f:
        if nuevo:
            f.write(f"# {time.strftime('%Y-%m-%d')}\n\n")
        f.write(f"- {time.strftime('%H:%M')} " + (f"**{titulo.strip()}** — " if titulo.strip() else "")
                + " ".join(str(texto).split()) + "\n")
    return True, t(f"Anotado en {archivo.parent.name}/{archivo.name}.", f"Noted in {archivo.parent.name}/{archivo.name}.")


def buscar_notas(carpeta, consulta, maximo=6):
    if not carpeta or not Path(carpeta).is_dir():
        return t("Primero elige la carpeta de notas en el asistente.", "First choose the notes folder in the assistant.")
    palabras = [sin_acentos(p) for p in re.findall(r"\w{3,}", consulta or "")]
    if not palabras:
        return "?"
    resultados = []
    for ruta in Path(carpeta).rglob("*.md"):
        if any(p.startswith(".") for p in ruta.relative_to(carpeta).parts):      # .obsidian, .trash…
            continue
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")[:200000]
        except OSError:
            continue
        normal = sin_acentos(texto)
        puntos = sum(normal.count(p) for p in palabras) + 3 * sum(p in sin_acentos(ruta.stem) for p in palabras)
        if puntos:
            i = min((normal.find(p) for p in palabras if p in normal), default=0)
            trozo = " ".join(texto[max(0, i - 120): i + 280].split())
            resultados.append((puntos, str(ruta.relative_to(carpeta)), trozo))
    resultados.sort(reverse=True)
    if not resultados:
        return t("No encontré nada en tus notas.", "Nothing found in your notes.")
    return "\n\n".join(f"[{r}] …{trozo}…" for _, r, trozo in resultados[:maximo])
