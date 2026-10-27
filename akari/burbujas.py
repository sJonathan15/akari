"""Las burbujas que dibujan las apps de escritorio (GET /api/burbujas).

La fuente es la misma que usan las cápsulas de Quickshell: cada capsulas/Capsula<Algo>.qml
declara su `nombre`, `lado`, `hueco`, `anchoCerrado`, `anchoAbierto`, `altoMaximo` y
`pideTeclado`. Así una cápsula nueva en Linux aparece sola como burbuja en Windows (y en la
app Electron) en cuanto el panel web sabe dibujarla (su nombre aparece en web/*.js).
Una cápsula puede quedarse fuera de las apps con la línea `// akari: sin-burbuja`.
"""
import re

from .comun import RAIZ

CARPETA = RAIZ / "capsulas"
WEB = RAIZ / "web"
# los valores por defecto de capsulas/Capsula.qml
FABRICA = {"lado": "derecha", "hueco": 8, "anchoCerrado": 250, "anchoAbierto": 380, "altoMaximo": 640, "teclado": False}
ICONOS = {"ia": "bolt", "dispositivos": "devices", "habilidades": "auto_awesome"}
TITULOS = {"ia": ("IA", "AI"), "dispositivos": ("Dispositivos", "Devices"), "habilidades": ("Habilidades", "Skills")}

_cache = None


def leer_qml(texto):
    """Propiedades de una cápsula (solo las literales; lo demás queda con su valor de fábrica)."""
    nombre = re.search(r'^\s*nombre:\s*"([\w-]+)"', texto, re.M)
    if not nombre or "akari: sin-burbuja" in texto:
        return None
    b = {"nombre": nombre.group(1), **FABRICA}
    lado = re.search(r'^\s*lado:\s*"(izquierda|derecha)"', texto, re.M)
    if lado:
        b["lado"] = lado.group(1)
    for clave in ("hueco", "anchoCerrado", "anchoAbierto", "altoMaximo"):
        m = re.search(rf"^\s*{clave}:\s*(\d+)\s*(?://.*)?$", texto, re.M)
        if m:
            b[clave] = int(m.group(1))
    b["teclado"] = bool(re.search(r"^\s*pideTeclado:\s*true", texto, re.M))
    return b


def lista(idioma="es"):
    global _cache
    if _cache is None:
        web = ""
        for js in WEB.glob("*.js"):
            try:
                web += js.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        burbujas = []
        for qml in sorted(CARPETA.glob("Capsula?*.qml")):
            try:
                b = leer_qml(qml.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            # solo las que el panel web sabe dibujar (?vista=burbuja&c=<nombre>)
            if b and re.search(rf"\b{re.escape(b['nombre'])}\b\s*:", web):
                burbujas.append(b)
        _cache = burbujas
    return [{**b, "icono": ICONOS.get(b["nombre"], "widgets"),
             "titulo": TITULOS.get(b["nombre"], (b["nombre"].capitalize(),) * 2)[0 if idioma == "es" else 1]}
            for b in _cache]
