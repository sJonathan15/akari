"""Asistente: atajos sin modelo, el bucle de herramientas con Ollama / OpenAI / Anthropic (servidores
falsos en este proceso) y los límites (cámara solo a pedido, archivos privados)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from akari import acciones, asistente  # noqa: E402


class Falso:
    """Servidor HTTP que responde una lista de respuestas en orden y guarda lo que recibió."""

    def __init__(self, respuestas):
        self.respuestas, self.recibido = list(respuestas), []
        falso = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                falso.recibido.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                cuerpo = json.dumps(falso.respuestas.pop(0)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

        self.servidor = HTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.servidor.server_port}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def cerrar(self):
        self.servidor.shutdown()


class Monitor:
    def __init__(self, camino, modelo="m"):
        self.camino, self.modelo = camino, modelo
        self.estado = {"listo": True, "vision_lista": True}

    def elegido(self, vision=False):
        return self.camino, self.modelo

    def claves(self):
        return {self.camino: "clave-de-prueba"}

    def ajustes(self):
        return {"modo": "local" if self.camino == "ollama" else "api"}


def nuevo(camino):
    a = asistente.Asistente(lambda: None, Monitor(camino))
    a.historial = []
    return a


AJ = {"notas": "", "donde": "fondo", "quien": "local"}


class Atajos(unittest.TestCase):
    def test_hora_sin_modelo(self):
        respuesta, herramienta = asistente.atajo("¿Qué hora es?")
        self.assertEqual(herramienta, "hora")
        self.assertRegex(respuesta, r"\d\d:\d\d")

    def test_musica_y_abrir(self):
        with mock.patch.object(acciones, "musica", return_value=(True, "ok")) as musica:
            self.assertEqual(asistente.atajo("siguiente canción")[1], "musica")
            musica.assert_called_with("siguiente")
            asistente.atajo("Oye akari, pausa")
            musica.assert_called_with("pausar")
        with mock.patch.object(acciones, "abrir_app", return_value=(True, "Abriendo Firefox.")) as abrir:
            self.assertEqual(asistente.atajo("abre firefox")[1], "abrir_app")
            abrir.assert_called_with("firefox")
        with mock.patch.object(acciones, "abrir", return_value=True) as abrir:
            self.assertEqual(asistente.atajo("abre github.com")[1], "abrir_enlace")
            abrir.assert_called_with("https://github.com")

    def test_lo_demas_va_al_modelo(self):
        with mock.patch.object(acciones, "abrir_app", return_value=(False, "no")):
            self.assertIsNone(asistente.atajo("abre la puerta del garaje"))
        self.assertIsNone(asistente.atajo("¿cuánto es 2 + 2?"))


class Bucle(unittest.TestCase):
    def test_ollama(self):
        f = Falso([{"message": {"role": "assistant", "content": "", "tool_calls": [
                       {"function": {"name": "abrir_app", "arguments": {"nombre": "Firefox"}}}]}},
                   {"message": {"role": "assistant", "content": "<think>…</think>Listo, abrí Firefox."}}])
        a = nuevo("ollama")
        with mock.patch.object(asistente, "OLLAMA", f.url), \
                mock.patch.object(acciones, "abrir_app", return_value=(True, "Abriendo Firefox.")) as abrir:
            respuesta, usadas = a._local("abre el navegador", AJ)
        f.cerrar()
        self.assertEqual(respuesta, "Listo, abrí Firefox.")
        self.assertEqual(usadas, ["abrir_app"])
        abrir.assert_called_with("Firefox")
        ruta, primero = f.recibido[0]
        self.assertEqual(ruta, "/api/chat")
        self.assertIn("abrir_app", [h["function"]["name"] for h in primero["tools"]])
        self.assertIn(":", primero["messages"][0]["content"])      # la hora va en el prompt del sistema
        segundo = f.recibido[1][1]["messages"]
        self.assertEqual(segundo[-1], {"role": "tool", "content": "Abriendo Firefox.", "tool_name": "abrir_app"})

    def test_openai(self):
        f = Falso([{"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                       {"id": "c1", "type": "function", "function": {"name": "musica", "arguments": "{\"accion\": \"que_suena\"}"}}]}}]},
                   {"choices": [{"message": {"role": "assistant", "content": "Suena Daft Punk."}}]}])
        a = nuevo("openai")
        with mock.patch.dict(asistente.PROVEEDORES["openai"], {"base": f.url}), \
                mock.patch.object(acciones, "musica", return_value=(True, "Daft Punk — One More Time")):
            respuesta, _ = a._local("¿qué suena?", AJ)
        f.cerrar()
        self.assertEqual(respuesta, "Suena Daft Punk.")
        mensajes = f.recibido[1][1]["messages"]
        self.assertEqual(mensajes[-2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(mensajes[-1], {"role": "tool", "tool_call_id": "c1", "content": "Daft Punk — One More Time"})

    def test_anthropic(self):
        f = Falso([{"content": [{"type": "tool_use", "id": "t1", "name": "listar_archivos", "input": {"ruta": "descargas"}}],
                    "stop_reason": "tool_use"},
                   {"content": [{"type": "text", "text": "Tienes 2 archivos."}]}])
        a = nuevo("anthropic")
        with mock.patch.dict(asistente.PROVEEDORES["anthropic"], {"base": f.url}), \
                mock.patch.object(acciones, "listar", return_value="a.pdf\nb.png"):
            respuesta, _ = a._local("¿qué hay en descargas?", AJ)
        f.cerrar()
        self.assertEqual(respuesta, "Tienes 2 archivos.")
        ruta, cuerpo = f.recibido[1]
        self.assertEqual(ruta, "/messages")
        self.assertEqual(cuerpo["messages"][-1]["content"][0], {"type": "tool_result", "tool_use_id": "t1", "content": "a.pdf\nb.png"})

    def test_mirar_pantalla_corta_el_turno(self):
        # un solo turno del modelo: lo que «ve» el modelo de visión es la respuesta, sin volver al chico
        f = Falso([{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "mirar_pantalla", "arguments": {"pregunta": "¿qué ves?"}}}]}}])
        a = nuevo("ollama")
        with mock.patch.object(asistente, "OLLAMA", f.url), mock.patch.object(asistente, "OCULTAR", 0), \
                mock.patch.object(acciones, "capturar_pantalla", return_value=b"\x89PNG\r\n\x1a\n..."), \
                mock.patch.object(asistente, "preguntar", return_value="Un editor con código Python.") as ver:
            respuesta, usadas = a._local("mira mi pantalla", AJ)
        f.cerrar()
        self.assertEqual(respuesta, "Un editor con código Python.")
        self.assertEqual(len(f.recibido), 1)
        self.assertIsNotNone(ver.call_args.kwargs["imagen"])
        self.assertFalse(a.ocultar)


class Limites(unittest.TestCase):
    def test_camara_solo_a_pedido(self):
        a = nuevo("ollama")
        with mock.patch.object(acciones, "foto_camara") as foto:
            salida, final = a.ejecutar("mirar_camara", {"pregunta": "¿cómo me veo?"}, "¿cómo me veo hoy?", AJ)
            foto.assert_not_called()
        self.assertFalse(final)

    def test_archivos_privados(self):
        casa = Path(tempfile.mkdtemp())
        (casa / ".ssh").mkdir()
        (casa / ".ssh" / "id_ed25519").write_text("secreto")
        (casa / "proyecto").mkdir()
        (casa / "proyecto" / ".env").write_text("API_KEY=secreto")
        (casa / "proyecto" / "notas.txt").write_text("hola")
        with mock.patch.object(acciones, "HOME", casa):
            self.assertNotIn("secreto", acciones.leer(str(casa / ".ssh" / "id_ed25519")))
            self.assertNotIn("secreto", acciones.leer(str(casa / "proyecto" / ".env")))
            self.assertEqual(acciones.leer(str(casa / "proyecto" / "notas.txt")), "hola")
            self.assertNotIn(".env", acciones.listar(str(casa / "proyecto")))
            self.assertNotIn("passwd", acciones.leer("/etc/passwd"))

    def test_notas(self):
        boveda = tempfile.mkdtemp()
        (Path(boveda) / "Recetas.md").write_text("# Recetas\n\nPan de masa madre: harina, agua y sal.\n", encoding="utf-8")
        ok, _ = acciones.anotar(boveda, "comprar harina")
        self.assertTrue(ok)
        self.assertEqual(len(list((Path(boveda) / "akari").glob("*.md"))), 1)
        self.assertIn("Recetas.md", acciones.buscar_notas(boveda, "masa madre"))
        self.assertEqual((Path(boveda) / "Recetas.md").read_text(encoding="utf-8").count("harina"), 1)   # la nota del usuario no se toca


if __name__ == "__main__":
    unittest.main()
