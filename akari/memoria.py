"""Memoria de sesiones: al terminar cada sesión de Claude Code, de Codex o del asistente de akari, un
resumen de 2–4 líneas (qué se hizo, en qué proyecto y archivos, qué quedó pendiente) va a la bitácora
del día y a la nota del proyecto.

  Claude Code   ~/.claude/projects/*/<sesión>.jsonl (y el gancho SessionEnd, si está conectado)
  Codex         ~/.codex/sessions/**/rollout-*.jsonl
  akari         registrar_asistente(...) desde el asistente

Una sesión se da por terminada cuando su archivo lleva INACTIVA sin cambiar (o cuando avisa el gancho).
El resumen lo hace el modelo de modelos.py; sin modelo (o si es por API y el usuario no lo permitió):
solo título, proyecto y archivos tocados.
"""
import json
import re
import time
from pathlib import Path

from . import cerebro as C
from .comun import HOME, t
from .ia import CLAUDE_DIR, CODEX_DIR, marca_tiempo

INACTIVA = 20 * 60          # sin cambios hace 20 min: terminó
DIAS = 7                    # la primera vez, solo las de la última semana
POR_VUELTA = 25             # cuántas se resumen por vuelta (no ocupar el modelo de golpe)
EDITAN = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Update", "Create"}


def fuentes():
    """(agente, archivo) de las sesiones en el equipo."""
    carpeta = CLAUDE_DIR / "projects"
    if carpeta.is_dir():
        for archivo in carpeta.glob("*/*.jsonl"):
            yield "claude", archivo
    carpeta = CODEX_DIR / "sessions"
    if carpeta.is_dir():
        for archivo in carpeta.rglob("rollout-*.jsonl"):
            yield "codex", archivo


def _texto(contenido):
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "\n".join(b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text"))
    return ""


def _pedido_valido(texto):
    texto = (texto or "").strip()
    return bool(texto) and not texto.startswith(("<", "Caveat:", "[Request interrupted")) and "<command-name>" not in texto[:200]


def nueva():
    return {"id": None, "cwd": None, "inicio": None, "fin": None, "titulo": None, "pedidos": [], "respuesta": "",
            "archivos": []}


def _tiempo(s, ts):
    if ts:
        s["inicio"] = min(s["inicio"] or ts, ts)
        s["fin"] = max(s["fin"] or ts, ts)


def _archivo(s, ruta):
    if ruta and ruta not in s["archivos"]:
        s["archivos"].append(ruta)


def leer_claude(archivo):
    s = nueva()
    with open(archivo, "rb") as f:
        for linea in f:
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            tipo = d.get("type")
            if tipo == "summary" and d.get("summary"):
                s["titulo"] = str(d["summary"])[:120]
                continue
            if tipo not in ("user", "assistant") or d.get("isSidechain"):
                continue
            _tiempo(s, marca_tiempo(d.get("timestamp")))
            s["id"] = s["id"] or d.get("sessionId")
            s["cwd"] = s["cwd"] or d.get("cwd")
            m = d.get("message") or {}
            if tipo == "user" and not d.get("isMeta"):
                texto = _texto(m.get("content"))
                if _pedido_valido(texto):
                    s["pedidos"].append(texto.strip()[:500])
            elif tipo == "assistant" and isinstance(m.get("content"), list):
                for b in m["content"]:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        s["respuesta"] = b["text"].strip()[-1500:]
                    elif b.get("type") == "tool_use" and b.get("name") in EDITAN:
                        entrada = b.get("input") or {}
                        _archivo(s, entrada.get("file_path") or entrada.get("notebook_path"))
    s["id"] = s["id"] or Path(archivo).stem
    return s


PARCHE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def leer_codex(archivo):
    s = nueva()
    with open(archivo, "rb") as f:
        for linea in f:
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            p = d.get("payload") or {}
            _tiempo(s, marca_tiempo(d.get("timestamp")))
            tipo = d.get("type")
            if tipo == "session_meta":
                s["id"] = p.get("id") or s["id"]
                s["cwd"] = p.get("cwd") or s["cwd"]
            elif tipo == "turn_context" and p.get("cwd"):
                s["cwd"] = s["cwd"] or p["cwd"]
            elif tipo == "event_msg" and p.get("type") == "user_message":
                if _pedido_valido(p.get("message")):
                    s["pedidos"].append(str(p["message"]).strip()[:500])
            elif tipo == "response_item":
                if p.get("type") == "message" and p.get("role") == "assistant":
                    texto = _texto(p.get("content"))
                    if texto.strip():
                        s["respuesta"] = texto.strip()[-1500:]
                elif p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                    cuerpo = p.get("arguments") or p.get("input") or ""
                    if not isinstance(cuerpo, str):
                        cuerpo = json.dumps(cuerpo)
                    try:            # function_call trae JSON con el parche dentro
                        cuerpo = " ".join(str(v) for v in json.loads(cuerpo).values()) if cuerpo.lstrip().startswith("{") else cuerpo
                    except (ValueError, AttributeError):
                        pass
                    for ruta in PARCHE.findall(cuerpo):
                        _archivo(s, ruta.strip())
    s["id"] = s["id"] or Path(archivo).stem
    return s


def titulo_de(s):
    if s.get("titulo"):
        return s["titulo"]
    for p in s["pedidos"]:
        primera = " ".join(p.splitlines()[0].split())
        if primera:
            return primera[:90] + ("…" if len(primera) > 90 else "")
    return t("Sesión sin mensajes", "Session without messages")


def _relativo(ruta, cwd):
    try:
        return str(Path(ruta).relative_to(cwd)) if cwd else ruta
    except ValueError:
        return ruta


def resumir(s, proyecto_nombre, monitor_modelos=None):
    """(resumen, pendiente, con_ia)."""
    titulo = titulo_de(s)
    ia, _ = C.puede_usar_ia(monitor_modelos)
    if not ia or not s["pedidos"]:
        return titulo, "", False
    from .modelos import ErrorIA, preguntar
    pedidos = s["pedidos"][:3] + (s["pedidos"][-2:] if len(s["pedidos"]) > 5 else s["pedidos"][3:5])
    texto = (f"{t('Proyecto', 'Project')}: {proyecto_nombre or s['cwd'] or '-'}\n"
             f"{t('Archivos tocados', 'Files touched')}: {', '.join(s['archivos'][:12]) or '-'}\n"
             f"{t('Lo que pidió la persona', 'What the person asked')}:\n" + "\n".join(f"- {p[:300]}" for p in pedidos) +
             f"\n{t('Última respuesta de la IA', 'Last AI reply')}:\n{s['respuesta'][-700:]}")
    try:
        r = preguntar(monitor_modelos, texto, sistema=t(
            "Resumes sesiones de trabajo con IA para la bitácora de una persona. Responde solo JSON: "
            '{"hecho": "1 o 2 frases: qué se hizo", "pendiente": "lo que quedó por hacer, o vacío"}. En español, sin adornos.',
            "You summarize AI work sessions for a person's log. Reply only JSON: "
            '{"hecho": "1 or 2 sentences: what was done", "pendiente": "what is left to do, or empty"}. In English, plain.'),
            timeout=90)
    except ErrorIA:
        return titulo, "", False
    d = C._json_de(r)
    hecho = " ".join(str(d.get("hecho") or "").split())[:400]
    pendiente = " ".join(str(d.get("pendiente") or "").split())[:300]
    if pendiente.lower().strip(" .") in ("", "-", "ninguno", "nada", "none", "nothing", "n/a", "vacío", "vacio"):
        pendiente = ""
    return hecho or titulo, pendiente, bool(hecho)


def proyecto_para(cwd):
    """El proyecto del mapa que contiene la carpeta; si no hay, uno nuevo con el nombre de la carpeta."""
    if not cwd:
        return None
    ruta = C.proyecto_de(cwd)
    if ruta:
        return ruta
    carpeta = Path(cwd)
    if carpeta == HOME or carpeta.parent == carpeta or HOME not in carpeta.parents and not carpeta.is_dir():
        return None
    with C.bd() as c:
        ocupadas = {r[0].lower() for r in c.execute("SELECT nota FROM proyectos")}
        nota = C.nombre_nota(carpeta.name)
        if nota.lower() in ocupadas:
            nota = C.nombre_nota(f"{carpeta.name} ({carpeta.parent.name})")
        n, base = 2, nota
        while nota.lower() in ocupadas:
            nota, n = f"{base} {n}", n + 1
        c.execute("""INSERT OR IGNORE INTO proyectos(ruta, nombre, nota, tipo, descripcion, origen, mtime)
            VALUES (?,?,?,?,?,?,?)""", (str(carpeta), carpeta.name, nota, "", C.leer_readme(carpeta), "sesion", time.time()))
    return str(carpeta)


def guardar(agente, s, archivo=None, tam=0, monitor_modelos=None):
    """Resume y guarda una sesión; rehace la bitácora del día y la nota del proyecto."""
    if not s["pedidos"] and not s["archivos"]:
        estado = "vacia"
    else:
        estado = "hecha"
    proyecto = proyecto_para(s["cwd"]) if estado == "hecha" else None
    nombre = C.nombre_proyecto(proyecto) if proyecto else ""
    resumen, pendiente, con_ia = resumir(s, nombre, monitor_modelos) if estado == "hecha" else ("", "", False)
    archivos = [_relativo(a, s["cwd"]) for a in s["archivos"]][:30]
    ident = f"{agente}:{s['id']}"
    fin = s["fin"] or time.time()
    with C.bd() as c:
        c.execute("""INSERT OR REPLACE INTO sesiones(id, agente, archivo, inicio, fin, cwd, proyecto, titulo, resumen, pendiente,
            archivos, tam, estado, con_ia) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (ident, agente, str(archivo or ""), s["inicio"] or fin, fin, s["cwd"], proyecto, titulo_de(s), resumen,
                   pendiente, json.dumps(archivos, ensure_ascii=False), tam, estado, int(con_ia)))
        # el pendiente de la sesión (uno por sesión: si se vuelve a resumir, se reemplaza)
        c.execute("DELETE FROM pendientes WHERE origen=? AND hecho IS NULL", (f"sesion:{ident}",))
        if pendiente:
            c.execute("INSERT INTO pendientes(texto, proyecto, creado, origen) VALUES (?,?,?,?)",
                      (pendiente, proyecto, time.time(), f"sesion:{ident}"))
    if estado == "hecha":
        C._regenerar(dia=time.strftime("%Y-%m-%d", time.localtime(fin)), proyecto=proyecto, pendientes=True)
    return ident


def encolar(agente, ident, archivo, cwd=None):
    """Lo llama el gancho SessionEnd: esa sesión se resume en la próxima vuelta, sin esperar."""
    with C.bd() as c:
        c.execute("""INSERT INTO sesiones(id, agente, archivo, fin, cwd, estado, tam) VALUES (?,?,?,?,?, 'cola', 0)
            ON CONFLICT(id) DO UPDATE SET estado='cola', archivo=excluded.archivo""",
                  (f"{agente}:{ident}", agente, str(archivo or ""), time.time(), cwd))


def procesar(monitor_modelos=None, ahora=None):
    """Una vuelta: las sesiones en cola (gancho) y las que terminaron desde la última vez."""
    if not C.configurado():
        return 0
    ahora = ahora or time.time()
    with C.bd() as c:
        hechas = {r["archivo"]: (r["tam"], r["estado"]) for r in c.execute("SELECT archivo, tam, estado FROM sesiones")}
        cola = [r["archivo"] for r in c.execute("SELECT archivo FROM sesiones WHERE estado='cola'")]
        desde = C.meta(c, "memoria_desde")
        if desde is None:
            desde = ahora - DIAS * 86400
            C.poner_meta(c, "memoria_desde", desde)
    candidatos = []
    for agente, archivo in fuentes():
        try:
            info = archivo.stat()
        except OSError:
            continue
        en_cola = str(archivo) in cola
        if info.st_mtime < desde and not en_cola:
            continue
        if not en_cola and ahora - info.st_mtime < INACTIVA:
            continue                            # todavía en uso
        previo = hechas.get(str(archivo))
        if previo and previo[1] != "cola" and info.st_size - (previo[0] or 0) < 2048:
            continue                            # ya resumida (y no creció casi nada)
        candidatos.append((not en_cola, -info.st_mtime, agente, archivo, info.st_size))
    candidatos.sort()
    hechos = 0
    for _, _, agente, archivo, tam in candidatos[:POR_VUELTA]:
        try:
            s = (leer_claude if agente == "claude" else leer_codex)(archivo)
        except OSError:
            continue
        with C.bd() as c:          # una sesión en cola guardada con otro id (el del gancho) se reemplaza
            c.execute("DELETE FROM sesiones WHERE archivo=? AND id != ?", (str(archivo), f"{agente}:{s['id']}"))
        guardar(agente, s, archivo, tam, monitor_modelos)
        hechos += 1
    return hechos


def registrar_asistente(ident, mensajes, cwd=None, archivos=None, monitor_modelos=None):
    """Para el asistente de akari: mensajes = [{"rol": "usuario"|"asistente", "texto"}]."""
    s = nueva()
    s.update(id=str(ident), cwd=cwd, inicio=time.time(), fin=time.time(), archivos=list(archivos or []))
    for m in mensajes or []:
        texto = str(m.get("texto") or "")
        if m.get("rol") == "usuario" and _pedido_valido(texto):
            s["pedidos"].append(texto[:500])
        elif m.get("rol") == "asistente" and texto.strip():
            s["respuesta"] = texto[-1500:]
    return guardar("akari", s, None, 0, monitor_modelos)
