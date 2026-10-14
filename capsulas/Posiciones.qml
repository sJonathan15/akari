pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Dónde dejó el usuario cada cápsula (arrastrándola). Se guarda en
// ~/.config/akari/posiciones.json y sobrevive a reinicios.
Singleton {
    id: posiciones

    function de(nombre) {
        return adaptador.capsulas[nombre] || null;
    }

    // x/y en píxeles de la pantalla (esquina de la cápsula cerrada); borde: "" (horizontal),
    // "izquierda" o "derecha" (pestaña vertical pegada a ese borde); x null = posición de fábrica
    function guardar(nombre, x, y, borde) {
        const c = Object.assign({}, adaptador.capsulas);
        if (x === null) delete c[nombre];
        else c[nombre] = { x: Math.round(x), y: Math.round(y), borde: borde || "" };
        adaptador.capsulas = c;
        archivo.writeAdapter();
    }

    FileView {
        id: archivo
        path: Quickshell.env("HOME") + "/.config/akari/posiciones.json"
        onLoadFailed: error => { if (error === FileViewError.FileNotFound) writeAdapter(); }

        JsonAdapter {
            id: adaptador
            property var capsulas: ({})
        }
    }
}
