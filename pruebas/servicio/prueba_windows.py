"""Lecturas de Windows: conversión del JSON de PnP (en cualquier sistema) y, en Windows, las de verdad."""
import sys
import unittest

from akari import windows
from akari.dispositivos import USB_CELULARES, armar, pista

MUESTRA = {
    "bt": [
        {"id": r"BTHENUM\DEV_AABBCCDDEEFF\7&1", "mac": "AABBCCDDEEFF", "nombre": "WH-1000XM5", "estado": "OK",
         "conectado": True, "bateria": 64, "clase": 0x240404},              # audio/vídeo: audífonos
        {"id": r"BTHLE\DEV_112233445566\7&2", "mac": "112233445566", "nombre": "MX Master 3S", "estado": "OK",
         "conectado": False, "bateria": None, "clase": 0x2580},              # periférico apuntador
        {"id": r"BTHENUM\DEV_112233445566\7&3", "mac": "112233445566", "nombre": "MX Master 3S", "estado": "OK",
         "conectado": True, "bateria": 80, "clase": None},                    # el mismo, por BR/EDR
        {"id": r"BTHENUM\DEV_0A0B0C0D0E0F\7&4", "mac": "0A0B0C0D0E0F", "nombre": "Pixel 9", "estado": "OK",
         "conectado": None, "bateria": None, "clase": 0x5a020c},             # teléfono, Windows viejo
    ],
    "usb": [
        {"vid": "046D", "pid": "C52B", "clase": "Mouse", "nombre": "USB Receiver", "generico": "HID-compliant mouse"},
        {"vid": "046D", "pid": "C52B", "clase": "Keyboard", "nombre": None, "generico": "HID Keyboard Device"},
        {"vid": "3434", "pid": "0281", "clase": "Keyboard", "nombre": "Keychron K2", "generico": "HID Keyboard Device"},
        {"vid": "046D", "pid": "085E", "clase": "MEDIA", "nombre": "BRIO", "generico": "USB Audio"},
        {"vid": "046D", "pid": "085E", "clase": "Camera", "nombre": "BRIO", "generico": "Logitech BRIO"},
        {"vid": "18D1", "pid": "4EE7", "clase": "WPD", "nombre": "Pixel 9", "generico": "Pixel 9"},
    ],
}


class Conversion(unittest.TestCase):
    def test_clase_bluetooth(self):
        self.assertEqual(windows.tipo_por_clase(0x2580), "raton")
        self.assertEqual(windows.tipo_por_clase(0x2540), "teclado")
        self.assertEqual(windows.tipo_por_clase(0x2508), "mando")
        self.assertEqual(windows.tipo_por_clase(0x240404), "audifonos")
        self.assertEqual(windows.tipo_por_clase(0x5a020c), "celular")
        self.assertIsNone(windows.tipo_por_clase(None))

    def test_convertir(self):
        bt, usb = windows.convertir(MUESTRA, pista, USB_CELULARES)
        self.assertEqual(bt["AA:BB:CC:DD:EE:FF"]["tipo"], "audifonos")
        mx = bt["11:22:33:44:55:66"]          # BTHLE + BTHENUM se juntan en uno
        self.assertEqual((mx["tipo"], mx["conectado"], mx["bateria"]), ("raton", True, 80))
        self.assertFalse(bt["0A:0B:0C:0D:0E:0F"]["conectado"])
        tipos = {u["id"]: u["tipo"] for u in usb}
        self.assertEqual(tipos, {"usb-046d-c52b": "raton", "usb-3434-0281": "teclado", "usb-18d1-4ee7": "celular"})

    def test_armar(self):
        # lo convertido entra tal cual al armado común (el de Linux)
        bt, usb = windows.convertir(MUESTRA, pista, USB_CELULARES)
        salida = armar((bt, [], usb, {}, []))
        self.assertEqual(salida["bt-AA:BB:CC:DD:EE:FF"]["bateria"], 64)
        self.assertEqual(salida["usb-3434-0281"]["nombre"], "Keychron K2")
        self.assertTrue(all(d["conectado"] for k, d in salida.items() if k.startswith("usb-")))


@unittest.skipUnless(sys.platform == "win32", "solo en Windows")
class WindowsDeVerdad(unittest.TestCase):
    def test_pnp(self):
        salida = windows.powershell(windows.SCRIPT, timeout=90)
        self.assertIsNotNone(salida, "el script de PowerShell falló")
        import json
        datos = json.loads(salida.strip().splitlines()[-1])
        self.assertIn("bt", datos)
        self.assertIn("usb", datos)
        lector = windows.LectorWindows(pista, USB_CELULARES)
        bt, usb = lector.leer(esperar=True)
        self.assertIsInstance(bt, dict)
        self.assertIsInstance(usb, list)

    def test_equipo(self):
        b = windows.bateria_equipo()
        self.assertTrue(b is None or 0 <= b["bateria"] <= 100)
        self.assertEqual(set(windows.bloqueos()), {"capslock", "numlock"})

    def test_dispositivos(self):
        from akari.dispositivos import MonitorDispositivos
        m = MonitorDispositivos(lambda: None)
        m.windows.leer(esperar=True)
        m.leer()
        self.assertIn("dispositivos", m.estado)


if __name__ == "__main__":
    unittest.main()
