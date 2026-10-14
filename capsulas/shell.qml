//@ pragma UseQApplication
import QtQuick
import Quickshell

// akari: tres cápsulas que cuelgan del borde superior, cerca del centro.
//   dispositivos (izquierda) · IA: Claude Code / Codex (derecha) · habilidades (más a la derecha)
// Se arrastran desde la cabecera a cualquier lugar; doble clic las devuelve a su sitio.
ShellRoot {
    CapsulaDispositivos {}
    CapsulaIA {}
    CapsulaHabilidades {}
}
