"""Richtet den Spieltisch auf diesem Rechner ein (aufgerufen von einrichten.bat).

1. Python prüfen (3.10+), Pakete installieren (PyMuPDF, numpy, pywebview)
2. Kampagnen-Ordner festlegen und anlegen (Standard: ..\\Kampagnen neben dem Programmordner)
3. python-pfad.txt und zentrale.json schreiben
4. Verknüpfung „Spieltisch-Zentrale“ auf dem Desktop und im Programmordner anlegen
5. Pfade vorhandener Kampagnen im Kampagnen-Ordner reparieren (z. B. nach Umzug auf diesen Rechner)

Optionen:  --wurzel ORDNER  --ja (keine Rückfragen)  --ohne-pakete  --ohne-verknuepfung
           --verknuepfung-ordner ORDNER (statt Desktop, z. B. zum Testen)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent
PAKETE = [("pymupdf", "PyMuPDF"), ("numpy", "numpy"), ("webview", "pywebview")]
OHNE_FENSTER = 0x08000000 if sys.platform == "win32" else 0


def schritt(text):
    print(f"\n== {text}")


def python_pruefen():
    schritt("Python")
    print(f"   {sys.version.split()[0]}  {sys.executable}")
    if sys.version_info < (3, 10):
        sys.exit("   Python ist zu alt – bitte Python 3.12 installieren (https://www.python.org/downloads/windows/).")
    if sys.version_info >= (3, 14):
        print("   Hinweis: sehr neues Python – falls pywebview nicht installiert werden kann, öffnet die Zentrale "
              "im Browser statt im eigenen Fenster (Python 3.12 oder 3.13 empfohlen).")


def fehlende():
    aus = []
    for modul, paket in PAKETE:
        r = subprocess.run([sys.executable, "-c", f"import {modul}"], capture_output=True)
        if r.returncode:
            aus.append(paket)
    return aus


def pakete_installieren():
    schritt("Pakete (PyMuPDF, numpy, pywebview)")
    fehlt = fehlende()
    if not fehlt:
        print("   alle schon vorhanden")
        return True
    print(f"   installiere: {', '.join(fehlt)} …")
    if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"])
    basis = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    if subprocess.run(basis + fehlt).returncode:
        print("   … zweiter Versuch nur für diesen Benutzer (--user)")
        subprocess.run(basis + ["--user"] + fehlt)
    fehlt = fehlende()
    if not fehlt:
        print("   ok")
        return True
    for p in fehlt:
        if p == "pywebview":
            print("   pywebview fehlt: die Zentrale öffnet sich dann im Browser statt im eigenen Fenster.")
        else:
            print(f"   FEHLER: {p} konnte nicht installiert werden (Internetverbindung? "
                  f"Von Hand: \"{sys.executable}\" -m pip install {p})")
    return not [p for p in fehlt if p != "pywebview"]


def zentrale_json():
    datei = BASIS / "zentrale.json"
    try:
        return json.loads(datei.read_text(encoding="utf-8")) if datei.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def wurzel_festlegen(a):
    schritt("Kampagnen-Ordner")
    gespeichert = zentrale_json().get("wurzel")
    standard = Path(a.wurzel or gespeichert or BASIS.parent / "Kampagnen")
    w = standard
    if not a.wurzel and not a.ja:
        print("   Hier liegen später die Kampagnen (je ein Unterordner).")
        try:
            e = input(f"   Ordner [{standard}] (Enter = übernehmen): ").strip().strip('"')
        except EOFError:
            e = ""
        if e:
            w = Path(e)
    w = w.expanduser().resolve()
    w.mkdir(parents=True, exist_ok=True)
    cfg = zentrale_json()
    cfg["wurzel"] = str(w)
    cfg.setdefault("beimBeendenStoppen", True)
    (BASIS / "zentrale.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   {w}")
    return w


def verknuepfung(ziel_lnk, pyw):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ST_LNK);"
          "$s.TargetPath=$env:ST_ZIEL;$s.Arguments=$env:ST_ARG;$s.WorkingDirectory=$env:ST_DIR;"
          "$s.Description='Spieltisch – Kampagnen verwalten';$s.Save()")
    env = {**os.environ, "ST_LNK": str(ziel_lnk), "ST_ZIEL": str(pyw), "ST_ARG": f'"{BASIS / "zentrale.py"}"',
           "ST_DIR": str(BASIS)}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env,
                       capture_output=True, text=True, creationflags=OHNE_FENSTER)
    return r.returncode == 0 and Path(ziel_lnk).is_file()


def desktop():
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                       capture_output=True, text=True, creationflags=OHNE_FENSTER)
    d = Path((r.stdout or "").strip() or Path.home() / "Desktop")
    return d if d.is_dir() else None


def verknuepfungen(a):
    schritt("Verknüpfung „Spieltisch-Zentrale“")
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe") if py.with_name("pythonw.exe").is_file() else py
    orte = [BASIS]
    if not a.ohne_verknuepfung:
        d = Path(a.verknuepfung_ordner) if a.verknuepfung_ordner else desktop()
        if d:
            d.mkdir(parents=True, exist_ok=True)
            orte.append(d)
    for o in orte:
        lnk = o / "Spieltisch-Zentrale.lnk"
        print(f"   {'ok    ' if verknuepfung(lnk, pyw) else 'FEHLER'} {lnk}")
    print(f"   (Alternativ: zentrale.bat im Programmordner)")


def kampagnen_reparieren(w):
    import sl_api
    kampagnen = [p for p in sorted(w.iterdir()) if (p / "kampagne.json").is_file() and not p.name.startswith(("_", "."))]
    if not kampagnen:
        return
    schritt("Vorhandene Kampagnen: Pfade prüfen")
    for p in kampagnen:
        if sl_api.pfade_ok(p) is True:
            print(f"   ok         {p.name}")
            continue
        try:
            print(f"   repariert  {p.name}: {sl_api.pfade_reparieren(p).split(' – ')[0]}")
        except Exception as e:  # noqa: BLE001
            print(f"   FEHLER     {p.name}: {e}")


def main():
    for strom in (sys.stdout, sys.stderr):  # Umlaute auch bei umgeleiteter Ausgabe (cp1252) nicht abstürzen lassen
        try:
            strom.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Spieltisch einrichten")
    ap.add_argument("--wurzel", help="Kampagnen-Ordner (Standard: ..\\Kampagnen neben dem Programm)")
    ap.add_argument("--ja", action="store_true", help="keine Rückfragen (Standardwerte)")
    ap.add_argument("--ohne-pakete", action="store_true")
    ap.add_argument("--ohne-verknuepfung", action="store_true", help="keine Desktop-Verknüpfung")
    ap.add_argument("--verknuepfung-ordner", help="Verknüpfung hier statt auf dem Desktop anlegen")
    a = ap.parse_args()
    print(f"Spieltisch einrichten – Programmordner {BASIS}")
    python_pruefen()
    ok = True if a.ohne_pakete else pakete_installieren()
    (BASIS / "python-pfad.txt").write_text(sys.executable + "\n", encoding="utf-8")
    w = wurzel_festlegen(a)
    if sys.platform == "win32":
        verknuepfungen(a)
    sys.path.insert(0, str(BASIS))
    if ok:
        kampagnen_reparieren(w)
    schritt("Fertig" if ok else "Mit Fehlern beendet")
    if ok:
        print("   Start: Doppelklick auf „Spieltisch-Zentrale“ (Desktop), dann „+ Neue Kampagne“.")
        print("   Gespielt wird mit Claude: Claude Desktop/Code, neue Sitzung im Kampagnenordner (siehe ANLEITUNG.pdf).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
