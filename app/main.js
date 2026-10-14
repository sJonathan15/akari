// akari como app de escritorio (Electron): para GNOME, X11 y cualquier escritorio sin
// layer-shell. Muestra una pastilla flotante siempre visible (como las cápsulas), un icono
// en la bandeja y el panel completo al hacer clic. Empaquetada como AppImage trae dentro el
// servicio de Python; si no está corriendo, lo arranca ella misma.
//
//   akari-app            pastilla + bandeja
//   akari-app --panel    solo el panel (lo usa `akari abrir`)
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, shell, nativeImage } = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const PUERTO = 47830;
const URL = `http://127.0.0.1:${PUERTO}/`;
const RAIZ = app.isPackaged ? path.join(process.resourcesPath, "akari") : path.resolve(__dirname, "..");
const CONFIG = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config"), "akari");
const AJUSTES_APP = path.join(CONFIG, "app.json");
const AUTOARRANQUE = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config"), "autostart", "akari.desktop");
const ICONO = path.join(RAIZ, "iconos", "akari.png");
const SOLO_PANEL = process.argv.includes("--panel");
const es = (app.getLocale() || process.env.LANG || "").startsWith("es");
const t = (a, b) => (es ? a : b);

// La pastilla necesita posición fija y "siempre visible": en Wayland nativo Electron no puede,
// así que se usa XWayland (está en GNOME, KDE y casi todos) salvo que se pida otra cosa.
if (process.env.DISPLAY && !process.argv.some((a) => a.startsWith("--ozone-platform"))) {
  app.commandLine.appendSwitch("ozone-platform", "x11");
}

app.setName("akari");
app.setPath("userData", path.join(CONFIG, "app"));
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

let pastilla = null, panel = null, bandeja = null, servicio = null;

function leerAjustes() {
  try { return JSON.parse(fs.readFileSync(AJUSTES_APP, "utf8")); } catch { return {}; }
}
function guardarAjustes(cambio) {
  fs.mkdirSync(CONFIG, { recursive: true });
  fs.writeFileSync(AJUSTES_APP, JSON.stringify({ ...leerAjustes(), ...cambio }, null, 2));
}

// ------------------------------------------------------------ servicio
function vivo() {
  return new Promise((ok) => {
    const req = http.get(URL + "api/estado", (r) => { r.resume(); ok(r.statusCode === 200); });
    req.on("error", () => ok(false));
    req.setTimeout(800, () => { req.destroy(); ok(false); });
  });
}
async function asegurarServicio() {
  if (await vivo()) return;
  // instalado con install.sh: servicio de systemd; si no, lo arranca la app
  const r = spawnSync("systemctl", ["--user", "start", "akari.service"], { stdio: "ignore" });
  for (let i = 0; i < 12 && r.status === 0 && !(await vivo()); i++) await new Promise((x) => setTimeout(x, 250));
  if (await vivo()) return;
  servicio = spawn("python3", ["-m", "akari", "servicio"], {
    env: { ...process.env, PYTHONPATH: RAIZ }, stdio: "ignore",
  });
  for (let i = 0; i < 40 && !(await vivo()); i++) await new Promise((x) => setTimeout(x, 250));
}

// ------------------------------------------------------------ ventanas
function crearPastilla() {
  const area = screen.getPrimaryDisplay().workArea;
  const a = leerAjustes();
  const ancho = 330, alto = 40;
  pastilla = new BrowserWindow({
    width: ancho, height: alto,
    x: a.x ?? Math.round(area.x + (area.width - ancho) / 2), y: a.y ?? area.y + 6,
    frame: false, transparent: true, resizable: false, alwaysOnTop: true, skipTaskbar: true,
    focusable: false, hasShadow: false, show: false, title: "akari",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  pastilla.setAlwaysOnTop(true, "floating");
  pastilla.setVisibleOnAllWorkspaces(true);
  pastilla.loadURL(URL + "?vista=capsula");
  pastilla.webContents.on("did-fail-load", () => setTimeout(() => pastilla?.loadURL(URL + "?vista=capsula"), 1500));
  pastilla.once("ready-to-show", () => { if (leerAjustes().pastilla !== false) pastilla.showInactive(); });
  pastilla.on("moved", () => { const [x, y] = pastilla.getPosition(); guardarAjustes({ x, y }); });
  pastilla.on("closed", () => { pastilla = null; });
}

function crearPanel() {
  const area = screen.getPrimaryDisplay().workArea;
  const ancho = Math.min(460, area.width - 20), alto = Math.min(800, area.height - 60);
  let x = Math.round(area.x + (area.width - ancho) / 2), y = area.y + 52;
  if (pastilla) {
    const p = pastilla.getBounds();
    x = Math.max(area.x, Math.min(area.x + area.width - ancho, Math.round(p.x + p.width / 2 - ancho / 2)));
    y = p.y + p.height + 8 + alto > area.y + area.height ? Math.max(area.y, p.y - alto - 8) : p.y + p.height + 8;
  }
  panel = new BrowserWindow({
    width: ancho, height: alto, x, y, minWidth: 380, minHeight: 480, show: false,
    title: "akari", icon: ICONO, backgroundColor: "#131317", autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  panel.setMenuBarVisibility(false);
  panel.loadURL(URL);
  panel.webContents.on("did-fail-load", () => setTimeout(() => panel?.loadURL(URL), 1500));
  panel.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; });
  panel.once("ready-to-show", () => { panel.show(); panel.focus(); });
  panel.on("closed", () => { panel = null; if (SOLO_PANEL) app.quit(); });
}

function alternarPanel() {
  if (!panel) return crearPanel();
  if (panel.isVisible() && panel.isFocused()) panel.hide();
  else { panel.show(); panel.focus(); }
}

// ------------------------------------------------------------ bandeja
function autoarranque(activar) {
  if (!activar) return fs.rmSync(AUTOARRANQUE, { force: true });
  const exe = process.env.APPIMAGE || process.execPath;
  const args = app.isPackaged ? "" : ` "${path.join(__dirname)}"`;
  fs.mkdirSync(path.dirname(AUTOARRANQUE), { recursive: true });
  fs.writeFileSync(AUTOARRANQUE, `[Desktop Entry]\nType=Application\nName=akari\nExec="${exe}"${args}\nIcon=${ICONO}\nX-GNOME-Autostart-enabled=true\n`);
}

function crearBandeja() {
  bandeja = new Tray(nativeImage.createFromPath(ICONO).resize({ width: 22, height: 22 }));
  bandeja.setToolTip("akari");
  const menu = () => Menu.buildFromTemplate([
    { label: t("Abrir panel", "Open panel"), click: alternarPanel },
    {
      label: t("Mostrar la cápsula", "Show the capsule"), type: "checkbox", checked: leerAjustes().pastilla !== false,
      click: (i) => { guardarAjustes({ pastilla: i.checked }); i.checked ? pastilla?.showInactive() : pastilla?.hide(); },
    },
    { label: t("Iniciar con la sesión", "Start on login"), type: "checkbox", checked: fs.existsSync(AUTOARRANQUE), click: (i) => autoarranque(i.checked) },
    { type: "separator" },
    { label: t("Salir", "Quit"), click: () => app.quit() },
  ]);
  bandeja.setContextMenu(menu());
  bandeja.on("click", alternarPanel);
}

ipcMain.on("alternar-panel", alternarPanel);
app.on("second-instance", (_e, argv) => (argv.includes("--panel") ? (panel ? (panel.show(), panel.focus()) : crearPanel()) : alternarPanel()));
app.on("window-all-closed", (e) => { if (!SOLO_PANEL) e.preventDefault?.(); });
app.on("before-quit", () => { if (servicio) servicio.kill(); });

app.whenReady().then(async () => {
  await asegurarServicio();
  if (SOLO_PANEL) return crearPanel();
  crearPastilla();
  crearBandeja();
});
