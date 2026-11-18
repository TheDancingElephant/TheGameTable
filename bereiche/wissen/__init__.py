"""Bereich Wissen (nur lesend): Regeldatenbank aus dem PRD (Grundregelwerk, Expertenregeln, Monsterhandbuch), Hausregeln der
Kampagne, Zauberkatalog (PRD + Spielmechanik aus daten/zauber.json).

Module:
    zauber_db     Zauberkatalog, Suche, Textausgaben (daten/zauber_prd.json, daten/zauber.json)
    regeln_db     Regelsuche (SQLite FTS5, regeln/regeln.sqlite), Hausregeln (sl/hausregeln.md)
    regeln_abruf  Abruf/Aktualisierung der Regeln vom PRD (Kommandozeile: python regeln_abruf.py …)
    regeln_md     HTML → Markdown
Öffentlich: zauber_katalog, zauber_finden, prd_finden, grad_fuer, klasse_der_liste, katalog_liste.
"""
from pathlib import Path

from . import zauber_db


def mechanik_datei(kx):
    """Spielmechanik der Zauber: kampagneneigene daten/zauber.json, sonst die des Programms."""
    eigene = Path(kx.einst["daten"]) / "zauber.json" if kx.einst.get("daten") else None
    return eigene if eigene and eigene.exists() else zauber_db.BASIS / "daten" / "zauber.json"


def zauber_katalog(kx):
    """name (klein) -> Katalogeintrag: alle PRD-Zauber, Mechanik aus zauber.json darüber."""
    return zauber_db.katalog(mechanik_datei(kx))


def zauber_finden(kx, name):
    return zauber_db.katalog_finden(zauber_katalog(kx), name)


def katalog_liste(kx):
    """Für /api/zauber: jeder Zauber einmal (ohne alte Alias-Namen und ohne PRD-Details), nach Grad und Name."""
    erg = [{k: v for k, v in z.items() if k != "prd"} for z in zauber_katalog(kx).values() if not z.get("aliasVon")]
    return sorted(erg, key=lambda d: (d.get("grad") or 0, d["name"]))


prd_finden = zauber_db.prd_finden
grad_fuer = zauber_db.grad_fuer
klasse_der_liste = zauber_db.klasse_der_liste
ALIASE = zauber_db.ALIASE

__all__ = ["ALIASE", "grad_fuer", "katalog_liste", "klasse_der_liste", "mechanik_datei", "prd_finden",
           "zauber_db", "zauber_finden", "zauber_katalog"]
