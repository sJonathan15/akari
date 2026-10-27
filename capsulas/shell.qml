//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io

// akari: tres grupos de cápsulas que cuelgan del borde superior, cerca del centro (ver AGENTS.md):
//   Equipo (izquierda) · IA (derecha) · Archivos (a la derecha de IA)
// Cada grupo es una píldora con un chip por pieza; se abre en la pieza que está bajo el puntero.
// Se arrastran desde la cabecera a cualquier lugar; doble clic los devuelve a su sitio.
// Para no mostrar piezas o grupos enteros (p. ej. si ya tienes otro widget igual), ponlos en
// ~/.config/akari/capsulas.json: { "ocultas": ["dispositivos", "audio", "archivos"] }
// La misma lista de grupos está en akari/grupos.py (la usa la app de escritorio).
ShellRoot {
    id: raiz
    property var ocultas: []

    FileView {
        path: Quickshell.env("HOME") + "/.config/akari/capsulas.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try { raiz.ocultas = JSON.parse(text()).ocultas || []; } catch (e) { raiz.ocultas = []; }
        }
        onLoadFailed: raiz.ocultas = []
    }
    function visible(grupo, piezas) {
        return !ocultas.includes(grupo) && piezas.some(p => !ocultas.includes(p));
    }

    LazyLoader {
        active: raiz.visible("equipo", ["dispositivos"])
        CapsulaGrupo {
            nombre: "equipo"
            lado: "izquierda"
            altoMaximo: 700
            ocultas: raiz.ocultas
            PiezaDispositivos {}
        }
    }
    LazyLoader {
        active: raiz.visible("ia", ["asistente", "uso", "modelos", "habilidades", "herramientas"])
        CapsulaGrupo {
            nombre: "ia"
            lado: "derecha"
            altoMaximo: 780
            ocultas: raiz.ocultas
            PiezaAsistente {}
            PiezaUso {}
            PiezaModelos {}
            PiezaHabilidades {}
            PiezaHerramientas {}
        }
    }
    LazyLoader {
        active: raiz.visible("archivos", ["documentos", "audio"])
        CapsulaGrupo {
            nombre: "archivos"
            lado: "derecha"
            hueco: 404              // a la derecha del grupo IA abierto (8 + 384 + margen)
            altoMaximo: 760
            ocultas: raiz.ocultas
            PiezaDocumentos {}
            PiezaAudio {}
        }
    }
}
