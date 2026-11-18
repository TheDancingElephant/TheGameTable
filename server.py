"""Spieltisch-Server (gemeinsames Tool für mehrere Kampagnen).

Start:            python server.py [--kampagne PFAD]   (Kampagnenordner mit kampagne.json)
Spieler-Ansicht:  http://localhost:<Port aus kampagne.json>/
SL-Ansicht:       http://localhost:<Port>/?sl=<Schlüssel aus sl/schluessel.txt>

Der vollständige Spielstand liegt in sl/zustand.json. Die Spieler-API liefert
nur, was die Charaktere wahrnehmen können; Kartenbilder werden serverseitig
im Nebel maskiert, damit nichts Verborgenes im Browser landet.
"""
import json
import math
import os
import re
import secrets
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import argparse
import contextlib
import pickle

import kampagne
import speicher
from bereiche import REAKTIONEN, kern
from bereiche.kern import Fehler
from bereiche.karte import barrieren, karten
from bereiche import charakter as CH, kampf as KM, karte as KA, magie as MA, reaktion, wissen as WI
from bereiche.wissen import zauber_db as ZDB

_arg = argparse.ArgumentParser()
_arg.add_argument("--kampagne", help="Kampagnenordner (mit kampagne.json)")
KAMP = kampagne.laden(_arg.parse_known_args()[0].kampagne)
BASIS = kampagne.TOOL
WEB = BASIS / "web"
SL = KAMP["sl"]
DATEN = KAMP["daten"]
CHARAKTERE = KAMP["charaktere"]
PROTOKOLL = KAMP["protokoll"]
ZUSTAND = KAMP["zustand"]
SCHLUESSEL = KAMP["schluessel"]
PORT = KAMP["port"]


for d in (SL, DATEN, CHARAKTERE, SL / "karten", SL / "notizen", SL / "quellen"):
    d.mkdir(parents=True, exist_ok=True)
if not SCHLUESSEL.exists():
    SCHLUESSEL.write_text(secrets.token_urlsafe(12), encoding="utf-8")
SL_KEY = SCHLUESSEL.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------- Zustand

def leerer_zustand():
    return {
        "version": 1,
        "szene": {"titel": "Vor dem Abenteuer", "untertitel": ""},
        "karteAktiv": None,
        "karten": {},
        "tokens": {},
        "initiative": {"aktiv": False, "runde": 0, "index": 0, "eintraege": []},
        "slStatus": "bereit",
        "letzteVerarbeitet": 0,
        "naechsteLogId": 1,
    }


_LOKAL = threading.local()


def kx():
    """Kontext des laufenden Befehls bzw. der laufenden Leseanfrage."""
    k = getattr(_LOKAL, "kx", None)
    if k is None:
        raise RuntimeError("Kein Befehlskontext (SPIEL.ausfuehren / SPIEL.lesen)")
    return k


class Spiel:
    def __init__(self):
        self.lock = threading.Condition()
        self.z = json.loads(ZUSTAND.read_text(encoding="utf-8")) if ZUSTAND.exists() else leerer_zustand()
        self.log = []
        if PROTOKOLL.exists():
            for zeile in PROTOKOLL.read_text(encoding="utf-8").splitlines():
                if zeile.strip():
                    self.log.append(json.loads(zeile))
        if self.log:
            self.z["naechsteLogId"] = max(self.z["naechsteLogId"], self.log[-1]["id"] + 1)
        self.bilder = {}      # karten-id -> numpy-Bild (Original)
        self.waende = {}      # karten-id -> Wandraster (für Bewegungsprüfung)
        self.jpeg_cache = {}  # (karten-id, nebel-version, ganz) -> bytes
        self.barr_cache = {}  # karten-id -> [Dateistempel, Barrieren-Dict, (seg, seite)]
        self.masken = {}      # karten-id -> Bool-Maske des aufgedeckten Bereichs (Sichtpolygon-Modus)
        self.barr_offen = {}  # karten-id -> Barrieren, die der laufende Befehl ändert (geschrieben bei Erfolg)

    # -- Befehle als Einheit
    def kontext(self):
        return kern.Kontext(self.z, self.log, speicher.Charakterspeicher(CHARAKTERE), KAMP, self, kern.zufall,
                            lambda: time.strftime("%H:%M"), REAKTIONEN)

    @contextlib.contextmanager
    def lesen(self):
        """Leseanfrage: eigener Kontext, nichts wird gespeichert."""
        alt = getattr(_LOKAL, "kx", None)
        _LOKAL.kx = self.kontext()
        try:
            yield _LOKAL.kx
        finally:
            _LOKAL.kx = alt

    def ausfuehren(self, f, *args):
        """Führt einen Befehl als Einheit aus (unter der Sperre): bei einem Fehler wird der Spielstand aus der
        Sicherung zurückgeholt und nichts geschrieben; sonst Protokoll, Charaktere, Barrieren, Spielstand speichern."""
        sicherung = pickle.dumps(self.z, pickle.HIGHEST_PROTOCOL)
        log_alt = list(self.log)
        k = self.kontext()
        alt = getattr(_LOKAL, "kx", None)
        _LOKAL.kx = k
        self.barr_offen = {}
        try:
            ergebnis = f(*args)
            tot_abgleich(self.z)
        except BaseException:
            self.z = pickle.loads(sicherung)
            self.log[:] = log_alt
            self.masken.clear()
            self.barr_cache.clear()
            self.barr_offen = {}
            raise
        finally:
            _LOKAL.kx = alt
        self.uebernehmen(k)
        return ergebnis

    def uebernehmen(self, k):
        for kid, daten in self.barr_offen.items():
            barrieren.speichern(SL, kid, daten)
            self.barr_cache.pop(kid, None)
        self.barr_offen = {}
        k.chars.schreiben()
        if k.log_neu_schreiben:
            PROTOKOLL.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.log), encoding="utf-8")
        elif k.neue:
            with PROTOKOLL.open("a", encoding="utf-8") as f:
                for e in k.neue:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        self.z["version"] += 1
        self.speichern()
        self.lock.notify_all()

    # -- Persistenz
    def speichern(self):
        tmp = ZUSTAND.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.z, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ZUSTAND)

    def eintragen(self, art, text, **extra):
        return kx().protokoll(art, text, **extra)

    # -- Karten
    def karte(self, kid=None):
        kid = kid or self.z["karteAktiv"]
        return self.z["karten"].get(kid) if kid else None

    def bild(self, kid):
        if kid not in self.bilder:
            self.bilder[kid] = karten.bild_laden(str(SL / "karten" / self.z["karten"][kid]["datei"]))
        return self.bilder[kid]

    def wand(self, kid):
        pfad = SL / "karten" / self.z["karten"][kid]["datei"]
        stempel = pfad.stat().st_mtime if pfad.exists() else 0
        if kid in self.waende and self.waende[kid][0] != stempel:  # Kartenbild geändert: neu laden
            del self.waende[kid]
            self.bilder.pop(kid, None)
            self.jpeg_cache = {s: v for s, v in self.jpeg_cache.items() if s[0] != kid}
        if kid not in self.waende:
            self.waende[kid] = (stempel, karten.wandkarte(self.bild(kid)))
        return self.waende[kid][1]

    def karten_jpeg(self, kid, ganz):
        k = self.z["karten"][kid]
        schluessel = (kid, k.get("nebelVersion", 0), ganz)
        if schluessel not in self.jpeg_cache:
            for alt in [s for s in self.jpeg_cache if s[0] == kid and s[2] == ganz]:
                del self.jpeg_cache[alt]
            offen = [tuple(c) for c in k.get("aufgedeckt", [])]
            pm = None
            if sichtmodus(k) and not ganz:
                bild = self.bild(kid)
                pm = barrieren.maske_in_pixel(self.maske(kid), bild.shape[1], bild.shape[0])
            self.jpeg_cache[schluessel] = karten.maskiert_jpeg(self.bild(kid), k, offen, ganz=ganz, pixelmaske=pm)
        return self.jpeg_cache[schluessel]

    # -- Barrieren (Wände/Türen) und Aufdeck-Maske (Sichtpolygon-Modus), nur serverseitig
    def barr(self, kid, blockierend=False):
        """Barrieren-Dict der Karte (sl/barrieren/<kid>.json, bei Dateiänderung neu geladen); None, wenn es keines gibt.
        Mit blockierend=True stattdessen (seg, seite) der aktuell sichtblockierenden Strecken."""
        if kid in self.barr_offen:
            d = self.barr_offen[kid]
            return barrieren.blockierend(d) if blockierend else d
        p = barrieren.pfad(SL, kid)
        stempel = p.stat().st_mtime if p.exists() else None
        c = self.barr_cache.get(kid)
        if c is None or c[0] != stempel:
            daten = barrieren.laden(SL, kid) if stempel else None
            c = [stempel, daten, barrieren.blockierend(daten) if daten else None]
            self.barr_cache[kid] = c
        return c[2] if blockierend else c[1]

    def barr_speichern(self, kid, daten):
        self.barr_offen[kid] = daten
        self.barr_cache.pop(kid, None)

    def maske(self, kid):
        """Aufdeck-Maske (Bool, MASKE_B px je Block); wird bei Bedarf aus dem Spielstand oder den aufgedeckten Feldern aufgebaut."""
        if kid not in self.masken:
            k = self.z["karten"][kid]
            if k.get("nebelMaske"):
                m = barrieren.maske_dekodieren(k["nebelMaske"])
            else:
                m = barrieren.maske_neu(int(k["w"]), int(k["h"]))
                for cx, cy in k.get("aufgedeckt", []):
                    barrieren.maske_rechteck(m, (k["ox"] + cx * k["zelle"], k["oy"] + cy * k["zelle"],
                                                 k["ox"] + (cx + 1) * k["zelle"], k["oy"] + (cy + 1) * k["zelle"]), True)
            self.masken[kid] = m
        return self.masken[kid]

    def maske_sichern(self, kid):
        self.z["karten"][kid]["nebelMaske"] = barrieren.maske_kodieren(self.masken[kid])

    def maske_verwerfen(self, kid):
        self.masken.pop(kid, None)

    def karte_neu_geladen(self, kid):
        self.bilder.pop(kid, None)
        self.waende.pop(kid, None)

    def offen_set(self, k):
        return KA.offen(k)

    # -- Sicht für Spieler
    def token_sichtbar(self, t, offen):
        return KA.sichtbar(t, offen)

    def taeuschung_fuer(self, t):
        return KA.taeuschung_fuer(kx(), t)

    def spieler_sicht(self):
        z = self.z
        k = self.karte()
        offen = self.offen_set(k) if k else set()
        tokens = []
        faelschungen = {}  # tokenId -> angezeigter Name (für die Initiativliste)
        for t in z["tokens"].values():
            if k is None or t.get("karte") != z["karteAktiv"]:
                continue
            td = self.taeuschung_fuer(t)
            if td is None:
                if not self.token_sichtbar(t, offen):
                    continue
                o = {key: t.get(key) for key in ("id", "name", "art", "x", "y", "groesse", "farbe", "zustaende", "charId", "symbol", "reichweite")}
            else:
                if not td.get("sichtbar") and not self.token_sichtbar(t, offen):
                    continue
                o = {key: td.get(key, t.get(key)) for key in ("name", "x", "y", "groesse", "farbe", "symbol")}
                o.update({key: t.get(key) for key in ("id", "art", "zustaende", "charId")})  # charId bleibt (Kartenlogik)
                faelschungen[t["id"]] = o["name"]
                if td.get("art") in ("sc", "gegner", "nsc"):
                    o["art"] = td["art"]
            if td is not None:
                pass  # keine TP/Gesundheit der echten Gestalt preisgeben
            elif t["art"] == "sc":
                o["tp"], o["tpMax"] = t.get("tp"), t.get("tpMax")
            else:
                o["gesundheit"] = gesundheit_text(t)
            tokens.append(o)
        ini = dict(z["initiative"])
        ini["eintraege"] = [
            {"name": faelschungen.get(e.get("tokenId"), e["name"]), "wert": e["wert"], "tokenId": e.get("tokenId"), "aktuell": i == ini["index"]}
            for i, e in enumerate(z["initiative"]["eintraege"])
            if not e.get("verborgen")
        ]
        aktuell = z["initiative"]["eintraege"][ini["index"]] if z["initiative"]["eintraege"] else None
        ini["amZug"] = (aktuell["name"] if aktuell and not aktuell.get("verborgen") else "???") if aktuell else None
        karte = None
        if k:
            karte = {key: k[key] for key in ("id", "name", "w", "h", "zelle", "ox", "oy")}
            karte["meterProFeld"] = k.get("meterProFeld", 1.5)
            karte["nebelVersion"] = k.get("nebelVersion", 0)
            karte["aufgedeckt"] = k.get("aufgedeckt", [])
        return {
            "version": z["version"],
            "kampagne": KAMP["name"],
            "szene": z["szene"],
            "karte": karte,
            "tokens": tokens,
            "initiative": ini,
            "zug": zug_info(),
            "angriffAusserhalb": z.get("angriffAusserhalb", False),
            "slStatus": z["slStatus"],
            "protokoll": [e for e in self.log if not e.get("verborgen")][-300:],
            "zustaende": ZUSTAENDE,
            "unterlagen": self.unterlagen(),
            "ausruestung": ausruestung(),
        }

    def unterlagen(self):
        """Was die Spieler jederzeit nachschlagen dürfen: bekannte Karten, Handouts, Gruppennotizen."""
        z = self.z
        karten = [{"id": kid, "name": k["name"], "nebelVersion": k.get("nebelVersion", 0), "w": k["w"], "h": k["h"],
                   "aktiv": kid == z["karteAktiv"], "legende": k.get("legende")}
                  for kid, k in z["karten"].items() if k.get("bekannt") or kid == z["karteAktiv"]]
        return {"karten": karten, "handouts": z.get("handouts", []), "notizen": z.get("gruppennotizen", "")}

    def sl_sicht(self):
        s = self.spieler_sicht()
        z = self.z
        k = self.karte()
        s["tokens"] = [t for t in z["tokens"].values() if k and t.get("karte") == z["karteAktiv"]]
        s["initiative"] = dict(z["initiative"])
        s["protokoll"] = self.log[-300:]
        s["karten"] = {kid: {"name": kk["name"]} for kid, kk in z["karten"].items()}
        s["sl"] = True
        return s


SPIEL = Spiel()


# ---------------------------------------------------------------- Übergang: Bereich Kampf (bereiche/kampf)
ZUSTAENDE, UNFAEHIG, gesundheit_text, tot_abgleich = KM.ZUSTAENDE, KM.UNFAEHIG, KM.gesundheit_text, KM.tot_abgleich


def zug_info():
    return KM.zug_info(kx())


def darf_handeln(t):
    KM.darf_handeln(kx(), t)


# ---------------------------------------------------------------- Übergang: Bereich Karte (bereiche/karte)
pf_distanz, token_felder, abstand = KA.pf_distanz, KA.token_felder, KA.abstand
zellen_rechteck, zellen_kreis = KA.zellen_rechteck, KA.zellen_kreis
reichweite_felder_t, sichtmodus, neue_id = KA.reichweite_felder, KA.sichtmodus, KA.neue_id


def token_finden(tid):
    return KA.finden(kx(), tid)


def auto_nebel_aktiv(k):
    return KA.auto_nebel_aktiv(kx(), k)


def nebel_sicht(tokens, k=None, kid=None):
    return KA.sicht(kx(), tokens, k, kid)


# ---------------------------------------------------------------- Übergang: Bereich Charakter (bereiche/charakter)
MODI, AUF = CH.MODI, CH.AUF
waffe_info, attr_mod = CH.waffe_info, CH.attr_mod


def meter_pro_feld():
    return CH.meter_pro_feld(kx())


def wirksam(c):
    return CH.wirksam(kx(), c)


def sc_char(t):
    return CH.von_token(kx(), t)


def char_laden(cid):
    return CH.laden(kx(), cid)


def char_speichern(c):
    CH.speichern(kx(), c)


def char_tp_sync(t):
    CH.tp_uebernehmen(kx(), t)


def sc_token(cid):
    return CH.sc_token(kx(), cid)


def ep_info(c):
    return CH.ep_info(kx(), c)


# ---------------------------------------------------------------- Würfel

def wuerfeln(ausdruck):
    """'1W20+5', '2w6 + 1w4 - 1'. Gibt (summe, details, nat20/nat1-Info) zurück."""
    return kern.wuerfeln(ausdruck, kx().w)


# ---------------------------------------------------------------- Felder & Nebel


# ---------------------------------------------------------------- Kampf: Waffen, Züge, Angriffe


# ---------------------------------------------------------------- Erfahrung & Stufenaufstieg

# Mittlere Aufstiegsgeschwindigkeit (PF1): EP, ab denen eine Stufe erreicht ist
# Erfahrungspunkte je Stufe (PF1), Index = Stufe; Aufstiegsgeschwindigkeit je Kampagne (kampagne.json: "epTempo")
# EP-Belohnung je Herausforderungsgrad

# ---------------------------------------------------------------- Zauber


# ---------------------------------------------------------------- Klassenfähigkeiten


# ---------------------------------------------------------------- Befehle


def sl_befehl(b):
    """Alle Spielleiter-Aktionen. Rückgabe: dict für die Antwort."""
    z = SPIEL.z
    op = b.get("op")
    if op == "erzaehle":
        SPIEL.eintragen("sl", b["text"], titel=b.get("titel"))
        z["slStatus"] = "bereit"
    elif op == "eintrag-loeschen":
        SPIEL.log[:] = [e for e in SPIEL.log if e["id"] != int(b["id"])]
        kx().log_neu_schreiben = True
    elif op == "notiz":  # nur SL, nicht im Spielerprotokoll
        SPIEL.eintragen("sl-notiz", b["text"], verborgen=True)
    elif op == "status":
        z["slStatus"] = b["status"]
    elif op == "szene":
        z["szene"] = {"titel": b.get("titel", ""), "untertitel": b.get("untertitel", "")}
        SPIEL.eintragen("system", f"Szene: {z['szene']['titel']}")
    elif op == "karte-registrieren":
        KA.registrieren(kx(), b["karte"])
    elif op == "karte-aktiv":
        KA.aktivieren(kx(), b["id"])
    elif op == "karte-bekannt":  # Karte in den Unterlagen der Spieler anzeigen (oder wieder entfernen)
        KA.bekannt(kx(), b)
    elif op == "handout":  # Text-Handout anlegen oder ersetzen (gleiche id)
        hs = z.setdefault("handouts", [])
        h = {"id": b["id"], "titel": b.get("titel") or b["id"], "text": b["text"]}
        alt = next((i for i, x in enumerate(hs) if x["id"] == b["id"]), None)
        if alt is None:
            hs.append(h)
            SPIEL.eintragen("system", f"Neue Unterlage: {h['titel']}")
        else:
            hs[alt] = h
    elif op == "handout-weg":
        z["handouts"] = [x for x in z.get("handouts", []) if x["id"] != b["id"]]
    elif op == "raster":
        KA.raster(kx(), b)
    elif op == "sicht":  # Sichtlinien-Aufdecken jetzt für alle SC auf der Karte (unabhängig vom Schalter)
        return {"aufgedeckt": KA.sicht(kx(), list(z["tokens"].values()), KA.aktive(kx(), b.get("karte")), b.get("karte"))}
    elif op.startswith("barriere") or op == "tuer":
        return KA.barrieren_befehl(kx(), op, b)
    elif op == "nebel-modus":  # stufenloser Sichtpolygon-Nebel (sicht) oder Feldraster (raster), pro Karte
        KA.nebel_modus(kx(), b)
    elif op in ("aufdecken", "verdecken"):
        KA.auf_zu(kx(), op, b)
    elif op in ("kasse", "item-neu", "item-aendern", "item-weg"):
        return ausruestung_aendern(b)
    elif op in ("buch-add", "buch-weg"):
        return MA.zauberbuch(kx(), {**b, "op": "add" if op == "buch-add" else "weg"})
    elif op == "abdecken":
        KA.abdecken(kx(), b)
    elif op == "token-setzen":
        return KA.setzen(kx(), b["token"])
    elif op == "token-aendern":
        KA.aendern(kx(), b["id"], b["werte"])
    elif op == "taeuschung":  # Illusionsansicht je SC (siehe README „Illusionen“)
        return KA.taeuschung(kx(), b)
    elif op == "token-entfernen":
        KA.entfernen(kx(), b["id"])
    elif op == "bewegen":
        return KM.sl_bewegen(kx(), b["id"], b["x"], b["y"])
    elif op == "tp":
        KM.tp_sl(kx(), b["id"], b["delta"])
    elif op == "zustand":
        KM.zustand_sl(kx(), b["id"], b["name"], b.get("an", True))
    elif op == "initiative":
        KM.initiative_befehl(kx(), b)
    elif op == "angriff":  # Angriff eines Gegners/NSC, ohne Regelprüfung (der SL entscheidet)
        KM.sl_angriff(kx(), b)
    elif op == "ep":  # Erfahrung vergeben: aus HG der Gegner oder fester Betrag, geteilt durch die Empfänger
        return CH.ep_befehl(kx(), b)
    elif op in ("aufstieg-fertig", "aufstieg-zurueck", "aufstieg-zeigen", "aufstieg-abbrechen"):
        return CH.aufstieg_sl(kx(), op, b)
    elif op == "char-setzen":  # einzelne Werte eines Charakters ändern, Pfad mit Punkten (z. B. rw.REF)
        CH.char_setzen(kx(), b["charId"], b["werte"])
    elif op == "rast":  # Zauberplätze zurücksetzen (alle oder ein Charakter)
        MA.rast(kx(), b.get("charId"))
    elif op == "zug":  # Aktionen des aktuellen Zuges anpassen
        KM.zug_aendern(kx(), b["werte"])
    elif op in ("modus", "modus-ende"):
        return CH.modus_befehl(kx(), op, b)
    elif op == "modus-zeit":
        return {"abgelaufen": CH.modi_zeit(kx(), int(b["runden"]))}
    elif op == "modi":
        return {"zeilen": CH.modi_liste(kx())}
    elif op == "wurf":
        summe, detail, besonders = wuerfeln(b["ausdruck"])
        verborgen = b.get("verborgen", False)
        SPIEL.eintragen("wurf", b.get("grund", ""), wer=b.get("wer", "SL"), ausdruck=b["ausdruck"],
                        ergebnis=summe, detail=detail, besonders=besonders, verborgen=verborgen)
        return {"ergebnis": summe, "detail": detail, "besonders": besonders}
    elif op == "verarbeitet":
        z["letzteVerarbeitet"] = int(b["bis"])
    else:
        raise Fehler(f"Unbekannter Befehl {op!r}")
    return {}


def weckende_ereignisse():
    """Gibt es unverarbeitete Ereignisse, die den SL wecken (Spieleraktion, Zugende …)?"""
    lv = SPIEL.z["letzteVerarbeitet"]
    for e in reversed(SPIEL.log):
        if e["id"] <= lv:
            return False
        if e.get("wecken", e["art"] == "spieler"):
            return True
    return False


# ---------------------------------------------------------------- Modi (Hast, Größe, Reichweite …)


def alle_charaktere():
    liste = [wirksam(c) for c in kx().chars.alle()]
    for c in liste:  # Fernkampf/Reichweite ergänzen, wo nicht angegeben
        for a in c.get("angriffe", []):
            info = waffe_info(a)
            a.setdefault("fernkampf", info["fernkampf"])
            if info["inkrement"] and not a.get("inkrement"):
                a["inkrement"] = info["inkrement"]
            a["beruehrung"] = info["beruehrung"]
        MA.ansicht(kx(), c)  # berechnete Zauberwerte für die Oberfläche (werden nicht gespeichert)
        c["_ep"] = ep_info(c)
    return liste


# ---------------------------------------------------------------- Ausrüstung / Gruppenkasse

MUENZEN = ("kp", "sp", "gp", "pp")


def ausruestung():
    """Gruppenkasse und Gegenstände je Träger (Charakter-ID oder 'gruppe'); beim ersten Aufruf aus den Charakterbögen übernommen."""
    z = SPIEL.z
    a = z.get("ausruestung")
    if a is None:
        a = {"kasse": {m: 0 for m in MUENZEN}, "gegenstaende": [], "naechsteId": 1}
        for c in alle_charaktere():
            for zeile in (c.get("ausruestung") or "").splitlines():
                zeile = zeile.strip()
                if zeile:
                    a["gegenstaende"].append({"id": a["naechsteId"], "name": zeile, "anzahl": 1, "traeger": c["id"], "ort": "dabei", "notiz": ""})
                    a["naechsteId"] += 1
        z["ausruestung"] = a
    return a


def ausruestung_aendern(b):
    """Spieler und SL: kasse (delta oder setzen), item-neu, item-aendern, item-weg."""
    a = ausruestung()
    op = b.get("op")
    if op == "kasse":
        for m in MUENZEN:
            if m in (b.get("delta") or {}):
                neu = a["kasse"][m] + int(b["delta"][m])
                if neu < 0:
                    raise Fehler(f"Nicht genug {m.upper()} in der Kasse")
                a["kasse"][m] = neu
            if m in (b.get("setzen") or {}):
                a["kasse"][m] = max(0, int(b["setzen"][m]))
        teile = ", ".join(f"{int(v):+d} {m}" for m, v in (b.get("delta") or {}).items() if int(v))
        SPIEL.eintragen("system", f"Gruppenkasse: {teile or 'geändert'} ({b.get('grund') or 'ohne Grund'})")
    elif op == "item-neu":
        name = (b.get("name") or "").strip()
        if not name:
            raise Fehler("Name fehlt")
        i = a["naechsteId"]
        a["naechsteId"] += 1
        a["gegenstaende"].append({"id": i, "name": name[:120], "anzahl": max(1, int(b.get("anzahl") or 1)),
                                  "traeger": b.get("traeger") or "gruppe", "ort": (b.get("ort") or "dabei")[:40],
                                  "notiz": (b.get("notiz") or "")[:300]})
        return {"id": i}
    elif op in ("item-aendern", "item-weg"):
        it = next((x for x in a["gegenstaende"] if x["id"] == int(b["id"])), None)
        if it is None:
            raise Fehler("Gegenstand nicht gefunden")
        if op == "item-weg":
            a["gegenstaende"].remove(it)
        else:
            for k in ("name", "traeger", "ort", "notiz"):
                if k in b:
                    it[k] = str(b[k])[:300]
            if "anzahl" in b:
                it["anzahl"] = max(1, int(b["anzahl"]))
    else:
        raise Fehler("Unbekannte Ausrüstungsaktion")
    return {}


def post_befehl(pfad, b):
    """Alle schreibenden Anfragen (läuft in SPIEL.ausfuehren)."""
    if pfad == "/api/sl/befehl":
        ergebnis = {}
        for befehl in (b if isinstance(b, list) else [b]):
            ergebnis = sl_befehl(befehl)
        return ergebnis
    if pfad == "/api/charakter":
        return CH.charakter_speichern(kx(), b, secrets.token_hex(3))
    if pfad == "/api/charakter-loeschen":
        CH.charakter_loeschen(kx(), b["id"])
        return {}
    return spieler_befehl(pfad, b)


def spieler_befehl(pfad, b):
    z = SPIEL.z
    if pfad == "/api/ausruestung":
        return ausruestung_aendern(b)
    if pfad == "/api/zauberbuch":
        return MA.zauberbuch(kx(), b)
    if pfad == "/api/zauber-vorbereiten":
        return MA.vorbereiten(kx(), b)
    if pfad == "/api/aktion":
        text = b.get("text", "").strip()
        if not text:
            raise Fehler("Leere Aktion")
        # Im laufenden Kampf sind Ansagen Teil des Zuges; der SL liest sie am Zugende
        im_zug = z["initiative"].get("aktiv") and z["initiative"].get("phase") == "laeuft"
        SPIEL.eintragen("spieler", text, wer=b.get("wer") or "Gruppe", wecken=not im_zug)
        if not im_zug:
            z["slStatus"] = "wartet"
    elif pfad == "/api/wurf":
        ini = z["initiative"]
        if b.get("initiative") and ini["aktiv"] and any(e["name"] == b.get("wer") for e in ini["eintraege"]):
            raise Fehler(f"{b.get('wer')} hat schon Initiative gewürfelt")
        summe, detail, besonders = wuerfeln(b["ausdruck"])
        # Proben außerhalb eines Kampfes wecken den SL (der Nachlauf von `warte` sammelt mehrere Würfe ein)
        wecken = not ini.get("aktiv")
        e = SPIEL.eintragen("wurf", b.get("grund", ""), wer=b.get("wer") or "Gruppe", ausdruck=b["ausdruck"],
                            ergebnis=summe, detail=detail, besonders=besonders, wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"
        if b.get("initiative") and ini["aktiv"]:
            KM.wurf_initiative(kx(), b.get("wer"), b.get("charId"), summe)
        return {"ergebnis": summe, "detail": detail, "besonders": besonders, "id": e["id"]}
    elif pfad == "/api/angriff":
        KM.sc_angriff(kx(), b)
    elif pfad == "/api/sturmangriff":
        KM.sturmangriff(kx(), b)
    elif pfad == "/api/zaubern":
        MA.wirken_spieler(kx(), b)
    elif pfad == "/api/faehigkeit":
        MA.faehigkeit_spieler(kx(), b)
    elif pfad in ("/api/aufstieg-plan", "/api/aufstieg-tp", "/api/aufstieg-senden"):
        return CH.aufstieg_spieler(kx(), pfad.rsplit("-", 1)[-1], b)
    elif pfad == "/api/zug-beenden":
        KM.zug_beenden(kx(), b["id"])
    elif pfad == "/api/aktion-verbrauchen":
        KM.aktion_nutzen(kx(), b["id"], b["aktion"], b.get("wofuer"))
    elif pfad == "/api/bewegen":
        KM.bewegen_spieler(kx(), b["id"], b["x"], b["y"])
    elif pfad == "/api/anstupsen":  # Spieler bitten den Spielleiter, zu handeln (weckt `sl.py warte`)
        SPIEL.eintragen("system", "Die Spieler bitten den Spielleiter zu handeln.", wecken=True)
        if z["slStatus"] == "bereit":
            z["slStatus"] = "wartet"
    elif pfad == "/api/zeigen":
        SPIEL.eintragen("zeigen", f"{b.get('wer') or 'Gruppe'} zeigt auf Feld ({b['x']},{b['y']})",
                        wer=b.get("wer") or "Gruppe", feld=[b["x"], b["y"]])
    elif pfad == "/api/sc-tp":
        KM.tp_spieler(kx(), b["id"], b["delta"])
    elif pfad == "/api/sc-zustand":
        KM.zustand_spieler(kx(), b["id"], b["name"])
    elif pfad == "/api/sc-platzieren":
        KA.sc_platzieren(kx(), b["charId"], b["x"], b["y"])
    elif pfad == "/api/gruppennotizen":
        z["gruppennotizen"] = str(b.get("text", ""))[:50000]
    elif pfad == "/api/sc-entfernen":
        KA.sc_entfernen(kx(), b["charId"])
    else:
        raise Fehler("Unbekannter Pfad")
    return {}


# ---------------------------------------------------------------- HTTP

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def antwort(self, code, daten, typ="application/json; charset=utf-8", extra=None):
        if not isinstance(daten, (bytes, bytearray)):
            daten = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(daten)

    def ist_sl(self, q):
        return (self.headers.get("X-SL") or q.get("sl", [""])[0]) == SL_KEY

    def koerper(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            with SPIEL.lesen():
                return self._get(u, q)
        except Exception as e:  # noqa: BLE001
            return self.antwort(500, {"fehler": str(e)})

    def _get(self, u, q):
        if True:
            if u.path == "/api/stand":
                sl = self.ist_sl(q)
                seit = int(q.get("seit", ["0"])[0])
                with SPIEL.lock:
                    ende = time.time() + 25
                    while SPIEL.z["version"] <= seit and time.time() < ende:
                        SPIEL.lock.wait(ende - time.time())
                    daten = SPIEL.sl_sicht() if sl else SPIEL.spieler_sicht()
                return self.antwort(200, daten)
            m = re.fullmatch(r"/api/karte/([\w-]+)\.jpg", u.path)
            if m:
                with SPIEL.lock:
                    kid = m.group(1)
                    if kid not in SPIEL.z["karten"]:
                        return self.antwort(404, {"fehler": "Karte unbekannt"})
                    if kid != SPIEL.z["karteAktiv"] and not SPIEL.z["karten"][kid].get("bekannt") and not self.ist_sl(q):
                        return self.antwort(403, {"fehler": "Karte nicht aktiv"})
                    daten = SPIEL.karten_jpeg(kid, ganz=self.ist_sl(q) and q.get("ganz", ["1"])[0] == "1")
                return self.antwort(200, daten, "image/jpeg")
            if u.path == "/api/charaktere":
                return self.antwort(200, alle_charaktere())
            if u.path == "/api/zauber":
                if q.get("name"):  # ein Zauber mit vollständigem PRD-Text
                    z = ZDB.prd_finden(q["name"][0])
                    k = WI.zauber_finden(kx(), q["name"][0])
                    if not z and not k:
                        return self.antwort(404, {"fehler": "Zauber unbekannt"})
                    return self.antwort(200, {**(k or {}), "prdText": (z or {}).get("text")})
                return self.antwort(200, WI.katalog_liste(kx()))
            if u.path == "/api/sl/ereignisse":
                if not self.ist_sl(q):
                    return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
                seit = int(q.get("seit", ["0"])[0])
                warten = min(float(q.get("warten", ["0"])[0] or 0), 120)  # Long-Poll für `warte` (Sekunden)
                with SPIEL.lock:
                    ende = time.time() + warten
                    while warten > 0 and not weckende_ereignisse() and time.time() < ende:
                        SPIEL.lock.wait(ende - time.time())
                    return self.antwort(200, {"eintraege": [e for e in SPIEL.log if e["id"] > seit],
                                              "letzteVerarbeitet": SPIEL.z["letzteVerarbeitet"],
                                              "slStatus": SPIEL.z["slStatus"]})
            if u.path == "/api/sl/barrieren":  # nur SL: erkannte Wände/Türen der Karte (für die SL-Ansicht)
                if not self.ist_sl(q):
                    return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
                with SPIEL.lock:
                    kid = q.get("karte", [SPIEL.z["karteAktiv"]])[0]
                    d = SPIEL.barr(kid)
                    if d is None:
                        return self.antwort(200, {"waende": [], "extra": []})
                    return self.antwort(200, {"waende": [[round(v) for v in s] for s in barrieren.aktive_waende(d).tolist()],
                                              "extra": d["extra"]})
            if u.path == "/api/sl/zustand":
                if not self.ist_sl(q):
                    return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
                with SPIEL.lock:
                    return self.antwort(200, SPIEL.z)
            # statische Dateien
            pfad = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            datei = (WEB / pfad).resolve()
            if WEB.resolve() not in datei.parents or not datei.is_file():
                return self.antwort(404, {"fehler": "nicht gefunden"})
            return self.antwort(200, datei.read_bytes(), MIME.get(datei.suffix, "application/octet-stream"))

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            b = self.koerper()
            if u.path.startswith("/api/sl/") and not self.ist_sl(q):
                return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
            with SPIEL.lock:
                ergebnis = SPIEL.ausfuehren(post_befehl, u.path, b)
            return self.antwort(200, ergebnis)
        except KeyError as e:
            return self.antwort(400, {"fehler": f"Angabe fehlt oder unbekannt: {e}"})
        except (Fehler, ValueError) as e:
            return self.antwort(400, {"fehler": str(e)})
        except Exception as e:  # noqa: BLE001
            return self.antwort(500, {"fehler": repr(e)})


def main():
    ThreadingHTTPServer.allow_reuse_address = False  # Windows: sonst können zwei Server denselben Port belegen
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} ist schon belegt – läuft der Server dieser (oder einer anderen) Kampagne schon?")
    srv.daemon_threads = True
    print(f"Spieltisch »{KAMP['name']}« läuft: http://localhost:{PORT}/  (Ordner: {KAMP['ordner']})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
