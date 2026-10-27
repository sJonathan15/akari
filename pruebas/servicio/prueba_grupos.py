"""Grupos de cápsulas/burbujas: tres grupos, piezas ocultables y el ancho de la píldora cerrada."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from akari import grupos  # noqa: E402
from akari.comun import CONFIG  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def ocultar(lista):
    CONFIG.mkdir(parents=True, exist_ok=True)
    (CONFIG / "capsulas.json").write_text(json.dumps({"ocultas": lista}))


class Grupos(unittest.TestCase):
    def tearDown(self):
        ocultar([])

    def test_tres_grupos_como_mucho(self):
        b = grupos.burbujas()
        self.assertEqual([g["id"] for g in b["grupos"]], ["equipo", "ia", "archivos"])
        self.assertEqual(len(grupos.GRUPO_DE), sum(len(g["piezas"]) for g in grupos.GRUPOS))   # cada pieza en un solo grupo

    def test_ocultar_piezas_y_grupos(self):
        ocultar(["audio", "cerebro", "equipo"])
        b = grupos.burbujas()
        self.assertEqual([g["id"] for g in b["grupos"]], ["ia", "archivos"])
        archivos = b["grupos"][1]
        self.assertEqual([p["id"] for p in archivos["piezas"]], ["documentos"])
        self.assertFalse(archivos["pestanas"])          # una sola pieza: sin pestañas
        self.assertEqual(archivos["anchoCerrado"], 58 + grupos.MARGEN_CHIPS)
        # el panel las muestra todas
        self.assertEqual(len(grupos.burbujas(todas=True)["grupos"]), 3)

    def test_grupo_sin_piezas_no_aparece(self):
        ocultar(["documentos", "audio", "cerebro"])
        self.assertNotIn("archivos", [g["id"] for g in grupos.burbujas()["grupos"]])

    def test_las_capsulas_tienen_las_mismas_piezas(self):
        # shell.qml (Quickshell) y grupos.py (app de escritorio) deben decir lo mismo
        shell = (RAIZ / "capsulas" / "shell.qml").read_text(encoding="utf-8")
        for g in grupos.GRUPOS:
            self.assertIn(f'nombre: "{g["id"]}"', shell)
            for p in g["piezas"]:
                archivo = next((RAIZ / "capsulas").glob(f"Pieza{p['id'].capitalize()}.qml"), None)
                self.assertIsNotNone(archivo, p["id"])
                texto = archivo.read_text(encoding="utf-8")
                self.assertIn(f'clave: "{p["id"]}"', texto)
                self.assertIn(f"anchoChip: {p['chip']}", texto)


if __name__ == "__main__":
    unittest.main()
