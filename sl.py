"""Spielleiter-Werkzeug (Kommandozeile) für den Spieltisch.

Die Befehlslogik liegt in sl_api.py (gemeinsam mit dem MCP-Server mcp_server.py).

Beispiele:
  python sl.py [--kampagne PFAD] warte                         # blockiert bis zur nächsten Spieleraktion, gibt neue Ereignisse aus
  python sl.py erzaehle "Der Regen peitscht ..." --titel "Rodericksbucht"
  python sl.py token gegner "Goblin 1" 12 7 --tp 6 --verborgen
  python sl.py zieh g1 10 7
  python sl.py tp g1 -5
  python sl.py aufdecken rechteck 3 3 12 9     |  aufdecken kreis 8 6 4  |  aufdecken alles
  python sl.py karte-neu haus1 "Altes Haus" --pdf ../Bodenplaene.pdf --seite 1 --ausschnitt 0 0 .5 .47
  python sl.py vorschau [--bereich x0 y0 x1 y1] [--spieler]
"""
import argparse
import json
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent
sys.path.insert(0, str(BASIS))
from sl_api import Spieltisch, SLFehler, kv_werte  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# --kampagne PFAD (global, vor dem Befehl) / SPIELTISCH_KAMPAGNE / Suche aufwärts nach kampagne.json
if "--kampagne" in sys.argv:
    _i = sys.argv.index("--kampagne")
    _pfad = sys.argv[_i + 1]
    del sys.argv[_i:_i + 2]
else:
    _pfad = None
try:
    ST = Spieltisch(_pfad)
except SLFehler as _e:
    sys.exit(str(_e))
KAMP = ST.kamp


def aus(text):
    if text:
        print(text)


def _stdin(text):
    return text if text != "-" else sys.stdin.read()


def _char_werte(paare):
    return {k: (json.loads(v) if v[:1] in "-0123456789[{\"tfn" else v) for k, _, v in (w.partition("=") for w in paare)}


# ------------------------------------------------------------------ Befehle (dünne Hülle um sl_api)

def cmd_warte(a):
    """Wartet auf Spieleraktionen. Sammelt nach der ersten Aktion noch kurz weitere ein."""
    print(ST.warte(nachlauf=a.nachlauf))


def cmd_log(a):
    aus(ST.log(a.n))


def cmd_erzaehle(a):
    ST.erzaehle(_stdin(a.text), titel=a.titel)


def cmd_streiche(a):
    ST.streiche(a.ids)


def cmd_notiz(a):
    ST.notiz(a.text)


def cmd_status(a):
    ST.status(a.status)


def cmd_szene(a):
    ST.szene(a.titel, a.untertitel)


def cmd_token(a):
    print(ST.token(a.art, a.name, a.x, a.y, id=a.id, tp=a.tp, groesse=a.groesse, farbe=a.farbe, symbol=a.symbol,
                   verborgen=a.verborgen, rk=a.rk, rkb=a.rkb, rkf=a.rkf, ref=a.ref, wil=a.wil, zaeh=a.zaeh, hg=a.hg))


def cmd_setze(a):
    ST.setze(a.id, kv_werte(a.werte))


def cmd_zeige(a):
    ST.zeige(a.id, a.verbergen)


def cmd_taeuschung(a):
    print(ST.taeuschung(a.token, fuer=a.fuer, name=a.name, symbol=a.symbol, farbe=a.farbe, x=a.x, y=a.y,
                        groesse=a.groesse, art=a.art, sichtbar=a.sichtbar, weg=a.weg, schalter=a.schalter))


def cmd_weg(a):
    ST.weg(a.ids)


def cmd_zieh(a):
    aus(ST.zieh(a.id, a.x, a.y))


def cmd_tp(a):
    ST.tp(a.id, a.delta)


def cmd_zustand(a):
    ST.zustand_setzen(a.id, a.zustaende)


def cmd_aufdecken(a):
    ST.nebel(True, a.form, a.felder, a.karte)


def cmd_verdecken(a):
    ST.nebel(False, a.form, a.felder, a.karte)


def cmd_abdecken(a):
    ST.abdecken(a.felder, a.entfernen, a.karte)


def cmd_karte_neu(a):
    print(ST.karte_neu(a.id, a.name, pdf=a.pdf, seite=a.seite, ausschnitt=a.ausschnitt, zelle_pt=a.zelle_pt,
                       bild=a.bild, zelle_px=a.zelle_px, leer=a.leer, aktiv=a.aktiv))


def cmd_karte(a):
    ST.karte(a.id)


def cmd_bekannt(a):
    ST.bekannt(a.id, a.nein, a.legende)


def cmd_sicht(a):
    """Sichtlinien-Aufdecken einmalig für alle SC der Karte."""
    ST.sicht(a.karte)


def cmd_sichtteilen(a):
    """Geteilte Sicht: GOLEM sieht zusätzlich, was PARTNER sieht (Charakterfeld sichtVon)."""
    print(ST.sichtteilen(a.char, a.partner, a.weg))


def cmd_handout(a):
    ST.handout(a.id, None if a.weg else _stdin(a.text), titel=a.titel, weg=a.weg)


def cmd_raster(a):
    ST.raster(karte=a.karte, zelle=a.zelle, ox=a.ox, oy=a.oy, meter=a.meter, waende=a.waende,
              nebel_auto=a.nebel_auto, sicht_felder=a.sicht_felder)


def cmd_angriff(a):
    print(ST.angriff(a.angreifer, a.ziel, a.bonus, a.schaden, waffe=a.waffe, krit=a.krit, beruehrung=a.beruehrung,
                     fernkampf=a.fernkampf, mods=a.mod, gelegenheitsangriff=a.ga))


def cmd_modus(a):
    print(ST.modus(a.ziel, a.name, runden=a.runden, minuten=a.minuten, stunden=a.stunden, groesse=a.groesse,
                   wirkung=a.wirkung, quelle=a.quelle))


def cmd_modus_zeit(a):
    print(ST.modus_zeit(a.runden, a.minuten, a.stunden))


def cmd_zug(a):
    ST.zug(kv_werte(a.werte, nur_json=True))


def cmd_ini(a):
    ST.ini(a.aktion, name=a.name, wert=a.wert, token=a.token, verborgen=a.verborgen)


def cmd_wurf(a):
    print(ST.wurf(a.ausdruck, grund=a.grund, wer=a.wer, offen=a.offen))


def cmd_stand(a):
    print(ST.stand())


def cmd_vorschau(a):
    """Rendert die aktive Karte mit Feldkoordinaten und Tokens als PNG (für den SL)."""
    daten, _ = ST.vorschau(karte=a.karte, bereich=a.bereich, spieler=a.spieler, raster=a.raster,
                           barrieren=a.barrieren, zoom=a.zoom)
    ziel = Path(a.ausgabe) if a.ausgabe else KAMP["sl"] / "vorschau.png"
    ziel.write_bytes(daten)
    print(ziel)


def cmd_barrieren(a):
    """Barrieren (Wände, Türen, Fenster) einer Karte: erkennen, auflisten, ändern. Nur SL-Ausgaben."""
    aus(ST.barrieren(a.aktion, karte=a.karte, ids=a.ids, typ=a.typ, von=a.von, bis=a.bis, einseitig=a.einseitig,
                     id=a.id, bereich=a.bereich, erzwingen=a.erzwingen))


def cmd_tuer(a):
    """Tür öffnen/schließen: tuer ID… | tuer --bei X Y  (+ --auf / --zu, sonst umschalten)."""
    print(ST.tuer(a.ids, a.bei, a.auf, a.zu, a.karte))


def cmd_nebel_modus(a):
    print(ST.nebel_modus(a.modus, a.karte))


def cmd_kasse(a):
    print(ST.kasse(a.kp, a.sp, a.gp, a.pp, setze=a.setze, grund=a.grund))


def cmd_beute(a):
    print(ST.beute(a.name, an=a.an, ort=a.ort, anzahl=a.anzahl, notiz=a.notiz))


def cmd_item(a):
    ST.item(a.id, an=a.an, ort=a.ort, anzahl=a.anzahl, name=a.name, notiz=a.notiz, weg=a.weg)


def cmd_buch(a):
    ST.buch(a.char, a.zauber, a.grad, a.weg)


def cmd_zauber(a):
    if a.name and not (a.klasse or a.grad is not None or a.schule or a.liste or a.volltext):
        try:
            return print(ST.zauber_info(" ".join(a.name), langtext=not a.kurz))
        except SLFehler:
            pass  # kein exakter Name: als Suche behandeln
    print(ST.zauber_suchen(" ".join(a.name) or None, a.klasse, a.grad, a.schule, a.volltext, a.max))


def cmd_regel(a):
    text = " ".join(a.frage)
    for art in ("talent", "zustand", "fertigkeit"):
        if getattr(a, art):
            return print(ST.regel_schnell(art, text or None, a.voraussetzung, a.art))
    if a.lesen or a.seite:
        return print(ST.regel_lesen(text or None, a.seite, a.abschnitt, a.ab, a.max_zeichen))
    if not text:
        return print(ST.regel_lesen())
    print(ST.regel_suchen(text, a.kategorie, a.buch, a.typ, a.max))


def cmd_regeln_aktualisieren(a):
    print(ST.regeln_aktualisieren(a.nur_index, meldung=lambda t: print(t, flush=True)))


def cmd_ausruestung(a):
    print(ST.ausruestung())


def cmd_charaktere_importieren(a):
    aus(ST.charaktere_importieren(a.pdfs, a.ueberschreiben))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("warte"); p.add_argument("--nachlauf", type=float, default=3); p.set_defaults(f=cmd_warte)
    p = sp.add_parser("log"); p.add_argument("n", type=int, nargs="?", default=30); p.set_defaults(f=cmd_log)
    p = sp.add_parser("erzaehle"); p.add_argument("text", help="'-' liest von stdin"); p.add_argument("--titel"); p.set_defaults(f=cmd_erzaehle)
    p = sp.add_parser("notiz"); p.add_argument("text"); p.set_defaults(f=cmd_notiz)
    p = sp.add_parser("streiche", help="Protokolleinträge löschen"); p.add_argument("ids", type=int, nargs="+"); p.set_defaults(f=cmd_streiche)
    p = sp.add_parser("status"); p.add_argument("status", choices=["bereit", "denkt", "wartet"]); p.set_defaults(f=cmd_status)
    p = sp.add_parser("szene"); p.add_argument("titel"); p.add_argument("--untertitel"); p.set_defaults(f=cmd_szene)

    p = sp.add_parser("token")
    p.add_argument("art", choices=["gegner", "nsc", "objekt"]); p.add_argument("name"); p.add_argument("x", type=int); p.add_argument("y", type=int)
    p.add_argument("--id"); p.add_argument("--tp", type=int); p.add_argument("--groesse", type=int, default=1)
    p.add_argument("--farbe"); p.add_argument("--symbol"); p.add_argument("--verborgen", action="store_true")
    p.add_argument("--rk", type=int); p.add_argument("--rkb", type=int, help="RK Berührung"); p.add_argument("--rkf", type=int, help="RK auf dem falschen Fuß")
    p.add_argument("--ref", type=int); p.add_argument("--wil", type=int); p.add_argument("--zaeh", type=int)
    p.add_argument("--hg", help="Herausforderungsgrad, z. B. 1/3 oder 2")
    p.set_defaults(f=cmd_token)
    p = sp.add_parser("angriff", help="Gegner greift an (gegen RK des Ziels, Schaden wird abgezogen)")
    p.add_argument("angreifer"); p.add_argument("ziel"); p.add_argument("bonus", type=int); p.add_argument("schaden")
    p.add_argument("--waffe", default="Angriff"); p.add_argument("--krit"); p.add_argument("--beruehrung", action="store_true")
    p.add_argument("--fernkampf", action="store_true"); p.add_argument("--mod", action="append", default=[], help="Text=Wert, z. B. Flankieren=2")
    p.add_argument("--ga", nargs="?", const="bewegung", choices=["bewegung", "andere"],
                   help="Gelegenheitsangriff (bewegung: Talent Beweglichkeit des Ziels zählt, +4 RK; andere: z. B. Zaubern)")
    p.set_defaults(f=cmd_angriff)
    p = sp.add_parser("ep", help="Erfahrung vergeben (geteilt durch die Empfänger)")
    p.add_argument("--gegner", nargs="*", default=[], help="Token-IDs besiegter Gegner (deren HG zählt)")
    p.add_argument("--hg", nargs="*", default=[], help="zusätzliche HG, z. B. 1/3 2")
    p.add_argument("--ep", type=int, default=0, help="fester Betrag (gesamt)")
    p.add_argument("--an", nargs="*", help="Charakter-IDs (Standard: alle SC auf der Karte)")
    p.add_argument("--grund", default="Begegnung")
    p.set_defaults(f=lambda a: print(ST.ep(a.gegner, a.hg, a.ep, a.an, a.grund)))
    p = sp.add_parser("char", help="Charakterwerte setzen: char ID pfad=wert (JSON), z. B. rw.REF=3 gab=1")
    p.add_argument("id"); p.add_argument("werte", nargs="+")
    p.set_defaults(f=lambda a: ST.char(a.id, _char_werte(a.werte)))
    p = sp.add_parser("aufstieg-fertig", help="Stufenaufstieg abschließen, nachdem die Werte eingetragen sind")
    p.add_argument("id"); p.add_argument("--klasse", help="neuer Klassentext, z. B. 'Kleriker 2'")
    p.add_argument("--erzwingen", action="store_true", help="auch ohne eingereichten Antrag abschließen (alter Ablauf)")
    p.set_defaults(f=lambda a: ST.aufstieg_fertig(a.id, a.klasse, a.erzwingen))
    p = sp.add_parser("aufstieg", help="eingereichten Aufstiegsantrag eines Spielers anzeigen und prüfen")
    p.add_argument("id")
    p.set_defaults(f=lambda a: print(ST.aufstieg(a.id)))
    p = sp.add_parser("aufstieg-zurueck", help="Aufstiegsantrag mit Begründung zur Überarbeitung zurückgeben")
    p.add_argument("id"); p.add_argument("--grund", default="")
    p.set_defaults(f=lambda a: ST.aufstieg_zurueck(a.id, a.grund))
    p = sp.add_parser("aufstieg-abbrechen", help="offenen Aufstieg verwerfen (TP-Wurf entfällt)")
    p.add_argument("id")
    p.set_defaults(f=lambda a: ST.aufstieg_abbrechen(a.id))
    p = sp.add_parser("modus", help="Modus/Buff auf Charakter oder Token: modus ID \"Hast\" [--runden N|--minuten N|--stunden N] "
                                     "[--groesse +1] [--wirkung rk=1 angriff=1 …]; bekannte Vorlagen: Hast, Heldenmut, Person vergrößern/verkleinern …")
    p.add_argument("ziel"); p.add_argument("name")
    p.add_argument("--runden", type=int); p.add_argument("--minuten", type=int); p.add_argument("--stunden", type=int)
    p.add_argument("--groesse", type=int, help="Größenstufen (+1 = eine Kategorie größer)")
    p.add_argument("--wirkung", nargs="*", default=[], metavar="SCHLÜSSEL=WERT")
    p.add_argument("--quelle", default="")
    p.set_defaults(f=cmd_modus)
    p = sp.add_parser("modus-ende", help="Modus beenden: modus-ende ID \"Hast\"")
    p.add_argument("ziel"); p.add_argument("name")
    p.set_defaults(f=lambda a: print(ST.modus_ende(a.ziel, a.name)))
    p = sp.add_parser("modus-zeit", help="Zeit vergeht (außerhalb des Kampfes): modus-zeit --minuten 10")
    p.add_argument("--runden", type=int, default=0); p.add_argument("--minuten", type=int, default=0); p.add_argument("--stunden", type=int, default=0)
    p.set_defaults(f=cmd_modus_zeit)
    p = sp.add_parser("modi", help="aktive Modi aller Charaktere/Token anzeigen")
    p.set_defaults(f=lambda a: print(ST.modi()))
    p = sp.add_parser("rast", help="Zauberplätze zurücksetzen"); p.add_argument("--char")
    p.set_defaults(f=lambda a: ST.rast(a.char))
    p = sp.add_parser("zug", help="Aktionen des aktuellen Zuges setzen, z. B. standard=false bewegt=0")
    p.add_argument("werte", nargs="+"); p.set_defaults(f=cmd_zug)
    p = sp.add_parser("setze"); p.add_argument("id"); p.add_argument("werte", nargs="+", help="schluessel=wert (JSON)"); p.set_defaults(f=cmd_setze)
    p = sp.add_parser("taeuschung", help="Illusion: Token wirkt für bestimmte SC (am Zug) anders; --weg entfernt; --schalter ein|aus global")
    p.add_argument("token", nargs="?"); p.add_argument("--fuer", nargs="+", metavar="CHAR-ID")
    p.add_argument("--name"); p.add_argument("--symbol"); p.add_argument("--farbe")
    p.add_argument("--x", type=int); p.add_argument("--y", type=int); p.add_argument("--groesse", type=int)
    p.add_argument("--art", choices=["sc", "gegner", "nsc"]); p.add_argument("--sichtbar", action="store_true", help="auch zeigen, wenn der Token sonst verborgen/im Nebel ist")
    p.add_argument("--weg", action="store_true"); p.add_argument("--schalter", choices=["ein", "aus"])
    p.set_defaults(f=cmd_taeuschung)
    p = sp.add_parser("sichtteilen", help="Geteilte Sicht: sichtteilen CHAR PARTNER (CHAR sieht auch, was PARTNER sieht); --weg hebt auf")
    p.add_argument("char"); p.add_argument("partner", nargs="?"); p.add_argument("--weg", action="store_true")
    p.set_defaults(f=cmd_sichtteilen)
    p = sp.add_parser("zeige");p.add_argument("id"); p.add_argument("--verbergen", action="store_true"); p.set_defaults(f=cmd_zeige)
    p = sp.add_parser("weg"); p.add_argument("ids", nargs="+"); p.set_defaults(f=cmd_weg)
    p = sp.add_parser("zieh"); p.add_argument("id"); p.add_argument("x", type=int); p.add_argument("y", type=int); p.set_defaults(f=cmd_zieh)
    p = sp.add_parser("tp"); p.add_argument("id"); p.add_argument("delta", type=int); p.set_defaults(f=cmd_tp)
    p = sp.add_parser("zustand"); p.add_argument("id"); p.add_argument("zustaende", nargs="+", help="+Liegend / -Liegend"); p.set_defaults(f=cmd_zustand)

    for name, f in (("aufdecken", cmd_aufdecken), ("verdecken", cmd_verdecken)):
        p = sp.add_parser(name)
        p.add_argument("form", choices=["rechteck", "kreis", "alles"])
        p.add_argument("felder", type=int, nargs="*", help="rechteck: x0 y0 x1 y1 | kreis: x y radius")
        p.add_argument("--karte"); p.set_defaults(f=f)
    p = sp.add_parser("abdecken"); p.add_argument("felder", type=int, nargs=4); p.add_argument("--entfernen", action="store_true")
    p.add_argument("--karte"); p.set_defaults(f=cmd_abdecken)

    p = sp.add_parser("karte-neu")
    p.add_argument("id"); p.add_argument("name")
    p.add_argument("--pdf"); p.add_argument("--seite", type=int, default=1)
    p.add_argument("--ausschnitt", type=float, nargs=4, default=[0, 0, 1, 1])
    p.add_argument("--zelle-pt", type=float, help="Feldgröße in pt erzwingen")
    p.add_argument("--bild", help="Bilddatei statt PDF")
    p.add_argument("--zelle-px", type=float)
    p.add_argument("--leer", type=int, nargs=2, metavar=("FELDER_X", "FELDER_Y"))
    p.add_argument("--aktiv", action="store_true"); p.set_defaults(f=cmd_karte_neu)
    p = sp.add_parser("karte-import", help="Karte mit exakten Wänden: Spieltisch-Kartenformat (.json) oder Universal VTT (.dd2vtt/.uvtt)")
    p.add_argument("datei"); p.add_argument("--id"); p.add_argument("--name"); p.add_argument("--aktiv", action="store_true")
    p.set_defaults(f=lambda a: print(ST.karte_import(a.datei, id=a.id, name=a.name, aktiv=a.aktiv)))
    p = sp.add_parser("karte-export", help="Karte mit Wänden/Türen nach sl/karten/ID.karte.json sichern")
    p.add_argument("id"); p.set_defaults(f=lambda a: print(ST.karte_export(a.id)))
    p = sp.add_parser("karte"); p.add_argument("id"); p.set_defaults(f=cmd_karte)
    p = sp.add_parser("bekannt", help="Karte in die Unterlagen der Spieler aufnehmen")
    p.add_argument("id"); p.add_argument("--nein", action="store_true"); p.add_argument("--legende", help="Handout-ID mit der Legende")
    p.set_defaults(f=cmd_bekannt)
    p = sp.add_parser("handout", help="Text-Handout für die Spieler (gleiche ID ersetzt)")
    p.add_argument("id"); p.add_argument("text", nargs="?", default="-", help="'-' liest von stdin"); p.add_argument("--titel")
    p.add_argument("--weg", action="store_true"); p.set_defaults(f=cmd_handout)
    p = sp.add_parser("raster"); p.add_argument("--karte"); p.add_argument("--zelle", type=float); p.add_argument("--ox", type=float)
    p.add_argument("--oy", type=float); p.add_argument("--meter", type=float)
    p.add_argument("--waende", choices=["ein", "aus"], help="Bewegung durch Wände sperren"); p.add_argument("--nebel-auto", choices=["ein", "aus", "standard"], help="Nebel nach SC-Bewegung automatisch per Sichtlinie aufdecken (pro Karte)")
    p.add_argument("--sicht-felder", type=int, help="Standard-Sichtweite in Feldern (ohne Dunkelsicht)"); p.set_defaults(f=cmd_raster)
    p = sp.add_parser("sicht"); p.add_argument("--karte"); p.set_defaults(f=cmd_sicht)
    p = sp.add_parser("nebel-modus", help="sicht = stufenloser Sichtpolygon-Nebel mit erkannten Wänden, raster = Feldraster (Standard)")
    p.add_argument("modus", choices=["sicht", "raster"]); p.add_argument("--karte"); p.set_defaults(f=cmd_nebel_modus)
    p = sp.add_parser("barrieren", help="Wände/Türen/Fenster: erkennen | liste | neu | aendern | weg | frei")
    p.add_argument("aktion", choices=["erkennen", "liste", "neu", "aendern", "weg", "frei"])
    p.add_argument("ids", nargs="*"); p.add_argument("--karte"); p.add_argument("--typ", choices=["wand", "tuer", "geheimtuer", "fenster"])
    p.add_argument("--von", type=float, nargs=2, metavar=("X", "Y")); p.add_argument("--bis", type=float, nargs=2, metavar=("X", "Y"))
    p.add_argument("--einseitig", choices=["links", "rechts"], help="Barriere blockiert nur von dieser Seite (Blick von von→bis)")
    p.add_argument("--id"); p.add_argument("--bereich", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="weg: Wandstücke in diesem Feldbereich ignorieren")
    p.add_argument("--erzwingen", action="store_true", help="erkennen: auch importierte Wände ersetzen")
    p.set_defaults(f=cmd_barrieren)
    p = sp.add_parser("tuer", help="Tür öffnen/schließen: tuer t5 | tuer --bei 12 7 --auf")
    p.add_argument("ids", nargs="*"); p.add_argument("--bei", type=float, nargs=2, metavar=("X", "Y")); p.add_argument("--karte")
    p.add_argument("--auf", action="store_true"); p.add_argument("--zu", action="store_true"); p.set_defaults(f=cmd_tuer)

    p = sp.add_parser("ini"); p.add_argument("aktion", choices=["start", "los", "eintrag", "entfernen", "aufdecken", "weiter", "ende"])
    p.add_argument("name", nargs="?"); p.add_argument("wert", type=float, nargs="?"); p.add_argument("--token")
    p.add_argument("--verborgen", action="store_true"); p.set_defaults(f=cmd_ini)
    p = sp.add_parser("wurf"); p.add_argument("ausdruck"); p.add_argument("--grund"); p.add_argument("--wer", default="SL")
    p.add_argument("--offen", action="store_true", help="für Spieler sichtbar"); p.set_defaults(f=cmd_wurf)
    p = sp.add_parser("stand"); p.set_defaults(f=cmd_stand)
    p = sp.add_parser("vorschau"); p.add_argument("--karte"); p.add_argument("--bereich", type=int, nargs=4)
    p.add_argument("--spieler", action="store_true"); p.add_argument("--raster", type=int, default=5)
    p.add_argument("--barrieren", action="store_true", help="erkannte Wände/Türen einzeichnen (nur SL)")
    p.add_argument("--zoom", type=float, default=0.6); p.add_argument("--ausgabe"); p.set_defaults(f=cmd_vorschau)
    p = sp.add_parser("kasse", help="Gruppenkasse: kasse --gp 100 --sp -20 [--setze] --grund '…'")
    for m in ("kp", "sp", "gp", "pp"):
        p.add_argument("--" + m, type=int)
    p.add_argument("--setze", action="store_true", help="Werte setzen statt addieren"); p.add_argument("--grund", default="")
    p.set_defaults(f=cmd_kasse)
    p = sp.add_parser("beute", help="Gegenstand anlegen: beute NAME --an CHAR-ID|gruppe --ort Rucksack [--anzahl N]")
    p.add_argument("name"); p.add_argument("--an", default="gruppe"); p.add_argument("--ort", default="dabei")
    p.add_argument("--anzahl", type=int, default=1); p.add_argument("--notiz", default=""); p.set_defaults(f=cmd_beute)
    p = sp.add_parser("item", help="Gegenstand ändern: item ID [--an CHAR] [--ort X] [--anzahl N] [--weg]")
    p.add_argument("id", type=int); p.add_argument("--an"); p.add_argument("--ort"); p.add_argument("--anzahl", type=int)
    p.add_argument("--name"); p.add_argument("--notiz"); p.add_argument("--weg", action="store_true"); p.set_defaults(f=cmd_item)
    p = sp.add_parser("buch", help="Zauberbuch: buch CHAR-ID --grad N \"Zauber 1\" \"Zauber 2\" [--weg]")
    p.add_argument("char"); p.add_argument("zauber", nargs="+"); p.add_argument("--grad", type=int, default=0)
    p.add_argument("--weg", action="store_true"); p.set_defaults(f=cmd_buch)
    p = sp.add_parser("ausruestung", help="Kasse und Ausrüstung aller Träger anzeigen"); p.set_defaults(f=cmd_ausruestung)
    p = sp.add_parser("zauber", help="Zauber nachschlagen (PRD): zauber \"Feuerball\" · zauber feuer --liste · "
                                     "zauber --klasse Barde --grad 3 [--schule Illusion] [--volltext]")
    p.add_argument("name", nargs="*"); p.add_argument("--klasse"); p.add_argument("--grad", type=int)
    p.add_argument("--schule"); p.add_argument("--volltext", action="store_true", help="auch im Beschreibungstext suchen")
    p.add_argument("--liste", action="store_true", help="immer als Trefferliste"); p.add_argument("--kurz", action="store_true",
    help="ohne Langtext"); p.add_argument("--max", type=int, default=40); p.set_defaults(f=cmd_zauber)
    p = sp.add_parser("regel", help="Regeln nachschlagen (PRD: Grundregelwerk + Expertenregeln, sl/hausregeln.md): regel Gelegenheitsangriff "
                                    "verlassen · regel --lesen ID|Titel · regel --seite Kampf · regel --talent Beweglichkeit · "
                                    "regel --zustand Hilflos · regel --fertigkeit Akrobatik · regel (ohne Angaben: Stand)")
    p.add_argument("frage", nargs="*"); p.add_argument("--kategorie"); p.add_argument("--typ")
    p.add_argument("--buch", help="Grundregelwerk oder Expertenregeln")
    p.add_argument("--max", type=int, default=5); p.add_argument("--lesen", action="store_true", help="Volltext (ID oder Titel)")
    p.add_argument("--seite"); p.add_argument("--abschnitt"); p.add_argument("--ab", type=int, default=0)
    p.add_argument("--max-zeichen", type=int, default=4000)
    p.add_argument("--talent", action="store_true"); p.add_argument("--zustand", action="store_true")
    p.add_argument("--fertigkeit", action="store_true"); p.add_argument("--voraussetzung"); p.add_argument("--art")
    p.set_defaults(f=cmd_regel)
    p = sp.add_parser("regeln-aktualisieren", help="Regeldatenbank aus dem PRD aktualisieren (nur Änderungen, ETag)")
    p.add_argument("--nur-index", action="store_true", help="nur Index/Markdown aus der Datenbank neu (ohne Netz)")
    p.set_defaults(f=cmd_regeln_aktualisieren)
    p = sp.add_parser("charaktere-importieren"); p.add_argument("pdfs", nargs="+"); p.add_argument("--ueberschreiben", action="store_true")
    p.set_defaults(f=cmd_charaktere_importieren)

    a = ap.parse_args()
    try:
        a.f(a)
    except SLFehler as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
