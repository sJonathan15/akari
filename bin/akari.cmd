@echo off
rem Lanzador de akari en Windows: akari ^<orden^>  (lo agrega al PATH install.ps1)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0akari.py" %*
) else (
  python "%~dp0akari.py" %*
)
