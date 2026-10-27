// Puente mínimo entre las páginas de akari y la app: abrir el panel y mover/abrir las burbujas.
// rutaDe(file): la ruta real de un archivo soltado (el resultado queda junto al original).
const { contextBridge, ipcRenderer, webUtils } = require("electron");
contextBridge.exposeInMainWorld("akari", {
  alternarPanel: () => ipcRenderer.send("alternar-panel"),
  burbuja: (accion, datos) => ipcRenderer.send("burbuja", String(accion), datos || {}),
  alCambiarForma: (fn) => ipcRenderer.on("burbuja:forma", (_e, forma) => fn(forma)),
  rutaDe: (archivo) => {
    try { return webUtils.getPathForFile(archivo) || ""; } catch { return ""; }
  },
  sistema: process.platform,
});
