"""El servicio de verdad, en un proceso aparte con un HOME vacío: arranca, responde y sirve el panel."""
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
URL = f"http://127.0.0.1:{os.environ.get('AKARI_PUERTO') or 47830}"     # otro puerto si akari ya está corriendo


class Servicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        env = {**os.environ, "HOME": cls.home, "USERPROFILE": cls.home, "APPDATA": os.path.join(cls.home, "AppData", "Roaming"),
               "LOCALAPPDATA": os.path.join(cls.home, "AppData", "Local"), "XDG_CONFIG_HOME": os.path.join(cls.home, ".config"),
               "XDG_CACHE_HOME": os.path.join(cls.home, ".cache"), "XDG_DATA_HOME": os.path.join(cls.home, ".local", "share"),
               "AKARI_DEMO": os.environ.get("AKARI_DEMO", ""), "AKARI_RELEASES_URL": "http://127.0.0.1:9"}
        cls.proc = subprocess.Popen([sys.executable, str(RAIZ / "bin" / "akari.py"), "servicio"], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                urllib.request.urlopen(URL + "/api/estado", timeout=1).read()
                break
            except OSError:
                time.sleep(0.25)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(10)

    def pedir(self, ruta):
        with urllib.request.urlopen(URL + ruta, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def test_estado(self):
        time.sleep(4)          # que pase al menos una lectura de dispositivos (en Windows, PnP)
        _, _, cuerpo = self.pedir("/api/estado")
        e = json.loads(cuerpo)
        self.assertIn(e["sistema"], ("linux", "windows"))
        self.assertIn("primary", e["tema"]["colores"])
        self.assertIsInstance(e["dispositivos"], dict)
        self.assertIn("habilidades", e)
        self.assertIn("configurado", e["cerebro"])

    def test_panel_y_burbuja(self):
        estado, tipo, cuerpo = self.pedir("/?vista=burbuja&c=ia")
        self.assertEqual(estado, 200)
        self.assertTrue(tipo.startswith("text/html"))
        self.assertIn(b'id="burbuja"', cuerpo)
        self.assertEqual(self.pedir("/app.js")[0], 200)

    def test_burbujas(self):
        _, tipo, cuerpo = self.pedir("/api/burbujas")
        grupos = json.loads(cuerpo)["grupos"]
        self.assertEqual([g["id"] for g in grupos], ["equipo", "ia", "archivos"])
        self.assertTrue(all(g["piezas"] and g["anchoCerrado"] > 0 for g in grupos))
        self.assertEqual(self.pedir("/?vista=burbuja&c=archivos")[0], 200)

    def test_reposo(self):
        # la app de escritorio avisa qué hay abierto: con nada abierto, el servicio va a su ritmo de reposo
        def avisar(abiertas):
            r = urllib.request.Request(URL + "/api/burbujas", data=json.dumps({"abiertas": abiertas}).encode(),
                                       method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=5) as respuesta:
                return json.loads(respuesta.read())["reposo"]
        self.assertTrue(avisar([]))
        self.assertFalse(avisar(["ia"]))
        self.assertFalse(json.loads(self.pedir("/api/burbujas")[2])["reposo"])

    def test_solo_json(self):
        r = urllib.request.Request(URL + "/api/ajustes", data=b"idioma=es", method="POST",
                                   headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(r, timeout=5)
        self.assertEqual(e.exception.code, 415)


if __name__ == "__main__":
    unittest.main()
