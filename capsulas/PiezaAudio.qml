import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Audio» del grupo Archivos: audio o video → .md con la transcripción (akari/audio.py), en el
// equipo con faster-whisper o con la clave de Groq / OpenAI; reuniones (micrófono + lo que suena)
// en Linux; resumen y notas con el modelo de «Modelos de IA».
Pieza {
    id: capsula
    clave: "audio"
    titulo: U.t("Audio", "Audio")
    icono: "graphic_eq"
    anchoChip: 72
    anchoAbierto: 380
    aceptaArchivos: true
    patron: /\.(mp3|wav|m4a|ogg|oga|opus|flac|aac|wma|amr|mpga|mpeg|mp4|mkv|mov|avi|webm|m4v|3gp|wmv)$/i

    readonly property var estado: Datos.audio
    readonly property var trabajos: estado ? estado.trabajos : []
    readonly property var actual: trabajos.find(x => x.estado === "transcribiendo") || null
    readonly property int activos: trabajos.filter(x => x.estado === "cola" || x.estado === "transcribiendo").length
    readonly property bool grabando: !!estado && !!estado.grabacion.desde
    readonly property bool ambos: !!estado && estado.listo_local && !!estado.api
    property string respuesta: ""
    property real ahora: Date.now() / 1000
    Timer { interval: 1000; repeat: true; running: capsula.grabando; onTriggered: capsula.ahora = Date.now() / 1000 }

    function accion(cuerpo) {
        respuesta = "";
        Datos.enviar("/api/audio", cuerpo, r => capsula.respuesta = r.ok ? "" : (r.mensaje || U.t("No se pudo.", "It didn't work.")));
    }

    onSoltaron: urls => {
        if (!estado || !estado.usa) { respuesta = U.t("Primero elige cómo transcribir.", "First choose how to transcribe."); return; }
        accion({ accion: "convertir", rutas: urls });
    }

    // grabando: punto rojo y el tiempo; transcribiendo: el %; si no, cuántas hay listas
    resumen: Component {
        Row {
            spacing: 4
            Item { width: 6; height: 1 }
            Icono {
                id: iconoChip
                anchors.verticalCenter: parent.verticalCenter
                text: capsula.archivoEncima ? "download" : capsula.grabando ? "radio_button_checked" : "graphic_eq"
                tam: 19
                relleno: 1
                color: capsula.grabando ? Tema.error : capsula.estado && !capsula.estado.usa ? Tema.contorno : Tema.primario
                SequentialAnimation on opacity {
                    running: capsula.grabando || capsula.activos > 0
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.35; duration: 700 }
                    NumberAnimation { to: 1; duration: 700 }
                    onRunningChanged: if (!running) iconoChip.opacity = 1   // con id: «parent» aquí no es el icono
                }
            }
            Etiqueta {
                anchors.verticalCenter: parent.verticalCenter
                text: !capsula.estado ? "—"
                    : capsula.grabando ? U.reloj(capsula.ahora - capsula.estado.grabacion.desde)
                    : capsula.actual && capsula.actual.pct !== null ? capsula.actual.pct + "%"
                    : String(capsula.trabajos.filter(x => x.estado === "listo").length)
                tam: capsula.grabando || capsula.actual ? Tema.textoChico + 1 : 15
                peso: Font.Medium
                font.family: capsula.grabando ? Tema.mono : Tema.fuente
                color: capsula.grabando ? Tema.error : capsula.actual ? Tema.primario : Tema.sobreSuperficie
            }
        }
    }

    // una opción para transcribir: icono, título, explicación y su botón
    component Opcion: Tarjeta {
        id: opcion
        property string icono: ""
        property bool elegida: false
        property string titulo: ""
        property string detalle: ""
        property string error: ""
        default property alias boton: hueco.data
        Layout.fillWidth: true
        Layout.leftMargin: 10
        Layout.rightMargin: 10
        Layout.preferredHeight: filaOpcion.implicitHeight + 24
        RowLayout {
            id: filaOpcion
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: 12
            spacing: 12
            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignTop
                radius: 18
                color: opcion.elegida ? Tema.primario : Tema.contSecundario
                Icono {
                    anchors.centerIn: parent
                    text: opcion.icono
                    tam: 19
                    relleno: opcion.elegida ? 1 : 0
                    color: opcion.elegida ? Tema.sobrePrimario : Tema.sobreContSecundario
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Etiqueta { Layout.fillWidth: true; text: opcion.titulo; peso: Font.Medium; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                Etiqueta {
                    Layout.fillWidth: true
                    text: opcion.detalle
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    tam: Tema.textoChico
                    color: Tema.sobreSuperficieVar
                }
                Etiqueta {
                    Layout.fillWidth: true
                    visible: opcion.error !== ""
                    text: opcion.error
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    tam: Tema.textoChico
                    color: Tema.error
                }
            }
            Item {
                id: hueco
                Layout.preferredWidth: childrenRect.width
                Layout.preferredHeight: childrenRect.height
            }
        }
    }

    cuerpo: Component {
        ColumnLayout {
            spacing: 8
            readonly property var a: capsula.estado

            Etiqueta {
                visible: !!parent.a && !parent.a.usa
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: U.t("Suelta una clase, una reunión o un video y sale un .md con la transcripción junto al original. Elige cómo:",
                          "Drop a lecture, a meeting or a video and get a .md transcript next to the original. Choose how:")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            // las dos formas de transcribir (hasta elegir una; para cambiar después, el panel)
            Opcion {
                readonly property var a: capsula.estado
                visible: !!a && !a.usa
                icono: "computer"
                elegida: !!a && a.usa === "local"
                titulo: U.t("En tu equipo (gratis, sin internet)", "On your computer (free, offline)")
                detalle: !a ? "" : (a.gpu ? U.t("Whisper large-v3-turbo en tu ", "Whisper large-v3-turbo on your ") + a.gpu + "."
                                         : U.t("Whisper small en el procesador: tarda más o menos lo que dura el audio.",
                                               "Whisper small on the processor: takes about as long as the audio."))
                        + (a.listo_local ? "" : U.t(" Se instala una vez, sin contraseña.", " Installs once, no password."))
                error: a ? a.error_instalacion : ""
                Boton {
                    visible: !!capsula.estado && !capsula.estado.listo_local
                    principal: !!capsula.estado && !capsula.estado.usa
                    ocupado: !!capsula.estado && capsula.estado.instalando
                    icono: ocupado ? "progress_activity" : "download"
                    texto: ocupado ? "…" : U.t("Instalar", "Install")
                    onPulsado: capsula.accion({ accion: "instalar" })
                }
            }
            Opcion {
                readonly property var a: capsula.estado
                visible: !!a && !a.usa
                icono: "key"
                elegida: !!a && !!a.api && a.usa === a.api
                titulo: U.t("Con tu clave de API", "With your API key")
                detalle: a && a.api ? U.t("Whisper de ", "Whisper by ") + a.api_nombre + U.t(": rápido; se cobra en tu cuenta.", ": fast; billed to your account.")
                    : U.t("Guarda una clave de Groq u OpenAI en «Modelos de IA» (panel).", "Save a Groq or OpenAI key in “AI models” (panel).")
                Boton {
                    visible: !!capsula.estado && !capsula.estado.api
                    icono: "open_in_new"
                    texto: U.t("Clave", "Key")
                    onPulsado: U.abrirPanel(Quickshell)
                }
            }

            // con cuál transcribir, si están los dos
            Pestanas {
                visible: capsula.ambos
                Layout.alignment: Qt.AlignHCenter
                alto: 26
                opciones: capsula.ambos ? [{ id: "auto", texto: U.t("Automático", "Automatic") },
                                           { id: "local", texto: U.t("Mi equipo", "My computer"), icono: "computer" },
                                           { id: "api", texto: capsula.estado.api_nombre, icono: "key" }] : []
                actual: capsula.estado ? capsula.estado.modo : "auto"
                onElegida: id => capsula.accion({ accion: "ajustes", modo: id })
            }

            // zona para soltar (en realidad se puede soltar en todo el grupo)
            Rectangle {
                visible: !!capsula.estado && !!capsula.estado.usa
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: zona.implicitHeight + 32
                radius: Tema.redondeoGrande
                color: capsula.archivoEncima ? Tema.alfa(Tema.primario, 0.10) : Tema.contenedor
                border.width: 1.5
                border.color: capsula.archivoEncima ? Tema.primario : Tema.contornoVar
                ColumnLayout {
                    id: zona
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 14
                    spacing: 6
                    Icono { Layout.alignment: Qt.AlignHCenter; text: "graphic_eq"; tam: 32; color: Tema.primario }
                    Etiqueta {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: U.t("Suelta aquí un audio o un video", "Drop an audio or video file here")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        peso: Font.Medium
                    }
                    Etiqueta {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: capsula.estado ? U.t("Sale un .md con la transcripción junto al original. ", "A .md transcript appears next to the original. ")
                            + (capsula.estado.usa === "local" ? "Whisper " + capsula.estado.modelo_local : "Whisper · " + capsula.estado.api_nombre) : ""
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    Column {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 4
                        spacing: 8
                        Boton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            principal: true
                            icono: "folder_open"
                            texto: U.t("Elegir archivos", "Choose files")
                            ocupado: !!capsula.estado && capsula.estado.eligiendo
                            onPulsado: capsula.accion({ accion: "elegir" })
                        }
                        Boton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: !!capsula.estado && capsula.estado.grabacion.disponible
                            principal: capsula.grabando
                            icono: capsula.grabando ? "stop_circle" : "radio_button_checked"
                            texto: capsula.grabando ? U.t("Parar · ", "Stop · ") + U.reloj(capsula.ahora - capsula.estado.grabacion.desde)
                                : U.t("Grabar reunión", "Record meeting")
                            onPulsado: capsula.accion({ accion: capsula.grabando ? "parar" : "grabar" })
                        }
                    }
                }
            }

            // resumir al terminar
            Tarjeta {
                visible: !!capsula.estado && !!capsula.estado.usa
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: filaResumir.implicitHeight + 20
                RowLayout {
                    id: filaResumir
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 14
                    anchors.rightMargin: 12
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Etiqueta { Layout.fillWidth: true; text: U.t("Resumir y sacar notas al terminar", "Summarize and take notes when done"); wrapMode: Text.WordWrap; elide: Text.ElideNone }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.estado && capsula.estado.ia_lista ? U.t("Con el modelo de «Modelos de IA».", "With the model in “AI models”.")
                                : U.t("Agrega una clave de API o usa un modelo local.", "Add an API key or use a local model.")
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            tam: Tema.textoChico
                            color: capsula.estado && capsula.estado.ia_lista ? Tema.sobreSuperficieVar : Tema.terciario
                        }
                    }
                    Interruptor {
                        visible: !!capsula.estado && capsula.estado.ia_lista
                        activo: !!capsula.estado && capsula.estado.resumir
                        onCambiado: valor => capsula.accion({ accion: "ajustes", resumir: valor })
                    }
                    Boton {
                        visible: !!capsula.estado && !capsula.estado.ia_lista
                        icono: "psychology"
                        texto: U.t("Elegir", "Choose")
                        onPulsado: U.abrirPanel(Quickshell)
                    }
                }
            }
            Etiqueta {
                visible: capsula.respuesta !== ""
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: capsula.respuesta
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.error
            }

            // ------------------------------------------------ últimas
            Tarjeta {
                visible: capsula.trabajos.length > 0
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: listaUltimos.implicitHeight + 20
                Column {
                    id: listaUltimos
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    spacing: 2
                    RowLayout {
                        width: parent.width
                        Etiqueta { Layout.fillWidth: true; Layout.leftMargin: 6; text: U.t("Últimas", "Recent"); peso: Font.Medium }
                        BotonIcono { icono: "delete_sweep"; onPulsado: capsula.accion({ accion: "limpiar" }) }
                    }
                    Repeater {
                        model: capsula.trabajos.slice(0, 8)
                        delegate: Rectangle {
                            id: filaAudio
                            required property var modelData
                            readonly property bool listo: modelData.estado === "listo"
                            readonly property bool ocupado: modelData.estado === "cola" || modelData.estado === "transcribiendo"
                            readonly property bool resumiendo: modelData.resumen === "haciendo"
                            width: listaUltimos.width
                            height: 44
                            radius: 10
                            color: listo && zonaFila.containsMouse ? Tema.contenedorAlto : "transparent"
                            MouseArea {
                                id: zonaFila
                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: filaAudio.listo
                                cursorShape: Qt.PointingHandCursor
                                onClicked: capsula.accion({ accion: "abrir", id: filaAudio.modelData.id })
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 2
                                spacing: 8
                                Icono {
                                    id: iconoAudio
                                    text: filaAudio.listo ? "description" : filaAudio.modelData.estado === "error" ? "error" : "progress_activity"
                                    tam: 19
                                    color: filaAudio.modelData.estado === "error" ? Tema.error : filaAudio.listo ? Tema.primario : Tema.sobreSuperficieVar
                                    RotationAnimation on rotation {
                                        running: filaAudio.ocupado
                                        from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                                        onRunningChanged: if (!running) iconoAudio.rotation = 0
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Etiqueta { Layout.fillWidth: true; text: filaAudio.modelData.nombre; tam: Tema.textoChico + 1; peso: Font.Medium }
                                    Etiqueta {
                                        Layout.fillWidth: true
                                        readonly property string res: filaAudio.modelData.resumen || ""
                                        text: filaAudio.modelData.estado === "cola" ? U.t("En espera…", "Waiting…")
                                            : filaAudio.modelData.estado === "transcribiendo" ? U.t("Transcribiendo", "Transcribing")
                                                + (filaAudio.modelData.pct !== null ? " · " + filaAudio.modelData.pct + " %" : "…")
                                            : filaAudio.listo ? (res.indexOf("error") === 0 ? res.slice(7)
                                                : filaAudio.resumiendo ? U.t("Resumiendo…", "Summarizing…")
                                                : "→ Markdown · " + filaAudio.modelData.mensaje)
                                            : filaAudio.modelData.mensaje
                                        tam: 10
                                        color: filaAudio.modelData.estado === "error" || res.indexOf("error") === 0 ? Tema.error : Tema.sobreSuperficieVar
                                    }
                                }
                                BotonIcono {
                                    id: botonResumir
                                    visible: filaAudio.listo
                                    icono: filaAudio.resumiendo ? "progress_activity" : "summarize"
                                    colorIcono: filaAudio.modelData.resumen === "listo" ? Tema.primario : Tema.sobreSuperficieVar
                                    onPulsado: if (!filaAudio.resumiendo) capsula.accion({ accion: "resumir", id: filaAudio.modelData.id })
                                }
                                BotonIcono {
                                    visible: filaAudio.listo
                                    icono: "folder_open"
                                    onPulsado: capsula.accion({ accion: "abrir", id: filaAudio.modelData.id, carpeta: true })
                                }
                            }
                        }
                    }
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
