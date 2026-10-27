import QtQuick
import Quickshell
import Quickshell.Wayland

// Cápsula de akari: una capa del escritorio (layer-shell), así que no aparece en
// el dock ni en Alt+Tab. Por defecto cuelga del borde superior, cerca del centro;
// se arrastra desde la cabecera a cualquier lugar (se recuerda en Posiciones) y
// doble clic la devuelve a su sitio.
//
// Dos formas:
//  * horizontal (arriba, abajo o en medio): se despliega hacia donde hay espacio
//    (cerca de un borde lateral, hacia el otro lado; en la mitad de abajo, hacia arriba);
//  * vertical: soltada a menos de 40 px del borde izquierdo o derecho se pega a él
//    como pestaña vertical y se despliega de lado, como un panel lateral.
// Si el contenido no cabe, se desplaza con la rueda.
PanelWindow {
    id: ventana

    property string nombre: ""              // clave para recordar la posición
    property string lado: "derecha"        // de qué lado del centro va por defecto
    property int hueco: 8                   // distancia al centro de la pantalla
    property int anchoCerrado: 250          // largo de la cápsula cerrada
    property int anchoAbierto: 380
    property int altoCerrado: 38            // grosor de la cápsula cerrada
    property int altoMaximo: 640
    // AKARI_ABIERTA=1 las deja abiertas al iniciar (para revisar el diseño)
    property bool abierta: Quickshell.env("AKARI_ABIERTA") === "1"
    property bool fijada: false             // clic en la cabecera la deja abierta
    property bool moviendo: false           // se está arrastrando
    property bool pideTeclado: false        // tiene campos de texto: acepta el teclado al hacer clic
    property bool retener: false            // no cerrarse aunque el puntero salga (p. ej. escribiendo)
    property bool aceptaArchivos: false     // se le pueden soltar archivos (se abre al arrastrar encima)
    property bool archivoEncima: false
    signal soltaron(var urls)               // ["file:///…", …]
    signal archivoEntro(var urls)           // al empezar a arrastrar encima (para elegir dónde abrirse)
    // clic en la cabecera: si esta función (punto en la escena) dice que lo atendió, no se fija/suelta
    property var tocarCabecera: null
    property Component cabecera
    property Component cuerpo
    readonly property int altoCuerpo: cargaCuerpo.item ? cargaCuerpo.item.implicitHeight : 0
    readonly property bool desplegada: abierta && !moviendo
    readonly property int margenBorde: 40   // a esta distancia de un lado se vuelve vertical

    // AKARI_PANTALLA=<nombre> (p. ej. eDP-1, DP-2) elige la pantalla; si no, la primera
    function pantallaPrincipal() {
        const lista = Quickshell.screens;
        const elegida = Quickshell.env("AKARI_PANTALLA");
        for (let i = 0; i < lista.length; i++)
            if (elegida && lista[i].name === elegida) return lista[i];
        return lista[0];
    }
    function limitar(v, min, max) { return Math.max(min, Math.min(max, v)); }

    // ------------------------------------------------ posición y forma
    // (cx, cy) = esquina superior izquierda de la cápsula cerrada, en la pantalla
    readonly property real xFabrica: lado === "derecha"
        ? screen.width / 2 + hueco
        : screen.width / 2 - hueco - anchoCerrado
    readonly property var guardada: nombre ? Posiciones.de(nombre) : null
    property real cx: guardada ? guardada.x : xFabrica
    property real cy: guardada ? guardada.y : 0
    property string borde: guardada && guardada.borde ? guardada.borde : ""
    readonly property bool vertical: borde !== ""
    readonly property bool bordeIzq: borde === "izquierda"
    // tamaño de la cápsula cerrada según la forma
    readonly property int largoV: Math.max(anchoCerrado, 156)   // largo de la pestaña vertical
    readonly property int wC: vertical ? altoCerrado : anchoCerrado
    readonly property int hC: vertical ? largoV : altoCerrado

    function volverAFabrica() {
        Posiciones.guardar(nombre, null);
        cx = Qt.binding(() => ventana.guardada ? ventana.guardada.x : ventana.xFabrica);
        cy = Qt.binding(() => ventana.guardada ? ventana.guardada.y : 0);
        borde = Qt.binding(() => ventana.guardada && ventana.guardada.borde ? ventana.guardada.borde : "");
    }
    // al soltar: pegada a un lado → pestaña vertical; si no → horizontal
    function soltar() {
        const w = screen.width, h = screen.height;
        if (cx <= margenBorde) { borde = "izquierda"; cx = 0; }
        else if (cx + wC >= w - margenBorde) { borde = "derecha"; cx = w - altoCerrado; }
        else { borde = ""; cx = limitar(cx, 0, w - anchoCerrado); }
        cy = limitar(cy, 0, h - hC);
        Posiciones.guardar(nombre, cx, cy, borde);
    }

    // ------------------------------------------------ hacia dónde se despliega (horizontal)
    // cerca de un borde (200 px) abre hacia el otro lado; en medio, hacia su lado de
    // siempre; y si no cabe, hacia donde quepa
    function calcularDerecha() {
        const w = screen.width, margen = 200;
        let derecha = cx < margen ? true : w - (cx + anchoCerrado) < margen ? false : lado === "derecha";
        if (derecha && cx + anchoAbierto > w) derecha = false;
        if (!derecha && cx + anchoCerrado - anchoAbierto < 0) derecha = true;
        return derecha;
    }
    readonly property bool haciaDerecha: calcularDerecha()
    readonly property bool haciaArriba: cy + altoCerrado / 2 > screen.height / 2
    readonly property int altoDisponible: Math.max(altoCerrado, Math.min(altoMaximo,
        Math.round(haciaArriba ? cy + altoCerrado : screen.height - cy)))
    readonly property int altoAbiertoH: Math.min(altoDisponible, altoCerrado + altoCuerpo)

    // ------------------------------------------------ panel lateral (vertical)
    readonly property int altoPanelV: Math.min(screen.height, Math.max(largoV, altoCuerpo + 20))
    readonly property int anchoPanelV: altoCerrado + anchoAbierto
    readonly property int topPanelV: limitar(Math.round(cy + largoV / 2 - altoPanelV / 2), 0, screen.height - altoPanelV)

    readonly property bool pegadaArriba: !vertical && cy <= 0
    readonly property bool pegadaAbajo: !vertical && cy + altoCerrado >= screen.height
    // sobre un dock o barra inferior: capa Overlay para no quedar detrás
    readonly property bool sobreDock: !vertical && cy + altoCerrado > screen.height - 64

    // geometría de la ventana: mientras se arrastra es justo la cápsula cerrada (así se
    // mueve 1:1 con el puntero); si no, el espacio que necesita al desplegarse
    screen: pantallaPrincipal()
    anchors { top: true; left: true }
    margins.left: Math.round(moviendo ? cx
        : vertical ? (bordeIzq ? 0 : screen.width - anchoPanelV)
        : haciaDerecha ? cx : cx + anchoCerrado - anchoAbierto)
    margins.top: Math.round(moviendo ? cy
        : vertical ? topPanelV
        : haciaArriba ? cy + altoCerrado - altoDisponible : cy)
    implicitWidth: moviendo ? wC : vertical ? anchoPanelV : anchoAbierto
    implicitHeight: moviendo ? hC : vertical ? altoPanelV : altoDisponible
    // respeta las barras de otros paneles (Waybar, la barra de GNOME/KDE…) sin reservar espacio propio
    exclusionMode: ExclusionMode.Normal
    exclusiveZone: 0
    color: "transparent"
    WlrLayershell.layer: sobreDock ? WlrLayer.Overlay : WlrLayer.Top
    // "dock": KWin la trata como panel, así que no se esconde con Mostrar escritorio (Meta+D)
    WlrLayershell.namespace: "dock"
    WlrLayershell.keyboardFocus: pideTeclado && desplegada ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    mask: Region { item: forma }

    Timer {
        id: cierre
        interval: 450
        onTriggered: if (!ventana.fijada && !ventana.retener && !ventana.archivoEncima && Quickshell.env("AKARI_ABIERTA") !== "1") ventana.abierta = false
    }
    onRetenerChanged: if (!retener && !forma.containsHover) cierre.restart()

    Rectangle {
        id: forma
        // apertura de 0 (cerrada) a 1 (abierta)
        readonly property real apertura: ventana.vertical
            ? Math.max(0, Math.min(1, (ancho.valor - ventana.altoCerrado) / Math.max(1, ventana.anchoAbierto)))
            : Math.max(0, Math.min(1, (alto.valor - ventana.altoCerrado) / Math.max(1, ventana.altoAbiertoH - ventana.altoCerrado)))
        readonly property real esquina: ventana.altoCerrado / 2 + (Tema.redondeoExtra - ventana.altoCerrado / 2) * apertura
        // dónde queda la cápsula cerrada dentro de la ventana
        readonly property real yCerradaV: ventana.cy - ventana.topPanelV

        x: ventana.moviendo ? 0
            : ventana.vertical ? (ventana.bordeIzq ? 0 : ventana.width - width)
            : ventana.haciaDerecha ? 0 : ventana.width - width
        y: ventana.moviendo ? 0
            : ventana.vertical ? yCerradaV * (1 - apertura)
            : ventana.haciaArriba ? ventana.height - height : 0
        width: ventana.moviendo ? ventana.wC : ancho.valor
        height: ventana.moviendo ? ventana.hC : alto.valor
        color: Tema.alfa(Tema.superficie, 0.94)
        // el lado pegado a un borde de la pantalla queda recto
        topLeftRadius: ventana.pegadaArriba || ventana.bordeIzq ? 0 : esquina
        bottomLeftRadius: ventana.pegadaAbajo || ventana.bordeIzq ? 0 : esquina
        topRightRadius: ventana.pegadaArriba || ventana.borde === "derecha" ? 0 : esquina
        bottomRightRadius: ventana.pegadaAbajo || ventana.borde === "derecha" ? 0 : esquina
        clip: true

        // Resortes sin rebote (amortiguación 1): abrir no viene de un gesto con impulso.
        Resorte {
            id: ancho
            objetivo: ventana.vertical
                ? (ventana.desplegada ? ventana.anchoPanelV : ventana.altoCerrado)
                : (ventana.desplegada ? ventana.anchoAbierto : ventana.anchoCerrado)
            respuesta: 0.38
        }
        Resorte {
            id: alto
            objetivo: ventana.vertical
                ? (ventana.desplegada ? ventana.altoPanelV : ventana.largoV)
                : (ventana.desplegada ? ventana.altoAbiertoH : ventana.altoCerrado)
            respuesta: 0.42
        }

        readonly property bool containsHover: sobre.hovered
        HoverHandler {
            id: sobre
            onHoveredChanged: {
                if (hovered) { cierre.stop(); ventana.abierta = true; }
                else cierre.restart();
            }
        }

        // Archivos arrastrados desde el gestor de archivos: al pasar por encima se abre (el
        // HoverHandler no se entera durante un arrastre) y al soltar avisa con sus URLs.
        DropArea {
            anchors.fill: parent
            enabled: ventana.aceptaArchivos && !ventana.moviendo
            keys: ["text/uri-list"]
            onEntered: drag => {
                ventana.archivoEncima = true;
                cierre.stop();
                if (drag.hasUrls) ventana.archivoEntro(Array.from(drag.urls).map(u => u.toString()));
                ventana.abierta = true;
            }
            onExited: { ventana.archivoEncima = false; cierre.restart(); }
            onDropped: drop => {
                ventana.archivoEncima = false;
                if (!drop.hasUrls) return;
                drop.acceptProposedAction();
                ventana.soltaron(Array.from(drop.urls).map(u => u.toString()));
                cierre.restart();
            }
        }

        // ---------------------------------------------- cabecera (o pestaña vertical)
        Item {
            id: zonaCabecera
            x: ventana.moviendo ? 0
                : ventana.vertical ? (ventana.bordeIzq ? 0 : forma.width - ventana.altoCerrado) : 0
            y: ventana.moviendo ? 0
                : ventana.vertical ? forma.yCerradaV - forma.y
                : ventana.haciaArriba ? forma.height - ventana.altoCerrado : 0
            width: ventana.moviendo ? ventana.wC : ventana.vertical ? ventana.altoCerrado : forma.width
            height: ventana.moviendo ? ventana.hC : ventana.vertical ? ventana.largoV : ventana.altoCerrado

            Loader {
                // en vertical la misma cabecera, girada: se lee de abajo arriba a la izquierda
                // y de arriba abajo a la derecha
                anchors.centerIn: parent
                width: ventana.vertical ? ventana.largoV : parent.width
                height: ventana.altoCerrado
                rotation: ventana.vertical ? (ventana.bordeIzq ? -90 : 90) : 0
                sourceComponent: ventana.cabecera
            }

            // clic: la deja fija abierta (otro clic la suelta); doble clic: a su lugar de fábrica
            TapHandler {
                onTapped: eventPoint => {
                    if (ventana.tocarCabecera && ventana.tocarCabecera(eventPoint.scenePosition)) return;
                    ventana.fijada = !ventana.fijada;
                    ventana.abierta = ventana.fijada || forma.containsHover;
                }
                onDoubleTapped: if (ventana.nombre) ventana.volverAFabrica()
            }
            // Arrastrar mueve la cápsula. Mientras se arrastra, la ventana es exactamente la
            // cápsula cerrada en (cx, cy); en cada paso se suma lo que el puntero se alejó del
            // punto donde se tomó (relativo a la cápsula) y vuelve a quedar bajo él.
            DragHandler {
                id: arrastre
                target: null
                enabled: ventana.nombre !== ""
                dragThreshold: 6
                cursorShape: active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property point agarre
                onActiveChanged: {
                    if (active) {
                        // punto agarrado, relativo a la cápsula cerrada (que está en cx, cy de la pantalla)
                        const p = centroid.scenePressPosition;
                        agarre = Qt.point(ventana.limitar(p.x - (ventana.cx - ventana.margins.left), 0, ventana.wC - 1),
                                          ventana.limitar(p.y - (ventana.cy - ventana.margins.top), 0, ventana.hC - 1));
                        ventana.moviendo = true;
                    } else {
                        ventana.moviendo = false;
                        ventana.soltar();
                    }
                }
                onCentroidChanged: {
                    if (!active || !ventana.moviendo) return;
                    ventana.cx = ventana.limitar(ventana.cx + centroid.position.x - agarre.x,
                                                 0, ventana.screen.width - ventana.wC);
                    ventana.cy = ventana.limitar(ventana.cy + centroid.position.y - agarre.y,
                                                 0, ventana.screen.height - ventana.hC);
                }
            }
        }

        // ---------------------------------------------- contenido (desplazable)
        Flickable {
            id: desplazable
            visible: !ventana.moviendo
            x: ventana.vertical ? (ventana.bordeIzq ? ventana.altoCerrado : 0)
                : ventana.haciaDerecha ? 0 : forma.width - width
            y: ventana.vertical ? 10 : ventana.haciaArriba ? 0 : ventana.altoCerrado
            width: ventana.anchoAbierto
            height: Math.max(0, ventana.vertical ? forma.height - 20 : forma.height - ventana.altoCerrado)
            contentWidth: width
            contentHeight: cargaCuerpo.implicitHeight
            interactive: contentHeight > height + 1
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            // el contenido aparece al ritmo de la apertura y se desliza desde la cabecera
            opacity: Math.max(0, (forma.apertura - 0.25) / 0.75)

            Loader {
                id: cargaCuerpo
                width: ventana.anchoAbierto
                sourceComponent: ventana.cuerpo
                transform: Translate {
                    x: ventana.vertical ? (ventana.bordeIzq ? -12 : 12) * (1 - forma.apertura) : 0
                    y: ventana.vertical ? 0 : (ventana.haciaArriba ? 12 : -12) * (1 - forma.apertura)
                }
            }
        }
    }
}
