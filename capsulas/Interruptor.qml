import QtQuick

// interruptor pequeño estilo Material 3
Rectangle {
    id: inter
    property bool activo: false
    signal cambiado(bool valor)
    implicitWidth: 38
    implicitHeight: 22
    radius: 11
    color: activo ? Tema.primario : Tema.contenedorMax
    border.width: activo ? 0 : 1.5
    border.color: Tema.contorno
    Behavior on color { ColorAnimation { duration: 150 } }
    Rectangle {
        width: inter.activo ? 16 : 12
        height: width
        radius: width / 2
        anchors.verticalCenter: parent.verticalCenter
        x: inter.activo ? parent.width - width - 3 : 5
        color: inter.activo ? Tema.sobrePrimario : Tema.contorno
        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: inter.cambiado(!inter.activo)
    }
}
