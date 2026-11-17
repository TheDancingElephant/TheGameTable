"""Findet den Kampagnenordner (der Ordner mit kampagne.json) für Server, sl.py und Hilfsskripte.

Reihenfolge: --kampagne PFAD, Umgebungsvariable SPIELTISCH_KAMPAGNE, sonst vom
aktuellen Verzeichnis aufwärts suchen.
"""
import json
import os
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent
STANDARD = {"name": "Spieltisch", "port": 8777}


def ordner_finden(pfad=None):
    pfad = pfad or os.environ.get("SPIELTISCH_KAMPAGNE")
    if pfad:
        p = Path(pfad).expanduser().resolve()
        if not (p / "kampagne.json").is_file():
            sys.exit(f"Kein Kampagnenordner (kampagne.json fehlt): {p}")
        return p
    for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (p / "kampagne.json").is_file():
            return p
    sys.exit("Kein Kampagnenordner gefunden: --kampagne PFAD angeben, SPIELTISCH_KAMPAGNE setzen "
             "oder aus einem Ordner mit kampagne.json starten.")


def laden(pfad=None):
    """Gibt das Kampagnen-Objekt zurück: ordner, name, port, sl, daten, charaktere, protokoll, karten, notizen."""
    ordner = ordner_finden(pfad)
    cfg = dict(STANDARD)
    cfg.update(json.loads((ordner / "kampagne.json").read_text(encoding="utf-8")))
    port = int(os.environ.get("SPIELTISCH_PORT") or cfg["port"])
    sl = ordner / "sl"
    daten = ordner / "daten"
    return {
        "ordner": ordner, "name": cfg["name"], "port": port,
        "sl": sl, "daten": daten, "charaktere": daten / "charaktere", "protokoll": daten / "protokoll.jsonl",
        "karten": sl / "karten", "notizen": sl / "notizen", "quellen": sl / "quellen",
        "zustand": sl / "zustand.json", "schluessel": sl / "schluessel.txt",
        "autoNebel": bool(cfg.get("autoNebel", False)),  # automatisch aufdecken (Standard aus; pro Karte überschreibbar)
        "modi": bool(cfg.get("modi", True)),  # Modi (Hast, Größe …) auswerten; false = abgeschaltet
        "epTempo": str(cfg.get("epTempo", "mittel")).lower(),  # langsam | mittel | schnell
    }
