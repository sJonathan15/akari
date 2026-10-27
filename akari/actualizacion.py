"""¿Hay una versión nueva de akari? Una vez al día mira la última release en GitHub.

Sin prereleases salvo que esta versión ya sea una beta (0.2.0-beta.1) o el usuario lo pida con
ajustes.json "actualizar": "beta"; "actualizar": false lo apaga del todo. Lo que encuentra va en
/api/estado como actualizacion: {version, notas, url, beta, pospuesta, instalando} y avisa una vez
por versión («Ahora no» la deja de avisar hasta la siguiente).

`akari actualizar` baja esa versión y vuelve a pasar el instalador con el que se instaló akari
(install.sh, install.ps1 o el instalador de la app de Windows): la configuración (CONFIG) y los
datos no se tocan. Luego reinicia el servicio y la interfaz.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from . import VERSION
from .comun import CACHE, CONFIG, DATOS, RAIZ, SIN_VENTANA, WINDOWS, ajustes, escribir_json, leer_json, notificar, t

REPO = "sJonathan15/akari"
API = os.environ.get("AKARI_RELEASES_URL") or f"https://api.github.com/repos/{REPO}"     # otra solo para pruebas
DESCARGAS = os.environ.get("AKARI_DESCARGAS_URL") or f"https://github.com/{REPO}"
REGISTRO = CACHE / "actualizar.log"
CADA = 24 * 3600
ARCHIVO = CACHE / "actualizacion.json"


def clave(version):
    """Orden de versiones semver: 0.2.0-beta.1 < 0.2.0-beta.2 < 0.2.0 < 0.10.0."""
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?", str(version or "").strip())
    if not m:
        return None
    numeros = tuple(int(x or 0) for x in m.groups()[:3])
    if not m.group(4):
        return numeros + ((1,),)
    pre = tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in m.group(4).split("."))
    return numeros + ((0,) + pre,)


def es_beta(version=None):
    return "-" in str(version or VERSION)


def mas_nueva(otra, actual=None):
    a, b = clave(otra), clave(actual or VERSION)
    return a is not None and b is not None and a > b


def pedir(ruta):
    req = urllib.request.Request(API + ruta, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"akari/{VERSION}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def ultima(con_betas):
    """La release más nueva (con o sin prereleases), como la da la API de GitHub."""
    if not con_betas:
        return pedir("/releases/latest")
    lista = [r for r in pedir("/releases?per_page=20") if not r.get("draft")]
    lista = [r for r in lista if clave(r.get("tag_name")) is not None]
    return max(lista, key=lambda r: clave(r["tag_name"]), default=None)


class Revisor:
    def __init__(self, cambio):
        self.cambio = cambio
        self.estado = None
        self.release = None       # la release entera (para `akari actualizar`)
        self.instalando = None    # el proceso de `akari actualizar` lanzado desde el panel
        guardado = leer_json(ARCHIVO)
        self._poner(guardado.get("release"), avisar=False)

    def modo(self):
        """None (apagado), "beta" (también prereleases) o "estable"."""
        valor = ajustes().get("actualizar")
        if valor is False:
            return None
        return "beta" if valor == "beta" or es_beta() else "estable"

    def _poner(self, release, avisar=True):
        anterior = self.estado
        if release and mas_nueva(release.get("tag_name")) and self.modo():
            self.release = release
            notas = (release.get("body") or "").strip()
            version = release["tag_name"].lstrip("v")
            self.estado = {"version": version, "notas": notas[:4000],
                           "url": release.get("html_url") or f"https://github.com/{REPO}/releases",
                           "beta": bool(release.get("prerelease")),
                           "pospuesta": leer_json(ARCHIVO).get("pospuesta") == version,
                           "instalando": self.instalando is not None and self.instalando.poll() is None}
        else:
            self.release = self.estado = None
        if self.estado != anterior:
            self.cambio()
        if avisar and self.estado and not self.estado["pospuesta"] and leer_json(ARCHIVO).get("avisada") != self.estado["version"]:
            notificar(t("Hay una versión nueva de akari", "A new version of akari is available"),
                      t(f"akari {self.estado['version']}: ábrelo desde el panel o con «akari actualizar».",
                        f"akari {self.estado['version']}: open it from the panel or run “akari actualizar”."))
            escribir_json(ARCHIVO, {**leer_json(ARCHIVO), "avisada": self.estado["version"]})

    def revisar(self, forzar=False):
        modo = self.modo()
        if not modo:
            return self._poner(None)
        guardado = leer_json(ARCHIVO)
        if not forzar and time.time() - float(guardado.get("revisado") or 0) < CADA and guardado.get("modo") == modo:
            return self._poner(guardado.get("release"), avisar=False)
        try:
            release = ultima(modo == "beta")
        except (OSError, ValueError) as e:      # sin internet o GitHub caído: mañana otra vez
            print(f"akari: no pude revisar si hay versión nueva: {e!r}", flush=True)
            return
        corta = {k: release.get(k) for k in ("tag_name", "name", "body", "html_url", "prerelease", "assets")} if release else None
        if corta and corta.get("assets"):
            corta["assets"] = [{"name": a.get("name"), "browser_download_url": a.get("browser_download_url"),
                                "size": a.get("size")} for a in corta["assets"]]
        escribir_json(ARCHIVO, {**guardado, "revisado": time.time(), "modo": modo, "release": corta})
        self._poner(corta)

    def accion(self, datos):
        """POST /api/actualizacion: revisar, ahora-no o instalar."""
        accion = datos.get("accion")
        if accion == "revisar":
            threading.Thread(target=self.revisar, args=(True,), daemon=True).start()
            return True, ""
        if not self.estado:
            return False, t("akari ya está al día.", "akari is up to date.")
        if accion == "ahora-no":
            escribir_json(ARCHIVO, {**leer_json(ARCHIVO), "pospuesta": self.estado["version"]})
            self._poner(self.release, avisar=False)
            return True, ""
        if accion == "instalar":
            if self.estado["instalando"]:
                return True, ""
            if instalacion() == "windows-app":
                # la app de Windows se actualiza sola (su aviso «Hay una versión nueva»)
                return False, t("Actualiza desde el aviso de la app de akari.", "Update from the akari app's notice.")
            self.instalando = lanzar_actualizacion(self.estado["version"])
            self._poner(self.release, avisar=False)
            threading.Thread(target=self._esperar_instalacion, daemon=True).start()
            return True, t("Actualizando… akari se reinicia solo.", "Updating… akari restarts by itself.")
        return False, "?"

    def _esperar_instalacion(self):
        codigo = self.instalando.wait()
        if codigo:      # si salió bien, este servicio ya no existe: lo reemplazó el nuevo
            notificar(t("No pude actualizar akari", "Could not update akari"),
                      t(f"Detalles en {REGISTRO}", f"Details in {REGISTRO}"))
        self._poner(self.release, avisar=False)

    def bucle(self, espera=60):
        """Un minuto después de arrancar y luego cada hora mira si ya toca (una vez al día)."""
        time.sleep(espera)
        while True:
            try:
                self.revisar()
            except Exception as e:
                print(f"akari: actualizacion: {e!r}", flush=True)
            time.sleep(3600)

    def arrancar(self):
        threading.Thread(target=self.bucle, daemon=True).start()


# ---------------------------------------------------------------- actualizar


def instalacion(raiz=None):
    """Cómo se instaló akari: git, linux (install.sh), windows-codigo (install.ps1 -DesdeCodigo),
    windows-app (instalador de la app de Windows), appimage u otra."""
    raiz = Path(raiz or RAIZ).resolve()
    if (raiz / ".git").exists():
        return "git"
    if raiz.name == "servicio" and (raiz.parent / "akari.exe").exists():
        return "windows-app"
    if "/.mount_" in str(raiz) or os.environ.get("APPIMAGE"):
        return "appimage"
    if raiz == Path(DATOS).resolve():
        return "windows-codigo" if WINDOWS else "linux"
    return "otra"


def lanzar_actualizacion(version):
    """`akari actualizar <versión>` aparte, para que sobreviva al reinicio del servicio."""
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    registro = open(REGISTRO, "w", encoding="utf-8")
    orden = [sys.executable, str(RAIZ / "bin" / "akari.py"), "actualizar", "--version", str(version)]
    if WINDOWS:
        aparte = {"creationflags": 0x00000008 | 0x00000200 | SIN_VENTANA["creationflags"]}  # DETACHED, NEW_GROUP, NO_WINDOW
    else:
        aparte = {"start_new_session": True}
    return subprocess.Popen(orden, stdin=subprocess.DEVNULL, stdout=registro, stderr=subprocess.STDOUT, **aparte)


def bajar(url, destino):
    req = urllib.request.Request(url, headers={"User-Agent": f"akari/{VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)
    return destino


def extraer(archivo, carpeta):
    """Descomprime sin dejar salir nada de `carpeta` (rutas absolutas, .., enlaces)."""
    carpeta = Path(carpeta).resolve()
    if str(archivo).endswith(".zip"):
        with zipfile.ZipFile(archivo) as z:
            for n in z.namelist():
                if not (carpeta / n).resolve().is_relative_to(carpeta):
                    raise ValueError(f"ruta peligrosa en el archivo: {n}")
            z.extractall(carpeta)
    else:
        with tarfile.open(archivo) as tf:
            miembros = []
            for m in tf.getmembers():
                if not (carpeta / m.name).resolve().is_relative_to(carpeta) or m.issym() or m.islnk() or m.isdev():
                    continue
                miembros.append(m)
            tf.extractall(carpeta, members=miembros)
    dentro = [d for d in carpeta.iterdir() if d.is_dir()]
    return dentro[0] if len(dentro) == 1 else carpeta


def objetivo(version=None):
    """La release a instalar: la pedida, o la más nueva del canal de este usuario."""
    if version:
        etiqueta = version if str(version).startswith("v") else f"v{version}"
        return pedir(f"/releases/tags/{etiqueta}")
    valor = ajustes().get("actualizar")
    return ultima(valor == "beta" or es_beta())


def reiniciar(tipo):
    """Tras instalar: el servicio y la interfaz con el código nuevo (la configuración sigue igual)."""
    akari = [sys.executable, str(RAIZ / "bin" / "akari.py")]
    if tipo == "linux":
        unidades = [u for u in ("akari.service", "akari-capsulas.service")
                    if shutil.which("systemctl") and subprocess.run(
                        ["systemctl", "--user", "is-active", "--quiet", u]).returncode == 0]
        if unidades:
            subprocess.run(["systemctl", "--user", "restart", *unidades])
        else:
            for patron in (f"{RAIZ}/bin/akari.py servicio", f"{RAIZ}/capsulas"):
                subprocess.run(["pkill", "-f", patron], stderr=subprocess.DEVNULL)
            time.sleep(1)
        subprocess.Popen([*akari, "arrancar"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


def actualizar(version=None, forzar=False):
    """`akari actualizar [--version X] [--forzar]`. Devuelve (ok, mensaje)."""
    tipo = instalacion()
    if tipo == "git":
        return False, t("Esta es una copia de git: actualízala con «git pull».", "This is a git checkout: update it with “git pull”.")
    if tipo in ("appimage", "otra"):
        return False, t(f"Baja la versión nueva desde {DESCARGAS}/releases", f"Download the new version from {DESCARGAS}/releases")
    if tipo == "windows-app" and os.environ.get("AKARI_APP_ID"):
        return False, t("Actualiza desde el aviso de la app de akari.", "Update from the akari app's notice.")
    try:
        release = objetivo(version)
    except (OSError, ValueError) as e:
        return False, t(f"No pude preguntar a GitHub: {e}", f"Could not reach GitHub: {e}")
    if not release:
        return False, t("No encontré ninguna versión publicada.", "No published version found.")
    etiqueta = release["tag_name"]
    if not forzar and not mas_nueva(etiqueta):
        return True, t(f"akari {VERSION} ya está al día.", f"akari {VERSION} is up to date.")
    print(t(f"Actualizando akari {VERSION} → {etiqueta.lstrip('v')}…", f"Updating akari {VERSION} → {etiqueta.lstrip('v')}…"), flush=True)
    tmp = Path(tempfile.mkdtemp(prefix="akari-actualizar-", dir=CACHE if CACHE.exists() else None))
    try:
        if tipo == "windows-app":
            exe = next((a["browser_download_url"] for a in release.get("assets") or []
                        if a.get("name") == "akari-setup-x64.exe"), None)
            if not exe:
                return False, t("Esa versión no trae el instalador de Windows.", "That version has no Windows installer.")
            setup = bajar(exe, CACHE / "akari-setup-x64.exe")
            # este proceso usa el Python de la app: el instalador corre cuando ya terminó. Cierra la
            # app, reemplaza sus archivos (la configuración está en %APPDATA%) y se vuelve a abrir.
            ps = lambda ruta: "'" + str(ruta).replace("'", "''") + "'"
            guion = (f"Start-Sleep -Seconds 2; Start-Process -Wait -FilePath {ps(setup)} -ArgumentList '/S'; "
                     f"Remove-Item {ps(setup)} -ErrorAction SilentlyContinue; Start-Process -FilePath {ps(RAIZ.parent / 'akari.exe')}")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", guion],
                             creationflags=0x00000008 | 0x00000200 | SIN_VENTANA["creationflags"])
            return True, t(f"Instalando akari {etiqueta.lstrip('v')}: la app se cierra y se vuelve a abrir sola.",
                           f"Installing akari {etiqueta.lstrip('v')}: the app closes and reopens by itself.")
        elif tipo == "windows-codigo":
            origen = extraer(bajar(f"{DESCARGAS}/archive/refs/tags/{etiqueta}.zip", tmp / "akari.zip"), tmp / "codigo")
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(origen / "install.ps1"),
                                "-Si", "-SinStatusline", "-DesdeCodigo", "-Version", etiqueta], **SIN_VENTANA)
            if r.returncode:
                return False, t(f"install.ps1 terminó con el código {r.returncode}.", f"install.ps1 exited with code {r.returncode}.")
        else:
            origen = extraer(bajar(f"{DESCARGAS}/archive/refs/tags/{etiqueta}.tar.gz", tmp / "akari.tar.gz"), tmp / "codigo")
            orden = ["bash", str(origen / "install.sh"), "--si", "--sin-dependencias", "--sin-statusline", "--version", etiqueta]
            interfaz = ajustes().get("interfaz")
            if interfaz in ("capsulas", "gnome", "app"):
                orden += ["--interfaz", interfaz]
            # sin sesión gráfica el instalador no arranca nada: lo hace reiniciar() después
            r = subprocess.run(orden, env={**os.environ, "DISPLAY": "", "WAYLAND_DISPLAY": ""})
            if r.returncode:
                return False, t(f"install.sh terminó con el código {r.returncode}.", f"install.sh exited with code {r.returncode}.")
            reiniciar(tipo)
    except (OSError, ValueError) as e:
        return False, t(f"No pude actualizar: {e}", f"Could not update: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    escribir_json(ARCHIVO, {k: v for k, v in leer_json(ARCHIVO).items() if k not in ("release", "revisado")})
    return True, t(f"akari {etiqueta.lstrip('v')} instalado. Tu configuración ({CONFIG}) sigue igual.",
                   f"akari {etiqueta.lstrip('v')} installed. Your settings ({CONFIG}) are unchanged.")
