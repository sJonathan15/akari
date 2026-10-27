"""Audio → Markdown: lo que Whisper inventa se quita y la transcripción sale en párrafos con hora."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from akari import audio  # noqa: E402


def seg(texto, inicio=0.0, fin=None, nsp=0.05, alp=-0.25, cr=1.4):
    return {"inicio": inicio, "fin": inicio + 3 if fin is None else fin, "texto": texto,
            "no_speech_prob": nsp, "avg_logprob": alp, "compression_ratio": cr}


def textos(segs):
    return [s["texto"] for s in segs]


class Limpieza(unittest.TestCase):
    def test_lo_bueno_queda(self):
        segs = [seg("Hola a todos, empezamos la reunión.", 0), seg("Primero el presupuesto.", 4)]
        self.assertEqual(textos(audio.limpiar(segs)), textos(segs))

    def test_silencio_y_poca_confianza(self):
        segs = [seg("Bien, sigamos.", 0), seg("Ah.", 4, nsp=0.85, alp=-0.9), seg("asdf qwer", 8, alp=-1.6),
                seg("la la la la la la la la", 12, cr=3.1), seg("Y eso es todo.", 16)]
        self.assertEqual(textos(audio.limpiar(segs)), ["Bien, sigamos.", "Y eso es todo."])

    def test_frases_de_subtitulos(self):
        segs = [seg("Hoy hablamos de plantas.", 0), seg("Subtítulos realizados por la comunidad de Amara.org", 5),
                seg("¡Suscríbete al canal!", 9), seg("Gracias por ver el video.", 12)]
        self.assertEqual(textos(audio.limpiar(segs)), ["Hoy hablamos de plantas."])

    def test_gracias_de_verdad_en_medio(self):
        # «gracias» dicho con claridad a mitad de la conversación es real
        segs = [seg("¿Me pasas la sal?", 0), seg("Gracias.", 3), seg("De nada, aquí tienes.", 6), seg("Rica comida.", 9)]
        self.assertEqual(len(audio.limpiar(segs)), 4)
        dudoso = [seg("¿Me pasas la sal?", 0), seg("Gracias.", 3, nsp=0.5), seg("De nada.", 6), seg("Ya.", 9)]
        self.assertNotIn("Gracias.", textos(audio.limpiar(dudoso)))

    def test_eco_del_prompt(self):
        prompt = audio.prompt_inicial()
        segs = [seg(prompt, 0), seg("Vamos con el primer punto.", 4)]
        self.assertEqual(textos(audio.limpiar(segs, prompt)), ["Vamos con el primer punto."])

    def test_bucles(self):
        segs = [seg("Entonces lo dejamos así.", 0)] + [seg("No sé, no sé.", 3 + i * 2) for i in range(6)]
        self.assertEqual(textos(audio.limpiar(segs)), ["Entonces lo dejamos así.", "No sé, no sé."])
        self.assertEqual(audio.sin_repeticiones("vale vale vale vale vale"), "vale")
        self.assertEqual(audio.sin_repeticiones("esto es lo que es"), "esto es lo que es")


class Markdown(unittest.TestCase):
    def test_parrafos_con_hora(self):
        segs = [seg("Uno.", 0, 2), seg("Dos.", 2.5, 4), seg("Tres, después de una pausa.", 9, 12), seg("Cuatro.", 75, 80)]
        md = audio.a_markdown("reunión.m4a", segs, "faster-whisper small")
        self.assertTrue(md.startswith("# reunión\n"))
        self.assertIn("**[00:00]** Uno. Dos.", md)
        self.assertIn("**[00:09]** Tres", md)
        self.assertIn("**[01:15]** Cuatro.", md)
        self.assertEqual(audio.reloj(3725), "1:02:05")

    def test_extensiones(self):
        self.assertTrue(audio.es_audio("file:///tmp/Mi%20clase.MP3"))
        self.assertTrue(audio.es_audio("video.mkv"))
        self.assertFalse(audio.es_audio("informe.pdf"))

    def test_multipart(self):
        cuerpo, tipo = audio._multipart({"model": "whisper-1"}, "a.ogg", b"\x00\x01")
        limite = tipo.split("boundary=")[1]
        self.assertIn(b'name="model"\r\n\r\nwhisper-1', cuerpo)
        self.assertTrue(cuerpo.endswith(f"--{limite}--\r\n".encode()))


if __name__ == "__main__":
    unittest.main()
