import QtQuick
import Quickshell
import QtQuick3D
import QtQuick3D.AssetUtils
import "utiles.js" as U

// Modelo .glb del dispositivo, iluminado con un mapa de estudio.
// Se puede agarrar con el ratón: gira 1:1 con la mano, al soltarlo conserva
// el impulso y luego vuelve a su giro lento. Sin modelo descargado, muestra el icono.
Item {
    id: visor
    property string modelo: "mouse"            // mouse | keyboard | headphones | phone (carpeta modelos/)
    property string tipo: "raton"              // para el icono si no hay modelo
    property bool encendido: true
    // ruta absoluta: Qt Quick 3D no entiende las rutas internas de Quickshell
    readonly property string carpeta: "file://" + (Quickshell.env("AKARI_RAIZ") || (Quickshell.shellDir + "/..")) + "/modelos/"
    // orientación de cada modelo para que se vea de tres cuartos
    readonly property var ajustes: ({
        mouse:      { rx: 0, ry: 210, inclinacion: -40, tam: 100 },
        headphones: { rx: 0, ry: 25,  inclinacion: -10, tam: 104 },
        keyboard:   { rx: 0, ry: 20,  inclinacion: -45, tam: 122 },
        phone:      { rx: 0, ry: 20,  inclinacion: -8,  tam: 92 }
    })
    property var ajusteManual: null            // para pruebas: { rx, ry, rz, inclinacion, tam }
    readonly property var ajuste: ajusteManual || ajustes[modelo] || ajustes.mouse

    // ---------------------------------------------------------- giro
    readonly property real giroLento: Tema.movimientoReducido ? 0 : 20   // grados por segundo
    property real angulo: 0
    property real tiempo: 0
    property real velocidad: giroLento
    property bool agarrado: false
    property var historial: []          // últimas posiciones para medir la velocidad al soltar

    // Inclinación extra al arrastrar en vertical, con resistencia en el borde.
    function elastico(exceso, dimension) {
        const c = 0.55;
        return (exceso * dimension * c) / (dimension + c * Math.abs(exceso));
    }
    Resorte { id: inclinacion; objetivo: 0; respuesta: 0.4; amortiguacion: 0.8 }

    FrameAnimation {
        running: vista.visible
        onTriggered: {
            if (visor.agarrado) return;
            const dt = Math.min(frameTime, 1 / 30);
            if (visor.ajuste.vaiven) {
                // balanceo: el impulso se frena y el ángulo vuelve suavemente al vaivén
                visor.tiempo += dt;
                visor.velocidad *= Math.pow(0.998, dt * 1000);
                let a = ((visor.angulo + visor.velocidad * dt + 180) % 360 + 360) % 360 - 180;
                const objetivo = Tema.movimientoReducido ? 0 : visor.ajuste.vaiven * Math.sin(visor.tiempo * 0.5);
                a += (objetivo - a) * (1 - Math.exp(-dt * 2.5));
                visor.angulo = a;
                return;
            }
            // el impulso decae como el desplazamiento de iOS (0,998 por ms) hacia el giro lento
            visor.velocidad = visor.giroLento + (visor.velocidad - visor.giroLento) * Math.pow(0.998, dt * 1000);
            visor.angulo = (visor.angulo + visor.velocidad * dt) % 360;
        }
    }

    // Al cambiar de dispositivo, el nuevo modelo aparece creciendo un poco.
    Resorte { id: aparicion; objetivo: 1; respuesta: 0.35 }
    onModeloChanged: {
        aparicion.saltar(0);
        aparicion.objetivo = 0;
        aparicion.objetivo = 1;
    }

    View3D {
        id: vista
        anchors.fill: parent
        visible: visor.modelo !== "" && carga.status === RuntimeLoader.Success
        opacity: (visor.encendido ? 1 : 0.35) * aparicion.valor
        scale: 0.9 + 0.1 * aparicion.valor

        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeFilmic
            lightProbe: Texture { source: visor.carpeta + "studio.hdr" }
            probeExposure: 1.7
        }

        PerspectiveCamera {
            position: Qt.vector3d(0, 0, 230)
            fieldOfView: 30
        }
        // luz principal, contraluz blanco que dibuja el contorno (clave para el ratón negro)
        // y un relleno suave del color del tema
        DirectionalLight {
            eulerRotation: Qt.vector3d(-40, -35, 0)
            brightness: 1.3
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(-20, 165, 0)
            brightness: 1.4
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(-10, 80, 0)
            color: Tema.primario
            brightness: 0.5
        }

        Node {
            eulerRotation.x: -visor.ajuste.inclinacion + inclinacion.valor
            Node {
                eulerRotation.y: visor.angulo
                Node {
                    eulerRotation: Qt.vector3d(visor.ajuste.rx, visor.ajuste.ry, visor.ajuste.rz || 0)
                    RuntimeLoader {
                        id: carga
                        // los modelos ya vienen centrados y de 1 unidad de lado (herramientas/modelos.py)
                        source: visor.modelo ? visor.carpeta + visor.modelo + ".glb" : ""
                        scale: Qt.vector3d(visor.ajuste.tam * (visor.ajuste.ex || 1), visor.ajuste.tam,
                                           visor.ajuste.tam * (visor.ajuste.ez || 1))
                        onStatusChanged: if (status === RuntimeLoader.Error && source != "") console.warn("Modelo 3D", source, errorString)
                    }
                }
            }
        }
    }

    MouseArea {
        anchors.fill: vista
        enabled: vista.visible
        cursorShape: visor.agarrado ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property real ultimoX: 0
        property real inicioY: 0

        onPressed: mouse => {
            // agarrar detiene el giro justo donde está (sin saltos)
            visor.agarrado = true;
            visor.velocidad = 0;
            ultimoX = mouse.x;
            inicioY = mouse.y;
            visor.historial = [{ t: Date.now(), a: visor.angulo }];
            inclinacion.saltar(inclinacion.valor);
        }
        onPositionChanged: mouse => {
            if (!visor.agarrado) return;
            visor.angulo += (mouse.x - ultimoX) * 0.6;          // 1:1 con la mano
            ultimoX = mouse.x;
            inclinacion.saltar(visor.elastico((mouse.y - inicioY) * 0.4, 30));
            const h = visor.historial.concat([{ t: Date.now(), a: visor.angulo }]);
            visor.historial = h.filter(p => Date.now() - p.t < 100);
        }
        onReleased: {
            // la velocidad de la mano pasa al giro: lanzarlo lo hace girar más
            const h = visor.historial;
            if (h.length >= 2) {
                const dt = (h[h.length - 1].t - h[0].t) / 1000;
                if (dt > 0) visor.velocidad = (h[h.length - 1].a - h[0].a) / dt;
            }
            visor.agarrado = false;
            inclinacion.objetivo = 0.0001;
            inclinacion.objetivo = 0;
        }
        onCanceled: released(null)
    }

    Icono {
        anchors.centerIn: parent
        visible: !vista.visible
        text: U.ICONOS[visor.tipo] || "devices"
        tam: Math.min(parent.width, parent.height) * 0.55
        relleno: 1
        color: visor.encendido ? Tema.primario : Tema.contornoVar
        opacity: 0.9 * aparicion.valor
        scale: 0.85 + 0.15 * aparicion.valor
    }
}
