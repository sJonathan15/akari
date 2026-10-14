import QtQuick

// Resorte con los dos parámetros que usa Apple: amortiguación (1 = sin rebote)
// y respuesta (segundos hasta llegar, más o menos). Al cambiar el objetivo a
// mitad de camino conserva la posición y la velocidad actuales, así que se
// puede interrumpir sin saltos.
Item {
    id: resorte

    property real objetivo: 0
    property real valor: 0
    property real velocidad: 0
    property real respuesta: 0.4
    property real amortiguacion: 1.0
    readonly property bool enMovimiento: animacion.running

    function saltar(v) {
        animacion.stop();
        valor = v;
        velocidad = 0;
    }

    Component.onCompleted: valor = objetivo
    onObjetivoChanged: {
        if (Tema.movimientoReducido) { saltar(objetivo); return; }
        animacion.start();
    }

    FrameAnimation {
        id: animacion
        onTriggered: {
            const dt = Math.min(frameTime, 1 / 30);
            const k = Math.pow(2 * Math.PI / resorte.respuesta, 2);
            const c = 4 * Math.PI * resorte.amortiguacion / resorte.respuesta;
            let x = resorte.valor, v = resorte.velocidad;
            const pasos = 4, h = dt / pasos;
            for (let i = 0; i < pasos; i++) {
                const a = -k * (x - resorte.objetivo) - c * v;
                v += a * h;
                x += v * h;
            }
            if (Math.abs(x - resorte.objetivo) < 0.05 && Math.abs(v) < 0.5) {
                resorte.valor = resorte.objetivo;
                resorte.velocidad = 0;
                stop();
                return;
            }
            resorte.valor = x;
            resorte.velocidad = v;
        }
    }
}
