import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Tarjeta del recorrido de bienvenida arriba del cuerpo de un grupo (CapsulaGrupo.qml): «2 de 9»,
// título, 1–2 frases, las acciones del paso y Anterior / Siguiente / Saltar. El estado vive en el
// servicio (akari/recorrido.py, /api/recorrido).
Tarjeta {
    id: tarjeta
    property var dueno: null           // el CapsulaGrupo donde va
    readonly property var rec: Datos.estado ? Datos.estado.recorrido : null
    readonly property var paso: rec && rec.activo ? rec.paso : null
    property string respuesta: ""

    function mover(accion, extra) {
        respuesta = "";
        Datos.enviar("/api/recorrido", Object.assign({ accion: accion }, extra || {}));
    }
    function hacer(a) {
        if (a.pieza) {
            if (tarjeta.dueno && tarjeta.dueno.piezas.some(p => p.clave === a.pieza)) tarjeta.dueno.elegir(a.pieza);
            else U.abrirPanel(Quickshell);
            return;
        }
        Datos.enviar(a.ruta, a.cuerpo, r => tarjeta.respuesta = r.mensaje || (r.ok ? U.t("Listo, sigue en marcha.", "Done, it's on its way.")
                                                                                     : U.t("No se pudo.", "It didn't work.")));
    }

    implicitHeight: columna.implicitHeight + 28
    border.width: 1.5
    border.color: Tema.primario

    ColumnLayout {
        id: columna
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 14
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                implicitWidth: numero.implicitWidth + 16
                implicitHeight: 20
                radius: 10
                color: Tema.primario
                Etiqueta {
                    id: numero
                    anchors.centerIn: parent
                    text: tarjeta.rec && tarjeta.paso ? U.t(tarjeta.rec.n + " de " + tarjeta.rec.total, tarjeta.rec.n + " of " + tarjeta.rec.total) : ""
                    tam: Tema.textoChico
                    peso: Font.Medium
                    color: Tema.sobrePrimario
                }
            }
            Item { Layout.fillWidth: true }
            Etiqueta {
                visible: !!tarjeta.rec && tarjeta.rec.voz_disponible
                text: U.t("Leérmelo en voz alta", "Read it aloud")
                tam: 10
                color: Tema.sobreSuperficieVar
            }
            Interruptor {
                visible: !!tarjeta.rec && tarjeta.rec.voz_disponible
                activo: !!tarjeta.rec && tarjeta.rec.voz
                onCambiado: valor => tarjeta.mover("voz", { activo: valor })
            }
            Etiqueta {
                text: U.t("Saltar", "Skip")
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: tarjeta.mover("saltar") }
            }
        }
        Etiqueta {
            Layout.fillWidth: true
            text: tarjeta.paso ? tarjeta.paso.titulo : ""
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: 15
            peso: Font.Medium
        }
        Etiqueta {
            Layout.fillWidth: true
            text: tarjeta.paso ? tarjeta.paso.texto : ""
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: Tema.textoChico + 1
            color: Tema.sobreSuperficieVar
        }
        Flow {
            Layout.fillWidth: true
            visible: !!tarjeta.paso && tarjeta.paso.acciones.length > 0
            spacing: 6
            Repeater {
                model: tarjeta.paso ? tarjeta.paso.acciones : []
                delegate: Boton {
                    required property var modelData
                    principal: !!modelData.principal
                    texto: modelData.texto
                    onPulsado: tarjeta.hacer(modelData)
                }
            }
        }
        Etiqueta {
            visible: tarjeta.respuesta !== ""
            Layout.fillWidth: true
            text: tarjeta.respuesta
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: Tema.textoChico
            color: Tema.terciario
        }
        RowLayout {
            Layout.fillWidth: true
            Boton {
                icono: "arrow_back"
                texto: U.t("Anterior", "Back")
                ocupado: !!tarjeta.rec && tarjeta.rec.n === 1
                onPulsado: tarjeta.mover("anterior")
            }
            Item { Layout.fillWidth: true }
            Boton {
                principal: true
                icono: "arrow_forward"
                texto: tarjeta.rec && tarjeta.rec.n === tarjeta.rec.total ? U.t("Terminar", "Finish") : U.t("Siguiente", "Next")
                onPulsado: tarjeta.mover("siguiente")
            }
        }
    }
}
