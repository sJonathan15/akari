"""Fuente de iconos para las cabeceras nativas de la app de Windows (escritorio/).

Saca de web/vendor/MaterialSymbolsRounded.woff2 (Apache-2.0) solo los iconos que dibujan las
burbujas cerradas, como fuente estática (relleno, peso 400) de pocos KB, y la tabla nombre →
carácter que usa escritorio/src/iconos.rs. Las cabeceras nativas no hacen ligaduras, por eso
cada icono va por su carácter (área privada de Unicode) y no por su nombre.

  python3 herramientas/iconos_nativos.py      (necesita: pip install fonttools brotli)
"""
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "web" / "vendor" / "MaterialSymbolsRounded.woff2"
SALIDA = RAIZ / "escritorio" / "recursos" / "iconos.ttf"
TABLA = RAIZ / "escritorio" / "src" / "iconos.rs"

# lo que usan las cabeceras (web/app.js: htmlCabecera) y algunos para burbujas nuevas
ICONOS = """mouse keyboard headphones smartphone sports_esports devices_other devices auto_awesome swap_horiz
diamond auto_stories music_note spa terminal smart_toy bolt widgets mic description handyman build folder
chat translate notes graphic_eq record_voice_over""".split()


def main():
    f = TTFont(FUENTE)
    # nombre del icono → glifo, por la tabla de ligaduras
    ligaduras = {}
    for lookup in f["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            st = getattr(st, "ExtSubTable", st)
            for primero, lista in getattr(st, "ligatures", {}).items():
                for lig in lista:
                    ligaduras[(primero, *lig.Component)] = lig.LigGlyph
    cmap = f.getBestCmap()
    por_letra = {chr(c): g for c, g in cmap.items() if c < 0x80}
    inverso = {}
    for c, g in cmap.items():
        if c >= 0xE000:
            inverso.setdefault(g, c)
    tabla = {}
    for nombre in ICONOS:
        clave = tuple(por_letra[ch] for ch in nombre)
        glifo = ligaduras.get(clave)
        if glifo is None or glifo not in inverso:
            raise SystemExit(f"no encontré el icono {nombre}")
        tabla[nombre] = inverso[glifo]

    estatica = instancer.instantiateVariableFont(f, {"FILL": 1, "wght": 400, "GRAD": 0, "opsz": 20})
    opciones = subset.Options()
    opciones.layout_features = []
    opciones.name_IDs = ["*"]
    opciones.notdef_outline = True
    recorte = subset.Subsetter(opciones)
    recorte.populate(unicodes=list(tabla.values()))
    recorte.subset(estatica)
    estatica.flavor = None
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    estatica.save(SALIDA)

    filas = "\n".join(f'  ("{n}", \'\\u{{{c:x}}}\'),' for n, c in sorted(tabla.items()))
    TABLA.write_text(f"""//! Iconos de Material Symbols (Apache-2.0) para las cabeceras nativas. Generado por
//! herramientas/iconos_nativos.py: no editar a mano.
pub const FUENTE: &[u8] = include_bytes!("../recursos/iconos.ttf");

pub const TABLA: &[(&str, char)] = &[
{filas}
];

pub fn icono(nombre: &str) -> char {{
  TABLA.iter().find(|(n, _)| *n == nombre).or_else(|| TABLA.iter().find(|(n, _)| *n == "widgets")).map(|(_, c)| *c).unwrap_or('?')
}}
""")
    print(f"{len(tabla)} iconos → {SALIDA.relative_to(RAIZ)} ({SALIDA.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
