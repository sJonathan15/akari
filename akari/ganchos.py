"""Conectar el cerebro con Claude Code y Codex (opcional, un botón para poner y otro para quitar).

Claude Code  ganchos en ~/.claude/settings.json:
               SessionStart → `akari cerebro sesion-inicio`: un resumen corto (pendientes, últimas
                              sesiones y «usa `akari cerebro buscar` antes de buscar con find»);
               SessionEnd   → `akari cerebro sesion-fin`: la sesión va a la memoria.
             Respaldo settings.json.bak-akari (el mismo de la línea de estado). Al quitar se sacan solo
             los ganchos de akari; si nadie más tocó el archivo, queda byte a byte como estaba.
Codex        un bloque entre marcas en el AGENTS.md global (~/.codex/AGENTS.md); al quitar se borra el
             bloque (y el archivo, si lo creó akari y quedó vacío).
"""
import json
import os
import shutil
import sys
from pathlib import Path

from . import cerebro as C
from .comun import CONFIG, HOME, RAIZ, WINDOWS, escribir_json, leer_json, t
from .ia import CLAUDE_DIR, CODEX_DIR

AJUSTES_CLAUDE = CLAUDE_DIR / "settings.json"
AGENTS_CODEX = CODEX_DIR / "AGENTS.md"
ESTADO = CONFIG / "ganchos.json"            # cómo estaban los archivos antes de conectar
EVENTOS = {"SessionStart": "sesion-inicio", "SessionEnd": "sesion-fin"}
INICIO_CODEX, FIN_CODEX = "<!-- akari-cerebro -->", "<!-- /akari-cerebro -->"


def orden(*args):
    """Cómo llamar a akari desde la terminal de un agente (con barras normales: anda en cmd y Git Bash)."""
    if shutil.which("akari"):
        return " ".join(["akari", *args])
    lanzador = HOME / ".local" / "bin" / "akari"
    if not WINDOWS and lanzador.exists():
        return " ".join([str(lanzador), *args])
    python = sys.executable.replace("\\", "/")
    return " ".join([f'"{python}"', f'"{(RAIZ / "bin" / "akari.py").as_posix()}"', *args])


def _nuestro(gancho):
    return "cerebro sesion-" in str(gancho.get("command", "")) and "akari" in str(gancho.get("command", ""))


# ---------------------------------------------------------------- Claude Code

def claude_conectado():
    ganchos = (leer_json(AJUSTES_CLAUDE).get("hooks") or {}) if AJUSTES_CLAUDE.exists() else {}
    return all(any(_nuestro(h) for g in ganchos.get(ev) or [] if isinstance(g, dict) for h in g.get("hooks") or [])
               for ev in EVENTOS)


def conectar_claude():
    if claude_conectado():
        return t("Claude Code ya usa el cerebro.", "Claude Code already uses the brain.")
    original = AJUSTES_CLAUDE.read_text(encoding="utf-8") if AJUSTES_CLAUDE.exists() else None
    datos = json.loads(original) if original and original.strip() else {}
    if not isinstance(datos, dict):
        return t("settings.json de Claude Code no es válido: no lo toqué.", "Claude Code's settings.json is invalid: left untouched.")
    if original is not None:
        respaldo = AJUSTES_CLAUDE.with_name(AJUSTES_CLAUDE.name + ".bak-akari")
        if not respaldo.exists():
            shutil.copy2(AJUSTES_CLAUDE, respaldo)
    estado = leer_json(ESTADO)
    estado["claude"] = {"original": original}
    escribir_json(ESTADO, estado)
    ganchos = datos.setdefault("hooks", {})
    for evento, sub in EVENTOS.items():
        lista = ganchos.setdefault(evento, [])
        lista.append({"hooks": [{"type": "command", "command": orden("cerebro", sub), "timeout": 30}]})
    escribir_json(AJUSTES_CLAUDE, datos)
    return t("Claude Code conectado al cerebro (respaldo: settings.json.bak-akari).",
             "Claude Code connected to the brain (backup: settings.json.bak-akari).")


def desconectar_claude():
    if not AJUSTES_CLAUDE.exists():
        return t("Claude Code no tenía el cerebro.", "Claude Code didn't have the brain.")
    datos = leer_json(AJUSTES_CLAUDE)
    ganchos = datos.get("hooks")
    if not isinstance(ganchos, dict):
        return t("Claude Code no tenía el cerebro.", "Claude Code didn't have the brain.")
    for evento in list(ganchos):
        lista = []
        for g in ganchos[evento] if isinstance(ganchos[evento], list) else []:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                quedan = [h for h in g["hooks"] if not _nuestro(h)]
                if not quedan and g["hooks"]:
                    continue
                g = {**g, "hooks": quedan}
            lista.append(g)
        if lista:
            ganchos[evento] = lista
        else:
            del ganchos[evento]
    if not ganchos:
        del datos["hooks"]
    estado = leer_json(ESTADO)
    original = (estado.get("claude") or {}).get("original", False)
    if original is None and not datos:              # el archivo lo creó akari
        AJUSTES_CLAUDE.unlink()
    elif isinstance(original, str) and _igual(original, datos):
        AJUSTES_CLAUDE.write_text(original, encoding="utf-8")       # tal cual, byte a byte
    else:
        escribir_json(AJUSTES_CLAUDE, datos)
    estado.pop("claude", None)
    escribir_json(ESTADO, estado)
    return t("Claude Code ya no usa el cerebro; settings.json quedó como estaba.",
             "Claude Code no longer uses the brain; settings.json is back as it was.")


def _igual(texto, datos):
    try:
        return (json.loads(texto) if texto.strip() else {}) == datos
    except ValueError:
        return False


# ---------------------------------------------------------------- Codex

def bloque_codex():
    b = C.boveda()
    como = (b / "Como-me-organizo.md") if b else None
    return "\n".join([
        INICIO_CODEX,
        "## " + t("Cerebro de akari (mapa de esta computadora y memoria de sesiones)",
                  "akari brain (map of this computer and session memory)"),
        t("- Antes de buscar archivos con find, ls o Get-ChildItem, usa `{0} buscar <palabras>` (o `donde <nombre>`).",
          "- Before searching for files with find, ls or Get-ChildItem, use `{0} buscar <words>` (or `donde <name>`).").format(orden("cerebro")),
        t("- Para saber en qué se quedó: `{0} sesiones` y `{0} pendientes`; anota con `{0} nota <texto>`.",
          "- To know where things were left: `{0} sesiones` and `{0} pendientes`; note with `{0} nota <text>`.").format(orden("cerebro")),
        (t(f"- Cómo se organiza esta persona: `{como}`", f"- How this person organizes things: `{como}`") if como else ""),
        t("- El cerebro nunca mueve ni cambia archivos; tú tampoco los muevas sin pedir permiso.",
          "- The brain never moves or changes files; don't move them without asking either."),
        FIN_CODEX,
    ]).replace("\n\n", "\n")


def codex_conectado():
    try:
        return INICIO_CODEX in AGENTS_CODEX.read_text(encoding="utf-8")
    except OSError:
        return False


def conectar_codex():
    original = AGENTS_CODEX.read_text(encoding="utf-8") if AGENTS_CODEX.exists() else None
    if not codex_conectado():
        estado = leer_json(ESTADO)
        estado["codex"] = {"original": original}
        escribir_json(ESTADO, estado)
    texto = _sin_bloque(original or "")
    nuevo = (texto.rstrip("\n") + "\n\n" if texto.strip() else "") + bloque_codex() + "\n"
    AGENTS_CODEX.parent.mkdir(parents=True, exist_ok=True)
    AGENTS_CODEX.write_text(nuevo, encoding="utf-8")
    return t("Codex conectado al cerebro (AGENTS.md global).", "Codex connected to the brain (global AGENTS.md).")


def _sin_bloque(texto):
    i = texto.find(INICIO_CODEX)
    j = texto.find(FIN_CODEX, i)
    if i < 0 or j < 0:
        return texto
    return texto[:i].rstrip("\n") + ("\n" if texto[:i].strip() else "") + texto[j + len(FIN_CODEX):].lstrip("\n")


def desconectar_codex():
    if not codex_conectado():
        return t("Codex no tenía el cerebro.", "Codex didn't have the brain.")
    texto = _sin_bloque(AGENTS_CODEX.read_text(encoding="utf-8"))
    estado = leer_json(ESTADO)
    original = (estado.get("codex") or {}).get("original", False)
    if original is None and not texto.strip():          # lo creó akari
        AGENTS_CODEX.unlink()
    elif isinstance(original, str) and texto.rstrip("\n") == original.rstrip("\n"):
        AGENTS_CODEX.write_text(original, encoding="utf-8")         # tal cual estaba
    else:
        AGENTS_CODEX.write_text(texto, encoding="utf-8")
    estado.pop("codex", None)
    escribir_json(ESTADO, estado)
    return t("Codex ya no usa el cerebro.", "Codex no longer uses the brain.")


# ---------------------------------------------------------------- todo junto

def estado():
    return {"claude": claude_conectado(), "codex": codex_conectado(),
            "claude_instalado": CLAUDE_DIR.exists(), "codex_instalado": CODEX_DIR.exists()}


def conectar(agente="todos"):
    mensajes = []
    if agente in ("claude", "todos") and (CLAUDE_DIR.exists() or agente == "claude"):
        mensajes.append(conectar_claude())
    if agente in ("codex", "todos") and (CODEX_DIR.exists() or agente == "codex"):
        mensajes.append(conectar_codex())
    return " ".join(mensajes) or t("No encontré Claude Code ni Codex en este equipo.", "Neither Claude Code nor Codex found.")


def desconectar(agente="todos"):
    mensajes = []
    if agente in ("claude", "todos"):
        mensajes.append(desconectar_claude())
    if agente in ("codex", "todos"):
        mensajes.append(desconectar_codex())
    return " ".join(mensajes)


# ---------------------------------------------------------------- lo que corren los ganchos

def _entrada():
    try:
        datos = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        return datos if isinstance(datos, dict) else {}
    except (ValueError, OSError):
        return {}


def contexto_inicio(cwd=None):
    """El texto corto que ve Claude Code al empezar una sesión."""
    if not C.configurado():
        return ""
    cmd = orden("cerebro")
    lineas = [t("Cerebro de akari: mapa de esta computadora y memoria de sesiones (nunca mueve ni cambia archivos).",
                "akari brain: map of this computer and session memory (never moves or changes files)."),
              t(f"- Antes de buscar archivos con find/ls, usa: {cmd} buscar <palabras>  (también: donde <nombre>, sesiones, "
                f"proyectos, pendiente <texto>, hecho <n>, nota <texto>)",
                f"- Before searching for files with find/ls, use: {cmd} buscar <words>  (also: donde <name>, sesiones, "
                f"proyectos, pendiente <text>, hecho <n>, nota <text>)")]
    b = C.boveda()
    if b:
        lineas.append(t(f"- Cómo se organiza esta persona: {b / 'Como-me-organizo.md'}", f"- How this person organizes: {b / 'Como-me-organizo.md'}"))
    proyecto = C.proyecto_de(cwd) if cwd else None
    ses = [s for s in C.sesiones(10) if not proyecto or s["proyecto"] == proyecto][:3]
    if ses:
        lineas.append(t("Últimas sesiones", "Latest sessions") + (f" ({C.nombre_proyecto(proyecto)})" if proyecto else "") + ":")
        for s in ses:
            lineas.append(f"- {C.cuando(s['fin'])} · {C.nombre_agente(s['agente'])} · {s['resumen'] or s['titulo']}"
                          + (f" · {t('pendiente', 'to do')}: {s['pendiente']}" if s.get("pendiente") else ""))
    abiertos = C.pendientes(proyecto=None)
    if proyecto:
        abiertos = [p for p in abiertos if p["proyecto"] == proyecto] or abiertos
    if abiertos:
        lineas.append(t("Pendientes:", "To-dos:"))
        lineas += [f"- #{p['id']} {p['texto']}" for p in abiertos[:5]]
    return "\n".join(lineas)


def sesion_inicio():
    d = _entrada()
    texto = contexto_inicio(d.get("cwd") or os.getcwd())
    if texto:
        C.registrar_uso("claude")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}}, ensure_ascii=False))


def sesion_fin():
    d = _entrada()
    if not C.configurado() or not d.get("session_id"):
        return
    from . import memoria
    memoria.encolar("claude", d["session_id"], d.get("transcript_path") or "", d.get("cwd"))
    C.registrar_uso("claude")
    # que el servicio la resuma ya (si no está corriendo, se hará al arrancar)
    try:
        import urllib.request
        from . import PUERTO
        req = urllib.request.Request(f"http://127.0.0.1:{PUERTO}/api/cerebro", data=b'{"accion": "memoria"}',
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).read()
    except OSError:
        pass
