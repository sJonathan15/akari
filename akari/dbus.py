"""Llamadas D-Bus mínimas. Usa PyGObject si está instalado y, si no, `busctl --json`
(viene con systemd), así akari no exige paquetes extra en ninguna distribución."""
import json
import subprocess

try:
    from gi.repository import Gio, GLib
    _GI = True
except ImportError:          # sin PyGObject
    _GI = False

SISTEMA, SESION = "system", "session"
_buses = {}


def _bus(cual):
    if cual not in _buses:
        try:
            _buses[cual] = Gio.bus_get_sync(Gio.BusType.SYSTEM if cual == SISTEMA else Gio.BusType.SESSION)
        except GLib.Error:
            _buses[cual] = None
    return _buses[cual]


def _desenvolver(v):
    """busctl --json escribe cada variante como {"type": "s", "data": ...}."""
    if isinstance(v, dict):
        if set(v) == {"type", "data"} and isinstance(v["type"], str):
            return _desenvolver(v["data"])
        return {k: _desenvolver(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_desenvolver(x) for x in v]
    return v


def llamar(bus, nombre, ruta, interfaz, metodo, firma="", args=(), espera=1500):
    """Devuelve la tupla de resultados o None si el servicio no está o falla."""
    if _GI:
        conexion = _bus(bus)
        if conexion is None:
            return None
        try:
            parametros = GLib.Variant(f"({firma})", tuple(args)) if firma else None
            r = conexion.call_sync(nombre, ruta, interfaz, metodo, parametros, None,
                                   Gio.DBusCallFlags.NONE, espera, None)
            return r.unpack() if r is not None else ()
        except GLib.Error:
            return None
    orden = ["busctl", "--user" if bus == SESION else "--system", "--json=short",
             f"--timeout={max(1, espera // 1000)}", "call", nombre, ruta, interfaz, metodo]
    if firma:
        orden.append(firma)
        for a in args:
            if isinstance(a, bool):
                orden.append("true" if a else "false")
            elif isinstance(a, (list, dict)):
                if a:           # solo hacen falta arreglos/diccionarios vacíos
                    return None
                orden.append("0")
            else:
                orden.append(str(a))
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=espera / 1000 + 2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    if not r.stdout.strip():
        return ()
    try:
        return tuple(_desenvolver(json.loads(r.stdout).get("data", [])))
    except ValueError:
        return None


def propiedades(bus, nombre, ruta, interfaz):
    r = llamar(bus, nombre, ruta, "org.freedesktop.DBus.Properties", "GetAll", "s", (interfaz,))
    return r[0] if r else {}


def objetos(bus, nombre, ruta="/"):
    r = llamar(bus, nombre, ruta, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return r[0] if r else None
