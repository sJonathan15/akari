// Comunicación de la página con la ventana que la contiene. Es lo único que cambia entre apps:
//  * Electron (app/, Linux X11 y GNOME): app/preload.js expone window.akari;
//  * Tauri (escritorio/, Windows): invoke() de Tauri para avisar y, de vuelta, la app llama a
//    window.__akariForma(forma) con eval;
//  * un navegador cualquiera: no hay ventana que mover, todo queda en nada.
// También da window.akari.rutaDe(file): la ruta real de un archivo soltado, para que lo que se
// genere (p. ej. el .md de un documento) quede junto al original.
const electron = window.akari;
const tauri = window.__TAURI_INTERNALS__;
let alCambiar = null;

function invocar(orden, args) {
  try {
    const r = tauri.invoke(orden, args);
    if (r && r.catch) r.catch(() => {});
  } catch {}
}

export const ventana = {
  app: electron ? "electron" : tauri ? "tauri" : null,
  // acciones de una burbuja: abrir, cerrar, alto, mover-inicio, mover, soltar, fabrica
  burbuja(accion, datos) {
    if (electron) electron.burbuja(accion, datos);
    else if (tauri) invocar("burbuja", { accion: String(accion), datos: datos || {} });
  },
  // la app dice qué forma tiene la burbuja (abierta, vertical, hacia dónde se despliega…)
  alCambiarForma(fn) {
    if (electron) return electron.alCambiarForma(fn);
    alCambiar = fn;
    const pendiente = window.__akariFormaPendiente;
    window.__akariFormaPendiente = null;
    if (pendiente) fn(pendiente);
  },
  alternarPanel() {
    if (electron) electron.alternarPanel();
    else if (tauri) invocar("alternar_panel", {});
  },
  rutaDe(archivo) {
    return (window.akari && window.akari.rutaDe && window.akari.rutaDe(archivo)) || "";
  },
};

// Arrastrar archivos sobre una burbuja cerrada la abre, para poder soltarlos en su cuerpo.
const enBurbuja = new URLSearchParams(location.search).get("vista") === "burbuja";
document.addEventListener("dragenter", (e) => {
  if (enBurbuja && e.dataTransfer && [...e.dataTransfer.types].includes("Files")) ventana.burbuja("abrir");
});

// Tauri: WebView2 no entrega los archivos soltados a la página; la app (escritorio/) los recibe
// con su ruta y llama a window.__akariArrastre. Aquí se vuelven un dragenter/dragover/drop
// normal con File de verdad, y rutaDe(file) devuelve la ruta de cada uno.
if (tauri && !electron) {
  const rutas = new WeakMap();
  window.akari = { rutaDe: (archivo) => rutas.get(archivo) || "" };
  window.__akariArrastre = ({ tipo, rutas: lista, x, y }) => {
    const dt = new DataTransfer();
    for (const ruta of lista || []) {
      const archivo = new File([], ruta.split(/[\\/]/).pop());
      rutas.set(archivo, ruta);
      dt.items.add(archivo);
    }
    let destino = document.elementFromPoint(x, y) || document.body;
    // en la cabecera de una burbuja: a su cuerpo (ahí está lo que acepta archivos)
    if (enBurbuja && !destino.closest("#b-cuerpo")) destino = document.querySelector("#b-contenido .pagina") || destino;
    const evento = { entrar: "dragenter", encima: "dragover", salir: "dragleave", soltar: "drop" }[tipo];
    if (evento) destino.dispatchEvent(new DragEvent(evento, { bubbles: true, cancelable: true, dataTransfer: dt, clientX: x, clientY: y }));
  };
}

// Tauri puede mandar la forma antes de que cargue este módulo: se guarda hasta que haya a quién dársela
window.__akariForma = (forma) => {
  if (alCambiar) alCambiar(forma);
  else window.__akariFormaPendiente = forma;
};
