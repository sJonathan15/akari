"""La bóveda de Obsidian del cerebro: notas que solo enlazan a los archivos reales, nunca los copian.

  Inicio.md                 resumen y enlaces
  Como-me-organizo.md       cómo ordena esta persona su computadora (lo leen primero los agentes)
  Mapa/<Área>.md            árbol de cada área con enlaces file:/// a los archivos
  Proyectos/<Proyecto>.md   ruta, de qué trata, últimas sesiones y pendientes
  Bitacora/AAAA-MM-DD.md    sesiones y notas del día
  Pendientes.md             lo que quedó por hacer (marcar [x] en Obsidian también vale)

Lo generado va entre <!-- akari --> y <!-- /akari -->; lo que el usuario escriba fuera de las marcas
se respeta en cada regeneración. Solo se escribe dentro de la carpeta de la bóveda.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from . import cerebro as C
from .comun import HOME, IDIOMA, t

INICIO, FIN = "<!-- akari -->", "<!-- /akari -->"
MAX_MAPA = 400          # entradas por nota de área (el resto: «y N más»)


# ---------------------------------------------------------------- escribir sin pisar al usuario

def fusionar(anterior, bloque):
    """El texto de la nota con `bloque` entre las marcas y todo lo demás tal cual estaba."""
    nuevo = f"{INICIO}\n{bloque.strip()}\n{FIN}"
    if anterior is None:
        return nuevo + "\n"
    i = anterior.find(INICIO)
    j = anterior.find(FIN, i + len(INICIO)) if i >= 0 else -1
    if i < 0 or j < 0:              # una nota del usuario con el mismo nombre: lo nuestro va al final
        return anterior.rstrip("\n") + "\n\n" + nuevo + "\n"
    return anterior[:i] + nuevo + anterior[j + len(FIN):]


def bloque_de(texto):
    i = texto.find(INICIO)
    j = texto.find(FIN, i + len(INICIO)) if i >= 0 else -1
    return texto[i + len(INICIO):j] if i >= 0 and j >= 0 else ""


def dentro(raiz, relativa):
    """La ruta de una nota, comprobando que queda dentro de la bóveda (nunca fuera)."""
    ruta = (raiz / relativa).resolve()
    if raiz.resolve() not in ruta.parents:
        raise OSError(f"fuera de la bóveda: {relativa}")
    return ruta


def escribir(relativa, bloque):
    raiz = C.boveda()
    if not raiz:
        return None
    ruta = dentro(raiz, relativa)
    try:
        anterior = ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        anterior = None
    nuevo = fusionar(anterior, bloque)
    if nuevo != anterior:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(f".{ruta.name}.tmp")
        tmp.write_text(nuevo, encoding="utf-8")
        os.replace(tmp, ruta)
    return ruta


def leer(relativa):
    raiz = C.boveda()
    try:
        return dentro(raiz, relativa).read_text(encoding="utf-8") if raiz else None
    except (FileNotFoundError, OSError):
        return None


# ---------------------------------------------------------------- formato

def enlace(ruta, texto=None):
    """[nombre](file:///…) al archivo real (Obsidian lo abre con su programa)."""
    p = Path(ruta)
    texto = (texto or p.name or str(p)).replace("[", "(").replace("]", ")")
    return f"[{texto}]({p.as_uri()})"


def corta(ruta):
    """~/… para las rutas de la carpeta personal (más fácil de leer)."""
    try:
        return "~" + os.sep + str(Path(ruta).relative_to(HOME)) if Path(ruta) != HOME else "~"
    except ValueError:
        return str(ruta)


def wiki(carpeta, nota, texto=None):
    return f"[[{carpeta}/{nota}|{texto or nota}]]" if carpeta else f"[[{nota}|{texto or nota}]]"


def hora(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def tam(n):
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}".replace(".0 ", " ")
        n /= 1024
    return ""


def titulo_dia(dia):
    return C.fecha_larga(datetime.strptime(dia, "%Y-%m-%d")).capitalize()


# ---------------------------------------------------------------- notas

def regenerar(todo=False, dia=None, proyecto=None, pendientes=False, inicio=True):
    """Rehace lo pedido; todo=True: la bóveda entera (después de una revisión)."""
    if not C.configurado():
        return
    if todo:
        nota_areas()
        for p in C.proyectos(2000):
            nota_proyecto(p["ruta"])
        como_me_organizo()
        nota_pendientes()
        nota_bitacora(time.strftime("%Y-%m-%d"))
    else:
        if dia:
            nota_bitacora(dia)
        if proyecto:
            nota_proyecto(proyecto)
        if pendientes:
            nota_pendientes()
    if inicio or todo:
        nota_inicio()


def nota_inicio():
    cif = C.cifras()
    areas, proys = C.areas(), C.proyectos(30)
    hoy = time.strftime("%Y-%m-%d")
    lineas = [
        f"# {t('Cerebro de akari', 'akari brain')}",
        "",
        t("> [!info] Este cerebro **no mueve, renombra ni cambia tus archivos**: solo mira sus nombres y arma este mapa "
          "para que tu IA los encuentre.",
          "> [!info] This brain **never moves, renames or changes your files**: it only looks at their names and builds "
          "this map so your AI can find them."),
        "",
        t(f"Última revisión: {_fecha(cif['ultima_revision'])} · {cif['archivos']:,} archivos · {cif['proyectos']} proyectos · "
          f"{cif['areas']} áreas", f"Last check: {_fecha(cif['ultima_revision'])} · {cif['archivos']:,} files · "
          f"{cif['proyectos']} projects · {cif['areas']} areas").replace(",", "." if IDIOMA == "es" else ","),
        "",
        f"## {t('Empieza aquí', 'Start here')}",
        f"- [[Como-me-organizo|{t('Cómo me organizo', 'How I organize')}]] — {t('lo que leen primero los agentes', 'what agents read first')}",
        f"- [[Pendientes|{t('Pendientes', 'To-dos')}]] ({cif['pendientes']})",
        f"- {t('Bitácora de hoy', 'Today’s log')}: [[Bitacora/{hoy}|{hoy}]]",
        "",
        f"## {t('Áreas', 'Areas')}",
    ]
    lineas += [f"- {wiki('Mapa', a['nota'], a['nombre'])} — `{corta(a['ruta'])}` · {a['docs']} {t('documentos', 'documents')}"
               for a in areas] or [t("- (todavía ninguna)", "- (none yet)")]
    lineas += ["", f"## {t('Proyectos', 'Projects')}"]
    for p in proys:
        ultima = f" · {t('última sesión', 'last session')} {C.cuando(p['ultima'])}" if p.get("ultima") else ""
        lineas.append(f"- {wiki('Proyectos', p['nota'], p['nombre'])} — `{corta(p['ruta'])}`{ultima}")
    if not proys:
        lineas.append(t("- (todavía ninguno)", "- (none yet)"))
    lineas += ["", f"## {t('Para tu IA', 'For your AI')}",
               t("`akari cerebro buscar <palabras>` · `akari cerebro donde <nombre>` · `akari cerebro sesiones` · "
                 "`akari cerebro pendiente <texto>`",
                 "`akari cerebro buscar <words>` · `akari cerebro donde <name>` · `akari cerebro sesiones` · "
                 "`akari cerebro pendiente <text>`")]
    escribir("Inicio.md", "\n".join(lineas))


def _fecha(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"


def nota_areas():
    vigentes = set()
    with C.bd() as c:
        for a in c.execute("SELECT * FROM areas").fetchall():
            vigentes.add(a["nota"] + ".md")
            escribir(f"Mapa/{a['nota']}.md", _arbol(c, a))
    # las notas de áreas que ya no existen se vacían (sin borrar lo que el usuario escribió en ellas)
    raiz = C.boveda()
    carpeta = raiz / "Mapa" if raiz else None
    if carpeta and carpeta.is_dir():
        for nota in carpeta.glob("*.md"):
            if nota.name not in vigentes and INICIO in nota.read_text(encoding="utf-8", errors="replace"):
                escribir(f"Mapa/{nota.name}", t("_Esta carpeta ya no está en el mapa._", "_This folder is no longer in the map._"))


def _arbol(c, area):
    ruta = area["ruta"]
    lineas = [f"# {area['nombre']}", "", f"`{ruta}` · {enlace(ruta, t('abrir carpeta', 'open folder'))} · "
              f"{area['docs']} {t('documentos', 'documents')}", ""]
    contados = [0]

    def rama(carpeta, nivel):
        hijos = c.execute("SELECT * FROM archivos WHERE carpeta=? ORDER BY tipo != 'carpeta', nombre COLLATE NOCASE",
                          (carpeta,)).fetchall()
        if area["sueltos"]:                     # p. ej. Descargas: solo lo suelto, lo más nuevo primero
            hijos = sorted([h for h in hijos if h["tipo"] != "carpeta"], key=lambda h: -(h["mtime"] or 0))
        for h in hijos:
            if contados[0] >= MAX_MAPA:
                return
            sangria = "  " * nivel
            if h["tipo"] == "carpeta":
                if h["proyecto"] and h["proyecto"] == h["ruta"]:
                    nota = c.execute("SELECT nota FROM proyectos WHERE ruta=?", (h["ruta"],)).fetchone()
                    lineas.append(f"{sangria}- 📦 {wiki('Proyectos', nota[0], h['nombre']) if nota else enlace(h['ruta'])}")
                    contados[0] += 1
                    continue
                lineas.append(f"{sangria}- 📁 {enlace(h['ruta'], h['nombre'] + '/')}")
                contados[0] += 1
                if nivel < 4:
                    rama(h["ruta"], nivel + 1)
            else:
                lineas.append(f"{sangria}- {enlace(h['ruta'])} · {datetime.fromtimestamp(h['mtime'] or 0):%Y-%m-%d} · {tam(h['tam'] or 0)}")
                contados[0] += 1

    rama(ruta, 0)
    if contados[0] >= MAX_MAPA:
        lineas.append(t(f"- … (y más: `akari cerebro buscar` los encuentra todos)", "- … (and more: `akari cerebro buscar` finds them all)"))
    return "\n".join(lineas)


def nota_proyecto(ruta):
    with C.bd() as c:
        p = c.execute("SELECT * FROM proyectos WHERE ruta=?", (ruta,)).fetchone()
    if not p:
        return
    ses = [s for s in C.sesiones(500) if s["proyecto"] == ruta][:10]
    abiertos = [x for x in C.pendientes() if x["proyecto"] == ruta]
    lineas = [f"# {p['nombre']}", "",
              f"- {t('Ruta', 'Path')}: `{ruta}` · {enlace(ruta, t('abrir carpeta', 'open folder'))}"]
    if p["tipo"]:
        lineas.append(f"- {t('Tipo', 'Type')}: {p['tipo']}")
    lineas += ["", f"## {t('De qué trata', 'What it is')}",
               p["descripcion"] or t("_Sin README todavía._", "_No README yet._"), "",
               f"## {t('Últimas sesiones', 'Latest sessions')}"]
    for s in ses:
        dia = datetime.fromtimestamp(s["fin"]).strftime("%Y-%m-%d")
        lineas.append(f"- [[Bitacora/{dia}|{dia}]] · {C.nombre_agente(s['agente'])} · {s['resumen'] or s['titulo']}")
        if s.get("pendiente"):
            lineas.append(f"  - {t('Pendiente', 'To do')}: {s['pendiente']}")
    if not ses:
        lineas.append(t("- (ninguna todavía)", "- (none yet)"))
    lineas += ["", f"## {t('Pendientes', 'To-dos')}"]
    lineas += [f"- [ ] {x['texto']} <!-- p{x['id']} -->" for x in abiertos] or [t("- (nada)", "- (nothing)")]
    escribir(f"Proyectos/{p['nota']}.md", "\n".join(lineas))


def nota_bitacora(dia):
    inicio = datetime.strptime(dia, "%Y-%m-%d").timestamp()
    fin = inicio + 86400
    with C.bd() as c:
        ses = c.execute("SELECT * FROM sesiones WHERE estado='hecha' AND fin >= ? AND fin < ? ORDER BY fin", (inicio, fin)).fetchall()
        notas = c.execute("SELECT * FROM notas WHERE t >= ? AND t < ? ORDER BY t", (inicio, fin)).fetchall()
        notas_p = {r["ruta"]: r["nota"] for r in c.execute("SELECT ruta, nota FROM proyectos")}
    lineas = [f"# {titulo_dia(dia)}", "", f"## {t('Sesiones', 'Sessions')}"]
    for s in ses:
        proy = f"**{wiki('Proyectos', notas_p[s['proyecto']], C.nombre_proyecto(s['proyecto']))}** — " \
            if s["proyecto"] in notas_p else ""
        lineas.append(f"- {hora(s['fin'])} · {C.nombre_agente(s['agente'])} · {proy}{s['resumen'] or s['titulo']}")
        archivos = json.loads(s["archivos"] or "[]")
        if archivos:
            lineas.append(f"  - {t('Archivos', 'Files')}: " + ", ".join(f"`{a}`" for a in archivos[:8]))
        if s["pendiente"]:
            lineas.append(f"  - {t('Pendiente', 'To do')}: {s['pendiente']}")
    if not ses:
        lineas.append(t("- (ninguna)", "- (none)"))
    if notas:
        lineas += ["", f"## {t('Notas', 'Notes')}"]
        for n in notas:
            proy = f" ({wiki('Proyectos', notas_p[n['proyecto']], C.nombre_proyecto(n['proyecto']))})" if n["proyecto"] in notas_p else ""
            lineas.append(f"- {hora(n['t'])} — {n['texto']}{proy}")
    escribir(f"Bitacora/{dia}.md", "\n".join(lineas))


def sincronizar_casillas():
    """Lo que el usuario marcó o desmarcó en Pendientes.md (dentro de las marcas) pasa a la base."""
    raiz = C.boveda()
    ruta = raiz / "Pendientes.md" if raiz else None
    texto = leer("Pendientes.md")
    if not texto:
        return
    with C.bd() as c:               # solo si el usuario la tocó después de la última vez que la escribió akari
        if abs(ruta.stat().st_mtime - (C.meta(c, "pendientes_mtime") or 0)) < 0.001:
            return
    bloque = bloque_de(texto)
    with C.bd() as c:
        for marca, ident in re.findall(r"^\s*- \[([ xX])\] .*?<!-- p(\d+) -->", bloque, re.M):
            fila = c.execute("SELECT hecho FROM pendientes WHERE id=?", (int(ident),)).fetchone()
            if not fila:
                continue
            if marca.lower() == "x" and fila["hecho"] is None:
                c.execute("UPDATE pendientes SET hecho=? WHERE id=?", (time.time(), int(ident)))
            elif marca == " " and fila["hecho"] is not None:
                c.execute("UPDATE pendientes SET hecho=NULL WHERE id=?", (int(ident),))


def nota_pendientes():
    sincronizar_casillas()
    todos = C.pendientes(todos=True)
    notas_p = {p["ruta"]: p["nota"] for p in C.proyectos(2000)}
    semana = time.time() - 7 * 86400

    def linea(p, hecho):
        proy = f" · {wiki('Proyectos', notas_p[p['proyecto']], p['proyecto_nombre'])}" if p["proyecto"] in notas_p else ""
        return f"- [{'x' if hecho else ' '}] {p['texto']}{proy} <!-- p{p['id']} -->"

    abiertos = [linea(p, False) for p in todos if p["hecho"] is None]
    hechos = [linea(p, True) for p in todos if p["hecho"] and p["hecho"] >= semana]
    lineas = [f"# {t('Pendientes', 'To-dos')}", "",
              t("_Márcalos aquí o con `akari cerebro hecho <número>`._", "_Tick them here or with `akari cerebro hecho <number>`._"), ""]
    lineas += abiertos or [t("- (nada pendiente)", "- (nothing to do)")]
    if hechos:
        lineas += ["", f"## {t('Hechos esta semana', 'Done this week')}", *hechos]
    ruta = escribir("Pendientes.md", "\n".join(lineas))
    if ruta:
        with C.bd() as c:
            C.poner_meta(c, "pendientes_mtime", ruta.stat().st_mtime)


# ---------------------------------------------------------------- cómo me organizo

def inventario():
    """Lo que ve el modelo para escribir «Cómo me organizo»: solo nombres, rutas y cuentas."""
    with C.bd() as c:
        areas = c.execute("SELECT * FROM areas ORDER BY docs DESC LIMIT 25").fetchall()
        proys = c.execute("SELECT * FROM proyectos ORDER BY mtime DESC LIMIT 25").fetchall()
        lineas = [t("Áreas (carpetas con muchos documentos):", "Areas (folders with many documents):")]
        for a in areas:
            subs = [r[0] for r in c.execute("""SELECT nombre FROM archivos WHERE carpeta=? AND tipo='carpeta'
                ORDER BY mtime DESC LIMIT 8""", (a["ruta"],))]
            lineas.append(f"- {a['ruta']} ({a['docs']} docs){'; ' + ', '.join(subs) if subs else ''}")
        lineas.append(t("Proyectos:", "Projects:"))
        lineas += [f"- {p['ruta']} ({p['tipo']})" for p in proys]
        lineas.append(t("Dónde hay más de cada tipo:", "Where each type is most common:"))
        for tipo in ("documento", "hoja", "presentacion", "imagen", "video"):
            filas = c.execute("""SELECT carpeta, COUNT(*) n FROM archivos WHERE tipo=? AND proyecto IS NULL GROUP BY carpeta
                ORDER BY n DESC LIMIT 4""", (tipo,)).fetchall()
            if filas:
                lineas.append(f"- {tipo}: " + "; ".join(f"{f['carpeta']} ({f['n']})" for f in filas))
        recientes = c.execute("""SELECT ruta FROM archivos WHERE tipo IN ('documento','hoja','presentacion') AND proyecto IS NULL
            ORDER BY mtime DESC LIMIT 25""").fetchall()
        lineas.append(t("Documentos recientes:", "Recent documents:"))
        lineas += [f"- {r[0]}" for r in recientes]
    return "\n".join(lineas)


def _sin_ia(c):
    """Versión sin modelo: lo mismo, en frases cortas."""
    lineas = []
    for a in c.execute("SELECT * FROM areas ORDER BY docs DESC LIMIT 15"):
        subs = [r[0] for r in c.execute("SELECT nombre FROM archivos WHERE carpeta=? AND tipo='carpeta' ORDER BY nombre LIMIT 6",
                                        (a["ruta"],))]
        detalle = t(f"{a['docs']} documentos", f"{a['docs']} documents") + (f"; {', '.join(subs)}" if subs else "")
        if a["sueltos"]:
            detalle = t(f"{a['docs']} documentos sueltos: ahí suelen quedar descargas y PDF",
                        f"{a['docs']} loose documents: downloads and PDFs tend to land here")
        lineas.append(f"- **{a['nombre']}**: `{a['ruta']}` ({detalle})")
    proys = c.execute("SELECT ruta, nombre FROM proyectos WHERE origen='mapa' ORDER BY mtime DESC LIMIT 40").fetchall()
    if proys:
        padres = {}
        for p in proys:
            padres.setdefault(str(Path(p["ruta"]).parent), []).append(p["nombre"])
        for padre, nombres in sorted(padres.items(), key=lambda x: -len(x[1]))[:5]:
            lineas.append(t(f"- Proyectos en `{padre}`: ", f"- Projects in `{padre}`: ") + ", ".join(nombres[:8]))
    for palabra, texto in (("cv", t("Los CV", "CVs")), ("curriculum", t("Los CV", "CVs")), ("factura", t("Facturas", "Invoices")),
                           ("invoice", t("Facturas", "Invoices")), ("tesis", t("La tesis", "The thesis")),
                           ("thesis", t("La tesis", "The thesis"))):
        filas = [f for f in C.buscar(palabra, 3) if f["tipo"] != "carpeta"]
        if filas:
            carpetas = list(dict.fromkeys(f["carpeta"] for f in filas))[:2]
            lineas.append(f"- {texto}: " + ", ".join(f"`{x}`" for x in carpetas))
    vistos, salida = set(), []
    for x in lineas:
        if x not in vistos:
            vistos.add(x)
            salida.append(x)
    return salida


def como_me_organizo(monitor_modelos=None, forzar=False):
    """La escribe el modelo (si hay y puede) mirando solo nombres y rutas; si no, akari con reglas."""
    inv = inventario()
    # los documentos recientes cambian a diario: solo áreas y proyectos deciden si hay que reescribirla
    firma = hashlib.sha1(inv.split(t("Documentos recientes:", "Recent documents:"))[0].encode()).hexdigest()
    with C.bd() as c:
        previa = C.meta(c, "como_firma")
        cuerpo_sin_ia = _sin_ia(c)
    monitor_modelos = monitor_modelos or _MODELOS.get("monitor")
    ia, _ = C.puede_usar_ia(monitor_modelos)
    actual = leer("Como-me-organizo.md")
    if not forzar and previa == firma and actual and INICIO in actual:
        return
    texto = None
    if ia:
        from .modelos import ErrorIA, preguntar
        try:
            texto = preguntar(monitor_modelos, inv, sistema=t(
                "Miras SOLO nombres y rutas de la computadora de una persona (no su contenido). Escribe en español entre 8 y 15 "
                "viñetas cortas que expliquen cómo organiza sus cosas y dónde está cada una, con las rutas exactas entre "
                "comillas invertidas, para que otra IA las encuentre rápido. Ejemplo: «- La universidad está en `D:\\U\\2026`, "
                "una carpeta por materia». No inventes nada que no esté en la lista. Solo las viñetas.",
                "You see ONLY names and paths from a person's computer (not their content). Write 8 to 15 short bullets in "
                "English explaining how they organize things and where each thing is, with exact paths in backticks, so "
                "another AI finds them fast. Example: “- University is in `D:\\U\\2026`, one folder per course”. Don't "
                "invent anything not in the list. Only the bullets."), timeout=120)
            texto = "\n".join(x for x in texto.splitlines() if x.strip().startswith(("-", "*", "•"))).strip() or None
        except ErrorIA:
            texto = None
    cabeza = f"# {t('Cómo me organizo', 'How I organize')}\n\n"
    if texto:
        pie = t("_Lo escribió el modelo de IA mirando solo nombres y rutas. Corrige o completa abajo, fuera de las marcas._",
                "_Written by the AI model looking only at names and paths. Fix or add below, outside the markers._")
        bloque = cabeza + texto + "\n\n" + pie
    else:
        pie = t("_Hecho por akari sin IA, mirando solo nombres y rutas. Elige un modelo en «Modelos de IA» para una versión "
                "mejor; corrige o completa abajo, fuera de las marcas._",
                "_Made by akari without AI, looking only at names and paths. Pick a model in “AI models” for a better "
                "version; fix or add below, outside the markers._")
        bloque = cabeza + ("\n".join(cuerpo_sin_ia) or t("- (todavía no hay suficiente para decir algo)", "- (not enough to say yet)")) + "\n\n" + pie
    escribir("Como-me-organizo.md", bloque)
    with C.bd() as c:
        C.poner_meta(c, "como_firma", firma)
        C.poner_meta(c, "como_ia", bool(texto))


_MODELOS = {}           # {"monitor": MonitorModelos} lo pone el servicio para las regeneraciones
