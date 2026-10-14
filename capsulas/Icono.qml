import QtQuick

// Icono de Material Symbols Rounded (el mismo juego de iconos de Caelestia).
Text {
    property real relleno: 0
    property int tam: 20
    font.family: Tema.iconos
    font.pixelSize: tam
    font.variableAxes: ({ "FILL": relleno, "opsz": tam })
    color: Tema.sobreSuperficie
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
}
