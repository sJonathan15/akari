"""Ayudantes del CI para publicar una versión (etiqueta v*):

  python herramientas/publicar.py version v0.2.0        pone 0.2.0 en el servicio, la app de Windows y la de Linux
  python herramientas/publicar.py latest v0.2.0 dist    escribe dist/latest.json con las firmas (*.sig) de dist/

latest.json es el formato del plugin updater de Tauri; lo leen la app de Windows
(escritorio/src/actualizar.rs) y el AppImage (app/actualizar.js).
"""
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPO = "https://github.com/sJonathan15/akari"
# archivo de la release → plataforma de latest.json
PLATAFORMAS = {"akari-setup-x64.exe": "windows-x86_64", "akari-x86_64.AppImage": "linux-x86_64",
               "akari-arm64.AppImage": "linux-aarch64"}


def limpia(etiqueta):
    version = etiqueta.strip().lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?", version):
        raise SystemExit(f"etiqueta rara: {etiqueta} (se espera vX.Y.Z o vX.Y.Z-beta.N)")
    return version


def cambiar(ruta, patron, nuevo):
    texto = ruta.read_text(encoding="utf-8")
    cambiado, n = re.subn(patron, nuevo, texto, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"no encontré la versión en {ruta}")
    ruta.write_text(cambiado, encoding="utf-8")


def version(etiqueta):
    v = limpia(etiqueta)
    cambiar(RAIZ / "akari" / "__init__.py", r'^VERSION = "[^"]*"', f'VERSION = "{v}"')
    cambiar(RAIZ / "escritorio" / "tauri.conf.json", r'^  "version": "[^"]*"', f'  "version": "{v}"')
    cambiar(RAIZ / "escritorio" / "Cargo.toml", r'^version = "[^"]*"', f'version = "{v}"')
    cambiar(RAIZ / "app" / "package.json", r'^  "version": "[^"]*"', f'  "version": "{v}"')
    print(f"versión {v}")


def latest(etiqueta, carpeta):
    v, carpeta = limpia(etiqueta), Path(carpeta)
    plataformas = {}
    for archivo, plataforma in PLATAFORMAS.items():
        firma = carpeta / f"{archivo}.sig"
        if (carpeta / archivo).exists() and firma.exists():
            plataformas[plataforma] = {"signature": firma.read_text(encoding="utf-8").strip(),
                                       "url": f"{REPO}/releases/download/v{v}/{archivo}"}
    if not plataformas:
        print("sin firmas (*.sig): no hay latest.json; las apps no se actualizarán solas con esta versión")
        return
    datos = {"version": v, "notes": f"{REPO}/releases/tag/v{v}",
             "pub_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "platforms": plataformas}
    (carpeta / "latest.json").write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8")
    print(f"latest.json: {', '.join(plataformas)}")


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "version" and len(sys.argv) == 3:
        version(sys.argv[2])
    elif orden == "latest" and len(sys.argv) == 4:
        latest(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
