import QtQuick

// Texto con espaciado según el tamaño: los números grandes se cierran un poco
// y el texto pequeño se abre, como en la tipografía de Apple.
Text {
    property int tam: Tema.texto
    property int peso: Font.Normal
    font.family: Tema.fuente
    font.pixelSize: tam
    font.weight: peso
    font.letterSpacing: tam >= 24 ? -0.03 * tam : tam >= 16 ? -0.01 * tam : tam <= 11 ? 0.2 : 0
    color: Tema.sobreSuperficie
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
}
