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
