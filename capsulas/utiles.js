.pragma library

// Idioma de la interfaz: el del sistema (LANG). Español si empieza por "es"; si no, inglés.
var idioma = Qt.locale().name.indexOf("es") === 0 ? "es" : "en";
function t(es, en) { return idioma === "es" ? es : en; }

function decimal(texto) { return idioma === "es" ? texto.replace(".", ",") : texto; }

function corto(n) {
    if (n === null || n === undefined) return "—";
    if (n >= 1e9) return decimal((n / 1e9).toFixed(2)) + " B";
    if (n >= 1e6) return decimal((n / 1e6).toFixed(n >= 1e7 ? 1 : 2)) + " M";
    if (n >= 1e4) return Math.round(n / 1e3) + " k";
    if (n >= 1e3) return decimal((n / 1e3).toFixed(1)) + " k";
    return String(Math.round(n));
}

function cuenta(seg) {
    seg = Math.max(0, Math.round(seg));
    const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60);
    if (h >= 24) return Math.floor(h / 24) + " d " + (h % 24) + " h";
    return h ? h + " h " + (m < 10 ? "0" : "") + m : m + " min";
}

function hace(seg) {
    seg = Math.max(0, Math.round(seg));
    const v = seg < 60 ? seg + " s" : seg < 3600 ? Math.floor(seg / 60) + " min" : Math.floor(seg / 3600) + " h";
    return t("hace " + v, v + " ago");
}

function hora(ts) {
    const d = new Date(ts * 1000);
    const h = d.getHours(), m = d.getMinutes();
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
}

// "06:00" + 30 -> "06:30" (da la vuelta a medianoche)
function moverHora(hhmm, delta) {
    const p = hhmm.split(":");
    const m = ((parseInt(p[0]) * 60 + parseInt(p[1]) + delta) % 1440 + 1440) % 1440;
    return (m < 600 ? "0" : "") + Math.floor(m / 60) + ":" + (m % 60 < 10 ? "0" : "") + m % 60;
}

function nivel(d) {
    if (!d || !d.conectado) return "nada";
    if (d.bateria === null || d.bateria === undefined) return "cable";
    if (d.bateria <= 20) return "bajo";
    if (d.bateria <= 50) return "medio";
    return "ok";
}

function textoCorto(d) {
    if (!d || !d.conectado) return "—";
    if (d.bateria !== null && d.bateria !== undefined) return d.bateria + "%";
    return d.conexion && d.conexion.indexOf("USB") >= 0 ? "USB" : "OK";
}

const ICONOS = { raton: "mouse", audifonos: "headphones", teclado: "keyboard", celular: "smartphone",
                 mando: "sports_esports", otro: "devices_other" };

// 125 -> "02:05"; 3725 -> "1:02:05" (grabaciones, transcripciones)
function reloj(seg) {
    seg = Math.max(0, Math.round(seg));
    const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
    const dos = n => (n < 10 ? "0" : "") + n;
    return (h ? h + ":" + dos(m) : dos(m)) + ":" + dos(s);
}

// abre el panel completo (claves de API, modelos de IA…)
function abrirPanel(Quickshell) {
    Quickshell.execDetached([(Quickshell.env("AKARI_RAIZ") || Quickshell.shellDir + "/..") + "/bin/akari", "abrir"]);
}

// ------------------------------------------------------------------ muñequito del asistente
// Un farolito con llama (akari = «luz»), 13 × 14 píxeles. Mismo dibujo en web/app.js.
// Letras: o contorno · b cuerpo · l brillo · e ojos · c mejillas · m boca · f llama · F centro de la llama
var MUNECO = [
    "......F......",
    ".....fFf.....",
    ".....fff.....",
    "......o......",
    "...ooooooo...",
    "..obbbbbbbo..",
    ".obllbbbbbbo.",
    ".oblbbbbbbbo.",
    ".obbbbbbbbbo.",
    ".obbbbbbbbbo.",
    ".obcbbbbbcbo.",
    "..obbbbbbbo..",
    "...ooooooo...",
    "...oo...oo..."
];

// [[x, y, letra], …] para un estado (pausa, escuchando, oyendo, confirmando, pensando, hablando,
// error) y un paso de animación (entero que sube solo, ~6 por segundo)
function pixelesMuneco(estado, paso) {
    var g = MUNECO.map(function (fila) { return fila.split(""); });
    function pon(x, y, c) { g[y][x] = c; }
    var parpadeo = estado !== "pausa" && paso % 26 === 0;
    if (estado === "pausa" || parpadeo) {               // ojos cerrados
        pon(3, 9, "e"); pon(4, 9, "e"); pon(8, 9, "e"); pon(9, 9, "e");
    } else if (estado === "pensando") {                 // mira hacia arriba
        pon(4, 7, "e"); pon(4, 8, "e"); pon(8, 7, "e"); pon(8, 8, "e");
    } else if (estado === "oyendo" || estado === "confirmando") {   // ojos grandes
        pon(4, 8, "e"); pon(5, 8, "e"); pon(4, 9, "e"); pon(5, 9, "e");
        pon(7, 8, "e"); pon(8, 8, "e"); pon(7, 9, "e"); pon(8, 9, "e");
    } else if (estado === "error") {                    // ojos en x
        pon(3, 8, "e"); pon(4, 9, "e"); pon(3, 10, "e"); pon(8, 8, "e"); pon(9, 9, "e"); pon(8, 10, "e");
    } else {
        pon(4, 8, "e"); pon(4, 9, "e"); pon(8, 8, "e"); pon(8, 9, "e");
    }
    if (estado === "hablando" && paso % 2 === 0) {      // boca abierta
        pon(5, 10, "m"); pon(6, 10, "m"); pon(7, 10, "m"); pon(6, 11, "m");
    } else if (estado !== "error") {
        pon(6, 10, "m");
    }
    // la llama: tiembla al pensar, crece al oír y se achica en pausa
    if (estado === "pausa") {
        pon(6, 0, "."); pon(5, 1, "."); pon(7, 1, "."); pon(6, 1, "f");
    } else if (estado === "pensando" || estado === "confirmando") {
        var lado = [5, 6, 7, 6][paso % 4];
        pon(6, 0, "."); pon(lado, 0, "F");
    } else if (estado === "oyendo") {
        pon(4, 1, "f"); pon(8, 1, "f"); pon(5, 0, "f"); pon(7, 0, "f");
    }
    var r = [];
    for (var y = 0; y < g.length; y++)
        for (var x = 0; x < g[y].length; x++)
            if (g[y][x] !== ".") r.push([x, y, g[y][x]]);
    return r;
}
