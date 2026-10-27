import QtQuick

// Pestañas en píldoras (las mismas de la cápsula de habilidades), para elegir una opción:
//   Pestanas { opciones: [{ id: "a", texto: "A" }, …]; actual: "a"; onElegida: id => … }
Row {
    id: pestanas
    property var opciones: []
    property string actual: ""
    property int alto: 30
    signal elegida(string id)
    spacing: 6

    Repeater {
        model: pestanas.opciones
        delegate: Rectangle {
            id: pestana
            required property var modelData
            readonly property bool activa: modelData.id === pestanas.actual
            width: filaPestana.implicitWidth + 24
            height: pestanas.alto
            radius: height / 2
            color: activa ? Tema.primario : Tema.contenedorAlto
            Row {
                id: filaPestana
                anchors.centerIn: parent
                spacing: 4
                Icono {
                    visible: !!pestana.modelData.icono
                    text: pestana.modelData.icono || ""
                    tam: 15
                    color: pestana.activa ? Tema.sobrePrimario : Tema.sobreSuperficieVar
                    anchors.verticalCenter: parent.verticalCenter
                }
                Etiqueta {
                    text: pestana.modelData.texto
                    peso: Font.Medium
                    tam: Tema.textoChico + 1
                    color: pestana.activa ? Tema.sobrePrimario : Tema.sobreSuperficieVar
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: pestanas.elegida(pestana.modelData.id)
            }
        }
    }
}
