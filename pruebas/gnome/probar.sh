#!/usr/bin/env bash
# Prueba la extensión de GNOME en un GNOME Shell sin pantalla (Docker). Necesita el servicio
# de akari corriendo en este equipo (comparte la red). Capturas en pruebas/gnome/salida/.
#   docker build -t akari-gnome pruebas/gnome && pruebas/gnome/probar.sh
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$AQUI/../.." && pwd)"
EXT=/home/prueba/.local/share/gnome-shell/extensions
mkdir -p "$AQUI/salida" && rm -f "$AQUI/salida/"*
docker run --rm --network host -u 0 -e LANG="${LANG:-es_EC.UTF-8}" \
  -v "$REPO/gnome/akari@sjonathan15.github.io:$EXT/akari@sjonathan15.github.io:ro" \
  -v "$AQUI/akari-prueba@local:$EXT/akari-prueba@local:ro" \
  -v "$AQUI/dentro.sh:/dentro.sh:ro" -v "$AQUI/salida:/salida" \
  akari-gnome bash /dentro.sh
ls "$AQUI/salida"
