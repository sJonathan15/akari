import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Herramientas» del grupo IA: programas de terminal que Claude Code y Codex aprovechan
// (gitleaks, semgrep, trivy, ast-grep, repomix, ccusage, rtk y el MCP context7). Ver
// akari/herramientas.py: se instalan sin contraseña si se puede; si no, se copia el comando o se
// abre en una terminal.
Pieza {
    id: capsula
    clave: "herramientas"
    titulo: U.t("Herramientas", "Tools")
    icono: "construction"
    anchoChip: 64
    anchoAbierto: 384

    readonly property var estado: Datos.herramientas
    readonly property bool instalando: !!estado && estado.lista.some(x => x.tarea && x.tarea.estado === "instalando")
    property string respuesta: ""

    function accion(id, cual) {
        respuesta = "";
        Datos.enviar("/api/herramientas", { id: id, accion: cual }, r => capsula.respuesta = r.mensaje || (r.ok ? "" : U.t("No se pudo.", "It didn't work.")));
    }

    resumen: Component {
        Row {
            spacing: 4
            Item { width: 6; height: 1 }
            Icono {
                id: iconoChip
                anchors.verticalCenter: parent.verticalCenter
                text: "construction"
                tam: 18
                relleno: 1
                color: Tema.primario
                SequentialAnimation on opacity {
                    running: capsula.instalando
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.35; duration: 700 }
                    NumberAnimation { to: 1; duration: 700 }
                    onRunningChanged: if (!running) iconoChip.opacity = 1
                }
            }
            Etiqueta {
                anchors.verticalCenter: parent.verticalCenter
                text: capsula.estado ? capsula.estado.instaladas + "/" + capsula.estado.total : "—"
                tam: Tema.textoChico + 1
                peso: Font.Medium
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
                text: U.t("Programas de terminal que Claude Code y Codex aprovechan: seguridad, contexto y gasto.",
                          "Terminal programs Claude Code and Codex make good use of: security, context and spending.")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            Etiqueta {
                visible: capsula.respuesta !== ""
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: capsula.respuesta
                wrapMode: Text.WrapAnywhere
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.terciario
            }
            Repeater {
                model: capsula.estado ? capsula.estado.lista : []
                delegate: Tarjeta {
                    id: fila
                    required property var modelData
                    readonly property var tarea: modelData.tarea || ({})
                    readonly property var metodo: modelData.metodo
                    readonly property bool ocupada: tarea.estado === "instalando"
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    Layout.preferredHeight: contenido.implicitHeight + 20
                    RowLayout {
                        id: contenido
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 12
                        anchors.rightMargin: 10
                        spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 34
                            Layout.preferredHeight: 34
                            Layout.alignment: Qt.AlignTop
                            radius: 17
                            color: fila.modelData.instalada ? Tema.primario : Tema.contSecundario
                            Icono {
                                anchors.centerIn: parent
                                text: fila.modelData.icono
                                tam: 18
                                relleno: fila.modelData.instalada ? 1 : 0
                                color: fila.modelData.instalada ? Tema.sobrePrimario : Tema.sobreContSecundario
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
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
                                text: fila.tarea.estado === "error" ? fila.tarea.mensaje
                                    : !fila.modelData.instalada && fila.metodo ? (fila.metodo.sudo ? "sudo · " : "") + fila.metodo.texto
                                    : fila.modelData.nota
                                wrapMode: Text.WrapAnywhere
                                elide: Text.ElideNone
                                tam: 10
                                font.family: fila.metodo && !fila.modelData.instalada ? Tema.mono : Tema.fuente
                                color: fila.tarea.estado === "error" ? Tema.error : Tema.contorno
                            }
                        }
                        // instalada · instalando · instalar · copiar/terminal (pide contraseña) · ver cómo
                        Icono {
                            visible: fila.modelData.instalada
                            text: "check"
                            tam: 20
                            color: Tema.primario
                        }
                        Icono {
                            id: girando
                            visible: fila.ocupada
                            text: "progress_activity"
                            tam: 20
                            color: Tema.primario
                            RotationAnimation on rotation {
                                running: fila.ocupada
                                from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                                onRunningChanged: if (!running) girando.rotation = 0
                            }
                        }
                        Boton {
                            visible: !fila.modelData.instalada && !fila.ocupada && !!fila.metodo && !fila.metodo.sudo
                            principal: true
                            texto: U.t("Instalar", "Install")
                            onPulsado: capsula.accion(fila.modelData.id, "instalar")
                        }
                        BotonIcono {
                            visible: !fila.modelData.instalada && !!fila.metodo && fila.metodo.sudo
                            icono: "content_copy"
                            onPulsado: capsula.accion(fila.modelData.id, "copiar")
                        }
                        BotonIcono {
                            visible: !fila.modelData.instalada && !!fila.metodo && fila.metodo.sudo
                            icono: "terminal"
                            onPulsado: capsula.accion(fila.modelData.id, "terminal")
                        }
                        BotonIcono {
                            visible: !fila.modelData.instalada && !fila.metodo
                            icono: "open_in_new"
                            onPulsado: Qt.openUrlExternally(fila.modelData.web)
                        }
                    }
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
