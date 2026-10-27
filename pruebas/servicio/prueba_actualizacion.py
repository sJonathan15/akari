"""Revisión de versiones nuevas contra un GitHub falso (sin internet)."""
import io
import json
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from akari import actualizacion as A  # noqa: E402

RELEASES = [
    {"tag_name": "v0.3.0-beta.1", "prerelease": True, "body": "beta", "html_url": "https://x/b", "assets": []},
    {"tag_name": "v0.2.0", "prerelease": False, "body": "**Novedades**", "html_url": "https://x/e",
     "assets": [{"name": "akari-setup-x64.exe", "browser_download_url": "https://x/e.exe", "size": 1, "otro": 1}]},
    {"tag_name": "v0.4.0", "draft": True},
]


class GitHubFalso(BaseHTTPRequestHandler):
    pedidos = []

    def do_GET(self):
        GitHubFalso.pedidos.append(self.path)
        datos = RELEASES[1] if self.path == "/releases/latest" else RELEASES
        cuerpo = json.dumps(datos).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


class Actualizacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), GitHubFalso)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ajustes = {}
        self.avisos = []
        self.cambios = 0
        GitHubFalso.pedidos = []
        carpeta = Path(tempfile.mkdtemp())
        self.parches = {"API": f"http://127.0.0.1:{self.srv.server_port}", "ARCHIVO": carpeta / "actualizacion.json",
                        "ajustes": lambda: self.ajustes, "notificar": lambda *a, **k: self.avisos.append(a),
                        "VERSION": "0.1.0"}
        self.antes = {k: getattr(A, k) for k in self.parches}
        for k, v in self.parches.items():
            setattr(A, k, v)

    def tearDown(self):
        for k, v in self.antes.items():
            setattr(A, k, v)

    def revisor(self):
        def cambio():
            self.cambios += 1
        return A.Revisor(cambio)

    def test_orden_de_versiones(self):
        orden = ["0.1.0", "0.2.0-alpha", "0.2.0-beta.1", "0.2.0-beta.2", "0.2.0-beta.10", "0.2.0", "v0.2.1", "0.10.0"]
        claves = [A.clave(v) for v in orden]
        self.assertEqual(claves, sorted(claves))
        self.assertTrue(A.mas_nueva("v0.2.0", "0.2.0-beta.1"))
        self.assertFalse(A.mas_nueva("0.1.0", "0.1.0"))
        self.assertFalse(A.mas_nueva("cualquiera", "0.1.0"))
        self.assertTrue(A.es_beta("0.2.0-beta.1") and not A.es_beta("0.2.0"))

    def test_estable_avisa_una_vez(self):
        r = self.revisor()
        r.revisar()
        self.assertEqual(GitHubFalso.pedidos, ["/releases/latest"])       # sin prereleases
        self.assertEqual(r.estado, {"version": "0.2.0", "notas": "**Novedades**", "url": "https://x/e", "beta": False,
                                   "pospuesta": False, "instalando": False})
        self.assertEqual(len(self.avisos), 1)
        self.assertGreater(self.cambios, 0)
        # al día siguiente no se vuelve a pedir ni a avisar (y lo guardado sobrevive a un reinicio)
        r2 = self.revisor()
        self.assertEqual(r2.estado["version"], "0.2.0")
        r2.revisar()
        self.assertEqual(len(GitHubFalso.pedidos), 1)
        self.assertEqual(len(self.avisos), 1)
        self.assertNotIn("otro", r2.release["assets"][0])

    def test_en_una_beta_tambien_betas(self):
        A.VERSION = "0.2.0-beta.1"
        r = self.revisor()
        r.revisar()
        self.assertEqual(GitHubFalso.pedidos, ["/releases?per_page=20"])
        self.assertEqual((r.estado["version"], r.estado["beta"]), ("0.3.0-beta.1", True))     # el borrador no cuenta

    def test_al_dia_y_apagado(self):
        A.VERSION = "0.2.0"
        r = self.revisor()
        r.revisar()
        self.assertIsNone(r.estado)
        self.ajustes["actualizar"] = "beta"
        r.revisar()       # otro modo: se vuelve a pedir
        self.assertEqual(r.estado["version"], "0.3.0-beta.1")
        self.ajustes["actualizar"] = False
        r.revisar()
        self.assertIsNone(r.estado)
        self.assertEqual(len(GitHubFalso.pedidos), 2)

    def test_sin_internet(self):
        A.API = "http://127.0.0.1:9"
        r = self.revisor()
        r.revisar()
        self.assertIsNone(r.estado)


    def test_ahora_no_y_ya_al_dia(self):
        r = self.revisor()
        self.assertEqual(r.accion({"accion": "instalar"})[0], False)        # nada que instalar todavía
        r.revisar()
        self.assertTrue(r.accion({"accion": "ahora-no"})[0])
        self.assertTrue(r.estado["pospuesta"])
        # pospuesta: no vuelve a avisar de esa versión, aunque se revise de nuevo
        r.revisar(forzar=True)
        self.assertEqual(len(self.avisos), 1)

    def test_como_se_instalo(self):
        raiz = Path(tempfile.mkdtemp())
        (raiz / ".git").mkdir()
        self.assertEqual(A.instalacion(raiz), "git")
        app = Path(tempfile.mkdtemp())
        (app / "servicio").mkdir()
        (app / "akari.exe").touch()
        self.assertEqual(A.instalacion(app / "servicio"), "windows-app")
        self.assertEqual(A.instalacion(Path(tempfile.mkdtemp())), "otra")

    def test_extraer_sin_salirse(self):
        carpeta = Path(tempfile.mkdtemp())
        archivo = carpeta / "a.tar.gz"
        with tarfile.open(archivo, "w:gz") as tf:
            for nombre in ("akari-1.0/install.sh", "../fuera.txt", "/tmp/absoluta.txt"):
                info = tarfile.TarInfo(nombre)
                info.size = 2
                tf.addfile(info, io.BytesIO(b"ok"))
            enlace = tarfile.TarInfo("akari-1.0/enlace")
            enlace.type, enlace.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tf.addfile(enlace)
        dentro = A.extraer(archivo, carpeta / "x")
        self.assertEqual(dentro.name, "akari-1.0")
        self.assertEqual(sorted(p.name for p in dentro.iterdir()), ["install.sh"])
        self.assertFalse((carpeta / "fuera.txt").exists())


if __name__ == "__main__":
    unittest.main()
