"""MCP-Server (stdio) für den Spieltisch: der einzige Zugang des SL-Agenten zum Tool.

Eine Instanz pro Kampagne:
    python <Programmordner>\\mcp_server.py "<Kampagnenordner>"

Der SL-Schlüssel bleibt in diesem Prozess (Header X-SL), der Agent sieht ihn nie. Dateien der Kampagne
(Notizen, Quellen, Charaktere, Karten) liest und schreibt der Agent nur über die Tools hier.
Implementiert das MCP-Protokoll direkt (JSON-RPC über stdin/stdout, keine Zusatzpakete nötig).
"""
import base64
import json
import sys
import threading
import time
import traceback
from pathlib import Path

BASIS = Path(__file__).resolve().parent
sys.path.insert(0, str(BASIS))

# stdout gehört dem Protokoll: alles andere (print, Warnungen) nach stderr
_AUS = sys.stdout.buffer
sys.stdout = sys.stderr
sys.stdin.reconfigure(encoding="utf-8")

from sl_api import Spieltisch, SLFehler  # noqa: E402

VERSIONEN = ("2025-06-18", "2025-03-26", "2024-11-05")
ST = None  # Spieltisch, nach dem Start gesetzt

# ------------------------------------------------------------------ Schema-Helfer


def S(d, enum=None):
    s = {"type": "string", "description": d}
    if enum:
        s["enum"] = list(enum)
    return s


def I(d):
    return {"type": "integer", "description": d}


def N(d):
    return {"type": "number", "description": d}


def B(d):
    return {"type": "boolean", "description": d}


def L(d, items=None, n=None):
    s = {"type": "array", "description": d, "items": items or {"type": "string"}}
    if n:
        s["minItems"] = s["maxItems"] = n
    return s


def O(d):
    return {"type": "object", "description": d, "additionalProperties": True}


KARTE = S("Karten-ID (Standard: aktive Karte)")
FELD2 = L("[X, Y] in Feldern (Gitterpunkte, halbe erlaubt)", {"type": "number"}, 2)

TOOLS = {}


def tool(name, beschreibung, props=None, pflicht=(), lesen=False, gruppe="", verwaltung=False):
    def deko(f):
        if name in TOOLS:
            raise RuntimeError(f"Tool-Name doppelt: {name}")
        TOOLS[name] = {"verwaltung": verwaltung, "name": name, "description": beschreibung,
                       "inputSchema": {"type": "object", "properties": props or {}, "required": list(pflicht),
                                       "additionalProperties": False},
                       "annotations": {"readOnlyHint": lesen, "title": f"{gruppe}: {name}" if gruppe else name},
                       "f": f}
        return f
    return deko


def bild(daten, typ, text):
    return [{"type": "text", "text": text}, {"type": "image", "data": base64.b64encode(daten).decode("ascii"), "mimeType": typ}]


# ------------------------------------------------------------------ Tisch

@tool("stand", "Überblick: Szene, aktive Karte, Token (ID, Art, Position, TP, Zustände), Initiative und aktueller Zug.",
      lesen=True, gruppe="Tisch")
def t_stand(a):
    return ST.stand()


@tool("protokoll", "Die letzten N Protokolleinträge (Spieleraktionen, Würfe, Angriffe, SL-Texte).",
      {"n": I("Anzahl (Standard 30)")}, lesen=True, gruppe="Tisch")
def t_protokoll(a):
    return ST.log(a.get("n") or 30)


@tool("warte", "Wartet blockierend auf die nächste Spieleraktion (ersetzt `sl.py warte` im Hintergrund). Gibt die neuen "
      "Ereignisse zurück, markiert sie als verarbeitet und setzt den SL-Status auf „denkt“. Bei Timeout: Hinweis, "
      "einfach erneut aufrufen. Nie zwei gleichzeitig. Vorher antworten (erzaehle) bzw. status_setzen bereit.",
      {"timeout": I("Sekunden bis zur Rückkehr ohne Ereignis (Standard 540, max. 3600)"),
       "nachlauf": N("Sekunden, die nach der ersten Aktion noch nachgesammelt werden (Standard 5)")}, gruppe="Tisch")
def t_warte(a, abbruch=None, fortschritt=None):
    timeout = max(5, min(int(a.get("timeout") or 540), 3600))
    stopp = threading.Event()

    def puls():  # Fortschrittsmeldungen halten die Verbindung wach (falls der Client sie anfordert)
        t0 = time.time()
        while not stopp.wait(20):
            if fortschritt:
                fortschritt(int(time.time() - t0), timeout, "warte auf Spieler …")
    if fortschritt:
        threading.Thread(target=puls, daemon=True).start()
    try:
        r = ST.warte(nachlauf=a.get("nachlauf", 5), timeout=timeout, abbruch=abbruch)
    finally:
        stopp.set()
    if r is None:
        return "Keine neue Spieleraktion (Timeout). Erneut `warte` aufrufen." if not (abbruch and abbruch.is_set()) else "abgebrochen"
    return r


@tool("erzaehle", "Erzähltext an den Tisch (Spieler sehen ihn; wörtliche Rede als `> „…“`-Zeilen). Setzt den SL-Status auf „bereit“.",
      {"text": S("Erzähltext (Markdown, mehrzeilig)"), "titel": S("Überschrift (optional)")}, ["text"], gruppe="Tisch")
def t_erzaehle(a):
    ST.erzaehle(a["text"], a.get("titel"))
    return "erzählt"


@tool("sl_notiz", "Unsichtbare SL-Notiz ins Protokoll (Spieler sehen sie nicht).", {"text": S("Text")}, ["text"], gruppe="Tisch")
def t_sl_notiz(a):
    return ST.notiz(a["text"]) or "notiert"


@tool("streiche", "Protokolleinträge löschen.", {"ids": L("Eintrags-IDs", {"type": "integer"})}, ["ids"], gruppe="Tisch")
def t_streiche(a):
    return ST.streiche(a["ids"]) or "gelöscht"


@tool("status_setzen", "SL-Status: bereit (Spieler können handeln), denkt, wartet. Nach Reaktionen ohne erzaehle: bereit.",
      {"status": S("Status", ["bereit", "denkt", "wartet"])}, ["status"], gruppe="Tisch")
def t_status(a):
    return ST.status(a["status"]) or f"Status: {a['status']}"


@tool("szene", "Szenentitel setzen.", {"titel": S("Titel"), "untertitel": S("Untertitel")}, ["titel"], gruppe="Tisch")
def t_szene(a):
    return ST.szene(a["titel"], a.get("untertitel")) or "Szene gesetzt"


@tool("handout", "Text-Handout für die Spieler anlegen oder ersetzen (gleiche ID); entfernen=true löscht es.",
      {"id": S("Handout-ID"), "text": S("Inhalt (Markdown)"), "titel": S("Titel"), "entfernen": B("Handout löschen")},
      ["id"], gruppe="Tisch")
def t_handout(a):
    return ST.handout(a["id"], a.get("text"), a.get("titel"), weg=a.get("entfernen", False)) or "ok"


@tool("wurf", "SL-Wurf (Standard verdeckt), z. B. 1W20+5, 2W6+3.",
      {"ausdruck": S("Würfelausdruck"), "grund": S("Wofür"), "wer": S("Wer würfelt (Standard SL)"),
       "offen": B("für Spieler sichtbar")}, ["ausdruck"], gruppe="Würfeln")
def t_wurf(a):
    return ST.wurf(a["ausdruck"], a.get("grund"), a.get("wer") or "SL", a.get("offen", False))


# ------------------------------------------------------------------ Token / Kampf

@tool("token_neu", "Gegner/NSC/Objekt-Token auf die aktive Karte setzen. Gibt die Token-ID zurück.",
      {"art": S("Art", ["gegner", "nsc", "objekt"]), "name": S("Name"), "x": I("Feld X"), "y": I("Feld Y"),
       "id": S("eigene ID (z. B. g1)"), "tp": I("Trefferpunkte (max.)"), "groesse": I("Felder (1 = Mittel, 2 = Groß …)"),
       "farbe": S("Farbe #rrggbb"), "symbol": S("Kürzel auf dem Token"), "verborgen": B("für Spieler unsichtbar"),
       "rk": I("RK"), "rkb": I("RK Berührung"), "rkf": I("RK auf dem falschen Fuß"), "ref": I("REF"), "wil": I("WIL"),
       "zaeh": I("ZÄH"), "hg": S("Herausforderungsgrad, z. B. 1/3 oder 2")},
      ["art", "name", "x", "y"], gruppe="Token")
def t_token_neu(a):
    return "Token " + ST.token(**{k: a.get(k) for k in ("art", "name", "x", "y", "id", "tp", "farbe", "symbol",
                                                         "rk", "rkb", "rkf", "ref", "wil", "zaeh", "hg")},
                               groesse=a.get("groesse") or 1, verborgen=a.get("verborgen", False))


@tool("token_aendern", "Beliebige Token-Felder setzen, z. B. {\"rk\": 15, \"name\": \"Ghul\", \"symbol\": \"G\"}.",
      {"id": S("Token-ID"), "werte": O("Feld -> Wert")}, ["id", "werte"], gruppe="Token")
def t_token_aendern(a):
    return ST.setze(a["id"], a["werte"]) or "geändert"


@tool("token_zeigen", "Token für Spieler sichtbar machen (sichtbar=true) oder verbergen (false).",
      {"id": S("Token-ID"), "sichtbar": B("Standard true")}, ["id"], gruppe="Token")
def t_token_zeigen(a):
    return ST.zeige(a["id"], verbergen=not a.get("sichtbar", True)) or "ok"


@tool("token_entfernen", "Token entfernen.", {"ids": L("Token-IDs")}, ["ids"], gruppe="Token")
def t_token_entfernen(a):
    return ST.weg(a["ids"]) or "entfernt"


@tool("zieh", "Token bewegen (warnt bei möglichen Gelegenheitsangriffen).",
      {"id": S("Token-ID"), "x": I("Feld X"), "y": I("Feld Y")}, ["id", "x", "y"], gruppe="Token")
def t_zieh(a):
    return ST.zieh(a["id"], a["x"], a["y"]) or "bewegt"


@tool("tp", "Trefferpunkte ändern (negativ = Schaden).", {"id": S("Token-ID"), "delta": I("Änderung")}, ["id", "delta"], gruppe="Token")
def t_tp(a):
    return ST.tp(a["id"], a["delta"]) or "ok"


@tool("zustand", "Zustände setzen/entfernen (Liegend, Wankend, Tot, Bewusstlos …).",
      {"id": S("Token-ID"), "an": L("Zustände einschalten"), "aus": L("Zustände ausschalten")}, ["id"], gruppe="Token")
def t_zustand(a):
    return ST.zustand_setzen(a["id"], ["+" + z for z in a.get("an") or []] + ["-" + z for z in a.get("aus") or []]) or "ok"


@tool("sc_platzieren", "SC-Token auf die aktive Karte setzen (nötig beim Kartenwechsel; zieh bewegt nur auf der alten Karte).",
      {"char_id": S("Charakter-ID (ohne sc-)"), "x": I("Feld X"), "y": I("Feld Y")}, ["char_id", "x", "y"], gruppe="Token")
def t_sc_platzieren(a):
    return ST.sc_platzieren(a["char_id"], a["x"], a["y"]) or "platziert"


@tool("angriff", "Angriff eines Gegners/NSC gegen RK des Ziels; Schaden wird abgezogen. Gibt das Ergebnis zurück.",
      {"angreifer": S("Token-ID"), "ziel": S("Token-ID"), "bonus": I("Angriffsbonus"), "schaden": S("Schaden, z. B. 1W8+3"),
       "waffe": S("Waffenname (Standard Angriff)"), "krit": S("Krit, z. B. 19-20/x2"), "beruehrung": B("Berührungsangriff"),
       "fernkampf": B("Fernkampf"), "mods": O("Situationsmodifikatoren, z. B. {\"Flankieren\": 2}"),
       "gelegenheitsangriff": {"type": "string", "enum": ["bewegung", "andere"],
                               "description": "Gelegenheitsangriff: bewegung (Ziel verließ/durchquerte bedrohtes Feld; "
                                              "Talent Beweglichkeit zählt, +4 RK) oder andere (z. B. Zaubern)"}},
      ["angreifer", "ziel", "bonus", "schaden"], gruppe="Kampf")
def t_angriff(a):
    return ST.angriff(a["angreifer"], a["ziel"], a["bonus"], a["schaden"], a.get("waffe") or "Angriff", a.get("krit"),
                      a.get("beruehrung", False), a.get("fernkampf", False), a.get("mods"), a.get("gelegenheitsangriff"))


@tool("taeuschung", "Illusion: Token wirkt für bestimmte SC (wenn sie am Zug sind) anders. entfernen=true hebt auf; "
      "schalter ein|aus schaltet die Täuschungsansicht global.",
      {"token": S("Token-ID"), "fuer": L("Charakter-IDs, die getäuscht werden"), "name": S("Scheinname"), "symbol": S("Symbol"),
       "farbe": S("Farbe"), "x": I("Schein-X"), "y": I("Schein-Y"), "groesse": I("Scheingröße"),
       "art": S("Scheinart", ["sc", "gegner", "nsc"]), "sichtbar": B("auch zeigen, wenn sonst verborgen/im Nebel"),
       "entfernen": B("Täuschung entfernen"), "schalter": S("global", ["ein", "aus"])}, gruppe="Kampf")
def t_taeuschung(a):
    return ST.taeuschung(a.get("token"), a.get("fuer"), a.get("name"), a.get("symbol"), a.get("farbe"), a.get("x"), a.get("y"),
                         a.get("groesse"), a.get("art"), a.get("sichtbar", False), a.get("entfernen", False), a.get("schalter"))


# ------------------------------------------------------------------ Initiative

@tool("ini", "Initiative: start (Kampf beginnt, Spieler würfeln), eintrag (Gegner eintragen), los (Reihenfolge starten), "
      "weiter (nächster), entfernen, aufdecken (verborgenen Eintrag zeigen), ende.",
      {"aktion": S("Aktion", ["start", "los", "eintrag", "entfernen", "aufdecken", "weiter", "ende"]),
       "name": S("Name (eintrag/entfernen/aufdecken)"), "wert": N("Initiativewert (eintrag)"), "token": S("Token-ID (eintrag)"),
       "verborgen": B("unbemerkt (eintrag)")}, ["aktion"], gruppe="Initiative")
def t_ini(a):
    ST.ini(a["aktion"], a.get("name"), a.get("wert"), a.get("token"), a.get("verborgen", False))
    return f"Initiative: {a['aktion']}"


@tool("zug", "Aktionen des aktuellen Zuges setzen, z. B. {\"standard\": false, \"bewegt\": 0}.",
      {"werte": O("Feld -> Wert")}, ["werte"], gruppe="Initiative")
def t_zug(a):
    return ST.zug(a["werte"]) or "ok"


# ------------------------------------------------------------------ Modi

@tool("modus", "Buff/Modus auf Charakter oder Token (Vorlagen: Hast, Heldenmut, Person vergrößern/verkleinern, Stierstärke … "
      "oder eigene Wirkung, Schlüssel: groesse ST GE KO IN WE CH rk rkr rkb rkf angriff nahangriff fernangriff schaden "
      "rkga ref wil zaeh rw ini kmb kmv tempo reichweite extraangriff fert:NAME).",
      {"ziel": S("Charakter- oder Token-ID"), "name": S("Modusname"), "runden": I("Dauer in Runden"), "minuten": I("Dauer in Minuten"),
       "stunden": I("Dauer in Stunden"), "groesse": I("Größenstufen (+1)"), "wirkung": O("Schlüssel -> ganze Zahl"),
       "quelle": S("Quelle (wer hat gezaubert)")}, ["ziel", "name"], gruppe="Modi")
def t_modus(a):
    return ST.modus(a["ziel"], a["name"], a.get("runden"), a.get("minuten"), a.get("stunden"), a.get("groesse"),
                    a.get("wirkung"), a.get("quelle") or "")


@tool("modus_ende", "Modus beenden.", {"ziel": S("Charakter- oder Token-ID"), "name": S("Modusname")}, ["ziel", "name"], gruppe="Modi")
def t_modus_ende(a):
    return ST.modus_ende(a["ziel"], a["name"]) or "beendet"


@tool("modus_zeit", "Zeit vergeht außerhalb des Kampfes (Modi laufen ab).",
      {"runden": I("Runden"), "minuten": I("Minuten"), "stunden": I("Stunden")}, gruppe="Modi")
def t_modus_zeit(a):
    return ST.modus_zeit(a.get("runden") or 0, a.get("minuten") or 0, a.get("stunden") or 0)


@tool("modi", "Aktive Modi aller Charaktere/Token.", lesen=True, gruppe="Modi")
def t_modi(a):
    return ST.modi()


# ------------------------------------------------------------------ Karten

@tool("karten_liste", "Alle Karten mit Feldbereich, Zellgröße, Nebelmodus, Barrieren (* = aktiv).", lesen=True, gruppe="Karte")
def t_karten_liste(a):
    return ST.karten_liste()


@tool("material_liste", "PDFs und Bilder im Kampagnenordner (Quellen für karte_neu).", lesen=True, gruppe="Karte")
def t_material_liste(a):
    return ST.material_liste()


@tool("material_vorschau", "PDF-Seite oder Bilddatei ansehen (blaues Hilfsgitter in Zehnteln der Seite), um Seite und "
      "Ausschnitt für karte_neu zu bestimmen. Bei Bilddateien die Feldgröße mit probe_raster [zelle, ox, oy] (in px des "
      "Originalbilds) prüfen: das grüne Raster muss auf den Kartenlinien liegen (kleinen Ausschnitt wählen). "
      "Pfad relativ zum Kampagnenordner.",
      {"datei": S("Pfad, z. B. Material/Plaene.pdf oder Level3C.png"), "seite": I("Seite (Standard 1)"),
       "ausschnitt": L("[x0, y0, x1, y1] als Bruchteile 0..1", {"type": "number"}, 4),
       "max_kante": I("längste Bildkante in px (Standard 1400)"), "gitter": B("Hilfsgitter (Standard true)"),
       "probe_raster": L("[zelle, ox, oy] Kandidatenraster (Bild: px, PDF: pt)", {"type": "number"})},
      ["datei"], lesen=True, gruppe="Karte")
def t_material_vorschau(a):
    daten, info = ST.material_vorschau(a["datei"], a.get("seite") or 1, a.get("ausschnitt"), a.get("max_kante") or 1400,
                                       a.get("gitter", True), a.get("probe_raster"))
    return bild(daten, "image/jpeg", info)


@tool("karte_neu", "Neue Karte anlegen (gleiche ID ersetzt): aus PDF-Seite (+Ausschnitt; Raster wird erkannt, sonst "
      "zelle_pt), aus Bilddatei (zelle_px = Feldgröße im Bild, vorher mit material_vorschau probe_raster prüfen; "
      "der Rasterversatz wird gesucht) oder leer. Danach: vorschau prüfen, ggf. raster, dann karte_einrichten.",
      {"id": S("Karten-ID (a-z, 0-9, -)"), "name": S("Anzeigename"), "pdf": S("PDF-Pfad relativ zum Kampagnenordner"),
       "seite": I("PDF-Seite (ab 1)"), "ausschnitt": L("[x0, y0, x1, y1] Bruchteile der Seite", {"type": "number"}, 4),
       "zelle_pt": N("Feldgröße im PDF in pt erzwingen"), "bild": S("Bilddatei statt PDF"),
       "zelle_px": N("Feldgröße im Bild in px (Bild wird auf 50 px/Feld skaliert)"),
       "versatz_erkennen": B("bei Bild mit zelle_px: Rasterversatz suchen (Standard true)"),
       "leer": L("[FELDER_X, FELDER_Y] leere Karte", {"type": "integer"}, 2), "aktiv": B("sofort aktivieren")},
      ["id", "name"], gruppe="Karte")
def t_karte_neu(a):
    return ST.karte_neu(a["id"], a["name"], a.get("pdf"), a.get("seite") or 1, a.get("ausschnitt"), a.get("zelle_pt"),
                        a.get("bild"), a.get("zelle_px"), a.get("leer"), a.get("aktiv", False), a.get("versatz_erkennen", True))


@tool("karte_import", "Karte mit exakten Wänden/Türen importieren, ohne Wanderkennung: Spieltisch-Kartenformat oder "
      "Universal VTT (.dd2vtt/.uvtt aus Dungeondraft, DungeonFog, Dungeon Alchemist). Schaltet Sichtnebel und Auto-Nebel ein. "
      "Spieltisch-Format (Koordinaten in Feldern = Gitterpunkte, Feld (0,0) oben links): {\"id\", \"name\", "
      "\"felder\": [B, H], \"raeume\": [{\"rechteck\": [x0,y0,x1,y1], \"boden\": \"stein|holz|erde|gras|wasser|sand|teppich|marmor\"} "
      "oder {\"vieleck\": [[x,y],…]}], \"waende\": [[[x,y],[x,y],…]], \"tueren\": [{\"von\": [x,y], \"bis\": [x,y], "
      "\"typ\": \"tuer|geheimtuer|fenster\", \"offen\": false, \"id\"}], \"oeffnungen\": [{\"von\", \"bis\"}], "
      "\"beschriftungen\": [{\"pos\", \"text\"}], \"hintergrund\": \"fels|erde|gras|wasser|schwarz\", \"meterProFeld\": 1.5}. "
      "Raumumrisse werden zu Wänden; überlappende Räume verschmelzen, aneinanderstoßende bekommen eine Wand; "
      "Türen und Öffnungen schneiden die Wand auf (müssen auf der Wandlinie liegen). Ohne \"bild\" zeichnet das Tool die "
      "Karte selbst (Geheimtüren sehen wie Wand aus, Beschriftungen sehen Spieler!). Mit \"bild\" (Pfad relativ zum "
      "Kampagnenordner) + \"zelle_px\" + \"versatz\" [px, px] werden die Wände über das vorhandene Bild gelegt. "
      "Gleiche ID ersetzt die Karte. Danach vorschau (barrieren=true, spieler=true) prüfen.",
      {"datei": S("Pfad relativ zum Kampagnenordner (.json, .dd2vtt, .uvtt)"), "daten": O("Kartenformat direkt als Objekt"),
       "id": S("Karten-ID (überschreibt die aus den Daten)"), "name": S("Anzeigename"),
       "aktiv": B("Karte aktivieren und Sicht aufdecken"),
       "sc": {"type": "array", "description": "SC platzieren (aktiviert die Karte): [{\"char_id\", \"x\", \"y\"}]",
              "items": {"type": "object", "properties": {"char_id": {"type": "string"}, "x": {"type": "integer"},
                                                         "y": {"type": "integer"}}, "required": ["char_id", "x", "y"]}}},
      gruppe="Karte")
def t_karte_import(a):
    return ST.karte_import(a.get("datei"), a.get("daten"), a.get("id"), a.get("name"), a.get("aktiv", False), a.get("sc"))


@tool("karte_export", "Karte mit ihren (korrigierten) Wänden und Türen ins Spieltisch-Kartenformat sichern "
      "(sl/karten/<id>.karte.json, wieder einlesbar mit karte_import).", {"id": S("Karten-ID")}, ["id"], gruppe="Karte")
def t_karte_export(a):
    return ST.karte_export(a["id"])


@tool("karte_aktivieren", "Karte aktiv schalten (Spieler sehen sie; wird automatisch bekannt).", {"id": S("Karten-ID")}, ["id"], gruppe="Karte")
def t_karte(a):
    return ST.karte(a["id"]) or f"Karte {a['id']} aktiv"


@tool("karte_bekannt", "Karte in die Unterlagen der Spieler aufnehmen (bekannt=false entfernt).",
      {"id": S("Karten-ID"), "bekannt": B("Standard true"), "legende": S("Handout-ID mit Legende")}, ["id"], gruppe="Karte")
def t_bekannt(a):
    return ST.bekannt(a["id"], nein=not a.get("bekannt", True), legende=a.get("legende")) or "ok"


@tool("raster", "Raster/Einstellungen einer Karte korrigieren: zelle (px pro Feld), ox/oy (Versatz px), meter pro Feld, "
      "Wände sperren Bewegung, automatischer Nebel nach SC-Bewegung, Standard-Sichtweite.",
      {"karte": KARTE, "zelle": N("px pro Feld"), "ox": N("Versatz X px"), "oy": N("Versatz Y px"), "meter": N("Meter pro Feld"),
       "waende": S("Bewegung durch Wände sperren", ["ein", "aus"]), "nebel_auto": S("Auto-Nebel", ["ein", "aus", "standard"]),
       "sicht_felder": I("Standardsichtweite in Feldern")}, gruppe="Karte")
def t_raster(a):
    return ST.raster(a.get("karte"), a.get("zelle"), a.get("ox"), a.get("oy"), a.get("meter"), a.get("waende"),
                     a.get("nebel_auto"), a.get("sicht_felder")) or "Raster gesetzt"


@tool("vorschau", "Kartenbild mit Feldkoordinaten (rot), Tokens, Nebel (abgedunkelt) und optional Wänden (magenta) / Türen "
      "(blau, mit ID) – nur für den SL. spieler=true zeigt die Spieleransicht. Für Details einen bereich wählen.",
      {"karte": KARTE, "bereich": L("[x0, y0, x1, y1] in Feldern", {"type": "integer"}, 4), "spieler": B("Spieleransicht"),
       "barrieren": B("Wände/Türen einzeichnen"), "raster": I("Beschriftung alle N Felder (Standard 5)"),
       "zoom": N("Zoom (Standard 0.6)"), "max_kante": I("längste Kante in px (Standard 1600)")}, lesen=True, gruppe="Karte")
def t_vorschau(a):
    daten, info = ST.vorschau(a.get("karte"), a.get("bereich"), a.get("spieler", False), a.get("raster") or 5,
                              a.get("barrieren", False), a.get("zoom") or 0.6, a.get("max_kante") or 1600, format="jpg")
    return bild(daten, "image/jpeg", info)


@tool("nebel", "Nebel von Hand auf- oder zudecken: rechteck [x0,y0,x1,y1], kreis [x,y,r] oder alles.",
      {"aktion": S("Aktion", ["aufdecken", "verdecken"]), "form": S("Form", ["rechteck", "kreis", "alles"]),
       "felder": L("rechteck: x0 y0 x1 y1 | kreis: x y r", {"type": "integer"}), "karte": KARTE}, ["aktion", "form"], gruppe="Nebel")
def t_nebel(a):
    return ST.nebel(a["aktion"] == "aufdecken", a["form"], a.get("felder"), a.get("karte")) or f"{a['aktion']}: {a['form']}"


@tool("abdecken", "Abdeckung (Rechteck, das auch aufgedeckt dunkel bleibt) setzen oder entfernen.",
      {"felder": L("[x0, y0, x1, y1]", {"type": "integer"}, 4), "entfernen": B("Abdeckung entfernen"), "karte": KARTE},
      ["felder"], gruppe="Nebel")
def t_abdecken(a):
    return ST.abdecken(a["felder"], a.get("entfernen", False), a.get("karte")) or "ok"


@tool("sicht", "Sichtlinien-Aufdecken jetzt einmalig für alle SC der Karte.", {"karte": KARTE}, gruppe="Nebel")
def t_sicht(a):
    return ST.sicht(a.get("karte")) or "Sicht aktualisiert"


@tool("sicht_teilen", "Geteilte Sicht: char sieht zusätzlich, was partner sieht (entfernen=true hebt auf).",
      {"char": S("Charakter-ID"), "partner": S("Charakter-ID"), "entfernen": B("aufheben")}, ["char"], gruppe="Nebel")
def t_sichtteilen(a):
    return ST.sichtteilen(a["char"], a.get("partner"), a.get("entfernen", False))


@tool("nebel_modus", "Nebelmodus der Karte: sicht = stufenloser Sichtpolygon-Nebel, der an erkannten Wänden stoppt "
      "(erkennt Barrieren automatisch, falls noch keine da), raster = Feldraster.",
      {"modus": S("Modus", ["sicht", "raster"]), "karte": KARTE}, ["modus"], gruppe="Nebel")
def t_nebel_modus(a):
    return ST.nebel_modus(a["modus"], a.get("karte"))


@tool("barrieren_erkennen", "Wände und Türen im Kartenbild automatisch erkennen (behält manuelle Barrieren, Löschbereiche "
      "und Türzustände). Danach mit vorschau (barrieren=true) prüfen. Importierte Karten (karte_import) sind geschützt.",
      {"karte": KARTE, "erzwingen": B("auch importierte, exakte Wände durch Erkennung ersetzen")}, gruppe="Barrieren")
def t_barr_erkennen(a):
    return ST.barrieren("erkennen", karte=a.get("karte"), erzwingen=a.get("erzwingen", False))


@tool("barrieren_liste", "Türen/Fenster/manuelle Barrieren einer Karte mit IDs, Zustand und Feldkoordinaten.",
      {"karte": KARTE}, lesen=True, gruppe="Barrieren")
def t_barr_liste(a):
    return ST.barrieren("liste", karte=a.get("karte"))


@tool("barriere_neu", "Barriere von Hand einziehen (z. B. Lücke in einer Wand schließen, Tür, Geheimtür, Fenster). "
      "Koordinaten = Gitterpunkte in Feldern, halbe erlaubt.",
      {"typ": S("Typ", ["wand", "tuer", "geheimtuer", "fenster"]), "von": FELD2, "bis": FELD2,
       "einseitig": S("blockiert nur von dieser Seite (Blick von→bis)", ["links", "rechts"]), "id": S("eigene ID"),
       "karte": KARTE}, ["typ", "von", "bis"], gruppe="Barrieren")
def t_barr_neu(a):
    return ST.barrieren("neu", karte=a.get("karte"), typ=a["typ"], von=a["von"], bis=a["bis"], einseitig=a.get("einseitig"),
                        id=a.get("id"))


@tool("barriere_aendern", "Typ oder Einseitigkeit einer Barriere ändern (z. B. erkannte Tür -> geheimtuer).",
      {"id": S("Barrieren-ID"), "typ": S("Typ", ["wand", "tuer", "geheimtuer", "fenster"]),
       "einseitig": S("Seite", ["links", "rechts"]), "karte": KARTE}, ["id"], gruppe="Barrieren")
def t_barr_aendern(a):
    return ST.barrieren("aendern", karte=a.get("karte"), ids=[a["id"]], typ=a.get("typ"), einseitig=a.get("einseitig")) or "geändert"


@tool("barrieren_entfernen", "Barrieren per ID löschen und/oder erkannte Wandstücke in einem Feldbereich ignorieren "
      "(z. B. Kreise um Raumnummern: Kreis ±1,1 Felder).",
      {"ids": L("Barrieren-IDs"), "bereich": L("[x0, y0, x1, y1] in Feldern", {"type": "number"}, 4), "karte": KARTE},
      gruppe="Barrieren")
def t_barr_weg(a):
    return ST.barrieren("weg", karte=a.get("karte"), ids=a.get("ids"), bereich=a.get("bereich"))


@tool("barrieren_bereiche_frei", "Alle Löschbereiche (barrieren_entfernen mit bereich) wieder aufheben.", {"karte": KARTE},
      gruppe="Barrieren")
def t_barr_frei(a):
    return ST.barrieren("frei", karte=a.get("karte")) or "Löschbereiche aufgehoben"


@tool("tuer", "Tür öffnen/schließen per ID oder nächste Tür bei einem Feld; ohne offen = umschalten. Zieht bei Auto-Nebel die Sicht nach.",
      {"ids": L("Tür-IDs"), "bei": FELD2, "offen": B("true = öffnen, false = schließen"), "karte": KARTE}, gruppe="Barrieren")
def t_tuer(a):
    o = a.get("offen")
    return ST.tuer(a.get("ids"), a.get("bei"), auf=o is True, zu=o is False, karte=a.get("karte"))


@tool("karte_einrichten", "Komplette Einrichtung einer Karte für den Sichtnebel in einem Schritt: Barrieren erkennen, "
      "Nebelmodus sicht, Auto-Nebel ein, Wände-Sperre wählbar, optional alten Nebel löschen, aktivieren, "
      "SC platzieren und Sicht aufdecken. Danach vorschau (spieler/barrieren) prüfen.",
      {"karte": S("Karten-ID"), "aktivieren": B("Karte aktiv schalten (Standard true)"),
       "waende_sperren": B("Bewegung durch erkannte Wände sperren (Standard false)"),
       "nebel_zuruecksetzen": B("alten Nebel verdecken (Standard true)"),
       "sc": {"type": "array", "description": "SC platzieren: [{\"char_id\": \"aritian\", \"x\": 3, \"y\": 4}, …]",
              "items": {"type": "object", "properties": {"char_id": {"type": "string"}, "x": {"type": "integer"},
                                                         "y": {"type": "integer"}}, "required": ["char_id", "x", "y"]}}},
      ["karte"], gruppe="Karte")
def t_karte_einrichten(a):
    kid = a["karte"]
    from bereiche.karte import barrieren as Bar
    vorhanden = Bar.laden(ST.kamp["sl"], kid)
    if vorhanden and vorhanden.get("quelle") == "import":
        aus = ["Wände aus Import übernommen (keine Erkennung)"]
    else:
        aus = [ST.barrieren("erkennen", karte=kid)]
    if a.get("aktivieren", True):
        ST.karte(kid)
        aus.append(f"Karte {kid} aktiv")
    ST.nebel_modus("sicht", kid)
    ST.raster(karte=kid, nebel_auto="ein", waende="ein" if a.get("waende_sperren") else "aus")
    if a.get("nebel_zuruecksetzen", True):
        ST.nebel(False, "alles", karte=kid)
    aus.append("Nebelmodus sicht, Auto-Nebel ein")
    for s in a.get("sc") or []:
        ST.sc_platzieren(s["char_id"], s["x"], s["y"])
        aus.append(f"{s['char_id']} bei ({s['x']},{s['y']})")
    if a.get("aktivieren", True):
        aus.append(ST.sicht(kid) or "Sicht aufgedeckt")
    return "\n".join(aus)


# ------------------------------------------------------------------ Charaktere / EP / Aufstieg

@tool("charaktere", "Alle Charaktere (ID, Name, Klasse, TP, EP).", lesen=True, gruppe="Charakter")
def t_charaktere(a):
    return ST.charaktere()


@tool("charakter", "Charakterbogen als JSON (wirksame Werte inkl. Modi). felder begrenzt die Ausgabe (z. B. [\"tp\", \"rw\", \"fertigkeiten\"]).",
      {"id": S("Charakter-ID"), "felder": L("nur diese Felder")}, ["id"], lesen=True, gruppe="Charakter")
def t_charakter(a):
    return json.dumps(ST.charakter(a["id"], a.get("felder")), ensure_ascii=False, indent=1)


@tool("char_setzen", "Charakterwerte setzen über Punktpfade, z. B. {\"rw.REF\": 3, \"zauberliste.23.verbraucht\": 1, \"ausruestung\": \"…\"}.",
      {"id": S("Charakter-ID"), "werte": O("Pfad -> Wert")}, ["id", "werte"], gruppe="Charakter")
def t_char(a):
    return ST.char(a["id"], a["werte"]) or "gesetzt"


@tool("ep", "Erfahrung vergeben (Gesamtbetrag wird geteilt): aus HG besiegter Gegner-Token, zusätzlichen HG oder festem Betrag.",
      {"gegner": L("Token-IDs besiegter Gegner"), "hg": L("zusätzliche HG, z. B. [\"1/3\", \"2\"]"), "ep": I("fester Betrag (gesamt)"),
       "an": L("Charakter-IDs (Standard: alle SC auf der Karte)"), "grund": S("Grund")}, gruppe="Charakter")
def t_ep(a):
    return ST.ep(a.get("gegner"), a.get("hg"), a.get("ep") or 0, a.get("an"), a.get("grund") or "Begegnung")


@tool("aufstieg_zeigen", "Eingereichten Aufstiegsantrag eines Spielers anzeigen und prüfen.", {"id": S("Charakter-ID")}, ["id"],
      lesen=True, gruppe="Aufstieg")
def t_aufstieg(a):
    return ST.aufstieg(a["id"])


@tool("aufstieg_fertig", "Stufenaufstieg abschließen (nachdem Werte eingetragen sind).",
      {"id": S("Charakter-ID"), "klasse": S("neuer Klassentext, z. B. Kleriker 2"), "erzwingen": B("ohne Antrag abschließen")},
      ["id"], gruppe="Aufstieg")
def t_aufstieg_fertig(a):
    return ST.aufstieg_fertig(a["id"], a.get("klasse"), a.get("erzwingen", False)) or "Aufstieg abgeschlossen"


@tool("aufstieg_zurueck", "Aufstiegsantrag mit Begründung zur Überarbeitung zurückgeben.",
      {"id": S("Charakter-ID"), "grund": S("Begründung")}, ["id"], gruppe="Aufstieg")
def t_aufstieg_zurueck(a):
    return ST.aufstieg_zurueck(a["id"], a.get("grund") or "") or "zurückgegeben"


@tool("aufstieg_abbrechen", "Offenen Aufstieg verwerfen (TP-Wurf entfällt).", {"id": S("Charakter-ID")}, ["id"], gruppe="Aufstieg")
def t_aufstieg_abbrechen(a):
    return ST.aufstieg_abbrechen(a["id"]) or "abgebrochen"


@tool("rast", "Rast: Zauberplätze zurücksetzen (alle oder ein Charakter), Modi laufen 8 Stunden ab.",
      {"char": S("Charakter-ID (Standard alle)")}, gruppe="Rast")
def t_rast(a):
    return ST.rast(a.get("char")) or "Rast"


@tool("charaktere_importieren", "Charaktere aus ausfüllbaren PDF-Bögen importieren (Pfade relativ zum Kampagnenordner).",
      {"pdfs": L("PDF-Pfade"), "ueberschreiben": B("vorhandene ersetzen")}, ["pdfs"], gruppe="Charakter")
def t_import(a):
    return ST.charaktere_importieren(a["pdfs"], a.get("ueberschreiben", False))


# ------------------------------------------------------------------ Kasse / Beute

@tool("kasse", "Gruppenkasse ändern (Standard: addieren; setzen=true setzt die Werte). Gibt den neuen Kassenstand zurück.",
      {"kp": I("Kupfer"), "sp": I("Silber"), "gp": I("Gold"), "pp": I("Platin"), "setzen": B("Werte setzen statt addieren"),
       "grund": S("Grund")}, gruppe="Kasse")
def t_kasse(a):
    return ST.kasse(a.get("kp"), a.get("sp"), a.get("gp"), a.get("pp"), a.get("setzen", False), a.get("grund") or "").split("\n")[0]


@tool("beute", "Gegenstand anlegen.", {"name": S("Name"), "an": S("Charakter-ID oder gruppe"), "ort": S("Ort (Standard dabei)"),
                                       "anzahl": I("Anzahl"), "notiz": S("Notiz")}, ["name"], gruppe="Kasse")
def t_beute(a):
    return ST.beute(a["name"], a.get("an") or "gruppe", a.get("ort") or "dabei", a.get("anzahl") or 1, a.get("notiz") or "")


@tool("item", "Gegenstand ändern (Träger, Ort, Anzahl, Name, Notiz) oder entfernen.",
      {"id": I("Gegenstands-ID"), "an": S("neuer Träger"), "ort": S("Ort"), "anzahl": I("Anzahl"), "name": S("Name"),
       "notiz": S("Notiz"), "entfernen": B("löschen")}, ["id"], gruppe="Kasse")
def t_item(a):
    return ST.item(a["id"], a.get("an"), a.get("ort"), a.get("anzahl"), a.get("name"), a.get("notiz"), a.get("entfernen", False)) or "ok"


@tool("ausruestung", "Kasse und Ausrüstung aller Träger.", lesen=True, gruppe="Kasse")
def t_ausruestung(a):
    return ST.ausruestung()


@tool("zauberbuch", "Zauber ins Zauberbuch eintragen (oder entfernen=true).",
      {"char": S("Charakter-ID"), "zauber": L("Zaubernamen"), "grad": I("Grad"), "entfernen": B("austragen")},
      ["char", "zauber"], gruppe="Kasse")
def t_buch(a):
    return ST.buch(a["char"], a["zauber"], a.get("grad") or 0, a.get("entfernen", False)) or "ok"


@tool("zauber_suchen", "Zauberdatenbank (deutsches PRD, ~1860 Zauber) durchsuchen: nach Namensteil, Klasse, Grad, Schule. "
      "Eine Zeile je Zauber (Schule, Klassen/Grade, Kurzbeschreibung). Mit klasse+grad z. B. alle Barde-3-Zauber.",
      {"text": S("Teil des Namens (bei volltext auch im Beschreibungstext)"), "klasse": S("z. B. Magier, Barde, Kleriker, Druide"),
       "grad": I("Zaubergrad (mit klasse: Grad dieser Klasse)"), "schule": S("z. B. Hervorrufung, Illusion"),
       "volltext": B("auch Beschreibungen durchsuchen"), "max_treffer": I("Standard 40")}, lesen=True, gruppe="Zauber")
def t_zauber_suchen(a):
    return ST.zauber_suchen(a.get("text"), a.get("klasse"), a.get("grad"), a.get("schule"), a.get("volltext", False),
                            a.get("max_treffer") or 40)


@tool("zauber_info", "Vollständige Zauberbeschreibung aus dem PRD: Schule, Grade aller Klassen, Zeitaufwand, Komponenten, "
      "Reichweite, Ziel/Effekt/Bereich, Wirkungsdauer, Rettungswurf, ZR, Text, Quelle.",
      {"name": S("Zaubername (deutsch)"), "langtext": B("Beschreibungstext mitliefern (Standard true)")}, ["name"],
      lesen=True, gruppe="Zauber")
def t_zauber_info(a):
    return ST.zauber_info(a["name"], a.get("langtext", True))


# ------------------------------------------------------------------ Regeln (PRD: Grundregelwerk, Expertenregeln + Hausregeln)

@tool("regel_suchen", "Regelfrage in der lokalen Regeldatenbank nachschlagen (PF1, deutsches PRD: Grundregelwerk + Expertenregeln, ohne Zauber) "
      "plus Hausregeln der Kampagne (sl/hausregeln.md, haben Vorrang). Liefert die besten Abschnitte kurz mit ID und Quelle; "
      "Volltext mit regel_lesen. IMMER vor einer Regelentscheidung nutzen statt aus dem Gedächtnis; Websuche nur, wenn nichts kommt. "
      "Abkürzungen gehen (GA, RK, KMB, KMV, TP, SG, GAB, RW …).",
      {"frage": S("Stichworte oder Frage, z. B. „Gelegenheitsangriff Bewegung verlassen“, „Hinterhältiger Angriff kritischer Treffer“"),
       "kategorie": S("Kapitel eingrenzen, z. B. Kampf, Magie, Ausrüstung, Fertigkeiten, Talente, Anhang, Umgebung, Spielleitung"),
       "buch": S("Buch eingrenzen: Grundregelwerk oder Expertenregeln (Treffer aus Expertenregeln sind mit EXP markiert)"),
       "typ": S("nur dieser Eintragstyp", ["regel", "talent", "zustand", "fertigkeit", "klasse", "prestigeklasse", "volk", "tabelle"]),
       "max_treffer": I("Standard 5, höchstens 20")}, ["frage"], lesen=True, gruppe="Regeln")
def t_regel_suchen(a):
    return ST.regel_suchen(a["frage"], a.get("kategorie"), a.get("buch"), a.get("typ"), a.get("max_treffer") or 5)


@tool("regel_lesen", "Volltext eines Regel-Eintrags: eintrag = ID aus regel_suchen (Zahl), H<n> für eine Hausregel, oder Titel. "
      "Nur seite (z. B. „Kampf“) = Inhaltsverzeichnis mit IDs; seite + abschnitt = Abschnitt dieser Seite. "
      "Lange Abschnitte werden gekürzt (weiter mit ab). Ohne Angaben: Stand der Datenbank.",
      {"eintrag": S("ID (z. B. 1234), H2 oder Titel"), "seite": S("Kapitel/Seite, z. B. Kampf, Anhang, Fertigkeiten/Akrobatik"),
       "abschnitt": S("Überschrift innerhalb der Seite"), "ab": I("ab Zeichen (Fortsetzung)"),
       "max_zeichen": I("Standard 4000")}, lesen=True, gruppe="Regeln")
def t_regel_lesen(a):
    return ST.regel_lesen(a.get("eintrag"), a.get("seite"), a.get("abschnitt"), a.get("ab") or 0, a.get("max_zeichen") or 4000)


@tool("talent_info", "Talent nachschlagen (Grundregelwerk + Expertenregeln): mit name voller Text (Voraussetzungen, Vorteil, Normal, Speziell); "
      "ohne name Liste, filterbar nach voraussetzung (Textteil) und art (Kampf, Metamagie, Erschaffung, Kritischer Treffer).",
      {"name": S("Talentname, z. B. Beweglichkeit"), "voraussetzung": S("z. B. Ausweichen"), "art": S("z. B. Kampf")},
      lesen=True, gruppe="Regeln")
def t_talent_info(a):
    return ST.regel_schnell("talent", a.get("name"), a.get("voraussetzung"), a.get("art"))


@tool("zustand_info", "Zustand nachschlagen (Anhang Zustände: Hilflos, Gelähmt, Betäubt, Liegend …); ohne name: Liste aller Zustände.",
      {"name": S("Zustand, z. B. Hilflos")}, lesen=True, gruppe="Regeln")
def t_zustand_info(a):
    return ST.regel_schnell("zustand", a.get("name"))


@tool("fertigkeit_info", "Fertigkeit nachschlagen (Attribut, Proben, SG-Tabellen, Aktion, Wiederholung …); ohne name: Liste.",
      {"name": S("Fertigkeit, z. B. Akrobatik")}, lesen=True, gruppe="Regeln")
def t_fertigkeit_info(a):
    return ST.regel_schnell("fertigkeit", a.get("name"))


_regeln_lauf = {"thread": None, "log": [], "ergebnis": None}


@tool("regeln_aktualisieren", "Regeldatenbank aus dem PRD (prd.5footstep.de) aktualisieren: prüft jede Inhaltsseite (ETag/Inhaltsvergleich), "
      "übernimmt geänderte/neue Seiten (1 s Pause je Abruf, ca. 20 Minuten), baut bei Änderungen den Index neu. Läuft im Hintergrund: "
      "erneuter Aufruf zeigt den Fortschritt. nur_index=true baut nur den Index aus der vorhandenen Datenbank neu (ohne Netz).",
      {"nur_index": B("nur Index neu (ohne Netz)")}, gruppe="Regeln")
def t_regeln_aktualisieren(a):
    th = _regeln_lauf["thread"]
    if th is not None and th.is_alive():
        return "Aktualisierung läuft …\n" + "\n".join(_regeln_lauf["log"][-3:])
    if th is not None and _regeln_lauf["ergebnis"] is not None:
        erg, _regeln_lauf["thread"], _regeln_lauf["ergebnis"] = _regeln_lauf["ergebnis"], None, None
        return "Fertig:\n" + erg
    _regeln_lauf["log"] = []

    def lauf():
        try:
            _regeln_lauf["ergebnis"] = ST.regeln_aktualisieren(a.get("nur_index", False), _regeln_lauf["log"].append)
        except SLFehler as e:
            _regeln_lauf["ergebnis"] = f"FEHLER: {e}"
    _regeln_lauf["thread"] = threading.Thread(target=lauf, daemon=True)
    _regeln_lauf["thread"].start()
    _regeln_lauf["thread"].join(20)  # kurze Läufe (nur Index, keine Änderungen) direkt beantworten
    if not _regeln_lauf["thread"].is_alive():
        erg, _regeln_lauf["thread"], _regeln_lauf["ergebnis"] = _regeln_lauf["ergebnis"], None, None
        return erg
    return "Aktualisierung gestartet (läuft im Hintergrund). Später regeln_aktualisieren erneut aufrufen für den Stand."


# ------------------------------------------------------------------ Notizen / Quellen

@tool("notizen_liste", "SL-Notizdateien (sl/notizen) mit Zeilenzahl.", lesen=True, gruppe="Notizen")
def t_notizen_liste(a):
    return ST.notizen_liste()


@tool("notiz_lesen", "SL-Notizdatei lesen (mit Zeilennummern, max. 600 Zeilen je Aufruf).",
      {"datei": S("Dateiname, z. B. kapitel1.md"), "von": I("ab Zeile"), "bis": I("bis Zeile")}, ["datei"], lesen=True, gruppe="Notizen")
def t_notiz_lesen(a):
    return ST.notiz_lesen(a["datei"], a.get("von") or 1, a.get("bis"))


@tool("notiz_anhaengen", "Text an eine Notizdatei anhängen, optional ans Ende eines Abschnitts (Überschrift enthält abschnitt, "
      "z. B. „Laufende Notizen“). Legt die Datei an, falls nötig.",
      {"datei": S("Dateiname"), "text": S("Text (Markdown)"), "abschnitt": S("Überschrift (Teilstring)")}, ["datei", "text"],
      gruppe="Notizen")
def t_notiz_anhaengen(a):
    return ST.notiz_anhaengen(a["datei"], a["text"], a.get("abschnitt"))


@tool("notiz_ersetzen", "Textstelle in einer Notizdatei ersetzen (alt muss genau einmal vorkommen, sonst alle=true).",
      {"datei": S("Dateiname"), "alt": S("bisheriger Text"), "neu": S("neuer Text"), "alle": B("alle Vorkommen")},
      ["datei", "alt", "neu"], gruppe="Notizen")
def t_notiz_ersetzen(a):
    return ST.notiz_ersetzen(a["datei"], a["alt"], a["neu"], a.get("alle", False))


@tool("notiz_schreiben", "Notizdatei neu schreiben (vorhandene nur mit ueberschreiben=true; alte Fassung wird gesichert).",
      {"datei": S("Dateiname"), "text": S("ganzer Inhalt"), "ueberschreiben": B("vorhandene ersetzen")}, ["datei", "text"],
      gruppe="Notizen")
def t_notiz_schreiben(a):
    return ST.notiz_schreiben(a["datei"], a["text"], a.get("ueberschreiben", False))


@tool("quellen_liste", "Abenteuertexte (sl/quellen) mit Zeilenzahl.", lesen=True, gruppe="Quellen")
def t_quellen_liste(a):
    return ST.quellen_liste()


@tool("quelle_lesen", "Abenteuertext lesen (Zeilenbereich, max. 400 Zeilen je Aufruf).",
      {"datei": S("Dateiname"), "von": I("ab Zeile"), "bis": I("bis Zeile")}, ["datei"], lesen=True, gruppe="Quellen")
def t_quelle_lesen(a):
    return ST.quelle_lesen(a["datei"], a.get("von") or 1, a.get("bis"))


@tool("suchen", "Volltextsuche (ohne Groß/Klein) in Quellen und/oder Notizen; Treffer mit Zeilennummer und Kontext.",
      {"muster": S("Suchtext"), "wo": S("Bereich (Standard quellen)", ["quellen", "notizen", "alle"]), "datei": S("nur diese Datei"),
       "regex": B("muster ist ein regulärer Ausdruck"), "kontext": I("Zeilen Kontext (Standard 1)"),
       "max_treffer": I("Standard 40")}, ["muster"], lesen=True, gruppe="Quellen")
def t_suchen(a):
    return ST.suchen(a["muster"], a.get("wo") or "quellen", a.get("datei"), a.get("regex", False),
                     1 if a.get("kontext") is None else a["kontext"], a.get("max_treffer") or 40)


@tool("quelle_aus_pdf", "Text einer Abenteuer-PDF nach sl/quellen/<datei>.txt übernehmen (mit Seitenmarken "
      "„=== Seite N ===“, passend zu material_vorschau/karte_neu). Danach mit suchen/quelle_lesen nutzen.",
      {"pdf": S("PDF-Pfad relativ zum Kampagnenordner"), "datei": S("Name der Textdatei (Standard: aus dem PDF-Namen)"),
       "seiten": L("[von, bis] (Standard alle)", {"type": "integer"}), "ueberschreiben": B("vorhandene Datei ersetzen")},
      ["pdf"], gruppe="Quellen")
def t_quelle_aus_pdf(a):
    return ST.quelle_aus_pdf(a["pdf"], a.get("datei"), a.get("seiten"), a.get("ueberschreiben", False))


# ------------------------------------------------------------------ Kampagnen verwalten

@tool("kampagnen_liste", "Alle Kampagnen (Ordner, Name, Port, Server an/aus, MCP eingerichtet).", lesen=True,
      gruppe="Verwaltung", verwaltung=True)
def t_kampagnen_liste(a):
    from sl_api import kampagnen_liste
    return kampagnen_liste(WURZEL)


@tool("kampagne_neu", "Neue Kampagne anlegen (neben den vorhandenen): Ordner aus der Vorlage, kampagne.json mit freiem Port, "
      ".mcp.json für diesen MCP-Server, CLAUDE.md (MCP-Leitfaden), sl/notizen/kapitel1.md; optional Abenteuer-PDFs nach "
      "Material/ kopieren und ihren Text nach sl/quellen/ übernehmen. Gespielt wird danach in einer neuen Sitzung im "
      "neuen Ordner (einmal als vertrauenswürdig bestätigen).",
      {"name": S("Kampagnenname"), "ordner": S("Ordnername (Standard: aus dem Namen)"), "port": I("Port (Standard: nächster freier ab 8780)"),
       "pdfs": L("Abenteuer-PDFs (absolute Pfade oder relativ zum Kampagnen-Hauptordner)"),
       "quellen": B("Text der PDFs nach sl/quellen (Standard true)"),
       "sperre": B(".claude/settings.json mit Datei-Sperre anlegen (Standard false)"),
       "ep_tempo": S("EP-Tempo", ["langsam", "mittel", "schnell"])}, ["name"], gruppe="Verwaltung", verwaltung=True)
def t_kampagne_neu(a):
    from sl_api import kampagne_neu
    return kampagne_neu(WURZEL, a["name"], a.get("ordner"), a.get("port"), a.get("pdfs"), a.get("quellen", True),
                        a.get("sperre", False), a.get("ep_tempo") or "mittel")


@tool("pfade_reparieren", "Pfade (Python, Programm, Kampagne) in .mcp.json und .claude/launch.json einer Kampagne neu "
      "schreiben, z. B. nach Verschieben des Ordners oder auf einem anderen Rechner. Danach Sitzung neu starten.",
      {"ordner": S("Ordnername der Kampagne unter dem Kampagnen-Hauptordner")}, ["ordner"], gruppe="Verwaltung",
      verwaltung=True)
def t_pfade_reparieren(a):
    from sl_api import pfade_reparieren
    o = a["ordner"]
    if not o or any(c in o for c in "/\\:") or o in (".", ".."):
        raise SLFehler("Ungültiger Ordnername")
    return pfade_reparieren(WURZEL / o)


# ------------------------------------------------------------------ Server

@tool("server_status", "Läuft der Spieltisch-Server dieser Kampagne? (Port, Spieler-URL)", lesen=True, gruppe="Server")
def t_server_status(a):
    if not ST.laeuft():
        return f"Server »{ST.kamp['name']}« läuft NICHT (Port {ST.port}). server_starten oder preview_start."
    z = ST.zustand()
    return f"Server »{ST.kamp['name']}« läuft: Spieler {ST.url.replace('127.0.0.1', 'localhost')}/ | SL-Status {z['slStatus']}"


@tool("server_starten", "Spieltisch-Server dieser Kampagne im Hintergrund starten (falls er nicht läuft).", gruppe="Server")
def t_server_starten(a):
    return ST.server_starten()


# ------------------------------------------------------------------ Protokoll (JSON-RPC über stdio)

ANLEITUNG = """Spieltisch-SL-Werkzeuge. Du bist Spielleiter; die Spieler handeln in der Web-App.
Ablauf: stand + protokoll lesen -> offene Aktionen beantworten (erzaehle) -> warte (blockiert bis zur nächsten Spieleraktion,
bei Timeout erneut aufrufen) -> reagieren -> warte … Ohne erzaehle reagiert? Dann status_setzen bereit vor warte.
Spoilerschutz: Ausgaben dieser Tools (Notizen, Quellen, Vorschau, verborgene Token) nie an die Spieler weitergeben.
Regeln (Pathfinder 1, nicht D&D 5e/PF2): vor jeder Regelentscheidung regel_suchen (bzw. talent_info/zustand_info/fertigkeit_info,
Zauber: zauber_info) statt aus dem Gedächtnis; HAUSREGEL-Treffer haben Vorrang; Websuche nur, wenn die Datenbank nichts liefert.
Neue Karte: material_liste/material_vorschau -> karte_neu -> vorschau (Raster prüfen, ggf. raster) -> karte_einrichten
-> vorschau barrieren=true, Kreise/Beschriftungen mit barrieren_entfernen bereich, Lücken mit barriere_neu -> vorschau spieler=true."""

ANLEITUNG_VERWALTUNG = """Spieltisch-Kampagnenverwaltung (ohne laufende Kampagne): kampagnen_liste zeigt die Kampagnen,
kampagne_neu legt eine neue an (Ordner, Port, .mcp.json, CLAUDE.md, Abenteuer-PDFs + Quelltext). Gespielt wird danach in
einer eigenen Sitzung im neuen Kampagnenordner."""
VERWALTUNG = False
WURZEL = None

_schreib_lock = threading.Lock()
_laufend = {}  # Anfrage-ID -> threading.Event (Abbruch)
_warte_aktiv = threading.Lock()


def senden(nachricht):
    daten = json.dumps(nachricht, ensure_ascii=False).encode("utf-8") + b"\n"
    with _schreib_lock:
        _AUS.write(daten)
        _AUS.flush()


def antwort(rid, ergebnis=None, fehler=None):
    m = {"jsonrpc": "2.0", "id": rid}
    if fehler:
        m["error"] = fehler
    else:
        m["result"] = ergebnis
    senden(m)


def tool_aufruf(rid, params):
    name = params.get("name")
    args = params.get("arguments") or {}
    t = TOOLS.get(name)
    if t is not None and VERWALTUNG and not t["verwaltung"]:
        t = None
    if t is None:
        return antwort(rid, fehler={"code": -32602, "message": f"Unbekanntes Tool {name!r}"})
    abbruch = threading.Event()
    _laufend[rid] = abbruch
    token = (params.get("_meta") or {}).get("progressToken")

    def fortschritt(wert, gesamt, text):
        if token is not None and not abbruch.is_set():
            senden({"jsonrpc": "2.0", "method": "notifications/progress",
                    "params": {"progressToken": token, "progress": wert, "total": gesamt, "message": text}})
    try:
        if name == "warte":
            if not _warte_aktiv.acquire(blocking=False):
                raise SLFehler("warte läuft bereits – nie zwei gleichzeitig")
            try:
                r = t["f"](args, abbruch=abbruch, fortschritt=fortschritt)
            finally:
                _warte_aktiv.release()
        else:
            r = t["f"](args)
        inhalt = r if isinstance(r, list) else [{"type": "text", "text": r if r else "ok"}]
        ergebnis = {"content": inhalt, "isError": False}
    except SLFehler as e:
        ergebnis = {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except (KeyError, TypeError, ValueError) as e:
        ergebnis = {"content": [{"type": "text", "text": f"Ungültige Angabe: {type(e).__name__}: {e}"}], "isError": True}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        ergebnis = {"content": [{"type": "text", "text": f"Interner Fehler: {type(e).__name__}: {e}"}], "isError": True}
    finally:
        _laufend.pop(rid, None)
    if not abbruch.is_set():
        antwort(rid, ergebnis)


def verarbeiten(m):
    methode = m.get("method")
    rid = m.get("id")
    p = m.get("params") or {}
    if methode == "initialize":
        v = p.get("protocolVersion")
        return antwort(rid, {"protocolVersion": v if v in VERSIONEN else VERSIONEN[0],
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": {"name": "spieltisch", "title": "Spieltisch – Kampagnenverwaltung" if VERWALTUNG else f"Spieltisch – {ST.kamp['name']}", "version": "1.0"},
                             "instructions": ANLEITUNG_VERWALTUNG if VERWALTUNG else ANLEITUNG})
    if methode == "ping":
        return antwort(rid, {})
    if methode == "tools/list":
        return antwort(rid, {"tools": [{k: v for k, v in t.items() if k not in ("f", "verwaltung")} for t in TOOLS.values()
                                       if t["verwaltung"] or not VERWALTUNG]})
    if methode == "tools/call":
        threading.Thread(target=tool_aufruf, args=(rid, p), daemon=True).start()
        return None
    if methode == "notifications/cancelled":
        e = _laufend.get(p.get("requestId"))
        if e:
            e.set()
        return None
    if methode and methode.startswith("notifications/"):
        return None
    if rid is not None:
        antwort(rid, fehler={"code": -32601, "message": f"Methode {methode!r} nicht unterstützt"})


def main():
    global ST, VERWALTUNG, WURZEL
    pfad = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    if "--kampagne" in sys.argv:
        pfad = sys.argv[sys.argv.index("--kampagne") + 1]
    if "--verwaltung" in sys.argv:  # Kampagnen-Wurzel (Ordner mit den Kampagnenordnern), keine Kampagne
        WURZEL = Path(sys.argv[sys.argv.index("--verwaltung") + 1]).resolve()
        VERWALTUNG = True
    elif pfad and Path(pfad).is_dir() and not (Path(pfad) / "kampagne.json").is_file():
        WURZEL, VERWALTUNG = Path(pfad).resolve(), True
    if VERWALTUNG:
        if not WURZEL.is_dir():
            print(f"spieltisch-mcp: Ordner fehlt: {WURZEL}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            ST = Spieltisch(pfad)
        except SLFehler as e:
            print(f"spieltisch-mcp: {e}", file=sys.stderr)
            sys.exit(1)
        ST.basis = ST.kamp["ordner"]  # relative Pfade (PDF, Bild) beziehen sich auf den Kampagnenordner
        WURZEL = ST.kamp["ordner"].parent
    # Erweiterungsmodule (DLLs) jetzt im Hauptthread laden: unter Windows hängt das Nachladen in einem
    # Worker-Thread, solange der Hauptthread blockierend von stdin liest.
    import numpy  # noqa: F401
    import pymupdf  # noqa: F401
    from bereiche.karte import karten  # noqa: F401
    from bereiche.karte import barrieren  # noqa: F401
    import import_charaktere  # noqa: F401
    from bereiche.karte import kartenformat  # noqa: F401
    from bereiche.wissen import regeln_abruf  # noqa: F401  (sqlite3, hashlib, ssl)
    if VERWALTUNG:
        print(f"spieltisch-mcp: Verwaltung {WURZEL}", file=sys.stderr)
    else:
        print(f"spieltisch-mcp: Kampagne »{ST.kamp['name']}« (Port {ST.port}), {len(TOOLS)} Tools", file=sys.stderr)
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            m = json.loads(zeile)
        except json.JSONDecodeError:
            senden({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        for einzel in (m if isinstance(m, list) else [m]):
            try:
                verarbeiten(einzel)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                if einzel.get("id") is not None:
                    antwort(einzel["id"], fehler={"code": -32603, "message": str(e)})


if __name__ == "__main__":
    main()
