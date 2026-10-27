// Comunicación de la página con la ventana que la contiene. Es lo único que cambia entre apps:
//  * Electron (app/, Linux X11 y GNOME): app/preload.js expone window.akari;
//  * Tauri (escritorio/, Windows): invoke() de Tauri para avisar y, de vuelta, la app llama a
//    window.__akariForma(forma) con eval;
//  * un navegador cualquiera: no hay ventana que mover, todo queda en nada.
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
};

// Tauri puede mandar la forma antes de que cargue este módulo: se guarda hasta que haya a quién dársela
window.__akariForma = (forma) => {
  if (alCambiar) alCambiar(forma);
  else window.__akariFormaPendiente = forma;
};
