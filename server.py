"""Spieltisch-Server (gemeinsames Tool für mehrere Kampagnen) – die Shell.

Start:            python server.py [--kampagne PFAD]   (Kampagnenordner mit kampagne.json)
Spieler-Ansicht:  http://localhost:<Port aus kampagne.json>/
SL-Ansicht:       http://localhost:<Port>/?sl=<Schlüssel aus sl/schluessel.txt>

Der Server ist die einzige Stelle, die Spielstand (sl/zustand.json), Protokoll (daten/protokoll.jsonl),
Charaktere und Barrieren schreibt. Die Spielregeln stehen in den Fachbereichen unter bereiche/ (siehe
ARCHITEKTUR.md); hier liegen nur HTTP, Sperre, Laden/Speichern, Würfel/Uhr, Kartenbilder und die Zuordnung
von Anfragen zu Fachfunktionen. Jede schreibende Anfrage läuft als Einheit: bei einem Fehler wird nichts
gespeichert. Die Spieler-API liefert nur, was die Charaktere wahrnehmen können; Kartenbilder werden im
Nebel maskiert, damit nichts Verborgenes im Browser landet.
"""
import argparse
import json
import os
import pickle
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import speicher
from bereiche import kampagne
from bereiche import REAKTIONEN, kern
from bereiche import besitz as BE, charakter as CH, kampf as KM, karte as KA, magie as MA, tisch as TI, wissen as WI
from bereiche.karte import barrieren, karten
from bereiche.kern import Fehler

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


# ---------------------------------------------------------------- Spielstand, Befehle als Einheit, Kartenressourcen

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
        self.waende = {}      # karten-id -> (Dateistempel, Wandraster für die Bewegungsprüfung)
        self.jpeg_cache = {}  # (karten-id, nebel-version, ganz) -> bytes
        self.barr_cache = {}  # karten-id -> [Dateistempel, Barrieren-Dict, (seg, seite)]
        self.masken = {}      # karten-id -> Bool-Maske des aufgedeckten Bereichs (Sichtpolygon-Modus)
        self.barr_offen = {}  # karten-id -> Barrieren, die der laufende Befehl ändert (geschrieben bei Erfolg)

    def kontext(self):
        return kern.Kontext(self.z, self.log, speicher.Charakterspeicher(CHARAKTERE), KAMP, self, kern.zufall,
                            lambda: time.strftime("%H:%M"), REAKTIONEN)

    def ausfuehren(self, f, *args):
        """Führt f(kx, *args) als Einheit aus (unter der Sperre): bei einem Fehler wird der Spielstand aus der
        Sicherung zurückgeholt und nichts geschrieben; sonst Protokoll, Charaktere, Barrieren, Spielstand speichern."""
        sicherung = pickle.dumps(self.z, pickle.HIGHEST_PROTOCOL)
        log_alt = list(self.log)
        kx = self.kontext()
        self.barr_offen = {}
        try:
            ergebnis = f(kx, *args)
            KM.tot_abgleich(self.z)  # Invariante: Gegner mit TP <= 0 sind tot
        except BaseException:
            self.z = pickle.loads(sicherung)
            self.log[:] = log_alt
            self.masken.clear()
            self.barr_cache.clear()
            self.barr_offen = {}
            raise
        self.uebernehmen(kx)
        return ergebnis

    def uebernehmen(self, kx):
        for kid, daten in self.barr_offen.items():
            barrieren.speichern(SL, kid, daten)
            self.barr_cache.pop(kid, None)
        self.barr_offen = {}
        kx.chars.schreiben()
        if kx.log_neu_schreiben:
            PROTOKOLL.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.log), encoding="utf-8")
        elif kx.neue:
            with PROTOKOLL.open("a", encoding="utf-8") as f:
                for e in kx.neue:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        self.z["version"] += 1
        self.speichern()
        self.lock.notify_all()

    def speichern(self):
        tmp = ZUSTAND.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.z, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ZUSTAND)

    # -- Kartenressourcen (kx.res)
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

    def karte_neu_geladen(self, kid):
        self.bilder.pop(kid, None)
        self.waende.pop(kid, None)

    def karten_jpeg(self, kid, ganz):
        k = self.z["karten"][kid]
        schluessel = (kid, k.get("nebelVersion", 0), ganz)
        if schluessel not in self.jpeg_cache:
            for alt in [s for s in self.jpeg_cache if s[0] == kid and s[2] == ganz]:
                del self.jpeg_cache[alt]
            offen = [tuple(c) for c in k.get("aufgedeckt", [])]
            pm = None
            if KA.sichtmodus(k) and not ganz:
                bild = self.bild(kid)
                pm = barrieren.maske_in_pixel(self.maske(kid), bild.shape[1], bild.shape[0])
            self.jpeg_cache[schluessel] = karten.maskiert_jpeg(self.bild(kid), k, offen, ganz=ganz, pixelmaske=pm)
        return self.jpeg_cache[schluessel]

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
        """Aufdeck-Maske (Bool, MASKE_B px je Block), bei Bedarf aus dem Spielstand oder den Feldern aufgebaut."""
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


SPIEL = Spiel()


# ---------------------------------------------------------------- Zuordnung: Anfrage -> Fachfunktion

def _sicht_alle(kx, b):
    return {"aufgedeckt": KA.sicht(kx, list(kx.z["tokens"].values()), KA.aktive(kx, b.get("karte")), b.get("karte"))}


def _barrieren(kx, b):
    return KA.barrieren_befehl(kx, b["op"], b)


def _aufstieg_sl(kx, b):
    return CH.aufstieg_sl(kx, b["op"], b)


SL_BEFEHLE = {
    # Tisch
    "erzaehle": lambda kx, b: TI.erzaehlen(kx, b["text"], b.get("titel")),
    "eintrag-loeschen": lambda kx, b: TI.eintrag_loeschen(kx, b["id"]),
    "notiz": lambda kx, b: TI.notiz(kx, b["text"]),
    "status": lambda kx, b: TI.status(kx, b["status"]),
    "szene": lambda kx, b: TI.szene(kx, b.get("titel", ""), b.get("untertitel", "")),
    "handout": lambda kx, b: TI.handout(kx, b["id"], b["text"], b.get("titel")),
    "handout-weg": lambda kx, b: TI.handout_weg(kx, b["id"]),
    "wurf": lambda kx, b: TI.sl_wurf(kx, b["ausdruck"], b.get("grund", ""), b.get("wer", "SL"), b.get("verborgen", False)),
    "verarbeitet": lambda kx, b: TI.verarbeitet(kx, b["bis"]),
    # Karte
    "karte-registrieren": lambda kx, b: KA.registrieren(kx, b["karte"]),
    "karte-aktiv": lambda kx, b: KA.aktivieren(kx, b["id"]),
    "karte-bekannt": KA.bekannt,
    "raster": KA.raster,
    "sicht": _sicht_alle,
    "tuer": _barrieren,
    "nebel-modus": KA.nebel_modus,
    "aufdecken": lambda kx, b: KA.auf_zu(kx, "aufdecken", b),
    "verdecken": lambda kx, b: KA.auf_zu(kx, "verdecken", b),
    "abdecken": KA.abdecken,
    "token-setzen": lambda kx, b: KA.setzen(kx, b["token"]),
    "token-aendern": lambda kx, b: KA.aendern(kx, b["id"], b["werte"]),
    "taeuschung": KA.taeuschung,
    "token-entfernen": lambda kx, b: KA.entfernen(kx, b["id"]),
    # Kampf
    "bewegen": lambda kx, b: KM.sl_bewegen(kx, b["id"], b["x"], b["y"]),
    "tp": lambda kx, b: KM.tp_sl(kx, b["id"], b["delta"]),
    "zustand": lambda kx, b: KM.zustand_sl(kx, b["id"], b["name"], b.get("an", True)),
    "initiative": KM.initiative_befehl,
    "angriff": KM.sl_angriff,
    "zug": lambda kx, b: KM.zug_aendern(kx, b["werte"]),
    # Charakter
    "ep": CH.ep_befehl,
    "char-setzen": lambda kx, b: CH.char_setzen(kx, b["charId"], b["werte"]),
    "modus": lambda kx, b: CH.modus_befehl(kx, "modus", b),
    "modus-ende": lambda kx, b: CH.modus_befehl(kx, "modus-ende", b),
    "modus-zeit": lambda kx, b: {"abgelaufen": CH.modi_zeit(kx, int(b["runden"]))},
    "modi": lambda kx, b: {"zeilen": CH.modi_liste(kx)},
    "aufstieg-fertig": _aufstieg_sl, "aufstieg-zurueck": _aufstieg_sl, "aufstieg-zeigen": _aufstieg_sl,
    "aufstieg-abbrechen": _aufstieg_sl,
    # Magie
    "rast": lambda kx, b: MA.rast(kx, b.get("charId")),
    "buch-add": lambda kx, b: MA.zauberbuch(kx, {**b, "op": "add"}),
    "buch-weg": lambda kx, b: MA.zauberbuch(kx, {**b, "op": "weg"}),
    # Besitz
    "kasse": BE.aendern, "item-neu": BE.aendern, "item-aendern": BE.aendern, "item-weg": BE.aendern,
}


def sl_befehl(kx, b):
    """Ein Spielleiter-Befehl {"op": …}. Rückgabe: dict für die Antwort."""
    op = b.get("op") or ""
    f = SL_BEFEHLE.get(op) or (_barrieren if op.startswith("barriere") else None)
    if f is None:
        raise Fehler(f"Unbekannter Befehl {op!r}")
    return f(kx, b) or {}


SPIELER_BEFEHLE = {
    "/api/aktion": lambda kx, b: TI.spieler_aktion(kx, b.get("text"), b.get("wer")),
    "/api/wurf": TI.spieler_wurf,
    "/api/anstupsen": lambda kx, b: TI.anstupsen(kx),
    "/api/zeigen": lambda kx, b: TI.zeigen(kx, b["x"], b["y"], b.get("wer")),
    "/api/gruppennotizen": lambda kx, b: TI.gruppennotizen(kx, b.get("text", "")),
    "/api/angriff": KM.sc_angriff,
    "/api/sturmangriff": KM.sturmangriff,
    "/api/zug-beenden": lambda kx, b: KM.zug_beenden(kx, b["id"]),
    "/api/aktion-verbrauchen": lambda kx, b: KM.aktion_nutzen(kx, b["id"], b["aktion"], b.get("wofuer")),
    "/api/bewegen": lambda kx, b: KM.bewegen_spieler(kx, b["id"], b["x"], b["y"]),
    "/api/sc-tp": lambda kx, b: KM.tp_spieler(kx, b["id"], b["delta"]),
    "/api/sc-zustand": lambda kx, b: KM.zustand_spieler(kx, b["id"], b["name"]),
    "/api/sc-platzieren": lambda kx, b: KA.sc_platzieren(kx, b["charId"], b["x"], b["y"]),
    "/api/sc-entfernen": lambda kx, b: KA.sc_entfernen(kx, b["charId"]),
    "/api/zaubern": MA.wirken_spieler,
    "/api/faehigkeit": MA.faehigkeit_spieler,
    "/api/zauberbuch": MA.zauberbuch,
    "/api/zauber-vorbereiten": MA.vorbereiten,
    "/api/ausruestung": BE.aendern,
    "/api/aufstieg-plan": lambda kx, b: CH.aufstieg_spieler(kx, "plan", b),
    "/api/aufstieg-tp": lambda kx, b: CH.aufstieg_spieler(kx, "tp", b),
    "/api/aufstieg-senden": lambda kx, b: CH.aufstieg_spieler(kx, "senden", b),
    "/api/charakter": lambda kx, b: CH.charakter_speichern(kx, b, secrets.token_hex(3)),
    "/api/charakter-loeschen": lambda kx, b: CH.charakter_loeschen(kx, b["id"]),
}


def post_befehl(kx, pfad, b):
    """Alle schreibenden Anfragen (läuft in SPIEL.ausfuehren)."""
    if pfad == "/api/sl/befehl":
        ergebnis = {}
        for befehl in (b if isinstance(b, list) else [b]):
            ergebnis = sl_befehl(kx, befehl)
        return ergebnis
    f = SPIELER_BEFEHLE.get(pfad)
    if f is None:
        raise Fehler("Unbekannter Pfad")
    return f(kx, b) or {}


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
            return self._get(u, q)
        except Exception as e:  # noqa: BLE001
            return self.antwort(500, {"fehler": str(e)})

    def _get(self, u, q):
        if u.path == "/api/stand":
            sl = self.ist_sl(q)
            seit = int(q.get("seit", ["0"])[0])
            with SPIEL.lock:
                ende = time.time() + 25
                while SPIEL.z["version"] <= seit and time.time() < ende:
                    SPIEL.lock.wait(ende - time.time())
                kx = SPIEL.kontext()
                return self.antwort(200, TI.sl_sicht(kx) if sl else TI.spieler_sicht(kx))
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
            with SPIEL.lock:
                return self.antwort(200, TI.charaktere_ansicht(SPIEL.kontext()))
        if u.path == "/api/zauber":
            kx = SPIEL.kontext()
            if q.get("name"):  # ein Zauber mit vollständigem PRD-Text
                z = WI.prd_finden(q["name"][0])
                k = WI.zauber_finden(kx, q["name"][0])
                if not z and not k:
                    return self.antwort(404, {"fehler": "Zauber unbekannt"})
                return self.antwort(200, {**(k or {}), "prdText": (z or {}).get("text")})
            return self.antwort(200, WI.katalog_liste(kx))
        if u.path.startswith("/api/wissen/"):
            return self._wissen(u.path, q)
        if u.path.startswith("/api/sl/") and not self.ist_sl(q):
            return self.antwort(403, {"fehler": "SL-Schlüssel fehlt"})
        if u.path == "/api/sl/ereignisse":
            seit = int(q.get("seit", ["0"])[0])
            warten = min(float(q.get("warten", ["0"])[0] or 0), 120)  # Long-Poll für `warte` (Sekunden)
            with SPIEL.lock:
                ende = time.time() + warten
                while warten > 0 and not TI.weckende_ereignisse(SPIEL.kontext()) and time.time() < ende:
                    SPIEL.lock.wait(ende - time.time())
                return self.antwort(200, {"eintraege": [e for e in SPIEL.log if e["id"] > seit],
                                          "letzteVerarbeitet": SPIEL.z["letzteVerarbeitet"],
                                          "slStatus": SPIEL.z["slStatus"]})
        if u.path == "/api/sl/barrieren":  # nur SL: erkannte Wände/Türen der Karte (für die SL-Ansicht)
            with SPIEL.lock:
                kid = q.get("karte", [SPIEL.z["karteAktiv"]])[0]
                d = SPIEL.barr(kid)
                if d is None:
                    return self.antwort(200, {"waende": [], "extra": []})
                return self.antwort(200, {"waende": [[round(v) for v in s] for s in barrieren.aktive_waende(d).tolist()],
                                          "extra": d["extra"]})
        if u.path == "/api/sl/zustand":
            with SPIEL.lock:
                return self.antwort(200, SPIEL.z)
        # statische Dateien
        pfad = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        datei = (WEB / pfad).resolve()
        if WEB.resolve() not in datei.parents or not datei.is_file():
            return self.antwort(404, {"fehler": "nicht gefunden"})
        return self.antwort(200, datei.read_bytes(), MIME.get(datei.suffix, "application/octet-stream"))

    def _wissen(self, pfad, q):
        """Nachschlagen (nur lesend, ohne Spielstand): Regeln, Zauber, Hausregeln für alle, Monster nur für den SL."""
        a = {k: v[0] for k, v in q.items() if k != "sl"}
        sl, haus, N = self.ist_sl(q), SL / "hausregeln.md", WI.nachschlagen
        try:
            if pfad == "/api/wissen/suche":
                daten = N.suche(a.get("q", ""), a.get("art"), a.get("buch"), a.get("typ"), sl, haus,
                                klasse=a.get("klasse"), grad=a.get("grad"), schule=a.get("schule"),
                                quelle=a.get("quelle"), volltext=a.get("volltext") == "1", hg=a.get("hg"),
                                monsterart=a.get("monsterart"))
            elif pfad == "/api/wissen/eintrag":
                daten = N.eintrag(a.get("art", "regel"), a.get("id"), a.get("name"), sl, haus)
            elif pfad == "/api/wissen/inhalt":
                daten = N.inhalt(a.get("seite"), sl)
            elif pfad == "/api/wissen/filter":
                daten = N.filter_listen(sl, haus)
            elif pfad == "/api/wissen/talente":
                daten = N.talente_tabelle(sl)
            elif pfad == "/api/wissen/zauber":
                daten = N.zauber_tabelle(a.get("q"), a.get("klasse"), a.get("grad"), a.get("schule"), a.get("quelle"),
                                         a.get("volltext") == "1")
            else:
                return self.antwort(404, {"fehler": "nicht gefunden"})
        except WI.NurSL as e:
            return self.antwort(403, {"fehler": str(e)})
        except Fehler as e:
            return self.antwort(404, {"fehler": str(e)})
        except ValueError:  # z. B. grad=abc, seite=xyz
            return self.antwort(400, {"fehler": "Ungültige Angabe"})
        return self.antwort(200, daten)

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
