"""Línea de estado de Claude Code (`akari statusline`).

Claude Code ejecuta este comando en cada actualización y le pasa por stdin un JSON con el
modelo, el contexto, el costo y los límites de uso (5 h y semanal). Se guarda una copia para
el servicio y se imprime una línea corta. Si el usuario ya tenía su propia línea de estado,
el instalador la anota en ~/.config/akari/statusline-previa.json y aquí se sigue usando.
"""
import json
import subprocess
import sys

from .comun import CONFIG, leer_json, t
from .ia import guardar_lectura


def pct(valor):
    return None if valor is None else round(float(valor))


def main():
    # Claude Code manda UTF-8 (en Windows la consola puede tener otra página de códigos)
    crudo = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        datos = json.loads(crudo or "{}")
    except ValueError:
        datos = {}
    try:
        if datos:
            guardar_lectura(dict(datos))
    except OSError:
        pass

    previa = leer_json(CONFIG / "statusline-previa.json").get("command")
    if previa:
        try:
            r = subprocess.run(previa, shell=True, input=crudo, capture_output=True, text=True, timeout=10)
            sys.stdout.write(r.stdout)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass

    partes = [(datos.get("model") or {}).get("display_name") or "Claude"]
    contexto = pct((datos.get("context_window") or {}).get("used_percentage"))
    if contexto is not None:
        partes.append(t(f"contexto {contexto}%", f"context {contexto}%"))
    limites = datos.get("rate_limits") or {}
    for clave, nombre in (("five_hour", "5 h"), ("seven_day", t("7 d", "7d"))):
        usado = pct((limites.get(clave) or {}).get("used_percentage"))
        if usado is not None:
            partes.append(f"{nombre} {usado}%")
    print(" · ".join(partes))
