import QtQuick

// Botón redondo con solo un icono (abrir carpeta, vaciar lista…).
Rectangle {
    id: boton
    property string icono: ""
    property color colorIcono: Tema.sobreSuperficieVar
    property int tam: 32
    signal pulsado()

    implicitWidth: tam
    implicitHeight: tam
    radius: tam / 2
    color: zona.pressed ? Tema.contenedorMax : zona.containsMouse ? Tema.contenedorAlto : "transparent"
    Icono {
        anchors.centerIn: parent
        text: boton.icono
        tam: Math.round(boton.tam * 0.56)
        color: boton.colorIcono
    }
    MouseArea {
        id: zona
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: boton.pulsado()
    }
}
