"""Herramientas de terminal útiles para quien usa Claude Code o Codex: detecta cuáles están y las
instala con lo que haya en el equipo (Linux y Windows).

Sin contraseña se instala con Homebrew, uv, pipx, npm (si su carpeta global es del usuario), cargo,
go o winget. Si la única forma es el gestor del sistema (pacman, apt, dnf, zypper) hace falta sudo:
akari no la pide, muestra el comando para copiarlo o lo abre en una terminal.
"""
import os
import subprocess
import threading
import time

from .comun import SIN_VENTANA, WINDOWS, buscar, copiar, entorno_completo, notificar, t, terminal
from .habilidades import conectores_mcp

# metodos: gestor -> paquete. «cargo-git» = cargo install --git <repo>. Se prueba en el orden de ORDEN.
HERRAMIENTAS = [
    {"id": "gitleaks", "icono": "key_off", "binarios": ["gitleaks"], "web": "https://github.com/gitleaks/gitleaks",
     "detalle": ("Busca claves y contraseñas filtradas en el código y en el historial de git antes de subirlo.",
                 "Finds leaked keys and passwords in code and git history before you push."),
     "metodos": {"brew": "gitleaks", "winget": "Gitleaks.Gitleaks", "pacman": "gitleaks", "apt": "gitleaks",
                 "dnf": "gitleaks", "go": "github.com/zricethezav/gitleaks/v8@latest"}},
    {"id": "semgrep", "icono": "bug_report", "binarios": ["semgrep"], "web": "https://github.com/semgrep/semgrep",
     "detalle": ("Revisa el código con reglas y encuentra errores y fallas de seguridad (SAST).",
                 "Scans code with rules to find bugs and security issues (SAST)."),
     "metodos": {"brew": "semgrep", "uv": "semgrep", "pipx": "semgrep"}},
    {"id": "trivy", "icono": "shield", "binarios": ["trivy"], "web": "https://trivy.dev/latest/getting-started/installation/",
     "detalle": ("Escanea dependencias, imágenes de Docker y configuraciones en busca de vulnerabilidades.",
                 "Scans dependencies, Docker images and configs for vulnerabilities."),
     "metodos": {"brew": "trivy", "winget": "AquaSecurity.Trivy", "pacman": "trivy", "zypper": "trivy"}},
    {"id": "ast-grep", "icono": "account_tree", "binarios": ["ast-grep"], "web": "https://ast-grep.github.io",
     "detalle": ("Busca y reemplaza código por su estructura, no por texto: ideal para refactorizar con un agente.",
                 "Searches and rewrites code by structure, not text: great for refactoring with an agent."),
     "metodos": {"brew": "ast-grep", "uv": "ast-grep-cli", "pipx": "ast-grep-cli", "npm": "@ast-grep/cli",
                 "pacman": "ast-grep", "cargo": "ast-grep"}},
    {"id": "repomix", "icono": "inventory_2", "binarios": ["repomix"], "web": "https://github.com/yamadashy/repomix",
     "detalle": ("Empaqueta un repositorio entero en un solo archivo para dárselo a una IA.",
                 "Packs a whole repository into one file to hand to an AI."),
     "metodos": {"brew": "repomix", "npm": "repomix"}},
    {"id": "ccusage", "icono": "receipt_long", "binarios": ["ccusage"], "web": "https://github.com/ryoppippi/ccusage",
     "detalle": ("Cuánto gastaste en Claude Code por día, mes o sesión, leyendo sus registros.",
                 "How much you spent in Claude Code per day, month or session, from its logs."),
     "metodos": {"npm": "ccusage"}},
    {"id": "rtk", "icono": "compress", "binarios": ["rtk"], "web": "https://github.com/rtk-ai/rtk",
     "detalle": ("Resume la salida de los comandos para que Claude Code gaste mucho menos tokens (luego: rtk init -g).",
                 "Trims command output so Claude Code spends far fewer tokens (then: rtk init -g)."),
     "metodos": {"brew": "rtk", "cargo-git": "https://github.com/rtk-ai/rtk"}},
    {"id": "context7", "icono": "menu_book", "mcp": True, "web": "https://context7.com",
     "detalle": ("Conector MCP: documentación al día de miles de librerías para Claude Code y Codex.",
                 "MCP connector: up-to-date docs for thousands of libraries in Claude Code and Codex.")},
]
# primero lo que no pide contraseña; los gestores del sistema al final (con sudo)
ORDEN = ["brew", "winget", "uv", "pipx", "npm", "pacman", "apt", "dnf", "zypper", "cargo", "cargo-git", "go"]
SISTEMA = {"pacman", "apt", "dnf", "zypper"}
INTERVALO = 30
CONTEXT7_URL = "https://mcp.context7.com/mcp"


def _gestor(nombre):
    """Ruta del gestor de paquetes `nombre` si está en este equipo."""
    exe = {"cargo-git": "cargo", "apt": "apt-get"}.get(nombre, nombre)
    if WINDOWS and nombre in SISTEMA | {"brew"}:
        return None
    if not WINDOWS and nombre == "winget":
        return None
    if nombre == "uv":
        from .extras import _uv
        return _uv()
    return buscar(exe)


def _npm_sin_sudo(npm):
    """¿npm instala global sin contraseña? (en Linux con Node del sistema el prefijo es /usr)."""
    if WINDOWS:
        return True
    try:
        r = subprocess.run([npm, "prefix", "-g"], capture_output=True, text=True, timeout=10, env=entorno_completo())
        return os.access(r.stdout.strip() or "/usr", os.W_OK)
    except (OSError, subprocess.TimeoutExpired):
        return False


_hay_paquete = {}


def _en_repos(gestor, paquete):
    """¿El gestor del sistema tiene el paquete? (apt y pacman se pueden consultar sin red)."""
    clave = (gestor, paquete)
    if clave not in _hay_paquete:
        orden = {"apt": ["apt-cache", "show", paquete], "pacman": ["pacman", "-Si", paquete]}.get(gestor)
        if not orden:
            _hay_paquete[clave] = True
        else:
            try:
                r = subprocess.run(orden, capture_output=True, timeout=15)
                _hay_paquete[clave] = r.returncode == 0 and bool(r.stdout.strip())
            except (OSError, subprocess.TimeoutExpired):
                _hay_paquete[clave] = False
    return _hay_paquete[clave]


def orden_de(gestor, paquete, exe):
    """(orden como lista, necesita sudo)."""
    if gestor == "brew":
        return [exe, "install", paquete], False
    if gestor == "winget":
        return [exe, "install", "-e", "--id", paquete, "--silent", "--accept-package-agreements",
                "--accept-source-agreements"], False
    if gestor == "uv":
        return [exe, "tool", "install", paquete], False
    if gestor == "pipx":
        return [exe, "install", paquete], False
    if gestor == "npm":
        sudo = not _npm_sin_sudo(exe)
        return (["sudo"] if sudo else []) + [exe, "install", "-g", paquete], sudo
    if gestor == "cargo":
        return [exe, "install", "--locked", paquete], False
    if gestor == "cargo-git":
        return [exe, "install", "--git", paquete], False
    if gestor == "go":
        return [exe, "install", paquete], False
    if gestor == "pacman":
        return ["sudo", "pacman", "-S", "--needed", paquete], True
    if gestor == "apt":
        return ["sudo", "apt", "install", "-y", paquete], True
    if gestor == "dnf":
        return ["sudo", "dnf", "install", "-y", paquete], True
    if gestor == "zypper":
        return ["sudo", "zypper", "install", "-y", paquete], True
    return None, False


def metodo(h):
    """Cómo instalar `h` aquí: {"gestor", "orden", "texto", "sudo"} o None si no hay forma."""
    if h.get("mcp"):
        return None
    for gestor in ORDEN:
        paquete = h["metodos"].get(gestor)
        exe = _gestor(gestor) if paquete else None
        if not exe or (gestor in SISTEMA and not _en_repos(gestor, paquete)):
            continue
        orden, sudo = orden_de(gestor, paquete, exe)
        partes = list(orden)
        i = 1 if partes[0] == "sudo" else 0
        partes[i] = os.path.basename(partes[i])         # «brew install …», no la ruta entera
        texto = " ".join(_comillas(x) for x in partes)
        return {"gestor": gestor, "orden": orden, "texto": texto, "sudo": sudo}
    return None


def _ordenes_mcp():
    """Para context7: (agente, orden) de cada agente que esté instalado."""
    ordenes = []
    claude, codex = buscar("claude"), buscar("codex")
    if claude:
        ordenes.append(("claude", [claude, "mcp", "add", "-s", "user", "--transport", "http", "context7", CONTEXT7_URL]))
    if codex:
        npx = "npx.cmd" if WINDOWS else "npx"
        ordenes.append(("codex", [codex, "mcp", "add", "context7", "--", npx, "-y", "@upstash/context7-mcp"]))
    return ordenes


class MonitorHerramientas:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.tareas = {}            # id -> {"estado": "instalando"|"error"|"listo", "mensaje"}
        self.estado = {}
        self._ultimo = None
        self._siguiente = 0

    def paso(self):
        if time.time() >= self._siguiente:
            self.calcular()

    def calcular(self):
        self._siguiente = time.time() + INTERVALO
        mcp = {(c["nombre"].lower(), c["agente"]) for c in conectores_mcp()}
        lista = []
        for h in HERRAMIENTAS:
            if h.get("mcp"):
                en = [a for a in ("claude", "codex") if (h["id"], a) in mcp]
                agentes = [a for a, _ in _ordenes_mcp()]
                instalada = bool(en) and set(agentes) <= set(en)
                m = None if instalada or not agentes else {"gestor": "mcp", "sudo": False,
                                                          "texto": " · ".join(f"{a} mcp add context7" for a in agentes if a not in en)}
                ruta, extra = None, (t("En ", "In ") + t(" y ", " & ").join(a.capitalize() for a in en)) if en else ""
                if not agentes:
                    extra = t("Necesita Claude Code o Codex", "Needs Claude Code or Codex")
            else:
                ruta = next((r for r in map(buscar, h["binarios"]) if r), None)
                instalada, extra = bool(ruta), ""
                m = None if instalada else metodo(h)
            lista.append({"id": h["id"], "nombre": h["id"], "icono": h["icono"], "detalle": t(*h["detalle"]),
                          "web": h["web"], "instalada": instalada, "ruta": ruta, "nota": extra,
                          "metodo": {k: v for k, v in m.items() if k != "orden"} if m else None,
                          "tarea": self.tareas.get(h["id"])})
        estado = {"lista": lista, "instaladas": sum(x["instalada"] for x in lista), "total": len(lista)}
        if estado != self._ultimo:
            self._ultimo = estado
            self.estado = estado
            self.al_cambiar()

    def _h(self, ident):
        return next((h for h in HERRAMIENTAS if h["id"] == ident), None)

    def accion(self, datos):
        h = self._h(str(datos.get("id")))
        accion = str(datos.get("accion"))
        if not h:
            return False, "?"
        if accion == "instalar":
            if (self.tareas.get(h["id"]) or {}).get("estado") == "instalando":
                return False, t("Ya se está instalando.", "Already installing.")
            if h.get("mcp"):
                threading.Thread(target=self._instalar_mcp, args=(h,), daemon=True).start()
                return True, ""
            m = metodo(h)
            if not m:
                return False, t("No encontré cómo instalarla aquí: mira su página.", "No way to install it here: see its page.")
            if m["sudo"]:
                return False, t("Necesita tu contraseña: cópialo o ábrelo en una terminal.", "Needs your password: copy it or open it in a terminal.")
            threading.Thread(target=self._instalar, args=(h, m), daemon=True).start()
            return True, ""
        if accion in ("copiar", "terminal"):
            m = metodo(h)
            if not m:
                return False, "?"
            if accion == "copiar":
                return (True, t("Copiado.", "Copied.")) if copiar(m["texto"]) else (False, m["texto"])
            ok = terminal(" ".join(_comillas(x) for x in m["orden"]), h["id"])
            self._siguiente = 0
            return (True, "") if ok else (False, t("No encontré una terminal. Copia el comando.", "No terminal found. Copy the command."))
        return False, "?"

    def _correr(self, h, orden):
        self.tareas[h["id"]] = {"estado": "instalando", "mensaje": ""}
        self.calcular()
        try:
            r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
                               env=entorno_completo(), stdin=subprocess.DEVNULL, **SIN_VENTANA)
            ok = r.returncode == 0
            mensaje = "" if ok else ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1][:200]
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, mensaje = False, str(e)[:200]
        return ok, mensaje

    def _instalar(self, h, m):
        ok, mensaje = self._correr(h, m["orden"])
        self._terminar(h, ok, mensaje)

    def _instalar_mcp(self, h):
        mensajes, todo = [], True
        for agente, orden in _ordenes_mcp():
            ok, mensaje = self._correr(h, orden)
            if not ok and "already exists" not in mensaje:
                todo = False
                mensajes.append(f"{agente}: {mensaje}")
        self._terminar(h, todo, " · ".join(mensajes))

    def _terminar(self, h, ok, mensaje):
        self.tareas[h["id"]] = {"estado": "listo" if ok else "error", "mensaje": mensaje}
        if ok:
            notificar(t("Herramienta instalada", "Tool installed"), h["id"])
        self.calcular()


def _comillas(x):
    if WINDOWS:
        return f"'{x}'" if " " in x else x
    import shlex
    return shlex.quote(x)


if __name__ == "__main__":      # python -m akari.herramientas: qué hay y cómo se instalaría
    m = MonitorHerramientas(lambda: None)
    m.calcular()
    for x in m.estado["lista"]:
        print(f"{x['id']:10} {'✓' if x['instalada'] else '·'} {(x['metodo'] or {}).get('texto', x['ruta'] or '')}")
