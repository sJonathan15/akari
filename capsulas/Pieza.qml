import QtQuick

// Una pieza de un grupo de cápsulas (CapsulaGrupo.qml): su chip en la píldora cerrada (`resumen`)
// y lo que muestra abierta (`cuerpo`). La lista de grupos y piezas está en akari/grupos.py.
Item {
    id: pieza
    visible: false

    property string clave: ""               // "dispositivos", "uso", "documentos"… (como en grupos.py)
    property string titulo: ""
    property string icono: ""
    property int anchoChip: 60              // ancho del chip en la píldora cerrada
    property int anchoAbierto: 384
    property bool pideTeclado: false        // tiene campos de texto
    property bool aceptaArchivos: false     // se le pueden soltar archivos…
    property var patron: null               // …de este tipo (expresión regular sobre la URL; null = todos)
    property Component resumen
    property Component cuerpo

    // los pone el grupo
    property var grupo: null
    readonly property bool activa: !!grupo && grupo.pieza === pieza
    readonly property bool abierta: activa && grupo.desplegada
    readonly property bool archivoEncima: activa && grupo.archivoEncima
    property bool retener: false            // pide que el grupo no se cierre (p. ej. escribiendo)
    signal soltaron(var urls)

    function acepta(url) { return aceptaArchivos && (!patron || patron.test(url)); }
    function mostrar() { if (grupo) grupo.elegir(clave); }
}
