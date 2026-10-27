"""Grupos y piezas de las burbujas (akari/burbujas.py, ver AGENTS.md)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akari import burbujas


class Burbujas(unittest.TestCase):
    def test_tres_grupos_y_nada_suelto(self):
        grupos = burbujas.lista("es")
        self.assertEqual([g["nombre"] for g in grupos], ["equipo", "ia", "archivos"])
        piezas = {g["nombre"]: [p["nombre"] for p in g["piezas"]] for g in grupos}
        self.assertIn("dispositivos", piezas["equipo"])
        self.assertIn("habilidades", piezas["ia"])
        self.assertIn("documentos", piezas["archivos"])
        for g in grupos:
            self.assertGreaterEqual(g["anchoAbierto"], max(burbujas.PIEZAS[p]["abierta"] for p in piezas[g["nombre"]]))
            self.assertTrue(all(p["titulo"] and p["icono"] and p["ancho"] for p in g["piezas"]))
        self.assertTrue(next(g for g in grupos if g["nombre"] == "ia")["teclado"])

    def test_solo_lo_que_la_web_dibuja(self):
        with mock.patch.object(burbujas, "secciones_web", return_value={"ia", "dispositivos"}):
            grupos = burbujas.lista("en")
        self.assertEqual([g["nombre"] for g in grupos], ["equipo", "ia"])
        self.assertEqual([g["pagina"] for g in grupos], ["dispositivos", "ia"])      # sin vista de grupo todavía
        with mock.patch.object(burbujas, "secciones_web", return_value={"ia", "dispositivos", "equipo", "archivos"}):
            self.assertEqual([g["pagina"] for g in burbujas.lista("en")], ["equipo", "ia"])

    def test_ocultas(self):
        carpeta = Path(tempfile.mkdtemp())
        (carpeta / "capsulas.json").write_text('{"ocultas": ["habilidades", "archivos"]}')
        with mock.patch.object(burbujas, "CONFIG", carpeta):
            grupos = {g["nombre"]: [p["nombre"] for p in g["piezas"]] for g in burbujas.lista("es")}
        self.assertNotIn("archivos", grupos)
        self.assertNotIn("habilidades", grupos["ia"])
        self.assertIn("dispositivos", grupos["equipo"])


if __name__ == "__main__":
    unittest.main()
