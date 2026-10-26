"""Colores del escritorio para que akari se vea nativo en cada sistema.

Se toma el primero que exista:
  1. ~/.config/akari/tema.json: {"acento": "#ff8800"} o colores sueltos (primary, surface…);
  2. Caelestia (~/.local/state/caelestia/scheme.json): el esquema Material 3 completo;
  3. pywal / wallust (~/.cache/wal/colors.json): el color más vivo de la paleta;
  4. KDE Plasma (kdeglobals): AccentColor o el color de selección;
  5. GNOME 47+: org.gnome.desktop.interface accent-color;
  6. Windows: el color de énfasis (HKCU\\Software\\Microsoft\\Windows\\DWM\\AccentColor).
Si no hay ninguno, la paleta oscura de akari. El resultado usa los nombres de Material 3
(los mismos de Caelestia), así lo entienden las cápsulas QML, el panel web y la app.
"""
import colorsys
import json
import os
import time

from .comun import CONFIG, HOME, WINDOWS, correr, leer_json, tiene

FABRICA = {
    "primary": "#b7c4ff", "onPrimary": "#1e2d60", "primaryContainer": "#6674ac",
    "secondary": "#c1c5e0", "secondaryContainer": "#41465c", "onSecondaryContainer": "#e0e2f0",
    "tertiary": "#f1b3e6", "error": "#ffb4ab", "success": "#b5ccba",
    "surface": "#131317", "onSurface": "#e4e1e7", "onSurfaceVariant": "#c6c5d1",
    "surfaceContainer": "#1f1f23", "surfaceContainerHigh": "#292a2e", "surfaceContainerHighest": "#343438",
    "outline": "#8f909a", "outlineVariant": "#45464f",
}
# acentos de GNOME 47+ (libadwaita)
ACENTOS_GNOME = {"blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a", "yellow": "#c88800",
                 "orange": "#ed5b00", "red": "#e62d42", "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396"}
CADA = 10


def rgb(hexa):
    hexa = str(hexa or "").lstrip("#")
    if len(hexa) == 8:          # AARRGGBB
        hexa = hexa[2:]
    if len(hexa) != 6:
        raise ValueError(hexa)
    return tuple(int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hexa(c):
    return "#" + "".join(f"{round(max(0, min(1, x)) * 255):02x}" for x in c)


def mezcla(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def desde_acento(acento):
    """Paleta oscura a partir de un solo color, como hacen las cápsulas con el acento de KDE."""
    a = rgb(acento)
    h, l, s = colorsys.rgb_to_hls(*a)
    claro = colorsys.hls_to_rgb(h, max(l, 0.78), min(s, 0.9) if s > 0.05 else s)
    superficie = rgb(FABRICA["surface"])
    return {**FABRICA,
            "primary": hexa(claro),
            "onPrimary": hexa(colorsys.hls_to_rgb(h, 0.2, min(s, 0.6))),
            "primaryContainer": hexa(mezcla(a, superficie, 0.45)),
            "secondaryContainer": hexa(mezcla(a, rgb("#2a2a30"), 0.75)),
            "onSecondaryContainer": hexa(mezcla(claro, (1, 1, 1), 0.6))}


def caelestia():
    colores = leer_json(HOME / ".local" / "state" / "caelestia" / "scheme.json").get("colours") or {}
    if not colores.get("primary"):
        return None
    return {**FABRICA, **{k: "#" + str(v).lstrip("#") for k, v in colores.items() if k in FABRICA}}


def pywal():
    colores = (leer_json(HOME / ".cache" / "wal" / "colors.json").get("colors") or {})
    candidatos = []
    for i in range(1, 7):
        try:
            c = rgb(colores.get(f"color{i}"))
        except ValueError:
            continue
        _, l, s = colorsys.rgb_to_hls(*c)
        candidatos.append((s * (1 - abs(l - 0.55)), colores[f"color{i}"]))
    return max(candidatos)[1] if candidatos else None


def kde():
    """Color de acento de KDE Plasma en hexadecimal ("r,g,b" en kdeglobals)."""
    ruta = HOME / ".config" / "kdeglobals"
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    seccion = ""
    seleccion = None
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("["):
            seccion = linea
        elif linea.startswith("AccentColor=") and seccion == "[General]":
            return kde_a_hexa(linea.split("=", 1)[1])
        elif linea.startswith("BackgroundNormal=") and seccion == "[Colors:Selection]":
            seleccion = linea.split("=", 1)[1]
    return kde_a_hexa(seleccion) if seleccion else None


def kde_a_hexa(texto):
    partes = [int(x) for x in texto.split(",")[:3]]
    return hexa(tuple(x / 255 for x in partes))


def gnome():
    escritorio = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "gnome" not in escritorio or not tiene("gsettings"):
        return None
    ok, salida = correr(["gsettings", "get", "org.gnome.desktop.interface", "accent-color"], timeout=3)
    return ACENTOS_GNOME.get(salida.strip("'\" \n")) if ok else None


def windows():
    if not WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
            valor, _ = winreg.QueryValueEx(k, "AccentColor")       # 0xAABBGGRR
    except (OSError, ImportError):
        return None
    return hexa(((valor & 0xFF) / 255, (valor >> 8 & 0xFF) / 255, (valor >> 16 & 0xFF) / 255))


def calcular():
    propio = leer_json(CONFIG / "tema.json")
    sueltos = {k: v for k, v in propio.items() if k in FABRICA}
    try:
        if propio.get("acento"):
            return {"fuente": "akari", "colores": {**desde_acento(propio["acento"]), **sueltos}}
        if sueltos:
            return {"fuente": "akari", "colores": {**FABRICA, **sueltos}}
    except ValueError:
        pass
    esquema = caelestia()
    if esquema:
        return {"fuente": "caelestia", "colores": esquema}
    for fuente, leer in (("pywal", pywal), ("kde", kde), ("gnome", gnome), ("windows", windows)):
        try:
            acento = leer()
            if acento:
                return {"fuente": fuente, "colores": desde_acento(acento)}
        except (ValueError, TypeError):
            continue
    return {"fuente": "akari", "colores": dict(FABRICA)}


class Tema:
    """El tema actual, recalculado como mucho cada CADA segundos."""

    def __init__(self):
        self.valor = calcular()
        self.t = time.time()

    def actual(self):
        if time.time() - self.t > CADA:
            self.t = time.time()
            self.valor = calcular()
        return self.valor


if __name__ == "__main__":
    print(json.dumps(calcular(), indent=2))
