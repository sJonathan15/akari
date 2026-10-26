pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Colores y tipografía. Si usas Caelestia, los colores salen de su esquema actual
// (~/.local/state/caelestia/scheme.json); en KDE Plasma se toma el color de acento del
// sistema (kdeglobals); si no, los colores que calcula el servicio (pywal / wallust,
// ~/.config/akari/tema.json…, ver akari/tema.py); y si nada de eso, una paleta oscura Material 3.
Singleton {
    id: tema

    property var c: ({})              // esquema de Caelestia (vacío si no hay)
    property color acentoSistema: "transparent"
    // colores del servicio ("#rrggbb"); solo si no hay Caelestia ni acento de KDE
    readonly property var servicio: Datos.estado && Datos.estado.tema && !c.primary && acentoSistema.a === 0
        ? Datos.estado.tema.colores : ({})
    function col(nombre, defecto) {
        const v = c[nombre];
        if (v) return "#" + v;
        return servicio[nombre] || defecto;
    }
    function alfa(color, a) { return Qt.rgba(color.r, color.g, color.b, a); }
    function mezcla(a, b, f) { return Qt.rgba(a.r + (b.r - a.r) * f, a.g + (b.g - a.g) * f, a.b + (b.b - a.b) * f, 1); }
    readonly property bool hayAcento: acentoSistema.a > 0 && !c.primary

    readonly property color primario: hayAcento ? Qt.lighter(acentoSistema, 1.35) : col("primary", "#b7c4ff")
    readonly property color sobrePrimario: col("onPrimary", "#1e2d60")
    readonly property color contPrimario: hayAcento ? mezcla(acentoSistema, "#131317", 0.45) : col("primaryContainer", "#6674ac")
    readonly property color secundario: col("secondary", "#c1c5e0")
    readonly property color contSecundario: hayAcento ? mezcla(acentoSistema, "#2a2a30", 0.75) : col("secondaryContainer", "#41465c")
    readonly property color sobreContSecundario: col("onSecondaryContainer", "#e0e2f0")
    readonly property color terciario: col("tertiary", "#f1b3e6")
    readonly property color error: col("error", "#ffb4ab")
    readonly property color exito: col("success", "#b5ccba")
    readonly property color superficie: col("surface", "#131317")
    readonly property color sobreSuperficie: col("onSurface", "#e4e1e7")
    readonly property color sobreSuperficieVar: col("onSurfaceVariant", "#c6c5d1")
    readonly property color contenedor: col("surfaceContainer", "#1f1f23")
    readonly property color contenedorAlto: col("surfaceContainerHigh", "#292a2e")
    readonly property color contenedorMax: col("surfaceContainerHighest", "#343438")
    readonly property color contorno: col("outline", "#8f909a")
    readonly property color contornoVar: col("outlineVariant", "#45464f")

    // si falta una fuente, Qt usa la del sistema; los iconos los instala install.sh
    function fuenteSi(nombre, otra) { return Qt.fontFamilies().indexOf(nombre) >= 0 ? nombre : otra; }
    readonly property string fuente: fuenteSi("Rubik", fuenteSi("Inter", Qt.application.font.family))
    readonly property string iconos: "Material Symbols Rounded"
    readonly property string mono: fuenteSi("CaskaydiaCove NF", fuenteSi("JetBrains Mono", "monospace"))

    readonly property int redondeoChico: 8
    readonly property int redondeo: 12
    readonly property int redondeoGrande: 20
    readonly property int redondeoExtra: 28
    readonly property int texto: 13
    readonly property int textoChico: 11
    readonly property int textoGrande: 18

    // curva "emphasized" de Material 3
    readonly property list<real> curva: [0.05, 0.7, 0.1, 1, 1, 1]
    readonly property int duracion: 400

    // con las animaciones de KDE en "instantáneas" (o AKARI_SIN_MOVIMIENTO=1) se apagan aquí también
    property bool movimientoReducido: Quickshell.env("AKARI_SIN_MOVIMIENTO") === "1"
    FileView {
        path: Quickshell.env("HOME") + "/.config/kdeglobals"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            const texto = text();
            const m = texto.match(/^AnimationDurationFactor=([0-9.]+)/m);
            if (m && parseFloat(m[1]) === 0) tema.movimientoReducido = true;
            // acento: [General] AccentColor o, si no, el color de selección
            const a = texto.match(/^AccentColor=(\d+),(\d+),(\d+)/m)
                || texto.match(/\[Colors:Selection\][^\[]*?^BackgroundNormal=(\d+),(\d+),(\d+)/m);
            if (a) tema.acentoSistema = Qt.rgba(a[1] / 255, a[2] / 255, a[3] / 255, 1);
        }
    }

    FileView {
        path: Quickshell.env("HOME") + "/.local/state/caelestia/scheme.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try { tema.c = JSON.parse(text()).colours || {}; } catch (e) {}
        }
    }
}
