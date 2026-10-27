import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Pieza «Dispositivos» del grupo Equipo: batería y estado de ratón, teclado, audífonos y celular.
Pieza {
    id: capsula
    clave: "dispositivos"
    titulo: U.t("Dispositivos", "Devices")
    icono: "devices"
    anchoChip: 254
    anchoAbierto: 384

    property var estado: Datos.disp
    property var dispositivos: estado ? estado.dispositivos : []
    // AKARI_DISPOSITIVO=<id> elige con cuál empezar (útil para revisar los modelos)
    property string elegido: Quickshell.env("AKARI_DISPOSITIVO") || ""
    property var actual: {
        for (const d of dispositivos) if (d.id === elegido) return d;
        return dispositivos.length ? dispositivos[0] : null;
    }
    property string respuesta: ""

    function colorNivel(n) {
        return ({ ok: Tema.exito, medio: Tema.terciario, bajo: Tema.error, cable: Tema.primario, nada: Tema.contorno })[n] || Tema.contorno;
    }
    function hayAlerta() {
        for (const d of dispositivos) if (U.nivel(d) === "bajo" && !d.cargando) return true;
        return false;
    }

    // ------------------------------------------------------------- cerrada
    resumen: Component {
        Item {
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 4

                Repeater {
                    // en la cápsula cerrada, los 4 primeros (el servicio pone primero los conectados)
                    model: capsula.dispositivos.slice(0, 4)
                    delegate: RowLayout {
                        required property var modelData
                        readonly property string nivel: U.nivel(modelData)
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 4
                        Icono {
                            text: U.ICONOS[modelData.tipo]
                            tam: 17
                            relleno: modelData.conectado ? 1 : 0
                            color: capsula.colorNivel(parent.nivel)
                            SequentialAnimation on opacity {
                                running: parent.nivel === "bajo" && !parent.modelData.cargando
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 700 }
                                NumberAnimation { to: 1; duration: 700 }
                            }
                        }
                        Etiqueta {
                            text: U.textoCorto(modelData) + (modelData.cargando ? "⚡" : "")
                            tam: Tema.textoChico
                            peso: Font.Medium
                            font.family: Tema.mono
                            color: parent.nivel === "nada" ? Tema.contorno : Tema.sobreSuperficieVar
                        }
                    }
                }
                Etiqueta {
                    visible: !Datos.enLinea || capsula.dispositivos.length === 0
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: !Datos.enLinea ? U.t("Iniciando akari…", "Starting akari…") : U.t("Sin periféricos todavía", "No devices yet")
                    tam: Tema.textoChico
                    color: Tema.sobreSuperficieVar
                }
            }
            Rectangle {   // aviso de batería baja: línea roja bajo la cápsula
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width * 0.4
                height: 2
                radius: 1
                color: Tema.error
                visible: capsula.hayAlerta() && !capsula.abierta
            }
        }
    }

    // ------------------------------------------------------------ abierta
    cuerpo: Component {
        ColumnLayout {
            spacing: 8

            // escenario 3D del dispositivo elegido
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: 214
                color: Tema.contenedor

                Rectangle {   // resplandor suave del color del tema detrás del modelo
                    anchors.centerIn: visor
                    width: 180; height: 180; radius: 90
                    color: Tema.alfa(Tema.primario, capsula.actual && capsula.actual.conectado ? 0.10 : 0.03)
                }
                Visor3D {
                    id: visor
                    anchors.fill: parent
                    anchors.margins: 6
                    modelo: capsula.actual && capsula.actual.modelo3d ? capsula.actual.modelo3d : ""
                    tipo: capsula.actual ? capsula.actual.tipo : "otro"
                    // AKARI_ENCENDIDO=1 muestra el modelo con brillo completo (para revisarlo)
                    encendido: !!(capsula.actual && capsula.actual.conectado) || Quickshell.env("AKARI_ENCENDIDO") === "1"
                    visible: capsula.abierta
                }
                ColumnLayout {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 16
                    spacing: 2
                    Etiqueta {
                        text: capsula.actual ? capsula.actual.tipo_nombre : ""
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    Etiqueta {
                        text: capsula.actual ? capsula.actual.nombre : ""
                        tam: Tema.textoGrande
                        peso: Font.Medium
                        Layout.maximumWidth: 250
                    }
                }
                Rectangle {   // chip de conexión
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 14
                    height: 28
                    width: filaChip.implicitWidth + 22
                    radius: 14
                    color: capsula.actual && capsula.actual.conectado ? Tema.contSecundario : Tema.contenedorAlto
                    Row {
                        id: filaChip
                        anchors.centerIn: parent
                        spacing: 6
                        Icono {
                            text: !capsula.actual || !capsula.actual.conectado ? "link_off"
                                : capsula.actual.conexion === "Bluetooth" ? "bluetooth"
                                : (capsula.actual.conexion || "").indexOf("Wi-Fi") >= 0 ? "wifi"
                                : (capsula.actual.conexion || "").indexOf("USB") >= 0 ? "usb" : "settings_input_antenna"
                            tam: 16
                            color: Tema.sobreContSecundario
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Etiqueta {
                            text: capsula.actual && capsula.actual.conectado ? capsula.actual.conexion : U.t("Desconectado", "Disconnected")
                            tam: Tema.textoChico
                            color: Tema.sobreContSecundario
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
                Item {   // anillo de batería
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 14
                    width: 64; height: 64
                    readonly property string nivel: U.nivel(capsula.actual)
                    Anillo {
                        anchors.fill: parent
                        grosor: 6
                        valor: !capsula.actual || !capsula.actual.conectado ? 0
                            : capsula.actual.bateria !== null ? capsula.actual.bateria / 100 : 1
                        color: capsula.colorNivel(parent.nivel)
                    }
                    Column {
                        anchors.centerIn: parent
                        Etiqueta {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: !!capsula.actual && capsula.actual.conectado && capsula.actual.bateria !== null
                            text: capsula.actual && capsula.actual.bateria !== null ? capsula.actual.bateria + "%" : ""
                            tam: 15
                            peso: Font.Medium
                        }
                        Icono {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: !capsula.actual || !capsula.actual.conectado || capsula.actual.bateria === null || capsula.actual.cargando
                            text: !capsula.actual || !capsula.actual.conectado ? "power_off"
                                : capsula.actual.cargando ? "bolt" : "power"
                            tam: capsula.actual && capsula.actual.cargando ? 14 : 22
                            relleno: 1
                            color: capsula.colorNivel(parent.parent.nivel)
                        }
                    }
                }
            }

            // lista de dispositivos
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: lista.implicitHeight + 12
                Column {
                    id: lista
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 2
                    Repeater {
                        model: capsula.dispositivos
                        delegate: Rectangle {
                            id: filaDisp
                            required property var modelData
                            readonly property bool esElegido: modelData.id === capsula.elegido
                            readonly property string nivel: U.nivel(modelData)
                            width: lista.width
                            height: 52
                            radius: Tema.redondeo + 2
                            color: zonaFila.pressed ? Tema.contenedorMax
                                : esElegido ? Tema.contenedorAlto
                                : zonaFila.containsMouse ? Tema.alfa(Tema.contenedorAlto, 0.6) : "transparent"
                            Behavior on color { enabled: !zonaFila.pressed; ColorAnimation { duration: 150 } }

                            Rectangle {
                                id: circulo
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: 36; height: 36; radius: 18
                                color: filaDisp.esElegido ? Tema.primario : Tema.contSecundario
                                Icono {
                                    anchors.centerIn: parent
                                    text: U.ICONOS[filaDisp.modelData.tipo]
                                    tam: 20
                                    relleno: filaDisp.esElegido ? 1 : 0
                                    color: filaDisp.esElegido ? Tema.sobrePrimario : Tema.sobreContSecundario
                                }
                            }
                            Column {
                                anchors.left: circulo.right
                                anchors.leftMargin: 12
                                anchors.right: derecha.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 1
                                Etiqueta {
                                    width: parent.width
                                    text: filaDisp.modelData.nombre
                                    peso: Font.Medium
                                }
                                Etiqueta {
                                    width: parent.width
                                    text: filaDisp.modelData.conectado
                                        ? filaDisp.modelData.conexion + (filaDisp.modelData.cargando ? U.t(" · cargando", " · charging") : "")
                                        : U.t("Desconectado", "Disconnected")
                                    tam: Tema.textoChico
                                    color: Tema.sobreSuperficieVar
                                }
                            }
                            Column {
                                id: derecha
                                anchors.right: parent.right
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 4
                                Etiqueta {
                                    anchors.right: parent.right
                                    text: filaDisp.modelData.conectado && filaDisp.modelData.bateria !== null
                                        ? filaDisp.modelData.bateria + " %"
                                        : filaDisp.modelData.conectado ? U.t("Sin dato", "No data") : "—"
                                    tam: Tema.textoChico
                                    peso: Font.Medium
                                    color: capsula.colorNivel(filaDisp.nivel)
                                }
                                Rectangle {
                                    anchors.right: parent.right
                                    visible: filaDisp.modelData.conectado && filaDisp.modelData.bateria !== null
                                    width: 44; height: 4; radius: 2
                                    color: Tema.contenedorMax
                                    Rectangle {
                                        width: parent.width * Math.max(0, Math.min(1, (filaDisp.modelData.bateria || 0) / 100))
                                        height: parent.height
                                        radius: 2
                                        color: capsula.colorNivel(filaDisp.nivel)
                                    }
                                }
                            }
                            MouseArea {
                                id: zonaFila
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onPressed: { capsula.elegido = filaDisp.modelData.id; capsula.respuesta = ""; }
                            }
                        }
                    }
                }
            }

            // detalles y acciones del elegido
            Tarjeta {
                Layout.fillWidth: true
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                Layout.preferredHeight: detalles.implicitHeight + 28
                visible: !!capsula.actual
                ColumnLayout {
                    id: detalles
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    spacing: 6

                    Repeater {
                        model: capsula.actual ? capsula.actual.detalles.slice(0, 4) : []
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Etiqueta { text: modelData[0]; tam: Tema.textoChico; color: Tema.sobreSuperficieVar }
                            Item { Layout.fillWidth: true }
                            Etiqueta { text: modelData[1]; tam: Tema.textoChico; peso: Font.Medium; Layout.maximumWidth: 200; horizontalAlignment: Text.AlignRight }
                        }
                    }
                    Etiqueta {
                        visible: !!(capsula.actual && capsula.actual.horas_restantes)
                        text: capsula.actual && capsula.actual.horas_restantes ? U.t("A este ritmo quedan unas ", "At this rate, about ") + capsula.actual.horas_restantes + U.t(" h", " h left") : ""
                        tam: Tema.textoChico
                        color: Tema.primario
                    }
                    Etiqueta {
                        visible: !!(capsula.actual && capsula.actual.ayuda)
                        Layout.fillWidth: true
                        text: capsula.actual && capsula.actual.ayuda ? capsula.actual.ayuda : ""
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 8
                        visible: botones.count > 0
                        Repeater {
                            id: botones
                            model: capsula.actual ? capsula.actual.acciones : []
                            delegate: Boton {
                                required property var modelData
                                required property int index
                                texto: modelData.etiqueta
                                icono: ({ conectar: "bluetooth_connected", desconectar: "bluetooth_disabled", sonar: "ring_volume" })[modelData.id] || ""
                                principal: index === 0
                                onPulsado: {
                                    ocupado = true;
                                    capsula.respuesta = modelData.id === "conectar" ? U.t("Conectando…", "Connecting…") : U.t("Un momento…", "One moment…");
                                    Datos.enviar("/api/dispositivos", { id: capsula.actual.id, accion: modelData.id },
                                                 r => { ocupado = false; capsula.respuesta = r.mensaje; });
                                }
                            }
                        }
                    }
                    // ¿se detectó mal? cambiar el tipo (ratón → teclado → …) u ocultarlo
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        Repeater {
                            model: [
                                { id: "tipo", icono: "swap_horiz", texto: U.t("Cambiar tipo", "Change type") },
                                { id: "ocultar", icono: "visibility_off", texto: U.t("Ocultar", "Hide") }
                            ]
                            delegate: Item {
                                id: ajuste
                                required property var modelData
                                implicitWidth: filaAjuste.implicitWidth
                                implicitHeight: 20
                                opacity: zonaAjuste.containsMouse ? 1 : 0.7
                                Row {
                                    id: filaAjuste
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4
                                    Icono { text: ajuste.modelData.icono; tam: 14; color: Tema.sobreSuperficieVar; anchors.verticalCenter: parent.verticalCenter }
                                    Etiqueta { text: ajuste.modelData.texto; tam: Tema.textoChico; color: Tema.sobreSuperficieVar; anchors.verticalCenter: parent.verticalCenter }
                                }
                                MouseArea {
                                    id: zonaAjuste
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Datos.enviar("/api/dispositivos", { id: capsula.actual.id, accion: ajuste.modelData.id },
                                                            r => capsula.respuesta = r.mensaje)
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    Etiqueta {
                        visible: capsula.respuesta !== ""
                        text: capsula.respuesta
                        tam: Tema.textoChico
                        color: Tema.sobreSuperficieVar
                    }
                }
            }

            // batería de la laptop
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 22
                Layout.rightMargin: 22
                visible: !!(capsula.estado && capsula.estado.equipo)
                Icono {
                    text: capsula.estado && capsula.estado.equipo && capsula.estado.equipo.estado === "cargando" ? "battery_charging_full" : "laptop"
                    tam: 16
                    color: Tema.sobreSuperficieVar
                }
                Etiqueta {
                    text: capsula.estado && capsula.estado.equipo
                        ? U.t("Equipo ", "Laptop ") + capsula.estado.equipo.bateria + " %"
                          + ({ cargando: U.t(" · cargando", " · charging"), descargando: U.t(" · con batería", " · on battery"),
                               llena: U.t(" · llena", " · full") }[capsula.estado.equipo.estado] || "") : ""
                    tam: Tema.textoChico
                    color: Tema.sobreSuperficieVar
                }
                Item { Layout.fillWidth: true }
                Etiqueta {
                    text: capsula.estado && capsula.estado.app_celular ? capsula.estado.app_celular + U.t(" activo", " on") : ""
                    tam: Tema.textoChico
                    color: Tema.contorno
                }
            }
            Item { Layout.preferredHeight: 6 }
        }
    }
}
