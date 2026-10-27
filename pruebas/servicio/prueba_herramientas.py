"""Herramientas: se elige una forma de instalar sin contraseña si la hay; sudo solo como comando."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from akari import herramientas as H  # noqa: E402


def con(gestores, npm_libre=True, en_repos=True):
    """Simula los gestores de paquetes que hay en el equipo."""
    return [mock.patch.object(H, "_gestor", side_effect=lambda g: f"/bin/{g}" if g in gestores else None),
            mock.patch.object(H, "_npm_sin_sudo", return_value=npm_libre),
            mock.patch.object(H, "_en_repos", return_value=en_repos)]


def metodo(ident, gestores, **kw):
    h = next(x for x in H.HERRAMIENTAS if x["id"] == ident)
    parches = con(gestores, **kw)
    for p in parches:
        p.start()
    try:
        return H.metodo(h)
    finally:
        for p in parches:
            p.stop()


class Metodos(unittest.TestCase):
    def test_sin_contrasena_primero(self):
        m = metodo("gitleaks", {"pacman", "go"})
        self.assertEqual(m["gestor"], "pacman")         # pacman antes que compilar con go…
        self.assertTrue(m["sudo"])
        self.assertEqual(m["texto"], "sudo pacman -S --needed gitleaks")
        self.assertEqual(metodo("gitleaks", {"pacman", "brew"})["gestor"], "brew")     # …pero brew no pide nada

    def test_uv_y_npm(self):
        self.assertEqual(metodo("semgrep", {"uv", "pipx"})["texto"], "uv tool install semgrep")
        m = metodo("repomix", {"npm"}, npm_libre=False)
        self.assertTrue(m["sudo"])
        self.assertEqual(m["texto"], "sudo npm install -g repomix")

    def test_sin_forma(self):
        self.assertIsNone(metodo("trivy", {"apt", "npm"}))           # trivy no está en los repos de apt
        self.assertIsNone(metodo("gitleaks", {"apt"}, en_repos=False))

    def test_windows(self):
        self.assertEqual(metodo("gitleaks", {"winget", "npm"})["orden"][:4], ["/bin/winget", "install", "-e", "--id"])

    def test_estado_y_mcp(self):
        mon = H.MonitorHerramientas(lambda: None)
        with mock.patch.object(H, "conectores_mcp", return_value=[{"nombre": "context7", "agente": "claude"}]), \
                mock.patch.object(H, "_ordenes_mcp", return_value=[("claude", ["claude"])]):
            mon.calcular()
        c7 = next(x for x in mon.estado["lista"] if x["id"] == "context7")
        self.assertTrue(c7["instalada"])
        self.assertEqual(mon.estado["total"], len(H.HERRAMIENTAS))
        self.assertTrue(all("orden" not in (x["metodo"] or {}) for x in mon.estado["lista"]))


if __name__ == "__main__":
    unittest.main()
