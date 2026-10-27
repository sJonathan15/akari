"""Lista de burbujas a partir de las cápsulas QML (akari/burbujas.py)."""
import unittest

from akari import burbujas

QML = """Capsula {
    id: capsula
    nombre: "voz"
    lado: "izquierda"
    hueco: 300          // al lado de dispositivos
    anchoCerrado: 120
    anchoAbierto: width * 2
    pideTeclado: true
}"""


class Burbujas(unittest.TestCase):
    def test_leer_qml(self):
        b = burbujas.leer_qml(QML)
        self.assertEqual((b["nombre"], b["lado"], b["hueco"], b["anchoCerrado"], b["teclado"]), ("voz", "izquierda", 300, 120, True))
        self.assertEqual(b["anchoAbierto"], burbujas.FABRICA["anchoAbierto"])     # una expresión: valor de fábrica
        self.assertIsNone(burbujas.leer_qml(QML.replace("Capsula {", "// akari: sin-burbuja\nCapsula {")))
        self.assertIsNone(burbujas.leer_qml("Item { }"))

    def test_las_del_repositorio(self):
        nombres = [b["nombre"] for b in burbujas.lista("es")]
        self.assertTrue({"ia", "dispositivos", "habilidades"} <= set(nombres))
        self.assertTrue(all(b["titulo"] and b["icono"] for b in burbujas.lista("en")))


if __name__ == "__main__":
    unittest.main()
