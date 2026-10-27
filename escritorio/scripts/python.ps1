# Python embebido oficial (python.org) para el instalador de Windows, recortado a lo que usa
# el servicio de akari. Queda en recursos\python y Tauri lo copia junto al .exe.
#
#   powershell -ExecutionPolicy Bypass -File scripts/python.ps1 [-Version 3.12.10] [-Arq amd64|arm64]
param([string]$Version = '3.12.10', [string]$Arq = 'amd64')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$destino = Join-Path $PSScriptRoot '..\recursos\python'
Get-ChildItem $destino -Exclude '.gitkeep' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force $destino | Out-Null

$zip = Join-Path ([IO.Path]::GetTempPath()) "python-$Version-embed-$Arq.zip"
Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$Version/python-$Version-embed-$Arq.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $destino -Force
Remove-Item $zip
$antes = (Get-ChildItem $destino -Recurse -File | Measure-Object Length -Sum).Sum

# Módulos con DLL propia que akari no usa (bases de datos, compresión, XML, asyncio…)
foreach ($f in '_sqlite3.pyd', 'sqlite3.dll', '_lzma.pyd', '_bz2.pyd', '_msi.pyd', '_elementtree.pyd', 'pyexpat.pyd',
                '_decimal.pyd', '_multiprocessing.pyd', '_overlapped.pyd', '_asyncio.pyd', 'winsound.pyd',
                '_zoneinfo.pyd', '_uuid.pyd', '_wmi.pyd') {
  Remove-Item (Join-Path $destino $f) -ErrorAction SilentlyContinue
}
# ...y paquetes de la biblioteca estándar (dentro de pythonXY.zip) que tampoco usa
$quitar = 'asyncio', 'unittest', 'pydoc_data', 'lib2to3', 'xmlrpc', 'sqlite3', 'curses', 'dbm', 'venv', 'ensurepip',
          'wsgiref', 'xml', 'tkinter', 'idlelib', 'turtledemo', 'msilib', 'test'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$biblioteca = Get-ChildItem $destino -Filter 'python*.zip' | Select-Object -First 1
$z = [IO.Compression.ZipFile]::Open($biblioteca.FullName, 'Update')
foreach ($e in @($z.Entries)) {
  $raiz = ($e.FullName -split '/')[0]
  if ($quitar -contains $raiz) { $e.Delete() }
}
$z.Dispose()
$despues = (Get-ChildItem $destino -Recurse -File | Measure-Object Length -Sum).Sum

# Lo que el servicio necesita tiene que seguir ahí
& (Join-Path $destino 'python.exe') -c "import ctypes, winreg, tomllib, ssl, http.server, urllib.request, json, concurrent.futures, colorsys, base64, unicodedata, encodings.idna; print('Python embebido listo:', __import__('sys').version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw 'El Python embebido no funciona' }
'Python embebido: {0:N1} MB → {1:N1} MB' -f ($antes / 1MB), ($despues / 1MB)
