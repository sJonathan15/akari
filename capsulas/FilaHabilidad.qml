import QtQuick
import QtQuick.Layouts
import "utiles.js" as U

// Una habilidad del catálogo: icono, nombre, para qué sirve y el botón de instalar.
Tarjeta {
    id: fila
    required property var modelData
    property var duena            // la cápsula (para nombreAgente y accion)
    readonly property var tarea: modelData.tarea
    readonly property bool instalando: !!tarea && tarea.estado === "instalando"
    readonly property bool instalada: modelData.instalada_en.length > 0 && modelData.falta_en.length === 0
    implicitHeight: contenido.implicitHeight + 24

    RowLayout {
        id: contenido
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 12

        Rectangle {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            Layout.alignment: Qt.AlignTop
            radius: 19
            color: fila.instalada ? Tema.primario : Tema.contSecundario
            Icono {
                anchors.centerIn: parent
                text: fila.modelData.icono
                tam: 20
                relleno: fila.instalada ? 1 : 0
                color: fila.instalada ? Tema.sobrePrimario : Tema.sobreContSecundario
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Etiqueta { Layout.fillWidth: true; text: fila.modelData.nombre; peso: Font.Medium }
            Etiqueta {
                Layout.fillWidth: true
                text: fila.modelData.detalle
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                maximumLineCount: 3
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            Etiqueta {
                Layout.fillWidth: true
                visible: text !== ""
                text: fila.tarea && fila.tarea.estado === "error" ? fila.tarea.mensaje
                    : fila.instalada ? U.t("Instalada en ", "Installed in ") + fila.modelData.instalada_en.map(fila.duena.nombreAgente).join(U.t(" y ", " & "))
                      + (fila.modelData.usos_7d ? " · " + fila.modelData.usos_7d + U.t(" usos", " uses") : "")
                    : fila.modelData.agentes.length === 0 ? U.t("Necesita Claude Code o Codex", "Needs Claude Code or Codex")
                    : ""
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: 10
                color: fila.tarea && fila.tarea.estado === "error" ? Tema.error : Tema.contorno
            }
        }
        // botón: instalar / instalando / listo
        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: fila.instalada ? 34 : textoBoton.implicitWidth + 26
            Layout.preferredHeight: 32
            radius: 16
            visible: fila.modelData.agentes.length > 0
            color: fila.instalada ? Tema.contenedorMax : Tema.primario
            opacity: fila.instalando ? 0.7 : 1
            scale: presion.valor
            Resorte { id: presion; objetivo: zona.pressed ? 0.94 : 1; respuesta: zona.pressed ? 0.1 : 0.3 }
            Etiqueta {
                id: textoBoton
                anchors.centerIn: parent
                visible: !fila.instalada && !fila.instalando
                text: fila.modelData.instalada_en.length ? U.t("Completar", "Finish") : U.t("Instalar", "Install")
                peso: Font.Medium
                tam: Tema.textoChico + 1
                color: Tema.sobrePrimario
            }
            Icono {
                anchors.centerIn: parent
                visible: fila.instalada || fila.instalando
                text: fila.instalando ? "progress_activity" : zona.containsMouse ? "delete" : "check"
                tam: 18
                color: fila.instalando ? Tema.sobrePrimario : zona.containsMouse ? Tema.error : Tema.primario
                RotationAnimation on rotation {
                    running: fila.instalando
                    from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                    onRunningChanged: if (!running) parent.rotation = 0
                }
            }
            MouseArea {
                id: zona
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: fila.instalando ? Qt.BusyCursor : Qt.PointingHandCursor
                // instalada: el clic la quita (solo si la instaló akari; las tuyas no se tocan)
                onClicked: if (!fila.instalando) fila.duena.accion(fila.modelData.id, fila.instalada ? "desinstalar" : "instalar")
            }
        }
    }
}
