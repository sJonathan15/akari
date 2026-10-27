"""Los grupos de burbujas que dibujan las apps de escritorio (GET /api/burbujas).

Como dice AGENTS.md, nada va suelto: cada función es una **pieza** de uno de tres grupos
(Equipo, IA, Archivos) y en las apps cada grupo es una burbuja con pestañas. Esta lista es la
única fuente para la app de Windows (escritorio/) y la de Electron (app/): una pieza aparece
sola en cuanto el panel web sabe dibujarla (su nombre está en SECCIONES de web/app.js). Una
pieza nueva se agrega aquí, en PIEZAS, con su grupo.

`~/.config/akari/capsulas.json` {"ocultas": [...]} oculta piezas o grupos enteros; un grupo sin
piezas visibles no se da. Mientras la web no tenga la vista de grupo con pestañas
(?vista=burbuja&c=equipo&pieza=dispositivos), cada grupo dice en `pagina` qué cargar y las
apps abren la página de la pieza que está bajo el puntero (?vista=burbuja&c=<pieza>).
"""
import re

from .comun import CONFIG, RAIZ, leer_json

WEB = RAIZ / "web"

# grupo: dónde va (como capsulas/Capsula.qml: lado y distancia al centro) y su nombre
GRUPOS = {
    "equipo": {"lado": "izquierda", "hueco": 8, "titulo": ("Equipo", "Computer"), "icono": "devices"},
    "ia": {"lado": "derecha", "hueco": 8, "titulo": ("IA", "AI"), "icono": "bolt"},
    # a la derecha de la de IA abierta (8 + 384 + margen)
    "archivos": {"lado": "derecha", "hueco": 404, "titulo": ("Archivos", "Files"), "icono": "folder"},
}
# pieza: su grupo, el ancho de su chip en la píldora cerrada (lógico) y lo que necesita abierta
PIEZAS = {
    "dispositivos": {"grupo": "equipo", "icono": "devices", "titulo": ("Dispositivos", "Devices"),
                     "chip": 232, "abierta": 384, "alto": 700},
    "asistente": {"grupo": "ia", "icono": "chat", "titulo": ("Asistente", "Assistant"),
                  "chip": 28, "abierta": 380, "alto": 760, "teclado": True},
    "ia": {"grupo": "ia", "icono": "bolt", "titulo": ("Uso de IA", "AI usage"),
           "chip": 206, "abierta": 360, "alto": 760, "teclado": True},
    "modelos": {"grupo": "ia", "icono": "smart_toy", "titulo": ("Modelos de IA", "AI models"),
                "chip": 28, "abierta": 380, "alto": 700},
    "habilidades": {"grupo": "ia", "icono": "auto_awesome", "titulo": ("Habilidades", "Skills"),
                    "chip": 56, "abierta": 380, "alto": 900},
    "herramientas": {"grupo": "ia", "icono": "handyman", "titulo": ("Herramientas", "Tools"),
                     "chip": 28, "abierta": 380, "alto": 700},
    "documentos": {"grupo": "archivos", "icono": "swap_horiz", "titulo": ("Documentos", "Documents"),
                   "chip": 150, "abierta": 380, "alto": 760},
    "audio": {"grupo": "archivos", "icono": "graphic_eq", "titulo": ("Audio", "Audio"),
              "chip": 28, "abierta": 380, "alto": 700},
    "cerebro": {"grupo": "archivos", "icono": "notes", "titulo": ("Cerebro", "Brain"),
                "chip": 28, "abierta": 380, "alto": 760},
}
MARGEN, ENTRE = 14, 10      # relleno de la píldora y espacio entre chips


def secciones_web():
    """Las vistas que sabe dibujar el panel web: las claves de SECCIONES en web/app.js."""
    try:
        texto = (WEB / "app.js").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    m = re.search(r"\bSECCIONES\s*=\s*\{(.*?)\};", texto, re.S)
    if not m:       # si cambió de forma: cualquier nombre conocido que aparezca como clave
        return {n for n in (*PIEZAS, *GRUPOS) if re.search(rf"\b{n}\s*:", texto)}
    return set(re.findall(r"(?:^|[{,\s])([a-z_]+)\s*:", m.group(1)))


def lista(idioma="es"):
    i = 0 if idioma == "es" else 1
    web = secciones_web()
    con_grupos = grupos_web(web)
    ocultas = set(leer_json(CONFIG / "capsulas.json").get("ocultas") or [])
    grupos = []
    for nombre, g in GRUPOS.items():
        if nombre in ocultas:
            continue
        piezas = [{"nombre": p, "titulo": d["titulo"][i], "icono": d["icono"], "ancho": d["chip"]}
                  for p, d in PIEZAS.items() if d["grupo"] == nombre and p in web and p not in ocultas]
        if not piezas:
            continue
        datos = [PIEZAS[p["nombre"]] for p in piezas]
        grupos.append({
            "nombre": nombre, "titulo": g["titulo"][i], "icono": g["icono"], "lado": g["lado"], "hueco": g["hueco"],
            "anchoCerrado": max(136, 2 * MARGEN + sum(p["ancho"] for p in piezas) + ENTRE * (len(piezas) - 1)),
            "anchoAbierto": max(d["abierta"] for d in datos),
            "altoMaximo": max(d["alto"] for d in datos),
            "teclado": any(d.get("teclado") for d in datos),
            "piezas": piezas,
            # qué página cargar: la del grupo (con pestañas) si la web ya la tiene; si no, la de su pieza
            "pagina": nombre if con_grupos else piezas[0]["nombre"],
        })
    return grupos


def grupos_web(web=None):
    """¿El panel web ya dibuja un grupo entero con pestañas (?vista=burbuja&c=<grupo>)?
    ("ia" es a la vez grupo y pieza: se mira por los otros dos.)"""
    return bool({"equipo", "archivos"} & (secciones_web() if web is None else web))
