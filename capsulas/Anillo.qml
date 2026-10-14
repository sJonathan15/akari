import QtQuick
import QtQuick.Shapes

// Progreso circular como el de Caelestia (pista tenue + arco redondeado).
Item {
    id: anillo
    property real valor: 0            // 0..1
    property color color: Tema.primario
    property color pista: Tema.contenedorMax
    property real grosor: 7

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "transparent"
            strokeColor: anillo.pista
            strokeWidth: anillo.grosor
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: anillo.width / 2; centerY: anillo.height / 2
                radiusX: anillo.width / 2 - anillo.grosor / 2; radiusY: radiusX
                startAngle: 0; sweepAngle: 360
            }
        }
        ShapePath {
            fillColor: "transparent"
            strokeColor: anillo.valor > 0.001 ? anillo.color : "transparent"
            strokeWidth: anillo.grosor
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: anillo.width / 2; centerY: anillo.height / 2
                radiusX: anillo.width / 2 - anillo.grosor / 2; radiusY: radiusX
                startAngle: -90
                sweepAngle: 360 * Math.max(0, Math.min(1, anillo.valor))
                Behavior on sweepAngle { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
            }
        }
    }
}
