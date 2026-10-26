"""Colores del escritorio (akari/tema.py) con archivos de ejemplo en un HOME temporal."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akari import tema

HEXA = re.compile(r"^#[0-9a-f]{6}$")


class Tema(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.parches = [mock.patch.object(tema, "HOME", self.home), mock.patch.object(tema, "CONFIG", self.home / "akari"),
                        mock.patch.object(tema, "gnome", lambda: None), mock.patch.object(tema, "windows", lambda: None)]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def escribir(self, ruta, texto):
        ruta = self.home / ruta
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto)

    def test_fabrica(self):
        t = tema.calcular()
        self.assertEqual(t["fuente"], "akari")
        self.assertTrue(all(HEXA.match(v) for v in t["colores"].values()))

    def test_acento(self):
        c = tema.desde_acento("#3584e4")
        self.assertTrue(all(HEXA.match(v) for v in c.values()))
        self.assertNotEqual(c["primary"], tema.FABRICA["primary"])

    def test_kde(self):
        self.escribir(".config/kdeglobals", "[Colors:Selection]\nBackgroundNormal=61,174,233\n\n[General]\nAccentColor=233,84,32\n")
        self.assertEqual(tema.kde(), "#e95420")
        self.assertEqual(tema.calcular()["fuente"], "kde")

    def test_caelestia_gana(self):
        self.escribir(".config/kdeglobals", "[General]\nAccentColor=233,84,32\n")
        self.escribir(".local/state/caelestia/scheme.json", json.dumps({"colours": {"primary": "ffb4a8", "surface": "1a1110"}}))
        t = tema.calcular()
        self.assertEqual((t["fuente"], t["colores"]["primary"], t["colores"]["surface"]), ("caelestia", "#ffb4a8", "#1a1110"))

    def test_pywal(self):
        self.escribir(".cache/wal/colors.json", json.dumps({"colors": {f"color{i}": c for i, c in
                                                                      enumerate(["#101010", "#777777", "#e0409a", "#888888"])}}))
        self.assertEqual(tema.pywal(), "#e0409a")

    def test_propio(self):
        self.escribir("akari/tema.json", json.dumps({"acento": "#00aa66", "surface": "#000000"}))
        t = tema.calcular()
        self.assertEqual((t["fuente"], t["colores"]["surface"]), ("akari", "#000000"))


if __name__ == "__main__":
    unittest.main()
