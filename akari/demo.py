"""Datos de ejemplo (AKARI_DEMO=1): para probar las interfaces y hacer capturas sin
mostrar datos reales. Nada de esto sale del equipo ni toca archivos del usuario."""
import math
import time

from .comun import IDIOMA, t
from .dispositivos import MODELO_3D, nombre_tipo
from .habilidades import CATALOGO
from .comun import leer_json
from .ia import resumir


def _mensajes(ahora, modelo, escala, semilla):
    msgs = []
    for i in range(900):
        ts = ahora - i * 410 - (semilla * 37 % 200)
        onda = 1 + math.sin(i / 7 + semilla)
        msgs.append({"t": ts, "modelo": modelo, "sesion": f"s{i // 120}", "proyecto": ("notas", "web", "tesis")[i // 120 % 3],
                     "agente": False, "entrada": int(900 * escala * onda), "cache_escrita": int(2500 * escala),
                     "cache_leida": int(40000 * escala), "salida": int(1300 * escala * onda), "razonamiento": 0})
    return msgs


def _ventana(usado, resta, largo):
    ahora = time.time()
    return {"usado": usado, "libre": round(100 - usado, 1), "reinicia": ahora + resta, "inicio": ahora + resta - largo,
            "transcurrido": round((largo - resta) / largo * 100, 1), "agotado_en": None}


def _dispositivo(ident, tipo, nombre, conexion, bateria, detalles, cargando=False, conectado=True):
    return {"id": ident, "tipo": tipo, "tipo_nombre": nombre_tipo(tipo), "modelo3d": MODELO_3D.get(tipo),
            "nombre": nombre, "descripcion": "", "conectado": conectado, "conexion": conexion if conectado else None,
            "bateria": bateria if conectado else None, "cargando": cargando if conectado else None,
            "detalles": detalles, "acciones": [], "ayuda": None, "horas_restantes": None, "historial": []}


def estado():
    ahora = time.time()
    c5, c7 = _ventana(38.0, 2 * 3600 + 600, 5 * 3600), _ventana(22.0, 4 * 86400, 7 * 86400)
    claude = {**resumir(_mensajes(ahora, "Opus 5.5", 1.0, 1), c5, c7, ahora),
              "cuenta": {"nombre": "Alex", "plan": "Max"}, "linea_estado": True,
              "activador": {"programado": True, "hora": "07:00", "mantener": False, "hasta": "23:00", "modelo": "haiku",
                            "ocupado": False, "ultimo": None, "proximo": ahora + 9 * 3600}}
    x5, x7 = _ventana(12.0, 3 * 3600, 5 * 3600), _ventana(9.0, 5 * 86400, 7 * 86400)
    codex = {**resumir(_mensajes(ahora - 3600, "GPT-5.1 Codex", 0.6, 2), x5, x7, ahora),
             "cuenta": {"nombre": "Alex", "plan": "Plus"}}

    disp = [
        _dispositivo("demo-mouse", "raton", "MX Master 3S", "Bluetooth", 82,
                     [[t("Señal Bluetooth", "Bluetooth signal"), "-52 dBm"]]),
        _dispositivo("demo-kbd", "teclado", "Keychron K2", t("Cable / receptor USB", "USB cable / receiver"), None,
                     [[t("Bloq Mayús", "Caps Lock"), t("desactivado", "off")], [t("Puerto", "Port"), "USB 2.0"]]),
        _dispositivo("demo-audio", "audifonos", "WH-1000XM5", "Bluetooth", 64,
                     [[t("Volumen", "Volume"), "45 %"], [t("Códec", "Codec"), "LDAC"], [t("Modo", "Mode"), t("Música (A2DP)", "Music (A2DP)")]]),
        _dispositivo("demo-phone", "celular", "Pixel 9", "KDE Connect (Wi-Fi)", 47,
                     [[t("Red móvil", "Mobile network"), "5G · " + t("buena", "good")]], cargando=True),
    ]
    disp[0]["horas_restantes"] = 31.5

    cat = leer_json(CATALOGO, {"recomendadas": [], "mas": []})
    puestas = {"pdf": 7, "docx": 3, "archify": 2}

    def tarjeta(e):
        en = ["claude"] if e["id"] in puestas else []
        return {"id": e["id"], "icono": e["icono"], "nombre": e["nombre"][IDIOMA], "detalle": e["detalle"][IDIOMA],
                "licencia": e.get("licencia"), "repo": e["fuente"]["repo"], "agentes": ["claude", "codex"],
                "instalada_en": en, "falta_en": [] if en else ["claude", "codex"], "usos_7d": puestas.get(e["id"], 0), "tarea": None}

    instaladas = [{"id": n, "nombre": n, "descripcion": "", "agentes": ["claude"], "origen": "akari", "usos_7d": u}
                  for n, u in puestas.items()]
    return {
        "ia": {"claude": claude, "codex": codex, "principal": "claude", "avisos": []},
        "dispositivos": {"dispositivos": disp, "equipo": {"bateria": 76, "estado": "descargando", "vacia_en": None, "llena_en": None},
                         "bluetooth_encendido": True, "app_celular": "KDE Connect", "mas_baja": "demo-phone",
                         "actividad": [], "umbrales": [20, 10, 5]},
        "habilidades": {"agentes": {"claude": True, "codex": True}, "instaladas": instaladas,
                        "recomendadas": [tarjeta(e) for e in cat["recomendadas"]], "mas": [tarjeta(e) for e in cat["mas"]],
                        "mcp": [{"nombre": "context7", "agente": "claude"}, {"nombre": "playwright", "agente": "codex"}],
                        "usos_7d": 12, "total": 3, "recomendadas_instaladas": 3},
        "cerebro": cerebro(),
    }


# ---------------------------------------------------------------- cerebro (datos inventados)

def _demo_ruta(*partes):
    return "~/" + "/".join(partes)


DEMO_ARCHIVOS = [
    ("Documentos/Universidad/2026/Tesis/Informe de la tesis.docx", "documento", 2),
    ("Documentos/Universidad/2026/Tesis/capitulo-3.md", "documento", 1),
    ("Documentos/Universidad/2026/Tesis/bibliografia.bib", "otro", 5),
    ("Descargas/CV-Alex-2026.pdf", "documento", 12),
    ("Trabajo/Informes/ventas-octubre.xlsx", "hoja", 3),
    ("Proyectos/tienda-web", "carpeta", 1),
]


def cerebro():
    ahora = time.time()
    sesiones = [
        {"id": "claude:1", "agente": "claude", "fin": ahora - 20 * 3600, "titulo": "Capítulo 3 de la tesis",
         "resumen": t("Se reescribió el capítulo 3 de la tesis con Claude.", "Rewrote chapter 3 of the thesis with Claude."),
         "pendiente": t("la bibliografía", "the bibliography"), "proyecto_nombre": "Tesis"},
        {"id": "codex:2", "agente": "codex", "fin": ahora - 3 * 3600, "titulo": "Carrito",
         "resumen": t("Se arregló el carrito de la tienda web.", "Fixed the web store's cart."), "pendiente": "",
         "proyecto_nombre": "tienda-web"},
    ]
    return {
        "configurado": True, "salud": "sano", "mensaje": "", "boveda": "~/Cerebro",
        "carpetas": ["~", "/media/Datos"], "texto_en": ["~/Documentos/Universidad"],
        "permitir_api": False, "modelo_api": False,
        "candidatas": [{"ruta": "~", "nombre": t("Carpeta personal", "Home folder"), "tipo": "personal"},
                       {"ruta": "/media/Datos", "nombre": "Datos", "tipo": "disco"}],
        "excluido": [], "progreso": None, "eligiendo": False,
        "cifras": {"archivos": 48213, "carpetas": 5120, "proyectos": 14, "areas": 6, "sesiones_hoy": 3, "sesiones": 128,
                   "pendientes": 2, "ultima_revision": ahora - 2 * 3600, "duracion": 41.2, "cortada": False,
                   "uso": {"claude": {"t": ahora - 1800, "hoy": 7}, "codex": {"t": ahora - 3 * 3600, "hoy": 2}}},
        "conectado": {"claude": True, "codex": True, "claude_instalado": True, "codex_instalado": True},
        "obsidian": True,
        "semantica": {"modelo": "embeddinggemma:300m", "listo": True, "vectores": 20000, "trabajando": False, "faltan": 0,
                      "error": "", "texto_en": ["~/Documentos/Universidad"]},
        "sesiones": sesiones,
        "pendientes": [{"id": 1, "texto": t("Agregar la bibliografía", "Add the bibliography"), "proyecto_nombre": "Tesis"},
                       {"id": 2, "texto": t("Enviar el CV actualizado", "Send the updated CV"), "proyecto_nombre": ""}],
    }


def cerebro_accion(datos):
    """Respuestas de ejemplo para POST /api/cerebro en modo demo (no toca nada)."""
    accion = datos.get("accion")
    ahora = time.time()
    if accion == "buscar":
        q = str(datos.get("q") or "").lower()
        hallados = [{"ruta": _demo_ruta(r), "nombre": r.split("/")[-1], "tipo": tipo, "tam": 48000,
                     "mtime": ahora - dias * 86400, "carpeta": _demo_ruta(*r.split("/")[:-1]), "via": "nombre"}
                    for r, tipo, dias in DEMO_ARCHIVOS if not q or any(p in r.lower() for p in q.split())]
        return {"ok": True, "resultados": hallados or [{"ruta": _demo_ruta(DEMO_ARCHIVOS[0][0]), "nombre": "Informe de la tesis.docx",
                                                        "tipo": "documento", "mtime": ahora - 2 * 86400, "via": "significado",
                                                        "carpeta": _demo_ruta("Documentos/Universidad/2026/Tesis")}]}
    if accion == "pregunta":
        return {"ok": True, "respuesta": t("Está en ~/Documentos/Universidad/2026/Tesis/Informe de la tesis.docx. Ayer trabajaste "
                                           "en el capítulo 3 con Claude; quedó pendiente la bibliografía.",
                                           "It's in ~/Documentos/Universidad/2026/Tesis/Informe de la tesis.docx. Yesterday you "
                                           "worked on chapter 3 with Claude; the bibliography is still to do.")}
    if accion == "en_que_quedamos":
        return {"ok": True, "texto": t("Ayer trabajaste (Tesis) con Claude Code: se reescribió el capítulo 3. Quedó pendiente: la bibliografía.",
                                       "Yesterday you worked (Thesis) with Claude Code: chapter 3 was rewritten. Left to do: the bibliography.")}
    return {"ok": True, "mensaje": t("(modo demo: no se cambió nada)", "(demo mode: nothing changed)")}
