import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Asistente» del grupo IA, como una cápsula de voz: el muñequito y su estado, dónde se hace
// (terminal o segundo plano), quién responde (Claude o el modelo de «Modelos de IA»), la palabra
// clave y la voz, un campo para escribir y el historial con la hora. Ver akari/asistente.py.
Pieza {
    id: capsula
    clave: "asistente"
    titulo: U.t("Asistente", "Assistant")
    icono: "chat"
    anchoChip: 48
    anchoAbierto: 384
    pideTeclado: true

    readonly property var estado: Datos.asistente
    readonly property var aj: estado ? estado.ajustes : null
    readonly property var voz: estado ? estado.voz : null
    readonly property string fase: !estado ? "pausa" : estado.historial.length && estado.historial[0].error
        && Date.now() / 1000 - estado.historial[0].t < 8 ? "error" : estado.estado
    property bool enviando: false

    function accion(cuerpo, listo) { Datos.enviar("/api/asistente", cuerpo, listo); }
    function preguntar(texto) {
        if (!texto.trim()) return;
        enviando = true;
        accion({ accion: "preguntar", texto: texto }, () => capsula.enviando = false);
    }
    function textoEstado() {
        if (!estado) return "…";
        return ({ pausa: U.t("Micrófono en pausa", "Microphone paused"),
                  escuchando: U.t("Escuchando «akari»…", "Listening for “akari”…"),
                  oyendo: U.t("Te escucho…", "I'm listening…"),
                  confirmando: U.t("Te escucho…", "I'm listening…"),
                  pensando: U.t("Pensando…", "Thinking…"),
                  hablando: U.t("Hablando…", "Speaking…"),
                  error: U.t("Algo falló", "Something failed") })[fase] || "";
    }

    resumen: Component {
        Item {
            Muneco {
                anchors.centerIn: parent
                width: 26
                height: 28
                estado: capsula.fase
            }
        }
    }

    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            // ------------------------------------------------ el muñequito y su estado
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 104
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 14
                    Rectangle {
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 80
                        radius: 20
                        color: Tema.alfa(Tema.primario, capsula.fase === "pausa" ? 0.06 : 0.14)
                        Behavior on color { ColorAnimation { duration: 300 } }
                        Muneco {
                            anchors.centerIn: parent
                            width: 65
                            height: 70
                            estado: capsula.fase
                            visible: capsula.abierta
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Etiqueta { Layout.fillWidth: true; text: U.t("Asistente", "Assistant"); tam: Tema.textoGrande; peso: Font.Medium }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.textoEstado()
                            color: capsula.fase === "pausa" ? Tema.sobreSuperficieVar : capsula.fase === "error" ? Tema.error : Tema.primario
                        }
                        Etiqueta {
                            Layout.fillWidth: true
                            visible: !!capsula.estado && !capsula.estado.listo
                            text: capsula.estado ? capsula.estado.motivo : ""
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            tam: Tema.textoChico
                            color: Tema.terciario
                        }
                    }
                }
            }

            // sin modelo: decirlo y llevar a «Modelos de IA»
            Boton {
                visible: !!capsula.estado && !capsula.estado.listo && !!capsula.aj && capsula.aj.quien === "local"
                Layout.alignment: Qt.AlignHCenter
                principal: true
                icono: "psychology"
                texto: U.t("Elegir un modelo de IA", "Choose an AI model")
                onPulsado: if (capsula.grupo) capsula.grupo.elegir("modelos")
            }

            // ------------------------------------------------ dónde y quién
            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 14
                columns: 2
                columnSpacing: 10
                rowSpacing: 8
                Etiqueta { text: U.t("Hacerlo en", "Do it in"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                Pestanas {
                    alto: 28
                    opciones: [{ id: "terminal", texto: U.t("Terminal", "Terminal"), icono: "terminal" },
                               { id: "fondo", texto: U.t("Segundo plano", "Background"), icono: "bolt" }]
                    actual: capsula.aj ? capsula.aj.donde : "fondo"
                    onElegida: id => capsula.accion({ accion: "ajustes", donde: id })
                }
                Etiqueta { text: U.t("Quién", "Who"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                Pestanas {
                    alto: 28
                    opciones: [{ id: "claude", texto: "Claude", icono: "auto_awesome" },
                               { id: "local", texto: U.t("Local", "Local"), icono: "psychology" }]
                    actual: capsula.aj ? capsula.aj.quien : "local"
                    onElegida: id => capsula.accion({ accion: "ajustes", quien: id })
                }
            }

            // ------------------------------------------------ voz
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: columnaVoz.implicitHeight + 20
                ColumnLayout {
                    id: columnaVoz
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    anchors.leftMargin: 14
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Etiqueta { Layout.fillWidth: true; text: U.t("Escuchar palabra clave «akari»", "Listen for “akari”") }
                        Interruptor {
                            enabled: !!capsula.voz && capsula.voz.instalada
                            opacity: enabled ? 1 : 0.4
                            activo: !!capsula.aj && capsula.aj.palabra_clave
                            onCambiado: valor => capsula.accion({ accion: "ajustes", palabra_clave: valor })
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Etiqueta { Layout.fillWidth: true; text: U.t("Responder en voz alta", "Answer out loud") }
                        BotonIcono {
                            visible: !!capsula.voz && capsula.voz.hablando
                            icono: "volume_off"
                            tam: 26
                            onPulsado: capsula.accion({ accion: "callar" })
                        }
                        Interruptor {
                            enabled: !!capsula.voz && capsula.voz.instalada
                            opacity: enabled ? 1 : 0.4
                            activo: !!capsula.aj && capsula.aj.voz_alta
                            onCambiado: valor => capsula.accion({ accion: "ajustes", voz_alta: valor })
                        }
                    }
                    // sin voz: se instala con un botón (sin ella, se le escribe)
                    RowLayout {
                        visible: !!capsula.voz && !capsula.voz.instalada
                        Layout.fillWidth: true
                        spacing: 8
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.voz && capsula.voz.error ? capsula.voz.error
                                : U.t("La voz se descarga aparte (≈350 MB, sin contraseña).", "Voice is a separate download (≈350 MB, no password).")
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            tam: Tema.textoChico
                            color: capsula.voz && capsula.voz.error ? Tema.error : Tema.sobreSuperficieVar
                        }
                        Boton {
                            ocupado: !!capsula.voz && capsula.voz.instalando
                            icono: ocupado ? "progress_activity" : "mic"
                            texto: ocupado ? "…" : U.t("Instalar voz", "Install voice")
                            onPulsado: capsula.accion({ accion: "instalar_voz" })
                        }
                    }
                    Etiqueta {
                        visible: !!capsula.voz && capsula.voz.instalada && !capsula.voz.microfono
                        Layout.fillWidth: true
                        text: U.t("Falta pw-record o parecord para usar el micrófono.", "pw-record or parecord is needed for the microphone.")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.terciario
                    }
                    // carpeta de notas (sirve una bóveda de Obsidian)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Icono { text: "edit_note"; tam: 18; color: Tema.sobreSuperficieVar }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.aj && capsula.aj.notas ? U.t("Notas: ", "Notes: ") + capsula.aj.notas.split(/[\\/]/).pop()
                                : U.t("Sin carpeta de notas", "No notes folder")
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                        BotonIcono {
                            icono: "folder_open"
                            tam: 28
                            onPulsado: capsula.accion({ accion: "elegir_notas" })
                        }
                    }
                }
            }

            // ------------------------------------------------ escribir
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 42
                radius: 21
                color: Tema.contenedorMax
                border.width: campo.activeFocus ? 1.5 : 0
                border.color: Tema.primario
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 5
                    spacing: 6
                    TextInput {
                        id: campo
                        Layout.fillWidth: true
                        clip: true
                        font.family: Tema.fuente
                        font.pixelSize: Tema.texto
                        color: Tema.sobreSuperficie
                        selectionColor: Tema.alfa(Tema.primario, 0.4)
                        enabled: !capsula.enviando && capsula.fase !== "pensando"
                        Binding { target: capsula; property: "retener"; value: campo.activeFocus }
                        onAccepted: { capsula.preguntar(text); text = ""; }
                        Keys.onEscapePressed: { text = ""; focus = false; }
                        Etiqueta {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !campo.text && !campo.activeFocus
                            text: U.t("O escríbelo aquí…", "Or type it here…")
                            color: Tema.contorno
                        }
                    }
                    Rectangle {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        radius: 16
                        color: Tema.primario
                        opacity: campo.text ? 1 : 0.5
                        Icono {
                            id: iconoEnviar
                            anchors.centerIn: parent
                            text: capsula.fase === "pensando" ? "progress_activity" : "arrow_upward"
                            tam: 18
                            color: Tema.sobrePrimario
                            RotationAnimation on rotation {
                                running: capsula.fase === "pensando"
                                from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                                onRunningChanged: if (!running) iconoEnviar.rotation = 0
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { capsula.preguntar(campo.text); campo.text = ""; }
                        }
                    }
                }
            }

            // ------------------------------------------------ historial
            Repeater {
                model: capsula.estado ? capsula.estado.historial.slice(0, 6) : []
                delegate: Tarjeta {
                    id: entrada
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    Layout.preferredHeight: columnaEntrada.implicitHeight + 20
                    color: Tema.contenedor
                    ColumnLayout {
                        id: columnaEntrada
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 10
                        anchors.leftMargin: 14
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Icono {
                                text: entrada.modelData.via === "voz" ? "mic" : "chat_bubble"
                                tam: 14
                                color: Tema.sobreSuperficieVar
                            }
                            Etiqueta {
                                Layout.fillWidth: true
                                text: entrada.modelData.pregunta
                                peso: Font.Medium
                                tam: Tema.textoChico + 1
                                wrapMode: Text.WordWrap
                                elide: Text.ElideNone
                                maximumLineCount: 2
                            }
                            Etiqueta {
                                text: U.hora(entrada.modelData.t)
                                tam: 10
                                font.family: Tema.mono
                                color: Tema.contorno
                            }
                        }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: entrada.modelData.respuesta
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            maximumLineCount: 6
                            tam: Tema.textoChico + 1
                            color: entrada.modelData.error ? Tema.error : Tema.sobreSuperficieVar
                        }
                        Etiqueta {
                            visible: entrada.modelData.herramientas.length > 0 || entrada.modelData.quien === "claude"
                            text: (entrada.modelData.quien === "claude" ? "Claude" : entrada.modelData.quien === "akari" ? U.t("sin modelo", "no model") : "")
                                + (entrada.modelData.herramientas.length ? (entrada.modelData.quien !== "local" ? " · " : "") + entrada.modelData.herramientas.join(" · ") : "")
                            tam: 10
                            color: Tema.contorno
                        }
                    }
                }
            }
            BotonIcono {
                visible: !!capsula.estado && capsula.estado.historial.length > 0
                Layout.alignment: Qt.AlignHCenter
                icono: "delete_sweep"
                onPulsado: capsula.accion({ accion: "borrar" })
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
