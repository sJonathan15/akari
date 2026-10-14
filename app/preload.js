// Puente mínimo para la pastilla: un clic abre o cierra el panel.
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("akari", { alternarPanel: () => ipcRenderer.send("alternar-panel") });
