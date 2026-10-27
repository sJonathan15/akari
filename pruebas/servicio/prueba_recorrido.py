"""Recorrido de bienvenida por la API: arranca solo la primera vez, avanza, retrocede, salta, se repite
y sigue en el mismo paso después de reiniciar el servicio."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
URL = f"http://127.0.0.1:{os.environ.get('AKARI_PUERTO') or 47830}"


class Recorrido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h = tempfile.mkdtemp()
        cls.env = {**os.environ, "HOME": h, "USERPROFILE": h, "APPDATA": os.path.join(h, "AppData", "Roaming"),
                   "LOCALAPPDATA": os.path.join(h, "AppData", "Local"), "XDG_CONFIG_HOME": os.path.join(h, ".config"),
                   "XDG_CACHE_HOME": os.path.join(h, ".cache"), "XDG_DATA_HOME": os.path.join(h, ".local", "share"),
                   "AKARI_DEMO": "1", "LANG": "es_ES.UTF-8"}
        cls.proc = None

    def arrancar(self):
        self.parar()
        self.__class__.proc = subprocess.Popen([sys.executable, str(RAIZ / "bin" / "akari.py"), "servicio"], env=self.env,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                urllib.request.urlopen(URL + "/api/recorrido", timeout=1).read()
                return
            except OSError:
                time.sleep(0.25)
        self.fail("el servicio no arrancó")

    def parar(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(10)
            self.__class__.proc = None

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            cls.proc.wait(10)

    def estado(self):
        with urllib.request.urlopen(URL + "/api/recorrido", timeout=5) as r:
            return json.load(r)

    def accion(self, accion, **extra):
        req = urllib.request.Request(URL + "/api/recorrido", data=json.dumps({"accion": accion, **extra}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)["recorrido"]

    def test_recorrido(self):
        self.arrancar()
        r = self.estado()
        self.assertTrue(r["activo"])                        # la primera vez arranca solo
        self.assertEqual((r["n"], r["paso"]["id"]), (1, "bienvenida"))
        total = r["total"]
        self.assertGreaterEqual(total, 9)
        r = self.accion("siguiente")
        self.assertEqual((r["n"], r["paso"]["grupo"]), (2, "equipo"))
        r = self.accion("siguiente")
        r = self.accion("anterior")
        self.assertEqual(r["n"], 2)
        self.assertTrue(r["paso"]["titulo"] and r["paso"]["texto"])
        # se reanuda en el mismo paso después de reiniciar
        self.arrancar()
        self.assertEqual(self.estado()["n"], 2)
        r = self.accion("ir", paso="cerebro")
        self.assertEqual((r["paso"]["grupo"], r["paso"]["pieza"]), ("archivos", "cerebro"))
        self.assertIn("no mueve", r["paso"]["titulo"])
        self.assertFalse(self.accion("saltar")["activo"])
        self.arrancar()
        self.assertFalse(self.estado()["activo"])         # saltado: no vuelve solo
        r = self.accion("reiniciar")
        self.assertEqual((r["activo"], r["n"]), (True, 1))
        for _ in range(total):
            r = self.accion("siguiente")
        self.assertFalse(r["activo"])                       # al pasar el último, termina
        # en /api/estado también está (lo leen las cápsulas y las burbujas)
        with urllib.request.urlopen(URL + "/api/estado", timeout=5) as resp:
            self.assertIn("recorrido", json.load(resp))
        self.parar()


if __name__ == "__main__":
    unittest.main()
