@echo off
rem Startet den Spieltisch-Server fuer eine Kampagne und oeffnet die Spieleransicht.
rem Aufruf:  start.bat "<Kampagnenordner>"     (ohne Parameter: aktueller Ordner / Umgebungsvariable SPIELTISCH_KAMPAGNE)
setlocal
call "%~dp0python_finden.bat"
if not defined PY (
  echo Python wurde nicht gefunden. Bitte zuerst einrichten.bat im Programmordner ausfuehren.
  pause
  exit /b 1
)
if not "%~1"=="" set "SPIELTISCH_KAMPAGNE=%~1"
set "PORT="
for /f %%p in ('call "%PY%" -c "import sys;sys.path.insert(0,sys.argv[1]);import kampagne;print(kampagne.laden()['port'])" "%~dp0."') do set "PORT=%%p"
if not defined PORT (
  echo Kein Kampagnenordner gefunden: start.bat "Kampagnenordner" angeben.
  pause
  exit /b 1
)
start "" http://localhost:%PORT%/
"%PY%" "%~dp0server.py"
