//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io

// akari: tres cápsulas que cuelgan del borde superior, cerca del centro.
//   dispositivos (izquierda) · IA: Claude Code / Codex (derecha) · habilidades (más a la derecha)
// Se arrastran desde la cabecera a cualquier lugar; doble clic las devuelve a su sitio.
// Para no mostrar alguna (p. ej. si ya tienes otro widget igual), ponla en
// ~/.config/akari/capsulas.json: { "ocultas": ["dispositivos", "ia"] }
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

    LazyLoader { active: !raiz.ocultas.includes("dispositivos"); CapsulaDispositivos {} }
    LazyLoader { active: !raiz.ocultas.includes("ia"); CapsulaIA {} }
    LazyLoader { active: !raiz.ocultas.includes("habilidades"); CapsulaHabilidades {} }
}
