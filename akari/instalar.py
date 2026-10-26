"""Conectar (o desconectar) akari a la línea de estado de Claude Code.

Lo usan install.sh, install.ps1 y la app de escritorio (menú de la bandeja). La línea de
estado que ya tuviera el usuario se anota en ~/.config/akari/statusline-previa.json y
`akari statusline` la sigue mostrando; al desconectar se devuelve tal cual estaba.
"""
import shutil
import sys

from .comun import CONFIG, HOME, RAIZ, WINDOWS, escribir_json, leer_json, t
from .ia import CLAUDE_DIR

AJUSTES = CLAUDE_DIR / "settings.json"
PREVIA = CONFIG / "statusline-previa.json"


def orden_statusline():
    """La orden que ejecutará Claude Code. Con barras normales funciona igual en cmd y en Git Bash."""
    lanzador = HOME / ".local" / "bin" / "akari"
    if not WINDOWS and lanzador.exists():
        return f"{lanzador} statusline"
    python = sys.executable.replace("\\", "/")
    return f'"{python}" "{(RAIZ / "bin" / "akari.py").as_posix()}" statusline'


def conectada():
    return "akari" in str((leer_json(AJUSTES).get("statusLine") or {}).get("command", ""))


def conectar_claude(orden=None):
    datos = leer_json(AJUSTES)
    if AJUSTES.exists() and not AJUSTES.with_name(AJUSTES.name + ".bak-akari").exists():
        shutil.copy2(AJUSTES, AJUSTES.with_name(AJUSTES.name + ".bak-akari"))
    actual = datos.get("statusLine") or {}
    if actual.get("command") and "akari" not in actual["command"]:
        escribir_json(PREVIA, {"command": actual["command"]})
    datos["statusLine"] = {"type": "command", "command": orden or orden_statusline(), "padding": 0}
    escribir_json(AJUSTES, datos)
    return t("Línea de estado de Claude Code conectada (respaldo: settings.json.bak-akari).",
             "Claude Code status line connected (backup: settings.json.bak-akari).")


def desconectar_claude():
    datos = leer_json(AJUSTES)
    if not conectada():
        return t("La línea de estado no era de akari: no la toqué.", "The status line was not akari's: left untouched.")
    previa = leer_json(PREVIA).get("command")
    if previa:
        datos["statusLine"] = {"type": "command", "command": previa}
    else:
        datos.pop("statusLine", None)
    escribir_json(AJUSTES, datos)
    return t("Línea de estado de Claude Code devuelta a como estaba.", "Claude Code status line restored.")
