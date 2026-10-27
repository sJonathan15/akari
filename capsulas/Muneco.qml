import QtQuick
import "utiles.js" as U

// El muñequito del asistente (pixel art, ver U.pixelesMuneco): un farolito con llama.
Canvas {
    id: muneco
    property string estado: "pausa"
    property int paso: 0
    readonly property int celda: Math.max(1, Math.floor(Math.min(width / 13, height / 14)))
    implicitWidth: 13 * 3
    implicitHeight: 14 * 3
    renderStrategy: Canvas.Cooperative

    readonly property var colores: ({
        o: Tema.mezcla(Tema.superficie, Tema.primario, 0.15), b: Tema.primario, l: Qt.lighter(Tema.primario, 1.35),
        e: Tema.sobrePrimario, c: Tema.alfa(Tema.terciario, 0.85), m: Tema.sobrePrimario,
        f: Tema.terciario, F: Qt.lighter(Tema.terciario, 1.3)
    })

    Timer {
        interval: 160
        repeat: true
        running: muneco.visible && !Tema.movimientoReducido
        onTriggered: muneco.paso++
    }
    onPasoChanged: requestPaint()
    onEstadoChanged: requestPaint()
    onColoresChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d");
        ctx.clearRect(0, 0, width, height);
        const c = celda, x0 = Math.floor((width - 13 * c) / 2), y0 = Math.floor((height - 14 * c) / 2);
        for (const [x, y, letra] of U.pixelesMuneco(estado, paso)) {
            ctx.fillStyle = colores[letra];
            ctx.fillRect(x0 + x * c, y0 + y * c, c, c);
        }
    }
}
