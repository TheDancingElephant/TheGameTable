@echo off
chcp 65001 >nul
rem Richtet den Spieltisch auf diesem Rechner ein (einmal nach dem Entpacken; erneut nach Python-Wechsel oder Umzug).
rem Optionen werden an einrichten.py weitergegeben, z. B.:  einrichten.bat --wurzel "E:\Kampagnen" --ja
setlocal
title Spieltisch einrichten
call "%~dp0python_finden.bat"
if not defined PY (
  echo.
  echo  Python wurde nicht gefunden ^(benoetigt: Python 3.10 oder neuer, empfohlen 3.12^).
  echo.
  echo  So installieren:
  echo    1. https://www.python.org/downloads/windows/ oeffnen, "Windows installer 64-bit" laden
  echo    2. Installer starten, unten den Haken "Add python.exe to PATH" setzen, "Install Now"
  echo  oder in einer Eingabeaufforderung:   winget install Python.Python.3.12
  echo.
  echo  Danach einrichten.bat erneut starten.
  echo.
  pause
  exit /b 1
)
"%PY%" "%~dp0einrichten.py" %*
set "ERG=%ERRORLEVEL%"
echo %* | "%SystemRoot%\System32\find.exe" /i "--ja" >nul || pause
exit /b %ERG%
