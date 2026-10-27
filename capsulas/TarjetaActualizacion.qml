import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// «Hay una versión nueva» arriba del grupo IA (CapsulaGrupo.qml), como la tarjeta del panel web.
// La decide el servicio (akari/actualizacion.py, /api/estado → actualizacion); «Actualizar» corre
// `akari actualizar` aparte y «Ahora no» la esconde hasta la próxima versión.
Tarjeta {
    id: tarjeta
    readonly property var act: Datos.estado ? Datos.estado.actualizacion : null
    readonly property bool hay: !!act && !act.pospuesta
    property string respuesta: ""

    function enviar(accion) {
        respuesta = "";
        Datos.enviar("/api/actualizacion", { accion: accion }, r => { if (!r.ok && r.mensaje) tarjeta.respuesta = r.mensaje; });
    }

    implicitHeight: columna.implicitHeight + 28

    ColumnLayout {
        id: columna
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 14
        spacing: 6

        Etiqueta {
            Layout.fillWidth: true
            text: tarjeta.hay ? U.t("Hay una versión nueva", "A new version is available") + " · akari " + tarjeta.act.version
                                + (tarjeta.act.beta ? " (beta)" : "") : ""
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            peso: Font.Medium
            color: Tema.primario
        }
        Etiqueta {
            Layout.fillWidth: true
            text: tarjeta.hay && tarjeta.act.instalando ? U.t("Actualizando… akari se reinicia solo.", "Updating… akari restarts by itself.")
                                                         : U.t("Tu configuración se conserva.", "Your settings are kept.")
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: Tema.textoChico
            color: Tema.sobreSuperficieVar
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
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Boton {
                principal: true
                icono: "system_update"
                texto: U.t("Actualizar", "Update")
                ocupado: tarjeta.hay && !!tarjeta.act.instalando
                onPulsado: tarjeta.enviar("instalar")
            }
            Boton {
                texto: U.t("Ahora no", "Not now")
                ocupado: tarjeta.hay && !!tarjeta.act.instalando
                onPulsado: tarjeta.enviar("ahora-no")
            }
            Boton {
                icono: "open_in_new"
                texto: U.t("Novedades", "What's new")
                onPulsado: Qt.openUrlExternally(tarjeta.act.url)
            }
        }
    }
}
