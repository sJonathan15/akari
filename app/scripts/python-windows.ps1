# Baja el Python embebido oficial (python.org) que el instalador de Windows lleva dentro,
# así akari funciona sin que el usuario instale Python. Lo usa `npm run windows` y el CI.
#
#   powershell -ExecutionPolicy Bypass -File scripts/python-windows.ps1 [-Version 3.12.10] [-Arq amd64|arm64]
param([string]$Version = '3.12.10', [string]$Arq = 'amd64')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$destino = Join-Path $PSScriptRoot '..\build\python'
if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
New-Item -ItemType Directory -Force $destino | Out-Null

$zip = Join-Path ([IO.Path]::GetTempPath()) "python-$Version-embed-$Arq.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$Version/python-$Version-embed-$Arq.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $destino -Force
Remove-Item $zip

# El ._pth del Python embebido fija sys.path; bin\akari.py agrega la carpeta de akari por su
# cuenta, así que no hace falta tocarlo. Se comprueba que estén los módulos que usa el servicio.
& (Join-Path $destino 'python.exe') -c "import ctypes, winreg, tomllib, ssl, http.server, json; print('Python embebido listo:', __import__('sys').version)"
if ($LASTEXITCODE -ne 0) { throw 'El Python embebido no funciona' }
