"""Comando `akari`.

  akari [servicio]     arranca el servicio (lo hace systemd o la app al iniciar sesión)
  akari arrancar       arranca el servicio y la interfaz si no están (sirve con o sin systemd)
  akari abrir          abre el panel completo (ventana flotante)
  akari app            abre las burbujas flotantes con icono en la bandeja (X11, XFCE, Windows…)
  akari estado         resumen en la terminal
  akari guia           cómo se usa akari en tu escritorio
  akari escritorio     qué interfaz conviene en este escritorio (cápsulas, GNOME o app)
  akari cerebro …      el mapa de tu computadora y la memoria de tus sesiones (akari cerebro ayuda)
  akari recorrido      vuelve a mostrar el recorrido de bienvenida
  akari conectar-claude / desconectar-claude   línea de estado de Claude Code
  akari statusline     línea de estado para Claude Code (la configura el instalador)
  akari version
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import PUERTO, VERSION
from .comun import CACHE, HOME, RAIZ, SIN_VENTANA, WINDOWS, ajustes, t

INTERFACES = ("capsulas", "gnome", "app")
UNIDADES = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "systemd" / "user"


def quickshell():
    return shutil.which("qs") or shutil.which("quickshell")


def escritorio():
    """Devuelve (nombre del escritorio, interfaz recomendada)."""
    if WINDOWS:
        return "windows", "app"
    nombre = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    if any(g in nombre for g in ("gnome", "ubuntu", "unity", "pantheon")):
        return nombre, "gnome"
    # wlr-layer-shell: KDE Plasma, Hyprland, Sway, niri, river, Wayfire, labwc, COSMIC…
    if wayland and quickshell():
        return nombre, "capsulas"
    # todo lo demás (X11, XFCE, Cinnamon, MATE, LXQt, Budgie, KDE sin Quickshell…): burbujas de la app
    return nombre, "app"


def interfaz_elegida():
    """La que dejó el instalador en ajustes.json; si no, la recomendada para este escritorio."""
    elegida = {"panel": "app"}.get(ajustes().get("interfaz"), ajustes().get("interfaz"))
    return elegida if elegida in INTERFACES else escritorio()[1]


GUIA = {
    "gnome": (
        """akari vive en la barra superior de GNOME (arriba a la derecha).

  1. CIERRA SESIÓN Y VUELVE A ENTRAR (solo la primera vez): GNOME carga
     las extensiones al iniciar sesión.
  2. Arriba a la derecha verás tres iconos nuevos:
       ratón/audífonos con %  → tus dispositivos y su batería
       ★ con %                → lo que te queda de Claude Code / Codex
       matraz con un número    → tus habilidades de IA
     Haz clic en cada uno para ver el detalle.
  3. Panel con modelos 3D: en cualquiera de esos menús, "Abrir panel (con 3D)",
     o busca "akari" en tus aplicaciones, o en la terminal: akari abrir

¿No aparecen los iconos tras volver a entrar?
     gnome-extensions enable akari@sjonathan15.github.io   (y vuelve a entrar)""",
        """akari lives in the GNOME top bar (top right).

  1. LOG OUT AND LOG BACK IN (first time only): GNOME loads extensions at login.
  2. At the top right you'll see three new icons:
       mouse/headphones with %  → your devices and their battery
       ★ with %                  → what's left of Claude Code / Codex
       flask with a number        → your AI skills
     Click each one for details.
  3. Panel with 3D models: "Open panel (with 3D)" in any of those menus,
     or search "akari" in your apps, or in a terminal: akari abrir

Icons missing after logging back in?
     gnome-extensions enable akari@sjonathan15.github.io   (then log in again)"""),
    "capsulas": (
        """akari son tres cápsulas que cuelgan del borde superior de la pantalla, cerca del centro:
Equipo (dispositivos), IA (uso, modelos, habilidades) y Archivos (documentos, audio).

  1. Pasa el ratón por un icono de una cápsula para abrirla en eso; abierta, clic en otro icono
     cambia. Suelta un archivo sobre Archivos para convertirlo o transcribirlo.
  2. Clic en su cabecera: la deja abierta. Arrástrala para moverla; contra un borde
     lateral se vuelve pestaña vertical. Doble clic: vuelve a su sitio.
  3. Panel completo con 3D: botón "Abrir panel completo" o, en la terminal: akari abrir

¿No ves las cápsulas?
     systemctl --user restart akari akari-capsulas""",
        """akari is three capsules hanging from the top edge of the screen, near the center:
Computer (devices), AI (usage, models, skills) and Files (documents, audio).

  1. Hover an icon on a capsule to open it there; once open, click another icon to switch.
     Drop a file on Files to convert or transcribe it.
  2. Click its header to pin it open. Drag it to move it; against a side edge it
     becomes a vertical tab. Double-click: back to its place.
  3. Full panel with 3D: "Open full panel" button or, in a terminal: akari abrir

Don't see the capsules?
     systemctl --user restart akari akari-capsulas"""),
    "app": (
        """akari son tres burbujas que cuelgan del borde superior de la pantalla, cerca del centro,
con un icono en la bandeja (igual que las cápsulas de KDE / Hyprland): Equipo (dispositivos),
IA (uso, modelos, habilidades) y Archivos (documentos, audio).

  1. Pasa el ratón por un icono de una burbuja para abrirla en eso; abierta, clic en otro icono
     cambia. Suelta un archivo sobre Archivos para convertirlo o transcribirlo.
  2. Clic en su cabecera: la deja abierta. Arrástrala para moverla; contra un borde
     lateral se vuelve pestaña vertical. Doble clic: vuelve a su sitio.
  3. Panel completo con 3D: clic en el icono de la bandeja, o en la terminal: akari abrir
  4. Desde el icono de la bandeja las ocultas o eliges si arrancan al iniciar sesión.

¿Las cerraste? Busca "akari" en tus aplicaciones, o en la terminal: akari app""",
        """akari is three bubbles hanging from the top edge of the screen, near the center,
with a tray icon (just like the KDE / Hyprland capsules): Computer (devices), AI (usage,
models, skills) and Files (documents, audio).

  1. Hover an icon on a bubble to open it there; once open, click another icon to switch.
     Drop a file on Files to convert or transcribe it.
  2. Click its header to pin it open. Drag it to move it; against a side edge it
     becomes a vertical tab. Double-click: back to its place.
  3. Full panel with 3D: click the tray icon, or in a terminal: akari abrir
  4. From the tray icon you can hide them or choose whether they start at login.

Closed them? Search "akari" in your apps, or in a terminal: akari app"""),
}
GUIA["panel"] = GUIA["app"]
COMUN = (
    """
En la terminal:  akari estado  (resumen) · akari abrir  (panel) · akari guia  (esta ayuda)
Si no hay datos: akari arrancar   (con systemd: systemctl --user restart akari)
Límites de Claude: aparecen después de tu próximo mensaje en Claude Code. Codex: después de usarlo.
Quitar akari:    ~/.local/share/akari/install.sh --desinstalar
Más ayuda:       https://github.com/sJonathan15/akari#primeros-pasos""",
    """
In a terminal:  akari estado  (summary) · akari abrir  (panel) · akari guia  (this help)
No data?        akari arrancar   (with systemd: systemctl --user restart akari)
Claude limits show up after your next message in Claude Code; Codex after you use it.
Remove akari:   ~/.local/share/akari/install.sh --desinstalar
More help:      https://github.com/sJonathan15/akari#first-steps""")


COMUN_WINDOWS = (
    """
En la terminal:  akari estado  (resumen) · akari abrir  (panel) · akari guia  (esta ayuda)
Si no hay datos: cierra akari desde el icono de la bandeja y vuelve a abrirlo.
Límites de Claude: aparecen después de tu próximo mensaje en Claude Code. Codex: después de usarlo.
Quitar akari:    Configuración → Aplicaciones → akari → Desinstalar
Más ayuda:       https://github.com/sJonathan15/akari#primeros-pasos""",
    """
In a terminal:  akari estado  (summary) · akari abrir  (panel) · akari guia  (this help)
No data?        quit akari from the tray icon and open it again.
Claude limits show up after your next message in Claude Code; Codex after you use it.
Remove akari:   Settings → Apps → akari → Uninstall
More help:      https://github.com/sJonathan15/akari#first-steps""")


def guia(interfaz=None):
    interfaz = interfaz if interfaz in GUIA else interfaz_elegida()
    texto = GUIA[interfaz]
    comun = COMUN_WINDOWS if WINDOWS else COMUN
    print(t(texto[0], texto[1]) + t(comun[0], comun[1]))


def pedir_estado():
    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/api/estado", timeout=3) as r:
        return json.load(r)


def vivo():
    try:
        pedir_estado()
        return True
    except (OSError, ValueError):
        return False


def python_sin_consola():
    """En Windows, pythonw.exe (no abre ventana); en Linux, el mismo intérprete."""
    if WINDOWS:
        w = Path(sys.executable).with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return sys.executable


def lanzar(orden, **kw):
    """Proceso independiente de esta terminal (sigue vivo al cerrarla)."""
    if WINDOWS:
        kw.setdefault("creationflags", 0x00000008 | 0x00000200 | SIN_VENTANA["creationflags"])  # DETACHED | NEW_GROUP
    else:
        kw.setdefault("start_new_session", True)
    kw.setdefault("stdout", subprocess.DEVNULL)
    kw.setdefault("stderr", subprocess.DEVNULL)
    return subprocess.Popen(orden, stdin=subprocess.DEVNULL, **kw)


def con_systemd(unidad):
    """¿Hay una unidad de systemd --user de akari y systemd de usuario funcionando?"""
    return not WINDOWS and (UNIDADES / unidad).exists() and shutil.which("systemctl") is not None and \
        subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True).returncode == 0


def corriendo(*fragmentos):
    """¿Hay un proceso de este usuario cuya línea de órdenes contiene todos los fragmentos? (Linux)"""
    for cmd in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            linea = cmd.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if all(f in linea for f in fragmentos):
            return True
    return False


def arrancar_servicio():
    if vivo():
        return True
    if con_systemd("akari.service"):
        subprocess.run(["systemctl", "--user", "start", "akari.service"], capture_output=True)
    else:
        CACHE.mkdir(parents=True, exist_ok=True)
        registro = open(CACHE / "servicio.log", "ab")
        lanzar([python_sin_consola(), str(RAIZ / "bin" / "akari.py"), "servicio"], stdout=registro, stderr=registro)
    for _ in range(40):
        if vivo():
            return True
        time.sleep(0.25)
    return False


def arrancar():
    """Arranque universal: lo usan el autoarranque del escritorio, el exec-once de Hyprland,
    el exec de Sway, el spawn-at-startup de niri… No hace nada si ya está todo corriendo."""
    ok = arrancar_servicio()
    interfaz = interfaz_elegida()
    if interfaz == "capsulas":
        if con_systemd("akari-capsulas.service"):
            # lanzado desde el exec-once de Hyprland / Sway sin uwsm: systemd aún no conoce la
            # pantalla de esta sesión y Quickshell no podría conectarse
            variables = [v for v in ("WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE",
                                     "HYPRLAND_INSTANCE_SIGNATURE", "SWAYSOCK", "NIRI_SOCKET") if os.environ.get(v)]
            if variables:
                subprocess.run(["systemctl", "--user", "import-environment", *variables], capture_output=True)
            subprocess.run(["systemctl", "--user", "start", "akari-capsulas.service"], capture_output=True)
        elif quickshell() and not corriendo("-p", str(RAIZ / "capsulas")):
            lanzar([quickshell(), "-p", str(RAIZ / "capsulas")], env={**os.environ, "AKARI_RAIZ": str(RAIZ)})
    elif interfaz == "app":
        abrir_app()
    if not ok:
        print(t(f"El servicio no respondió; mira {CACHE / 'servicio.log'}", f"The service did not answer; see {CACHE / 'servicio.log'}"))
    return 0 if ok else 1


def app_instalada():
    """La app de escritorio: el AppImage en Linux; en Windows la instalada con su instalador."""
    if WINDOWS:
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
            exe = Path(base or "-") / "Programs" / "akari" / "akari.exe"
            if exe.exists():
                return exe
            exe = Path(base or "-") / "akari" / "akari.exe"
            if exe.exists():
                return exe
        return None
    app = RAIZ / "app" / "akari-panel"
    return app if app.exists() else None


def abrir_app(*args):
    app = app_instalada()
    if not app:
        return False
    extra, env = ([], dict(os.environ)) if WINDOWS else entorno_appimage()
    lanzar([str(app), *args, *extra], env=env)
    return True


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
    if abrir_app("--panel"):
        return
    electron = RAIZ / "app" / "node_modules" / ".bin" / ("electron.cmd" if WINDOWS else "electron")
    if electron.exists():
        lanzar([str(electron), str(RAIZ / "app"), "--panel"])
        return
    arrancar_servicio()
    navegadores = ["chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave", "brave-browser",
                   "microsoft-edge-stable", "vivaldi", "msedge", "chrome"]
    if WINDOWS:     # Edge viene con Windows aunque no esté en el PATH
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            navegadores.append(str(Path(base or "-") / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
    for nav in navegadores:
        ruta = shutil.which(nav) or (nav if Path(nav).is_file() else None)
        if ruta:
            lanzar([ruta, f"--app={url}", "--class=akari", "--window-size=420,760"])
            return
    webbrowser.open(url)


def resumen():
    try:
        e = pedir_estado()
    except OSError:
        print(t("El servicio no está corriendo. Arráncalo con: akari arrancar",
                "The service is not running. Start it with: akari arrancar"))
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


def recorrido():
    """Vuelve a mostrar el recorrido de bienvenida en las cápsulas / burbujas (o en el panel, en GNOME)."""
    if not arrancar_servicio():
        print(t("El servicio no respondió: akari arrancar", "The service did not answer: akari arrancar"))
        return 1
    req = urllib.request.Request(f"http://127.0.0.1:{PUERTO}/api/recorrido", data=b'{"accion": "reiniciar"}',
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        json.load(r)
    if interfaz_elegida() == "gnome":
        abrir()
    else:
        arrancar()
    print(t("Recorrido de bienvenida en marcha: mira las cápsulas de arriba.", "Welcome tour started: look at the capsules at the top."))
    return 0


def main():
    # la consola de Windows usa cp1252 / cp850: sin esto, "→", "★" o "✓" la hacen fallar
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    orden = sys.argv[1] if len(sys.argv) > 1 else "servicio"
    if orden == "servicio":
        from .servidor import main as servir
        servir()
    elif orden == "statusline":
        from .statusline import main as linea
        linea()
    elif orden == "abrir":
        abrir()
    elif orden == "arrancar":
        sys.exit(arrancar())
    elif orden == "app":
        if not abrir_app():
            sys.exit(t("No está la app de escritorio: vuelve a ejecutar el instalador.",
                       "The desktop app is missing: run the installer again."))
    elif orden in ("conectar-claude", "desconectar-claude"):
        from .instalar import conectar_claude, desconectar_claude
        print(conectar_claude(sys.argv[2] if len(sys.argv) > 2 else None) if orden == "conectar-claude" else desconectar_claude())
    elif orden == "estado":
        sys.exit(resumen())
    elif orden in ("recorrido", "tour"):
        sys.exit(recorrido())
    elif orden in ("cerebro", "brain"):
        from .cerebro import main as cerebro
        sys.exit(cerebro(sys.argv[2:]))
    elif orden in ("guia", "guía", "guide"):
        guia(sys.argv[2] if len(sys.argv) > 2 else None)
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
