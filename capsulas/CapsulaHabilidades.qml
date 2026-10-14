import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Habilidades (skills) de Claude Code y Codex: las 10 recomendadas para el día a día con
// botón de instalar, las que ya tienes con cuántas veces las usó tu IA, y los conectores MCP.
Capsula {
    id: capsula
    nombre: "habilidades"
    lado: "derecha"
    hueco: 380                  // a la derecha de la cápsula de IA abierta (8 + 360 + margen)
    anchoCerrado: 136
    anchoAbierto: 380
    altoMaximo: 900

    property var estado: Datos.hab
    property string pestana: "recomendadas"
    property bool verMas: false
    readonly property var recomendadas: estado ? estado.recomendadas : []
    readonly property bool instalando: recomendadas.concat(estado ? estado.mas : [])
        .some(r => r.tarea && r.tarea.estado === "instalando")
    readonly property bool hayAgente: !!(estado && (estado.agentes.claude || estado.agentes.codex))

    function accion(id, cual) { Datos.enviar("/api/habilidades", { id: id, accion: cual }); }
    function nombreAgente(a) { return a === "claude" ? "Claude" : "Codex"; }

    // ------------------------------------------------------------- cerrada
    cabecera: Component {
        RowLayout {
            spacing: 6
            Item { Layout.preferredWidth: 8 }
            Icono {
                text: "auto_awesome"
                tam: 19
                relleno: 1
                color: Tema.primario
                RotationAnimation on rotation {
                    running: capsula.instalando
                    from: 0; to: 360; duration: 1400; loops: Animation.Infinite
                    onRunningChanged: if (!running) parent.rotation = 0
                }
            }
            Etiqueta {
                text: capsula.estado ? capsula.estado.total : "—"
                tam: 16
                peso: Font.Medium
            }
            Etiqueta {
                Layout.fillWidth: true
                text: !Datos.enLinea ? "…" : U.t("habilidades", "skills")
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            Item { Layout.preferredWidth: 8 }
        }
    }

    // ------------------------------------------------------------ abierta
    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            // pestañas
            Row {
                Layout.alignment: Qt.AlignHCenter
                spacing: 6
                Repeater {
                    model: [
                        { id: "recomendadas", texto: U.t("Recomendadas", "Recommended") },
                        { id: "instaladas", texto: U.t("Instaladas", "Installed") + (capsula.estado ? " " + capsula.estado.total : "") },
                        { id: "mcp", texto: "MCP" + (capsula.estado ? " " + capsula.estado.mcp.length : "") }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        readonly property bool activa: modelData.id === capsula.pestana
                        width: textoPestana.implicitWidth + 24
                        height: 30
                        radius: 15
                        color: activa ? Tema.primario : Tema.contenedorAlto
                        Etiqueta {
                            id: textoPestana
                            anchors.centerIn: parent
                            text: parent.modelData.texto
                            peso: Font.Medium
                            tam: Tema.textoChico + 1
                            color: parent.activa ? Tema.sobrePrimario : Tema.sobreSuperficieVar
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: capsula.pestana = parent.modelData.id
                        }
                    }
                }
            }

            Etiqueta {
                visible: Datos.enLinea && !capsula.hayAgente
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: U.t("Instala Claude Code o Codex para usar habilidades.", "Install Claude Code or Codex to use skills.")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }

            // ------------------------------------------------ recomendadas
            Etiqueta {
                visible: capsula.pestana === "recomendadas"
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: U.t("10 habilidades útiles para el día a día. Se descargan de su repositorio original en GitHub.",
                          "10 useful everyday skills. They download from their original GitHub repository.")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            Repeater {
                model: capsula.pestana === "recomendadas"
                    ? capsula.recomendadas.concat(capsula.verMas && capsula.estado ? capsula.estado.mas : []) : []
                delegate: FilaHabilidad {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    duena: capsula
                }
            }
            Etiqueta {
                visible: capsula.pestana === "recomendadas"
                Layout.alignment: Qt.AlignHCenter
                text: capsula.verMas ? U.t("Ver menos", "Show less") : U.t("Ver más habilidades", "More skills")
                color: Tema.primario
                peso: Font.Medium
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: capsula.verMas = !capsula.verMas
                }
            }

            // ------------------------------------------------ instaladas
            Tarjeta {
                visible: capsula.pestana === "instaladas"
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: listaInst.implicitHeight + 20
                Column {
                    id: listaInst
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    spacing: 2
                    Etiqueta {
                        visible: !!capsula.estado && capsula.estado.total === 0
                        width: parent.width
                        text: U.t("Todavía no tienes habilidades. Mira las recomendadas.", "No skills yet. Check the recommended ones.")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        color: Tema.sobreSuperficieVar
                    }
                    Repeater {
                        model: capsula.pestana === "instaladas" && capsula.estado ? capsula.estado.instaladas : []
                        delegate: Item {
                            required property var modelData
                            width: listaInst.width
                            height: 42
                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 6
                                anchors.right: usos.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1
                                Etiqueta { width: parent.width; text: modelData.nombre; peso: Font.Medium }
                                Etiqueta {
                                    width: parent.width
                                    text: modelData.agentes.map(capsula.nombreAgente).join(" · ")
                                        + (modelData.origen === "plugin" ? " · plugin" : modelData.origen === "akari" ? " · akari" : "")
                                    tam: Tema.textoChico
                                    color: Tema.sobreSuperficieVar
                                }
                            }
                            Rectangle {
                                id: usos
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                height: 22
                                width: textoUsos.implicitWidth + 16
                                radius: 11
                                color: modelData.usos_7d ? Tema.alfa(Tema.primario, 0.18) : "transparent"
                                Etiqueta {
                                    id: textoUsos
                                    anchors.centerIn: parent
                                    text: modelData.usos_7d ? modelData.usos_7d + U.t(" usos", " uses") : U.t("sin usar", "unused")
                                    tam: Tema.textoChico
                                    color: modelData.usos_7d ? Tema.primario : Tema.contorno
                                }
                            }
                        }
                    }
                    Etiqueta {
                        visible: !!capsula.estado && capsula.estado.total > 0
                        width: parent.width
                        topPadding: 6
                        text: U.t("Usos de los últimos 7 días en Claude Code.", "Uses in the last 7 days in Claude Code.")
                        tam: 10
                        color: Tema.contorno
                    }
                }
            }

            // ------------------------------------------------ conectores MCP
            Tarjeta {
                visible: capsula.pestana === "mcp"
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: listaMcp.implicitHeight + 24
                Column {
                    id: listaMcp
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 6
                    Etiqueta {
                        width: parent.width
                        text: U.t("Conectores MCP: dan a tu IA acceso a otras apps (documentación, navegador, calendarios…).",
                                  "MCP connectors give your AI access to other apps (docs, browser, calendars…).")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    Repeater {
                        model: capsula.pestana === "mcp" && capsula.estado ? capsula.estado.mcp : []
                        delegate: Row {
                            required property var modelData
                            spacing: 8
                            Icono { text: "hub"; tam: 18; color: Tema.primario; anchors.verticalCenter: parent.verticalCenter }
                            Etiqueta { text: modelData.nombre; peso: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
                            Etiqueta { text: capsula.nombreAgente(modelData.agente); tam: Tema.textoChico; color: Tema.sobreSuperficieVar; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                    Etiqueta {
                        visible: !!capsula.estado && capsula.estado.mcp.length === 0
                        text: U.t("No tienes conectores MCP.", "No MCP connectors.")
                        color: Tema.contorno
                    }
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
