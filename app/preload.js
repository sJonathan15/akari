// Puente mínimo entre las páginas de akari y la app: abrir el panel y mover/abrir las burbujas.
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("akari", {
  alternarPanel: () => ipcRenderer.send("alternar-panel"),
  burbuja: (accion, datos) => ipcRenderer.send("burbuja", String(accion), datos || {}),
  alCambiarForma: (fn) => ipcRenderer.on("burbuja:forma", (_e, forma) => fn(forma)),
  sistema: process.platform,
});
