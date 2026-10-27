"""Modelos de IA: qué recomienda según el equipo y que la clave nunca salga en el estado."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from akari import modelos  # noqa: E402


def monitor(eq, instalados=()):
    with mock.patch.object(modelos, "equipo", return_value=eq):
        m = modelos.MonitorModelos(lambda: None)
    m.ollama = {"estado": "activo", "modelos": [{"nombre": n, "gb": 1, "vision": False} for n in instalados]}
    m.calcular()
    return m


def sugeridos(m):
    return {r["sugerido"]: r["id"] for r in m.estado["recomendados"] if r.get("sugerido")}


class Recomendaciones(unittest.TestCase):
    def test_tarjeta_de_6_gb(self):
        m = monitor({"ram_gb": 16, "gpu": {"nombre": "RTX", "vram_gb": 6}})
        self.assertEqual(sugeridos(m), {"texto": "qwen3:4b-instruct", "vision": "qwen3-vl:4b-instruct"})

    def test_tarjeta_de_12_gb(self):
        m = monitor({"ram_gb": 32, "gpu": {"nombre": "RTX", "vram_gb": 12}})
        self.assertEqual(sugeridos(m), {"texto": "qwen3:14b", "vision": "qwen3-vl:8b-instruct"})

    def test_sin_tarjeta(self):
        # en CPU no se recomienda el más grande que entra: tardaría demasiado
        m = monitor({"ram_gb": 16, "gpu": {}})
        self.assertEqual(sugeridos(m)["texto"], "qwen3:4b-instruct")
        self.assertEqual(modelos.cabe(9.3, m.equipo), "no")

    def test_poca_memoria(self):
        m = monitor({"ram_gb": 4, "gpu": {}})
        self.assertEqual(sugeridos(m), {"texto": "gemma3:1b"})


class Eleccion(unittest.TestCase):
    def test_sin_nada_pide_api_o_local(self):
        m = monitor({"ram_gb": 8, "gpu": {}})
        self.assertFalse(m.estado["listo"])
        self.assertTrue(m.estado["motivo"])

    def test_local(self):
        m = monitor({"ram_gb": 8, "gpu": {}}, ["qwen3:4b-instruct"])
        self.assertEqual(m.accion({"accion": "usar", "modo": "local", "modelo": "qwen3:4b-instruct", "tipo": "texto"}), (True, ""))
        self.assertEqual(m.elegido(), ("ollama", "qwen3:4b-instruct"))
        self.assertIsNone(m.elegido(vision=True)[0])     # no hay modelo que mire imágenes

    def test_la_clave_no_sale_en_el_estado(self):
        m = monitor({"ram_gb": 8, "gpu": {}})
        clave = "sk-ant-secreta-1234567890-abcd"
        with mock.patch.object(modelos, "listar_modelos", return_value=["claude-sonnet-x", "claude-haiku-x"]):
            ok, _ = m.accion({"accion": "clave", "proveedor": "anthropic", "clave": clave})
        self.assertTrue(ok)
        self.assertNotIn("secreta", json.dumps(m.estado))
        self.assertEqual(m.elegido(), ("anthropic", "claude-haiku-x"))      # el económico
        if os.name != "nt":
            self.assertEqual(os.stat(modelos.CLAVES).st_mode & 0o777, 0o600)

    def test_clave_rara(self):
        m = monitor({"ram_gb": 8, "gpu": {}})
        self.assertFalse(m.accion({"accion": "clave", "proveedor": "anthropic", "clave": "con espacios adentro"})[0])
        self.assertFalse(m.accion({"accion": "descargar", "modelo": "x; rm -rf /"})[0])


if __name__ == "__main__":
    unittest.main()
