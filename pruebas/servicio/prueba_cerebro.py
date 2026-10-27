"""Cerebro con una carpeta personal falsa (en un proceso aparte: las rutas de akari se fijan al importar).

El mapa encuentra lo repartido y nunca .ssh ni .env; la bóveda no copia contenido; nada se mueve ni
cambia (mtime y sha256 antes y después); lo escrito a mano fuera de las marcas sobrevive; los ganchos
se ponen y se quitan dejando settings.json y AGENTS.md como estaban; las sesiones van a la bitácora.
"""
import hashlib
import http.server
import json
import re
import threading
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CONTENIDO = "texto del capitulo tres que la boveda no copia"


class OllamaFalso(http.server.BaseHTTPRequestHandler):
    """Lo mínimo de Ollama para la búsqueda por significado: un modelo de embeddings que convierte cada
    palabra (sin el prefijo de la tarea) en una dimensión. Parecido = comparte palabras."""
    def log_message(self, *a):
        pass

    def _json(self, datos):
        cuerpo = json.dumps(datos).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._json({"models": [{"name": "embeddinggemma:300m", "size": 600 * 2**20, "digest": "x"}]})

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            return self._json({"capabilities": ["embedding"]})
        vectores = []
        for texto in datos["input"]:
            texto = texto.split(": ", 2)[-1].lower()            # sin «task: … | query: »
            v = [0.0] * 300
            for palabra in re.findall(r"\w{3,}", texto):
                v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 256] += 1
            vectores.append(v)
        self._json({"embeddings": vectores})


def armar(h):
    archivos = {
        "Documentos/Universidad/2026/tesis/informe de la tesis.docx": "x",
        "Documentos/Universidad/2026/tesis/capitulo-3.md": CONTENIDO + "\nLa fotosíntesis de las algas marinas.",
        "Descargas/CV-2026.pdf": "x",
        "Trabajo/Informes/ventas.xlsx": "x",
        "Proyectos/web/package.json": '{"name": "web"}',
        "Proyectos/web/README.md": "# Web\n\nLa tienda en línea de la familia, hecha con Vite.\n",
        "Proyectos/web/node_modules/lib/index.js": "x",
        "Proyectos/web/.git/HEAD": "ref",
        ".ssh/id_rsa": "llave",
        ".env": "TOKEN=1",
        "Documentos/credentials.json": "{}",
        "Documentos/llave.pem": "x",
    }
    for i in range(6):
        archivos[f"Documentos/Universidad/2025/apunte{i}.pdf"] = "x"
        archivos[f"Trabajo/Informes/informe-{i}.xlsx"] = "x"
    for rel, texto in archivos.items():
        ruta = Path(h) / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")


def huellas(h, fuera):
    """ruta -> (mtime, sha256) de todo lo del usuario (sin la bóveda ni los datos de akari)."""
    salida = {}
    for raiz, dirs, archivos in os.walk(h):
        dirs[:] = [d for d in dirs if os.path.join(raiz, d) not in fuera]
        for a in archivos:
            p = os.path.join(raiz, a)
            salida[p] = (os.stat(p).st_mtime_ns, hashlib.sha256(Path(p).read_bytes()).hexdigest())
    return salida


class Cerebro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        armar(cls.home)
        h = cls.home
        cls.env = {**os.environ, "HOME": h, "USERPROFILE": h, "APPDATA": os.path.join(h, "AppData", "Roaming"),
                   "LOCALAPPDATA": os.path.join(h, "AppData", "Local"), "XDG_CONFIG_HOME": os.path.join(h, ".config"),
                   "XDG_CACHE_HOME": os.path.join(h, ".cache"), "XDG_DATA_HOME": os.path.join(h, ".local", "share"),
                   "LANG": "es_ES.UTF-8", "OLLAMA_HOST": "http://127.0.0.1:9", "CLAUDE_CONFIG_DIR": os.path.join(h, ".claude"),
                   "CODEX_HOME": os.path.join(h, ".codex"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        cls.env.pop("CLAUDECODE", None)
        cls.ollama = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaFalso)
        threading.Thread(target=cls.ollama.serve_forever, daemon=True).start()
        cls.env["OLLAMA_HOST"] = f"http://127.0.0.1:{cls.ollama.server_address[1]}"
        cls.boveda = os.path.join(h, "Cerebro")
        fuera = {cls.boveda, os.path.join(h, ".config"), os.path.join(h, ".local"), os.path.join(h, ".cache"),
                 os.path.join(h, "AppData")}
        cls.antes = huellas(h, fuera)
        cls.py("from akari import cerebro as C; print(C.configurar([C.HOME])); C.revisar()")
        cls.despues = huellas(h, fuera)

    @classmethod
    def tearDownClass(cls):
        cls.ollama.shutdown()

    @classmethod
    def py(cls, codigo):
        r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), env=cls.env, capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return r.stdout

    def akari(self, *args, entrada=None):
        r = subprocess.run([sys.executable, str(RAIZ / "bin" / "akari.py"), "cerebro", *args], env=self.env, input=entrada,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return r.stdout

    def test_mapa_encuentra_y_excluye(self):
        self.assertIn("informe de la tesis.docx", self.akari("buscar", "informe", "tesis"))
        self.assertIn("CV-2026.pdf", self.akari("donde", "cv"))
        for oculto in ("id_rsa", "env", "credentials", "llave", "index"):
            self.assertNotIn(oculto, self.akari("buscar", oculto).lower().replace("no lo encontré", ""), oculto)
        proyectos = self.akari("proyectos")
        self.assertIn("web", proyectos)
        areas = json.loads(self.py("import json; from akari import cerebro as C; print(json.dumps([a['nombre'] for a in C.areas()]))"))
        self.assertIn("Universidad", areas)
        self.assertIn("Trabajo", areas)

    def test_nada_se_mueve_ni_cambia(self):
        self.assertEqual(self.antes, self.despues)

    def test_la_boveda_solo_enlaza(self):
        notas = list(Path(self.boveda).rglob("*.md"))
        self.assertTrue(any(n.name == "Inicio.md" for n in notas))
        self.assertTrue((Path(self.boveda) / "Mapa" / "Universidad.md").exists())
        for n in notas:
            texto = n.read_text(encoding="utf-8")
            self.assertNotIn(CONTENIDO, texto, n)
            self.assertIn("<!-- akari -->", texto)
        self.assertIn("file://", (Path(self.boveda) / "Mapa" / "Universidad.md").read_text(encoding="utf-8"))

    def test_lo_escrito_a_mano_sobrevive(self):
        inicio = Path(self.boveda) / "Inicio.md"
        inicio.write_text("Mi nota arriba\n\n" + inicio.read_text(encoding="utf-8") + "\nY otra abajo\n", encoding="utf-8")
        self.py("from akari import cerebro as C; C.revisar()")
        texto = inicio.read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("Mi nota arriba\n"))
        self.assertIn("Y otra abajo", texto)
        self.assertEqual(texto.count("<!-- akari -->"), 1)

    def test_pendientes_y_notas(self):
        salida = self.akari("pendiente", "Pagar", "la", "matrícula")
        self.assertIn("#", salida)
        self.assertIn("Pagar la matrícula", self.akari("pendientes"))
        self.assertIn("Pagar la matrícula", (Path(self.boveda) / "Pendientes.md").read_text(encoding="utf-8"))
        self.assertIn("Pagar", self.akari("hecho", "matrícula"))
        self.assertNotIn("Pagar la matrícula", self.akari("pendientes"))
        self.akari("nota", "Hablé con el profesor")
        hoy = time.strftime("%Y-%m-%d")
        self.assertIn("Hablé con el profesor", (Path(self.boveda) / "Bitacora" / f"{hoy}.md").read_text(encoding="utf-8"))

    def test_casilla_marcada_en_obsidian(self):
        self.akari("pendiente", "Llamar", "al", "banco")
        nota = Path(self.boveda) / "Pendientes.md"
        nota.write_text(nota.read_text(encoding="utf-8").replace("- [ ] Llamar al banco", "- [x] Llamar al banco"), encoding="utf-8")
        futuro = time.time() + 5
        os.utime(nota, (futuro, futuro))
        self.akari("pendiente", "Otra", "cosa")          # al reescribir la nota se lee lo marcado
        self.assertNotIn("Llamar al banco", self.akari("pendientes"))

    def test_ganchos_dejan_todo_como_estaba(self):
        claude = Path(self.home) / ".claude"
        codex = Path(self.home) / ".codex"
        claude.mkdir(exist_ok=True)
        codex.mkdir(exist_ok=True)
        ajustes = '{\n    "theme": "dark",\n    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hola"}]}]}\n}\n'
        (claude / "settings.json").write_text(ajustes, encoding="utf-8")
        (codex / "AGENTS.md").write_text("# Mis reglas\n\nSé breve.\n", encoding="utf-8")
        self.akari("conectar")
        puesto = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(puesto["hooks"]), {"Stop", "SessionStart", "SessionEnd"})
        self.assertIn("akari-cerebro", (codex / "AGENTS.md").read_text(encoding="utf-8"))
        contexto = json.loads(self.akari("sesion-inicio", entrada=json.dumps({"cwd": self.home})))
        self.assertIn("cerebro buscar", contexto["hookSpecificOutput"]["additionalContext"])
        self.akari("desconectar")
        self.assertEqual((claude / "settings.json").read_text(encoding="utf-8"), ajustes)
        self.assertEqual((codex / "AGENTS.md").read_text(encoding="utf-8"), "# Mis reglas\n\nSé breve.\n")

    def test_ganchos_sin_archivos_previos(self):
        claude = Path(self.home) / ".claude"
        (claude / "settings.json").unlink(missing_ok=True)
        claude.mkdir(exist_ok=True)
        self.akari("conectar", "claude")
        self.assertTrue((claude / "settings.json").exists())
        self.akari("desconectar", "claude")
        self.assertFalse((claude / "settings.json").exists())

    def test_sesiones_a_la_bitacora(self):
        tesis = os.path.join(self.home, "Documentos", "Universidad", "2026", "tesis")
        carpeta = Path(self.home) / ".claude" / "projects" / "-tesis"
        carpeta.mkdir(parents=True, exist_ok=True)
        viejo = time.time() - 3600
        cuando = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(viejo))
        lineas = [
            {"type": "user", "sessionId": "s1", "cwd": tesis, "timestamp": cuando,
             "message": {"role": "user", "content": "Ayúdame con el capítulo 3"}},
            {"type": "assistant", "sessionId": "s1", "cwd": tesis, "timestamp": cuando,
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "Edit", "input": {"file_path": os.path.join(tesis, "capitulo-3.md")}},
                 {"type": "text", "text": "Listo; falta la bibliografía."}]}},
        ]
        archivo = carpeta / "s1.jsonl"
        archivo.write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
        os.utime(archivo, (viejo, viejo))
        self.py("from akari import memoria; memoria.procesar()")
        sesiones = self.akari("sesiones")
        self.assertIn("Ayúdame con el capítulo 3", sesiones)
        self.assertIn("tesis", sesiones)
        dia = time.strftime("%Y-%m-%d", time.localtime(viejo))
        bitacora = (Path(self.boveda) / "Bitacora" / f"{dia}.md").read_text(encoding="utf-8")
        self.assertIn("capitulo-3.md", bitacora)
        self.assertIn("Ayúdame con el capítulo 3", self.akari("pregunta", "¿en qué nos quedamos con la tesis?"))

    def test_herramientas_del_asistente(self):
        salida = self.py("from akari import cerebro as C; print(C.usar_herramienta('buscar_archivo', {'consulta': 'cv'}))")
        self.assertIn("CV-2026.pdf", salida)
        fuera = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)        # existe, pero fuera del cerebro
        fuera.close()
        salida = self.py(f"from akari import cerebro as C; ok, m = C.abrir_archivo({fuera.name!r}); print(ok, m)")
        os.unlink(fuera.name)
        self.assertTrue(salida.startswith("False"))

    def test_busqueda_por_significado(self):
        # el texto de los documentos solo se lee en las carpetas que el usuario activa
        tesis = os.path.join(self.home, "Documentos", "Universidad", "2026", "tesis")
        self.py("from akari import cerebro as C; C.SEMANTICA.actualizar(tope=5000)")
        self.assertNotIn("capitulo-3.md", self.py("from akari import cerebro as C; print([r['ruta'] for r in C.SEMANTICA.buscar('fotosíntesis algas')])"))
        self.py(f"from akari import cerebro as C; C.configurar([C.HOME], texto_en=[{tesis!r}]); C.SEMANTICA.actualizar(tope=5000)")
        hallados = self.py("from akari import cerebro as C; print([r['ruta'] for r in C.SEMANTICA.buscar('fotosíntesis algas')])")
        self.assertIn("capitulo-3.md", hallados)
        self.assertIn("embeddinggemma", self.akari("estado"))
        self.assertIn("~", self.akari("buscar", "algas", "marinas"))          # «~» = encontrado por significado

    def test_boveda_en_subcarpeta_si_ya_hay_cosas(self):
        otra = Path(self.home) / "MiBoveda"
        (otra / ".obsidian").mkdir(parents=True, exist_ok=True)
        (otra / "nota.md").write_text("mía", encoding="utf-8")
        salida = self.py(f"from akari import cerebro as C; print(C.boveda_para({str(otra)!r}))")
        self.assertEqual(Path(salida.strip()), otra / "akari")


if __name__ == "__main__":
    unittest.main()
