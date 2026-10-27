import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Documentos» del grupo Archivos (lo mismo que la pestaña del panel): PDF, Word y Excel a
// Markdown y Markdown o lo copiado a Word o PDF. Se le pueden soltar archivos encima del grupo,
// cerrado o abierto; el resultado queda junto al original (ver akari/documentos.py).
Pieza {
    id: capsula
    clave: "documentos"
    titulo: U.t("Documentos", "Documents")
    icono: "swap_horiz"
    anchoChip: 58
    anchoAbierto: 380
    aceptaArchivos: true
    patron: /\.(pdf|docx?|odt|rtf|csv|pptx|html?|xlsx|xlsm|xls|ods|md|markdown|txt)$/i

    readonly property var estado: Datos.docs
    property string modo: "a-md"            // "a-md" | "desde-md"
    property string formato: "docx"         // "docx" | "pdf" (desde Markdown)
    property string respuesta: ""
    readonly property var trabajos: estado ? estado.trabajos : []
    readonly property int activos: trabajos.filter(x => x.estado === "cola" || x.estado === "convirtiendo").length
    readonly property bool pdfNo: modo === "desde-md" && formato === "pdf" && !!estado && !estado.libreoffice
    readonly property var iconos: ({ md: "markdown", docx: "description", pdf: "picture_as_pdf" })

    function accion(cuerpo) {
        respuesta = "";
        Datos.enviar("/api/documentos", Object.assign({ modo: modo, formato: formato }, cuerpo),
                     r => capsula.respuesta = r.ok ? "" : (r.mensaje || U.t("No se pudo.", "It didn't work.")));
    }
    function destino(f) { return f === "md" ? "Markdown" : f === "pdf" ? "PDF" : "Word"; }

    onSoltaron: urls => {
        if (!estado || !estado.listo) { respuesta = U.t("Primero instala el conversor.", "Install the converter first."); return; }
        accion({ accion: "convertir", rutas: urls });
    }

    // icono (gira mientras convierte; flecha de bajar con un archivo encima) y cuántos van
    resumen: Component {
        Row {
            spacing: 4
            Item { width: 6; height: 1 }
            Icono {
                id: iconoCabecera
                anchors.verticalCenter: parent.verticalCenter
                text: capsula.archivoEncima ? "download" : "swap_horiz"
                tam: 19
                relleno: 1
                color: capsula.estado && !capsula.estado.listo ? Tema.contorno : Tema.primario
                RotationAnimation on rotation {
                    running: capsula.activos > 0 && !capsula.archivoEncima
                    from: 0; to: 360; duration: 1400; loops: Animation.Infinite
                    onRunningChanged: if (!running) iconoCabecera.rotation = 0   // «parent» aquí es la fila
                }
            }
            Etiqueta {
                anchors.verticalCenter: parent.verticalCenter
                text: !capsula.estado ? "—" : capsula.activos ? String(capsula.activos) : String(capsula.trabajos.filter(x => x.estado === "listo").length)
                tam: 15
                peso: Font.Medium
                color: capsula.activos ? Tema.primario : Tema.sobreSuperficie
            }
        }
    }

    // ------------------------------------------------------------ abierta
    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            Pestanas {
                visible: !!capsula.estado && capsula.estado.listo
                Layout.alignment: Qt.AlignHCenter
                opciones: [{ id: "a-md", texto: U.t("A Markdown", "To Markdown") },
                           { id: "desde-md", texto: U.t("Desde Markdown", "From Markdown") }]
                actual: capsula.modo
                onElegida: id => { capsula.modo = id; capsula.respuesta = ""; }
            }

            // ------------------------------------------------ instalar
            Tarjeta {
                visible: !!capsula.estado && !capsula.estado.listo
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: filaInstalar.implicitHeight + 24
                RowLayout {
                    id: filaInstalar
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 12
                    spacing: 12
                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        Layout.alignment: Qt.AlignTop
                        radius: 19
                        color: Tema.contSecundario
                        Icono { anchors.centerIn: parent; text: "swap_horiz"; tam: 20; color: Tema.sobreContSecundario }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Etiqueta { Layout.fillWidth: true; text: U.t("Conversor de documentos", "Document converter"); peso: Font.Medium }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: U.t("PDF, Word y Excel a Markdown (para una IA u Obsidian) y Markdown o lo copiado a Word o PDF. Se instala una vez (≈150 MB, sin contraseña).",
                                      "PDF, Word and Excel to Markdown (for an AI or Obsidian) and Markdown or copied text to Word or PDF. Installs once (≈150 MB, no password).")
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                        Etiqueta {
                            Layout.fillWidth: true
                            visible: !!capsula.estado && !!capsula.estado.error_instalacion
                            text: capsula.estado ? capsula.estado.error_instalacion : ""
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            tam: Tema.textoChico
                            color: Tema.error
                        }
                    }
                }
            }
            Boton {
                visible: !!capsula.estado && !capsula.estado.listo
                Layout.alignment: Qt.AlignHCenter
                principal: true
                ocupado: !!capsula.estado && capsula.estado.instalando
                icono: ocupado ? "progress_activity" : "download"
                texto: ocupado ? U.t("Instalando…", "Installing…") : U.t("Instalar", "Install")
                onPulsado: capsula.accion({ accion: "instalar" })
            }

            Row {
                visible: !!capsula.estado && capsula.estado.listo && capsula.modo === "desde-md"
                Layout.alignment: Qt.AlignHCenter
                spacing: 6
                Etiqueta { text: U.t("Sacar como", "Save as"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar; anchors.verticalCenter: parent.verticalCenter }
                Pestanas {
                    alto: 26
                    opciones: [{ id: "docx", texto: "Word", icono: "description" }, { id: "pdf", texto: "PDF", icono: "picture_as_pdf" }]
                    actual: capsula.formato
                    onElegida: id => capsula.formato = id
                }
            }
            Etiqueta {
                visible: capsula.pdfNo
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: U.t("Para PDF hace falta LibreOffice (gratis). Word funciona sin él.", "PDF needs LibreOffice (free). Word works without it.")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
                color: Tema.error
            }

            // zona para soltar (en realidad se puede soltar en toda la cápsula)
            Rectangle {
                visible: (!!capsula.estado && capsula.estado.listo)
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
                    Icono {
                        Layout.alignment: Qt.AlignHCenter
                        text: capsula.modo === "a-md" ? "upload_file" : "markdown"
                        tam: 32
                        color: Tema.primario
                    }
                    Etiqueta {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: capsula.modo === "a-md" ? U.t("Suelta aquí PDF, Word, Excel o CSV", "Drop PDF, Word, Excel or CSV here")
                            : U.t("Suelta aquí archivos Markdown (.md)", "Drop Markdown (.md) files here")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        peso: Font.Medium
                    }
                    Etiqueta {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: capsula.modo === "a-md" ? U.t("Sale un .md junto al original, listo para una IA u Obsidian.", "A .md appears next to the original, ready for an AI or Obsidian.")
                            : U.t("Sale un documento con las tablas bien repartidas.", "You get a document with well-sized tables.")
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
                            ocupado: (!!capsula.estado && capsula.estado.eligiendo) || capsula.pdfNo
                            onPulsado: capsula.accion({ accion: "elegir" })
                        }
                        Boton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: capsula.modo === "desde-md"
                            icono: "content_paste"
                            texto: U.t("Convertir lo copiado", "Convert clipboard")
                            ocupado: capsula.pdfNo
                            onPulsado: capsula.accion({ accion: "portapapeles" })
                        }
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

            // ------------------------------------------------ últimos
            Tarjeta {
                visible: (!!capsula.estado && capsula.estado.listo) && capsula.trabajos.length > 0
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
                        Etiqueta { Layout.fillWidth: true; Layout.leftMargin: 6; text: U.t("Últimos", "Recent"); peso: Font.Medium }
                        BotonIcono {
                            icono: "folder"
                            onPulsado: capsula.accion({ accion: "carpeta" })
                        }
                        BotonIcono {
                            icono: "delete_sweep"
                            onPulsado: capsula.accion({ accion: "limpiar" })
                        }
                    }
                    Repeater {
                        model: capsula.trabajos.slice(0, 8)
                        delegate: Rectangle {
                            id: filaDoc
                            required property var modelData
                            readonly property bool listo: modelData.estado === "listo"
                            readonly property bool ocupado: modelData.estado === "cola" || modelData.estado === "convirtiendo"
                            width: listaUltimos.width
                            height: 44
                            radius: 10
                            color: listo && zonaFila.containsMouse ? Tema.contenedorAlto : "transparent"
                            MouseArea {
                                id: zonaFila
                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: filaDoc.listo
                                cursorShape: Qt.PointingHandCursor
                                onClicked: capsula.accion({ accion: "abrir", id: filaDoc.modelData.id })
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 2
                                spacing: 10
                                Icono {
                                    id: iconoDoc
                                    text: filaDoc.listo ? (capsula.iconos[filaDoc.modelData.formato] || "description")
                                        : filaDoc.modelData.estado === "error" ? "error" : "progress_activity"
                                    tam: 19
                                    color: filaDoc.modelData.estado === "error" ? Tema.error : filaDoc.listo ? Tema.primario : Tema.sobreSuperficieVar
                                    RotationAnimation on rotation {
                                        running: filaDoc.ocupado
                                        from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                                        onRunningChanged: if (!running) iconoDoc.rotation = 0
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Etiqueta { Layout.fillWidth: true; text: filaDoc.modelData.nombre; tam: Tema.textoChico + 1; peso: Font.Medium }
                                    Etiqueta {
                                        Layout.fillWidth: true
                                        text: filaDoc.modelData.estado === "cola" ? U.t("En espera…", "Waiting…")
                                            : filaDoc.modelData.estado === "convirtiendo" ? U.t("Convirtiendo a ", "Converting to ") + capsula.destino(filaDoc.modelData.formato) + "…"
                                            : filaDoc.listo ? "→ " + capsula.destino(filaDoc.modelData.formato) + " · " + filaDoc.modelData.mensaje
                                            : filaDoc.modelData.mensaje
                                        tam: 10
                                        color: filaDoc.modelData.estado === "error" ? Tema.error : Tema.sobreSuperficieVar
                                    }
                                }
                                BotonIcono {
                                    visible: filaDoc.listo
                                    icono: "folder_open"
                                    onPulsado: capsula.accion({ accion: "abrir", id: filaDoc.modelData.id, carpeta: true })
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
