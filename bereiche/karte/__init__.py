"""Bereich Karte: Karten, Raster, Token, Bewegung und Wege, Barrieren, Nebel, Sicht, Täuschungen.

Öffentlich:
    Geometrie: pf_distanz, abstand, token_felder, zellen_rechteck, zellen_kreis, reichweite_felder
    Token: aktive, offen, sichtbar, finden, neue_id, belegt, setzen, aendern, entfernen, bewegen, sc_platzieren,
           sc_entfernen, taeuschung, taeuschung_fuer, sicht_partner, umgroessern
    Nebel/Sicht: sicht, nebel_aendern, auf_zu, abdecken, raster, nebel_modus, sichtmodus, auto_nebel_aktiv
    Karten/Barrieren: registrieren, aktivieren, bekannt, barrieren_befehl, weg
    Module: karten (Bild, Raster, Wege), barrieren (Wände/Türen, Sichtpolygon), kartenformat (Import/Export)
Fachereignisse, die dieser Bereich auslöst: token_bewegt (token, von), token_entfernt (token_id).
Reaktionen: token_bewegt → Auto-Nebel; charakter_modi, token_groesse → Tokengröße/Reichweite.
Die Shell stellt `kx.res` bereit: bild, wand, barr, barr_speichern, maske, maske_sichern, maske_verwerfen,
karte_neu_geladen.
"""
from . import barrieren, karten, kartenformat
from .befehle import aktivieren, barrieren_befehl, bekannt, erkennen as barrieren_erkennen, registrieren
from .geometrie import abstand, pf_distanz, reichweite_felder, token_felder, zellen_kreis, zellen_rechteck
from .nebel import (abdecken, aendern as nebel_aendern, auf_zu, auto_nebel_aktiv, modus as _modus, raster, sicht,
                    sicht_radius, sichtmodus)
from .token import (aendern, aktive, belegt, bewegen, entfernen, finden, mit_sichtpartnern, neue_id, offen,
                    sc_entfernen, sc_platzieren, setzen, sicht_partner, sichtbar, taeuschung, taeuschung_fuer,
                    umgroessern)


def nebel_modus(kx, b):
    """Nebelmodus sicht|raster einer Karte (erkennt Barrieren, falls noch keine da sind)."""
    _modus(kx, b, barrieren_erkennen)


def weg(kx, k, von, nach, erlaubt=None):
    """Weglänge in Feldern um Wände herum (None = kein Weg), auf der aktiven Karte."""
    return karten.weg_felder(kx.res.wand(kx.z["karteAktiv"]), k, von, nach, erlaubt=erlaubt)


__all__ = ["abdecken", "abstand", "aendern", "aktive", "aktivieren", "auf_zu", "auto_nebel_aktiv", "barrieren",
           "barrieren_befehl", "barrieren_erkennen", "bekannt", "belegt", "bewegen", "entfernen", "finden", "karten",
           "kartenformat", "mit_sichtpartnern", "nebel_aendern", "nebel_modus", "neue_id", "offen", "pf_distanz",
           "raster", "registrieren", "reichweite_felder", "sc_entfernen", "sc_platzieren", "setzen", "sicht",
           "sicht_partner", "sicht_radius", "sichtbar", "sichtmodus", "taeuschung", "taeuschung_fuer", "token_felder",
           "umgroessern", "weg", "zellen_kreis", "zellen_rechteck"]
