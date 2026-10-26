#!/usr/bin/env bash
# akari 明かり — instalador para Linux (en Windows: install.ps1).
#
#   curl -fsSL https://raw.githubusercontent.com/sJonathan15/akari/main/install.sh | bash
#   ./install.sh                  desde una copia del repositorio
#
# Interfaces:
#   capsulas   cápsulas de Quickshell (layer-shell): KDE Plasma, Hyprland/Caelestia, Sway, niri…
#   gnome      extensión nativa en la barra superior de GNOME
#   app        burbujas flotantes (AppImage): X11, XFCE, Cinnamon, MATE, LXQt, Budgie, o donde
#              no haya Quickshell (Debian, Ubuntu, Mint…). Se ven y se usan igual que las cápsulas.
#
# Opciones:
#   --interfaz capsulas|gnome|app     forzar la interfaz (si no, se elige según el escritorio)
#   --sin-statusline                  no conectar la línea de estado de Claude Code
#   --sin-dependencias                no instalar paquetes del sistema (no usa sudo)
#   --desinstalar                     quitar akari (deja ~/.config/akari)
#   --si                              responder "sí" a todo
set -euo pipefail

REPO_URL="${AKARI_REPO:-https://github.com/sJonathan15/akari}"
DESTINO="${XDG_DATA_HOME:-$HOME/.local/share}/akari"
BIN="$HOME/.local/bin"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/akari"
UNIDADES="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
FUENTES="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
EXT_GNOME="akari@sjonathan15.github.io"

INTERFAZ="" STATUSLINE=1 DEPENDENCIAS=1 DESINSTALAR=0 SI=0
while [ $# -gt 0 ]; do
  case "$1" in
    --interfaz) INTERFAZ="${2:-}"; [ "$INTERFAZ" = panel ] && INTERFAZ=app; shift ;;
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

# Compositores que no leen ~/.config/autostart: ahí akari se agrega a su propio archivo de
# arranque (una línea con "akari arrancar", que no hace nada si ya está corriendo).
ARRANQUE_HYPR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr/hyprland.conf"
ARRANQUE_SWAY="${XDG_CONFIG_HOME:-$HOME/.config}/sway/config"
ARRANQUE_NIRI="${XDG_CONFIG_HOME:-$HOME/.config}/niri/config.kdl"
ARRANQUE_LABWC="${XDG_CONFIG_HOME:-$HOME/.config}/labwc/autostart"
ARRANQUE_RIVER="${XDG_CONFIG_HOME:-$HOME/.config}/river/init"
ARRANQUE_WAYFIRE="${XDG_CONFIG_HOME:-$HOME/.config}/wayfire.ini"
quitar_arranques() {
  local f
  for f in "$ARRANQUE_HYPR" "$ARRANQUE_SWAY" "$ARRANQUE_NIRI" "$ARRANQUE_LABWC" "$ARRANQUE_RIVER" "$ARRANQUE_WAYFIRE"; do
    [ -f "$f" ] && grep -q "akari arrancar\|\"akari\" \"arrancar\"\|bin/akari\" \"arrancar" "$f" || continue
    sed -i -e '/^# akari: /d' -e '/^\/\/ akari$/d' -e '/akari arrancar/d' -e '/bin\/akari" "arrancar"/d' "$f"
  done
}

if [ "$(id -u)" = 0 ]; then
  error "No ejecutes el instalador como root: instala akari para tu usuario." "Do not run the installer as root: akari installs for your user."
fi

# ------------------------------------------------------------------ desinstalar
if [ "$DESINSTALAR" = 1 ]; then
  paso "Quitando akari…" "Removing akari…"
  systemctl --user disable --now akari-capsulas.service akari.service 2>/dev/null || true
  rm -f "$UNIDADES/akari.service" "$UNIDADES/akari-capsulas.service"
  systemctl --user daemon-reload 2>/dev/null || true
  pkill -f "$DESTINO/capsulas" 2>/dev/null || true
  pkill -f "$DESTINO/bin/akari.py servicio" 2>/dev/null || true
  quitar_arranques
  if tiene gnome-extensions; then gnome-extensions disable "$EXT_GNOME" 2>/dev/null || true; fi
  rm -rf "$HOME/.local/share/gnome-shell/extensions/$EXT_GNOME"
  # devolver la línea de estado anterior de Claude Code
  if [ -x "$DESTINO/bin/akari" ] && tiene python3; then "$DESTINO/bin/akari" desconectar-claude >/dev/null 2>&1 || true; fi
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
for g in pacman apt-get dnf zypper xbps-install apk eopkg emerge; do tiene "$g" && { GESTOR="$g"; break; }; done
AUR=""
for g in paru yay; do tiene "$g" && { AUR="$g"; break; }; done

paso "Revisando tu equipo" "Checking your system"
ok "Distribución: ${PRETTY_NAME:-$DISTRO} · escritorio: ${ESCRITORIO:-?} · sesión: ${SESION:-?}" \
   "Distribution: ${PRETTY_NAME:-$DISTRO} · desktop: ${ESCRITORIO:-?} · session: ${SESION:-?}"
tiene python3 || error "Falta python3 (viene en casi todas las distribuciones; instálalo y vuelve a intentar)." \
                       "python3 is missing (it ships with almost every distribution; install it and retry)."
SYSTEMD=0
tiene systemctl && systemctl --user show-environment >/dev/null 2>&1 && SYSTEMD=1
[ "$SYSTEMD" = 1 ] || aviso "Sin systemd de usuario: akari arrancará desde el inicio de sesión de tu escritorio." \
                            "No systemd user session: akari will start from your desktop's login autostart."

if [ -z "$INTERFAZ" ]; then
  case "$ESCRITORIO" in
    # solo GNOME Shell carga extensiones (Pantheon, Budgie, Cinnamon o Unity no)
    *gnome*|*ubuntu*) if tiene gnome-shell; then INTERFAZ=gnome; else INTERFAZ=app; fi ;;
    *) if [ "$SESION" = wayland ]; then INTERFAZ=capsulas; else INTERFAZ=app; fi ;;
  esac
fi
case "$INTERFAZ" in capsulas|gnome|app) ;; *) error "Interfaz desconocida: $INTERFAZ (capsulas, gnome o app)" "Unknown interface: $INTERFAZ (capsulas, gnome or app)" ;; esac

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
    apk) sudo apk add "$@" ;;
    eopkg) sudo eopkg install -y "$@" ;;
    *) return 1 ;;      # Gentoo (emerge) y otros: el usuario elige sus USE flags; solo se avisa
  esac
}

# Quickshell (layer-shell) para las cápsulas: KDE Plasma, Hyprland, Sway, niri, river, labwc, COSMIC…
asegurar_quickshell() {
  if tiene qs || tiene quickshell; then ok "Quickshell ya está instalado" "Quickshell is already installed"; return 0; fi
  [ "$DEPENDENCIAS" = 1 ] || return 1
  case "$GESTOR" in
    # Arch, CachyOS, EndeavourOS, Manjaro, Garuda…: repositorios oficiales y, si no está, el AUR
    pacman)
      instalar_paquetes quickshell qt6-quick3d assimp qt6-svg && return 0
      if [ -n "$AUR" ]; then "$AUR" -S --needed --noconfirm quickshell qt6-quick3d assimp qt6-svg && return 0; fi ;;
    dnf)
      sudo dnf install -y dnf-plugins-core >/dev/null 2>&1 || true
      sudo dnf copr enable -y errornointernet/quickshell && instalar_paquetes quickshell qt6-qtquick3d assimp && return 0 ;;
    zypper) instalar_paquetes quickshell qt6-quick3d && return 0 ;;
    xbps-install) instalar_paquetes quickshell qt6-quick3d && return 0 ;;
    apk) instalar_paquetes quickshell qt6-qtquick3d && return 0 ;;
    emerge) aviso "Gentoo: instala gui-apps/quickshell (overlay GURU) y vuelve a ejecutar el instalador." \
                  "Gentoo: install gui-apps/quickshell (GURU overlay) and run the installer again." ;;
  esac
  # NixOS o Nix en cualquier distribución: sin root, en el perfil del usuario
  if tiene nix && preguntar "¿Instalar Quickshell con Nix (en tu perfil, sin sudo)?" "Install Quickshell with Nix (in your profile, no sudo)?"; then
    nix --extra-experimental-features "nix-command flakes" profile install nixpkgs#quickshell && return 0
  fi
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
if [ "$INTERFAZ" = capsulas ] && ! asegurar_quickshell; then
  aviso "Quickshell no está disponible en esta distribución: uso las burbujas de la app (se ven y se usan igual)." \
        "Quickshell is not available on this distribution: using the app's bubbles (same look and behavior)."
  INTERFAZ=app
fi
paso "Interfaz: $INTERFAZ" "Interface: $INTERFAZ"

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

if [ "$INTERFAZ" = app ] || [ "$INTERFAZ" = gnome ]; then
  # la app (AppImage) de la última versión publicada; sin ella, `akari abrir` usa el navegador
  # enlace fijo a la última versión (no usa la API de GitHub, que limita las consultas anónimas)
  case "$(uname -m)" in x86_64|amd64) ARQ=x86_64 ;; aarch64|arm64) ARQ=arm64 ;; *) ARQ="" ;; esac
  URL_APP="$REPO_URL/releases/latest/download/akari-$ARQ.AppImage"
  if [ -n "$ARQ" ] && curl -fsSL -o "$DESTINO/app/akari-panel.tmp" "$URL_APP" \
     && mv "$DESTINO/app/akari-panel.tmp" "$DESTINO/app/akari-panel"; then
    chmod +x "$DESTINO/app/akari-panel"
    ok "App de escritorio (AppImage) instalada" "Desktop app (AppImage) installed"
    # los AppImage necesitan libfuse2; Ubuntu 22.04+ ya no lo trae (sin él, akari lo extrae al abrir: más lento)
    if ! ldconfig -p 2>/dev/null | grep -q "libfuse.so.2"; then
      case "$GESTOR" in
        apt-get) instalar_paquetes libfuse2t64 2>/dev/null || instalar_paquetes libfuse2 || true ;;
        dnf) instalar_paquetes fuse-libs || true ;;
        pacman) instalar_paquetes fuse2 || true ;;
        zypper) instalar_paquetes libfuse2 || true ;;
        xbps-install) instalar_paquetes fuse || true ;;
        apk) instalar_paquetes fuse || true ;;
      esac
    fi
  else
    rm -f "$DESTINO/app/akari-panel.tmp"
    aviso "No pude bajar la app (AppImage): el panel se abrirá en tu navegador." "Could not download the app (AppImage): the panel will open in your browser."
    # sin la app, en Wayland con Quickshell quedan las cápsulas; si no, el panel en el navegador
    if [ "$INTERFAZ" = app ] && [ "$SESION" = wayland ] && asegurar_quickshell; then
      INTERFAZ=capsulas
      aviso "Uso las cápsulas de Quickshell en su lugar." "Using the Quickshell capsules instead."
    fi
  fi
fi

# se recuerda para `akari arrancar` y `akari guia`
python3 - "$CONFIG/ajustes.json" "$INTERFAZ" <<'PY'
import json, os, sys
ruta, interfaz = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(ruta))
except (OSError, ValueError):
    d = {}
d["interfaz"] = interfaz
os.makedirs(os.path.dirname(ruta), exist_ok=True)
json.dump(d, open(ruta + ".tmp", "w"), indent=2, ensure_ascii=False)
os.replace(ruta + ".tmp", ruta)
PY

# ------------------------------------------------------------------ servicios
if [ "$SYSTEMD" = 1 ]; then
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
fi

# Arranque con la sesión, con o sin systemd: `akari arrancar` levanta lo que falte (servicio,
# cápsulas o burbujas) y no hace nada si ya está corriendo. Lo leen KDE, XFCE, Cinnamon, MATE,
# LXQt, Budgie, COSMIC, GNOME… (~/.config/autostart); los compositores sueltos, su archivo propio.
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
printf '[Desktop Entry]\nType=Application\nName=akari\nComment=akari: AI usage, devices and skills\nExec=%s arrancar\nIcon=%s\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n' \
  "$DESTINO/bin/akari" "$DESTINO/iconos/akari.png" > "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/akari.desktop"
# Con systemd y graphical-session.target activo (KDE, GNOME, Hyprland con uwsm…) ya arrancan los
# servicios; si no (Hyprland/Sway/niri lanzados a mano, sin systemd), se agrega al compositor.
SESION_SYSTEMD=0
[ "$SYSTEMD" = 1 ] && systemctl --user is-active graphical-session.target >/dev/null 2>&1 && SESION_SYSTEMD=1
quitar_arranques
if [ "$INTERFAZ" != gnome ] && [ "$SESION_SYSTEMD" = 0 ]; then
  agregados=""
  if [ -L "$ARRANQUE_HYPR" ]; then      # dotfiles enlazados (Caelestia, end-4…): no se tocan
    aviso "Tu hyprland.conf es un enlace a tus dotfiles: agrega tú esta línea →  exec-once = $BIN/akari arrancar" \
          "Your hyprland.conf links to your dotfiles: add this line yourself →  exec-once = $BIN/akari arrancar"
  elif [ -f "$ARRANQUE_HYPR" ]; then
    printf '\n# akari: cápsulas / burbujas\nexec-once = %s arrancar\n' "$BIN/akari" >> "$ARRANQUE_HYPR"; agregados="$agregados Hyprland"
  fi
  if [ -f "$ARRANQUE_SWAY" ]; then printf '\n# akari: cápsulas / burbujas\nexec %s arrancar\n' "$BIN/akari" >> "$ARRANQUE_SWAY"; agregados="$agregados Sway"; fi
  if [ -f "$ARRANQUE_NIRI" ]; then printf '\n// akari\nspawn-at-startup "%s" "arrancar"\n' "$BIN/akari" >> "$ARRANQUE_NIRI"; agregados="$agregados niri"; fi
  if [ -f "$ARRANQUE_LABWC" ] || [ -d "$(dirname "$ARRANQUE_LABWC")" ]; then printf '# akari: cápsulas / burbujas\n%s arrancar &\n' "$BIN/akari" >> "$ARRANQUE_LABWC"; agregados="$agregados labwc"; fi
  if [ -f "$ARRANQUE_RIVER" ]; then printf '\n# akari: cápsulas / burbujas\n%s arrancar &\n' "$BIN/akari" >> "$ARRANQUE_RIVER"; agregados="$agregados river"; fi
  if [ -f "$ARRANQUE_WAYFIRE" ]; then
    if grep -q '^\[autostart\]' "$ARRANQUE_WAYFIRE"; then sed -i "/^\[autostart\]/a akari = $BIN/akari arrancar" "$ARRANQUE_WAYFIRE"
    else printf '\n[autostart]\nakari = %s arrancar\n' "$BIN/akari" >> "$ARRANQUE_WAYFIRE"; fi
    agregados="$agregados Wayfire"
  fi
  # niri valida su archivo al leerlo: si la línea nueva lo rompe, se quita
  if [ -f "$ARRANQUE_NIRI" ] && tiene niri && ! niri validate -c "$ARRANQUE_NIRI" >/dev/null 2>&1; then
    sed -i -e '/^\/\/ akari$/d' -e '/bin\/akari" "arrancar"/d' "$ARRANQUE_NIRI"
  fi
  if [ -n "$agregados" ]; then ok "Arranque agregado a:$agregados" "Autostart added to:$agregados"; fi
fi
ok "akari arranca con tu sesión (con o sin systemd)" "akari starts with your session (with or without systemd)"
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ "$INTERFAZ" != gnome ]; then "$DESTINO/bin/akari" arrancar >/dev/null 2>&1 || true; fi

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/akari.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=akari
Comment=AI usage, device batteries and AI skills
Comment[es]=Uso de la IA, batería de tus periféricos y habilidades
Exec=$DESTINO/bin/akari abrir
Icon=$DESTINO/iconos/akari.png
Categories=Utility;Monitor;
EOF

# ------------------------------------------------------------------ Claude Code
if [ "$STATUSLINE" = 1 ] && { [ -d "$HOME/.claude" ] || tiene claude; }; then
  paso "Claude Code" "Claude Code"
  if preguntar "¿Conectar akari a la línea de estado de Claude Code? (así ve tus límites de 5 h y semanal; tu línea actual se conserva)" \
               "Connect akari to Claude Code's status line? (so it can read your 5-hour and weekly limits; your current line is kept)"; then
    "$DESTINO/bin/akari" conectar-claude "$BIN/akari statusline" >/dev/null
    ok "Línea de estado conectada (respaldo: ~/.claude/settings.json.bak-akari)" "Status line connected (backup: ~/.claude/settings.json.bak-akari)"
  fi
fi

echo
paso "¡Listo! akari está instalado. Así se usa:" "Done! akari is installed. Here's how to use it:"
echo
"$DESTINO/bin/akari" guia "$INTERFAZ" | sed 's/^/  /'
echo
if [ "$INTERFAZ" = gnome ]; then
  printf '\033[1;38;5;215m  ⚠  %s\033[0m\n' "$(t "IMPORTANTE: cierra sesión y vuelve a entrar para ver akari en la barra superior." "IMPORTANT: log out and back in to see akari in the top bar.")"
  if tiene notify-send; then
    notify-send -a akari -i "$DESTINO/iconos/akari.png" "$(t "akari está instalado" "akari is installed")" \
      "$(t "Cierra sesión y vuelve a entrar para verlo en la barra superior." "Log out and back in to see it in the top bar.")" 2>/dev/null || true
  fi
fi
