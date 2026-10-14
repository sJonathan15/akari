pragma Singleton
import QtQuick
import Quickshell

// Estado del servicio de akari (127.0.0.1:47830), pedido cada 2 s.
Singleton {
    id: datos

    readonly property string base: "http://127.0.0.1:47830"
    property var estado: null
    property bool enLinea: false
    readonly property var ia: estado ? estado.ia : null
    readonly property var disp: estado ? estado.dispositivos : null
    readonly property var hab: estado ? estado.habilidades : null

    function actualizar() {
        const x = new XMLHttpRequest();
        x.onreadystatechange = () => {
            if (x.readyState !== XMLHttpRequest.DONE) return;
            let r = null;
            if (x.status === 200) { try { r = JSON.parse(x.responseText); } catch (e) {} }
            datos.enLinea = !!r;
            if (r) datos.estado = r;
        };
        x.open("GET", base + "/api/estado");
        x.send();
    }

    // POST con JSON (el servicio rechaza todo lo demás)
    function enviar(ruta, cuerpo, listo) {
        const x = new XMLHttpRequest();
        x.onreadystatechange = () => {
            if (x.readyState !== XMLHttpRequest.DONE) return;
            let r = { ok: false, mensaje: "akari no respondió / akari did not answer" };
            if (x.status === 200) { try { r = JSON.parse(x.responseText); } catch (e) {} }
            if (listo) listo(r);
            actualizar();
        };
        x.open("POST", base + ruta);
        x.setRequestHeader("Content-Type", "application/json");
        x.send(JSON.stringify(cuerpo));
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: datos.actualizar()
    }
}
