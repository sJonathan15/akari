import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Cerebro» del grupo Archivos: el mapa de la computadora y la memoria de las sesiones con IA
// (ver akari/cerebro.py). Nunca mueve ni cambia archivos del usuario. Cerrada: cuántos archivos conoce
// (o un aviso si falta crearlo). Abierta: estado, buscador «¿dónde está…?» con Abrir y Mostrar en
// carpeta, «En qué quedamos» y los botones de Obsidian, revisar y conectar con Claude Code / Codex.
// La primera vez, lo esencial (qué recorre, qué nunca mira) y «Crear mi cerebro» con la carpeta
// personal; para elegir otras carpetas, el panel completo.
Pieza {
    id: capsula
    clave: "cerebro"
    titulo: U.t("Cerebro", "Brain")
    icono: "neurology"
    anchoChip: 70
    anchoAbierto: 380
    pideTeclado: true

    readonly property var estado: Datos.cerebro
    readonly property bool listo: !!estado && estado.configurado
    readonly property var cif: estado && estado.cifras ? estado.cifras : ({})
    property var resultados: []
    property string respuesta: ""
    property bool buscando: false

    function corto(n) { return n === undefined || n === null ? "—" : U.corto(n); }
    function accion(cuerpo, listoFn) {
        Datos.enviar("/api/cerebro", cuerpo, r => {
            if (listoFn) listoFn(r);
            else capsula.respuesta = r.mensaje || (r.ok ? "" : U.t("No se pudo.", "It didn't work."));
        });
    }
    function buscar(q) {
        if (!q.trim()) { resultados = []; return; }
        buscando = true;
        accion({ accion: "buscar", q: q }, r => { capsula.buscando = false; capsula.resultados = r.resultados || []; });
    }
    function iconoTipo(tipo) {
        return ({ carpeta: "folder", documento: "description", hoja: "table_chart", presentacion: "slideshow",
                  imagen: "image", audio: "music_note", video: "movie", codigo: "code", area: "folder_special",
                  proyecto: "inventory_2", sesion: "history", nota: "sticky_note_2", texto: "article" })[tipo] || "draft";
    }
    function nombreAgente(a) { return a === "claude" ? "Claude Code" : a === "codex" ? "Codex" : U.t("asistente", "assistant"); }
    function cuando(ts) {
        if (!ts) return "—";
        const dias = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(ts * 1000).setHours(0, 0, 0, 0)) / 86400000);
        return dias <= 0 ? U.t("hoy", "today") : dias === 1 ? U.t("ayer", "yesterday") : U.t("hace " + dias + " días", dias + " days ago");
    }

    resumen: Component {
        Row {
            spacing: 4
            Item { width: 6; height: 1 }
            Icono {
                id: iconoChip
                anchors.verticalCenter: parent.verticalCenter
                text: "neurology"
                tam: 19
                relleno: capsula.listo ? 1 : 0
                color: !capsula.listo ? Tema.terciario : capsula.estado.salud === "atencion" ? Tema.terciario : Tema.primario
                SequentialAnimation on opacity {
                    running: capsula.listo && capsula.estado.salud === "revisando"
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.35; duration: 700 }
                    NumberAnimation { to: 1; duration: 700 }
                    onRunningChanged: if (!running) iconoChip.opacity = 1
                }
            }
            Etiqueta {
                anchors.verticalCenter: parent.verticalCenter
                text: !capsula.estado ? "—" : !capsula.listo ? U.t("crear", "set up") : capsula.corto(capsula.cif.archivos)
                tam: capsula.listo ? 15 : Tema.textoChico
                peso: Font.Medium
            }
        }
    }

    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            // ------------------------------------------------ primera vez
            Tarjeta {
                visible: !!capsula.estado && !capsula.listo
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: primera.implicitHeight + 28
                ColumnLayout {
                    id: primera
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 16
                    spacing: 8
                    Etiqueta {
                        Layout.fillWidth: true
                        text: U.t("No mueve, renombra ni cambia tus archivos.", "It never moves, renames or changes your files.")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoGrande
                        peso: Font.Medium
                        color: Tema.primario
                    }
                    Etiqueta {
                        Layout.fillWidth: true
                        text: U.t("Solo mira sus nombres y arma un mapa (una bóveda de Obsidian) para que tu IA los encuentre y recuerde en qué quedaron. Todo se queda en tu equipo.",
                                  "It only looks at their names and builds a map (an Obsidian vault) so your AI finds them and remembers where you left off. Everything stays on your computer.")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    Etiqueta {
                        Layout.fillWidth: true
                        text: U.t("Nunca mira: ", "Never looks at: ") + (capsula.estado ? capsula.estado.excluido.join(" · ") : "")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: 10
                        color: Tema.contorno
                    }
                    RowLayout {
                        spacing: 8
                        Boton {
                            principal: true
                            icono: "neurology"
                            texto: U.t("Crear mi cerebro", "Create my brain")
                            onPulsado: capsula.accion({ accion: "configurar", carpetas: [capsula.estado.candidatas[0].ruta] })
                        }
                        Boton {
                            texto: U.t("Elegir carpetas", "Choose folders")
                            onPulsado: U.abrirPanel(Quickshell)
                        }
                    }
                }
            }

            // ------------------------------------------------ estado y cifras
            RowLayout {
                visible: capsula.listo
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 12
                spacing: 6
                Icono {
                    text: !capsula.listo ? "" : capsula.estado.salud === "revisando" ? "sync" : capsula.estado.salud === "sano" ? "check_circle" : "error"
                    tam: 16
                    relleno: 1
                    color: capsula.listo && capsula.estado.salud === "sano" ? Tema.exito : Tema.terciario
                }
                Etiqueta {
                    Layout.fillWidth: true
                    text: !capsula.listo ? "" : capsula.estado.salud === "revisando"
                        ? U.t("Revisando… ", "Checking… ") + capsula.corto(capsula.estado.progreso ? capsula.estado.progreso.archivos : 0)
                        : (capsula.estado.salud === "sano" ? U.t("Sano", "Healthy") : U.t("Revisar", "Needs a check"))
                          + " · " + U.t("revisado ", "checked ") + (capsula.cif.ultima_revision ? U.hace(Date.now() / 1000 - capsula.cif.ultima_revision) : "—")
                    tam: Tema.textoChico
                    color: Tema.sobreSuperficieVar
                }
            }
            Etiqueta {
                visible: capsula.listo
                Layout.fillWidth: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                text: capsula.corto(capsula.cif.archivos) + U.t(" archivos · ", " files · ") + (capsula.cif.proyectos || 0)
                    + U.t(" proyectos · ", " projects · ") + (capsula.cif.areas || 0) + U.t(" áreas · ", " areas · ")
                    + (capsula.cif.sesiones_hoy || 0) + U.t(" sesiones hoy", " sessions today")
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                tam: Tema.textoChico
            }

            // ------------------------------------------------ buscador
            Rectangle {
                visible: capsula.listo
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 40
                radius: 20
                color: Tema.contenedorMax
                border.width: campo.activeFocus ? 1.5 : 0
                border.color: Tema.primario
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 10
                    spacing: 6
                    Icono { text: capsula.buscando ? "progress_activity" : "search"; tam: 18; color: Tema.sobreSuperficieVar }
                    TextInput {
                        id: campo
                        Layout.fillWidth: true
                        clip: true
                        font.family: Tema.fuente
                        font.pixelSize: Tema.texto
                        color: Tema.sobreSuperficie
                        selectionColor: Tema.alfa(Tema.primario, 0.4)
                        Binding { target: capsula; property: "retener"; value: campo.activeFocus }
                        onTextEdited: espera.restart()
                        onAccepted: capsula.buscar(text)
                        Keys.onEscapePressed: { text = ""; capsula.resultados = []; focus = false; }
                        Timer { id: espera; interval: 250; onTriggered: capsula.buscar(campo.text) }
                        Etiqueta {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !campo.text && !campo.activeFocus
                            text: U.t("¿Dónde está…?", "Where is…?")
                            color: Tema.contorno
                        }
                    }
                }
            }
            Repeater {
                model: capsula.resultados.slice(0, 8)
                delegate: RowLayout {
                    id: fila
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 8
                    spacing: 8
                    Icono { text: capsula.iconoTipo(fila.modelData.tipo); tam: 18; color: Tema.primario }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Etiqueta { Layout.fillWidth: true; text: fila.modelData.nombre; peso: Font.Medium; tam: Tema.textoChico + 1 }
                        Etiqueta { Layout.fillWidth: true; text: fila.modelData.carpeta || fila.modelData.ruta; tam: 10; color: Tema.contorno; elide: Text.ElideMiddle }
                    }
                    BotonIcono {
                        icono: "open_in_new"
                        onPulsado: capsula.accion({ accion: "abrir", ruta: fila.modelData.ruta })
                    }
                    BotonIcono {
                        icono: "folder_open"
                        onPulsado: capsula.accion({ accion: "abrir", ruta: fila.modelData.ruta, carpeta: true })
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
                color: Tema.terciario
            }

            // ------------------------------------------------ en qué quedamos
            Tarjeta {
                visible: capsula.listo && (capsula.estado.sesiones.length > 0 || capsula.estado.pendientes.length > 0)
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: memoria.implicitHeight + 24
                ColumnLayout {
                    id: memoria
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 14
                    spacing: 6
                    Etiqueta { text: U.t("En qué quedamos", "Where we left off"); peso: Font.Medium }
                    Repeater {
                        model: capsula.listo ? capsula.estado.sesiones.slice(0, 3) : []
                        delegate: Etiqueta {
                            required property var modelData
                            Layout.fillWidth: true
                            text: capsula.cuando(modelData.fin) + " · " + capsula.nombreAgente(modelData.agente)
                                + (modelData.proyecto_nombre ? " · " + modelData.proyecto_nombre : "") + ": "
                                + (modelData.resumen || modelData.titulo)
                                + (modelData.pendiente ? U.t(" — pendiente: ", " — to do: ") + modelData.pendiente : "")
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            maximumLineCount: 3
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                    }
                    Repeater {
                        model: capsula.listo ? capsula.estado.pendientes.slice(0, 4) : []
                        delegate: RowLayout {
                            id: pend
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 6
                            BotonIcono {
                                icono: "check_box_outline_blank"
                                tam: 26
                                onPulsado: capsula.accion({ accion: "hecho", id: pend.modelData.id })
                            }
                            Etiqueta {
                                Layout.fillWidth: true
                                text: pend.modelData.texto + (pend.modelData.proyecto_nombre ? " · " + pend.modelData.proyecto_nombre : "")
                                tam: Tema.textoChico
                            }
                        }
                    }
                }
            }

            // ------------------------------------------------ botones
            Flow {
                visible: capsula.listo
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                spacing: 6
                Boton {
                    icono: "auto_stories"
                    texto: capsula.estado && capsula.estado.obsidian ? U.t("Abrir en Obsidian", "Open in Obsidian") : U.t("Instalar Obsidian", "Install Obsidian")
                    onPulsado: capsula.accion({ accion: capsula.estado.obsidian ? "obsidian" : "obsidian_instalar" })
                }
                Boton {
                    icono: "sync"
                    texto: U.t("Revisar ahora", "Check now")
                    ocupado: capsula.listo && capsula.estado.salud === "revisando"
                    onPulsado: capsula.accion({ accion: "revisar" })
                }
                Boton {
                    readonly property bool puesto: capsula.listo && (capsula.estado.conectado.claude || capsula.estado.conectado.codex)
                    icono: puesto ? "link_off" : "link"
                    texto: puesto ? U.t("Desconectar agentes", "Disconnect agents") : U.t("Conectar con Claude Code / Codex", "Connect Claude Code / Codex")
                    onPulsado: capsula.accion({ accion: puesto ? "desconectar" : "conectar" })
                }
                Boton {
                    icono: "folder_managed"
                    texto: U.t("Elegir carpetas", "Choose folders")
                    onPulsado: U.abrirPanel(Quickshell)
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
