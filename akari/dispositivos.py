"""Periféricos detectados automáticamente: ratón, teclado, audífonos, celular, mandos…

Fuentes (todas opcionales; lo que no exista se salta):
  * BlueZ: dispositivos Bluetooth vinculados, su tipo (Icon) y batería;
  * UPower: batería de ratones/teclados inalámbricos (p. ej. Logitech) y de la laptop;
  * /sys: periféricos USB externos y su tipo según las interfaces HID de arranque;
  * PipeWire/PulseAudio (pactl): volumen, códec y perfil de audífonos Bluetooth;
  * KDE Connect (KDE) o GSConnect (GNOME): batería, carga y señal del celular;
  * en Windows: PnP (Bluetooth y USB), la batería del equipo y Bloq Mayús (ver windows.py).

Lo que el usuario corrige (nombre, tipo, ocultar) va a ~/.config/akari/dispositivos.json.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from . import dbus, windows
from .comun import CONFIG, DATOS, WINDOWS, escribir_json, leer_json, notificar, t

PREFERENCIAS = CONFIG / "dispositivos.json"
CONOCIDOS = DATOS / "dispositivos-conocidos.json"
HISTORIAL = DATOS / "baterias.json"
DIAS_RECORDAR = 14
MUESTRA_HISTORIAL = 300
HORAS_HISTORIAL = 48

TIPOS = ("raton", "teclado", "audifonos", "celular", "mando", "otro")
# modelo 3D de cada tipo (carpeta modelos/)
MODELO_3D = {"raton": "mouse", "teclado": "keyboard", "audifonos": "headphones", "celular": "phone"}
ICONO_BT = {
    "input-mouse": "raton", "input-keyboard": "teclado", "input-gaming": "mando",
    "audio-headset": "audifonos", "audio-headphones": "audifonos", "audio-card": "audifonos",
    "phone": "celular",
}
# Tipos de UPower (org.freedesktop.UPower.Device.Type)
TIPO_UPOWER = {5: "raton", 6: "teclado", 8: "celular", 12: "mando", 17: "audifonos", 19: "audifonos"}
ESTADOS_UPOWER = {1: "cargando", 2: "descargando", 4: "llena"}
# fabricantes USB de celulares (para reconocer uno conectado por cable)
USB_CELULARES = {"18d1", "2717", "04e8", "22b8", "12d1", "2a70", "0bb4", "1004", "0fce", "2ae5", "19d2",
                 "1bbb", "0e8d", "2d95", "22d9", "29a9", "05c6"}
PISTAS = {"raton": ("mouse", "ratón", "raton", "trackball"), "teclado": ("keyboard", "teclado", "kbd"),
          "audifonos": ("headset", "headphone", "earbud", "buds", "auricular", "audífono", "airpods"),
          "mando": ("controller", "gamepad", "joystick", "xbox", "dualsense", "dualshock")}
VELOCIDADES = {"1.5": "USB 1.1", "12": "USB 1.1", "480": "USB 2.0", "5000": "USB 3.0", "10000": "USB 3.1", "20000": "USB 3.2"}


def nombre_tipo(tipo):
    return {
        "raton": t("Ratón", "Mouse"), "teclado": t("Teclado", "Keyboard"), "audifonos": t("Audífonos", "Headphones"),
        "celular": t("Celular", "Phone"), "mando": t("Mando", "Controller"), "otro": t("Dispositivo", "Device"),
    }[tipo]


def leer(ruta, defecto=None):
    try:
        return Path(ruta).read_text().strip()
    except OSError:
        return defecto


def mac_normal(mac):
    return (mac or "").upper().replace("_", ":")


def pista(texto):
    texto = (texto or "").lower()
    for tipo, palabras in PISTAS.items():
        if any(p in texto for p in palabras):
            return tipo
    return None


# ---------------------------------------------------------------- lecturas

def leer_bluetooth():
    objetos = dbus.objetos(dbus.SISTEMA, "org.bluez")
    if objetos is None:
        return {}, None
    dispositivos, encendido = {}, False
    for ruta, interfaces in objetos.items():
        if "org.bluez.Adapter1" in interfaces:
            encendido = encendido or bool(interfaces["org.bluez.Adapter1"].get("Powered"))
        d = interfaces.get("org.bluez.Device1")
        if not d or not (d.get("Paired") or d.get("Connected")):
            continue
        bat = interfaces.get("org.bluez.Battery1") or {}
        mac = mac_normal(d.get("Address"))
        nombre = d.get("Alias") or d.get("Name") or mac
        dispositivos[mac] = {
            "ruta": ruta, "nombre": nombre,
            "tipo": ICONO_BT.get(d.get("Icon") or "") or pista(nombre),
            "conectado": bool(d.get("Connected")),
            "bateria": bat.get("Percentage"), "rssi": d.get("RSSI"),
        }
    return dispositivos, encendido


def leer_upower():
    r = dbus.llamar(dbus.SISTEMA, "org.freedesktop.UPower", "/org/freedesktop/UPower",
                    "org.freedesktop.UPower", "EnumerateDevices")
    perifericos, equipo = [], None
    for ruta in (r[0] if r else []):
        p = dbus.propiedades(dbus.SISTEMA, "org.freedesktop.UPower", ruta, "org.freedesktop.UPower.Device")
        if not p:
            continue
        if p.get("Type") == 2 and p.get("PowerSupply"):        # batería de la laptop
            equipo = {"bateria": round(p.get("Percentage", 0)),
                      "estado": ESTADOS_UPOWER.get(p.get("State"), ""),
                      "vacia_en": p.get("TimeToEmpty") or None, "llena_en": p.get("TimeToFull") or None}
            continue
        tipo = TIPO_UPOWER.get(p.get("Type"))
        if not tipo or not p.get("IsPresent", True) or p.get("Percentage") is None:
            continue
        nativa = p.get("NativePath") or ruta
        mac = mac_normal(p.get("Serial")) if ":" in (p.get("Serial") or "") else ""
        if not mac and "dev_" in nativa:          # /org/bluez/hci0/dev_AA_BB_…
            mac = mac_normal(nativa.split("dev_")[-1][:17])
        perifericos.append({
            "id": "upower-" + Path(nativa).name, "mac": mac, "tipo": tipo,
            "nombre": p.get("Model") or nombre_tipo(tipo),
            "bateria": round(p["Percentage"]), "cargando": p.get("State") == 1,
        })
    return perifericos, equipo


def leer_usb():
    """Periféricos USB externos (no los internos de la laptop) agrupados por aparato."""
    lista = []
    base = Path("/sys/bus/usb/devices")
    if not base.exists():
        return lista
    for d in base.iterdir():
        vid = leer(d / "idVendor")
        if not vid or ":" in d.name or leer(d / "removable") == "fixed":
            continue
        clases, protocolos = set(), set()
        for i in d.glob(f"{d.name}:*"):
            clase = leer(i / "bInterfaceClass")
            clases.add(clase)
            if clase == "03" and leer(i / "bInterfaceSubClass") == "01":
                protocolos.add(leer(i / "bInterfaceProtocol"))
        producto = leer(d / "product", "") or ""
        fabricante = leer(d / "manufacturer", "") or ""
        tipo = None
        if vid.lower() in USB_CELULARES or ("06" in clases and "03" not in clases):
            tipo = "celular"
        elif "03" in clases:
            # pistas del nombre primero; luego las interfaces de arranque:
            # 2 = ratón (los teclados casi nunca la tienen), 1 = teclado
            tipo = pista(producto) or ("raton" if "02" in protocolos else "teclado" if "01" in protocolos else pista(fabricante))
        elif "01" in clases and "0e" not in clases:     # audio USB (sin cámara)
            tipo = "audifonos"
        if not tipo:
            continue
        lista.append({
            "id": f"usb-{vid.lower()}-{(leer(d / 'idProduct') or '').lower()}",
            "sysfs": str(d.resolve()), "tipo": tipo,
            "nombre": producto or fabricante or nombre_tipo(tipo), "fabricante": fabricante,
            "velocidad": leer(d / "speed"),
        })
    return lista


def leer_leds(sysfs):
    """Bloq Mayús / Bloq Num de un teclado USB (LEDs del kernel bajo su carpeta en /sys)."""
    estado = {}
    for led in Path("/sys/class/leds").glob("input*::*"):
        try:
            if not str(led.resolve()).startswith(sysfs + "/"):
                continue
        except OSError:
            continue
        estado[led.name.split("::", 1)[1]] = leer(led / "brightness", "0") != "0"
    return estado


def leer_audio():
    try:
        r = subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True, timeout=2)
        salidas = json.loads(r.stdout or "[]")
        predeterminada = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    por_mac = {}
    for s in salidas:
        p = s.get("properties", {})
        mac = mac_normal(p.get("api.bluez5.address"))
        if not mac:
            continue
        canales = []
        for v in (s.get("volume") or {}).values():
            try:
                canales.append(int(str(v.get("value_percent", "0%")).rstrip("%")))
            except ValueError:
                pass
        por_mac[mac] = {
            "volumen": round(sum(canales) / len(canales)) if canales else None,
            "silencio": bool(s.get("mute")),
            "codec": (p.get("api.bluez5.codec") or "").upper() or None,
            "perfil": p.get("api.bluez5.profile"),
            "predeterminada": s.get("name") == predeterminada,
        }
    return por_mac


def leer_kdeconnect():
    base = "/modules/kdeconnect"
    r = dbus.llamar(dbus.SESION, "org.kde.kdeconnect", base, "org.kde.kdeconnect.daemon", "devices", "bb", (False, False))
    if r is None:
        return None
    equipos = []
    for ident in r[0]:
        ruta = f"{base}/devices/{ident}"
        p = dbus.propiedades(dbus.SESION, "org.kde.kdeconnect", ruta, "org.kde.kdeconnect.device")
        bat = dbus.propiedades(dbus.SESION, "org.kde.kdeconnect", f"{ruta}/battery", "org.kde.kdeconnect.device.battery")
        red = dbus.propiedades(dbus.SESION, "org.kde.kdeconnect", f"{ruta}/connectivity_report",
                               "org.kde.kdeconnect.device.connectivity_report")
        if p.get("type") not in (None, "smartphone", "phone", "tablet"):
            continue
        carga = bat.get("charge")
        equipos.append({
            "id": "kdc-" + ident, "ruta": ruta, "app": "KDE Connect",
            "nombre": p.get("name") or ident,
            "alcanzable": bool(p.get("isReachable")),
            "vinculado": bool(p.get("isPaired", p.get("pairState") == 3)),
            "bateria": carga if isinstance(carga, int) and carga >= 0 else None,
            "cargando": bat.get("isCharging"),
            "red": red.get("cellularNetworkType"), "senal": red.get("cellularNetworkStrength"),
        })
    return equipos


def leer_gsconnect():
    servicio = "org.gnome.Shell.Extensions.GSConnect"
    objetos = dbus.objetos(dbus.SESION, servicio, "/org/gnome/Shell/Extensions/GSConnect")
    if objetos is None:
        return None
    equipos = []
    for ruta, interfaces in objetos.items():
        p = interfaces.get("org.gnome.Shell.Extensions.GSConnect.Device")
        if not p or p.get("Type") not in (None, "phone", "tablet"):
            continue
        bateria = cargando = None
        r = dbus.llamar(dbus.SESION, servicio, ruta, "org.gtk.Actions", "Describe", "s", ("battery",))
        try:
            estado = r[0][2][0]          # (b g av) → estado (bsii): cargando, icono, nivel, tiempo
            cargando, bateria = bool(estado[0]), (estado[2] if estado[2] >= 0 else None)
        except (TypeError, IndexError, KeyError):
            pass
        equipos.append({
            "id": "gsc-" + Path(ruta).name, "ruta": ruta, "app": "GSConnect",
            "nombre": p.get("Name") or "Phone", "alcanzable": bool(p.get("Connected")),
            "vinculado": bool(p.get("Paired")), "bateria": bateria, "cargando": cargando,
            "red": None, "senal": None,
        })
    return equipos


# ------------------------------------------------------------- armado

SENAL = {0: t("sin señal", "no signal"), 1: t("débil", "weak"), 2: t("regular", "fair"),
         3: t("buena", "good"), 4: t("excelente", "excellent")}
PERFILES = {"a2dp-sink": t("Música (A2DP)", "Music (A2DP)"),
            "headset-head-unit": t("Llamadas (HFP)", "Calls (HFP)"),
            "handsfree_head_unit": t("Llamadas (HFP)", "Calls (HFP)")}


def nuevo(ident, tipo, nombre, descripcion=""):
    return {"id": ident, "tipo": tipo, "nombre": nombre, "descripcion": descripcion,
            "conectado": False, "conexion": None, "bateria": None, "cargando": None,
            "detalles": [], "acciones": [], "ayuda": None, "_rutas": {}}


def armar(lecturas):
    bt, upower, usb, audio, telefonos = lecturas
    salida = {}

    # Bluetooth
    for mac, b in bt.items():
        tipo = b["tipo"] or "otro"
        if tipo == "otro" and not b["conectado"]:
            continue
        d = nuevo("bt-" + mac, tipo, b["nombre"], "Bluetooth")
        d["_mac"] = mac
        if b["conectado"]:
            d["conectado"], d["conexion"] = True, "Bluetooth"
            d["bateria"] = b["bateria"]
            if b["rssi"] is not None:
                d["detalles"].append([t("Señal Bluetooth", "Bluetooth signal"), f"{b['rssi']} dBm"])
        if WINDOWS:     # Windows no deja conectar/desconectar desde fuera: se abren sus ajustes
            d["acciones"].append({"id": "ajustes_bt", "etiqueta": t("Ajustes de Bluetooth", "Bluetooth settings")})
        else:
            d["acciones"].append({"id": "desconectar" if b["conectado"] else "conectar",
                                  "etiqueta": t("Desconectar", "Disconnect") if b["conectado"] else t("Conectar", "Connect")})
        d["_rutas"]["bluez"] = b["ruta"]
        a = audio.get(mac)
        if a and b["conectado"]:
            if a["volumen"] is not None:
                d["detalles"].insert(0, [t("Volumen", "Volume"), t("silenciado", "muted") if a["silencio"] else f"{a['volumen']} %"])
                d["volumen"] = a["volumen"]
            if a["codec"]:
                d["detalles"].append([t("Códec", "Codec"), a["codec"]])
            if a["perfil"]:
                d["detalles"].append([t("Modo", "Mode"), PERFILES.get(a["perfil"], a["perfil"])])
            d["detalles"].append([t("Salida de audio", "Audio output"),
                                  t("Predeterminada", "Default") if a["predeterminada"] else t("No es la predeterminada", "Not the default")])
        salida[d["id"]] = d

    # USB
    for u in usb:
        d = nuevo(u["id"], u["tipo"], u["nombre"] or nombre_tipo(u["tipo"]), u["fabricante"])
        d["conectado"], d["conexion"] = True, t("Cable / receptor USB", "USB cable / receiver")
        if u["velocidad"]:
            d["detalles"].append([t("Puerto", "Port"), VELOCIDADES.get(u["velocidad"], f"{u['velocidad']} Mb/s")])
        if u["tipo"] == "teclado":
            leds = windows.bloqueos() if WINDOWS else leer_leds(u["sysfs"])
            if leds:
                d["detalles"].insert(0, [t("Bloq Mayús", "Caps Lock"), t("activado", "on") if leds.get("capslock") else t("desactivado", "off")])
                d["detalles"].insert(1, [t("Bloq Num", "Num Lock"), t("activado", "on") if leds.get("numlock") else t("desactivado", "off")])
                d["bloq_mayus"] = bool(leds.get("capslock"))
        salida[d["id"]] = d

    # UPower: batería de lo ya visto por Bluetooth o de inalámbricos con receptor propio
    for p in upower:
        destino = next((d for d in salida.values() if p["mac"] and d.get("_mac") == p["mac"]), None)
        if destino is None:
            destino = next((d for d in salida.values() if d["id"].startswith("usb-") and d["tipo"] == p["tipo"]
                            and d["bateria"] is None), None)
            if destino:
                destino["detalles"].append([t("Inalámbrico", "Wireless"), p["nombre"]])
        if destino is None:
            destino = nuevo(p["id"], p["tipo"], p["nombre"])
            destino["conectado"], destino["conexion"] = True, t("Inalámbrico", "Wireless")
            salida[destino["id"]] = destino
        if destino["bateria"] is None:
            destino["bateria"], destino["cargando"] = p["bateria"], p["cargando"]

    # Celular por KDE Connect / GSConnect (el más reciente alcanzable gana sobre el Bluetooth)
    for tel in telefonos:
        if not tel["vinculado"]:
            continue
        existente = next((d for d in salida.values() if d["tipo"] == "celular"
                          and d["nombre"].lower() == tel["nombre"].lower()), None)
        d = existente or nuevo(tel["id"], "celular", tel["nombre"])
        d["detalles"].append([t("Vinculado en", "Paired in"), tel["app"]])
        if tel["alcanzable"]:
            d["conectado"] = True
            d["conexion"] = d["conexion"] or f"{tel['app']} (Wi-Fi)"
            d["bateria"], d["cargando"] = tel["bateria"], tel["cargando"]
            if tel["red"]:
                d["detalles"].insert(0, [t("Red móvil", "Mobile network"), f"{tel['red']} · {SENAL.get(tel['senal'], '—')}"])
                d["senal"] = tel["senal"]
            d["acciones"].insert(0, {"id": "sonar", "etiqueta": t("Hacer sonar", "Ring")})
            d["_rutas"]["telefono"] = (tel["app"], tel["ruta"])
        elif not d["conectado"]:
            d["ayuda"] = t("Vinculado pero fuera de alcance: revisa que esté en la misma Wi-Fi.",
                           "Paired but unreachable: make sure it is on the same Wi-Fi.")
        salida[d["id"]] = d

    for d in salida.values():
        if d["cargando"] is None and d["bateria"] is not None:
            d["cargando"] = False
        if not d["conectado"] and not d["ayuda"]:
            d["ayuda"] = {
                "audifonos": t("Enciéndelos: se conectan solos porque ya están vinculados.",
                               "Turn them on: they reconnect on their own since they are paired."),
                "celular": t("Vincúlalo por Bluetooth o conéctalo por USB para ver su estado.",
                             "Pair it over Bluetooth or plug it in over USB to see its status.") if WINDOWS else
                t("Instala KDE Connect (o GSConnect en GNOME) en el equipo y en el celular para ver su batería.",
                  "Install KDE Connect (or GSConnect on GNOME) on the computer and the phone to see its battery."),
            }.get(d["tipo"], t("Conéctalo o enciéndelo para ver su estado.", "Connect or turn it on to see its status."))
    return salida


# ---------------------------------------------------- historial y estimación

class Historial:
    def __init__(self):
        self.datos = leer_json(HISTORIAL)
        self.ultima = 0

    def anotar(self, dispositivos, ahora):
        if ahora - self.ultima < MUESTRA_HISTORIAL:
            return
        self.ultima = ahora
        corte = ahora - HORAS_HISTORIAL * 3600
        for d in dispositivos:
            serie = [m for m in self.datos.get(d["id"], []) if m[0] >= corte]
            if d["bateria"] is not None:
                serie.append([round(ahora), d["bateria"], bool(d["cargando"])])
            self.datos[d["id"]] = serie
        self.datos = {k: v for k, v in self.datos.items() if v}
        escribir_json(HISTORIAL, self.datos)

    def serie(self, ident):
        return self.datos.get(ident, [])

    def horas_restantes(self, d, ahora):
        """Pendiente de las últimas 3 h de descarga (mínimos cuadrados)."""
        if d["bateria"] is None or d["cargando"]:
            return None
        puntos = [(ts, b) for ts, b, c in self.serie(d["id"]) if ts >= ahora - 3 * 3600 and not c]
        puntos.append((ahora, d["bateria"]))
        if len(puntos) < 4 or puntos[-1][0] - puntos[0][0] < 3600:
            return None
        n = len(puntos)
        mt = sum(x for x, _ in puntos) / n
        mb = sum(b for _, b in puntos) / n
        den = sum((x - mt) ** 2 for x, _ in puntos)
        if not den:
            return None
        pendiente = sum((x - mt) * (b - mb) for x, b in puntos) / den * 3600
        if pendiente > -0.3:
            return None
        return round(d["bateria"] / -pendiente, 1)


# ----------------------------------------------------------------- monitor

ORDEN_TIPOS = {tipo: i for i, tipo in enumerate(TIPOS)}


class MonitorDispositivos:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.historial = Historial()
        self.conocidos = leer_json(CONOCIDOS)
        self.estado = {}
        self.rutas = {}
        self.anterior, self.pendiente, self.avisados = {}, {}, {}
        self.cargado_avisado = set()
        self.actividad = []
        self.bloqueo = threading.Lock()
        self.windows = windows.LectorWindows(pista, USB_CELULARES) if WINDOWS else None

    def preferencias(self):
        p = leer_json(PREFERENCIAS)
        umbrales = p.get("umbrales_bateria") or [20, 10, 5]
        return {"ocultar": set(p.get("ocultar") or []), "nombres": p.get("nombres") or {},
                "tipos": p.get("tipos") or {}, "umbrales": sorted(umbrales, reverse=True)}

    def evento(self, texto, tipo="info", titulo=None, urgente=False):
        self.actividad.insert(0, {"t": time.time(), "texto": texto, "tipo": tipo})
        del self.actividad[40:]
        notificar(titulo or texto, "" if titulo is None else texto, urgente)

    def revisar_alertas(self, dispositivos, umbrales):
        for d in dispositivos:
            # conexión / desconexión, confirmada en dos lecturas para no avisar por un parpadeo
            visto, veces = self.pendiente.get(d["id"], (d["conectado"], 0))
            veces = veces + 1 if visto == d["conectado"] else 1
            self.pendiente[d["id"]] = (d["conectado"], veces)
            if veces >= 2 and self.anterior.get(d["id"]) != d["conectado"]:
                if d["id"] in self.anterior:
                    if d["conectado"]:
                        self.evento(t(f"{d['nombre']} se conectó.", f"{d['nombre']} connected."), "conexion")
                    else:
                        self.evento(t(f"{d['nombre']} se desconectó.", f"{d['nombre']} disconnected."), "desconexion")
                self.anterior[d["id"]] = d["conectado"]
            b = d["bateria"]
            if b is None or not d["conectado"]:
                continue
            avisados = self.avisados.setdefault(d["id"], set())
            if d["cargando"] or b > umbrales[0] + 5:
                avisados.clear()
            else:
                for umbral in umbrales:
                    if b <= umbral and umbral not in avisados:
                        avisados.update(u for u in umbrales if u >= umbral)
                        self.evento(t(f"Le queda {b} %. Conviene cargarlo pronto.", f"{b}% left. Charge it soon.")
                                    if umbral > umbrales[-1] else
                                    t(f"Le queda {b} %. Se apagará en breve.", f"{b}% left. It will turn off soon."),
                                    "bateria", titulo=t(f"{d['nombre']}: batería baja", f"{d['nombre']}: low battery"),
                                    urgente=umbral <= 10)
                        break
            if d["cargando"] and b >= 100 and d["id"] not in self.cargado_avisado:
                self.cargado_avisado.add(d["id"])
                self.evento(t("Ya está al 100 %.", "It is fully charged."), "carga",
                            titulo=t(f"{d['nombre']} cargado", f"{d['nombre']} charged"))
            if not d["cargando"]:
                self.cargado_avisado.discard(d["id"])

    def leer(self):
        with self.bloqueo:
            self._leer()

    def _leer(self):
        prefs = self.preferencias()
        if self.windows:
            bt, usb = self.windows.leer()
            encendido, upower, equipo, kdc, gsc = None, [], windows.bateria_equipo(), None, None
            lecturas = (bt, upower, usb, {}, [])
        else:
            bt, encendido = leer_bluetooth()
            upower, equipo = leer_upower()
            kdc, gsc = leer_kdeconnect(), leer_gsconnect()
            lecturas = (bt, upower, leer_usb(), leer_audio(), (kdc or []) + (gsc or []))
        actuales = armar(lecturas)
        ahora = time.time()

        # recordar lo visto: un USB desenchufado sigue en la lista unos días
        for d in actuales.values():
            self.conocidos[d["id"]] = {"nombre": d["nombre"], "tipo": d["tipo"], "visto": ahora if d["conectado"]
                                       else self.conocidos.get(d["id"], {}).get("visto", 0)}
        corte = ahora - DIAS_RECORDAR * 86400
        for ident, c in list(self.conocidos.items()):
            if ident in actuales:
                continue
            if c.get("visto", 0) < corte:
                del self.conocidos[ident]
                continue
            d = nuevo(ident, c["tipo"], c["nombre"])
            d["ayuda"] = t("Conéctalo o enciéndelo para ver su estado.", "Connect or turn it on to see its status.")
            actuales[ident] = d
        escribir_json(CONOCIDOS, self.conocidos)

        rutas, lista = {}, []
        for d in actuales.values():
            if d["id"] in prefs["ocultar"]:
                continue
            rutas[d["id"]] = d.pop("_rutas", {})
            d.pop("_mac", None)
            d["nombre"] = prefs["nombres"].get(d["id"], d["nombre"])
            if prefs["tipos"].get(d["id"]) in TIPOS:
                d["tipo"] = prefs["tipos"][d["id"]]
            d["tipo_nombre"] = nombre_tipo(d["tipo"])
            d["modelo3d"] = MODELO_3D.get(d["tipo"])
            lista.append(d)
        lista.sort(key=lambda d: (not d["conectado"], ORDEN_TIPOS.get(d["tipo"], 9), d["nombre"].lower()))

        self.historial.anotar(lista, ahora)
        for d in lista:
            d["horas_restantes"] = self.historial.horas_restantes(d, ahora)
            d["historial"] = [[x, b] for x, b, _ in self.historial.serie(d["id"])[-288:]]
        self.revisar_alertas(lista, prefs["umbrales"])
        con_bateria = [d for d in lista if d["conectado"] and d["bateria"] is not None]
        estado = {
            "dispositivos": lista,
            "equipo": equipo,
            "bluetooth_encendido": encendido,
            "app_celular": "KDE Connect" if kdc is not None else "GSConnect" if gsc is not None else None,
            "mas_baja": min(con_bateria, key=lambda d: d["bateria"])["id"] if con_bateria else None,
            "actividad": self.actividad[:20],
            "umbrales": prefs["umbrales"],
        }
        self.rutas = rutas
        if estado != self.estado:
            self.estado = estado
            self.al_cambiar()

    # ------------------------------------------------------------ acciones

    def accion(self, ident, accion, valor=None):
        d = next((x for x in self.estado.get("dispositivos", []) if x["id"] == ident), None)
        if not d:
            return False, t("No encontré ese dispositivo.", "Device not found.")
        rutas = self.rutas.get(ident, {})
        if accion == "probar":
            notificar(t(f"{d['nombre']}: así se ve un aviso", f"{d['nombre']}: this is how alerts look"),
                      t("Te avisaré cuando la batería esté baja.", "You will be notified when the battery is low."))
            return True, t("Aviso enviado.", "Notification sent.")
        if accion in ("ocultar", "renombrar", "tipo"):
            p = leer_json(PREFERENCIAS)
            if accion == "ocultar":
                p["ocultar"] = sorted(set(p.get("ocultar") or []) | {ident})
            elif accion == "renombrar" and str(valor or "").strip():
                p.setdefault("nombres", {})[ident] = str(valor).strip()[:60]
            elif accion == "tipo":
                actual = d["tipo"] if valor not in TIPOS else None
                p.setdefault("tipos", {})[ident] = valor if valor in TIPOS else TIPOS[(TIPOS.index(actual) + 1) % len(TIPOS)]
            escribir_json(PREFERENCIAS, p)
            return True, t("Guardado.", "Saved.")
        if accion == "ajustes_bt" and WINDOWS:
            os.startfile("ms-settings:bluetooth")
            return True, t("Abrí los ajustes de Bluetooth.", "Bluetooth settings opened.")
        if accion in ("conectar", "desconectar") and "bluez" in rutas:
            metodo = "Connect" if accion == "conectar" else "Disconnect"
            ok = dbus.llamar(dbus.SISTEMA, "org.bluez", rutas["bluez"], "org.bluez.Device1", metodo, espera=20000) is not None
            return ok, t("Listo.", "Done.") if ok else t("No respondió. Revisa que esté encendido y cerca.",
                                                         "No answer. Make sure it is on and nearby.")
        if accion == "sonar" and "telefono" in rutas:
            app, ruta = rutas["telefono"]
            if app == "KDE Connect":
                ok = dbus.llamar(dbus.SESION, "org.kde.kdeconnect", ruta + "/findmyphone",
                                 "org.kde.kdeconnect.device.findmyphone", "ring") is not None
            else:
                ok = dbus.llamar(dbus.SESION, "org.gnome.Shell.Extensions.GSConnect", ruta, "org.gtk.Actions",
                                 "Activate", "sava{sv}", ("ring", [], {})) is not None
            return ok, t("Sonando…", "Ringing…") if ok else t("El celular no respondió.", "The phone did not answer.")
        return False, t("Esa acción no está disponible ahora.", "That action is not available right now.")
