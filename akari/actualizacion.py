"""¿Hay una versión nueva de akari? Una vez al día mira la última release en GitHub.

Sin prereleases salvo que esta versión ya sea una beta (0.2.0-beta.1) o el usuario lo pida con
ajustes.json "actualizar": "beta"; "actualizar": false lo apaga del todo. Lo que encuentra va en
/api/estado como actualizacion: {version, notas, url, beta} y avisa una vez por versión.
"""
import json
import os
import re
import threading
import time
import urllib.request

from . import VERSION
from .comun import CACHE, ajustes, escribir_json, leer_json, notificar, t

REPO = "sJonathan15/akari"
API = os.environ.get("AKARI_RELEASES_URL") or f"https://api.github.com/repos/{REPO}"     # otra solo para pruebas
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
            self.estado = {"version": release["tag_name"].lstrip("v"), "notas": notas[:4000],
                           "url": release.get("html_url") or f"https://github.com/{REPO}/releases",
                           "beta": bool(release.get("prerelease"))}
        else:
            self.release = self.estado = None
        if self.estado != anterior:
            self.cambio()
        if avisar and self.estado and leer_json(ARCHIVO).get("avisada") != self.estado["version"]:
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
