#!/usr/bin/env python3
"""Prepara los modelos 3D de akari (todos CC0, dominio público).

  * ratón, audífonos y celular: modelos CC0 de Poly Pizza;
  * teclado: se genera aquí mismo (cuerpo + teclas), así que es nuestro y también CC0;
  * luz de estudio: HDRI CC0 de Poly Haven.

Cada modelo se centra y se escala a 1 unidad de lado (Qt Quick 3D no informa bien las
medidas de los .glb al cargarlos en tiempo de ejecución, y el panel web lo agradece).

Uso:  python3 herramientas/modelos.py      (deja todo en modelos/ y escribe CREDITS.md)
"""
import json
import struct
import urllib.request
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "modelos"

POLY_PIZZA = {
    "mouse": {"url": "https://static.poly.pizza/c0123ed1-38d1-4532-a711-3fccdc42fe25.glb",
              "titulo": "Computer Mouse", "autor": "CreativeTrio", "pagina": "https://poly.pizza/m/V2Ebx3pvo4"},
    "headphones": {"url": "https://static.poly.pizza/b72a848f-b4c6-40fb-ada7-69c4c524bd27.glb",
                   "titulo": "Headphones", "autor": "CreativeTrio", "pagina": "https://poly.pizza/m/PSsWSIAYIL"},
    "phone": {"url": "https://static.poly.pizza/bb788859-3dca-4a80-b4da-f5f26e6148f6.glb",
              "titulo": "Phone", "autor": "Quaternius", "pagina": "https://poly.pizza/m/k2kgBepoMU"},
}
HDRI = {"url": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/studio_small_09_1k.hdr",
        "titulo": "Studio Small 09", "autor": "Sergej Majboroda", "pagina": "https://polyhaven.com/a/studio_small_09"}


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "akari/0.1 (+https://github.com/sJonathan15/akari)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# ------------------------------------------------------------------ glb

def leer_glb(datos):
    magia, version, _ = struct.unpack_from("<III", datos, 0)
    if magia != 0x46546C67:
        raise ValueError("no es un .glb")
    largo_json = struct.unpack_from("<I", datos, 12)[0]
    return json.loads(datos[20:20 + largo_json]), datos[20 + largo_json:]


def escribir_glb(gltf, resto=b""):
    texto = json.dumps(gltf, separators=(",", ":")).encode()
    texto += b" " * ((4 - len(texto) % 4) % 4)
    cuerpo = struct.pack("<II", len(texto), 0x4E4F534A) + texto + resto
    return struct.pack("<III", 0x46546C67, 2, 12 + len(cuerpo)) + cuerpo


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _matriz(nodo):
    if "matrix" in nodo:
        m = nodo["matrix"]          # glTF guarda por columnas
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = nodo.get("translation", [0, 0, 0])
    x, y, z, w = nodo.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = nodo.get("scale", [1, 1, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0, 0, 0, 1]]


def normalizar(datos):
    """Envuelve la escena en un nodo que la centra y la deja de 1 unidad de lado."""
    gltf, resto = leer_glb(datos)
    nodos, mallas, accesos = gltf.get("nodes", []), gltf.get("meshes", []), gltf.get("accessors", [])
    minimo, maximo = [float("inf")] * 3, [float("-inf")] * 3

    def recorrer(i, padre):
        nodo = nodos[i]
        m = _mul(padre, _matriz(nodo))
        if "mesh" in nodo:
            for prim in mallas[nodo["mesh"]]["primitives"]:
                a = accesos[prim["attributes"]["POSITION"]]
                for x in (a["min"][0], a["max"][0]):
                    for y in (a["min"][1], a["max"][1]):
                        for z in (a["min"][2], a["max"][2]):
                            p = [sum(m[f][c] * v for c, v in enumerate((x, y, z, 1))) for f in range(3)]
                            for k in range(3):
                                minimo[k] = min(minimo[k], p[k])
                                maximo[k] = max(maximo[k], p[k])
        for h in nodo.get("children", []):
            recorrer(h, m)

    identidad = [[float(i == j) for j in range(4)] for i in range(4)]
    escena = gltf["scenes"][gltf.get("scene", 0)]
    for raiz in escena["nodes"]:
        recorrer(raiz, identidad)
    lado = max(maximo[k] - minimo[k] for k in range(3)) or 1
    f = 1 / lado
    centro = [(minimo[k] + maximo[k]) / 2 for k in range(3)]
    nodos.append({"name": "akari-ajuste", "children": list(escena["nodes"]),
                  "scale": [f, f, f], "translation": [-c * f for c in centro]})
    escena["nodes"] = [len(nodos) - 1]
    return escribir_glb(gltf, resto)


# ------------------------------------------------------------- teclado propio

def caja(x0, y0, z0, x1, y1, z1, bisel=0.0):
    """Vértices, normales e índices de una caja (con la cara de arriba algo más chica: tecla)."""
    a = bisel
    caras = [  # (normal, 4 esquinas)
        ((0, 1, 0), [(x0 + a, y1, z0 + a), (x1 - a, y1, z0 + a), (x1 - a, y1, z1 - a), (x0 + a, y1, z1 - a)]),
        ((0, -1, 0), [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]),
        ((0, 0, 1), [(x0, y0, z1), (x0 + a, y1, z1 - a), (x1 - a, y1, z1 - a), (x1, y0, z1)]),
        ((0, 0, -1), [(x1, y0, z0), (x1 - a, y1, z0 + a), (x0 + a, y1, z0 + a), (x0, y0, z0)]),
        ((1, 0, 0), [(x1, y0, z1), (x1 - a, y1, z1 - a), (x1 - a, y1, z0 + a), (x1, y0, z0)]),
        ((-1, 0, 0), [(x0, y0, z0), (x0 + a, y1, z0 + a), (x0 + a, y1, z1 - a), (x0, y0, z1)]),
    ]
    pos, nor, ind = [], [], []
    for n, esquinas in caras:
        base = len(pos)
        pos += esquinas
        nor += [n] * 4
        ind += [base, base + 2, base + 1, base, base + 3, base + 2]   # antihorario visto desde fuera
    return pos, nor, ind


def teclado():
    """Teclado compacto (75 %) con cuerpo, teclas y barra espaciadora. Unidades: cm."""
    u, hueco = 1.9, 0.18          # paso de tecla y separación
    filas = [  # anchos en unidades de tecla
        [1] * 13 + [1, 1],
        [1.5] + [1] * 12 + [1.5, 1],
        [1.75] + [1] * 11 + [2.25, 1],
        [2.25] + [1] * 10 + [1.75, 1, 1],
        [1.25, 1.25, 1.25, 6.25, 1, 1, 1, 1, 1],
    ]
    ancho = 15 * u
    fondo = len(filas) * u
    margen = 0.9
    piezas = {"cuerpo": ([], [], []), "teclas": ([], [], []), "acento": ([], [], [])}

    def agregar(destino, datos):
        pos, nor, ind = piezas[destino]
        base = len(pos)
        pos += datos[0]
        nor += datos[1]
        ind += [base + i for i in datos[2]]

    agregar("cuerpo", caja(-ancho / 2 - margen, 0, -fondo / 2 - margen, ancho / 2 + margen, 1.6, fondo / 2 + margen, 0.25))
    for f, fila in enumerate(filas):
        z = -fondo / 2 + f * u
        x = -ancho / 2
        for i, w in enumerate(fila):
            # acento: Esc, Enter y las flechas de la derecha
            destino = "acento" if (f == 0 and i == 0) or (f == 2 and w == 2.25) else "teclas"
            agregar(destino, caja(x + hueco, 1.6, z + hueco, x + w * u - hueco, 2.55, z + u - hueco, 0.22))
            x += w * u
    return piezas


def glb_desde_piezas(piezas, colores):
    binario = bytearray()
    vistas, accesos, mallas, nodos, materiales = [], [], [], [], []
    for nombre, (pos, nor, ind) in piezas.items():
        prims = []
        for datos, formato, tipo, objetivo in ((pos, "<3f", "VEC3", 34962), (nor, "<3f", "VEC3", 34962),
                                              (ind, "<I", "SCALAR", 34963)):
            inicio = len(binario)
            for v in datos:
                binario += struct.pack(formato, *(v if isinstance(v, tuple) else (v,)))
            vistas.append({"buffer": 0, "byteOffset": inicio, "byteLength": len(binario) - inicio, "target": objetivo})
            acceso = {"bufferView": len(vistas) - 1, "count": len(datos), "type": tipo,
                      "componentType": 5126 if tipo == "VEC3" else 5125}
            if datos is pos:
                acceso["min"] = [min(p[k] for p in pos) for k in range(3)]
                acceso["max"] = [max(p[k] for p in pos) for k in range(3)]
            accesos.append(acceso)
            prims.append(len(accesos) - 1)
        materiales.append({"name": nombre, "pbrMetallicRoughness": {
            "baseColorFactor": [*colores[nombre], 1], "metallicFactor": 0.0, "roughnessFactor": 0.55}})
        mallas.append({"name": nombre, "primitives": [{"attributes": {"POSITION": prims[0], "NORMAL": prims[1]},
                                                         "indices": prims[2], "material": len(materiales) - 1}]})
        nodos.append({"name": nombre, "mesh": len(mallas) - 1})
    gltf = {"asset": {"version": "2.0", "generator": "akari herramientas/modelos.py"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodos)))}], "nodes": nodos, "meshes": mallas,
            "materials": materiales, "accessors": accesos, "bufferViews": vistas,
            "buffers": [{"byteLength": len(binario)}]}
    binario += b"\0" * ((4 - len(binario) % 4) % 4)
    gltf["buffers"][0]["byteLength"] = len(binario)
    resto = struct.pack("<II", len(binario), 0x004E4942) + bytes(binario)
    return escribir_glb(gltf, resto)


# ------------------------------------------------------------------ main

def main():
    DESTINO.mkdir(exist_ok=True)
    creditos = ["# 3D models / Modelos 3D", "",
                "All models and the studio light are **CC0 1.0 (public domain)**: free to use, modify and",
                "redistribute, even commercially, without attribution. We credit the authors anyway, with thanks.",
                "",
                "Todos los modelos y la luz de estudio son **CC0 1.0 (dominio público)**. Igual damos crédito.", ""]
    for nombre, m in POLY_PIZZA.items():
        print(f"{nombre}: {m['titulo']} ({m['autor']})")
        (DESTINO / f"{nombre}.glb").write_bytes(normalizar(bajar(m["url"])))
        creditos.append(f"- `{nombre}.glb` — \"{m['titulo']}\" by {m['autor']} — {m['pagina']} — CC0 1.0")
    print("keyboard: generado")
    (DESTINO / "keyboard.glb").write_bytes(normalizar(glb_desde_piezas(teclado(), {
        "cuerpo": (0.16, 0.17, 0.19), "teclas": (0.86, 0.87, 0.89), "acento": (0.98, 0.62, 0.25)})))
    creditos.append("- `keyboard.glb` — generated by `herramientas/modelos.py` (akari) — CC0 1.0")
    print("studio.hdr: Poly Haven")
    (DESTINO / "studio.hdr").write_bytes(bajar(HDRI["url"]))
    creditos.append(f"- `studio.hdr` — \"{HDRI['titulo']}\" by {HDRI['autor']} — {HDRI['pagina']} — CC0 1.0")
    (DESTINO / "CREDITS.md").write_text("\n".join(creditos) + "\n", encoding="utf-8")
    for f in sorted(DESTINO.iterdir()):
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
