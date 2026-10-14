"""Comando `akari`.

  akari [servicio]     arranca el servicio (lo hace systemd al iniciar sesión)
  akari abrir          abre el panel (ventana flotante)
  akari app            abre la cápsula flotante con icono en la bandeja (X11, XFCE…)
  akari estado         resumen en la terminal
  akari escritorio     qué interfaz conviene en este escritorio (cápsulas, GNOME o panel)
  akari statusline     línea de estado para Claude Code (la configura el instalador)
  akari version
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import webbrowser

from . import PUERTO, VERSION
from .comun import RAIZ, t


def escritorio():
    """Devuelve (nombre del escritorio, interfaz recomendada)."""
    nombre = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    if "gnome" in nombre or "ubuntu" in nombre or "unity" in nombre:
        return nombre, "gnome"
    # wlr-layer-shell: KDE Plasma, Hyprland, Sway, niri, river, Wayfire, labwc, COSMIC…
    if wayland and (shutil.which("qs") or shutil.which("quickshell")):
        return nombre, "capsulas"
    return nombre, "panel"


def pedir_estado():
    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/api/estado", timeout=3) as r:
        return json.load(r)


def entorno_appimage():
    """Ajustes para que el AppImage abra en cualquier distribución: (argumentos extra, entorno).
    * Sin libfuse2 (Ubuntu 22.04+ no lo trae) el AppImage no se monta: se extrae y se ejecuta.
    * Ubuntu 23.10+ (AppArmor) bloquea el sandbox de Chromium en apps sin instalar: --no-sandbox."""
    env = dict(os.environ)
    try:
        libs = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        libs = "libfuse.so.2"
    if "libfuse.so.2" not in libs:
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    extra = []
    try:
        if open("/proc/sys/kernel/apparmor_restrict_unprivileged_userns").read().strip() == "1":
            extra.append("--no-sandbox")
    except OSError:
        pass
    return extra, env


def abrir():
    """Panel: la app empaquetada si existe; si no, el navegador en modo aplicación."""
    url = f"http://127.0.0.1:{PUERTO}/"
    for app in (RAIZ / "app" / "akari-panel", RAIZ / "app" / "node_modules" / ".bin" / "electron"):
        if app.exists():
            extra, env = entorno_appimage()
            orden = [str(app), "--panel", *extra] if app.name == "akari-panel" else [str(app), str(RAIZ / "app"), "--panel", *extra]
            subprocess.Popen(orden, start_new_session=True, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    for nav in ("chromium", "google-chrome-stable", "google-chrome", "brave", "microsoft-edge-stable", "vivaldi"):
        if shutil.which(nav):
            subprocess.Popen([nav, f"--app={url}", "--class=akari", "--window-size=420,760"],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    webbrowser.open(url)


def resumen():
    try:
        e = pedir_estado()
    except OSError:
        print(t("El servicio no está corriendo. Arráncalo con: systemctl --user start akari",
                "The service is not running. Start it with: systemctl --user start akari"))
        return 1
    for clave in ("claude", "codex"):
        p = (e["ia"] or {}).get(clave)
        if not p:
            continue
        cinco = p["limites"]["cinco_horas"]
        libre = f"{round(cinco['libre'])}%" if cinco else "—"
        print(f"{clave.capitalize():8} {t('libre 5 h', '5h left')}: {libre:>5}   "
              f"{t('tokens hoy', 'tokens today')}: {p['tokens']['hoy']['nuevos']:,}   {p.get('modelo_actual') or ''}")
    for d in (e["dispositivos"] or {}).get("dispositivos", []):
        bat = f"{d['bateria']}%" if d["bateria"] is not None else "—"
        print(f"{d['tipo_nombre']:10} {d['nombre'][:28]:28} {'●' if d['conectado'] else '○'} {bat:>5}")
    h = e["habilidades"] or {}
    if h:
        print(t(f"Habilidades: {h['total']} instaladas · {h['recomendadas_instaladas']}/10 recomendadas",
                f"Skills: {h['total']} installed · {h['recomendadas_instaladas']}/10 recommended"))
    return 0


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else "servicio"
    if orden == "servicio":
        from .servidor import main as servir
        servir()
    elif orden == "statusline":
        from .statusline import main as linea
        linea()
    elif orden == "abrir":
        abrir()
    elif orden == "app":
        app = RAIZ / "app" / "akari-panel"
        if not app.exists():
            sys.exit(t("No está la app (AppImage): vuelve a ejecutar el instalador.", "The app (AppImage) is missing: run the installer again."))
        extra, env = entorno_appimage()
        subprocess.Popen([str(app), *extra], start_new_session=True, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif orden == "estado":
        sys.exit(resumen())
    elif orden == "escritorio":
        nombre, interfaz = escritorio()
        print(f"{nombre or '?'} → {interfaz}")
    elif orden in ("version", "--version", "-v"):
        print(f"akari {VERSION}")
    else:
        print(__doc__)
        sys.exit(0 if orden in ("ayuda", "help", "--help", "-h") else 2)


if __name__ == "__main__":
    main()
