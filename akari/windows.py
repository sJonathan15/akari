"""Lecturas propias de Windows (sin instalar nada: Windows PowerShell 5.1 y ctypes).

  * Bluetooth: los aparatos vinculados (PnP `BTHENUM\\DEV_…` / `BTHLE\\DEV_…`), si están
    conectados, su clase (ratón, teclado, audio, celular…) y la batería que reporta Windows;
  * USB: ratones, teclados, audio USB y celulares conectados por cable (por VID/PID);
  * batería de la laptop (GetSystemPowerStatus) y Bloq Mayús / Bloq Num (GetKeyState).

Devuelve los mismos datos que las lecturas de Linux para que `dispositivos.armar` no cambie.
"""
import ctypes
import json
import threading
import time

from .comun import WINDOWS, powershell

# Una sola pasada por PnP con todas las propiedades que hacen falta. La salida es JSON en
# ASCII (lo que no lo es va como \\uXXXX) para no depender de la página de códigos de la consola.
SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$K_BATERIA = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$K_CONECTADO = '{83DA6326-97A6-4088-9453-A1923F573B29} 15'
$K_CLASE = '{2BD67D8B-8BEB-48D5-87E0-6CDA3428040A} 10'
$K_PADRE = '{4340A6C5-93FA-4706-972C-7B648008A5A7} 8'
$K_NOMBRE_BUS = '{540B947E-8B40-45BC-A8A2-6A0B894CBDA2} 4'

# Una consulta por propiedad (para todos los aparatos a la vez): Windows devuelve en KeyName a
# veces el GUID y a veces el nombre (DEVPKEY_…), así no hace falta saber cuál.
function Props($ids, $claves) {
  $tabla = @{}
  if (-not $ids) { return $tabla }
  foreach ($k in $claves) {
    foreach ($p in @(Get-PnpDeviceProperty -InstanceId $ids -KeyName $k)) {
      if ($p.Type -eq 'Empty' -or $null -eq $p.Data) { continue }
      if (-not $tabla.ContainsKey($p.InstanceId)) { $tabla[$p.InstanceId] = @{} }
      $tabla[$p.InstanceId][$k] = $p.Data
    }
  }
  return $tabla
}

$bt = @()
$nodos = @(Get-PnpDevice -Class Bluetooth | Where-Object { $_.InstanceId -match '^BTH(ENUM|LE)\\DEV_([0-9A-F]{12})' })
$pb = Props @($nodos | ForEach-Object { $_.InstanceId }) @($K_BATERIA, $K_CONECTADO, $K_CLASE)
foreach ($d in $nodos) {
  $null = $d.InstanceId -match 'DEV_([0-9A-F]{12})'
  $p = $pb[$d.InstanceId]; if (-not $p) { $p = @{} }
  $bt += [ordered]@{
    id = $d.InstanceId; mac = $Matches[1]; nombre = $d.FriendlyName; estado = "$($d.Status)"
    conectado = $p[$K_CONECTADO]; bateria = $p[$K_BATERIA]; clase = $p[$K_CLASE]
  }
}

$usb = @()
$hid = @(Get-PnpDevice -PresentOnly | Where-Object {
  $_.Class -in @('Mouse', 'Keyboard', 'MEDIA', 'WPD', 'Camera', 'Image') -and
  $_.InstanceId -match '^(USB|HID)\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})' })
$padres = Props @($hid | ForEach-Object { $_.InstanceId }) @($K_PADRE, $K_NOMBRE_BUS)
$ids_padre = @($padres.Values | ForEach-Object { $_[$K_PADRE] } | Where-Object { $_ } | Select-Object -Unique)
$nombres_padre = Props $ids_padre @($K_NOMBRE_BUS)
foreach ($d in $hid) {
  $null = $d.InstanceId -match 'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})'
  $p = $padres[$d.InstanceId]; if (-not $p) { $p = @{} }
  $nombre = $p[$K_NOMBRE_BUS]
  if (-not $nombre -and $p[$K_PADRE] -and $nombres_padre[$p[$K_PADRE]]) { $nombre = $nombres_padre[$p[$K_PADRE]][$K_NOMBRE_BUS] }
  $usb += [ordered]@{ vid = $Matches[1]; pid = $Matches[2]; clase = "$($d.Class)"; nombre = $nombre; generico = $d.FriendlyName }
}

$json = ConvertTo-Json -Compress -Depth 4 @{ bt = $bt; usb = $usb }
[regex]::Replace($json, '[^\x00-\x7F]', { param($m) '\u{0:x4}' -f [int][char]$m.Value })
"""

# clase de dispositivo Bluetooth (Class of Device): clase mayor en los bits 8-12
CLASE_MAYOR = {2: "celular", 4: "audifonos"}
CADA = 12          # segundos entre pasadas por PnP (cada una tarda ~1 s)


def tipo_por_clase(clase):
    """Class of Device de Bluetooth -> tipo de akari (o None si no dice nada útil)."""
    if not isinstance(clase, int) or clase <= 0:
        return None
    mayor = (clase >> 8) & 0x1F
    if mayor == 5:                      # periférico: teclado / apuntador / mando
        menor = clase >> 6 & 0x3
        if menor == 2:
            return "raton"
        if menor in (1, 3):
            return "teclado"
        if (clase >> 2 & 0xF) in (1, 2):
            return "mando"
        return None
    return CLASE_MAYOR.get(mayor)


def mac(texto):
    texto = (texto or "").upper()
    return ":".join(texto[i:i + 2] for i in range(0, 12, 2)) if len(texto) == 12 else texto


def convertir(datos, pista, celulares):
    """JSON del script -> (bluetooth, usb) con el formato de las lecturas de Linux."""
    bt = {}
    for d in datos.get("bt") or []:
        nombre = d.get("nombre") or mac(d.get("mac"))
        direccion = mac(d.get("mac"))
        conectado = d.get("conectado")
        if conectado is None:            # Windows antiguo sin esa propiedad
            conectado = d.get("estado") == "OK" and d.get("bateria") is not None
        anterior = bt.get(direccion)     # el mismo aparato puede salir por BTHENUM y por BTHLE
        nuevo = {
            "ruta": d.get("id"), "nombre": nombre,
            "tipo": tipo_por_clase(d.get("clase")) or pista(nombre),
            "conectado": bool(conectado),
            "bateria": d.get("bateria") if isinstance(d.get("bateria"), int) else None, "rssi": None,
        }
        if anterior:
            nuevo["conectado"] = nuevo["conectado"] or anterior["conectado"]
            nuevo["bateria"] = nuevo["bateria"] if nuevo["bateria"] is not None else anterior["bateria"]
            nuevo["tipo"] = nuevo["tipo"] or anterior["tipo"]
        bt[direccion] = nuevo

    grupos = {}
    for u in datos.get("usb") or []:
        clave = f"{(u.get('vid') or '').lower()}-{(u.get('pid') or '').lower()}"
        g = grupos.setdefault(clave, {"clases": set(), "nombre": None, "vid": (u.get("vid") or "").lower()})
        g["clases"].add(u.get("clase"))
        g["nombre"] = g["nombre"] or u.get("nombre")
    usb = []
    for clave, g in grupos.items():
        nombre = g["nombre"] or ""
        clases = g["clases"]
        tipo = None
        if g["vid"] in celulares or "WPD" in clases:
            tipo = "celular"
        elif clases & {"Mouse", "Keyboard"}:
            tipo = pista(nombre) or ("raton" if "Mouse" in clases else "teclado")
        elif "MEDIA" in clases and not clases & {"Camera", "Image"}:
            tipo = "audifonos"
        if not tipo:
            continue
        usb.append({"id": "usb-" + clave, "sysfs": None, "tipo": tipo, "nombre": nombre or None,
                    "fabricante": "", "velocidad": None})
    return bt, usb


class _Estado(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def bateria_equipo():
    """Batería de la laptop, con el mismo formato que la de UPower (None en un equipo de escritorio)."""
    e = _Estado()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
            return None
    except (OSError, AttributeError):
        return None
    if e.BatteryFlag & 128 or e.BatteryFlag == 255 or e.BatteryLifePercent > 100:
        return None
    estado = "cargando" if e.BatteryFlag & 8 else "llena" if e.ACLineStatus == 1 and e.BatteryLifePercent >= 100 \
        else "descargando" if e.ACLineStatus == 0 else ""
    resta = e.BatteryLifeTime if e.BatteryLifeTime not in (0, 0xFFFFFFFF) else None
    return {"bateria": e.BatteryLifePercent, "estado": estado, "vacia_en": resta, "llena_en": None}


def bloqueos():
    """{'capslock': bool, 'numlock': bool} del teclado (es el mismo para todos en Windows)."""
    try:
        u = ctypes.windll.user32
        return {"capslock": bool(u.GetKeyState(0x14) & 1), "numlock": bool(u.GetKeyState(0x90) & 1)}
    except (OSError, AttributeError):
        return {}


class LectorWindows:
    """Guarda la última pasada por PnP y la renueva en segundo plano cada CADA segundos."""

    def __init__(self, pista, celulares):
        self.pista, self.celulares = pista, celulares
        self.datos = {"bt": [], "usb": []}
        self.listo = 0
        self.ocupado = False
        self.bloqueo = threading.Lock()

    def _pasada(self):
        try:
            salida = powershell(SCRIPT, timeout=40)
            if salida:
                datos = json.loads(salida.strip().splitlines()[-1])
                if isinstance(datos, dict):
                    self.datos = datos
        except (ValueError, IndexError):
            pass
        finally:
            self.listo = time.time()
            self.ocupado = False

    def leer(self, esperar=False):
        if not WINDOWS:
            return {}, []
        with self.bloqueo:
            toca = not self.ocupado and time.time() - self.listo > CADA
            if toca:
                self.ocupado = True
        if toca:
            if esperar or not self.listo:
                self._pasada()          # la primera vez se espera, para no empezar vacío
            else:
                threading.Thread(target=self._pasada, daemon=True).start()
        return convertir(self.datos, self.pista, self.celulares)
