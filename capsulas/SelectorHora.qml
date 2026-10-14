import QtQuick
import "utiles.js" as U

// hora con flechas; la rueda también la mueve de 30 en 30 min
Row {
    id: sel
    property string hora: "06:00"
    signal cambiada(string hora)
    spacing: 0
    Repeater {
        model: [-30, 0, 30]
        delegate: Item {
            required property int modelData
            width: modelData ? 18 : etiquetaHora.implicitWidth + 4
            height: 22
            Icono {
                visible: parent.modelData !== 0
                anchors.centerIn: parent
                text: parent.modelData < 0 ? "chevron_left" : "chevron_right"
                tam: 16
                color: flecha.containsMouse ? Tema.primario : Tema.sobreSuperficieVar
            }
            Etiqueta {
                id: etiquetaHora
                visible: parent.modelData === 0
                anchors.centerIn: parent
                text: sel.hora
                font.family: Tema.mono
                peso: Font.Medium
                color: Tema.primario
            }
            MouseArea {
                id: flecha
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: parent.modelData ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: if (parent.modelData) sel.cambiada(U.moverHora(sel.hora, parent.modelData))
                onWheel: w => sel.cambiada(U.moverHora(sel.hora, w.angleDelta.y > 0 ? 30 : -30))
            }
        }
    }
}
