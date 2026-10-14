#!/usr/bin/env bash
# akari 明かり — instalador para Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/sJonathan15/akari/main/install.sh | bash
#   ./install.sh                  desde una copia del repositorio
#
# Opciones:
#   --interfaz capsulas|gnome|panel   forzar la interfaz (si no, se elige según el escritorio)
#   --sin-statusline                  no conectar la línea de estado de Claude Code
#   --sin-dependencias                no instalar paquetes del sistema (no usa sudo)
#   --desinstalar                     quitar akari (deja ~/.config/akari)
#   --si                              responder "sí" a todo
set -euo pipefail

REPO_URL="https://github.com/sJonathan15/akari"
DESTINO="${XDG_DATA_HOME:-$HOME/.local/share}/akari"
BIN="$HOME/.local/bin"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/akari"
UNIDADES="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
FUENTES="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
EXT_GNOME="akari@sjonathan15.github.io"

INTERFAZ="" STATUSLINE=1 DEPENDENCIAS=1 DESINSTALAR=0 SI=0
while [ $# -gt 0 ]; do
  case "$1" in
    --interfaz) INTERFAZ="${2:-}"; shift ;;
    --sin-statusline) STATUSLINE=0 ;;
    --sin-dependencias) DEPENDENCIAS=0 ;;
    --desinstalar|--uninstall) DESINSTALAR=1 ;;
    --si|--yes|-y) SI=1 ;;
    *) echo "opción desconocida / unknown option: $1"; exit 2 ;;
  esac
  shift
done

# ------------------------------------------------------------------ mensajes
case "${LANGUAGE:-${LC_ALL:-${LANG:-}}}" in es*) ES=1 ;; *) ES=0 ;; esac
t() { if [ "$ES" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
paso() { printf '\033[1;38;5;215m➜\033[0m %s\n' "$(t "$1" "$2")"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$(t "$1" "$2")"; }
aviso(){ printf '  \033[33m!\033[0m %s\n' "$(t "$1" "$2")"; }
error(){ printf '\033[31m✗ %s\033[0m\n' "$(t "$1" "$2")" >&2; exit 1; }
preguntar() {   # preguntar "texto es" "text en"  → 0 = sí
  [ "$SI" = 1 ] && return 0
  [ -r /dev/tty ] || return 0
  local r; printf '  %s [S/n] ' "$(t "$1" "$2")"; read -r r < /dev/tty || r=""
  case "$r" in [nN]*) return 1 ;; *) return 0 ;; esac
}
tiene() { command -v "$1" >/dev/null 2>&1; }

if [ "$(id -u)" = 0 ]; then
  error "No ejecutes el instalador como root: instala akari para tu usuario." "Do not run the installer as root: akari installs for your user."
fi

# ------------------------------------------------------------------ desinstalar
if [ "$DESINSTALAR" = 1 ]; then
  paso "Quitando akari…" "Removing akari…"
  systemctl --user disable --now akari-capsulas.service akari.service 2>/dev/null || true
  rm -f "$UNIDADES/akari.service" "$UNIDADES/akari-capsulas.service"
  systemctl --user daemon-reload 2>/dev/null || true
  if tiene gnome-extensions; then gnome-extensions disable "$EXT_GNOME" 2>/dev/null || true; fi
  rm -rf "$HOME/.local/share/gnome-shell/extensions/$EXT_GNOME"
  # devolver la línea de estado anterior de Claude Code
  if [ -f "$HOME/.claude/settings.json" ] && tiene python3; then
    python3 - "$HOME/.claude/settings.json" "$CONFIG/statusline-previa.json" <<'PY' || true
import json, sys, os
ajustes, previa = sys.argv[1], sys.argv[2]
d = json.load(open(ajustes))
if "akari" in json.dumps(d.get("statusLine", "")):
    try:
        d["statusLine"] = {"type": "command", "command": json.load(open(previa))["command"]}
    except (OSError, ValueError, KeyError):
        d.pop("statusLine", None)
    tmp = ajustes + ".tmp"
    json.dump(d, open(tmp, "w"), indent=2)
    os.replace(tmp, ajustes)
PY
  fi
  rm -f "$BIN/akari" "$HOME/.local/share/applications/akari.desktop" "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/akari.desktop"
  rm -rf "$DESTINO"
  ok "akari quitado. Tus ajustes siguen en $CONFIG." "akari removed. Your settings remain in $CONFIG."
  exit 0
fi

# ------------------------------------------------------------------ sistema
. /etc/os-release 2>/dev/null || true
DISTRO="${ID:-linux}"; PARECIDA="${ID_LIKE:-}"
ESCRITORIO="$(printf '%s' "${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-}}" | tr '[:upper:]' '[:lower:]')"
SESION="${XDG_SESSION_TYPE:-}"; [ -n "${WAYLAND_DISPLAY:-}" ] && SESION=wayland

GESTOR=""
for g in pacman apt-get dnf zypper xbps-install; do tiene "$g" && { GESTOR="$g"; break; }; done

paso "Revisando tu equipo" "Checking your system"
ok "Distribución: ${PRETTY_NAME:-$DISTRO} · escritorio: ${ESCRITORIO:-?} · sesión: ${SESION:-?}" \
   "Distribution: ${PRETTY_NAME:-$DISTRO} · desktop: ${ESCRITORIO:-?} · session: ${SESION:-?}"
tiene python3 || error "Falta python3 (viene en casi todas las distribuciones; instálalo y vuelve a intentar)." \
                       "python3 is missing (it ships with almost every distribution; install it and retry)."
tiene systemctl || aviso "Sin systemd: tendrás que arrancar 'akari servicio' tú mismo al iniciar sesión." \
                         "No systemd: you will need to start 'akari servicio' yourself at login."

if [ -z "$INTERFAZ" ]; then
  case "$ESCRITORIO" in
    *gnome*|*ubuntu*|*unity*|*pantheon*) INTERFAZ=gnome ;;
    *) if [ "$SESION" = wayland ]; then INTERFAZ=capsulas; else INTERFAZ=panel; fi ;;
  esac
fi

instalar_paquetes() {   # instalar_paquetes paq1 paq2…  (nombres para el gestor detectado)
  [ "$DEPENDENCIAS" = 1 ] || return 1
  [ $# -gt 0 ] || return 0
  aviso "Se instalarán paquetes del sistema (pide tu clave de sudo): $*" "System packages will be installed (asks for your sudo password): $*"
  case "$GESTOR" in
    pacman) sudo pacman -S --needed --noconfirm "$@" ;;
    apt-get) sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
    dnf) sudo dnf install -y "$@" ;;
    zypper) sudo zypper --non-interactive install "$@" ;;
    xbps-install) sudo xbps-install -Sy "$@" ;;
    *) return 1 ;;
  esac
}

# Quickshell (layer-shell) para las cápsulas: KDE Plasma, Hyprland, Sway, niri, river, labwc, COSMIC…
asegurar_quickshell() {
  if tiene qs || tiene quickshell; then ok "Quickshell ya está instalado" "Quickshell is already installed"; return 0; fi
  case "$GESTOR" in
    pacman) instalar_paquetes quickshell qt6-quick3d assimp qt6-svg && return 0 ;;
    dnf)
      if [ "$DEPENDENCIAS" = 1 ]; then
        sudo dnf install -y dnf-plugins-core >/dev/null 2>&1 || true
        sudo dnf copr enable -y errornointernet/quickshell && instalar_paquetes quickshell qt6-qtquick3d assimp && return 0
      fi ;;
    zypper) instalar_paquetes quickshell qt6-quick3d && return 0 ;;
  esac
  return 1
}

# ------------------------------------------------------------------ archivos
paso "Copiando akari a $DESTINO" "Copying akari to $DESTINO"
ORIGEN=""
if [ -f "$(dirname "$0")/akari/__init__.py" ] 2>/dev/null; then
  ORIGEN="$(cd "$(dirname "$0")" && pwd)"
fi
if [ -z "$ORIGEN" ]; then
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  if tiene git; then
    git clone --depth 1 -q "$REPO_URL" "$TMP/akari"
  else
    curl -fsSL "$REPO_URL/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP" && mv "$TMP"/akari-main "$TMP/akari"
  fi
  ORIGEN="$TMP/akari"
fi
if [ "$ORIGEN" != "$DESTINO" ]; then
  mkdir -p "$DESTINO"
  for parte in akari bin capsulas web modelos iconos gnome app install.sh LICENSE README.md; do
    [ -e "$ORIGEN/$parte" ] || continue
    rm -rf "${DESTINO:?}/$parte"
    if [ "$parte" = app ]; then
      mkdir -p "$DESTINO/app" && cp "$ORIGEN/app/"*.js "$ORIGEN/app/package"*.json "$DESTINO/app/"
    else
      cp -r "$ORIGEN/$parte" "$DESTINO/$parte"
    fi
  done
fi
find "$DESTINO" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
chmod +x "$DESTINO/bin/akari"
mkdir -p "$BIN" "$CONFIG"
ln -sf "$DESTINO/bin/akari" "$BIN/akari"
ok "Comando: $BIN/akari" "Command: $BIN/akari"
case ":$PATH:" in *":$BIN:"*) ;; *) aviso "Añade $BIN a tu PATH para usar 'akari' en la terminal." "Add $BIN to your PATH to use 'akari' in the terminal." ;; esac

# fuente de iconos (Material Symbols Rounded, Apache 2.0) y Rubik (OFL), si faltan
if tiene fc-list; then
  mkdir -p "$FUENTES"
  if ! fc-list | grep -qi "Material Symbols Rounded"; then
    curl -fsSL -o "$FUENTES/MaterialSymbolsRounded.ttf" \
      "https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsRounded%5BFILL,GRAD,opsz,wght%5D.ttf" \
      && ok "Fuente de iconos instalada" "Icon font installed" || aviso "No pude bajar la fuente de iconos" "Could not download the icon font"
  fi
  if ! fc-list | grep -qi "Rubik"; then
    curl -fsSL -o "$FUENTES/Rubik.ttf" "https://github.com/google/fonts/raw/main/ofl/rubik/Rubik%5Bwght%5D.ttf" \
      && ok "Fuente Rubik instalada" "Rubik font installed" || true
  fi
  fc-cache -f "$FUENTES" >/dev/null 2>&1 || true
fi

# notificaciones y audio (opcionales)
FALTAN=()
tiene notify-send || case "$GESTOR" in pacman) FALTAN+=(libnotify) ;; apt-get) FALTAN+=(libnotify-bin) ;; dnf|zypper) FALTAN+=(libnotify) ;; esac
if [ ${#FALTAN[@]} -gt 0 ]; then instalar_paquetes "${FALTAN[@]}" || aviso "Sin notify-send no habrá avisos de escritorio." "Without notify-send there will be no desktop alerts."; fi

# ------------------------------------------------------------------ interfaz
paso "Interfaz: $INTERFAZ" "Interface: $INTERFAZ"
if [ "$INTERFAZ" = capsulas ] && ! asegurar_quickshell; then
  aviso "No pude instalar Quickshell en esta distribución: uso el panel flotante." "Could not install Quickshell on this distribution: using the floating panel."
  INTERFAZ=panel
fi

if [ "$INTERFAZ" = gnome ]; then
  EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_GNOME"
  rm -rf "$EXT_DIR" && mkdir -p "$(dirname "$EXT_DIR")"
  cp -r "$DESTINO/gnome/$EXT_GNOME" "$EXT_DIR"
  if tiene gnome-extensions; then gnome-extensions enable "$EXT_GNOME" 2>/dev/null || true; fi
  if tiene gsettings; then
    actuales="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || echo '@as []')"
    case "$actuales" in *"$EXT_GNOME"*) ;; *)
      nuevo="$(python3 -c "import ast,sys; l=ast.literal_eval(sys.argv[1].replace('@as ','')); l.append(sys.argv[2]); print(str(l))" "$actuales" "$EXT_GNOME")"
      gsettings set org.gnome.shell enabled-extensions "$nuevo" 2>/dev/null || true ;;
    esac
  fi
  ok "Extensión de GNOME instalada. Cierra sesión y vuelve a entrar para verla en la barra." \
     "GNOME extension installed. Log out and back in to see it in the top bar."
fi

if [ "$INTERFAZ" = panel ] || [ "$INTERFAZ" = gnome ]; then
  # la app (AppImage) de la última versión publicada; sin ella, `akari abrir` usa el navegador
  URL_APP="$(curl -fsSL https://api.github.com/repos/sJonathan15/akari/releases/latest 2>/dev/null \
    | python3 -c "import json,sys; a=[x['browser_download_url'] for x in json.load(sys.stdin).get('assets',[]) if x['name'].endswith('.AppImage')]; print(a[0] if a else '')" 2>/dev/null || true)"
  if [ -n "$URL_APP" ] && curl -fsSL -o "$DESTINO/app/akari-panel" "$URL_APP"; then
    chmod +x "$DESTINO/app/akari-panel"
    ok "App de escritorio (AppImage) instalada" "Desktop app (AppImage) installed"
  else
    aviso "Sin AppImage publicada todavía: el panel se abrirá en tu navegador." "No AppImage published yet: the panel will open in your browser."
  fi
fi

# ------------------------------------------------------------------ servicios
if tiene systemctl && systemctl --user show-environment >/dev/null 2>&1; then
  paso "Servicios de la sesión (systemd --user)" "Session services (systemd --user)"
  mkdir -p "$UNIDADES"
  cat > "$UNIDADES/akari.service" <<EOF
[Unit]
Description=akari: AI usage, devices and skills service
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=$DESTINO/bin/akari servicio
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
EOF
  if [ "$INTERFAZ" = capsulas ]; then
    QS="$(command -v qs || command -v quickshell)"
    cat > "$UNIDADES/akari-capsulas.service" <<EOF
[Unit]
Description=akari: desktop capsules (Quickshell)
PartOf=graphical-session.target
After=graphical-session.target akari.service
Wants=akari.service

[Service]
Environment=AKARI_RAIZ=$DESTINO
ExecStart=$QS -p $DESTINO/capsulas
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
  fi
  systemctl --user daemon-reload || true
  if systemctl --user enable --now akari.service >/dev/null 2>&1; then ok "akari.service activo" "akari.service running"
  else aviso "No pude arrancar akari.service: revisa 'journalctl --user -u akari'." "Could not start akari.service: check 'journalctl --user -u akari'."; fi
  if [ "$INTERFAZ" = capsulas ]; then
    if systemctl --user enable --now akari-capsulas.service >/dev/null 2>&1; then ok "Cápsulas activas (arriba, en el centro)" "Capsules running (top center)"
    else aviso "No pude arrancar las cápsulas: revisa 'journalctl --user -u akari-capsulas'." "Could not start the capsules: check 'journalctl --user -u akari-capsulas'."; fi
  fi
  if [ "$INTERFAZ" = panel ] && [ -x "$DESTINO/app/akari-panel" ]; then
    mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
    printf '[Desktop Entry]\nType=Application\nName=akari\nExec=%s\nIcon=%s\nX-GNOME-Autostart-enabled=true\n' \
      "$DESTINO/app/akari-panel" "$DESTINO/iconos/akari.png" > "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/akari.desktop"
    (nohup "$DESTINO/app/akari-panel" >/dev/null 2>&1 &)
    ok "Cápsula flotante activa (también arranca con tu sesión)" "Floating capsule running (also starts with your session)"
  fi
else
  aviso "Sin systemd de usuario: arranca 'akari servicio' al iniciar sesión (por ejemplo, desde el autoarranque de tu escritorio)." \
        "No systemd user session: start 'akari servicio' at login (for example, from your desktop's autostart)."
fi

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/akari.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=akari
Comment=AI usage, device batteries and AI skills
Comment[es]=Uso de la IA, batería de tus periféricos y habilidades
Exec=$DESTINO/bin/akari abrir
Icon=$DESTINO/iconos/akari.svg
Categories=Utility;Monitor;
EOF

# ------------------------------------------------------------------ Claude Code
if [ "$STATUSLINE" = 1 ] && { [ -d "$HOME/.claude" ] || tiene claude; }; then
  paso "Claude Code" "Claude Code"
  if preguntar "¿Conectar akari a la línea de estado de Claude Code? (así ve tus límites de 5 h y semanal; tu línea actual se conserva)" \
               "Connect akari to Claude Code's status line? (so it can read your 5-hour and weekly limits; your current line is kept)"; then
    python3 - "$HOME/.claude/settings.json" "$CONFIG/statusline-previa.json" "$BIN/akari statusline" <<'PY'
import json, os, shutil, sys
ajustes, previa, orden = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.dirname(ajustes), exist_ok=True)
try:
    d = json.load(open(ajustes))
except (OSError, ValueError):
    d = {}
if os.path.exists(ajustes) and not os.path.exists(ajustes + ".bak-akari"):
    shutil.copy2(ajustes, ajustes + ".bak-akari")
actual = d.get("statusLine") or {}
if actual.get("command") and "akari" not in actual["command"]:
    json.dump({"command": actual["command"]}, open(previa, "w"), indent=2)
d["statusLine"] = {"type": "command", "command": orden, "padding": 0}
tmp = ajustes + ".tmp"
json.dump(d, open(tmp, "w"), indent=2)
os.replace(tmp, ajustes)
PY
    ok "Línea de estado conectada (respaldo: ~/.claude/settings.json.bak-akari)" "Status line connected (backup: ~/.claude/settings.json.bak-akari)"
  fi
fi

echo
paso "¡Listo! akari está encendido." "Done! akari is on."
case "$INTERFAZ" in
  capsulas) echo "  $(t "Pasa el ratón por las cápsulas de arriba; arrástralas para moverlas." "Hover the capsules at the top; drag them to move them.")" ;;
  gnome) echo "  $(t "Cierra sesión y vuelve a entrar: verás akari en la barra superior." "Log out and back in: you'll see akari in the top bar.")" ;;
  panel) echo "  $(t "Abre el panel con: akari abrir" "Open the panel with: akari abrir")" ;;
esac
echo "  $(t "Resumen en la terminal: akari estado · Quitar: ./install.sh --desinstalar" "Terminal summary: akari estado · Remove: ./install.sh --desinstalar")"
