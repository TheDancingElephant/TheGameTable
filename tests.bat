@echo off
rem Alle Tests des Spieltischs (Pflicht vor jeder Live-Uebernahme). Optional: set SPIELTISCH_ALTSTAENDE=Ordner;Ordner
cd /d "%~dp0"
set PY=python
if exist python-pfad.txt set /p PY=<python-pfad.txt
"%PY%" -m unittest %*
