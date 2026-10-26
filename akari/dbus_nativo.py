"""Cliente D-Bus mínimo en Python puro (solo la biblioteca estándar).

Es el respaldo para distribuciones sin PyGObject ni `busctl` (sin systemd: Void, Artix,
Devuan, MX Linux, Alpine, Gentoo con OpenRC…). Habla el protocolo directamente por el
socket del bus: autenticación EXTERNAL, llamadas a métodos y lectura de las respuestas.
Solo hace lo que akari necesita: llamar a un método y desempaquetar el resultado igual que
lo hace PyGObject (variantes ya abiertas, estructuras como tuplas, diccionarios como dict).
"""
import os
import socket
import struct
import threading

SISTEMA, SESION = "system", "session"
SOCKET_SISTEMA = "unix:path=/var/run/dbus/system_bus_socket"

# alineación de cada tipo básico (especificación de D-Bus, "Marshaling")
ALINEACION = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8, "h": 4,
              "s": 4, "o": 4, "g": 1, "v": 1, "a": 4, "(": 8, "{": 8}
FIJOS = {"y": "B", "b": "I", "n": "h", "q": "H", "i": "i", "u": "I", "x": "q", "t": "Q", "d": "d", "h": "I"}


class ErrorDBus(Exception):
    pass


def fin_tipo(firma, i):
    """Índice justo después del tipo completo que empieza en firma[i]."""
    c = firma[i]
    if c == "a":
        return fin_tipo(firma, i + 1)
    if c in "({":
        cierre, nivel = ")" if c == "(" else "}", 0
        for j in range(i, len(firma)):
            if firma[j] in "({":
                nivel += 1
            elif firma[j] in ")}":
                nivel -= 1
                if nivel == 0:
                    if firma[j] != cierre:
                        raise ErrorDBus("firma inválida: " + firma)
                    return j + 1
        raise ErrorDBus("firma inválida: " + firma)
    if c not in ALINEACION:
        raise ErrorDBus("tipo desconocido: " + c)
    return i + 1


def tipos(firma):
    """'sa{sv}i' -> ['s', 'a{sv}', 'i']"""
    lista, i = [], 0
    while i < len(firma):
        j = fin_tipo(firma, i)
        lista.append(firma[i:j])
        i = j
    return lista


def firma_de(valor):
    """Firma de un valor de Python para meterlo en una variante."""
    if isinstance(valor, bool):
        return "b"
    if isinstance(valor, int):
        return "i" if -2 ** 31 <= valor < 2 ** 31 else "x"
    if isinstance(valor, float):
        return "d"
    if isinstance(valor, str):
        return "s"
    if isinstance(valor, dict):
        return "a{sv}"
    if isinstance(valor, (list, tuple)):
        return "av"
    raise ErrorDBus(f"no sé empaquetar {type(valor).__name__}")


# ---------------------------------------------------------------- empaquetar

class Escritor:
    def __init__(self):
        self.buf = bytearray()

    def alinear(self, n):
        self.buf += b"\0" * (-len(self.buf) % n)

    def escribir(self, firma, valor):
        c = firma[0]
        if c in FIJOS:
            self.alinear(ALINEACION[c])
            self.buf += struct.pack("<" + FIJOS[c], int(bool(valor)) if c == "b" else valor)
        elif c in "so":
            datos = str(valor).encode()
            self.alinear(4)
            self.buf += struct.pack("<I", len(datos)) + datos + b"\0"
        elif c == "g":
            datos = str(valor).encode()
            self.buf += struct.pack("<B", len(datos)) + datos + b"\0"
        elif c == "v":
            # (firma, valor) explícito, o se deduce del tipo de Python
            sub, dato = valor if isinstance(valor, tuple) and len(valor) == 2 and isinstance(valor[0], str) \
                else (firma_de(valor), valor)
            self.escribir("g", sub)
            self.escribir(sub, dato)
        elif c == "a":
            elemento = firma[1:]
            self.alinear(4)
            lugar = len(self.buf)
            self.buf += b"\0\0\0\0"
            self.alinear(ALINEACION[elemento[0]])
            inicio = len(self.buf)
            if elemento[0] == "{":
                clave, val = tipos(elemento[1:-1])
                for k, v in dict(valor).items():
                    self.alinear(8)
                    self.escribir(clave, k)
                    self.escribir(val, v)
            else:
                for v in valor:
                    self.escribir(elemento, v)
            struct.pack_into("<I", self.buf, lugar, len(self.buf) - inicio)
        elif c == "(":
            self.alinear(8)
            for sub, v in zip(tipos(firma[1:-1]), valor):
                self.escribir(sub, v)
        else:
            raise ErrorDBus("tipo no soportado: " + firma)


# ---------------------------------------------------------------- desempaquetar

class Lector:
    def __init__(self, datos, orden="<", pos=0):
        self.datos, self.orden, self.pos = datos, orden, pos

    def alinear(self, n):
        self.pos += -self.pos % n

    def leer(self, firma):
        c = firma[0]
        if c in FIJOS:
            self.alinear(ALINEACION[c])
            formato = self.orden + FIJOS[c]
            (v,) = struct.unpack_from(formato, self.datos, self.pos)
            self.pos += struct.calcsize(formato)
            return bool(v) if c == "b" else v
        if c in "so":
            self.alinear(4)
            (n,) = struct.unpack_from(self.orden + "I", self.datos, self.pos)
            v = self.datos[self.pos + 4:self.pos + 4 + n].decode("utf-8", errors="replace")
            self.pos += 4 + n + 1
            return v
        if c == "g":
            n = self.datos[self.pos]
            v = self.datos[self.pos + 1:self.pos + 1 + n].decode()
            self.pos += 1 + n + 1
            return v
        if c == "v":
            return self.leer(self.leer("g"))
        if c == "a":
            elemento = firma[1:]
            self.alinear(4)
            (n,) = struct.unpack_from(self.orden + "I", self.datos, self.pos)
            self.pos += 4
            self.alinear(ALINEACION[elemento[0]])
            fin = self.pos + n
            if elemento[0] == "{":
                clave, val = tipos(elemento[1:-1])
                salida = {}
                while self.pos < fin:
                    self.alinear(8)
                    k = self.leer(clave)
                    salida[k] = self.leer(val)
                return salida
            salida = []
            while self.pos < fin:
                salida.append(self.leer(elemento))
            return salida
        if c == "(":
            self.alinear(8)
            return tuple(self.leer(sub) for sub in tipos(firma[1:-1]))
        raise ErrorDBus("tipo no soportado: " + firma)


# ---------------------------------------------------------------- conexión

def direcciones(bus):
    if bus == SISTEMA:
        texto = os.environ.get("DBUS_SYSTEM_BUS_ADDRESS") or SOCKET_SISTEMA
    else:
        texto = os.environ.get("DBUS_SESSION_BUS_ADDRESS") or ""
        if not texto and os.environ.get("XDG_RUNTIME_DIR"):
            texto = "unix:path=" + os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus")
    salida = []
    for d in texto.split(";"):
        if not d.startswith("unix:"):
            continue
        claves = dict(p.split("=", 1) for p in d[5:].split(",") if "=" in p)
        if "path" in claves:
            salida.append(claves["path"])
        elif "abstract" in claves:
            salida.append("\0" + claves["abstract"])
    return salida


class Conexion:
    def __init__(self, ruta, espera):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(espera)
        self.sock.connect(ruta)
        self.serie = 0
        self.resto = b""
        self.sock.sendall(b"\0AUTH EXTERNAL " + str(os.getuid()).encode().hex().encode() + b"\r\n")
        linea = self._linea()
        if not linea.startswith(b"OK"):
            raise ErrorDBus("autenticación rechazada")
        self.sock.sendall(b"BEGIN\r\n")
        self.llamar("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "Hello")

    def _linea(self):
        while b"\r\n" not in self.resto:
            trozo = self.sock.recv(4096)
            if not trozo:
                raise ErrorDBus("el bus cerró la conexión")
            self.resto += trozo
        linea, self.resto = self.resto.split(b"\r\n", 1)
        return linea

    def _recibir(self, n):
        while len(self.resto) < n:
            trozo = self.sock.recv(max(65536, n - len(self.resto)))
            if not trozo:
                raise ErrorDBus("el bus cerró la conexión")
            self.resto += trozo
        datos, self.resto = self.resto[:n], self.resto[n:]
        return datos

    def llamar(self, destino, ruta, interfaz, metodo, firma="", args=()):
        self.serie += 1
        cuerpo = Escritor()
        for sub, v in zip(tipos(firma), args):
            cuerpo.escribir(sub, v)
        campos = [(1, ("o", ruta)), (2, ("s", interfaz)), (3, ("s", metodo)), (6, ("s", destino))]
        if firma:
            campos.append((8, ("g", firma)))
        cabecera = Escritor()
        cabecera.buf += struct.pack("<cBBBII", b"l", 1, 0, 1, len(cuerpo.buf), self.serie)
        cabecera.escribir("a(yv)", campos)
        cabecera.alinear(8)
        self.sock.sendall(bytes(cabecera.buf) + bytes(cuerpo.buf))
        while True:     # se descartan las señales (NameAcquired…) hasta llegar a nuestra respuesta
            fijo = self._recibir(16)
            orden = "<" if fijo[0:1] == b"l" else ">"
            tipo = fijo[1]
            largo_cuerpo, _, largo_campos = struct.unpack_from(orden + "III", fijo, 4)
            resto = self._recibir(largo_campos + (-(16 + largo_campos) % 8) + largo_cuerpo)
            mensaje = fijo + resto
            campos = dict(Lector(mensaje, orden, 12).leer("a(yv)"))
            if tipo not in (2, 3) or campos.get(5) != self.serie:
                continue
            lector = Lector(mensaje, orden, 16 + largo_campos + (-(16 + largo_campos) % 8))
            valores = tuple(lector.leer(sub) for sub in tipos(campos.get(8, "")))
            if tipo == 3:
                raise ErrorDBus(f"{campos.get(4)}: {valores[0] if valores else ''}")
            return valores

    def cerrar(self):
        try:
            self.sock.close()
        except OSError:
            pass


_conexiones = {}
_bloqueo = threading.Lock()


def disponible(bus):
    return hasattr(socket, "AF_UNIX") and hasattr(os, "getuid") and bool(direcciones(bus))


def llamar(bus, nombre, ruta, interfaz, metodo, firma="", args=(), espera=1500):
    """Como dbus.llamar: la tupla de resultados, o None si el bus o el servicio no están."""
    with _bloqueo:
        conexion = _conexiones.get(bus)
        for intento in range(2):         # una conexión vieja puede haberse cortado: se reintenta una vez
            if conexion is None:
                for direccion in direcciones(bus):
                    try:
                        conexion = Conexion(direccion, 3)
                        break
                    except (OSError, ErrorDBus):
                        conexion = None
                if conexion is None:
                    return None
                _conexiones[bus] = conexion
            try:
                conexion.sock.settimeout(max(1, espera / 1000))
                return conexion.llamar(nombre, ruta, interfaz, metodo, firma, args)
            except ErrorDBus as e:
                if "cerró" not in str(e):
                    return None
            except (OSError, struct.error, IndexError, ValueError):
                pass
            conexion.cerrar()
            conexion = _conexiones[bus] = None
        return None
