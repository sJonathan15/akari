#!/usr/bin/env bash
# Corre dentro del contenedor (lo llama probar.sh): GNOME Shell sin pantalla con la extensión.
if [ "$(id -u)" = 0 ]; then
  rm -rf /run/systemd/seats   # sin logind: GNOME usa su gestor de sesión de reserva
  mkdir -p /run/dbus && dbus-daemon --system --fork
  chmod 777 /salida
  chown prueba /home/prueba/.local /home/prueba/.local/share /home/prueba/.local/share/gnome-shell /home/prueba/.local/share/gnome-shell/extensions
  exec runuser -u prueba -- env LANG="$LANG" bash "$0"
fi
export XDG_RUNTIME_DIR=/tmp/run && mkdir -p -m 700 "$XDG_RUNTIME_DIR"
exec dbus-run-session -- bash -c '
  gsettings set org.gnome.shell enabled-extensions "['"'"'akari@sjonathan15.github.io'"'"', '"'"'akari-prueba@local'"'"']"
  gsettings set org.gnome.shell disable-user-extensions false
  gsettings set org.gnome.desktop.interface color-scheme prefer-dark
  gsettings set org.gnome.shell welcome-dialog-last-shown-version 999
  timeout 60 gnome-shell --headless --wayland --virtual-monitor 1400x900 > /salida/shell.log 2>&1 &
  for i in $(seq 55); do [ -f /salida/listo ] && break; sleep 1; done
'
