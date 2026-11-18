"""Gemeinsamer Kern aller Fachbereiche: Fehler, Würfel, Kontext eines Befehls.

Ein Kontext (`kx`) bündelt alles, was eine Fachfunktion lesen und ändern darf:

    kx.z        Spielstand (sl/zustand.json als Dict)
    kx.log      Protokoll (Liste, enthält schon die in diesem Befehl neuen Einträge)
    kx.chars    Charaktere (laden/speichern/alle, siehe speicher.Charakterspeicher)
    kx.einst    Kampagnen-Einstellungen (kampagne.laden: name, epTempo, autoNebel, modi …)
    kx.res      Karten-Ressourcen (bild, wand, barr, barr_speichern, maske, maske_sichern)
    kx.w        Würfel: kx.w(20) -> 1..20
    kx.protokoll(art, text, **extra)   Protokolleintrag (sichtbar am Tisch bzw. für den SL)
    kx.ereignis(name, **daten)         Fachereignis an die eingetragenen Reaktionen

Fachfunktionen berühren keine Dateien, keine Uhr und keinen Zufall außer über den Kontext.
"""
import random
import re


class Fehler(Exception):
    """Meldung an Spieler/SL (HTTP 400); der Befehl wird vollständig zurückgenommen."""


WURF_RE = re.compile(r"([+-]?)\s*(?:(\d*)\s*[wWdD]\s*(\d+)|(\d+))")


def zufall(seiten):
    return random.randint(1, seiten)


class FesterWuerfel:
    """Würfel für Tests: liefert die vorgegebenen Ergebnisse der Reihe nach (danach Fehler)."""

    def __init__(self, werte):
        self.werte = list(werte)

    def __call__(self, seiten):
        if not self.werte:
            raise AssertionError("FesterWuerfel: keine Werte mehr")
        w = self.werte.pop(0)
        if not 1 <= w <= seiten:
            raise AssertionError(f"FesterWuerfel: {w} passt nicht zu W{seiten}")
        return w


def wuerfeln(ausdruck, w=zufall):
    """'1W20+5', '2w6 + 1w4 - 1'. Gibt (summe, details, 'nat20'/'nat1'/None) zurück."""
    a = str(ausdruck).replace(" ", "")
    if not a or not re.fullmatch(r"([+-]?(\d*[wWdD]\d+|\d+))+", a):
        raise ValueError(f"Unverständlicher Wurf: {ausdruck!r}")
    summe, teile, besonders = 0, [], None
    for vz, anz, seiten, zahl in WURF_RE.findall(a):
        faktor = -1 if vz == "-" else 1
        if seiten:
            n, s = int(anz or 1), int(seiten)
            if n > 100 or s > 1000:
                raise ValueError("Zu viele Würfel")
            wuerfe = [w(s) for _ in range(n)]
            summe += faktor * sum(wuerfe)
            teile.append(f"{'-' if faktor < 0 else '+'}{n}W{s}[{','.join(map(str, wuerfe))}]")
            if s == 20 and n == 1:
                besonders = "nat20" if wuerfe[0] == 20 else "nat1" if wuerfe[0] == 1 else besonders
        else:
            summe += faktor * int(zahl)
            teile.append(f"{'-' if faktor < 0 else '+'}{zahl}")
    return summe, " ".join(teile).lstrip("+"), besonders


class Kontext:
    def __init__(self, z, log, chars, einst=None, res=None, w=zufall, uhr=lambda: "", reaktionen=None):
        self.z, self.log, self.chars = z, log, chars
        self.einst = einst or {}
        self.res = res
        self.w = w
        self.uhr = uhr
        self.reaktionen = reaktionen or {}
        self.neue = []                 # in diesem Befehl neue Protokolleinträge
        self.log_neu_schreiben = False  # Protokoll wurde gekürzt (Eintrag gelöscht): ganze Datei neu schreiben

    def protokoll(self, art, text, **extra):
        e = {"id": self.z["naechsteLogId"], "zeit": self.uhr(), "art": art, "text": text, **extra}
        self.z["naechsteLogId"] += 1
        self.log.append(e)
        self.neue.append(e)
        return e

    def ereignis(self, name, **daten):
        """Fachereignis: ruft alle Reaktionen auf, gibt deren Ergebnisse (ohne None) zurück."""
        return [r for f in self.reaktionen.get(name, []) if (r := f(self, **daten)) is not None]

    def wuerfeln(self, ausdruck):
        return wuerfeln(ausdruck, self.w)

    def w20(self):
        return self.w(20)
