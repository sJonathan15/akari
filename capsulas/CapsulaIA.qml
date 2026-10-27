import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

Capsula {
    id: capsula
    nombre: "ia"
    lado: "derecha"
    anchoCerrado: 262
    anchoAbierto: 360
    altoMaximo: 760
    pideTeclado: true

    // Claude Code y/o Codex: se muestra el último que usaste; con los dos, pestañas arriba
    property string elegido: ""
    readonly property var ia: Datos.ia
    readonly property var proveedores: ia ? ["claude", "codex"].filter(p => !!ia[p]) : []
    readonly property string proveedor: proveedores.indexOf(elegido) >= 0 ? elegido
        : ia && ia.principal ? ia.principal : (proveedores[0] || "")
    readonly property bool esClaude: proveedor === "claude"
    property var estado: ia && proveedor ? ia[proveedor] : null
    property real ahora: Date.now() / 1000
    readonly property var v5: estado && estado.limites ? estado.limites.cinco_horas : null
    readonly property var v7: estado && estado.limites ? estado.limites.siete_dias : null
    readonly property var ultima: estado && estado.cinta && estado.cinta.length ? estado.cinta[0] : null
    readonly property bool trabajando: !!ultima && ahora - ultima.t < 25
    readonly property string modelo: estado && estado.modelo_actual ? estado.modelo_actual : ""
    readonly property string familia: !modelo ? "" : esClaude ? modelo.split(" ")[0] : "GPT"
    readonly property var act: estado && estado.activador ? estado.activador : null
    property bool enviando: false           // de pulsar Enviar a que el servidor lo toma
    readonly property bool ocupado: enviando || !!(act && act.ocupado)

    function enviar(texto) {
        if (capsula.ocupado) return;
        capsula.enviando = true;
        Datos.enviar("/api/ia/activar", { mensaje: texto }, () => capsula.enviando = false);
    }
    function ajustar(cambio) { Datos.enviar("/api/ia/activador", cambio); }

    // cada familia de modelos con su color e icono
    function colorFamilia(f) {
        return ({ Opus: Tema.primario, Fable: Tema.terciario, Sonnet: Tema.secundario, Haiku: Tema.exito, GPT: Tema.exito })[f] || Tema.sobreSuperficieVar;
    }
    function iconoFamilia(f) {
        return ({ Opus: "diamond", Fable: "auto_stories", Sonnet: "music_note", Haiku: "spa", GPT: "terminal" })[f] || "smart_toy";
    }

    function colorLibre(v) {
        if (!v) return Tema.contorno;
        return v.libre <= 10 ? Tema.error : v.libre <= 25 ? Tema.terciario : Tema.primario;
    }
    function ritmo(v) {
        if (!v || !v.reinicia) return "";
        if (v.agotado_en) return U.t("A este ritmo se acaba a las ", "At this pace it runs out at ") + U.hora(v.agotado_en);
        return U.t("Se renueva a las ", "Renews at ") + U.hora(v.reinicia) + U.t(" · en ", " · in ") + U.cuenta(v.reinicia - ahora);
    }

    Timer { interval: 1000; running: true; repeat: true; onTriggered: capsula.ahora = Date.now() / 1000 }

    // ------------------------------------------------------------- cerrada
    cabecera: Component {
        RowLayout {
            spacing: 8
            Item { Layout.preferredWidth: 6 }
            Anillo {
                Layout.preferredWidth: 22
                Layout.preferredHeight: 22
                grosor: 4
                valor: capsula.v5 ? capsula.v5.libre / 100 : 0
                color: capsula.colorLibre(capsula.v5)
            }
            Etiqueta {
                text: capsula.v5 ? Math.round(capsula.v5.libre) + "%" : "—"
                tam: 16
                peso: Font.Medium
                color: capsula.colorLibre(capsula.v5)
            }
            Etiqueta {
                text: !Datos.enLinea ? U.t("Iniciando…", "Starting…") : !capsula.proveedor ? U.t("sin Claude ni Codex", "no Claude or Codex")
                    : capsula.v5 ? U.t("libre", "left") : U.t("sin lectura", "no data")
                tam: Tema.textoChico
                color: Tema.sobreSuperficieVar
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                visible: capsula.familia !== ""
                Layout.preferredHeight: 22
                Layout.preferredWidth: filaModelo.implicitWidth + 14
                radius: 11
                color: Tema.alfa(capsula.colorFamilia(capsula.familia), 0.16)
                Row {
                    id: filaModelo
                    anchors.centerIn: parent
                    spacing: 3
                    Icono {
                        text: capsula.iconoFamilia(capsula.familia)
                        tam: 13
                        relleno: 1
                        color: capsula.colorFamilia(capsula.familia)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Etiqueta {
                        text: capsula.familia
                        tam: Tema.textoChico
                        peso: Font.Medium
                        color: capsula.colorFamilia(capsula.familia)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            Etiqueta {
                visible: !!(capsula.v5 && capsula.v5.reinicia)
                text: capsula.v5 && capsula.v5.reinicia ? U.cuenta(capsula.v5.reinicia - capsula.ahora) : ""
                tam: Tema.textoChico
                font.family: Tema.mono
                color: Tema.sobreSuperficieVar
            }
            Rectangle {   // late mientras Claude responde
                Layout.preferredWidth: 7
                Layout.preferredHeight: 7
                radius: 4
                color: capsula.trabajando ? Tema.terciario : Tema.contornoVar
                SequentialAnimation on opacity {
                    running: capsula.trabajando
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 600 }
                    NumberAnimation { to: 1; duration: 600 }
                }
            }
            Item { Layout.preferredWidth: 10 }
        }
    }

    // ------------------------------------------------------------ abierta
    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            // Claude / Codex (solo si están los dos)
            Row {
                Layout.alignment: Qt.AlignHCenter
                visible: capsula.proveedores.length > 1
                spacing: 6
                Repeater {
                    model: capsula.proveedores
                    delegate: Rectangle {
                        required property string modelData
                        readonly property bool activa: modelData === capsula.proveedor
                        width: textoPestana.implicitWidth + 28
                        height: 30
                        radius: 15
                        color: activa ? Tema.primario : Tema.contenedorAlto
                        Etiqueta {
                            id: textoPestana
                            anchors.centerIn: parent
                            text: parent.modelData === "claude" ? "Claude Code" : "Codex"
                            peso: Font.Medium
                            color: parent.activa ? Tema.sobrePrimario : Tema.sobreSuperficieVar
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: capsula.elegido = parent.modelData
                        }
                    }
                }
            }

            // sin Claude Code ni Codex instalados
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: sinIA.implicitHeight + 28
                visible: Datos.enLinea && !capsula.proveedor
                Etiqueta {
                    id: sinIA
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    text: U.t("No encontré Claude Code ni Codex en este equipo. Cuando los instales e inicies sesión, aquí verás tus límites y tokens.",
                              "Neither Claude Code nor Codex was found. Once you install one and sign in, your limits and tokens show up here.")
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    color: Tema.sobreSuperficieVar
                }
            }

            // límites
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: limites.implicitHeight + 28
                visible: !!capsula.estado
                ColumnLayout {
                    id: limites
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    spacing: 14

                    Repeater {
                        model: [
                            { titulo: U.t("Límite de 5 horas", "5-hour limit"), v: capsula.v5 },
                            { titulo: U.t("Límite semanal", "Weekly limit"), v: capsula.v7 }
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            spacing: 14
                            Item {
                                Layout.preferredWidth: 64
                                Layout.preferredHeight: 64
                                Anillo {
                                    anchors.fill: parent
                                    grosor: 6
                                    valor: parent.parent.modelData.v ? parent.parent.modelData.v.libre / 100 : 0
                                    color: capsula.colorLibre(parent.parent.modelData.v)
                                }
                                Etiqueta {
                                    anchors.centerIn: parent
                                    text: parent.parent.modelData.v ? Math.round(parent.parent.modelData.v.libre) + "%" : "—"
                                    tam: 16
                                    peso: Font.Medium
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Etiqueta { text: modelData.titulo; peso: Font.Medium }
                                Etiqueta {
                                    text: modelData.v ? U.t("Te queda el " + Math.round(modelData.v.libre) + " %", Math.round(modelData.v.libre) + "% left") : U.t("Sin lectura todavía", "No reading yet")
                                    tam: Tema.textoChico
                                    color: Tema.sobreSuperficieVar
                                }
                                Etiqueta {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: capsula.ritmo(modelData.v)
                                    tam: Tema.textoChico
                                    color: modelData.v && modelData.v.agotado_en ? Tema.error : Tema.sobreSuperficieVar
                                }
                            }
                        }
                    }
                    Etiqueta {
                        visible: !!capsula.estado && !capsula.estado.limites.disponible
                        Layout.fillWidth: true
                        text: capsula.esClaude
                            ? U.t("Envía un mensaje en Claude Code y tus límites aparecerán aquí.", "Send a message in Claude Code and your limits will show up here.")
                            : U.t("Usa Codex y tus límites aparecerán aquí.", "Use Codex and your limits will show up here.")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    // cuenta con la que iniciaste sesión (nombre y plan, nunca el correo)
                    Etiqueta {
                        visible: !!(capsula.estado && capsula.estado.cuenta)
                        text: capsula.estado && capsula.estado.cuenta
                            ? [capsula.estado.cuenta.nombre, capsula.estado.cuenta.plan].filter(x => !!x).join(" · ") : ""
                        tam: Tema.textoChico
                        color: Tema.contorno
                    }
                }
            }

            // activar la ventana de 5 horas (solo Claude): mensaje propio, botón o a una hora fija
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: activar.implicitHeight + 28
                visible: capsula.esClaude
                ColumnLayout {
                    id: activar
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    spacing: 10

                    RowLayout {
                        spacing: 6
                        Icono { text: "bolt"; tam: 18; relleno: 1; color: capsula.v5 ? Tema.primario : Tema.terciario }
                        Etiqueta { text: U.t("Activar 5 horas", "Start 5-hour window"); peso: Font.Medium }
                        Item { Layout.fillWidth: true }
                        Etiqueta {
                            text: capsula.ocupado ? U.t("enviando…", "sending…")
                                : capsula.v5 && capsula.v5.reinicia ? U.t("abierta hasta ", "open until ") + U.hora(capsula.v5.reinicia)
                                : U.t("sin ventana abierta", "no open window")
                            tam: Tema.textoChico
                            color: capsula.ocupado ? Tema.terciario : Tema.sobreSuperficieVar
                        }
                    }

                    // campo de mensaje + enviar (vacío = solo activar)
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 20
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
                                enabled: !capsula.ocupado
                                Binding { target: capsula; property: "retener"; value: campo.activeFocus }
                                onAccepted: { capsula.enviar(text); text = ""; }
                                Keys.onEscapePressed: { text = ""; focus = false; }
                                Etiqueta {
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: !campo.text && !campo.activeFocus
                                    text: U.t("Escríbele a Claude…", "Message Claude…")
                                    color: Tema.contorno
                                }
                            }
                            Rectangle {
                                Layout.preferredWidth: 30
                                Layout.preferredHeight: 30
                                radius: 15
                                color: Tema.primario
                                opacity: capsula.ocupado ? 0.6 : 1
                                scale: presionEnviar.valor
                                Resorte { id: presionEnviar; objetivo: zonaEnviar.pressed ? 0.9 : 1; respuesta: zonaEnviar.pressed ? 0.1 : 0.3 }
                                Icono {
                                    anchors.centerIn: parent
                                    text: capsula.ocupado ? "progress_activity" : campo.text ? "send" : "bolt"
                                    tam: 17
                                    relleno: 1
                                    color: Tema.sobrePrimario
                                    RotationAnimation on rotation {
                                        running: capsula.ocupado
                                        from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                                        onRunningChanged: if (!running) parent.rotation = 0
                                    }
                                }
                                MouseArea {
                                    id: zonaEnviar
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: { capsula.enviar(campo.text); campo.text = ""; }
                                }
                            }
                        }
                    }
                    Etiqueta {
                        visible: !capsula.act || !capsula.act.ultimo
                        Layout.fillWidth: true
                        text: U.t("Vacío solo activa la ventana con un saludo a Haiku (cuesta casi nada).",
                                  "Empty just starts the window with a tiny Haiku greeting (costs almost nothing).")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.contorno
                    }

                    // último envío: tu mensaje y lo que respondió (o el error)
                    ColumnLayout {
                        readonly property var u: capsula.act ? capsula.act.ultimo : null
                        visible: !!u
                        Layout.fillWidth: true
                        spacing: 2
                        Etiqueta {
                            Layout.fillWidth: true
                            visible: !!(parent.u && parent.u.mensaje)
                            text: parent.u ? U.t("Tú: ", "You: ") + parent.u.mensaje : ""
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: !parent.u ? ""
                                : !parent.u.ok ? (parent.u.error || U.t("No hubo respuesta.", "No answer."))
                                : parent.u.respuesta ? parent.u.respuesta
                                : U.t("Ventana activada ", "Window started ") + U.hace(capsula.ahora - parent.u.t) + (parent.u.automatico ? U.t(" (sola)", " (automatic)") : "")
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            maximumLineCount: 6
                            color: parent.u && !parent.u.ok ? Tema.error : Tema.sobreSuperficie
                        }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Tema.contornoVar }

                    // programación
                    RowLayout {
                        spacing: 6
                        Icono { text: "schedule"; tam: 16; color: Tema.sobreSuperficieVar }
                        Etiqueta { text: U.t("Cada día a las", "Every day at"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                        SelectorHora {
                            hora: capsula.act ? capsula.act.hora : "06:00"
                            onCambiada: h => capsula.ajustar({ hora: h })
                        }
                        Item { Layout.fillWidth: true }
                        Interruptor {
                            activo: !!(capsula.act && capsula.act.programado)
                            onCambiado: v => capsula.ajustar({ programado: v })
                        }
                    }
                    RowLayout {
                        spacing: 6
                        Icono { text: "autorenew"; tam: 16; color: Tema.sobreSuperficieVar }
                        Etiqueta { text: U.t("Renovarla sola hasta las", "Keep renewing until"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                        SelectorHora {
                            hora: capsula.act ? capsula.act.hasta : "23:00"
                            onCambiada: h => capsula.ajustar({ hasta: h })
                        }
                        Item { Layout.fillWidth: true }
                        Interruptor {
                            activo: !!(capsula.act && capsula.act.mantener)
                            onCambiado: v => capsula.ajustar({ mantener: v })
                        }
                    }
                    Etiqueta {
                        visible: !!(capsula.act && (capsula.act.programado || capsula.act.mantener))
                        Layout.fillWidth: true
                        text: !capsula.act ? ""
                            : (capsula.act.programado && capsula.act.proximo ? U.t("Próxima activación: ", "Next start: ") + (capsula.act.proximo - capsula.ahora < 86400 && new Date(capsula.act.proximo * 1000).getDate() === new Date().getDate() ? U.t("hoy", "today") : U.t("mañana", "tomorrow")) + U.t(" a las ", " at ") + U.hora(capsula.act.proximo) + ". " : "")
                              + (capsula.act.mantener ? U.t("Al acabarse, abre otra hasta las ", "When it ends, opens another until ") + capsula.act.hasta + "." : "")
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.contorno
                    }
                }
            }

            // modelo en uso
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 68
                visible: capsula.modelo !== ""
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 14
                    spacing: 12
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 20
                        color: capsula.colorFamilia(capsula.familia)
                        Icono {
                            anchors.centerIn: parent
                            text: capsula.iconoFamilia(capsula.familia)
                            tam: 22
                            relleno: 1
                            color: Tema.sobrePrimario
                        }
                    }
                    ColumnLayout {
                        spacing: 1
                        Etiqueta { text: U.t("Modelo en uso", "Current model"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                        Etiqueta { text: capsula.modelo; tam: 17; peso: Font.Medium }
                    }
                    Item { Layout.fillWidth: true }
                    // reparto de hoy entre modelos
                    ColumnLayout {
                        spacing: 3
                        readonly property var lista: capsula.estado && capsula.estado.modelos_hoy ? capsula.estado.modelos_hoy.slice(0, 3) : []
                        readonly property real total: lista.reduce((a, m) => a + m.nuevos, 0) || 1
                        Etiqueta {
                            Layout.alignment: Qt.AlignRight
                            text: U.t("Hoy", "Today")
                            tam: 10
                            color: Tema.contorno
                        }
                        Repeater {
                            model: parent.lista
                            delegate: Etiqueta {
                                required property var modelData
                                Layout.alignment: Qt.AlignRight
                                text: modelData.modelo.split(" ")[0] + " " + Math.round(modelData.nuevos / parent.total * 100) + " %"
                                tam: Tema.textoChico
                                peso: Font.Medium
                                color: capsula.colorFamilia(modelData.modelo.split(" ")[0])
                            }
                        }
                    }
                }
            }

            // tokens de hoy
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 150
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 4
                    RowLayout {
                        Etiqueta { text: U.t("Tokens de hoy", "Tokens today"); tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                        Item { Layout.fillWidth: true }
                        Etiqueta {
                            text: capsula.estado ? (capsula.estado.ritmo_por_min ? U.corto(capsula.estado.ritmo_por_min) + "/min" : U.t("en pausa", "idle")) : ""
                            tam: Tema.textoChico
                            font.family: Tema.mono
                            color: capsula.trabajando ? Tema.terciario : Tema.sobreSuperficieVar
                        }
                    }
                    RowLayout {
                        spacing: 10
                        Etiqueta {
                            text: capsula.estado ? U.corto(capsula.estado.tokens.hoy.nuevos) : "—"
                            tam: 30
                            peso: Font.Medium
                        }
                        Etiqueta {
                            Layout.alignment: Qt.AlignBottom
                            Layout.bottomMargin: 5
                            text: capsula.estado ? capsula.estado.tokens.hoy.mensajes + U.t(" respuestas", " replies") : ""
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                    }
                    // última hora, por minuto
                    Row {
                        id: barras
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 2
                        readonly property var datos: capsula.estado ? capsula.estado.por_minuto : []
                        readonly property real maximo: Math.max(1, ...datos)
                        Repeater {
                            model: barras.datos
                            delegate: Rectangle {
                                required property var modelData
                                width: (barras.width - 59 * 2) / 60
                                height: modelData ? Math.max(3, barras.height * modelData / barras.maximo) : 2
                                anchors.bottom: parent.bottom
                                radius: 1.5
                                color: modelData ? Tema.primario : Tema.contenedorMax
                                Behavior on height { NumberAnimation { duration: 300 } }
                            }
                        }
                    }
                    Etiqueta { text: U.t("Última hora", "Last hour"); tam: 10; color: Tema.contorno }
                }
            }

            // modelos de IA para el asistente (API o locales)
            TarjetaModelos {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: implicitHeight
            }

            // última respuesta
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 60
                visible: !!capsula.ultima
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 14
                    spacing: 12
                    Rectangle {
                        Layout.preferredWidth: 36
                        Layout.preferredHeight: 36
                        radius: 18
                        color: capsula.trabajando ? Tema.primario : Tema.contSecundario
                        Icono {
                            anchors.centerIn: parent
                            text: capsula.trabajando ? "progress_activity" : "receipt_long"
                            tam: 20
                            color: capsula.trabajando ? Tema.sobrePrimario : Tema.sobreContSecundario
                            RotationAnimation on rotation {
                                running: capsula.trabajando
                                from: 0; to: 360; duration: 1200; loops: Animation.Infinite
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.ultima ? "+" + capsula.ultima.salida.toLocaleString(Qt.locale(), "f", 0) + U.t(" tokens de salida", " output tokens") : ""
                            peso: Font.Medium
                        }
                        Etiqueta {
                            Layout.fillWidth: true
                            text: capsula.ultima ? U.hace(capsula.ahora - capsula.ultima.t) + " · " + capsula.ultima.modelo + " · " + capsula.ultima.proyecto : ""
                            tam: Tema.textoChico
                            color: Tema.sobreSuperficieVar
                        }
                    }
                }
            }

            Boton {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 2
                texto: U.t("Abrir panel completo", "Open full panel")
                icono: "open_in_new"
                principal: true
                onPulsado: Quickshell.execDetached([(Quickshell.env("AKARI_RAIZ") || Quickshell.shellDir + "/..") + "/bin/akari", "abrir"])
            }
            Item { Layout.preferredHeight: 8 }
        }
    }
}
