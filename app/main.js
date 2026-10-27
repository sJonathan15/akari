// akari como app de escritorio (Electron) para todo lo que no tiene layer-shell: Windows,
// X11 (XFCE, Cinnamon, MATE…), GNOME o distribuciones sin Quickshell. Muestra las mismas tres
// burbujas que las cápsulas de KDE / Hyprland (cuelgan del borde de arriba, se abren al pasar
// el ratón, se arrastran y contra un borde lateral se vuelven pestaña vertical), un icono en la
// bandeja y el panel completo con 3D. Empaquetada (AppImage / instalador de Windows) trae dentro
// el servicio de Python —en Windows también el propio Python— y lo arranca si no está corriendo.
//
//   akari-app            burbujas + bandeja
//   akari-app --panel    solo el panel (lo usa `akari abrir`)
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, shell, nativeImage } = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const WINDOWS = process.platform === "win32";
const LINUX = process.platform === "linux";
const PUERTO = 47830;
const URL = `http://127.0.0.1:${PUERTO}/`;
const APP_ID = "io.github.sjonathan15.akari";
const RAIZ = app.isPackaged ? path.join(process.resourcesPath, "akari") : path.resolve(__dirname, "..");
const XDG_CONFIG = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
// mismas carpetas que el servicio (akari/comun.py)
const CONFIG = WINDOWS ? path.join(process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming"), "akari")
  : path.join(XDG_CONFIG, "akari");
const AJUSTES_APP = path.join(CONFIG, "app.json");
const POSICIONES = path.join(CONFIG, "posiciones.json");
const AUTOARRANQUE = path.join(XDG_CONFIG, "autostart", "akari.desktop");
const AJUSTES_CLAUDE = path.join(process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude"), "settings.json");
const ICONO = path.join(RAIZ, "iconos", "akari.png");
const SOLO_PANEL = process.argv.includes("--panel");
const es = (app.getLocale() || process.env.LANG || "").startsWith("es");
const t = (a, b) => (es ? a : b);

// Las burbujas necesitan posición fija y "siempre visible": en Wayland nativo Electron no puede,
// así que en Linux se usa XWayland (está en GNOME, KDE y casi todos) salvo que se pida otra cosa.
if (LINUX && process.env.DISPLAY && !process.argv.some((a) => a.startsWith("--ozone-platform"))) {
  if (process.env.XDG_SESSION_TYPE !== "x11") {
    // GTK se inicia antes que este archivo: hay que volver a arrancar con el entorno de X11
    process.env.XDG_SESSION_TYPE = "x11";
    process.env.GDK_BACKEND = "x11";
    app.relaunch({ execPath: process.env.APPIMAGE || process.execPath, args: process.argv.slice(1) });
    app.exit(0);
  }
  app.commandLine.appendSwitch("ozone-platform", "x11");
}
if (LINUX) app.commandLine.appendSwitch("enable-transparent-visuals");

app.setName("akari");
if (WINDOWS) app.setAppUserModelId(APP_ID);     // avisos y bandeja con el nombre "akari"
app.setPath("userData", path.join(CONFIG, "app"));
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

let panel = null, bandeja = null, servicio = null;
const burbujas = new Map();     // nombre -> Burbuja

function leerJSON(ruta) {
  try { return JSON.parse(fs.readFileSync(ruta, "utf8")); } catch { return {}; }
}
function escribirJSON(ruta, datos) {
  fs.mkdirSync(path.dirname(ruta), { recursive: true });
  fs.writeFileSync(ruta + ".tmp", JSON.stringify(datos, null, 2));
  fs.renameSync(ruta + ".tmp", ruta);
}
const leerAjustes = () => leerJSON(AJUSTES_APP);
const guardarAjustes = (cambio) => escribirJSON(AJUSTES_APP, { ...leerAjustes(), ...cambio });

// ------------------------------------------------------------ servicio
// El intérprete: en Windows el Python embebido que trae el instalador; si no, el del sistema.
function python() {
  const embebido = path.join(process.resourcesPath || "", "python", "python.exe");
  if (WINDOWS && app.isPackaged && fs.existsSync(embebido)) return embebido;
  return WINDOWS ? "python" : "python3";
}
function akari(...args) {
  return spawn(python(), [path.join(RAIZ, "bin", "akari.py"), ...args], {
    env: { ...process.env, AKARI_APP_ID: APP_ID }, stdio: "ignore", windowsHide: true,
  });
}

function vivo() {
  return new Promise((ok) => {
    const req = http.get(URL + "api/estado", (r) => { r.resume(); ok(r.statusCode === 200); });
    req.on("error", () => ok(false));
    req.setTimeout(800, () => { req.destroy(); ok(false); });
  });
}
async function asegurarServicio() {
  if (await vivo()) return;
  if (LINUX) {     // instalado con install.sh: servicio de systemd; si no, lo arranca la app
    const r = spawnSync("systemctl", ["--user", "start", "akari.service"], { stdio: "ignore" });
    for (let i = 0; i < 12 && r.status === 0 && !(await vivo()); i++) await new Promise((x) => setTimeout(x, 250));
    if (await vivo()) return;
  }
  servicio = akari("servicio");
  servicio.on("error", () => { servicio = null; });
  for (let i = 0; i < 40 && !(await vivo()); i++) await new Promise((x) => setTimeout(x, 250));
}

// ------------------------------------------------------------ burbujas
// Las mismas medidas que capsulas/*.qml. Las posiciones se guardan en posiciones.json
// (el mismo archivo y formato que usan las cápsulas de Quickshell), relativas al área de trabajo.
const ALTO = 38;              // grosor de la burbuja cerrada
const MARGEN_BORDE = 40;      // a esta distancia de un lado se vuelve pestaña vertical
// los tres grupos de AGENTS.md, por si el servicio es de una versión sin GET /api/burbujas
const BURBUJAS = {
  equipo: { lado: "izquierda", hueco: 8, anchoCerrado: 274, anchoAbierto: 384, altoMaximo: 700 },
  ia: { lado: "derecha", hueco: 8, anchoCerrado: 342, anchoAbierto: 384, altoMaximo: 780, teclado: true },
  archivos: { lado: "derecha", hueco: 404, anchoCerrado: 154, anchoAbierto: 380, altoMaximo: 760 },
};
const limitar = (v, min, max) => Math.max(min, Math.min(max, v));

// AKARI_PANTALLA=<número o nombre> elige el monitor; si no, el principal
function pantalla() {
  const lista = screen.getAllDisplays();
  const elegida = process.env.AKARI_PANTALLA;
  return lista.find((d, i) => elegida && (String(i) === elegida || d.label === elegida)) || screen.getPrimaryDisplay();
}

class Burbuja {
  constructor(nombre, medidas) {
    Object.assign(this, medidas);
    this.nombre = nombre;
    this.abierta = false;
    this.moviendo = false;
    this.altoCuerpo = 0;
    const g = (leerJSON(POSICIONES).capsulas || {})[nombre];
    this.cx = g && Number.isFinite(g.x) ? g.x : null;     // null = posición de fábrica
    this.cy = g && Number.isFinite(g.y) ? g.y : 0;
    this.borde = (g && g.borde) || "";
    this.ventana = new BrowserWindow({
      ...this.limites(), frame: false, transparent: true, backgroundColor: "#00000000", resizable: false,
      alwaysOnTop: true, skipTaskbar: true, focusable: !!this.teclado, hasShadow: false, show: false,
      minimizable: false, maximizable: false, fullscreenable: false, title: "akari",
      webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
    });
    this.ventana.setAlwaysOnTop(true, WINDOWS ? "screen-saver" : "floating");
    this.ventana.setVisibleOnAllWorkspaces(true);
    const pagina = `${URL}?vista=burbuja&c=${nombre}`;     // el grupo, con sus piezas en pestañas
    this.ventana.loadURL(pagina);
    this.ventana.webContents.on("did-fail-load", () => setTimeout(() => this.ventana?.loadURL(pagina), 1500));
    this.ventana.webContents.on("did-finish-load", () => this.avisar());
    this.ventana.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; });
    this.ventana.once("ready-to-show", () => { if (leerAjustes().burbujas !== false) this.ventana.showInactive(); });
    this.ventana.on("closed", () => { this.ventana = null; });
  }

  get area() { return pantalla().workArea; }
  get vertical() { return this.borde !== ""; }
  get izquierda() { return this.borde === "izquierda"; }
  get largoV() { return Math.max(this.anchoCerrado, 156); }
  get wC() { return this.vertical ? ALTO : this.anchoCerrado; }
  get hC() { return this.vertical ? this.largoV : ALTO; }
  get x() {
    const W = this.area.width;
    if (this.cx === null) return this.lado === "derecha" ? Math.round(W / 2 + this.hueco) : Math.round(W / 2 - this.hueco - this.anchoCerrado);
    return this.cx;
  }
  // cerca de un borde (200 px) abre hacia el otro lado; en medio, hacia su lado de siempre
  get haciaDerecha() {
    const W = this.area.width, x = this.x;
    let d = x < 200 ? true : W - (x + this.anchoCerrado) < 200 ? false : this.lado === "derecha";
    if (d && x + this.anchoAbierto > W) d = false;
    if (!d && x + this.anchoCerrado - this.anchoAbierto < 0) d = true;
    return d;
  }
  get haciaArriba() { return this.cy + ALTO / 2 > this.area.height / 2; }
  get altoAbierto() {
    const H = this.area.height;
    const disponible = Math.max(ALTO, Math.min(this.altoMaximo, this.haciaArriba ? this.cy + ALTO : H - this.cy));
    return Math.min(disponible, ALTO + this.altoCuerpo);
  }
  get altoPanelV() { return Math.min(this.area.height, Math.max(this.largoV, this.altoCuerpo + 20)); }
  get topPanelV() { return limitar(Math.round(this.cy + this.largoV / 2 - this.altoPanelV / 2), 0, this.area.height - this.altoPanelV); }
  get desplegada() { return this.abierta && !this.moviendo; }

  // rectángulo de la ventana en la pantalla
  limites() {
    const a = this.area, W = a.width;
    let r;
    if (!this.desplegada) {
      r = this.vertical ? { x: this.izquierda ? 0 : W - ALTO, y: this.cy, width: ALTO, height: this.largoV }
        : { x: this.x, y: this.cy, width: this.anchoCerrado, height: ALTO };
    } else if (this.vertical) {
      const ancho = ALTO + this.anchoAbierto;
      r = { x: this.izquierda ? 0 : W - ancho, y: this.topPanelV, width: ancho, height: this.altoPanelV };
    } else {
      const alto = this.altoAbierto;
      r = { x: this.haciaDerecha ? this.x : this.x + this.anchoCerrado - this.anchoAbierto,
            y: this.haciaArriba ? this.cy + ALTO - alto : this.cy, width: this.anchoAbierto, height: alto };
    }
    return { x: Math.round(a.x + r.x), y: Math.round(a.y + r.y), width: Math.round(r.width), height: Math.round(r.height) };
  }

  // lo que la página necesita para dibujar la forma (y animarla) dentro de la ventana
  forma(ventanaCerrada) {
    const H = this.area.height;
    return {
      abierta: this.desplegada, ventanaCerrada: !!ventanaCerrada, moviendo: this.moviendo,
      vertical: this.vertical, borde: this.borde, haciaDerecha: this.haciaDerecha, haciaArriba: this.haciaArriba,
      pegadaArriba: !this.vertical && this.cy <= 0, pegadaAbajo: !this.vertical && this.cy + ALTO >= H,
      altoCerrado: ALTO, anchoCerrado: this.anchoCerrado, anchoAbierto: this.anchoAbierto, largoV: this.largoV,
      cerrada: { w: this.wC, h: this.hC, y: this.vertical ? this.cy - this.topPanelV : 0 },
    };
  }
  avisar(ventanaCerrada) {
    if (this.ventana) this.ventana.webContents.send("burbuja:forma", this.forma(ventanaCerrada ?? !this.desplegada));
  }
  ajustar() {
    if (!this.ventana) return;
    this.ventana.setBounds(this.limites());
  }

  abrir() {
    clearTimeout(this.encogiendo);
    if (this.desplegada) return;
    this.abierta = true;
    this.ajustar();
    this.avisar(false);
  }
  cerrar() {
    if (!this.abierta) return;
    this.abierta = false;
    this.avisar(false);         // la página anima el cierre (400 ms) y después se achica la ventana
    clearTimeout(this.encogiendo);
    this.encogiendo = setTimeout(() => this.encoger(), 450);
  }
  encoger() {
    if (this.desplegada) return;
    this.ajustar();
    this.avisar(true);
  }
  alto(h) {
    h = Math.ceil(h);
    if (h === this.altoCuerpo) return;
    this.altoCuerpo = h;
    if (this.desplegada) this.ajustar();
  }

  empezarMover() {
    this.moviendo = true;
    this.inicio = { x: this.x, y: this.cy };
    this.ajustar();
    this.avisar(true);
  }
  mover(dx, dy) {
    if (!this.moviendo) return;
    const a = this.area;
    this.cx = limitar(this.inicio.x + dx, 0, a.width - this.wC);
    this.cy = limitar(this.inicio.y + dy, 0, a.height - this.hC);
    this.ajustar();
  }
  // al soltar: pegada a un lado → pestaña vertical; si no → horizontal
  soltar() {
    if (!this.moviendo) return;
    const W = this.area.width, H = this.area.height;
    if (this.cx <= MARGEN_BORDE) { this.borde = "izquierda"; this.cx = 0; }
    else if (this.cx + this.wC >= W - MARGEN_BORDE) { this.borde = "derecha"; this.cx = W - ALTO; }
    else { this.borde = ""; this.cx = limitar(this.cx, 0, W - this.anchoCerrado); }
    this.cy = limitar(this.cy, 0, H - this.hC);
    this.moviendo = false;
    this.guardar();
    this.ajustar();
    this.avisar();
  }
  fabrica() {
    this.cx = null; this.cy = 0; this.borde = "";
    this.guardar();
    this.ajustar();
    this.avisar();
  }
  guardar() {
    const datos = leerJSON(POSICIONES);
    datos.capsulas = { ...(datos.capsulas || {}) };
    if (this.cx === null) delete datos.capsulas[this.nombre];
    else datos.capsulas[this.nombre] = { x: Math.round(this.cx), y: Math.round(this.cy), borde: this.borde };
    escribirJSON(POSICIONES, datos);
  }
  // la pantalla cambió (otro monitor, otra resolución): que siga dentro
  recolocar() {
    const a = this.area;
    if (this.cx !== null) this.cx = this.borde === "derecha" ? a.width - ALTO : limitar(this.cx, 0, a.width - this.wC);
    this.cy = limitar(this.cy, 0, a.height - this.hC);
    this.ajustar();
    this.avisar();
  }
  mostrar(si) {
    if (!this.ventana) return;
    if (si) this.ventana.showInactive(); else this.ventana.hide();
  }
}

// Una burbuja por grupo (Equipo, IA, Archivos); la lista sale del servicio (GET /api/burbujas,
// akari/grupos.py), así una pieza o un grupo nuevo aparece solo.
function pedirBurbujas() {
  return new Promise((ok) => {
    const req = http.get(URL + "api/burbujas", (r) => {
      let texto = "";
      r.on("data", (c) => (texto += c));
      r.on("end", () => {
        try {
          const lista = JSON.parse(texto).grupos;
          if (Array.isArray(lista) && lista.length) return ok(Object.fromEntries(lista.map((g) => [g.id, g])));
        } catch {}
        ok(BURBUJAS);
      });
    });
    req.on("error", () => ok(BURBUJAS));
    req.setTimeout(2000, () => { req.destroy(); ok(BURBUJAS); });
  });
}

async function crearBurbujas() {
  for (const [nombre, medidas] of Object.entries(await pedirBurbujas())) burbujas.set(nombre, new Burbuja(nombre, medidas));
  const recolocar = () => burbujas.forEach((b) => b.recolocar());
  screen.on("display-metrics-changed", recolocar);
  screen.on("display-added", recolocar);
  screen.on("display-removed", recolocar);
}
const deQuien = (e) => [...burbujas.values()].find((b) => b.ventana && b.ventana.webContents === e.sender);
const ACCIONES = {
  abrir: (b) => b.abrir(), cerrar: (b) => b.cerrar(),
  alto: (b, d) => b.alto(Number(d.alto) || 0),
  "mover-inicio": (b) => b.empezarMover(), mover: (b, d) => b.mover(Number(d.dx) || 0, Number(d.dy) || 0),
  soltar: (b) => b.soltar(), fabrica: (b) => b.fabrica(),
};
ipcMain.on("burbuja", (e, accion, datos) => {
  const b = deQuien(e);
  if (b && ACCIONES[accion]) ACCIONES[accion](b, datos || {});
});

// ------------------------------------------------------------ panel completo
function crearPanel() {
  const area = pantalla().workArea;
  const ancho = Math.min(460, area.width - 20), alto = Math.min(800, area.height - 60);
  panel = new BrowserWindow({
    width: ancho, height: alto, x: Math.round(area.x + (area.width - ancho) / 2), y: area.y + 52,
    minWidth: 380, minHeight: 480, show: false,
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
function autoarranqueActivo() {
  return LINUX ? fs.existsSync(AUTOARRANQUE) : app.getLoginItemSettings().openAtLogin;
}
function autoarranque(activar) {
  if (!LINUX) return app.setLoginItemSettings({ openAtLogin: activar });
  if (!activar) return fs.rmSync(AUTOARRANQUE, { force: true });
  const exe = process.env.APPIMAGE || process.execPath;
  let args = app.isPackaged ? "" : ` "${path.join(__dirname)}"`;
  // Ubuntu 23.10+ (AppArmor) bloquea el sandbox de Chromium en apps sin instalar
  try {
    if (fs.readFileSync("/proc/sys/kernel/apparmor_restrict_unprivileged_userns", "utf8").trim() === "1") args += " --no-sandbox";
  } catch {}
  fs.mkdirSync(path.dirname(AUTOARRANQUE), { recursive: true });
  fs.writeFileSync(AUTOARRANQUE, `[Desktop Entry]\nType=Application\nName=akari\nExec="${exe}"${args}\nIcon=${ICONO}\nX-GNOME-Autostart-enabled=true\n`);
}

function claudeConectado() {
  const linea = (leerJSON(AJUSTES_CLAUDE).statusLine || {}).command || "";
  return linea.includes("akari");
}

function crearBandeja() {
  bandeja = new Tray(nativeImage.createFromPath(ICONO).resize({ width: WINDOWS ? 16 : 22, height: WINDOWS ? 16 : 22 }));
  bandeja.setToolTip("akari");
  const menu = () => Menu.buildFromTemplate([
    { label: t("Abrir panel", "Open panel"), click: alternarPanel },
    {
      label: t("Mostrar las burbujas", "Show the bubbles"), type: "checkbox", checked: leerAjustes().burbujas !== false,
      click: (i) => { guardarAjustes({ burbujas: i.checked }); burbujas.forEach((b) => b.mostrar(i.checked)); },
    },
    { label: t("Devolver las burbujas a su sitio", "Put the bubbles back in place"), click: () => burbujas.forEach((b) => b.fabrica()) },
    { label: t("Iniciar con la sesión", "Start on login"), type: "checkbox", checked: autoarranqueActivo(), click: (i) => autoarranque(i.checked) },
    {
      label: t("Conectar con Claude Code (límites)", "Connect to Claude Code (limits)"), type: "checkbox", checked: claudeConectado(),
      click: (i) => akari(i.checked ? "conectar-claude" : "desconectar-claude").on("exit", () => bandeja.setContextMenu(menu())),
    },
    { type: "separator" },
    { label: t("Salir", "Quit"), click: () => app.quit() },
  ]);
  bandeja.setContextMenu(menu());
  bandeja.on("click", alternarPanel);
  bandeja.on("right-click", () => bandeja.setContextMenu(menu()));
}

ipcMain.on("alternar-panel", alternarPanel);
app.on("second-instance", (_e, argv) => {
  if (argv.includes("--panel")) return panel ? (panel.show(), panel.focus()) : crearPanel();
  if (leerAjustes().burbujas === false) {
    guardarAjustes({ burbujas: true });
    burbujas.forEach((b) => b.mostrar(true));
  }
  alternarPanel();
});
app.on("window-all-closed", (e) => { if (!SOLO_PANEL) e.preventDefault?.(); });
app.on("before-quit", () => { if (servicio) servicio.kill(); });

app.whenReady().then(async () => {
  await asegurarServicio();
  if (SOLO_PANEL) return crearPanel();
  // en Windows y macOS la primera vez queda para iniciar con la sesión (se cambia en la bandeja)
  if (!LINUX && leerAjustes().autoarranque === undefined) {
    autoarranque(true);
    guardarAjustes({ autoarranque: true });
  }
  // las ventanas transparentes de Linux salen negras si se crean antes de que el compositor responda
  setTimeout(crearBurbujas, LINUX ? 300 : 0);
  crearBandeja();
});
