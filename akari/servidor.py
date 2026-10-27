"""Servicio de akari: un solo proceso y un solo puerto (127.0.0.1:47830).

GET  /api/estado          todo junto: {ia, dispositivos, habilidades, sistema}
GET  /eventos             lo mismo por SSE cada vez que cambia
POST /api/ia/activar      {"mensaje": "..."}            (ventana de 5 h de Claude)
POST /api/ia/activador    {"programado", "hora", "mantener", "hasta"}
POST /api/dispositivos    {"id", "accion", "valor"?}
POST /api/habilidades     {"id", "accion", "destino"?}
POST /api/ajustes         {"idioma"?, "avisos"?}
POST /api/modelos         {"accion", ...}           (API o modelos locales, ver modelos.py)
POST /api/documentos      {"accion", ...}           (conversor de documentos ⇄ Markdown)
POST /api/documentos/subir  cuerpo = el archivo; cabeceras X-Akari-Nombre y X-Akari-Formato
GET  /api/burbujas        los grupos (Equipo, IA, Archivos) y sus piezas para las apps (ver burbujas.py)
POST /api/burbujas        {"abiertas": [...]}: la app avisa qué hay abierto; sin nada → reposo
GET  /                    panel web (web/) y /modelos/*.glb
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import PUERTO, VERSION, burbujas, demo
from .comun import CONFIG, IDIOMA, RAIZ, WINDOWS, ajustes, escribir_json
from .dispositivos import MonitorDispositivos
from .habilidades import MonitorHabilidades
from .ia import MonitorIA
from .modelos import MonitorModelos
from .documentos import Conversor
from .tema import Tema

DEMO = os.environ.get("AKARI_DEMO") == "1"     # datos de ejemplo (capturas, pruebas)
MAX_SUBIDA = 200 * 2**20
# La app de Windows (escritorio/) pide revisar como mucho cada 5 s y, si no hay nada abierto
# (solo las cabeceras de las burbujas), bajar al ritmo de reposo: casi nada de CPU.
MINIMO = float(os.environ.get("AKARI_INTERVALO_MIN") or 0)
REPOSO = {"ia": 30, "dispositivos": 120, "habilidades": 120, "tema": 60, "modelos": 120}
ESTATICOS = {"/": RAIZ / "web", "/modelos/": RAIZ / "modelos"}
TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript",
         ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json",
         ".glb": "model/gltf-binary", ".hdr": "application/octet-stream", ".woff2": "font/woff2"}


class Servicio:
    def __init__(self):
        self.cond = threading.Condition()
        self.version = 0
        self.ia = MonitorIA(self.cambio)
        self.dispositivos = MonitorDispositivos(self.cambio)
        self.habilidades = MonitorHabilidades(self.cambio)
        self.modelos = MonitorModelos(self.cambio)
        self.documentos = Conversor(self.cambio)
        self.tema = Tema()
        self._tema = self.tema.valor
        self.reposo = False
        self.despertar = threading.Condition()

    def ventanas(self, abiertas):
        """La app de escritorio dice qué burbujas (o el panel) están abiertas."""
        reposo = not abiertas
        if reposo != self.reposo:
            self.reposo = reposo
            if not reposo:      # al abrir una, datos frescos ya
                with self.despertar:
                    self.despertar.notify_all()

    def revisar_tema(self):
        if self.tema.actual() != self._tema:
            self._tema = self.tema.valor
            self.cambio()

    def cambio(self):
        with self.cond:
            self.version += 1
            self.cond.notify_all()

    def estado(self):
        base = {"version": VERSION, "idioma": IDIOMA, "ahora": time.time(), "tema": self.tema.valor,
                "sistema": "windows" if WINDOWS else "linux"}
        if DEMO:
            return {**base, **demo.estado(), "demo": True}
        return {**base, "ia": self.ia.estado, "dispositivos": self.dispositivos.estado, "habilidades": self.habilidades.estado,
                "modelos": self.modelos.estado, "documentos": self.documentos.estado}

    def _bucle(self, paso, intervalo, reposo):
        while True:
            try:
                paso()
            except Exception as e:      # un archivo raro no debe tumbar el servicio
                print(f"akari: {paso.__qualname__}: {e!r}", file=sys.stderr, flush=True)
            with self.despertar:
                self.despertar.wait(reposo if self.reposo else max(intervalo, MINIMO))

    def arrancar(self):
        for paso, intervalo, clave in ((self.ia.paso, 1, "ia"), (self.dispositivos.leer, 3, "dispositivos"),
                                       (self.habilidades.paso, 5, "habilidades"), (self.revisar_tema, 5, "tema"),
                                       (self.modelos.paso, 10, "modelos")):
            threading.Thread(target=self._bucle, args=(paso, intervalo, REPOSO[clave]), daemon=True).start()
        threading.Thread(target=self.modelos.refrescar_proveedores, daemon=True).start()


def crear_manejador(servicio):
    class Manejador(BaseHTTPRequestHandler):
        server_version = f"akari/{VERSION}"

        def log_message(self, *args):
            pass

        def _enviar(self, codigo, tipo, cuerpo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _json(self, datos, codigo=200):
            self._enviar(codigo, TIPOS[".json"], json.dumps(datos, ensure_ascii=False).encode())

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta == "/api/estado":
                return self._json(servicio.estado())
            if ruta == "/eventos":
                return self._eventos()
            if ruta == "/api/burbujas":
                return self._json({"burbujas": burbujas.lista(IDIOMA), "grupos_web": burbujas.grupos_web(),
                                   "reposo": servicio.reposo})
            base, carpeta = ("/modelos/", ESTATICOS["/modelos/"]) if ruta.startswith("/modelos/") else ("/", ESTATICOS["/"])
            archivo = (carpeta / (ruta[len(base):] or "index.html")).resolve()
            if carpeta.resolve() not in archivo.parents or not archivo.is_file():
                return self._enviar(404, "text/plain", b"not found")
            self._enviar(200, TIPOS.get(archivo.suffix, "application/octet-stream"), archivo.read_bytes())

        def do_POST(self):
            # Solo JSON: una página web cualquiera no puede mandarlo a localhost sin permiso CORS
            # (que no damos), así que nadie de afuera puede accionar nada.
            if self.path.split("?")[0] == "/api/documentos/subir":
                return self._subir()
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json({"ok": False}, 415)
            try:
                largo = min(int(self.headers.get("Content-Length", 0)), 16384)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                if not isinstance(datos, dict):
                    raise ValueError
            except ValueError:
                return self._json({"ok": False}, 400)
            ruta = self.path.split("?")[0]
            if ruta == "/api/ia/activar":
                ok = servicio.ia.activador.activar(str(datos.get("mensaje") or "")[:2000])
                return self._json({"ok": ok})
            if ruta == "/api/ia/activador":
                servicio.ia.activador.cambiar(datos)
                return self._json({"ok": True})
            if ruta == "/api/dispositivos":
                ok, mensaje = servicio.dispositivos.accion(str(datos.get("id")), str(datos.get("accion")), datos.get("valor"))
                threading.Thread(target=servicio.dispositivos.leer, daemon=True).start()
                return self._json({"ok": ok, "mensaje": mensaje})
            if ruta == "/api/habilidades":
                ok, mensaje = servicio.habilidades.accion(str(datos.get("id")), str(datos.get("accion")), datos.get("destino"))
                return self._json({"ok": ok, "mensaje": mensaje})
            if ruta == "/api/modelos":
                ok, mensaje = servicio.modelos.accion(datos)
                return self._json({"ok": ok, "mensaje": mensaje})
            if ruta == "/api/documentos":
                ok, mensaje = servicio.documentos.accion(datos)
                return self._json({"ok": ok, "mensaje": mensaje})
            if ruta == "/api/burbujas":
                abiertas = datos.get("abiertas")
                servicio.ventanas([str(x) for x in abiertas] if isinstance(abiertas, list) else [])
                return self._json({"ok": True, "reposo": servicio.reposo})
            if ruta == "/api/ajustes":
                a = ajustes()
                if datos.get("idioma") in ("es", "en", "auto"):
                    a["idioma"] = datos["idioma"]
                if isinstance(datos.get("avisos"), bool):
                    a["avisos"] = datos["avisos"]
                escribir_json(CONFIG / "ajustes.json", a)
                return self._json({"ok": True, "reiniciar": "idioma" in datos})
            self._json({"ok": False}, 404)

        def _subir(self):
            # application/octet-stream + cabecera propia: un navegador no lo manda a otro sitio sin
            # preguntar antes (CORS), y aquí nunca se le da permiso.
            from urllib.parse import unquote
            if (self.headers.get("Content-Type", "").split(";")[0].strip() != "application/octet-stream"
                    or not self.headers.get("X-Akari-Nombre")):
                return self._json({"ok": False}, 415)
            largo = int(self.headers.get("Content-Length") or 0)
            if not 0 < largo <= MAX_SUBIDA:
                return self._json({"ok": False, "mensaje": "> 200 MB"}, 413)
            contenido = self.rfile.read(largo)
            ok, mensaje = servicio.documentos.subir(unquote(self.headers["X-Akari-Nombre"]), contenido,
                                                    self.headers.get("X-Akari-Formato", "docx"))
            return self._json({"ok": ok, "mensaje": mensaje})

        def _eventos(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            visto = -1
            try:
                while True:
                    with servicio.cond:
                        if servicio.version == visto:
                            servicio.cond.wait(timeout=15)
                        version = servicio.version
                    if version != visto:
                        visto = version
                        self.wfile.write(b"data: " + json.dumps(servicio.estado()).encode() + b"\n\n")
                    else:
                        self.wfile.write(b": latido\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    return Manejador


class Servidor(ThreadingHTTPServer):
    # en Windows SO_REUSEADDR deja que dos procesos escuchen en el mismo puerto: ahí no se usa
    allow_reuse_address = not WINDOWS
    daemon_threads = True


def main():
    servicio = Servicio()
    servicio.arrancar()
    try:
        servidor = Servidor(("127.0.0.1", PUERTO), crear_manejador(servicio))
    except OSError as e:
        sys.exit(f"akari: el puerto {PUERTO} está ocupado ({e}). ¿Ya hay otro akari corriendo?")
    print(f"akari {VERSION} en http://127.0.0.1:{PUERTO}", flush=True)
    servidor.serve_forever()
