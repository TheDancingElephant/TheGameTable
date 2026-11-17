@echo off
rem Startet die Spieltisch-Zentrale (Kampagnenverwaltung) ohne Konsolenfenster.
setlocal
call "%~dp0python_finden.bat"
if not defined PY (
  echo Python wurde nicht gefunden. Bitte zuerst einrichten.bat ausfuehren.
  pause
  exit /b 1
)
start "" "%PYW%" "%~dp0zentrale.py" %*
