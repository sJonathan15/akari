# GNOME Shell sin pantalla para probar la extensión de akari:
#   docker build -t akari-gnome pruebas/gnome && pruebas/gnome/probar.sh
FROM fedora:43
RUN dnf -y install gnome-shell mutter dbus-daemon glib2 gsettings-desktop-schemas \
      adwaita-icon-theme google-noto-sans-fonts mesa-dri-drivers && dnf clean all
RUN useradd -m prueba
USER prueba
