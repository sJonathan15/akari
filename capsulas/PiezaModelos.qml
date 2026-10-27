import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Modelos de IA» del grupo IA: con qué piensan el asistente, el resumen de audios y las demás
// funciones con IA (una clave de API o un modelo local recomendado para este equipo).
Pieza {
    id: capsula
    clave: "modelos"
    titulo: U.t("Modelos de IA", "AI models")
    icono: "psychology"
    anchoChip: 44
    anchoAbierto: 384

    readonly property var m: Datos.modelos
    readonly property bool bajando: !!m && !!m.ollama.descarga && !m.ollama.descarga.error && m.ollama.descarga.pct < 100

    // cerebro lleno si hay modelo listo; una llave (en el color de aviso) si falta
    resumen: Component {
        Item {
            Icono {
                id: iconoModelos
                anchors.centerIn: parent
                text: capsula.bajando ? "progress_activity" : capsula.m && capsula.m.listo ? "psychology" : "key"
                tam: 19
                relleno: capsula.m && capsula.m.listo ? 1 : 0
                color: capsula.m && capsula.m.listo ? Tema.primario : Tema.terciario
                RotationAnimation on rotation {
                    running: capsula.bajando
                    from: 0; to: 360; duration: 1200; loops: Animation.Infinite
                    onRunningChanged: if (!running) iconoModelos.rotation = 0
                }
            }
        }
    }

    cuerpo: Component {
        ColumnLayout {
            spacing: 8
            Etiqueta {
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: U.t("Con esto piensan el asistente, los resúmenes de audio y las demás funciones con IA.",
                          "The assistant, audio summaries and the other AI features think with this.")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            TarjetaModelos {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: implicitHeight
            }
            // el chico busca y el otro conversa (ver akari/cerebro.py)
            Tarjeta {
                readonly property var pa: capsula.m ? capsula.m.para_archivos : null
                readonly property var embed: capsula.m && capsula.m.embeddings ? capsula.m.embeddings.find(e => e.sugerido) : null
                visible: !!pa && !!embed
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: filaBuscar.implicitHeight + 22
                RowLayout {
                    id: filaBuscar
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 14
                    anchors.rightMargin: 10
                    spacing: 8
                    Icono { text: "travel_explore"; tam: 20; color: Tema.primario }
                    Etiqueta {
                        Layout.fillWidth: true
                        text: !parent.parent.pa ? "" : U.t("Para buscar y abrir archivos: ", "To find and open files: ")
                            + parent.parent.pa.buscar + U.t(" (buscar)", " (search)")
                            + (parent.parent.pa.conversar ? " + " + parent.parent.pa.conversar + U.t(" (conversar)", " (chat)") : "")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                    }
                    Boton {
                        visible: !!parent.parent.embed && !parent.parent.embed.instalado && capsula.m.ollama.estado === "activo"
                        texto: U.t("Descargar", "Download")
                        onPulsado: Datos.enviar("/api/modelos", { accion: "descargar", modelo: parent.parent.embed.id, usar: false })
                    }
                    Icono { visible: !!parent.parent.embed && parent.parent.embed.instalado; text: "check"; tam: 20; color: Tema.primario }
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
