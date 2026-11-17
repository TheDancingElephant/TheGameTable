@echo off
rem Sucht ein passendes Python (3.10 oder neuer) und setzt PY (python.exe) und PYW (pythonw.exe).
rem Reihenfolge: Umgebungsvariable SPIELTISCH_PYTHON, python-pfad.txt (von einrichten.bat), py-Launcher,
rem python im PATH, uebliche Installationsorte. Nichts gefunden: PY bleibt leer.
rem Aufruf aus anderen Skripten:  call "%~dp0python_finden.bat"
set "PY="
set "PYW="
set "_PP=%~dp0python_pruefen.py"

if defined SPIELTISCH_PYTHON call :probe "%SPIELTISCH_PYTHON%"
if defined PY goto :fertig
if exist "%~dp0python-pfad.txt" (
  set /p _GESPEICHERT=<"%~dp0python-pfad.txt"
  call :probe_gespeichert
)
if defined PY goto :fertig
where py >nul 2>nul && for /f "usebackq delims=" %%i in (`py -3 "%_PP%" 2^>nul`) do set "PY=%%i"
if defined PY goto :fertig
where python >nul 2>nul && for /f "usebackq delims=" %%i in (`python "%_PP%" 2^>nul`) do set "PY=%%i"
if defined PY goto :fertig
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%SystemDrive%\Python3*") do (
  if not defined PY if exist "%%~d\python.exe" call :probe "%%~d\python.exe"
)
:fertig
if defined PY (
  for %%f in ("%PY%") do if exist "%%~dpfpythonw.exe" (set "PYW=%%~dpfpythonw.exe") else (set "PYW=%PY%")
)
set "_PP="
set "_GESPEICHERT="
goto :eof

:probe_gespeichert
if not defined _GESPEICHERT goto :eof
if exist "%_GESPEICHERT%" call :probe "%_GESPEICHERT%"
goto :eof

:probe
for /f "usebackq delims=" %%i in (`call "%~1" "%_PP%" 2^>nul`) do set "PY=%%i"
goto :eof
