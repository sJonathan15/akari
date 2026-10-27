"""Las cápsulas (Quickshell) y burbujas (app de escritorio) van en tres grupos, cada uno con sus
piezas en pestañas (ver AGENTS.md). Este es el único lugar donde está la lista: la app de Windows
la pide con GET /api/burbujas en vez de tener una propia.

~/.config/akari/capsulas.json {"ocultas": ["audio", "equipo", …]} oculta piezas o grupos enteros.
"""
from .comun import CONFIG, leer_json, t

# medidas en píxeles, las mismas de capsulas/*.qml: hueco = distancia al centro de la pantalla;
# chip = ancho del resumen de cada pieza en la píldora cerrada
GRUPOS = [
    {"id": "equipo", "nombre": ("Equipo", "Computer"), "lado": "izquierda", "hueco": 8, "anchoAbierto": 384,
     "altoMaximo": 700, "piezas": [
         {"id": "dispositivos", "nombre": ("Dispositivos", "Devices"), "icono": "devices", "chip": 254},
     ]},
    {"id": "ia", "nombre": ("IA", "AI"), "lado": "derecha", "hueco": 8, "anchoAbierto": 384,
     "altoMaximo": 780, "teclado": True, "piezas": [
         {"id": "uso", "nombre": ("Uso de IA", "AI usage"), "icono": "bolt", "chip": 92},
         {"id": "modelos", "nombre": ("Modelos de IA", "AI models"), "icono": "psychology", "chip": 44},
         {"id": "habilidades", "nombre": ("Habilidades", "Skills"), "icono": "auto_awesome", "chip": 58},
         {"id": "herramientas", "nombre": ("Herramientas", "Tools"), "icono": "construction", "chip": 64},
     ]},
    {"id": "archivos", "nombre": ("Archivos", "Files"), "lado": "derecha", "hueco": 404, "anchoAbierto": 380,
     "altoMaximo": 760, "archivos": True, "piezas": [
         {"id": "documentos", "nombre": ("Documentos", "Documents"), "icono": "swap_horiz", "chip": 58},
         {"id": "audio", "nombre": ("Audio", "Audio"), "icono": "graphic_eq", "chip": 72},
     ]},
]
GRUPO_DE = {p["id"]: g["id"] for g in GRUPOS for p in g["piezas"]}
MARGEN_CHIPS = 20           # relleno a los lados de la fila de chips


def ocultas():
    lista = leer_json(CONFIG / "capsulas.json").get("ocultas")
    return {str(x) for x in lista} if isinstance(lista, list) else set()


def burbujas(todas=False):
    """Los grupos visibles con sus piezas visibles, en el idioma del usuario (todas=True: sin ocultar)."""
    fuera = set() if todas else ocultas()
    grupos = []
    for g in GRUPOS:
        if g["id"] in fuera:
            continue
        piezas = [{"id": p["id"], "nombre": t(*p["nombre"]), "icono": p["icono"], "chip": p["chip"]}
                  for p in g["piezas"] if p["id"] not in fuera]
        if not piezas:
            continue
        grupo = {k: v for k, v in g.items() if k not in ("nombre", "piezas")}
        grupo.update(nombre=t(*g["nombre"]), piezas=piezas, pestanas=len(piezas) > 1,
                     anchoCerrado=sum(p["chip"] for p in piezas) + MARGEN_CHIPS + 4 * (len(piezas) - 1),
                     teclado=bool(g.get("teclado")), archivos=bool(g.get("archivos")))
        grupos.append(grupo)
    return {"grupos": grupos, "alto": 38, "margenBorde": 40}
