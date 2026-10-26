"""Cliente D-Bus en Python puro: empaquetado y, si hay dbus-daemon, una conversación real."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from akari import dbus_nativo as n


class Empaquetado(unittest.TestCase):
    def ida_y_vuelta(self, firma, valor):
        e = n.Escritor()
        e.escribir(firma, valor)
        return n.Lector(bytes(e.buf)).leer(firma)

    def test_firmas(self):
        self.assertEqual(n.tipos("sa{sv}i(bsii)av"), ["s", "a{sv}", "i", "(bsii)", "av"])
        with self.assertRaises(n.ErrorDBus):
            n.tipos("a{sv")

    def test_basicos(self):
        for firma, valor in (("y", 7), ("b", True), ("n", -3), ("q", 65000), ("i", -70000), ("u", 4000000000),
                             ("x", -2 ** 40), ("t", 2 ** 60), ("d", 1.5), ("s", "ratón ñ"), ("o", "/org/bluez/hci0"),
                             ("g", "a{sv}")):
            self.assertEqual(self.ida_y_vuelta(firma, valor), valor, firma)

    def test_compuestos(self):
        # lo que devuelve BlueZ en GetManagedObjects
        objetos = {"/org/bluez/hci0/dev_AA": {"org.bluez.Device1": {"Alias": "MX", "Connected": True, "RSSI": -52},
                                              "org.bluez.Battery1": {"Percentage": 82}}}
        self.assertEqual(self.ida_y_vuelta("a{oa{sa{sv}}}", objetos), objetos)
        # GSConnect: Describe -> (bgav) con una variante (bsii) dentro
        estado = (True, "", [("(bsii)", (True, "battery-good", 64, 3600))])
        self.assertEqual(self.ida_y_vuelta("(bgav)", estado), (True, "", [(True, "battery-good", 64, 3600)]))
        self.assertEqual(self.ida_y_vuelta("as", []), [])
        self.assertEqual(self.ida_y_vuelta("a{sv}", {}), {})
        self.assertEqual(self.ida_y_vuelta("at", [1, 2]), [1, 2])     # relleno a 8 tras la longitud

    def test_big_endian(self):
        import struct
        datos = struct.pack(">I", 3) + b"abc\0"
        self.assertEqual(n.Lector(datos, ">").leer("s"), "abc")

    def test_direcciones(self):
        viejo = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        try:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = "tcp:host=x;unix:abstract=/tmp/dbus-x,guid=1;unix:path=/run/user/1/bus"
            self.assertEqual(n.direcciones(n.SESION), ["\0/tmp/dbus-x", "/run/user/1/bus"])
        finally:
            if viejo is None:
                os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
            else:
                os.environ["DBUS_SESSION_BUS_ADDRESS"] = viejo


@unittest.skipUnless(shutil.which("dbus-daemon") and hasattr(os, "getuid"), "sin dbus-daemon")
class BusReal(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        socket = os.path.join(self.carpeta, "bus")
        self.daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--address=unix:path=" + socket],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if os.path.exists(socket):
                break
            time.sleep(0.05)
        self.viejo = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + socket
        n._conexiones.clear()

    def tearDown(self):
        for c in n._conexiones.values():
            if c:
                c.cerrar()
        n._conexiones.clear()
        self.daemon.terminate()
        self.daemon.wait()
        shutil.rmtree(self.carpeta, ignore_errors=True)
        if self.viejo is None:
            os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
        else:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = self.viejo

    def llamar(self, *args):
        return n.llamar(n.SESION, "org.freedesktop.DBus", "/org/freedesktop/DBus", *args)

    def test_metodos(self):
        nombres = self.llamar("org.freedesktop.DBus", "ListNames")[0]
        self.assertIn("org.freedesktop.DBus", nombres)
        self.assertEqual(self.llamar("org.freedesktop.DBus", "NameHasOwner", "s", ("no.existe",)), (False,))
        props = self.llamar("org.freedesktop.DBus.Properties", "GetAll", "s", ("org.freedesktop.DBus",))[0]
        self.assertIsInstance(props, dict)

    def test_servicio_ausente(self):
        # como BlueZ o KDE Connect cuando no están: None, sin excepciones
        self.assertIsNone(n.llamar(n.SESION, "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"))

    def test_reconecta(self):
        self.llamar("org.freedesktop.DBus", "ListNames")
        n._conexiones[n.SESION].sock.close()          # conexión cortada por fuera
        self.assertIsNotNone(self.llamar("org.freedesktop.DBus", "ListNames"))


if __name__ == "__main__":
    unittest.main()
