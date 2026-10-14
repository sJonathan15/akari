"""Habilidades (skills) y conectores MCP de Claude Code y Codex.

  * Detecta lo instalado: ~/.claude/skills, skills de plugins, $CODEX_HOME/skills y los
    servidores MCP de ~/.claude.json y ~/.codex/config.toml.
  * Cuenta cuántas veces Claude usó cada skill en los últimos 7 días.
  * Recomienda 10 habilidades útiles para el día a día (catalogo.json) y las instala
    descargando solo su carpeta desde el repositorio original de GitHub.
"""
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .comun import IDIOMA, escribir_json, leer_json, notificar, t, tiene
from .ia import CLAUDE_DIR, CLAUDE_JSON, CODEX_DIR, Lector, marca_tiempo

CATALOGO = Path(__file__).resolve().parent / "catalogo.json"
MARCA = ".akari.json"                 # akari deja esto en lo que instala (y solo borra eso)
LIMITE_ARCHIVOS, LIMITE_BYTES = 600, 60 * 1024 * 1024
INTERVALO = 20


def carpetas_skills():
    return {"claude": CLAUDE_DIR / "skills", "codex": CODEX_DIR / "skills"}


def agentes():
    return {"claude": CLAUDE_DIR.exists() or tiene("claude"), "codex": CODEX_DIR.exists() or tiene("codex")}


def frontmatter(ruta):
    """name y description del encabezado YAML de un SKILL.md (sin depender de PyYAML)."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")[:6000]
    except OSError:
        return {}
    m = re.match(r"---\s*\n(.*?)\n---", texto, re.S)
    datos = {}
    for linea in (m.group(1) if m else "").splitlines():
        c = re.match(r"(name|description):\s*(.*)", linea)
        if c:
            datos[c.group(1)] = c.group(2).strip().strip("\"'")
    return datos


def corto(texto, largo=140):
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= largo else texto[: largo - 1].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------- lo instalado

def instaladas():
    lista = {}
    for agente, carpeta in carpetas_skills().items():
        if not carpeta.is_dir():
            continue
        for skill in sorted(carpeta.iterdir()):
            if skill.name.startswith(".") or not (skill / "SKILL.md").is_file():
                continue
            fm = frontmatter(skill / "SKILL.md")
            ident = fm.get("name") or skill.name
            e = lista.setdefault(ident, {"id": ident, "nombre": ident, "descripcion": corto(fm.get("description")),
                                         "agentes": [], "origen": "usuario", "carpetas": {}})
            e["agentes"].append(agente)
            e["carpetas"][agente] = skill.name
            if (skill / MARCA).exists():
                e["origen"] = "akari"
    # skills que vienen dentro de plugins de Claude Code
    cache = CLAUDE_DIR / "plugins" / "cache"
    if cache.is_dir():
        for md in cache.glob("*/*/*/skills/*/SKILL.md"):
            fm = frontmatter(md)
            ident = fm.get("name") or md.parent.name
            if ident not in lista:
                lista[ident] = {"id": ident, "nombre": ident, "descripcion": corto(fm.get("description")),
                                "agentes": ["claude"], "origen": "plugin", "carpetas": {}}
    return lista


def conectores_mcp():
    lista = [{"nombre": n, "agente": "claude"} for n in (leer_json(CLAUDE_JSON).get("mcpServers") or {})]
    try:
        import tomllib
        with open(CODEX_DIR / "config.toml", "rb") as f:
            lista += [{"nombre": n, "agente": "codex"} for n in (tomllib.load(f).get("mcp_servers") or {})]
    except (OSError, ValueError, ImportError):
        pass
    return lista


class UsosClaude(Lector):
    """Cuenta las llamadas a la herramienta Skill en los registros de Claude Code."""

    def __init__(self):
        super().__init__(CLAUDE_DIR / "projects")
        self.usos = []          # (t, skill)

    def procesar(self, archivo, lineas):
        cambio = False
        for linea in lineas:
            if b'"Skill"' not in linea or b'"tool_use"' not in linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            ts = marca_tiempo(d.get("timestamp")) or time.time()
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                    nombre = str((b.get("input") or {}).get("skill") or "").split(":")[-1]
                    if nombre:
                        self.usos.append((ts, nombre))
                        cambio = True
        corte = time.time() - 7 * 86400
        self.usos = [u for u in self.usos if u[0] >= corte]
        return cambio

    def conteo(self):
        return Counter(n for _, n in self.usos)


# --------------------------------------------------------------- instalar

def pedir(url, binario=False):
    cabeceras = {"User-Agent": "akari/0.1 (+https://github.com/sJonathan15/akari)"}
    if os.environ.get("GITHUB_TOKEN") and "api.github.com" in url:
        cabeceras["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras), timeout=60) as r:
        datos = r.read()
    return datos if binario else json.loads(datos)


def descargar_carpeta(fuente, destino):
    """Baja solo la carpeta `ruta` del repositorio (árbol de git + archivos sueltos)."""
    repo, ruta, ref = fuente["repo"], fuente["ruta"].strip("/"), fuente.get("ref", "main")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or ".." in ruta or not re.fullmatch(r"[\w./-]+", ref):
        raise ValueError("fuente inválida")
    arbol = pedir(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1")
    archivos = [a for a in arbol.get("tree", []) if a.get("type") == "blob" and a["path"].startswith(ruta + "/")]
    if not archivos:
        raise ValueError(t("No encontré esa carpeta en el repositorio.", "That folder was not found in the repository."))
    if len(archivos) > LIMITE_ARCHIVOS or sum(a.get("size", 0) for a in archivos) > LIMITE_BYTES:
        raise ValueError(t("La habilidad es demasiado grande.", "The skill is too large."))
    temporal = destino.with_name(f".{destino.name}.descargando")
    shutil.rmtree(temporal, ignore_errors=True)
    temporal.mkdir(parents=True)
    raiz = temporal.resolve()

    def bajar(a):
        relativa = a["path"][len(ruta) + 1:]
        final = (temporal / relativa).resolve()
        if raiz not in final.parents:          # nada fuera de la carpeta de la skill
            raise ValueError("ruta inválida")
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(pedir(f"https://raw.githubusercontent.com/{repo}/{ref}/{a['path']}", binario=True))

    try:
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(bajar, archivos))
        if not (temporal / "SKILL.md").is_file():
            raise ValueError(t("La carpeta no tiene SKILL.md.", "The folder has no SKILL.md."))
        escribir_json(temporal / MARCA, {"fuente": fuente, "instalado": time.time()})
        shutil.rmtree(destino, ignore_errors=True)
        temporal.rename(destino)
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    return len(archivos)


# --------------------------------------------------------------- monitor

class MonitorHabilidades:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.usos = UsosClaude()
        self.tareas = {}            # id -> {estado: instalando|listo|error, mensaje}
        self.estado = {}
        self._ultimo = 0

    def catalogo(self):
        return leer_json(CATALOGO, {"recomendadas": [], "mas": []})

    def paso(self):
        cambio = self.usos.actualizar()
        if cambio or time.time() - self._ultimo > INTERVALO:
            self.calcular()

    def calcular(self):
        self._ultimo = time.time()
        hay = agentes()
        puestas = instaladas()
        conteo = self.usos.conteo()

        def tarjeta(e):
            permitidos = [a for a in e.get("agentes", ["claude", "codex"]) if hay.get(a)]
            ident = e["id"]
            en = puestas.get(ident, {}).get("agentes", [])
            return {
                "id": ident, "icono": e.get("icono", "extension"),
                "nombre": e["nombre"].get(IDIOMA) or e["nombre"]["en"],
                "detalle": e["detalle"].get(IDIOMA) or e["detalle"]["en"],
                "licencia": e.get("licencia"), "repo": e["fuente"]["repo"],
                "agentes": permitidos, "instalada_en": en,
                "falta_en": [a for a in permitidos if a not in en],
                "usos_7d": conteo.get(ident, 0),
                "tarea": self.tareas.get(ident),
            }

        cat = self.catalogo()
        lista = sorted(puestas.values(), key=lambda s: (-conteo.get(s["id"], 0), s["nombre"].lower()))
        estado = {
            "agentes": hay,
            "instaladas": [{**{k: v for k, v in s.items() if k != "carpetas"}, "usos_7d": conteo.get(s["id"], 0)}
                           for s in lista],
            "recomendadas": [tarjeta(e) for e in cat.get("recomendadas", [])],
            "mas": [tarjeta(e) for e in cat.get("mas", [])],
            "mcp": conectores_mcp(),
            "usos_7d": sum(conteo.values()),
        }
        estado["total"] = len(estado["instaladas"])
        estado["recomendadas_instaladas"] = sum(1 for r in estado["recomendadas"] if r["instalada_en"])
        if estado != self.estado:
            self.estado = estado
            self.al_cambiar()

    # ------------------------------------------------------------ acciones

    def accion(self, ident, accion, destino=None):
        cat = self.catalogo()
        entrada = next((e for e in cat.get("recomendadas", []) + cat.get("mas", []) if e["id"] == ident), None)
        hay = agentes()
        if accion == "instalar":
            if not entrada:
                return False, t("Esa habilidad no está en el catálogo.", "That skill is not in the catalog.")
            if (self.tareas.get(ident) or {}).get("estado") == "instalando":
                return False, t("Ya se está instalando.", "Already installing.")
            permitidos = [a for a in entrada.get("agentes", ["claude", "codex"]) if hay.get(a)]
            elegidos = [destino] if destino in permitidos else permitidos
            if not elegidos:
                return False, t("No encontré Claude Code ni Codex en este equipo.", "Neither Claude Code nor Codex was found.")
            self.tareas[ident] = {"estado": "instalando", "mensaje": t("Descargando…", "Downloading…")}
            threading.Thread(target=self._instalar, args=(entrada, elegidos), daemon=True).start()
            self.calcular()
            return True, t("Instalando…", "Installing…")
        if accion == "desinstalar":
            borradas = 0
            for agente, carpeta in carpetas_skills().items():
                if destino and agente != destino:
                    continue
                skill = carpeta / ident
                # solo lo que instaló akari: nunca se borra una skill propia del usuario
                if (skill / MARCA).is_file() and skill.resolve().parent == carpeta.resolve():
                    shutil.rmtree(skill)
                    borradas += 1
            self.tareas.pop(ident, None)
            self.calcular()
            return (True, t("Desinstalada.", "Uninstalled.")) if borradas else \
                (False, t("Solo puedo quitar lo que instaló akari.", "Only skills installed by akari can be removed."))
        return False, t("Acción desconocida.", "Unknown action.")

    def _instalar(self, entrada, elegidos):
        ident = entrada["id"]
        try:
            carpetas = carpetas_skills()
            primero = None
            for agente in elegidos:
                destino = carpetas[agente] / ident
                if (destino / "SKILL.md").exists() and not (destino / MARCA).exists():
                    continue          # el usuario ya tiene una propia con ese nombre: no se toca
                destino.parent.mkdir(parents=True, exist_ok=True)
                if primero is None:
                    n = descargar_carpeta(entrada["fuente"], destino)
                    primero = destino
                else:
                    shutil.rmtree(destino, ignore_errors=True)
                    shutil.copytree(primero, destino)
            nombre = entrada["nombre"].get(IDIOMA) or entrada["nombre"]["en"]
            self.tareas[ident] = {"estado": "listo", "mensaje": t("Instalada", "Installed"), "t": time.time()}
            notificar(t(f"Habilidad instalada: {nombre}", f"Skill installed: {nombre}"),
                      t("Ya puedes pedírsela a tu IA en una sesión nueva.", "Ask your AI for it in a new session."))
        except (OSError, ValueError, urllib.error.URLError) as e:
            self.tareas[ident] = {"estado": "error", "mensaje": str(e)[:160], "t": time.time()}
        self.calcular()
