import QtQuick
import QtQuick.Layouts
import Quickshell
import "utiles.js" as U

// Modelos de IA para el asistente: qué se está usando y, si no hay nada, el modelo local que
// recomienda akari para este equipo con su botón. Las claves de API se escriben en el panel.
Tarjeta {
    id: tarjeta
    readonly property var m: Datos.modelos
    readonly property var descarga: m ? m.ollama.descarga : null
    readonly property bool bajando: !!descarga && !descarga.error && descarga.pct < 100
    // el modelo de texto recomendado para este equipo (o el de visión si falta ése)
    readonly property var sugerido: {
        if (!m) return null;
        const r = m.recomendados;
        const falta = (tipo) => r.find(x => x.sugerido === tipo && !x.en_uso);
        return !m.listo ? falta("texto") : !m.vision_lista && m.modo === "local" ? falta("vision") : null;
    }
    property string respuesta: ""

    implicitHeight: col.implicitHeight + 28
    visible: !!m

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 10

        RowLayout {
            spacing: 12
            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                radius: 18
                color: tarjeta.m && tarjeta.m.listo ? Tema.primario : Tema.contSecundario
                Icono {
                    id: iconoModelos
                    anchors.centerIn: parent
                    text: tarjeta.bajando ? "progress_activity" : tarjeta.m && tarjeta.m.listo ? "psychology" : "key"
                    tam: 20
                    color: tarjeta.m && tarjeta.m.listo ? Tema.sobrePrimario : Tema.sobreContSecundario
                    RotationAnimation on rotation {
                        running: tarjeta.bajando
                        from: 0; to: 360; duration: 1200; loops: Animation.Infinite
                        onRunningChanged: if (!running) iconoModelos.rotation = 0
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Etiqueta {
                    Layout.fillWidth: true
                    text: U.t("Modelos de IA", "AI models")
                    peso: Font.Medium
                }
                Etiqueta {
                    Layout.fillWidth: true
                    text: !tarjeta.m ? ""
                        : tarjeta.bajando ? U.t("Descargando ", "Downloading ") + tarjeta.descarga.modelo + " · " + tarjeta.descarga.pct + " %"
                        : tarjeta.m.listo ? (tarjeta.m.modo === "local" ? (tarjeta.m.local.texto || tarjeta.m.local.vision) + U.t(" · en tu equipo", " · local") : tarjeta.m.modelo)
                        : tarjeta.m.motivo
                    tam: Tema.textoChico
                    color: tarjeta.m && !tarjeta.m.listo ? Tema.terciario : Tema.sobreSuperficieVar
                }
            }
        }

        // recomendado para este equipo (gratis, con Ollama)
        Etiqueta {
            Layout.fillWidth: true
            visible: !!tarjeta.sugerido && !tarjeta.bajando
            text: tarjeta.sugerido ? U.t("Para tu equipo te recomiendo ", "For your computer I recommend ") + tarjeta.sugerido.id + ": " + tarjeta.sugerido.nota : ""
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: Tema.textoChico
            color: Tema.sobreSuperficieVar
        }
        Etiqueta {
            Layout.fillWidth: true
            visible: tarjeta.respuesta !== "" || !!(tarjeta.descarga && tarjeta.descarga.error)
            text: tarjeta.respuesta || (tarjeta.descarga && tarjeta.descarga.error ? tarjeta.descarga.error : "")
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            tam: Tema.textoChico
            color: Tema.error
        }

        RowLayout {
            spacing: 8
            Boton {
                visible: !!tarjeta.sugerido && !tarjeta.bajando && !!tarjeta.m && tarjeta.m.ollama.estado !== "no_instalado"
                principal: true
                icono: tarjeta.sugerido && tarjeta.sugerido.instalado ? "check" : "download"
                texto: !tarjeta.sugerido ? "" : tarjeta.sugerido.instalado ? U.t("Usar", "Use")
                    : U.t("Descargar · ", "Download · ") + tarjeta.sugerido.gb + " GB"
                onPulsado: {
                    const s = tarjeta.sugerido;
                    tarjeta.respuesta = "";
                    Datos.enviar("/api/modelos", s.instalado
                        ? { accion: "usar", modo: "local", modelo: s.id, tipo: s.vision ? "vision" : "texto" }
                        : { accion: "descargar", modelo: s.id, usar: true }, r => tarjeta.respuesta = r.ok ? "" : (r.mensaje || ""));
                }
            }
            Boton {
                visible: !!tarjeta.m && !tarjeta.m.listo && tarjeta.m.ollama.estado === "no_instalado"
                principal: true
                icono: "download"
                texto: U.t("Instalar Ollama", "Install Ollama")
                onPulsado: Datos.enviar("/api/modelos", { accion: "instalar_ollama" }, r => tarjeta.respuesta = r.ok ? "" : (r.mensaje || ""))
            }
            Boton {
                visible: !!tarjeta.m && !tarjeta.m.listo && tarjeta.m.ollama.estado === "apagado"
                principal: true
                icono: "power_settings_new"
                texto: U.t("Encender Ollama", "Start Ollama")
                onPulsado: Datos.enviar("/api/modelos", { accion: "arrancar_ollama" })
            }
            // claves de API, otros modelos y la prueba: en el panel
            Boton {
                icono: "tune"
                texto: tarjeta.m && tarjeta.m.listo ? U.t("Cambiar", "Change") : U.t("Usar una API", "Use an API")
                onPulsado: Quickshell.execDetached([(Quickshell.env("AKARI_RAIZ") || Quickshell.shellDir + "/..") + "/bin/akari", "abrir"])
            }
        }
    }
}
