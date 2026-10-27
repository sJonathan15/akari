# Mide la app de escritorio instalada: RAM (Working Set de todos sus procesos: la app, WebView2
# y el servicio de Python), CPU en reposo y, con -Raton, que una burbuja se abra al pasar el
# puntero de verdad y se cierre al salir. Lo usa el CI de Windows; deja un JSON con los datos.
#
#   pwsh scripts/medir.ps1 -Exe "$env:LOCALAPPDATA\Programs\akari\akari.exe" [-Espera 30] [-Ventana 20] [-Raton]
param(
  [Parameter(Mandatory)][string]$Exe,
  [int]$Espera = 30,
  [int]$Ventana = 20,
  [switch]$Raton,
  [string]$Nombre = 'akari',
  [string]$Salida = 'medicion.json',
  [string]$Captura = '',
  # tras usar una burbuja, cuánto esperar para medir otra vez (la app de Windows destruye su WebView2 al minuto)
  [int]$TrasUso = 0
)
$ErrorActionPreference = 'Stop'

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class Ventanas {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public delegate bool Cada(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Cada f, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static List<int[]> De(HashSet<uint> pids) {
    var l = new List<int[]>();
    EnumWindows((h, p) => {
      uint pid; GetWindowThreadProcessId(h, out pid);
      RECT r;
      if (pids.Contains(pid) && IsWindowVisible(h) && GetWindowRect(h, out r) && r.Right - r.Left > 1)
        l.Add(new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top });
      return true;
    }, IntPtr.Zero);
    return l;
  }
}
'@
[void][Ventanas]::SetProcessDPIAware()

# la app y todo lo que cuelga de ella (WebView2, Python, PowerShell de paso…)
function Arbol([int]$raiz) {
  $todos = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name)
  $ids = [System.Collections.Generic.HashSet[int]]::new()
  [void]$ids.Add($raiz)
  do {
    $antes = $ids.Count
    foreach ($p in $todos) { if ($ids.Contains([int]$p.ParentProcessId)) { [void]$ids.Add([int]$p.ProcessId) } }
  } while ($ids.Count -ne $antes)
  return @($ids)
}
function Procesos([int]$raiz) { @(Arbol $raiz | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }) }
function Rects([int]$raiz) {
  $set = [System.Collections.Generic.HashSet[uint32]]::new()
  foreach ($i in (Arbol $raiz)) { [void]$set.Add([uint32]$i) }
  return @([Ventanas]::De($set) | ForEach-Object { , @($_) })
}
function Mover([int]$x, [int]$y) {
  [void][Ventanas]::SetCursorPos($x, $y)
  [Ventanas]::mouse_event(0x0001, 1, 0, 0, [UIntPtr]::Zero)     # un movimiento real: WM_MOUSEMOVE
  [Ventanas]::mouse_event(0x0001, -1, 0, 0, [UIntPtr]::Zero)
}

Write-Host "Arrancando $Exe"
$app = Start-Process $Exe -PassThru
Start-Sleep -Seconds $Espera

# ------------------------------------------------------------ RAM
$procs = Procesos $app.Id
$ws = ($procs | Measure-Object WorkingSet64 -Sum).Sum
$privada = ($procs | Measure-Object PrivateMemorySize64 -Sum).Sum
$detalle = @($procs | Group-Object ProcessName | ForEach-Object {
  [ordered]@{ proceso = $_.Name; cuantos = $_.Count; ws_mb = [math]::Round((($_.Group | Measure-Object WorkingSet64 -Sum).Sum) / 1MB, 1) }
})

# ------------------------------------------------------------ CPU en reposo
# se muestrea cada segundo para contar también los procesos que nacen y mueren en medio
$inicio = @{}
foreach ($p in $procs) { try { $inicio[$p.Id] = $p.TotalProcessorTime.TotalMilliseconds } catch {} }
$ultimo = @{} + $inicio
$reloj = [Diagnostics.Stopwatch]::StartNew()
while ($reloj.Elapsed.TotalSeconds -lt $Ventana) {
  foreach ($p in (Procesos $app.Id)) {
    try { $ultimo[$p.Id] = [math]::Max([double]($ultimo[$p.Id] ?? 0), $p.TotalProcessorTime.TotalMilliseconds) } catch {}
  }
  Start-Sleep -Milliseconds 1000
}
$segundos = $reloj.Elapsed.TotalSeconds
$usado = 0.0
foreach ($id in $ultimo.Keys) { $usado += $ultimo[$id] - [double]($inicio[$id] ?? 0) }
$nucleos = [Environment]::ProcessorCount
$cpu = $usado / ($segundos * 1000 * $nucleos) * 100

# ------------------------------------------------------------ burbujas y ratón
$rects = @(Rects $app.Id | Where-Object { $_[2] -gt 20 -and $_[3] -gt 20 })   # sin las ventanitas ocultas de la bandeja
$prueba = $null     # (en PowerShell $prueba y $Raton no se pisan; $raton sí sería el mismo que $Raton)
if ($Raton) {
  # instalación nueva: el recorrido de bienvenida deja abierta la burbuja de su paso; se salta como quien ya lo vio
  try { Invoke-RestMethod -Method Post http://127.0.0.1:47830/api/recorrido -ContentType 'application/json' -Body '{"accion": "saltar"}' | Out-Null } catch { }
  Start-Sleep -Seconds 3      # que la página lo vea y la burbuja se cierre
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $pantalla = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $centro = $pantalla.Left + $pantalla.Width / 2
  # la de IA: la primera a la derecha del centro
  $ia = $rects | Where-Object { $_[0] -ge $centro } | Sort-Object { $_[0] } | Select-Object -First 1
  if ($ia) {
    Mover ($ia[0] + 40) ($ia[1] + 15)
    # la primera vez se crea WebView2: hasta 8 s
    $abierta = $null
    foreach ($i in 1..27) {
      Start-Sleep -Milliseconds 300
      $abierta = Rects $app.Id | Where-Object { $_[0] -le $ia[0] + 40 -and $_[0] + $_[2] -ge $ia[0] + 40 -and $_[1] -le $ia[1] + 15 -and $_[3] -gt $ia[3] * 3 } | Select-Object -First 1
      if ($abierta) { break }
    }
    $tarda = $i * 300
    Start-Sleep -Milliseconds 700      # que termine la animación
    if ($Captura) {
      $bmp = New-Object System.Drawing.Bitmap 1280, 820
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen([int]($centro - 640), $pantalla.Top, 0, 0, $bmp.Size)
      $bmp.Save($Captura, [System.Drawing.Imaging.ImageFormat]::Png)
      $g.Dispose(); $bmp.Dispose()
    }
    Mover ($pantalla.Left + 30) ($pantalla.Bottom - 30)
    $cerrada = $null
    foreach ($i in 1..13) {
      Start-Sleep -Milliseconds 300
      $cerrada = Rects $app.Id | Where-Object { $_[0] -eq $ia[0] -and $_[1] -eq $ia[1] -and $_[3] -eq $ia[3] } | Select-Object -First 1
      if ($cerrada) { break }
    }
    $prueba = [ordered]@{
      cerrada_antes = $ia; abierta = $abierta; cerrada_despues = $cerrada; abre_en_ms = $tarda
      se_abrio = [bool]($abierta -and $abierta[3] -gt $ia[3] * 3)
      se_cerro = [bool]($cerrada -and $cerrada[3] -eq $ia[3])
    }
  }
}

$tras = $null
if ($TrasUso -gt 0) {
  Start-Sleep -Seconds $TrasUso
  $tras = [math]::Round(((Procesos $app.Id) | Measure-Object WorkingSet64 -Sum).Sum / 1MB, 1)
}

# ------------------------------------------------------------ recorrido por los grupos (capturas)
# Después de medir, para que no cambie los números: todo cerrado y cada grupo abierto, con sus medidas;
# las píldoras no deben encimarse ni salirse de la pantalla.
$visita = $null
if ($Raton -and $Captura) {
  $base = [IO.Path]::GetFileNameWithoutExtension($Captura)
  $todo = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  function Foto($nombre) {
    $bmp = New-Object System.Drawing.Bitmap $todo.Width, $todo.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($todo.Left, $todo.Top, 0, 0, $bmp.Size)
    $bmp.Save("$base-$nombre.png", [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
  }
  Mover ($pantalla.Left + 30) ($pantalla.Bottom - 30)
  Start-Sleep -Seconds 2
  $pildoras = @(Rects $app.Id | Where-Object { $_[2] -gt 20 -and $_[3] -gt 20 } | Sort-Object { $_[0] })
  Foto 'cerradas'
  $encimadas = 0
  for ($a = 0; $a -lt $pildoras.Count; $a++) {
    for ($b = $a + 1; $b -lt $pildoras.Count; $b++) {
      $x = $pildoras[$a]; $y = $pildoras[$b]
      if ($x[0] -lt $y[0] + $y[2] -and $y[0] -lt $x[0] + $x[2] -and $x[1] -lt $y[1] + $y[3] -and $y[1] -lt $x[1] + $x[3]) { $encimadas++ }
    }
  }
  $fuera = @($pildoras | Where-Object { $_[0] -lt $todo.Left -or $_[1] -lt $todo.Top -or $_[0] + $_[2] -gt $todo.Right -or $_[1] + $_[3] -gt $todo.Bottom }).Count
  $grupos = @()
  $n = 0
  foreach ($p in $pildoras) {
    $n++
    $px = $p[0] + [int]($p[2] / 2); $py = $p[1] + [int]($p[3] / 2)
    Mover $px $py
    $abierta = $null
    foreach ($i in 1..27) {
      Start-Sleep -Milliseconds 300
      $abierta = Rects $app.Id | Where-Object { $_[0] -le $px -and $_[0] + $_[2] -ge $px -and $_[1] -le $py -and $_[3] -gt $p[3] * 2 } | Select-Object -First 1
      if ($abierta) { break }
    }
    Start-Sleep -Milliseconds 900
    Foto "grupo$n"
    $grupos += [ordered]@{ pildora = $p; abierta = $abierta
                           cabe = [bool]($abierta -and $abierta[1] + $abierta[3] -le $todo.Bottom -and $abierta[0] -ge $todo.Left -and $abierta[0] + $abierta[2] -le $todo.Right) }
    Mover ($pantalla.Left + 30) ($pantalla.Bottom - 30)
    Start-Sleep -Seconds 2
  }
  $visita = [ordered]@{ pantalla = @($todo.Width, $todo.Height); pildoras = $pildoras; encimadas = $encimadas; fuera = $fuera; grupos = $grupos }
  # una sola imagen (el CI sube captura.png): todo cerrado y cada grupo abierto, en una cuadrícula de 2 columnas
  $fotos = @("$base-cerradas.png") + @(1..$n | ForEach-Object { "$base-grupo$_.png" })
  $ancho = [int]($todo.Width / 2); $alto = [int]($todo.Height / 2)
  $hoja = New-Object System.Drawing.Bitmap ($ancho * 2), ($alto * [math]::Ceiling($fotos.Count / 2))
  $g = [System.Drawing.Graphics]::FromImage($hoja)
  $g.Clear([System.Drawing.Color]::Black)
  for ($i = 0; $i -lt $fotos.Count; $i++) {
    $img = [System.Drawing.Image]::FromFile((Resolve-Path $fotos[$i]))
    $g.DrawImage($img, ($i % 2) * $ancho, [math]::Floor($i / 2) * $alto, $ancho, $alto)
    $img.Dispose()
  }
  $g.Dispose()
  $hoja.Save($Captura, [System.Drawing.Imaging.ImageFormat]::Png)
  $hoja.Dispose()
}

$datos = [ordered]@{
  app = $Nombre
  ram_ws_mb = [math]::Round($ws / 1MB, 1)
  ram_privada_mb = [math]::Round($privada / 1MB, 1)
  procesos = $procs.Count
  detalle = $detalle
  cpu_reposo_pct = [math]::Round($cpu, 2)
  ram_tras_uso_mb = $tras
  cpu_segundos = [math]::Round($segundos, 1)
  nucleos = $nucleos
  ventanas = @($rects | ForEach-Object { , @($_) })
  raton = $prueba
  visita = $visita
  pid = $app.Id
}
$datos | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $Salida
$datos | ConvertTo-Json -Depth 6
