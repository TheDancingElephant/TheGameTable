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
import random
import re
import secrets
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import argparse

import kampagne
import barrieren
import karten
import modi as MODI
import zauber_db as ZDB

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

ZUSTAENDE = [
    "Auf dem falschen Fuß", "Benommen", "Betäubt", "Bewusstlos", "Blind", "Entkräftet",
    "Erschöpft", "Erschüttert", "Fasziniert", "Festgehalten", "Gelähmt", "Geblendet",
    "Hilflos", "Im Ringkampf", "In Panik", "Kränkelnd", "Liegend", "Sterbend", "Stabil",
    "Taub", "Tot", "Übelkeit", "Unsichtbar", "Verängstigt", "Verstrickt", "Verwirrt", "Wankend",
]

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

    # -- Persistenz
    def speichern(self):
        tmp = ZUSTAND.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.z, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ZUSTAND)

    def geaendert(self):
        tot_abgleich(self.z)
        self.z["version"] += 1
        self.speichern()
        self.lock.notify_all()

    def eintragen(self, art, text, **extra):
        e = {"id": self.z["naechsteLogId"], "zeit": time.strftime("%H:%M"), "art": art, "text": text, **extra}
        self.z["naechsteLogId"] += 1
        self.log.append(e)
        with PROTOKOLL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return e

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
        p = barrieren.pfad(SL, kid)
        stempel = p.stat().st_mtime if p.exists() else None
        c = self.barr_cache.get(kid)
        if c is None or c[0] != stempel:
            daten = barrieren.laden(SL, kid) if stempel else None
            c = [stempel, daten, barrieren.blockierend(daten) if daten else None]
            self.barr_cache[kid] = c
        return c[2] if blockierend else c[1]

    def barr_speichern(self, kid, daten):
        barrieren.speichern(SL, kid, daten)
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

    def offen_set(self, k):
        return {tuple(c) for c in k.get("aufgedeckt", [])}

    # -- Sicht für Spieler
    def token_sichtbar(self, t, offen):
        if t["art"] == "sc":
            return True
        if not t.get("sichtbar", True):
            return False
        return (t["x"], t["y"]) in offen

    def taeuschung_fuer(self, t):
        """Illusionsansicht: Eintrag aus t['taeuschung'] für den SC, der gerade in der Initiative dran ist.
        Nur im Kampf, nur wenn global nicht abgeschaltet, nie für den aktiven Token selbst. Sonst None."""
        z = self.z
        td = t.get("taeuschung")
        if not td or z.get("taeuschungAus"):
            return None
        ini = z["initiative"]
        if not ini.get("aktiv") or ini.get("phase") == "wuerfeln" or not z.get("zug"):
            return None
        akt = z["tokens"].get(z["zug"].get("tokenId") or "")
        if not akt or akt["art"] != "sc" or akt["id"] == t["id"]:
            return None
        r = td.get(akt.get("charId") or "")
        if r is None:  # geteilte Sicht: Golem o. ä. sieht, was sein Sichtpartner sieht (eigener Eintrag hat Vorrang)
            p = sicht_partner(akt)
            if p:
                r = td.get(p.get("charId") or "")
        return r

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


def gesundheit_text(t):
    if t.get("tpMax") in (None, 0):
        return None
    if t.get("tp", 0) <= 0:
        return "kampfunfähig"
    q = t["tp"] / t["tpMax"]
    if q >= 1:
        return "unverletzt"
    if q > 0.5:
        return "leicht verletzt"
    if q > 0.25:
        return "schwer verletzt"
    return "dem Tode nah"


# ---------------------------------------------------------------- Würfel

WURF_RE = re.compile(r"([+-]?)\s*(?:(\d*)\s*[wWdD]\s*(\d+)|(\d+))")


def wuerfeln(ausdruck):
    """'1W20+5', '2w6 + 1w4 - 1'. Gibt (summe, details, nat20/nat1-Info) zurück."""
    a = ausdruck.replace(" ", "")
    if not a or not re.fullmatch(r"([+-]?(\d*[wWdD]\d+|\d+))+", a):
        raise ValueError(f"Unverständlicher Wurf: {ausdruck!r}")
    summe, teile, besonders = 0, [], None
    for vz, anz, seiten, zahl in WURF_RE.findall(a):
        faktor = -1 if vz == "-" else 1
        if seiten:
            n, s = int(anz or 1), int(seiten)
            if n > 100 or s > 1000:
                raise ValueError("Zu viele Würfel")
            w = [random.randint(1, s) for _ in range(n)]
            summe += faktor * sum(w)
            teile.append(f"{'-' if faktor < 0 else '+'}{n}W{s}[{','.join(map(str, w))}]")
            if s == 20 and n == 1:
                besonders = "nat20" if w[0] == 20 else "nat1" if w[0] == 1 else besonders
        else:
            summe += faktor * int(zahl)
            teile.append(f"{'-' if faktor < 0 else '+'}{zahl}")
    detail = " ".join(teile).lstrip("+")
    return summe, detail, besonders


# ---------------------------------------------------------------- Felder & Nebel

def zellen_rechteck(x0, y0, x1, y1):
    return [(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]


def zellen_kreis(cx, cy, r):
    return [(x, y) for x in range(cx - r, cx + r + 1) for y in range(cy - r, cy + r + 1)
            if pf_distanz(cx, cy, x, y) <= r]


def pf_distanz(x0, y0, x1, y1):
    """Felder nach PF1-Diagonalregel (1-2-1-2 …)."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    return max(dx, dy) + min(dx, dy) // 2


def token_felder(t):
    g = t.get("groesse", 1)
    return [(t["x"] + i, t["y"] + j) for i in range(g) for j in range(g)]


def abstand(t1, t2):
    """Kleinster Abstand in Feldern zwischen zwei Tokens (berücksichtigt Größe)."""
    return min(pf_distanz(a[0], a[1], b[0], b[1]) for a in token_felder(t1) for b in token_felder(t2))


# ---------------------------------------------------------------- Kampf: Waffen, Züge, Angriffe

FERN_RE = re.compile(r"bogen|armbrust|schleuder|blasrohr|wurf|berührungslos|strahl", re.I)
INKREMENTE = [("langbogen", 30), ("kurzbogen", 18), ("schwere armbrust", 36), ("armbrust", 24),
              ("schleuder", 15), ("blasrohr", 6), ("wurfspeer", 9), ("wurfaxt", 3), ("dolch", 3),
              ("berührungslos", 9)]
UNFAEHIG = ("Bewusstlos", "Sterbend", "Hilflos", "Gelähmt", "Betäubt")


def waffe_info(a):
    """Fernkampf? Grundreichweite (m)? Berührungsangriff? – aus Angaben oder Waffenname."""
    name = (a.get("name") or "").lower()
    fern = a.get("fernkampf")
    if fern is None:
        fern = bool(FERN_RE.search(name))
    ink = a.get("inkrement") or (next((m for n, m in INKREMENTE if n in name), 9) if fern else None)
    return {"fernkampf": fern, "inkrement": ink, "beruehrung": "berührung" in name}


def krit_info(krit):
    k = (krit or "").replace(" ", "").lower()
    m = re.search(r"(\d+)-20", k)
    m2 = re.search(r"[x×](\d)", k)
    return (int(m.group(1)) if m else 20), (int(m2.group(1)) if m2 else 2)


def meter_pro_feld():
    try:
        return (SPIEL.karte() or {}).get("meterProFeld", 1.5)
    except Exception:
        return 1.5


def wirksam(c):
    """Charakter mit angewendeten Modi (Hast, Größe …); unverändert, wenn Modi in der Kampagne abgeschaltet sind."""
    if c is None or not KAMP.get("modi", True):
        return c
    return MODI.char_wirksam(c, lambda a: waffe_info(a)["fernkampf"], meter_pro_feld())


def sc_char(t):
    try:
        return wirksam(char_laden(t["charId"])) if t.get("charId") else None
    except Fehler:
        return None


def reichweite_felder_t(t):
    """Nahkampfreichweite eines Tokens in Feldern (1 = angrenzend; gesetzt durch Größenmodi)."""
    return max(1, int(t.get("reichweite") or 1))


def tempo_felder(t):
    c = sc_char(t) or {}
    k = SPIEL.karte()
    return int((c.get("bewegung") or 9) // ((k or {}).get("meterProFeld", 1.5)))


def bewegungsbedarf(felder, tempo):
    """Wie viele Bewegungsaktionen kostet eine Strecke? 1 Feld = 1,5-m-Schritt (kostet keine)."""
    if felder <= 1:
        return 0
    return 1 if felder <= tempo else 2 if felder <= 2 * tempo else 3


def zug_info():
    z = SPIEL.z
    zug = z.get("zug")
    if not zug or not z["initiative"].get("aktiv"):
        return None
    t = z["tokens"].get(zug.get("tokenId") or "")
    eintrag = next((e for e in z["initiative"]["eintraege"] if e["name"] == zug["name"]), {})
    info = {"tokenId": zug.get("tokenId"), "name": "???" if eintrag.get("verborgen") else zug["name"],
            "art": t["art"] if t else "gegner"}
    if t and t["art"] == "sc":
        tempo = tempo_felder(t)
        n = bewegungsbedarf(zug["bewegt"], tempo) + (1 if zug["bewegung"] else 0)
        aktionen = (0 if zug["bewegung"] else 1) + (0 if zug["standard"] else 1)
        grenze = max(tempo * aktionen, 1 if zug["bewegt"] == 0 else 0)
        info.update({
            "standardFrei": not zug["standard"] and n <= 1,
            "bewegungFrei": n == 0,
            "schnellFrei": not zug["schnell"],
            "tempo": tempo, "bewegt": zug["bewegt"], "restFelder": max(0, grenze - zug["bewegt"]),
        })
    return info


def zug_starten():
    z = SPIEL.z
    ini = z["initiative"]
    if not ini["eintraege"]:
        z["zug"] = None
        return
    e = ini["eintraege"][ini["index"]]
    z["zug"] = {"tokenId": e.get("tokenId"), "name": e["name"], "bewegt": 0,
                "standard": False, "bewegung": False, "schnell": False}
    SPIEL.eintragen("system", f"Runde {ini['runde']}: {'Ein unbekannter Gegner' if e.get('verborgen') else e['name']} ist am Zug")


def tot_abgleich(z):
    """Gegner/NSC: Zustand „Tot“ automatisch setzen (TP <= 0) bzw. wieder entfernen (TP > 0).
    Nur automatisch gesetzte Markierungen (Feld totAuto) werden wieder entfernt; von Hand gesetztes „Tot“ bleibt.
    SC bleiben unberührt (Sterbend/Bewusstlos)."""
    for t in z["tokens"].values():
        if t.get("art") not in ("gegner", "nsc") or t.get("tp") is None:
            continue
        zs = t.setdefault("zustaende", [])
        if t["tp"] <= 0 and "Tot" not in zs:
            zs.append("Tot")
            t["totAuto"] = True
        elif t["tp"] > 0 and "Tot" in zs and t.get("totAuto"):
            zs.remove("Tot")
            del t["totAuto"]
        elif t["tp"] > 0 and "Tot" not in zs:
            t.pop("totAuto", None)


def ist_tot(z, eintrag):
    t = z["tokens"].get(eintrag.get("tokenId") or "")
    return bool(t and t.get("art") in ("gegner", "nsc") and "Tot" in t.get("zustaende", []))


def ini_weiter():
    z = SPIEL.z
    ini = z["initiative"]
    if not ini["eintraege"]:
        return
    tot_abgleich(z)
    n = len(ini["eintraege"])
    for _ in range(n):  # tote Gegner/NSC überspringen (höchstens eine volle Runde)
        ini["index"] += 1
        if ini["index"] >= n:
            ini["index"] = 0
            ini["runde"] += 1
            modi_zeit(1)
        if not ist_tot(z, ini["eintraege"][ini["index"]]):
            break
    zug_starten()


def darf_handeln(t):
    """Im Kampf darf nur der aktive Charakter handeln – und nur, wenn der SL nicht gerade dran ist."""
    z = SPIEL.z
    ini = z["initiative"]
    if not ini.get("aktiv"):
        return
    if ini.get("phase") != "laeuft":
        raise Fehler("Erst Initiative würfeln – der Kampf beginnt gleich")
    if z["slStatus"] != "bereit":
        raise Fehler("Der Spielleiter ist gerade am Zug – bitte warten")
    zug = z.get("zug") or {}
    if zug.get("tokenId") != t["id"]:
        raise Fehler(f"{t['name']} ist nicht am Zug")


def flankiert(angreifer, ziel):
    """Verbündeter steht auf der gegenüberliegenden Seite des Ziels (vereinfacht für mittelgroße Ziele)."""
    if ziel.get("groesse", 1) != 1 or abstand(angreifer, ziel) > 1:
        return False
    gegenueber = (2 * ziel["x"] - angreifer["x"], 2 * ziel["y"] - angreifer["y"])
    for t in SPIEL.z["tokens"].values():
        if (t is not angreifer and t["art"] == angreifer["art"] and t.get("karte") == ziel.get("karte")
                and gegenueber in token_felder(t) and not set(t.get("zustaende", [])) & set(UNFAEHIG)):
            return True
    return False


def ziel_rk(ziel, beruehrung):
    zs = ziel.get("zustaende", [])
    if ziel["art"] == "sc":
        rk = (sc_char(ziel) or {}).get("rk", {})
        normal, ber, ff = rk.get("normal"), rk.get("beruehrung"), rk.get("adff")
    else:
        normal, ber, ff = ziel.get("rk"), ziel.get("rkBeruehrung"), ziel.get("rkAdff")
    if beruehrung:
        return ber if ber is not None else normal
    if ("Auf dem falschen Fuß" in zs or set(zs) & set(UNFAEHIG)) and ff is not None:
        return ff
    return normal


def angriff_aufloesen(wer, ziel, waffe, bonus, schaden, krit, beruehrung, nahkampf, mods):
    """Würfelt einen Angriff gegen die (verdeckte) RK, inkl. Kritischem Treffer, und zieht Schaden ab."""
    zs = ziel.get("zustaende", [])
    if "Liegend" in zs:
        mods.append(("Ziel liegt", 4 if nahkampf else -4))
    if nahkampf and set(zs) & set(UNFAEHIG):
        mods.append(("Ziel hilflos", 4))
    summe_mods = sum(v for _, v in mods)
    rk = ziel_rk(ziel, beruehrung)
    d20 = random.randint(1, 20)
    gesamt = d20 + bonus + summe_mods
    detail = f"1W20[{d20}] {bonus:+d}" + "".join(f" {v:+d} {t}" for t, v in mods)
    titel = f"{wer} greift {ziel['name']} an ({waffe})"
    besonders = "nat20" if d20 == 20 else "nat1" if d20 == 1 else None
    if rk is None:  # keine RK hinterlegt: der SL wertet aus
        SPIEL.eintragen("angriff", titel, wer=wer, ergebnis=gesamt, detail=detail, besonders=besonders,
                        treffer=None, schadenAusdruck=schaden, wecken=True)
        SPIEL.z["slStatus"] = "wartet"
        return None
    treffer = d20 == 20 or (d20 != 1 and gesamt >= rk)
    bereich, mult = krit_info(krit)
    kritisch, bestaetigung = False, None
    if treffer and d20 >= bereich:
        b20 = random.randint(1, 20)
        bsum = b20 + bonus + summe_mods
        kritisch = b20 == 20 or (b20 != 1 and bsum >= rk)
        bestaetigung = f"Bestätigung 1W20[{b20}] = {bsum}"
    schaden_summe, sdetail = None, []
    if treffer and schaden:
        schaden_summe = 0
        for _ in range(mult if kritisch else 1):
            s, d, _ = wuerfeln(schaden)
            schaden_summe += s
            sdetail.append(d)
        schaden_summe = max(1, schaden_summe)
        if ziel.get("tp") is not None:
            ziel["tp"] -= schaden_summe
            if ziel["art"] == "sc":
                char_tp_sync(ziel)
    SPIEL.eintragen("angriff", titel, wer=wer, ergebnis=gesamt, detail=detail, besonders=besonders,
                    treffer=treffer, kritisch=kritisch, bestaetigung=bestaetigung, schaden=schaden_summe,
                    schadenDetail=" + ".join(sdetail), zielId=ziel["id"])
    SPIEL.eintragen("sl-notiz", f"{titel}: {gesamt} gegen RK {rk} → {'Treffer' if treffer else 'daneben'}"
                    f"{', kritisch' if kritisch else ''}; {ziel['name']} TP {ziel.get('tp')}/{ziel.get('tpMax')}",
                    verborgen=True)
    return treffer


def sturmangriff_feld(t, ziel):
    """Landefeld für einen Sturmangriff: angrenzend ans Ziel, mindestens 2 Felder (3 m) und höchstens das
    Doppelte der Bewegungsrate entfernt, auf freiem, aufgedecktem Boden, ohne Umweg. Gibt (x, y, weg) zurück."""
    k = SPIEL.karte()
    offen = SPIEL.offen_set(k)
    tempo = tempo_felder(t)
    g = t.get("groesse", 1)
    start = (t["x"], t["y"])
    wand = k.get("waendeSperren") and t.get("karte", SPIEL.z["karteAktiv"]) == SPIEL.z["karteAktiv"]
    belegt = {f for s in SPIEL.z["tokens"].values() if s is not t and s.get("karte") == t.get("karte")
              for f in token_felder(s)}
    besser = None
    gz = ziel.get("groesse", 1)
    for x in range(ziel["x"] - g, ziel["x"] + gz + 1):
        for y in range(ziel["y"] - g, ziel["y"] + gz + 1):
            probe = {"x": x, "y": y, "groesse": g}
            felder = token_felder(probe)
            if abstand(probe, ziel) > 1 or any(f in belegt for f in felder):
                continue
            if abstand(probe, ziel) == 0 or any(f not in offen for f in felder):
                continue
            luft = pf_distanz(start[0], start[1], x, y)
            if luft < 2 or luft > 2 * tempo:
                continue
            weg = luft
            if wand:
                weg = karten.weg_felder(SPIEL.wand(SPIEL.z["karteAktiv"]), k, start, (x, y), erlaubt=offen)
                if weg is None or weg > luft * 1.25 + 1:
                    continue
            if weg > 2 * tempo:
                continue
            if besser is None or (weg, luft) < (besser[2], besser[3]):
                besser = (x, y, weg, luft)
    if besser is None:
        raise Fehler("Sturmangriff nicht möglich: kein freies Feld neben dem Ziel in gerader Linie, mindestens 3 m und höchstens "
                     f"{2 * tempo * 1.5:g} m entfernt")
    return besser[0], besser[1], besser[2]


# ---------------------------------------------------------------- Erfahrung & Stufenaufstieg

# Mittlere Aufstiegsgeschwindigkeit (PF1): EP, ab denen eine Stufe erreicht ist
# Erfahrungspunkte je Stufe (PF1), Index = Stufe; Aufstiegsgeschwindigkeit je Kampagne (kampagne.json: "epTempo")
EP_TABELLEN = {
    "langsam": [0, 0, 3000, 7500, 14000, 23000, 35000, 53000, 77000, 115000, 160000, 235000, 330000, 475000,
                665000, 955000, 1350000, 1900000, 2700000, 3850000, 5350000],
    "mittel": [0, 0, 2000, 5000, 9000, 15000, 23000, 35000, 51000, 75000, 105000, 155000, 220000, 315000,
               445000, 635000, 890000, 1300000, 1800000, 2550000, 3600000],
    "schnell": [0, 0, 1300, 3300, 6000, 10000, 15000, 23000, 34000, 50000, 71000, 105000, 145000, 210000,
                295000, 425000, 600000, 850000, 1200000, 1700000, 2400000],
}
EP_MITTEL = EP_TABELLEN.get(KAMP.get("epTempo", "mittel"), EP_TABELLEN["mittel"])  # Name bleibt, Tabelle je Kampagne
# EP-Belohnung je Herausforderungsgrad
HG_EP = {"1/8": 50, "1/6": 65, "1/4": 100, "1/3": 135, "1/2": 200, "1": 400, "2": 600, "3": 800, "4": 1200,
         "5": 1600, "6": 2400, "7": 3200, "8": 4800, "9": 6400, "10": 9600, "11": 12800, "12": 19200,
         "13": 25600, "14": 38400, "15": 51200, "16": 76800, "17": 102400, "18": 153600, "19": 204800, "20": 307200}
TREFFERWUERFEL = [("barbar", 12), ("kämpfer", 10), ("paladin", 10), ("waldläufer", 10), ("gestaltwandler", 10),
                  ("schwertkämpfer", 10), ("kavalier", 10), ("antipaladin", 10), ("magus", 8), ("kleriker", 8),
                  ("druide", 8), ("schurke", 8), ("barde", 8), ("mönch", 8), ("alchemist", 8), ("inquisitor", 8),
                  ("orakel", 8), ("hexenjäger", 8), ("ninja", 8), ("schamane", 8), ("skalde", 8), ("investigator", 8),
                  ("magier", 6), ("hexenmeister", 6), ("hexe", 6), ("arkanist", 6)]


FERTIGKEITSPUNKTE = [("schurke", 8), ("ninja", 8), ("investigator", 6), ("barde", 6), ("waldläufer", 6), ("inquisitor", 6),
                     ("skalde", 4), ("gestaltwandler", 4), ("barbar", 4), ("druide", 4), ("mönch", 4), ("alchemist", 4),
                     ("orakel", 4), ("schwertkämpfer", 4), ("kavalier", 4), ("hexenjäger", 4)]


def stufe_von(c):
    if c.get("stufe"):
        return int(c["stufe"])
    zahlen = re.findall(r"\d+", c.get("klasse") or "")  # Mehrklassig: "Mönch 5 Schurke 3" = Stufe 8
    return sum(int(z) for z in zahlen) if zahlen else 1


def trefferwuerfel(klasse):
    k = (klasse or "").lower()
    return next((w for n, w in TREFFERWUERFEL if n in k), 8)


def ep_info(c):
    stufe = stufe_von(c)
    ep = int(c.get("ep") or 0)
    naechste = EP_MITTEL[stufe + 1] if stufe + 1 < len(EP_MITTEL) else None
    return {"stufe": stufe, "ep": ep, "naechste": naechste, "basis": EP_MITTEL[stufe] if stufe < len(EP_MITTEL) else 0,
            "aufstiegMoeglich": naechste is not None and ep >= naechste and not c.get("aufstieg"),
            "tw": trefferwuerfel(c.get("klasse")),
            "fertigkeitspunkte": next((p for n, p in FERTIGKEITSPUNKTE if n in (c.get("klasse") or "").lower()), 2),
            "koMod": attr_mod((c.get("attribute") or {}).get("KO")),
            "inMod": attr_mod((c.get("attribute") or {}).get("IN"))}


def ep_vergeben(char_ids, je, grund):
    for c in alle_charaktere():
        if c["id"] not in char_ids:
            continue
        vorher = ep_info(c)["aufstiegMoeglich"]
        c["ep"] = int(c.get("ep") or 0) + je
        info = ep_info(c)
        char_speichern(c)
        if info["aufstiegMoeglich"] and not vorher:
            SPIEL.eintragen("system", f"⬆ {c['name']} kann auf Stufe {info['stufe'] + 1} aufsteigen!")
    namen = ", ".join(c["name"] for c in alle_charaktere() if c["id"] in char_ids)
    SPIEL.eintragen("ep", f"{grund}: {je} EP für {namen}", ep=je, grund=grund)


# ---------------------------------------------------------------- Zauber

ZAUBER_DATEI = DATEN / "zauber.json" if (DATEN / "zauber.json").exists() else BASIS / "daten" / "zauber.json"
ATTRIBUT_NACH_KLASSE = [("kleriker", "WE"), ("druide", "WE"), ("waldläufer", "WE"), ("inquisitor", "WE"), ("schamane", "WE"),
                        ("hexenmeister", "CH"), ("barde", "CH"), ("paladin", "CH"), ("orakel", "CH"), ("skalde", "CH")]
FORMEL_RE = re.compile(r"\{([^{}]+)\}")
RW_NAMEN = {"REF": "Reflex", "WIL": "Willen", "ZAEH": "Zähigkeit"}


def zauber_db():
    """name (klein) -> Katalogeintrag: alle PRD-Zauber (daten/zauber_prd.json), Mechanik aus zauber.json darüber."""
    return ZDB.katalog(ZAUBER_DATEI)


def zauber_katalog_liste():
    """Für /api/zauber: jeder Zauber einmal (ohne alte Alias-Namen und ohne PRD-Details), nach Grad und Name."""
    erg = [{k: v for k, v in z.items() if k != "prd"} for z in zauber_db().values() if not z.get("aliasVon")]
    return sorted(erg, key=lambda d: (d.get("grad") or 0, d["name"]))


def attr_mod(wert):
    return 0 if wert is None else (int(wert) - 10) // 2


def zauberstufe(c):
    if c.get("zauberstufe"):
        return int(c["zauberstufe"])
    m = re.search(r"\d+", c.get("klasse") or "")
    return int(m.group()) if m else 1


def zauberattribut(c):
    if c.get("zauberattribut"):
        return c["zauberattribut"]
    klasse = (c.get("klasse") or "").lower()
    return next((a for k, a in ATTRIBUT_NACH_KLASSE if k in klasse), "IN")


def formel(text, stufe):
    """Ersetzt {…} durch das Ergebnis (nur Zahlen, stufe, min, max, Grundrechenarten)."""
    def ersetzen(m):
        ausdruck = m.group(1)
        if not re.fullmatch(r"[\d\s+\-*/(),stufeminax]+", ausdruck):
            raise Fehler(f"Ungültige Formel {ausdruck!r}")
        return str(int(eval(ausdruck, {"__builtins__": {}}, {"stufe": stufe, "min": min, "max": max})))
    return FORMEL_RE.sub(ersetzen, str(text)) if text is not None else None


def zauber_reichweite(r, stufe):
    """Reichweite in Metern; 'beruehrung' = angrenzend, 'selbst' = 0."""
    if isinstance(r, (int, float)):
        return float(r)
    return {"nah": 7.5 + 1.5 * (stufe // 2), "mittel": 30 + 3 * stufe, "fern": 120 + 12 * stufe,
            "beruehrung": 1.5, "selbst": 0}.get(r, 7.5)


def zauber_def(c, eintrag):
    """Vollständige Zauberdaten: Datenbank + Angaben am Charakter, Formeln ausgerechnet."""
    d = dict(ZDB.katalog_finden(zauber_db(), eintrag.get("name")) or {"modus": "sl", "ziel": "keins", "reichweite": "nah"})
    if eintrag.get("grad") in (None, "") and d.get("klassen"):  # Grad passend zur Klasse des Charakters
        g = ZDB.grad_fuer(d, ZDB.zauberklasse(c))
        if g is not None:
            d["grad"] = g
    d.update({k: v for k, v in eintrag.items() if k not in ("verbraucht",) and v not in (None, "")})
    stufe = zauberstufe(c)
    for k in ("schaden", "effekt", "rkBonus"):
        if k in d:
            d[k] = formel(d[k], stufe)
    d["reichweiteM"] = zauber_reichweite(d.get("reichweite", "nah"), stufe)
    fokus = (c.get("zauberfokus") or {}).get(d.get("schule"), 0)  # Zauberfokus/Mächtiger Zauberfokus: SG-Bonus je Schule
    d["sg"] = 10 + int(d.get("grad") or 0) + attr_mod((c.get("attribute") or {}).get(zauberattribut(c))) + int(fokus or 0)
    d["stufe"] = stufe
    d.setdefault("aktion", "standard")
    return d


def beruehrungsbonus(c, fern):
    """Bonus für Berührungsangriffe: Eintrag aus der Angriffsliste, sonst GAB + GE/ST."""
    for a in c.get("angriffe", []):
        n = (a.get("name") or "").lower()
        if ("berührungslos" in n) == fern and "berührung" in n:
            return int(a.get("bonus") or 0)
    attr = c.get("attribute") or {}
    return int(c.get("gab") or 0) + attr_mod(attr.get("GE" if fern else "ST"))


def rettungswurf_bonus(ziel, rw):
    if ziel["art"] == "sc":
        return (sc_char(ziel) or {}).get("rw", {}).get(rw)
    return ziel.get({"REF": "ref", "WIL": "wil", "ZAEH": "zaeh"}[rw])


def _spontan_quelle(c, eintrag):
    """Für spontanes Zaubern (z. B. Wunden verursachen): ein vorbereiteter Zauber gleichen Grades
    mit freiem Platz, der kein Domänenzauber ist."""
    for e in c.get("zauberliste", []):
        if (e is not eintrag and not e.get("spontan") and not e.get("domaene") and e.get("grad") == eintrag.get("grad")
                and e.get("proTag") not in (None, "") and int(e.get("verbraucht") or 0) < int(e["proTag"])):
            return e
    return None


def zauber_frei(c, eintrag):
    """Wie oft der Zauber heute noch gewirkt werden kann (None = beliebig oft)."""
    if eintrag.get("spontan"):
        return sum(int(e["proTag"]) - int(e.get("verbraucht") or 0) for e in c.get("zauberliste", [])
                   if not e.get("spontan") and not e.get("domaene") and e.get("grad") == eintrag.get("grad")
                   and e.get("proTag") not in (None, ""))
    if eintrag.get("pool"):
        p = (c.get("zauberpools") or {}).get(eintrag["pool"], {})
        return max(0, int(p.get("max") or 0) - int(p.get("verbraucht") or 0))
    if eintrag.get("proTag") in (None, ""):
        return None
    return max(0, int(eintrag["proTag"]) - int(eintrag.get("verbraucht") or 0))


def zauberplatz_verbrauchen(c, eintrag):
    """Verbraucht den passenden Platz; Rückgabe: Hinweistext für das Protokoll."""
    if zauber_frei(c, eintrag) == 0:
        raise Fehler(f"{eintrag['name']}: heute keine Zauberplätze mehr")
    if eintrag.get("spontan"):
        quelle = _spontan_quelle(c, eintrag)
        quelle["verbraucht"] = int(quelle.get("verbraucht") or 0) + 1
        return f" (spontan anstelle von {quelle['name']})"
    if eintrag.get("pool"):
        p = c["zauberpools"][eintrag["pool"]]
        p["verbraucht"] = int(p.get("verbraucht") or 0) + 1
        return ""
    if eintrag.get("proTag") not in (None, ""):
        eintrag["verbraucht"] = int(eintrag.get("verbraucht") or 0) + 1
    return ""


def zauber_aktion_frei(d):
    info = zug_info()
    if d["aktion"] == "schnell":
        return info["schnellFrei"]
    if d["aktion"] == "voll":
        return info["standardFrei"] and info["bewegungFrei"]
    return info["standardFrei"]


def rettungswurf_aufloesen(t, ziel, d, titel, verdeckt=False):
    """Rettungswurf des Ziels gegen den SG, dann Schaden (ggf. halbiert) und Zustand."""
    z = SPIEL.z
    rw = d["rettungswurf"]
    bonus = rettungswurf_bonus(ziel, rw)
    if bonus is None:  # Rettungswurf des Gegners unbekannt: der SL entscheidet
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnisText=f"{RW_NAMEN[rw]}-Wurf gegen SG {d['sg']}",
                        detail=f"{d.get('schaden') or ''} {d.get('effekt', '')}".strip(), wecken=True)
        z["slStatus"] = "wartet"
        return
    w = random.randint(1, 20)
    gelungen = w == 20 or (w != 1 and w + int(bonus) >= d["sg"])
    schaden = None
    if d.get("schaden"):
        schaden, _, _ = wuerfeln(d["schaden"])
        if gelungen:
            schaden = schaden // 2 if d.get("beiErfolg") == "halb" else 0
        if schaden and ziel.get("tp") is not None:
            ziel["tp"] -= schaden
            if ziel["art"] == "sc":
                char_tp_sync(ziel)
    zustand = d.get("zustandBeiErfolg") if gelungen else d.get("zustand")
    if zustand and zustand not in ziel.setdefault("zustaende", []):
        ziel["zustaende"].append(zustand)
    ergebnis = ("widersteht" if gelungen else "erliegt dem Zauber") + (f" – {zustand}" if zustand else "") \
        + (f" – {schaden} Schaden" if schaden else "")
    rw_text = f"{RW_NAMEN[rw]}-Wurf 1W20[{w}]{int(bonus):+d} = {w + int(bonus)}. {d.get('effekt', '')}"
    SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnisText=f"{ziel['name']} {ergebnis}",
                    detail="" if verdeckt else rw_text)
    SPIEL.eintragen("sl-notiz", f"{titel}: SG {d['sg']}, {ziel['name']}: {rw_text}" if verdeckt
                    else f"{titel}: SG {d['sg']}, Wurf {w + int(bonus)}", verborgen=True)


def zauber_wirken(t, c, index, ziel=None, feld=None):
    z = SPIEL.z
    liste = c.get("zauberliste") or []
    if not 0 <= index < len(liste):
        raise Fehler("Zauber nicht gefunden")
    eintrag = liste[index]
    d = zauber_def(c, eintrag)
    ini = z["initiative"]
    if ini.get("aktiv"):
        darf_handeln(t)
        if not zauber_aktion_frei(d):
            raise Fehler("Dafür ist keine passende Aktion mehr frei")
    if set(t.get("zustaende", [])) & set(UNFAEHIG):
        raise Fehler(f"{t['name']} kann nicht zaubern")
    if zauber_frei(c, eintrag) == 0:
        raise Fehler(f"{d['name']}: heute keine Zauberplätze mehr")

    # Ziel prüfen
    zielart = d.get("ziel", "keins")
    if not ini.get("aktiv") and z.get("angriffAusserhalb") and zielart in ("gegner", "feld"):
        raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
    if zielart == "selbst":
        ziel = t
    if zielart in ("gegner", "verbuendet"):
        if ziel is None:
            raise Fehler("Bitte ein Ziel wählen")
        if zielart == "gegner" and ziel["art"] == "sc":
            raise Fehler("Dieser Zauber richtet sich gegen Gegner")
        if not SPIEL.token_sichtbar(ziel, SPIEL.offen_set(SPIEL.karte())):
            raise Fehler("Ziel nicht sichtbar")
        d_felder = abstand(t, ziel)
        if d.get("reichweite") == "beruehrung":
            if d_felder > reichweite_felder_t(t):
                raise Fehler(f"{ziel['name']} ist nicht in Berührungsreichweite")
        elif d_felder * SPIEL.karte().get("meterProFeld", 1.5) > d["reichweiteM"]:
            raise Fehler(f"{ziel['name']} ist außer Reichweite ({d['reichweiteM']:g} m)")
    if zielart == "feld" and feld is None:
        raise Fehler("Bitte ein Zielfeld wählen")

    # Platz und Aktion verbrauchen
    hinweis = zauberplatz_verbrauchen(c, eintrag)
    char_speichern(c)
    if ini.get("aktiv"):
        zug = z["zug"]
        if d["aktion"] == "schnell":
            zug["schnell"] = True
        else:
            zug["standard"] = True
            if d["aktion"] == "voll":
                zug["bewegung"] = True

    wo = f" auf {ziel['name']}" if ziel is not None and ziel is not t else f" auf Feld ({feld[0]},{feld[1]})" if feld else ""
    titel = f"{t['name']} wirkt {d['name']}{wo}{hinweis}"
    modus = d.get("modus", "sl")
    wecken = False
    if modus in ("angriff-fern", "angriff-nah"):
        fern = modus == "angriff-fern"
        mods = []
        if fern and any(s["art"] == "sc" and s is not t and abstand(s, ziel) <= 1 for s in z["tokens"].values()
                        if s.get("karte") == ziel.get("karte")):
            mods.append(("in den Nahkampf", -4))
        if not fern and flankiert(t, ziel):
            mods.append(("Flankieren", 2))
        mit_rw = bool(d.get("rettungswurf"))  # z. B. Wunden verursachen: Berührung trifft, Wille halbiert
        treffer = angriff_aufloesen(t["name"], ziel, f"✦ {d['name']}{hinweis}", beruehrungsbonus(c, fern),
                                    None if mit_rw else d.get("schaden"), "x2", True, not fern, mods)
        if mit_rw and treffer:
            rettungswurf_aufloesen(t, ziel, d, titel)
    elif modus == "automatisch":
        s, detail, _ = wuerfeln(d["schaden"])
        if ziel.get("tp") is not None:
            ziel["tp"] -= s
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"{s} Schaden ({d.get('art', '')})",
                        detail=f"{d['schaden']}: {detail} – trifft automatisch")
    elif modus == "rettungswurf":
        rettungswurf_aufloesen(t, ziel, d, titel)
    elif modus == "heilung":
        s, detail, _ = wuerfeln(d["schaden"])
        if ziel.get("tp") is not None:
            ziel["tp"] = min(ziel["tp"] + s, ziel.get("tpMax") or ziel["tp"] + s)
            if ziel["art"] == "sc":
                char_tp_sync(ziel)
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"heilt {s} TP", detail=f"{d['schaden']}: {detail}")
    else:  # effekt oder sl
        if ziel is not None:
            if d.get("entferntZustand") in ziel.get("zustaende", []):
                ziel["zustaende"].remove(d["entferntZustand"])
            if d.get("setztZustand") and d["setztZustand"] not in ziel.setdefault("zustaende", []):
                ziel["zustaende"].append(d["setztZustand"])
        wecken = modus == "sl" and not ini.get("aktiv")
        SPIEL.eintragen("zauber", titel, wer=t["name"],
                        ergebnisText="der Spielleiter wertet aus" if modus == "sl" else "wirkt",
                        detail=d.get("effekt", ""), feld=list(feld) if feld else None, wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"

    # Offensiver Zauber außerhalb des Kampfes: der Kampf beginnt
    if not ini.get("aktiv") and zielart in ("gegner", "feld") and modus != "effekt":
        z["angriffAusserhalb"] = True
        SPIEL.eintragen("zugende", f"{t['name']} zaubert überraschend – der Kampf beginnt!", wecken=True)
        z["slStatus"] = "wartet"
    elif not ini.get("aktiv") and not wecken:
        SPIEL.eintragen("zugende", f"{t['name']} hat gezaubert.", wecken=True)
        z["slStatus"] = "wartet"


# ---------------------------------------------------------------- Klassenfähigkeiten

def faehigkeit_def(c, e):
    """Fähigkeit aus dem Charakter; Standard-SG 10 + ½ Stufe + Attribut kann am Eintrag mit 'sg' überschrieben werden."""
    d = dict(e)
    d.setdefault("aktion", "keine")
    d.setdefault("modus", "sl")
    d.setdefault("ziel", "keins")
    return d


def faehigkeit_aktion_frei(d):
    if d["aktion"] == "keine":
        return True
    info = zug_info()
    return {"schnell": info["schnellFrei"], "bewegung": info["bewegungFrei"]}.get(d["aktion"], info["standardFrei"])


def bereich_ziele(t, radius_m):
    k = SPIEL.karte()
    m = k.get("meterProFeld", 1.5)
    return [s for s in SPIEL.z["tokens"].values()
            if s["art"] != "sc" and s.get("karte") == t.get("karte") and abstand(t, s) * m <= radius_m]


def faehigkeit_wirken(t, c, index, ziel=None):
    z = SPIEL.z
    liste = c.get("faehigkeitenListe") or []
    if not 0 <= index < len(liste):
        raise Fehler("Fähigkeit nicht gefunden")
    d = faehigkeit_def(c, liste[index])
    ini = z["initiative"]
    offensiv = d["modus"] == "bereich" or d["ziel"] == "gegner"
    if ini.get("aktiv"):
        darf_handeln(t)
        if not faehigkeit_aktion_frei(d):
            raise Fehler("Dafür ist keine passende Aktion mehr frei")
    elif offensiv and z.get("angriffAusserhalb"):
        raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
    if set(t.get("zustaende", [])) & set(UNFAEHIG):
        raise Fehler(f"{t['name']} kann nicht handeln")
    if d["ziel"] in ("gegner", "verbuendet"):
        if ziel is None:
            raise Fehler("Bitte ein Ziel wählen")
        if d["ziel"] == "gegner" and ziel["art"] == "sc":
            raise Fehler("Diese Fähigkeit richtet sich gegen Gegner")
        if not SPIEL.token_sichtbar(ziel, SPIEL.offen_set(SPIEL.karte())):
            raise Fehler("Ziel nicht sichtbar")
        if d.get("reichweite", "beruehrung") == "beruehrung":
            if abstand(t, ziel) > reichweite_felder_t(t):
                raise Fehler(f"{ziel['name']} ist nicht in Berührungsreichweite")
        elif abstand(t, ziel) * SPIEL.karte().get("meterProFeld", 1.5) > float(d["reichweite"]):
            raise Fehler(f"{ziel['name']} ist außer Reichweite ({d['reichweite']} m)")

    if ini.get("aktiv") and d["aktion"] != "keine":
        zug = z["zug"]
        zug[{"schnell": "schnell", "bewegung": "bewegung"}.get(d["aktion"], "standard")] = True

    wo = f" auf {ziel['name']}" if ziel is not None and ziel is not t else ""
    titel = f"{t['name']} nutzt {d['name']}{wo}"
    wecken = False
    if d["modus"] == "bereich":
        ziele = bereich_ziele(t, float(d["radius"]))
        sg = int(d["sg"]) if d.get("sg") is not None else 10
        dd = {**d, "sg": sg}
        sichtbar = [s for s in ziele if SPIEL.token_sichtbar(s, SPIEL.offen_set(SPIEL.karte()))]
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnisText=f"{len(ziele)} Ziel(e) im Umkreis von {d['radius']:g} m"
                        if sichtbar or not ziele else "Umkreis wird ausgewertet",
                        detail=d.get("effekt", ""))
        for s in ziele:
            if d.get("untotHeilt") and s.get("untot"):
                h, detail, _ = wuerfeln(d["schaden"])
                if s.get("tp") is not None:
                    s["tp"] = min(s["tp"] + h, s.get("tpMax") or s["tp"] + h)
                SPIEL.eintragen("sl-notiz", f"{titel}: {s['name']} (Untot) heilt {h} TP ({detail})", verborgen=True)
                if s in sichtbar:
                    SPIEL.eintragen("zauber", f"{s['name']} wird gestärkt", wer=t["name"])
            else:
                rettungswurf_aufloesen(t, s, dd, f"{titel} → {s['name']}", verdeckt=True)
        if not ziele:
            SPIEL.eintragen("sl-notiz", f"{titel}: niemand im Umkreis", verborgen=True)
    elif d["modus"] == "heilung":
        s, detail, _ = wuerfeln(d["schaden"])
        if ziel.get("tp") is not None:
            ziel["tp"] = min(ziel["tp"] + s, ziel.get("tpMax") or ziel["tp"] + s)
            if ziel["art"] == "sc":
                char_tp_sync(ziel)
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"heilt {s} TP", detail=f"{d['schaden']}: {detail}")
    elif d["modus"] == "wurf":
        s, detail, _ = wuerfeln(d["wurf"])
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"{d['wurf']} = {s}",
                        detail=f"{detail}. {d.get('effekt', '')}")
    else:  # sl: der Spielleiter wertet aus
        wecken = not ini.get("aktiv")
        SPIEL.eintragen("zauber", titel, wer=t["name"], ergebnisText="der Spielleiter wertet aus",
                        detail=d.get("effekt", ""), wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"

    if not ini.get("aktiv") and not wecken:
        SPIEL.eintragen("zugende", f"{t['name']} hat {d['name']} genutzt.", wecken=True)
        z["slStatus"] = "wartet"


# ---------------------------------------------------------------- Befehle

class Fehler(Exception):
    pass


def token_finden(tid):
    t = SPIEL.z["tokens"].get(tid)
    if not t:
        # auch per Name (ohne Groß/Klein)
        for kandidat in SPIEL.z["tokens"].values():
            if kandidat["name"].lower() == str(tid).lower():
                return kandidat
        raise Fehler(f"Token {tid!r} nicht gefunden")
    return t


def neue_id(praefix, vorhanden):
    i = 1
    while f"{praefix}{i}" in vorhanden:
        i += 1
    return f"{praefix}{i}"


def sichtmodus(k):
    """Stufenloser Nebel nach Sichtpolygon (statt Feldraster) für diese Karte aktiv?"""
    return bool(k) and k.get("nebelModus") == "sicht"


def nebel_aendern(k, zellen, auf):
    if sichtmodus(k):  # Maske für die Darstellung mitführen (Felder: ganze Feldfläche)
        m = SPIEL.maske(k["id"])
        for cx, cy in zellen:
            barrieren.maske_rechteck(m, (k["ox"] + cx * k["zelle"], k["oy"] + cy * k["zelle"],
                                         k["ox"] + (cx + 1) * k["zelle"], k["oy"] + (cy + 1) * k["zelle"]), auf)
        SPIEL.maske_sichern(k["id"])
    offen = SPIEL.offen_set(k)
    if auf:
        offen |= set(zellen)
    else:
        offen -= set(zellen)
    k["aufgedeckt"] = sorted([list(c) for c in offen])
    k["nebelVersion"] = k.get("nebelVersion", 0) + 1


def sicht_partner(t):
    """Geteilte Sicht: SC-Token, dessen Sicht `t` zusätzlich nutzt (Feld `sichtVon` = Charakter-ID, am Token oder
    in den Charakterdaten; Vereinigung mit der eigenen Sicht). Ohne Feld: None (jeder sieht für sich)."""
    if t.get("art") != "sc":
        return None
    cid = t.get("sichtVon")
    if not cid and t.get("charId"):
        try:
            cid = char_laden(t["charId"]).get("sichtVon")
        except Fehler:
            cid = None
    if not cid or cid == t.get("charId"):
        return None
    p = sc_token(cid)
    if p is None or p.get("karte") != t.get("karte"):
        return None
    return p


def mit_sichtpartnern(tokens):
    """Erweitert eine Tokenliste um die Sichtpartner (ohne Doppelte)."""
    ids = {t["id"] for t in tokens}
    out = list(tokens)
    for t in tokens:
        p = sicht_partner(t)
        if p and p["id"] not in ids:
            ids.add(p["id"])
            out.append(p)
    return out


def sicht_radius(t, k):
    """Sichtweite in Feldern: Token-Feld `sicht`, sonst Dunkelsicht aus den Charakterdaten, sonst Karten-/Standardwert (8)."""
    if t.get("sicht"):
        return int(t["sicht"])
    c = sc_char(t) or {}
    m = re.search(r"Dunkelsicht\D{0,12}?(\d+(?:[.,]\d+)?)\s*m", str(c.get("faehigkeiten", "")))
    if m:
        return max(1, int(float(m.group(1).replace(",", ".")) // k.get("meterProFeld", 1.5)))
    return int(k.get("sichtFelder", 8))


def auto_nebel_aktiv(k):
    return bool(k.get("autoNebel", KAMP.get("autoNebel", False)))


def nebel_sicht(tokens, k=None, kid=None):
    """Deckt per Sichtlinie auf (nur aufdecken). Gibt die Anzahl neu aufgedeckter Felder zurück."""
    z = SPIEL.z
    kid = kid or z["karteAktiv"]
    k = k or SPIEL.karte(kid)
    if not k or "zelle" not in k:
        return 0
    tokens = mit_sichtpartnern(tokens)
    if sichtmodus(k) and SPIEL.barr(kid) is not None:
        return nebel_sichtpolygon(tokens, k, kid)
    wand = SPIEL.wand(kid)
    neu = set()
    for t in tokens:
        if t["art"] != "sc" or t.get("karte", kid) != kid:
            continue
        neu.update(karten.sicht_felder(wand, k, (t["x"], t["y"]), sicht_radius(t, k)))
    neu -= SPIEL.offen_set(k)
    if neu:
        nebel_aendern(k, neu, True)
    return len(neu)


def nebel_sichtpolygon(tokens, k, kid):
    """Sichtpolygon-Nebel: Strahlen vom Mittelpunkt jeder Spielfigur bis zur nächsten Barriere (höchstens Sichtweite);
    das Polygon wird stufenlos in die Aufdeck-Maske eingetragen. Pflegt zusätzlich die Feldliste (Mittelpunkt sichtbar),
    damit Tokensichtbarkeit und Altfunktionen weiterlaufen. Gibt die Zahl neu aufgedeckter Felder zurück."""
    seg, seite = SPIEL.barr(kid, blockierend=True)
    maske = SPIEL.maske(kid)
    z, ox, oy = k["zelle"], k["ox"], k["oy"]
    M = barrieren.MASKE_B
    geaendert = False
    neue_felder = set()
    for t in tokens:
        if t["art"] != "sc" or t.get("karte", kid) != kid:
            continue
        r = (sicht_radius(t, k) + 0.5) * z
        mitte = (ox + (t["x"] + 0.5) * z, oy + (t["y"] + 0.5) * z)
        beste = None
        for dx, dy in [(0, 0)] + [(a * 14, b * 14) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]:
            o = (mitte[0] + dx, mitte[1] + dy)
            winkel, dist = barrieren.sichtpolygon(seg, seite, o, r)
            if beste is None or dist.sum() > beste[2].sum():
                beste = (o, winkel, dist)
            if (dx, dy) == (0, 0) and dist.max() > 0.3 * z:
                break  # Mittelpunkt sieht normal; Ausweichpunkte nur, wenn die Figur praktisch in einer Wand steht
        o, winkel, dist = beste
        y0, x0, neu = barrieren.sicht_zeichnen(maske, o, winkel, dist)
        if neu.any():
            geaendert = True
        rmax = float(dist.max()) + z
        for cy in range(int((o[1] - rmax - oy) // z), int((o[1] + rmax - oy) // z) + 1):
            for cx in range(int((o[0] - rmax - ox) // z), int((o[0] + rmax - ox) // z) + 1):
                px, py = ox + (cx + 0.5) * z, oy + (cy + 0.5) * z
                if 0 <= px < k["w"] and 0 <= py < k["h"] and maske[int(py // M), int(px // M)]:
                    neue_felder.add((cx, cy))
    neue_felder -= SPIEL.offen_set(k)
    if geaendert or neue_felder:
        SPIEL.maske_sichern(kid)
        k["aufgedeckt"] = sorted([list(c) for c in SPIEL.offen_set(k) | neue_felder])
        k["nebelVersion"] = k.get("nebelVersion", 0) + 1
    return len(neue_felder)


def barrieren_befehl(op, b):
    """SL-Befehle rund um Barrieren (Wände, Türen, Fenster); Koordinaten in Feldern (Gitterpunkte, auch halbe)."""
    z = SPIEL.z
    kid = b.get("karte") or z["karteAktiv"]
    k = SPIEL.karte(kid)
    if k is None:
        raise Fehler("Keine Karte")
    zl, ox, oy = k["zelle"], k["ox"], k["oy"]

    def px(x, y):
        return [ox + float(x) * zl, oy + float(y) * zl]

    def feld(p):
        return [round((p[0] - ox) / zl * 2) / 2, round((p[1] - oy) / zl * 2) / 2]

    def mitte(e):
        return (e["p"][0] + e["p"][2]) / 2, (e["p"][1] + e["p"][3]) / 2

    if op == "barrieren-setzen":  # fertige Barrieren (z. B. aus dem Kartenimport) übernehmen
        d = b.get("daten")
        if not isinstance(d, dict) or not isinstance(d.get("waende"), list) or not isinstance(d.get("extra"), list):
            raise Fehler("barrieren-setzen: daten mit waende und extra erwartet")
        d.setdefault("loeschen", [])
        SPIEL.barr_speichern(kid, d)
        return {"waende": len(d["waende"]), "tueren": sum(1 for e in d["extra"] if e["typ"] in ("tuer", "geheimtuer"))}
    if op == "barrieren-erkennen":
        alt = SPIEL.barr(kid)
        if alt and alt.get("quelle") == "import" and not b.get("erzwingen"):
            raise Fehler("Die Wände dieser Karte stammen aus einem Import und sind exakt; Erkennung würde sie ersetzen "
                         "(erzwingen=true, falls gewollt)")
        neu = barrieren.erkennen(SPIEL.bild(kid), int(zl))
        if alt:  # Korrekturen und Türzustände behalten
            neu["loeschen"] = alt.get("loeschen", [])
            alte = [e for e in alt["extra"] if e.get("quelle") == "auto"]
            for e in neu["extra"]:
                m = mitte(e)
                for a in alte:
                    if math.hypot(mitte(a)[0] - m[0], mitte(a)[1] - m[1]) < 12:
                        e["offen"], e["typ"], e["blockiertVon"] = a.get("offen", False), a["typ"], a.get("blockiertVon")
            neu["extra"] += [e for e in alt["extra"] if e.get("quelle") != "auto"]
        SPIEL.barr_speichern(kid, neu)
        return {"waende": len(neu["waende"]), "tueren": sum(1 for e in neu["extra"] if e["typ"] in ("tuer", "geheimtuer"))}
    d = SPIEL.barr(kid)
    if d is None:
        raise Fehler("Für diese Karte gibt es noch keine Barrieren (sl.py barrieren erkennen)")
    ids = [e["id"] for e in d["extra"]]
    if op == "barriere-liste":
        return {"karte": kid, "waende": len(barrieren.aktive_waende(d)), "nebelModus": k.get("nebelModus", "raster"),
                "extra": [{"id": e["id"], "typ": e["typ"], "offen": bool(e.get("offen")), "von": feld(e["p"][:2]),
                           "bis": feld(e["p"][2:]), "blockiertVon": e.get("blockiertVon"), "quelle": e.get("quelle")}
                          for e in d["extra"]]}
    if op == "tuer":
        ziele = list(b.get("ids") or [])
        if b.get("bei"):  # nächste Tür zu einem Feld (Gitterpunkt oder Feldmitte, z. B. 12.5 7)
            c = px(*b["bei"])
            tueren = [e for e in d["extra"] if e["typ"] in ("tuer", "geheimtuer")]
            if tueren:
                e = min(tueren, key=lambda e: math.hypot(mitte(e)[0] - c[0], mitte(e)[1] - c[1]))
                if math.hypot(mitte(e)[0] - c[0], mitte(e)[1] - c[1]) <= 1.6 * zl:
                    ziele.append(e["id"])
        if not ziele:
            raise Fehler("Keine Tür gefunden (ID oder Feld prüfen: sl.py barrieren liste)")
        res = []
        for i in ziele:
            if i not in ids:
                raise Fehler(f"Barriere {i!r} unbekannt")
            e = d["extra"][ids.index(i)]
            if e["typ"] not in ("tuer", "geheimtuer"):
                raise Fehler(f"{i} ist keine Tür")
            e["offen"] = (not e.get("offen")) if b.get("offen") is None else bool(b["offen"])
            res.append(f"{i}: {'offen' if e['offen'] else 'geschlossen'}")
        SPIEL.barr_speichern(kid, d)
        if sichtmodus(k) and auto_nebel_aktiv(k):
            nebel_sicht([t for t in z["tokens"].values() if t["art"] == "sc"], k, kid)  # Sicht durch die Tür sofort nachziehen
        return {"tueren": res}
    if op == "barriere-neu":
        typ = b.get("typ", "wand")
        if typ not in barrieren.TYPEN:
            raise Fehler(f"Typ {typ!r} unbekannt ({', '.join(barrieren.TYPEN)})")
        i = 1
        while f"m{i}" in ids:
            i += 1
        e = {"id": b.get("id") or f"m{i}", "typ": typ, "p": px(*b["von"]) + px(*b["bis"]), "offen": bool(b.get("offen", False)),
             "blockiertVon": b.get("blockiertVon"), "quelle": "manuell"}
        if e["id"] in ids:
            raise Fehler(f"ID {e['id']} existiert schon")
        d["extra"].append(e)
        SPIEL.barr_speichern(kid, d)
        return {"id": e["id"]}
    if op == "barriere-aendern":
        if b["id"] not in ids:
            raise Fehler(f"Barriere {b['id']!r} unbekannt")
        e = d["extra"][ids.index(b["id"])]
        for key in ("typ", "blockiertVon"):
            if key in b:
                e[key] = b[key]
        SPIEL.barr_speichern(kid, d)
        return {}
    if op == "barriere-weg":
        n = 0
        for i in b.get("ids") or []:
            if i not in ids:
                raise Fehler(f"Barriere {i!r} unbekannt")
        if b.get("ids"):
            n = len(b["ids"])
            d["extra"] = [e for e in d["extra"] if e["id"] not in b["ids"]]
        if b.get("bereich"):  # erkannte Wandstücke (und manuelle Barrieren) in diesem Feldbereich ignorieren
            x0, y0, x1, y1 = b["bereich"]
            r = px(min(x0, x1), min(y0, y1)) + px(max(x0, x1), max(y0, y1))
            vor = len(barrieren.aktive_waende(d))
            d.setdefault("loeschen", []).append(r)
            n += vor - len(barrieren.aktive_waende(d))
            behalten = [e for e in d["extra"] if not (e.get("quelle") == "manuell" and r[0] <= mitte(e)[0] <= r[2]
                                                      and r[1] <= mitte(e)[1] <= r[3])]
            n += len(d["extra"]) - len(behalten)
            d["extra"] = behalten
        SPIEL.barr_speichern(kid, d)
        return {"entfernt": n}
    if op == "barriere-bereiche-frei":  # alle Löschbereiche wieder aufheben
        d["loeschen"] = []
        SPIEL.barr_speichern(kid, d)
        return {}
    raise Fehler(f"Unbekannter Barrieren-Befehl {op!r}")


def sl_befehl(b):
    """Alle Spielleiter-Aktionen. Rückgabe: dict für die Antwort."""
    z = SPIEL.z
    op = b.get("op")
    if op == "erzaehle":
        SPIEL.eintragen("sl", b["text"], titel=b.get("titel"))
        z["slStatus"] = "bereit"
    elif op == "eintrag-loeschen":
        SPIEL.log = [e for e in SPIEL.log if e["id"] != int(b["id"])]
        PROTOKOLL.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in SPIEL.log), encoding="utf-8")
    elif op == "notiz":  # nur SL, nicht im Spielerprotokoll
        SPIEL.eintragen("sl-notiz", b["text"], verborgen=True)
    elif op == "status":
        z["slStatus"] = b["status"]
    elif op == "szene":
        z["szene"] = {"titel": b.get("titel", ""), "untertitel": b.get("untertitel", "")}
        SPIEL.eintragen("system", f"Szene: {z['szene']['titel']}")
    elif op == "karte-registrieren":
        k = b["karte"]
        k.setdefault("aufgedeckt", [])
        k.setdefault("abdeckungen", [])
        k.setdefault("meterProFeld", 1.5)
        k["nebelVersion"] = k.get("nebelVersion", 0) + 1
        z["karten"][k["id"]] = k
        SPIEL.bilder.pop(k["id"], None)
        SPIEL.waende.pop(k["id"], None)
    elif op == "karte-aktiv":
        if b["id"] not in z["karten"]:
            raise Fehler(f"Karte {b['id']!r} unbekannt")
        z["karteAktiv"] = b["id"]
        z["karten"][b["id"]]["bekannt"] = True
        SPIEL.eintragen("system", f"Karte: {z['karten'][b['id']]['name']}")
    elif op == "karte-bekannt":  # Karte in den Unterlagen der Spieler anzeigen (oder wieder entfernen)
        k = SPIEL.karte(b["id"])
        k["bekannt"] = bool(b.get("bekannt", True))
        if "legende" in b:
            k["legende"] = b["legende"]
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
        k = SPIEL.karte(b.get("karte"))
        for key in ("zelle", "ox", "oy", "meterProFeld"):
            if key in b:
                k[key] = float(b[key])
        if "waendeSperren" in b:
            k["waendeSperren"] = bool(b["waendeSperren"])
        if "autoNebel" in b:
            if b["autoNebel"] is None:
                k.pop("autoNebel", None)
            else:
                k["autoNebel"] = bool(b["autoNebel"])
        if "sichtFelder" in b:
            k["sichtFelder"] = int(b["sichtFelder"])
        k["nebelVersion"] = k.get("nebelVersion", 0) + 1
    elif op == "sicht":  # Sichtlinien-Aufdecken jetzt für alle SC auf der Karte (unabhängig vom Schalter)
        return {"aufgedeckt": nebel_sicht([t for t in z["tokens"].values()], SPIEL.karte(b.get("karte")), b.get("karte"))}
    elif op.startswith("barriere") or op == "tuer":
        return barrieren_befehl(op, b)
    elif op == "nebel-modus":  # stufenloser Sichtpolygon-Nebel (sicht) oder Feldraster (raster), pro Karte
        kid = b.get("karte") or z["karteAktiv"]
        k = SPIEL.karte(kid)
        if b["modus"] == "sicht":
            if SPIEL.barr(kid) is None:
                barrieren_befehl("barrieren-erkennen", {"karte": kid})
            SPIEL.masken.pop(kid, None)
            k.pop("nebelMaske", None)
            k["nebelModus"] = "sicht"
            SPIEL.maske(kid)
            SPIEL.maske_sichern(kid)
        else:
            k.pop("nebelModus", None)
            k.pop("nebelMaske", None)
            SPIEL.masken.pop(kid, None)
        k["nebelVersion"] = k.get("nebelVersion", 0) + 1
    elif op in ("aufdecken", "verdecken"):
        k = SPIEL.karte(b.get("karte"))
        form = b.get("form", "rechteck")
        if form == "rechteck":
            zellen = zellen_rechteck(*b["felder"])
        elif form == "kreis":
            zellen = zellen_kreis(*b["felder"])
        elif form == "liste":
            zellen = [tuple(c) for c in b["felder"]]
        elif form == "alles":
            x0, y0, x1, y1 = karten.zellbereich(k)
            zellen = zellen_rechteck(x0, y0, x1, y1)
        else:
            raise Fehler(f"Form {form!r} unbekannt")
        nebel_aendern(k, zellen, op == "aufdecken")
    elif op in ("kasse", "item-neu", "item-aendern", "item-weg"):
        return ausruestung_aendern(b)
    elif op in ("buch-add", "buch-weg"):
        return zauberbuch_aendern({**b, "op": "add" if op == "buch-add" else "weg"})
    elif op == "abdecken":
        k = SPIEL.karte(b.get("karte"))
        if b.get("entfernen"):
            k["abdeckungen"] = [a for a in k["abdeckungen"] if a != b["felder"]]
        else:
            k["abdeckungen"].append(list(b["felder"]))
        k["nebelVersion"] = k.get("nebelVersion", 0) + 1
    elif op == "token-setzen":
        t = dict(b["token"])
        t.setdefault("id", neue_id({"gegner": "g", "nsc": "n", "objekt": "o", "sc": "sc"}.get(t.get("art", "gegner"), "t"), z["tokens"]))
        t.setdefault("art", "gegner")
        t.setdefault("groesse", 1)
        t.setdefault("zustaende", [])
        t.setdefault("sichtbar", True)
        t.setdefault("karte", z["karteAktiv"])
        if "tpMax" in t:
            t.setdefault("tp", t["tpMax"])
        z["tokens"][t["id"]] = t
        return {"id": t["id"]}
    elif op == "token-aendern":
        t = token_finden(b["id"])
        for key, wert in b["werte"].items():
            if wert is None:
                t.pop(key, None)
            else:
                t[key] = wert
    elif op == "taeuschung":  # Illusionsansicht je SC (siehe README „Illusionen“)
        if b.get("schalter") in ("ein", "aus"):
            z["taeuschungAus"] = b["schalter"] == "aus"
            return {"aus": z["taeuschungAus"]}
        t = token_finden(b["id"])
        td = t.setdefault("taeuschung", {})
        if b.get("weg"):
            for cid in (b.get("fuer") or list(td)):
                td.pop(cid, None)
        else:
            eintrag = {k: b[k] for k in ("name", "symbol", "farbe", "x", "y", "groesse", "sichtbar", "art")
                       if b.get(k) is not None}
            if not eintrag:
                raise Fehler("Täuschung ohne Angaben (name/symbol/farbe/x/y/groesse/sichtbar/art)")
            for cid in b["fuer"]:
                td[cid] = dict(eintrag)
        if not td:
            t.pop("taeuschung", None)
        return {"taeuschung": t.get("taeuschung", {})}
    elif op == "token-entfernen":
        t = token_finden(b["id"])
        del z["tokens"][t["id"]]
        ini_entfernen(z["initiative"], lambda e: e.get("tokenId") == t["id"])
    elif op == "bewegen":
        t = token_finden(b["id"])
        bedroht = []
        if t["art"] != "sc" and z["initiative"].get("aktiv"):  # Gelegenheitsangriff möglich? (nur Hinweis)
            bedroht = [s["name"] for s in z["tokens"].values()
                       if s["art"] == "sc" and s.get("karte") == t.get("karte") and abstand(s, t) <= 1
                       and not set(s.get("zustaende", [])) & set(UNFAEHIG)]
        t["x"], t["y"] = int(b["x"]), int(b["y"])
        if t["art"] == "sc" and auto_nebel_aktiv(SPIEL.karte(t.get("karte"))):
            nebel_sicht([t])
        if bedroht:
            return {"warnung": f"Gelegenheitsangriff möglich für: {', '.join(bedroht)} ({t['name']} verließ ein bedrohtes Feld)"}
    elif op == "tp":
        t = token_finden(b["id"])
        t["tp"] = t.get("tp", 0) + int(b["delta"])
        if t["art"] == "sc" and t.get("charId"):
            char_tp_sync(t)
    elif op == "zustand":
        t = token_finden(b["id"])
        zs = t.setdefault("zustaende", [])
        if b.get("an", True) and b["name"] not in zs:
            zs.append(b["name"])
        elif not b.get("an", True) and b["name"] in zs:
            zs.remove(b["name"])
    elif op == "initiative":
        ini = z["initiative"]
        aktion = b["aktion"]
        if aktion == "start":
            ini.update({"aktiv": True, "phase": "wuerfeln", "runde": 0, "index": 0, "eintraege": []})
            z["zug"] = None
            z["angriffAusserhalb"] = False
            SPIEL.eintragen("system", "Kampf! Würfelt Initiative.")
        elif aktion == "los":  # alle haben gewürfelt: erster Zug beginnt
            ini_sortieren(ini)
            ini.update({"phase": "laeuft", "runde": 1, "index": 0})
            zug_starten()
        elif aktion == "eintrag":
            ini_entfernen(ini, lambda e: e["name"] == b["name"])
            wert = float(b["wert"])
            ini["eintraege"].append({"name": b["name"], "wert": int(wert) if wert.is_integer() else wert, "tokenId": b.get("tokenId"),
                                     "verborgen": b.get("verborgen", False)})
            ini_sortieren(ini)
        elif aktion == "entfernen":
            ini_entfernen(ini, lambda e: e["name"] == b["name"])
        elif aktion == "aufdecken":
            for e in ini["eintraege"]:
                if e["name"] == b["name"]:
                    e["verborgen"] = False
        elif aktion == "weiter":
            ini_weiter()
        elif aktion == "ende":
            ini.update({"aktiv": False, "phase": None, "runde": 0, "index": 0, "eintraege": []})
            z["zug"] = None
            z["angriffAusserhalb"] = False
            SPIEL.eintragen("system", "Der Kampf ist vorbei.")
    elif op == "angriff":  # Angriff eines Gegners/NSC, ohne Regelprüfung (der SL entscheidet)
        a = token_finden(b["angreifer"])
        ziel = token_finden(b["ziel"])
        angriff_aufloesen(a["name"], ziel, b.get("waffe", "Angriff"), int(b["bonus"]), b.get("schaden"),
                          b.get("krit"), b.get("beruehrung", False), not b.get("fernkampf", False),
                          [(t, int(v)) for t, v in b.get("mods", [])]
                          + (MODI.token_angriff_mods(a, b.get("fernkampf", False)) if KAMP.get("modi", True) and not a.get("charId") else []))
    elif op == "ep":  # Erfahrung vergeben: aus HG der Gegner oder fester Betrag, geteilt durch die Empfänger
        empfaenger = b.get("an") or [t["charId"] for t in z["tokens"].values()
                                     if t["art"] == "sc" and t.get("karte") == z["karteAktiv"] and t.get("charId")]
        if not empfaenger:
            raise Fehler("Keine Empfänger")
        gesamt = int(b.get("ep") or 0)
        hg_liste = list(b.get("hg") or [])
        for tid in b.get("gegner") or []:
            t = token_finden(tid)
            if t.get("hg") is None:
                raise Fehler(f"{t['name']} hat keinen HG")
            hg_liste.append(str(t["hg"]))
        for hg in hg_liste:
            if str(hg) not in HG_EP:
                raise Fehler(f"Unbekannter HG {hg}")
            gesamt += HG_EP[str(hg)]
        je = gesamt // len(empfaenger)
        ep_vergeben(set(empfaenger), je, b.get("grund") or "Erfahrung")
        return {"je": je, "gesamt": gesamt}
    elif op in ("aufstieg-fertig", "aufstieg-zurueck", "aufstieg-zeigen", "aufstieg-abbrechen"):
        return aufstieg_sl(op, b)
    elif op == "char-setzen":  # einzelne Werte eines Charakters ändern, Pfad mit Punkten (z. B. rw.REF)
        c = char_laden(b["charId"])
        for pfad, wert in b["werte"].items():
            pfad_setzen(c, pfad, wert)
        char_speichern(c)
        t = sc_token(c["id"])
        if t:
            t.update({"name": c["name"], "tpMax": c.get("tp", {}).get("max"), "tp": c.get("tp", {}).get("aktuell")})
    elif op == "rast":  # Zauberplätze zurücksetzen (alle oder ein Charakter)
        for c in alle_charaktere():
            if b.get("charId") in (None, c["id"]):
                for e in c.get("zauberliste", []):
                    e["verbraucht"] = 0
                for p in (c.get("zauberpools") or {}).values():
                    p["verbraucht"] = 0
                if c.get("betaeubendPool"):
                    c["betaeubendPool"]["verbraucht"] = 0
                char_speichern(c)
        modi_zeit(4800)  # 8 Stunden: Modi mit kürzerer Dauer enden
        SPIEL.eintragen("system", "Nach der Rast sind die Zauberplätze wieder frei.")
    elif op == "zug":  # Aktionen des aktuellen Zuges anpassen
        if not z.get("zug"):
            raise Fehler("Kein Zug aktiv")
        for key, wert in b["werte"].items():
            z["zug"][key] = wert
    elif op in ("modus", "modus-ende"):
        return modi_befehl(op, b)
    elif op == "modus-zeit":
        return {"abgelaufen": modi_zeit(int(b["runden"]))}
    elif op == "modi":
        return {"zeilen": modi_liste()}
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


def pfad_setzen(o, pfad, wert):
    """Setzt einen Wert über einen Punktpfad; Zahlen im Pfad indizieren Listen (z. B. zauberliste.23.verbraucht)."""
    teile = pfad.split(".")
    for k in teile[:-1]:
        if isinstance(o, list):
            try:
                o = o[int(k)]
            except (ValueError, IndexError):
                raise Fehler(f"Pfad {pfad!r}: Listenindex {k!r} ungültig")
        else:
            o = o.setdefault(k, {})
    letzter = teile[-1]
    if isinstance(o, list):
        try:
            o[int(letzter)] = wert
        except (ValueError, IndexError):
            raise Fehler(f"Pfad {pfad!r}: Listenindex {letzter!r} ungültig")
    else:
        o[letzter] = wert


# ---------------------------------------------------------------- Modi (Hast, Größe, Reichweite …)

def modi_ziel(kennung):
    """Ziel eines Modus: ('char', Charakterdaten roh) oder ('token', Token ohne Charakterdatei)."""
    t = SPIEL.z["tokens"].get(kennung)
    if t is None and (CHARAKTERE / f"{kennung}.json").exists():
        return "char", char_laden(kennung)
    if t is None:
        t = token_finden(kennung)
    if t.get("charId"):
        return "char", char_laden(t["charId"])
    return "token", t


def token_umgroessern(t, g):
    """Setzt die Tokengröße; beim Wachsen wird ein freier Platz in der Nähe gesucht. Gibt einen Hinweis zurück oder None."""
    alt = t.get("groesse", 1)
    if g <= alt:
        t["groesse"] = g
        return None
    belegt = {f for s in SPIEL.z["tokens"].values() if s is not t and s.get("karte") == t.get("karte")
              for f in token_felder(s)}
    wachs = g - alt
    kandidaten = sorted(((dx, dy) for dx in range(-wachs, 1) for dy in range(-wachs, 1)), key=lambda d: (abs(d[0]) + abs(d[1]), d))
    for dx, dy in kandidaten:
        x, y = t["x"] + dx, t["y"] + dy
        if x < 0 or y < 0:
            continue
        if not any(f in belegt for f in token_felder({"x": x, "y": y, "groesse": g})):
            t.update({"x": x, "y": y, "groesse": g})
            return None
    t["groesse"] = g
    return f"{t['name']} wächst, aber es ist zu eng – das Token überlappt andere"


def modi_token_sync(t, c):
    """Überträgt Größe/Reichweite der wirksamen Charakterdaten c auf das Token t."""
    w = (c or {}).get("_wirkung") or {}
    g_neu, reich, hinweis = w.get("tokenGroesse"), w.get("reichweite"), None
    if g_neu or reich:
        t.setdefault("modiToken", {"groesse": t.get("groesse", 1)})
        ziel = g_neu or t["modiToken"]["groesse"]
        if ziel != t.get("groesse", 1):
            hinweis = token_umgroessern(t, ziel)
        if reich:
            t["reichweite"] = reich
        else:
            t.pop("reichweite", None)
    elif "modiToken" in t:
        basis = t.pop("modiToken")["groesse"]
        if basis != t.get("groesse", 1):
            hinweis = token_umgroessern(t, basis)
        t.pop("reichweite", None)
    return hinweis


def modi_syncen(art, obj):
    """Nach einer Änderung der Modi: Datei speichern, Tokens aktualisieren. Gibt Hinweise zurück."""
    hinweise = []
    if art == "char":
        char_speichern(obj)
        eff = wirksam(char_laden(obj["id"]))
        for t in SPIEL.z["tokens"].values():
            if t.get("charId") == obj["id"]:
                h = modi_token_sync(t, eff)
                if h:
                    hinweise.append(h)
    else:
        vorher = obj.get("groesse", 1)
        MODI.token_anwenden(obj, meter_pro_feld())
        neu = obj.get("groesse", 1)
        if neu != vorher:
            obj["groesse"] = vorher
            h = token_umgroessern(obj, neu)
            if h:
                hinweise.append(h)
    return hinweise


def modi_log(obj, text):
    if obj.get("art") != "gegner" and obj.get("sichtbar", True):
        SPIEL.eintragen("system", text)
    else:
        SPIEL.eintragen("sl-notiz", text, verborgen=True)


def modi_zeit(runden):
    """Zieht Runden von allen Modi ab (Kampfrunde = 1, Rast = 4800 usw.) und meldet Abgelaufenes."""
    if not KAMP.get("modi", True):
        return []
    aus_liste = []
    for p in sorted(CHARAKTERE.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        if not MODI.aktive(c):
            continue
        c["modi"], aus = MODI.zeit(c["modi"], runden)
        modi_syncen("char", c)
        aus_liste += [({"name": c["name"], "art": "sc"}, n) for n in aus]
    for t in list(SPIEL.z["tokens"].values()):
        if not t.get("charId") and MODI.aktive(t):
            t["modi"], aus = MODI.zeit(t["modi"], runden)
            modi_syncen("token", t)
            aus_liste += [(t, n) for n in aus]
    for o, n in aus_liste:
        modi_log(o, f"{o['name']}: {n} endet.")
    return [f"{o['name']}: {n}" for o, n in aus_liste]


def modi_befehl(op, b):
    art, obj = modi_ziel(b["ziel"])
    name = (b.get("name") or "").strip()
    tok = obj if art == "token" else (sc_token(obj["id"]) or {"art": "sc"})
    if op == "modus":
        if not name:
            raise Fehler("Name des Modus fehlt")
        wirk = MODI.vorlage(name)
        try:
            wirk.update(MODI.wirkung_pruefen(b.get("wirkung") or {}))
            if b.get("groesse") is not None:
                wirk["groesse"] = int(b["groesse"])
        except ValueError as e:
            raise Fehler(str(e))
        if not wirk:
            raise Fehler(f"{name!r} ist keine bekannte Vorlage – Wirkung angeben (--wirkung rk=1 …)")
        rest = b.get("runden")
        obj["modi"] = MODI.setzen(list(obj.get("modi") or []), name, wirk, None if rest is None else int(rest), b.get("quelle", ""))
        hinweise = modi_syncen(art, obj)
        modus = obj["modi"][-1]
        modi_log(tok, f"{obj['name']}: {name} ({MODI.wirkung_text(wirk)}; {MODI.dauer_text(modus)})")
        return {"text": f"{obj['name']}: {name} aktiv – {MODI.wirkung_text(wirk)}; {MODI.dauer_text(modus)}", "hinweise": hinweise}
    if op == "modus-ende":
        neu, gefunden = MODI.entfernen(list(obj.get("modi") or []), name)
        if not gefunden:
            raise Fehler(f"{obj['name']} hat keinen Modus {name!r}")
        obj["modi"] = neu
        hinweise = modi_syncen(art, obj)
        modi_log(tok, f"{obj['name']}: {name} endet.")
        return {"text": f"{obj['name']}: {name} beendet", "hinweise": hinweise}
    raise Fehler("Unbekannter Modus-Befehl")


def modi_liste():
    zeilen = []
    for p in sorted(CHARAKTERE.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        for m in MODI.aktive(c):
            zeilen.append(f"{c['name']}: {m['name']} – {MODI.wirkung_text(m['wirkung'])}; {MODI.dauer_text(m)}")
    for t in SPIEL.z["tokens"].values():
        if not t.get("charId"):
            for m in MODI.aktive(t):
                zeilen.append(f"{t['name']} ({t['id']}): {m['name']} – {MODI.wirkung_text(m['wirkung'])}; {MODI.dauer_text(m)}")
    return zeilen


def ini_entfernen(ini, entfernen):
    """Entfernt Initiative-Einträge, ohne den Zeiger auf den aktuellen Zug zu verschieben:
    wer vor dem aktuellen Eintrag entfernt wird, lässt den Index mitwandern."""
    idx = ini.get("index", 0)
    neu, neuer_index, gesetzt = [], 0, False
    for i, e in enumerate(ini["eintraege"]):
        if entfernen(e):
            continue
        if i >= idx and not gesetzt:
            neuer_index, gesetzt = len(neu), True
        neu.append(e)
    ini["eintraege"] = neu
    ini["index"] = neuer_index if gesetzt else 0


def ini_sortieren(ini):
    aktuell = ini["eintraege"][ini["index"]]["name"] if ini["eintraege"] and ini["index"] < len(ini["eintraege"]) else None
    ini["eintraege"].sort(key=lambda e: -float(e["wert"]))
    if aktuell and ini.get("phase") == "laeuft":
        ini["index"] = next(i for i, e in enumerate(ini["eintraege"]) if e["name"] == aktuell)


def char_laden(cid):
    p = CHARAKTERE / f"{cid}.json"
    if not p.exists():
        raise Fehler(f"Charakter {cid!r} nicht gefunden")
    return json.loads(p.read_text(encoding="utf-8"))


def char_speichern(c):
    c = MODI.speicherbar(c)  # abgeleitete Modus-Werte nie auf die Platte schreiben
    for e in c.get("zauberliste", []):
        e.pop("_d", None)
    for k in ("_ep", "_zauberKlasse", "_vorbereiten"):
        c.pop(k, None)
    p = CHARAKTERE / f"{c['id']}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def char_tp_sync(t):
    try:
        c = char_laden(t["charId"])
    except Fehler:
        return
    c.setdefault("tp", {})["aktuell"] = t["tp"]
    char_speichern(c)


def alle_charaktere():
    liste = [wirksam(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(CHARAKTERE.glob("*.json"))]
    for c in liste:  # Fernkampf/Reichweite ergänzen, wo nicht angegeben
        for a in c.get("angriffe", []):
            info = waffe_info(a)
            a.setdefault("fernkampf", info["fernkampf"])
            if info["inkrement"] and not a.get("inkrement"):
                a["inkrement"] = info["inkrement"]
            a["beruehrung"] = info["beruehrung"]
        for e in c.get("zauberliste", []):  # berechnete Werte für die Oberfläche (werden nicht gespeichert)
            try:
                d = zauber_def(c, e)
            except Fehler:
                continue
            d["beruehrungsbonus"] = beruehrungsbonus(c, d.get("modus") == "angriff-fern")
            d["frei"] = zauber_frei(c, e)
            if e.get("pool"):
                d["poolMax"] = (c.get("zauberpools") or {}).get(e["pool"], {}).get("max")
            e["_d"] = d
        c["_ep"] = ep_info(c)
        c["_zauberKlasse"] = ZDB.zauberklasse(c)  # Zauberliste (Feld oder aus der Klasse erraten)
        c["_vorbereiten"] = ZDB.kann_vorbereiten(c)  # Knopf „Zauber vorbereiten“ zeigen
    return liste


def sc_token(cid):
    for t in SPIEL.z["tokens"].values():
        if t.get("charId") == cid and t["art"] == "sc":
            return t
    return None


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


def _zauberliste_stand(c):
    return json.dumps([{k: v for k, v in e.items() if k != "_d"} for e in c.get("zauberliste") or []], sort_keys=True)


def zauber_vorbereiten(b):
    """Zauber neu vorbereiten (nach der Rast). op "plan": Plätze und Auswahl; op "speichern": namen je Platz."""
    c = char_laden(b["charId"])
    if SPIEL.z["initiative"].get("aktiv"):
        raise Fehler("Zauber erst nach dem Kampf vorbereiten")
    liste = c.get("zauberliste") or []
    if b.get("op") == "plan":
        buch = c.get("zauberbuch") or []
        return {"klasse": ZDB.zauberklasse(c), "plaetze": ZDB.plaetze(liste), "stand": _zauberliste_stand(c),
                "aliase": ZDB.ALIASE,
                "buch": [{"name": e["name"], "grad": e["grad"]} for e in buch] if buch else None}
    if b.get("stand") != _zauberliste_stand(c):
        raise Fehler("Die Zauberliste wurde inzwischen geändert – bitte den Dialog neu öffnen")
    try:
        neu = ZDB.neu_vorbereiten(liste, b.get("namen") or [])
    except ValueError as e:
        raise Fehler(str(e)) from None
    alt = {e["name"].lower() for e in liste}
    dazu = sorted({e["name"] for e in neu if e["name"].lower() not in alt})
    c["zauberliste"] = neu
    char_speichern(c)
    SPIEL.eintragen("system", f"{c['name']} bereitet die Zauber neu vor"
                    + (f" (neu: {', '.join(dazu)})" if dazu else " (unverändert)" if neu == liste else "") + ".")
    return {}


def zauberbuch_aendern(b):
    """Zauberbuch eines Charakters: Einträge {name, grad} hinzufügen ('add') oder entfernen ('weg')."""
    c = char_laden(b["charId"])
    buch = c.setdefault("zauberbuch", [])
    name = (b.get("name") or "").strip()
    if not name:
        raise Fehler("Zaubername fehlt")
    if b.get("op") == "weg":
        c["zauberbuch"] = [e for e in buch if e["name"].lower() != name.lower()]
    else:
        grad = int(b.get("grad", 0))
        if not 0 <= grad <= 9:
            raise Fehler("Grad muss zwischen 0 und 9 liegen")
        if not any(e["name"].lower() == name.lower() for e in buch):
            buch.append({"name": name[:80], "grad": grad})
    char_speichern(c)
    return {}


import aufstieg as AUF  # noqa: E402  (Stufenaufstiegs-Assistent)


def aufstieg_laden(b):
    """Charakter für den Assistenten holen und Voraussetzungen prüfen."""
    c = char_laden(b["charId"])
    info = ep_info(c)
    if SPIEL.z["initiative"].get("aktiv"):
        raise Fehler("Stufenaufstiege erst nach dem Kampf")
    if c.get("aufstieg") or info["aufstiegMoeglich"]:
        return c, info
    raise Fehler(f"{c['name']} hat noch nicht genug Erfahrung")


def aufstieg_spieler(pfad, b):
    c, info = aufstieg_laden(b)
    auf = c.get("aufstieg")
    if auf is None:
        auf = {"zielStufe": info["stufe"] + 1, "status": "entwurf"}
    if auf.get("status") == "freigegeben":
        raise Fehler("Dieser Aufstieg ist schon abgeschlossen")
    klasse = (b.get("klasse") or auf.get("klasse") or "").strip() or None
    vorlage = b["vorlage"] if "vorlage" in b else auf.get("vorlage")
    vorlagen = b["vorlagen"] if "vorlagen" in b else auf.get("vorlagen")
    p = AUF.plan(c, auf["zielStufe"], klasse, vorlage, vorlagen)
    if pfad == "/api/aufstieg-plan":
        return {"plan": p, "aufstieg": auf, "tpWuerfelbar": not auf.get("tp")}
    if pfad == "/api/aufstieg-tp":
        if auf.get("status") == "eingereicht":
            raise Fehler("Der Aufstieg liegt schon beim Spielleiter")
        if not auf.get("tp"):  # nur einmal: Ergebnis bleibt, auch wenn der Dialog neu geöffnet wird
            plus, text = AUF.tp_wurf(p["tw"], p["koMod"], "wurf" if b.get("art") == "wurf" else "schnitt",
                                     lambda tw: random.randint(1, tw))
            auf["tp"] = {"plus": plus, "text": text}
            auf["klasse"] = p["klasse"]
            auf["vorlage"] = p["vorlage"] or ""
            auf["vorlagen"] = p["vorlagenMap"]
            SPIEL.eintragen("system", f"{c['name']} bestimmt die Trefferpunkte für Stufe {auf['zielStufe']}: +{plus} ({text}).")
        c["aufstieg"] = auf
        char_speichern(c)
        return {"aufstieg": auf}
    # senden
    if auf.get("status") == "eingereicht":
        raise Fehler("Der Aufstieg liegt schon beim Spielleiter")
    antrag = b.get("antrag") or {}
    fehler, warn = AUF.pruefen(c, p, antrag, auf.get("tp"))
    if fehler:
        raise Fehler("Nicht abschickbar: " + " · ".join(fehler))
    auf.update({"status": "eingereicht", "antrag": antrag, "klasse": p["klasse"], "vorlage": p["vorlage"] or "", "vorlagen": p["vorlagenMap"], "warnungen": warn, "kommentar": ""})
    c["aufstieg"] = auf
    char_speichern(c)
    z = AUF.zusammenfassung(c, p, antrag, auf["tp"])
    SPIEL.eintragen("aufstieg", f"{c['name']} steigt auf: {p['klasse']} (Stufe {auf['zielStufe']})", wer=c["name"],
                    detail=" · ".join(z[1:]) + (f" · Hinweise: {'; '.join(warn)}" if warn else ""),
                    wuensche="Antrag wartet auf Freigabe (sl.py aufstieg-fertig " + c["id"] + ")", wecken=True)
    SPIEL.z["slStatus"] = "wartet"
    return {}


def aufstieg_sl(op, b):
    c = char_laden(b["charId"])
    auf = c.get("aufstieg")
    if not auf:
        raise Fehler("Kein Aufstieg offen")
    if op == "aufstieg-abbrechen":
        c.pop("aufstieg")
        char_speichern(c)
        return {}
    p = AUF.plan(c, auf["zielStufe"], auf.get("klasse"), auf.get("vorlage", ""), auf.get("vorlagen"))
    antrag = auf.get("antrag")
    if op == "aufstieg-zeigen":
        if not antrag:
            return {"text": f"Aufstieg auf Stufe {auf['zielStufe']}: Status {auf.get('status')}, noch kein Antrag."}
        f, w = AUF.pruefen(c, p, antrag, auf.get("tp"))
        return {"text": "\n".join(AUF.zusammenfassung(c, p, antrag, auf["tp"])
                                  + [f"FEHLER: {x}" for x in f] + [f"Hinweis: {x}" for x in w])}
    if op == "aufstieg-zurueck":
        if not antrag:
            raise Fehler("Kein Antrag eingereicht")
        auf["status"] = "entwurf"
        auf["kommentar"] = b.get("grund") or ""
        char_speichern(c)
        SPIEL.eintragen("system", f"Der Spielleiter gibt den Aufstieg von {c['name']} zurück: {auf['kommentar'] or 'bitte überarbeiten'}")
        return {}
    # aufstieg-fertig
    if antrag and auf.get("status") == "eingereicht":
        f, w = AUF.pruefen(c, p, antrag, auf.get("tp"))
        if f:
            raise Fehler("Antrag fehlerhaft: " + " · ".join(f))
        c.pop("aufstieg")
        AUF.anwenden(c, p, antrag, auf["tp"])
        if b.get("klasse"):
            c["klasse"] = b["klasse"]
        char_speichern(c)
        t = sc_token(c["id"])
        if t:
            t.update({"name": c["name"], "tpMax": c["tp"]["max"], "tp": c["tp"]["aktuell"]})
        SPIEL.eintragen("system", f"⬆ {c['name']} ist jetzt Stufe {c['stufe']} ({c.get('klasse')}).")
        return {}
    if auf.get("status") == "entwurf" and not b.get("erzwingen"):
        raise Fehler("Der Spieler hat den Aufstieg noch nicht abgeschickt (mit --erzwingen trotzdem abschließen)")
    c.pop("aufstieg")  # alter Ablauf: Werte hat der SL von Hand eingetragen
    c["stufe"] = auf["zielStufe"]
    if b.get("klasse"):
        c["klasse"] = b["klasse"]
    char_speichern(c)
    SPIEL.eintragen("system", f"⬆ {c['name']} ist jetzt Stufe {c['stufe']} ({c.get('klasse')}).")
    return {}


def spieler_befehl(pfad, b):
    z = SPIEL.z
    if pfad == "/api/ausruestung":
        return ausruestung_aendern(b)
    if pfad == "/api/zauberbuch":
        return zauberbuch_aendern(b)
    if pfad == "/api/zauber-vorbereiten":
        return zauber_vorbereiten(b)
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
            t = sc_token(b.get("charId")) if b.get("charId") else None
            sl_befehl({"op": "initiative", "aktion": "eintrag", "name": b.get("wer"), "wert": summe,
                       "tokenId": t["id"] if t else None})
            namen = {e["name"] for e in ini["eintraege"]}
            fehlend = [t["name"] for t in z["tokens"].values()
                       if t["art"] == "sc" and t.get("karte") == z["karteAktiv"] and t["name"] not in namen]
            if ini.get("phase") == "wuerfeln" and not fehlend:
                SPIEL.eintragen("zugende", "Alle Charaktere haben Initiative gewürfelt.", wecken=True)
                z["slStatus"] = "wartet"
        return {"ergebnis": summe, "detail": detail, "besonders": besonders, "id": e["id"]}
    elif pfad == "/api/angriff":
        t = token_finden(b["id"])
        ziel = token_finden(b["ziel"])
        if t["art"] != "sc" or ziel["art"] == "sc":
            raise Fehler("Angreifen können nur eure Charaktere – und zwar Gegner")
        k = SPIEL.karte()
        if not SPIEL.token_sichtbar(ziel, SPIEL.offen_set(k)):
            raise Fehler("Ziel nicht sichtbar")
        ini = z["initiative"]
        c = sc_char(t) or {}
        a = c.get("angriffe", [])[int(b["angriff"])]
        serie = a.get("serie")
        if ini.get("aktiv"):
            darf_handeln(t)
            zi = zug_info()
            if serie:
                if not (zi["standardFrei"] and zi["bewegungFrei"]) or z["zug"]["bewegt"] > 1:
                    raise Fehler("Ein Vollangriff braucht Standard- und Bewegungsaktion (nur ein 1,5-m-Schritt davor erlaubt)")
            elif not zi["standardFrei"]:
                raise Fehler("Keine Standard-Aktion mehr frei")
        elif z.get("angriffAusserhalb"):
            raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
        if set(t.get("zustaende", [])) & set(UNFAEHIG):
            raise Fehler(f"{t['name']} kann nicht handeln")
        info = waffe_info(a)
        d = abstand(t, ziel)
        mods = []
        if info["fernkampf"]:
            n = max(1, math.ceil(d * k.get("meterProFeld", 1.5) / info["inkrement"]))
            if n > 10:
                raise Fehler(f"{ziel['name']} ist außer Reichweite")
            if n > 1:
                mods.append(("Entfernung", -2 * (n - 1)))
            nahkampf_gegner = [s for s in z["tokens"].values() if s["art"] == "sc" and s is not t
                               and s.get("karte") == ziel.get("karte") and abstand(s, ziel) <= 1]
            if nahkampf_gegner:
                mods.append(("in den Nahkampf", -4))
        else:
            if d > reichweite_felder_t(t):
                raise Fehler(f"{ziel['name']} steht nicht neben {t['name']}" if reichweite_felder_t(t) == 1
                             else f"{ziel['name']} ist außerhalb der Reichweite von {t['name']} ({reichweite_felder_t(t) * meter_pro_feld():g} m)")
            if flankiert(t, ziel):
                mods.append(("Flankieren", 2))
        betaeubend = a.get("betaeubend")
        # Serie: Zahl (nur Bonus) oder {"bonus", "schaden", "name"} je Angriff
        eintraege = [x if isinstance(x, dict) else {"bonus": int(x)} for x in serie] if serie else [{"bonus": int(a.get("bonus") or 0)}]
        boni = [int(e["bonus"]) for e in eintraege]
        # Betäubender Schlag je Angriff: am Eintrag der Serie ("betaeubend": SG oder false), sonst Wert der Waffe
        stuns = [e["betaeubend"] if "betaeubend" in e else betaeubend for e in eintraege]
        anzahl = sum(1 for x in stuns if x)
        if anzahl:
            pool = c.setdefault("betaeubendPool", {"max": 5, "verbraucht": 0})
            if pool["max"] - pool["verbraucht"] < anzahl:
                raise Fehler(f"Betäubender Schlag: nur noch {pool['max'] - pool['verbraucht']} Anwendung(en) heute, "
                             f"dieser Angriff braucht {anzahl}")
            pool["verbraucht"] += anzahl
            char_speichern(c)
        for i, bonus in enumerate(boni):
            name = eintraege[i].get("name") or (a.get("name", "Angriff") + (f" ({i + 1}. Schlag)" if serie else ""))
            if stuns[i]:
                name += " · Betäubender Schlag"
            treffer = angriff_aufloesen(t["name"], ziel, name, bonus, eintraege[i].get("schaden") or a.get("schaden"),
                                        a.get("krit"), info["beruehrung"], not info["fernkampf"], list(mods))
            if stuns[i] and treffer:
                sg = int(stuns[i])
                bonus_rw = rettungswurf_bonus(ziel, "ZAEH")
                if bonus_rw is None:
                    SPIEL.eintragen("sl-notiz", f"Betäubender Schlag trifft {ziel['name']}: ZÄH SG {sg}, der SL wertet aus",
                                    verborgen=True, wecken=True)
                    z["slStatus"] = "wartet"
                else:
                    w20 = random.randint(1, 20)
                    erg = w20 + int(bonus_rw)
                    geschafft = erg >= sg
                    SPIEL.eintragen("zauber", f"{ziel['name']}: Zähigkeitswurf gegen Betäubenden Schlag (SG {sg})",
                                    wer=ziel["name"], ergebnis=erg, ergebnisText="widersteht" if geschafft else "betäubt",
                                    detail=f"1W20[{w20}] {int(bonus_rw):+d} gegen SG {sg}")
                    if not geschafft:
                        zs = ziel.setdefault("zustaende", [])
                        for zn in ("Betäubt", "Erschöpft"):
                            if zn not in zs:
                                zs.append(zn)
        if ini.get("aktiv"):
            z["zug"]["standard"] = True
            if serie:
                z["zug"]["bewegung"] = True
        else:
            z["angriffAusserhalb"] = True
            SPIEL.eintragen("zugende", f"{t['name']} greift überraschend an – der Kampf beginnt!", wecken=True)
            z["slStatus"] = "wartet"
    elif pfad == "/api/sturmangriff":
        t = token_finden(b["id"])
        ziel = token_finden(b["ziel"])
        if t["art"] != "sc" or ziel["art"] == "sc":
            raise Fehler("Angreifen können nur eure Charaktere – und zwar Gegner")
        k = SPIEL.karte()
        if not SPIEL.token_sichtbar(ziel, SPIEL.offen_set(k)):
            raise Fehler("Ziel nicht sichtbar")
        ini = z["initiative"]
        if not ini.get("aktiv"):
            raise Fehler("Einen Sturmangriff gibt es nur im Kampf")
        darf_handeln(t)
        info = zug_info()
        if not (info["standardFrei"] and info["bewegungFrei"]) or z["zug"]["bewegt"] > 0:
            raise Fehler("Für den Sturmangriff werden Standard- und Bewegungsaktion gebraucht (volle Aktion, vorher nicht bewegt)")
        if set(t.get("zustaende", [])) & set(UNFAEHIG):
            raise Fehler(f"{t['name']} kann nicht handeln")
        c = sc_char(t) or {}
        a = c.get("angriffe", [])[int(b["angriff"])]
        winfo = waffe_info(a)
        anspringen = "anspringen" in json.dumps({k: c.get(k) for k in ("talente", "faehigkeiten", "notizen")}, ensure_ascii=False).lower()
        if a.get("betaeubend"):
            raise Fehler("Für den Sturmangriff bitte den Einzelschlag ohne Betäubenden Schlag wählen")
        if a.get("serie") and not anspringen:
            raise Fehler("Ein Vollangriff beim Sturmangriff geht nur mit Anspringen (Pounce)")
        if winfo["fernkampf"] or winfo["beruehrung"]:
            raise Fehler("Ein Sturmangriff geht nur mit einer Nahkampfwaffe")
        x, y, weg = sturmangriff_feld(t, ziel)
        alt = (t["x"], t["y"])
        t["x"], t["y"] = x, y
        z["zug"]["bewegt"] = weg
        z["zug"]["bewegung"] = True
        meter = weg * (k.get("meterProFeld", 1.5) if k else 1.5)
        SPIEL.eintragen("bewegung", f"{t['name']} stürmt {weg} Felder ({meter:g} m) nach ({x},{y}) – Sturmangriff auf {ziel['name']}",
                        wer=t["name"], von=list(alt), nach=[x, y])
        mods = [("Sturmangriff", 2)]
        if flankiert(t, ziel):
            mods.append(("Flankieren", 2))
        serie = a.get("serie")
        eintraege = [x if isinstance(x, dict) else {"bonus": int(x)} for x in serie] if serie else [{"bonus": int(a.get("bonus") or 0)}]
        for i, e in enumerate(eintraege):
            name = e.get("name") or (a.get("name", "Angriff") + (f" ({i + 1}. Angriff)" if serie else ""))
            angriff_aufloesen(t["name"], ziel, f"{name} · Sturmangriff" + (" (Anspringen)" if serie else ""), int(e["bonus"]),
                              e.get("schaden") or a.get("schaden"), a.get("krit"), False, True, list(mods))
        z["zug"]["standard"] = True
        SPIEL.eintragen("system", f"{t['name']}: Sturmangriff – RK −2 bis zum nächsten Zug")
    elif pfad == "/api/zaubern":
        t = token_finden(b["id"])
        if t["art"] != "sc":
            raise Fehler("Nur eure Charaktere zaubern")
        c = sc_char(t)
        if not c:
            raise Fehler("Charakter nicht gefunden")
        ziel = token_finden(b["ziel"]) if b.get("ziel") else None
        zauber_wirken(t, c, int(b["zauber"]), ziel, tuple(b["feld"]) if b.get("feld") else None)
    elif pfad == "/api/faehigkeit":
        t = token_finden(b["id"])
        if t["art"] != "sc":
            raise Fehler("Nur eure Charaktere handeln")
        c = sc_char(t)
        if not c:
            raise Fehler("Charakter nicht gefunden")
        ziel = token_finden(b["ziel"]) if b.get("ziel") else None
        faehigkeit_wirken(t, c, int(b["index"]), ziel)
    elif pfad in ("/api/aufstieg-plan", "/api/aufstieg-tp", "/api/aufstieg-senden"):
        return aufstieg_spieler(pfad, b)
    elif pfad == "/api/zug-beenden":
        t = token_finden(b["id"])
        darf_handeln(t)
        if not z["initiative"].get("aktiv"):
            raise Fehler("Kein Kampf")
        SPIEL.eintragen("zugende", f"{t['name']} beendet den Zug.", wer=t["name"], wecken=True)
        ini_weiter()
        z["slStatus"] = "wartet"
    elif pfad == "/api/aktion-verbrauchen":
        t = token_finden(b["id"])
        darf_handeln(t)
        if not z["initiative"].get("aktiv"):
            raise Fehler("Kein Kampf")
        aktion = b["aktion"]
        info = zug_info()
        frei = {"standard": info["standardFrei"], "bewegung": info["bewegungFrei"], "schnell": info["schnellFrei"]}
        if not frei.get(aktion):
            raise Fehler("Diese Aktion ist schon verbraucht")
        z["zug"][aktion] = True
        name = {"standard": "Standard-Aktion", "bewegung": "Bewegungsaktion", "schnell": "Schnelle Aktion"}[aktion]
        SPIEL.eintragen("system", f"{t['name']} nutzt die {name}{': ' + b['wofuer'] if b.get('wofuer') else ''}")
    elif pfad == "/api/bewegen":
        t = token_finden(b["id"])
        if t["art"] != "sc":
            raise Fehler("Nur eigene Charaktere können bewegt werden")
        alt = (t["x"], t["y"])
        felder = pf_distanz(*alt, int(b["x"]), int(b["y"]))
        k = SPIEL.karte()
        if k and k.get("waendeSperren") and t.get("karte", z["karteAktiv"]) == z["karteAktiv"]:
            weg = karten.weg_felder(SPIEL.wand(z["karteAktiv"]), k, alt, (int(b["x"]), int(b["y"])), erlaubt=SPIEL.offen_set(k))
            if weg is None or weg > felder * 1.5 + 2:
                raise Fehler("Dort geht es nicht direkt hin: eine Wand oder unerforschtes Gebiet ist im Weg. Zieht Schritt für Schritt um die Ecke.")
            felder = max(felder, weg)
        if z["initiative"].get("aktiv"):
            darf_handeln(t)
            info = zug_info()
            if felder > info["restFelder"]:
                raise Fehler(f"Zu weit: {t['name']} kann noch {info['restFelder']} Felder gehen")
            z["zug"]["bewegt"] += felder
        t["x"], t["y"] = int(b["x"]), int(b["y"])
        k = SPIEL.karte()
        if k and t.get("karte", z["karteAktiv"]) == z["karteAktiv"] and auto_nebel_aktiv(k):
            nebel_sicht([t], k)
        meter = felder * (k.get("meterProFeld", 1.5) if k else 1.5)
        # Außerhalb eines Kampfes weckt Bewegung den SL (der Nachlauf von `warte` sammelt mehrere Züge ein)
        wecken = not z["initiative"].get("aktiv")
        SPIEL.eintragen("bewegung", f"{t['name']} bewegt sich {felder} Felder ({meter:g} m) nach ({t['x']},{t['y']})",
                        wer=t["name"], von=list(alt), nach=[t["x"], t["y"]], wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"
    elif pfad == "/api/anstupsen":  # Spieler bitten den Spielleiter, zu handeln (weckt `sl.py warte`)
        SPIEL.eintragen("system", "Die Spieler bitten den Spielleiter zu handeln.", wecken=True)
        if z["slStatus"] == "bereit":
            z["slStatus"] = "wartet"
    elif pfad == "/api/zeigen":
        SPIEL.eintragen("zeigen", f"{b.get('wer') or 'Gruppe'} zeigt auf Feld ({b['x']},{b['y']})",
                        wer=b.get("wer") or "Gruppe", feld=[b["x"], b["y"]])
    elif pfad == "/api/sc-tp":
        t = token_finden(b["id"])
        if t["art"] != "sc":
            raise Fehler("Nur eigene Charaktere")
        t["tp"] = t.get("tp", 0) + int(b["delta"])
        if t.get("tpMax") is not None:
            t["tp"] = min(t["tp"], t["tpMax"])  # Heilung nicht über das Maximum
        char_tp_sync(t)
        SPIEL.eintragen("system", f"{t['name']}: TP {'+' if int(b['delta']) >= 0 else ''}{b['delta']} → {t['tp']}/{t.get('tpMax')}")
    elif pfad == "/api/sc-zustand":
        t = token_finden(b["id"])
        if t["art"] != "sc":
            raise Fehler("Nur eigene Charaktere")
        zs = t.setdefault("zustaende", [])
        if b["name"] in zs:
            zs.remove(b["name"])
        else:
            zs.append(b["name"])
    elif pfad == "/api/sc-platzieren":
        c = char_laden(b["charId"])
        if not z["karteAktiv"]:
            raise Fehler("Keine Karte aktiv")
        t = sc_token(c["id"])
        if t is None:
            t = {"id": "sc-" + c["id"], "art": "sc", "charId": c["id"], "zustaende": [], "sichtbar": True}
            z["tokens"][t["id"]] = t
        t.update({"name": c["name"], "farbe": c.get("farbe", "#3a7bd5"), "karte": z["karteAktiv"],
                  "x": int(b["x"]), "y": int(b["y"]), "groesse": c.get("groesseFelder", 1),
                  "tpMax": c.get("tp", {}).get("max"), "tp": c.get("tp", {}).get("aktuell", c.get("tp", {}).get("max"))})
        SPIEL.eintragen("system", f"{c['name']} betritt die Karte bei ({t['x']},{t['y']})")
    elif pfad == "/api/gruppennotizen":
        z["gruppennotizen"] = str(b.get("text", ""))[:50000]
    elif pfad == "/api/sc-entfernen":
        t = sc_token(b["charId"])
        if t:
            del z["tokens"][t["id"]]
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
                    k = ZDB.katalog_finden(zauber_db(), q["name"][0])
                    if not z and not k:
                        return self.antwort(404, {"fehler": "Zauber unbekannt"})
                    return self.antwort(200, {**(k or {}), "prdText": (z or {}).get("text")})
                return self.antwort(200, zauber_katalog_liste())
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
        except Exception as e:  # noqa: BLE001
            return self.antwort(500, {"fehler": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            b = self.koerper()
            with SPIEL.lock:
                if u.path == "/api/sl/befehl":
                    if not self.ist_sl(q):
                        return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
                    ergebnis = {}
                    for befehl in (b if isinstance(b, list) else [b]):
                        ergebnis = sl_befehl(befehl)
                    SPIEL.geaendert()
                    return self.antwort(200, ergebnis)
                if u.path == "/api/charakter":
                    c = b
                    if not c.get("name"):
                        raise Fehler("Name fehlt")
                    c["id"] = c.get("id") or re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-") or secrets.token_hex(3)
                    char_speichern(c)
                    t = sc_token(c["id"])
                    if t:
                        t.update({"name": c["name"], "farbe": c.get("farbe", t.get("farbe")),
                                  "tpMax": c.get("tp", {}).get("max"), "tp": c.get("tp", {}).get("aktuell")})
                    SPIEL.geaendert()
                    return self.antwort(200, c)
                if u.path == "/api/charakter-loeschen":
                    p = CHARAKTERE / f"{b['id']}.json"
                    if p.exists():
                        p.unlink()
                    t = sc_token(b["id"])
                    if t:
                        del SPIEL.z["tokens"][t["id"]]
                    SPIEL.geaendert()
                    return self.antwort(200, {})
                ergebnis = spieler_befehl(u.path, b)
                SPIEL.geaendert()
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
