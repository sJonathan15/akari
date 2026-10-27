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
            Item { Layout.preferredHeight: 6 }
        }
    }
}
