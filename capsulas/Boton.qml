import QtQuick

// Botón tonal en forma de píldora (estilo Caelestia / Material 3).
Rectangle {
    id: boton
    property string texto: ""
    property string icono: ""
    property bool principal: false
    property bool ocupado: false
    signal pulsado()

    implicitHeight: 36
    implicitWidth: fila.implicitWidth + 32
    radius: height / 2
    color: principal ? Tema.primario : Tema.contSecundario
    opacity: ocupado ? 0.6 : 1

    // Respuesta al presionar, no al soltar: se hunde al instante y vuelve con un resorte.
    scale: presion.valor
    Resorte { id: presion; objetivo: zona.pressed ? 0.96 : 1; respuesta: zona.pressed ? 0.1 : 0.3 }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: principal ? Tema.sobrePrimario : Tema.sobreSuperficie
        opacity: zona.pressed ? 0.16 : zona.containsMouse ? 0.08 : 0
        Behavior on opacity { enabled: !zona.pressed; NumberAnimation { duration: 150 } }
    }
    Row {
        id: fila
        anchors.centerIn: parent
        spacing: 6
        Icono {
            visible: boton.icono !== ""
            text: boton.icono
            tam: 18
            color: boton.principal ? Tema.sobrePrimario : Tema.sobreContSecundario
            anchors.verticalCenter: parent.verticalCenter
        }
        Etiqueta {
            text: boton.texto
            peso: Font.Medium
            color: boton.principal ? Tema.sobrePrimario : Tema.sobreContSecundario
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: zona
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: if (!boton.ocupado) boton.pulsado()
    }
}
