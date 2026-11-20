"""Baut den Startzustand der Beispielkampagne „Das Praxisjahr“ neu auf (für Entwickler).

    python beispiele/"Das Praxisjahr"/Material/aufbauen.py ARBEITSORDNER [--port 8799]

Legt unter ARBEITSORDNER eine Kampagne aus diesem Beispiel an (ohne Startzustand), startet ihren Server auf dem
angegebenen Port, importiert die Karten (Material/karten/*.karte.json bzw. Bilder in sl/karten), setzt Unterlagen,
verborgene Gegner und die Startszene, stoppt den Server wieder und schreibt den Startzustand (sl/zustand.json,
sl/karten/, sl/barrieren/) zurück ins Beispiel. Protokoll, Schlüssel und Logs werden nicht übernommen.
Die Kartenbilder selbst entstehen mit Material/karten/karten_bauen.py.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BEISPIEL = Path(__file__).resolve().parents[1]
TOOL = BEISPIEL.parents[1]
sys.path.insert(0, str(TOOL))

import sl_api  # noqa: E402

HANDOUTS = (("willkommen", "Willkommen in den Grovari-Höhlen"), ("orte-torstadt", "Torstadt – Orte"),
            ("orte-grovaristadt", "Grovaristadt – Orte"))
# Karten ohne Wände/Nebel: id, Name, Datei, Meter pro Feld, Zelle (px pro Feld im Bild)
EINFACH = (("torstadt", "Torstadt", "torstadt.png", 40, 50), ("grovaristadt", "Grovaristadt", "grovaristadt.png", 40, 50),
           ("hoehlen", "Die Grovari-Höhlen", "hoehlen.jpg", 1600, 40), ("tiefenburg", "Tiefenburg", "tiefenburg.jpg", 20, 50),
           ("illiatist", "Illiatist", "illiatist.jpg", 20, 50))
RATTE = dict(tp=5, rk=14, rkb=14, rkf=11, ref=5, wil=1, zaeh=3, hg="1/3", symbol="R", verborgen=True)
GEGNER = (("Schreckensratte", 9, 7, "rat1", RATTE), ("Schreckensratte", 15, 7, "rat2", RATTE),
          ("Schreckensratte", 14, 10, "rat3", RATTE),
          ("Rattenschwarm", 12, 15, "schwarm", dict(tp=16, rk=14, rkb=14, rkf=12, ref=5, wil=2, zaeh=4, hg="2", symbol="S",
                                                   verborgen=True)),
          ("Rattenmutter", 24, 25, "mutter", dict(tp=18, rk=15, rkb=12, rkf=13, ref=5, wil=1, zaeh=6, hg="1", symbol="M",
                                                 verborgen=True)),
          ("Schreckensratte", 22, 23, "rat4", RATTE), ("Schreckensratte", 23, 27, "rat5", RATTE))
START_SC = (("grimbar", 10, 6), ("nissa", 11, 6), ("ilvaen", 10, 7), ("zikko", 11, 7))  # Exerzierplatz Torstadt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arbeitsordner")
    ap.add_argument("--port", type=int, default=8799)
    a = ap.parse_args()
    wurzel = Path(a.arbeitsordner)
    wurzel.mkdir(parents=True, exist_ok=True)
    ziel = wurzel / BEISPIEL.name
    if ziel.exists():
        shutil.rmtree(ziel)
    print(sl_api.kampagne_neu(wurzel, BEISPIEL.name, port=a.port, beispiel=BEISPIEL.name))
    (ziel / "sl" / "zustand.json").unlink(missing_ok=True)  # alten Startzustand verwerfen, neu aufbauen
    shutil.rmtree(ziel / "sl" / "barrieren", ignore_errors=True)
    st = sl_api.Spieltisch(ziel, basis=ziel)
    print(st.server_starten())
    try:
        for hid, titel in HANDOUTS:
            text = (BEISPIEL / "Material" / "handouts" / f"{hid}.md").read_text(encoding="utf-8")
            st.handout(hid, text, titel=titel)
        for kid, name, datei, meter, zelle in EINFACH:
            import pymupdf
            pix = pymupdf.Pixmap(str(ziel / "sl" / "karten" / datei))
            st.befehl(op="karte-registrieren", karte={"id": kid, "name": name, "datei": datei, "w": float(pix.w),
                                                     "h": float(pix.h), "zelle": float(zelle), "ox": 0.0, "oy": 0.0,
                                                     "meterProFeld": float(meter), "waendeSperren": False,
                                                     "quelle": {"bild": datei}})
            st.nebel(True, "alles", karte=kid)
        st.bekannt("torstadt", legende="orte-torstadt")
        st.bekannt("grovaristadt", legende="orte-grovaristadt")
        st.bekannt("hoehlen")
        print(st.karte_import(datei="Material/karten/wachhaus.karte.json"))
        print(st.karte_import(datei="Material/karten/zisternen.karte.json", aktiv=True))
        for name, x, y, tid, werte in GEGNER:
            st.token("gegner", name, x, y, id=tid, **werte)
        st.token("nsc", "Tamla Grünschiefer", 26, 9, id="tamla", tp=6, symbol="T", verborgen=True)
        st.karte("torstadt")
        st.bekannt("zisternen", nein=True)  # beim Aktivieren automatisch „bekannt“ – die SC kennen sie noch nicht
        for cid, x, y in START_SC:
            st.sc_platzieren(cid, x, y)
        st.szene("Die Kaserne", untertitel="Abenteuer 1 – Ratten unter dem Wall")
        st.status("bereit")
    finally:
        stoppen(a.port)
    z = json.loads((ziel / "sl" / "zustand.json").read_text(encoding="utf-8"))
    z.update(version=1, letzteVerarbeitet=0, naechsteLogId=1)
    (BEISPIEL / "sl" / "zustand.json").write_text(json.dumps(z, ensure_ascii=False, indent=1), encoding="utf-8")
    for ordner in ("karten", "barrieren"):
        q, d = ziel / "sl" / ordner, BEISPIEL / "sl" / ordner
        d.mkdir(parents=True, exist_ok=True)
        for p in q.iterdir():
            if p.is_file():
                shutil.copy2(p, d / p.name)
    print(f"Startzustand nach {BEISPIEL / 'sl'} geschrieben")


def stoppen(port):
    """Server auf dem Port beenden (nur Windows/PowerShell; sonst bitte von Hand)."""
    befehl = (f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
              "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", befehl], check=False)
    time.sleep(1)


if __name__ == "__main__":
    main()
