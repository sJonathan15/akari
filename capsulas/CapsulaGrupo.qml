import QtQuick
import "utiles.js" as U

// Un grupo de piezas en una sola cápsula (ver AGENTS.md): cerrada es una píldora con el chip de cada
// pieza; al pasar el ratón por un chip se abre en esa pieza y, abierta, un clic en otro chip cambia
// de pieza (clic en el de la pieza abierta la fija, como siempre). Si queda una sola pieza visible
// se ve sin pestañas. Las piezas ocultas en capsulas.json no aparecen.
//
//   CapsulaGrupo { nombre: "ia"; lado: "derecha"; ocultas: raiz.ocultas; PiezaUso {} PiezaModelos {} }
Capsula {
    id: grupo

    default property list<Pieza> todas
    property var ocultas: []
    readonly property var piezas: {
        const r = [];
        for (let i = 0; i < todas.length; i++)
            if (!ocultas.includes(todas[i].clave)) r.push(todas[i]);
        return r;
    }
    property string actual: ""
    readonly property var pieza: piezas.find(p => p.clave === actual) || piezas[0] || null
    readonly property bool conPestanas: piezas.length > 1
    readonly property int espacioChips: 4
    property var chips: ({})                // clave -> chip dibujado (para saber cuál se tocó)

    function elegir(clave) { actual = clave; }
    function piezaPara(url) { return piezas.find(p => p.acepta(url)) || null; }

    anchoCerrado: piezas.reduce((suma, p) => suma + p.anchoChip, 0) + espacioChips * Math.max(0, piezas.length - 1) + 20
    anchoAbierto: pieza ? pieza.anchoAbierto : 380
    pideTeclado: piezas.some(p => p.pideTeclado)
    retener: piezas.some(p => p.retener)
    aceptaArchivos: piezas.some(p => p.aceptaArchivos)

    Component.onCompleted: { for (let i = 0; i < todas.length; i++) todas[i].grupo = grupo; }

    // al arrastrar un archivo encima, se abre en la pieza que se ocupa de él
    onArchivoEntro: urls => {
        const p = urls.length ? piezaPara(urls[0]) : null;
        if (p) actual = p.clave;
    }
    // y al soltarlo, cada archivo va a su pieza
    onSoltaron: urls => {
        const reparto = new Map();
        for (const u of urls) {
            const p = piezaPara(u);
            if (!p) continue;
            if (!reparto.has(p)) reparto.set(p, []);
            reparto.get(p).push(u);
        }
        let primera = true;
        for (const [p, lista] of reparto) {
            if (primera) actual = p.clave;
            primera = false;
            p.soltaron(lista);
        }
    }

    // abierta, un clic en el chip de otra pieza cambia a ella (no fija ni suelta la cápsula)
    tocarCabecera: punto => {
        if (!desplegada || !conPestanas) return false;
        for (const clave in chips) {
            const chip = chips[clave];
            if (!chip) continue;
            const local = chip.mapFromItem(null, punto.x, punto.y);
            if (chip.contains(local) && clave !== (pieza ? pieza.clave : "")) {
                actual = clave;
                return true;
            }
        }
        return false;
    }

    cabecera: Component {
        Item {
            Row {
                anchors.centerIn: parent
                spacing: grupo.espacioChips
                Repeater {
                    model: grupo.piezas
                    delegate: Item {
                        id: chip
                        required property var modelData
                        readonly property bool elegida: grupo.pieza === modelData
                        width: modelData.anchoChip
                        height: grupo.altoCerrado
                        Component.onCompleted: { const c = Object.assign({}, grupo.chips); c[modelData.clave] = chip; grupo.chips = c; }
                        Component.onDestruction: { const c = Object.assign({}, grupo.chips); if (c[modelData.clave] === chip) delete c[modelData.clave]; grupo.chips = c; }

                        // la pestaña elegida (solo abierta y con más de una pieza)
                        Rectangle {
                            anchors.fill: parent
                            anchors.topMargin: 5
                            anchors.bottomMargin: 5
                            radius: height / 2
                            color: Tema.alfa(Tema.primario, chip.elegida ? 0.16 : 0)
                            border.width: chip.elegida ? 0 : 1
                            border.color: Tema.alfa(Tema.contornoVar, sobreChip.hovered && grupo.desplegada ? 1 : 0)
                            opacity: grupo.conPestanas && grupo.desplegada ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 150 } }
                        }
                        Loader {
                            anchors.fill: parent
                            sourceComponent: chip.modelData.resumen
                        }
                        // cerrada, el chip bajo el puntero decide en qué pieza se abre
                        HoverHandler {
                            id: sobreChip
                            onHoveredChanged: if (hovered && !grupo.abierta) grupo.actual = chip.modelData.clave
                        }
                    }
                }
            }
        }
    }

    cuerpo: Component {
        Loader {
            sourceComponent: grupo.pieza ? grupo.pieza.cuerpo : null
            height: item ? item.implicitHeight : 0
        }
    }
}
