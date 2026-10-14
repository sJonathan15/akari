"""Datos de ejemplo (AKARI_DEMO=1): para probar las interfaces y hacer capturas sin
mostrar datos reales. Nada de esto sale del equipo ni toca archivos del usuario."""
import math
import time

from .comun import IDIOMA, t
from .dispositivos import MODELO_3D, nombre_tipo
from .habilidades import CATALOGO
from .comun import leer_json
from .ia import resumir


def _mensajes(ahora, modelo, escala, semilla):
    msgs = []
    for i in range(900):
        ts = ahora - i * 410 - (semilla * 37 % 200)
        onda = 1 + math.sin(i / 7 + semilla)
        msgs.append({"t": ts, "modelo": modelo, "sesion": f"s{i // 120}", "proyecto": ("notas", "web", "tesis")[i // 120 % 3],
                     "agente": False, "entrada": int(900 * escala * onda), "cache_escrita": int(2500 * escala),
                     "cache_leida": int(40000 * escala), "salida": int(1300 * escala * onda), "razonamiento": 0})
    return msgs


def _ventana(usado, resta, largo):
    ahora = time.time()
    return {"usado": usado, "libre": round(100 - usado, 1), "reinicia": ahora + resta, "inicio": ahora + resta - largo,
            "transcurrido": round((largo - resta) / largo * 100, 1), "agotado_en": None}


def _dispositivo(ident, tipo, nombre, conexion, bateria, detalles, cargando=False, conectado=True):
    return {"id": ident, "tipo": tipo, "tipo_nombre": nombre_tipo(tipo), "modelo3d": MODELO_3D.get(tipo),
            "nombre": nombre, "descripcion": "", "conectado": conectado, "conexion": conexion if conectado else None,
            "bateria": bateria if conectado else None, "cargando": cargando if conectado else None,
            "detalles": detalles, "acciones": [], "ayuda": None, "horas_restantes": None, "historial": []}


def estado():
    ahora = time.time()
    c5, c7 = _ventana(38.0, 2 * 3600 + 600, 5 * 3600), _ventana(22.0, 4 * 86400, 7 * 86400)
    claude = {**resumir(_mensajes(ahora, "Opus 5.5", 1.0, 1), c5, c7, ahora),
              "cuenta": {"nombre": "Alex", "plan": "Max"}, "linea_estado": True,
              "activador": {"programado": True, "hora": "07:00", "mantener": False, "hasta": "23:00", "modelo": "haiku",
                            "ocupado": False, "ultimo": None, "proximo": ahora + 9 * 3600}}
    x5, x7 = _ventana(12.0, 3 * 3600, 5 * 3600), _ventana(9.0, 5 * 86400, 7 * 86400)
    codex = {**resumir(_mensajes(ahora - 3600, "GPT-5.1 Codex", 0.6, 2), x5, x7, ahora),
             "cuenta": {"nombre": "Alex", "plan": "Plus"}}

    disp = [
        _dispositivo("demo-mouse", "raton", "MX Master 3S", "Bluetooth", 82,
                     [[t("Señal Bluetooth", "Bluetooth signal"), "-52 dBm"]]),
        _dispositivo("demo-kbd", "teclado", "Keychron K2", t("Cable / receptor USB", "USB cable / receiver"), None,
                     [[t("Bloq Mayús", "Caps Lock"), t("desactivado", "off")], [t("Puerto", "Port"), "USB 2.0"]]),
        _dispositivo("demo-audio", "audifonos", "WH-1000XM5", "Bluetooth", 64,
                     [[t("Volumen", "Volume"), "45 %"], [t("Códec", "Codec"), "LDAC"], [t("Modo", "Mode"), t("Música (A2DP)", "Music (A2DP)")]]),
        _dispositivo("demo-phone", "celular", "Pixel 9", "KDE Connect (Wi-Fi)", 47,
                     [[t("Red móvil", "Mobile network"), "5G · " + t("buena", "good")]], cargando=True),
    ]
    disp[0]["horas_restantes"] = 31.5

    cat = leer_json(CATALOGO, {"recomendadas": [], "mas": []})
    puestas = {"pdf": 7, "docx": 3, "archify": 2}

    def tarjeta(e):
        en = ["claude"] if e["id"] in puestas else []
        return {"id": e["id"], "icono": e["icono"], "nombre": e["nombre"][IDIOMA], "detalle": e["detalle"][IDIOMA],
                "licencia": e.get("licencia"), "repo": e["fuente"]["repo"], "agentes": ["claude", "codex"],
                "instalada_en": en, "falta_en": [] if en else ["claude", "codex"], "usos_7d": puestas.get(e["id"], 0), "tarea": None}

    instaladas = [{"id": n, "nombre": n, "descripcion": "", "agentes": ["claude"], "origen": "akari", "usos_7d": u}
                  for n, u in puestas.items()]
    return {
        "ia": {"claude": claude, "codex": codex, "principal": "claude", "avisos": []},
        "dispositivos": {"dispositivos": disp, "equipo": {"bateria": 76, "estado": "descargando", "vacia_en": None, "llena_en": None},
                         "bluetooth_encendido": True, "app_celular": "KDE Connect", "mas_baja": "demo-phone",
                         "actividad": [], "umbrales": [20, 10, 5]},
        "habilidades": {"agentes": {"claude": True, "codex": True}, "instaladas": instaladas,
                        "recomendadas": [tarjeta(e) for e in cat["recomendadas"]], "mas": [tarjeta(e) for e in cat["mas"]],
                        "mcp": [{"nombre": "context7", "agente": "claude"}, {"nombre": "playwright", "agente": "codex"}],
                        "usos_7d": 12, "total": 3, "recomendadas_instaladas": 3},
    }
