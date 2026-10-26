# akari 明かり — instalador para Windows 10 / 11 (en Linux: install.sh).
#
#   irm https://raw.githubusercontent.com/sJonathan15/akari/main/install.ps1 | iex
#
# Con opciones:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/sJonathan15/akari/main/install.ps1))) -Desinstalar
#
#   -Si              responder "sí" a todo
#   -SinStatusline   no conectar la línea de estado de Claude Code
#   -DesdeCodigo     no usar la app: instalar el servicio con tu Python y abrir el panel en Edge
#   -Desinstalar     quitar akari (deja %APPDATA%\akari)
#
# Lo normal: baja el instalador de la app (akari-setup-x64.exe, de Releases), que trae dentro
# Python, el servicio y las tres burbujas flotantes; queda para iniciar con Windows.
param([switch]$Si, [switch]$SinStatusline, [switch]$DesdeCodigo, [switch]$Desinstalar)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
# lo que imprime akari (Python) llega en UTF-8 y se muestra bien con tildes
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Repo = if ($env:AKARI_REPO) { $env:AKARI_REPO } else { 'https://github.com/sJonathan15/akari' }
$Es = (Get-UICulture).Name -like 'es*'
function T($es, $en) { if ($Es) { $es } else { $en } }
function Paso($es, $en) { Write-Host "➜ $(T $es $en)" -ForegroundColor DarkYellow }
function Ok($es, $en) { Write-Host "  ✓ $(T $es $en)" -ForegroundColor Green }
function Aviso($es, $en) { Write-Host "  ! $(T $es $en)" -ForegroundColor Yellow }
function Preguntar($es, $en) {
  if ($Si) { return $true }
  $r = Read-Host "  $(T $es $en) [S/n]"
  return -not ($r -match '^[nN]')
}

$Local = $env:LOCALAPPDATA
$App = Join-Path $Local 'Programs\akari'
$AppExe = Join-Path $App 'akari.exe'
$AppPython = Join-Path $App 'resources\python\python.exe'
$AppAkari = Join-Path $App 'resources\akari\bin\akari.py'
$Codigo = Join-Path $Local 'akari'                       # instalación desde el código
$Bin = Join-Path $Codigo 'bin'
$Inicio = Join-Path ([Environment]::GetFolderPath('Startup')) 'akari.lnk'

# Python de verdad (no el atajo de la Microsoft Store, que solo abre la tienda)
function Buscar-Python {
  foreach ($orden in @(@('py', '-3'), @('python'), @('python3'))) {
    if (-not (Get-Command $orden[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($orden | Select-Object -Skip 1)
    $ruta = & $orden[0] @extra -c "import sys; print(sys.executable) if sys.version_info >= (3, 9) else None" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ruta) { return ($ruta | Select-Object -Last 1).Trim() }
  }
  return $null
}

function Akari([string[]]$argumentos) {
  if (Test-Path $AppPython) { & $AppPython $AppAkari @argumentos }
  elseif (Test-Path (Join-Path $Bin 'akari.py')) { $py = Buscar-Python; if ($py) { & $py (Join-Path $Bin 'akari.py') @argumentos } }
}

function Quitar-DelPath($carpeta) {
  $actual = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not $actual) { return }
  $nuevo = ($actual -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $carpeta.TrimEnd('\') }) -join ';'
  [Environment]::SetEnvironmentVariable('Path', $nuevo, 'User')
}

# ------------------------------------------------------------------ desinstalar
if ($Desinstalar) {
  Paso 'Quitando akari…' 'Removing akari…'
  Akari @('desconectar-claude') | Out-Null
  Get-Process akari -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*akari.py*servicio*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  $desinstalador = Join-Path $App 'Uninstall akari.exe'
  if (Test-Path $desinstalador) { Start-Process -Wait $desinstalador -ArgumentList '/S' }
  Remove-Item -Force $Inicio -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $Codigo -ErrorAction SilentlyContinue
  Quitar-DelPath $Bin
  Ok "akari quitado. Tus ajustes siguen en $env:APPDATA\akari." "akari removed. Your settings remain in $env:APPDATA\akari."
  return
}

Paso 'Revisando tu equipo' 'Checking your system'
$so = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
Ok "Sistema: $so · $env:PROCESSOR_ARCHITECTURE" "System: $so · $env:PROCESSOR_ARCHITECTURE"

# ------------------------------------------------------------------ la app (recomendado)
$conApp = $false
if (-not $DesdeCodigo) {
  Paso 'Bajando la app de akari (burbujas + servicio)' 'Downloading the akari app (bubbles + service)'
  # x64 también corre en Windows ARM (emulación)
  $setup = Join-Path ([IO.Path]::GetTempPath()) 'akari-setup-x64.exe'
  try {
    Invoke-WebRequest -UseBasicParsing "$Repo/releases/latest/download/akari-setup-x64.exe" -OutFile $setup
    Get-Process akari -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Process -Wait $setup -ArgumentList '/S'
    Remove-Item $setup -ErrorAction SilentlyContinue
    $conApp = Test-Path $AppExe
  } catch {
    Aviso "No pude bajar la app ($($_.Exception.Message))." "Could not download the app ($($_.Exception.Message))."
  }
  if ($conApp) { Ok "App instalada en $App" "App installed in $App" }
  else { Aviso 'Sigo con la instalación desde el código (panel en el navegador, sin burbujas).' 'Falling back to the source install (panel in the browser, no bubbles).' }
}

# ------------------------------------------------------------------ desde el código (respaldo)
if (-not $conApp) {
  $py = Buscar-Python
  if (-not $py) {
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Preguntar '¿Instalar Python 3.12 con winget (para tu usuario)?' 'Install Python 3.12 with winget (for your user)?')) {
      winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements | Out-Host
      $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
      $py = Buscar-Python
    }
    if (-not $py) { throw (T 'Falta Python 3.9 o más nuevo: instálalo desde https://www.python.org y vuelve a intentar.' 'Python 3.9+ is missing: install it from https://www.python.org and retry.') }
  }
  Ok "Python: $py" "Python: $py"
  Paso "Copiando akari a $Codigo" "Copying akari to $Codigo"
  $tmp = Join-Path ([IO.Path]::GetTempPath()) "akari-$([guid]::NewGuid())"
  New-Item -ItemType Directory -Force $tmp | Out-Null
  $local = if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'akari\__init__.py'))) { $PSScriptRoot } else { $null }
  if (-not $local) {
    Invoke-WebRequest -UseBasicParsing "$Repo/archive/refs/heads/main.zip" -OutFile (Join-Path $tmp 'akari.zip')
    Expand-Archive (Join-Path $tmp 'akari.zip') -DestinationPath $tmp -Force
    $local = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
  }
  New-Item -ItemType Directory -Force $Codigo | Out-Null
  foreach ($parte in 'akari', 'bin', 'web', 'modelos', 'iconos', 'install.ps1', 'LICENSE', 'README.md') {
    $origen = Join-Path $local $parte
    if (-not (Test-Path $origen)) { continue }
    Remove-Item -Recurse -Force (Join-Path $Codigo $parte) -ErrorAction SilentlyContinue
    Copy-Item -Recurse -Force $origen (Join-Path $Codigo $parte)
  }
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

  # `akari` en la terminal
  $rutas = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not (($rutas -split ';') -contains $Bin)) {
    [Environment]::SetEnvironmentVariable('Path', ((@($rutas, $Bin) | Where-Object { $_ }) -join ';'), 'User')
  }
  Ok "Comando: $Bin\akari.cmd" "Command: $Bin\akari.cmd"

  # el servicio arranca con Windows, sin ventana (pythonw)
  $pyw = Join-Path (Split-Path $py) 'pythonw.exe'
  if (-not (Test-Path $pyw)) { $pyw = $py }
  $atajo = (New-Object -ComObject WScript.Shell).CreateShortcut($Inicio)
  $atajo.TargetPath = $pyw
  $atajo.Arguments = "`"$Bin\akari.py`" servicio"
  $atajo.WorkingDirectory = $Codigo
  $atajo.IconLocation = "$pyw,0"
  $atajo.Save()
  Start-Process $pyw -ArgumentList "`"$Bin\akari.py`" servicio" -WindowStyle Hidden
  Ok 'El servicio arranca con Windows' 'The service starts with Windows'
}

# ------------------------------------------------------------------ Claude Code
$hayClaude = (Test-Path (Join-Path $env:USERPROFILE '.claude')) -or (Get-Command claude -ErrorAction SilentlyContinue)
if (-not $SinStatusline -and $hayClaude) {
  Paso 'Claude Code' 'Claude Code'
  if (Preguntar '¿Conectar akari a la línea de estado de Claude Code? (así ve tus límites de 5 h y semanal; tu línea actual se conserva)' 'Connect akari to Claude Code''s status line? (so it can read your 5-hour and weekly limits; your current line is kept)') {
    Akari @('conectar-claude') | Out-Null
    Ok 'Línea de estado conectada (respaldo: ~\.claude\settings.json.bak-akari)' 'Status line connected (backup: ~\.claude\settings.json.bak-akari)'
  }
}

Write-Host ''
Paso '¡Listo! akari está instalado. Así se usa:' 'Done! akari is installed. Here''s how to use it:'
Write-Host ''
if ($conApp) {
  Start-Process $AppExe
  Akari @('guia', 'app') | ForEach-Object { "  $_" }
} else {
  Start-Sleep -Seconds 2
  Akari @('abrir')
  Write-Host (T '  El panel de akari se abre en Edge. Ábrelo cuando quieras con:  akari abrir' '  The akari panel opens in Edge. Open it any time with:  akari abrir')
  Write-Host (T '  Para tener las burbujas flotantes, instala la app: vuelve a ejecutar este instalador sin -DesdeCodigo.' '  For the floating bubbles, install the app: run this installer again without -DesdeCodigo.')
}
