"""Gemeinsame Bibliothek für den Spielleiter-Zugriff auf den Spieltisch.

Wird von `sl.py` (Kommandozeile) und `mcp_server.py` (MCP für den SL-Agenten) genutzt.
Jede Methode gibt Text zurück (das, was `sl.py` ausgibt) oder Daten; Fehler kommen als `SLFehler`
(statt `sys.exit`), damit der MCP-Server sie als Tool-Fehler melden kann.

    from sl_api import Spieltisch
    st = Spieltisch("<Kampagnenordner>")
    print(st.stand())
"""
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASIS = Path(__file__).resolve().parent
if str(BASIS) not in sys.path:
    sys.path.insert(0, str(BASIS))
from bereiche import kampagne  # noqa: E402
from bereiche.kampagne import (BASIS as _TOOL, _json_lesen, _platzhalter, _sperre_pfad, _freier_port,  # noqa: E402,F401
                               kampagnen_liste, pfade_ok, pfade_reparieren, pfade_schreiben, python_exe,
                               vorlage_ordner, VORLAGE)
from bereiche.kern import Fehler as SLFehler  # noqa: E402  (Meldungen an den SL; gleiche Klasse wie im Kern)
from bereiche.wissen import regeln_db, zauber_db  # noqa: E402


def ereignis_text(e):
    art = e["art"]
    if art == "spieler":
        return f"#{e['id']} [{e['zeit']}] SPIELER ({e.get('wer')}): {e['text']}"
    if art == "wurf":
        bes = f" **{e['besonders']}**" if e.get("besonders") else ""
        return f"#{e['id']} WURF {e.get('wer')}: {e['text'] or e['ausdruck']} = {e['ergebnis']} ({e['detail']}){bes}"
    if art == "angriff":
        if e.get("treffer") is None:
            return f"#{e['id']} ANGRIFF {e['text']}: {e['ergebnis']} ({e['detail']}) – OHNE RK, bitte auswerten (Schaden {e.get('schadenAusdruck')})"
        erg = ("KRITISCHER TREFFER" if e.get("kritisch") else "Treffer") if e["treffer"] else "daneben"
        schaden = f", {e['schaden']} Schaden" if e.get("schaden") else ""
        return f"#{e['id']} ANGRIFF {e['text']}: {e['ergebnis']} ({e['detail']}) → {erg}{schaden}"
    if art == "ep":
        return f"#{e['id']} EP: {e['text']}"
    if art == "aufstieg":
        return f"#{e['id']} >>> AUFSTIEG {e['text']} | {e.get('detail')} | {e.get('wuensche') or '-'}  (Details: aufstieg ID)"
    if art == "zauber":
        return f"#{e['id']} ZAUBER {e['text']}: {e.get('ergebnisText') or ''} | {e.get('detail') or ''}"
    if art == "zugende":
        return f"#{e['id']} >>> {e['text']}"
    if art == "sl":
        return f"#{e['id']} SL: {e['text'][:160]}{'…' if len(e['text']) > 160 else ''}"
    return f"#{e['id']} {art.upper()}: {e['text']}"


def _weckt(e):
    return e.get("wecken", e["art"] == "spieler")


def kv_werte(paare, nur_json=False):
    """'a=1' 'b=text' -> {"a": 1, "b": "text"} (Werte als JSON, sonst Text)."""
    werte = {}
    for kv in paare:
        k, _, v = kv.partition("=")
        if nur_json:
            werte[k] = json.loads(v)
            continue
        try:
            werte[k] = json.loads(v)
        except json.JSONDecodeError:
            werte[k] = v
    return werte


def _dauer(runden=None, minuten=None, stunden=None):
    r = (runden or 0) + (minuten or 0) * 10 + (stunden or 0) * 600
    return r or None


TEXT_ENDUNGEN = (".md", ".txt")
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")


class Spieltisch:
    def __init__(self, kampagnenpfad=None, basis=None):
        """kampagnenpfad: Ordner mit kampagne.json (sonst SPIELTISCH_KAMPAGNE / Suche aufwärts).
        basis: Bezug für relative Dateipfade (PDF/Bild bei karte_neu …); Standard: aktuelles Verzeichnis."""
        try:
            self.kamp = kampagne.laden(kampagnenpfad)
        except SystemExit as e:
            raise SLFehler(str(e)) from None
        self.port = self.kamp["port"]
        self.url = f"http://127.0.0.1:{self.port}"
        self.basis = Path(basis) if basis else None

    # ------------------------------------------------------------ Grundlagen

    @property
    def key(self):
        p = self.kamp["schluessel"]
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    def pfad(self, p):
        """Relativen Dateipfad auflösen (gegen `basis`, sonst aktuelles Verzeichnis)."""
        if p is None:
            return None
        q = Path(p).expanduser()
        if not q.is_absolute():
            q = (self.basis or Path.cwd()) / q
        return q

    def anfrage(self, pfad, daten=None, timeout=60):
        req = urllib.request.Request(self.url + pfad, headers={"X-SL": self.key, "Content-Type": "application/json"},
                                     data=None if daten is None else json.dumps(daten).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            roh = e.read().decode("utf-8", "replace")
            try:
                text = json.loads(roh).get("fehler", roh)
            except (json.JSONDecodeError, AttributeError):
                text = roh
            raise SLFehler(f"Fehler {e.code}: {text}") from None
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as e:
            raise SLFehler(f"Spieltisch-Server »{self.kamp['name']}« nicht erreichbar ({self.url}): "
                           f"{getattr(e, 'reason', e)}. Läuft er? (server_status / server_starten)") from None

    def befehl(self, **b):
        return self.anfrage("/api/sl/befehl", b)

    def zustand(self):
        """Voller Spielstand (SL). Läuft der Server nicht, wird sl/zustand.json gelesen."""
        try:
            return self.anfrage("/api/sl/zustand")
        except SLFehler as e:
            if "nicht erreichbar" in str(e) and self.kamp["zustand"].exists():
                return json.loads(self.kamp["zustand"].read_text(encoding="utf-8"))
            raise

    def laeuft(self):
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                return True
        except OSError:
            return False

    def server_starten(self, warten=15):
        """Startet server.py für diese Kampagne im Hintergrund (Ausgabe nach sl/server.log)."""
        if self.laeuft():
            return f"Server läuft bereits: {self.url}/"
        log = open(self.kamp["sl"] / "server.log", "a", encoding="utf-8")
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([str(python_exe()), str(BASIS / "server.py"), "--kampagne", str(self.kamp["ordner"])],
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, cwd=str(BASIS), creationflags=flags,
                         close_fds=True)
        ende = time.time() + warten
        while time.time() < ende:
            if self.laeuft():
                return f"Server gestartet: Spieler {self.url}/  (SL-Ansicht mit ?sl=<Schlüssel>)"
            time.sleep(0.3)
        raise SLFehler("Server antwortet nicht (sl/server.log prüfen)")

    # ------------------------------------------------------------ Tisch / Protokoll

    def warte(self, nachlauf=3, timeout=None, abbruch=None):
        """Blockiert bis zur nächsten weckenden Spieleraktion, sammelt `nachlauf` Sekunden nach,
        markiert die Ereignisse als verarbeitet und setzt den SL-Status auf „denkt“.
        timeout=None: unbegrenzt. Gibt den Ereignistext zurück, bei Timeout None.
        abbruch: optionales threading.Event zum Abbrechen."""
        ende = None if timeout is None else time.time() + timeout
        lv = None
        while True:
            if abbruch is not None and abbruch.is_set():
                return None
            rest = 25 if ende is None else ende - time.time()
            if rest <= 0:
                return None
            t0 = time.time()
            try:
                seit = 10 ** 12 if lv is None else lv
                w = max(0.0, min(25.0 if abbruch is None else 3.0, rest))  # abbrechbar: kurze Long-Polls
                r = self.anfrage(f"/api/sl/ereignisse?seit={seit}&warten={w:.0f}", timeout=w + 20)
            except SLFehler:
                time.sleep(2)
                continue
            if lv is None or r["letzteVerarbeitet"] != lv:
                lv = r["letzteVerarbeitet"]
                r = self.anfrage(f"/api/sl/ereignisse?seit={lv}")
            neu = [e for e in r["eintraege"] if e["id"] > r["letzteVerarbeitet"]]
            if any(_weckt(e) for e in neu):
                break
            if time.time() - t0 < 0.8:  # alter Server ohne Long-Poll: selbst takten
                time.sleep(1)
        if nachlauf:
            if abbruch is not None:
                abbruch.wait(nachlauf)
            else:
                time.sleep(nachlauf)
        if abbruch is not None and abbruch.is_set():  # abgebrochen: nichts als verarbeitet markieren
            return None
        r = self.anfrage(f"/api/sl/ereignisse?seit={r['letzteVerarbeitet']}")
        neu = r["eintraege"]
        self.befehl(op="verarbeitet", bis=neu[-1]["id"])
        self.befehl(op="status", status="denkt")
        return "=== Neue Ereignisse am Spieltisch ===\n" + "\n".join(ereignis_text(e) for e in neu)

    def log(self, n=30):
        r = self.anfrage("/api/sl/ereignisse?seit=0")
        return "\n".join(ereignis_text(e) for e in r["eintraege"][-n:])

    def erzaehle(self, text, titel=None):
        if not (text or "").strip():
            raise SLFehler("Kein Text zum Erzählen")
        self.befehl(op="erzaehle", text=text.strip(), titel=titel)
        return ""

    def streiche(self, ids):
        for i in ids:
            self.befehl(op="eintrag-loeschen", id=int(i))
        return ""

    def notiz(self, text):
        self.befehl(op="notiz", text=text)
        return ""

    def status(self, status):
        if status not in ("bereit", "denkt", "wartet"):
            raise SLFehler("Status: bereit | denkt | wartet")
        self.befehl(op="status", status=status)
        return ""

    def szene(self, titel, untertitel=None):
        self.befehl(op="szene", titel=titel, untertitel=untertitel or "")
        return ""

    def handout(self, id, text=None, titel=None, weg=False):
        if weg:
            self.befehl(op="handout-weg", id=id)
            return ""
        if not (text or "").strip():
            raise SLFehler("Handout-Text fehlt")
        self.befehl(op="handout", id=id, titel=titel, text=text.strip())
        return ""

    def wurf(self, ausdruck, grund=None, wer="SL", offen=False):
        r = self.befehl(op="wurf", ausdruck=ausdruck, grund=grund or "", wer=wer, verborgen=not offen)
        bes = f"  ({r['besonders']})" if r.get("besonders") else ""
        return f"{r['ergebnis']}  [{r['detail']}]{bes}"

    def stand(self):
        from bereiche.karte import karten
        z = self.anfrage("/api/sl/zustand")
        k = z["karten"].get(z["karteAktiv"]) if z["karteAktiv"] else None
        aus = [f"Szene: {z['szene']['titel']}  |  Karte: {k['name'] if k else '-'} ({z['karteAktiv']})  |  SL-Status: {z['slStatus']}"]
        if k:
            aus.append(f"  Felder {karten.zellbereich(k)}, aufgedeckt: {len(k.get('aufgedeckt', []))} Felder, Abdeckungen: {k.get('abdeckungen')}")
        for t in z["tokens"].values():
            if t.get("karte") != z["karteAktiv"]:
                continue
            tp = f" TP {t.get('tp')}/{t.get('tpMax')}" if t.get("tpMax") else ""
            aus.append(f"  {t['id']:8} {t['art']:7} {t['name']:22} ({t['x']},{t['y']}){tp}"
                       f"{'' if t.get('sichtbar', True) else ' [verborgen]'} {' '.join(t.get('zustaende', []))}")
        ini = z["initiative"]
        if ini["aktiv"]:
            zug = z.get("zug")
            aus.append(f"  Initiative ({ini.get('phase')}) Runde {ini['runde']}:"
                       + (f"  Zug: {zug['name']} bewegt={zug['bewegt']} standard={zug['standard']} "
                          f"bewegung={zug['bewegung']} schnell={zug['schnell']}" if zug else ""))
            for i, e in enumerate(ini["eintraege"]):
                aus.append(f"   {'>' if i == ini['index'] else ' '} {e['wert']:>4} {e['name']}{' [verborgen]' if e.get('verborgen') else ''}")
        return "\n".join(aus)

    # ------------------------------------------------------------ Token / Kampf

    def token(self, art, name, x, y, id=None, tp=None, groesse=1, farbe=None, symbol=None, verborgen=False,
              rk=None, rkb=None, rkf=None, ref=None, wil=None, zaeh=None, hg=None):
        if art not in ("gegner", "nsc", "objekt"):
            raise SLFehler("art: gegner | nsc | objekt")
        t = {"art": art, "name": name, "x": int(x), "y": int(y), "groesse": groesse or 1, "sichtbar": not verborgen}
        if id:
            t["id"] = id
        if tp is not None:
            t["tpMax"] = tp
        for feld, wert in (("rk", rk), ("rkBeruehrung", rkb), ("rkAdff", rkf), ("ref", ref), ("wil", wil),
                           ("zaeh", zaeh), ("hg", hg)):
            if wert is not None:
                t[feld] = wert
        if farbe:
            t["farbe"] = farbe
        if symbol:
            t["symbol"] = symbol
        return str(self.befehl(op="token-setzen", token=t)["id"])

    def setze(self, id, werte):
        self.befehl(op="token-aendern", id=id, werte=werte)
        return ""

    def zeige(self, id, verbergen=False):
        self.befehl(op="token-aendern", id=id, werte={"sichtbar": not verbergen})
        return ""

    def weg(self, ids):
        for tid in ids:
            self.befehl(op="token-entfernen", id=tid)
        return ""

    def zieh(self, id, x, y):
        r = self.befehl(op="bewegen", id=id, x=int(x), y=int(y))
        return "⚠ " + r["warnung"] if r.get("warnung") else ""

    def tp(self, id, delta):
        self.befehl(op="tp", id=id, delta=int(delta))
        return ""

    def zustand_setzen(self, id, zustaende):
        """zustaende: ["+Liegend", "-Wankend", "Benommen"] (ohne Vorzeichen = an)."""
        for z in zustaende:
            self.befehl(op="zustand", id=id, name=z.lstrip("+-"), an=not z.startswith("-"))
        return ""

    def sc_platzieren(self, char_id, x, y):
        """SC-Token auf die aktive Karte setzen (auch beim Kartenwechsel)."""
        self.anfrage("/api/sc-platzieren", {"charId": char_id, "x": int(x), "y": int(y)})
        return ""

    def taeuschung(self, token=None, fuer=None, name=None, symbol=None, farbe=None, x=None, y=None, groesse=None,
                   art=None, sichtbar=False, weg=False, schalter=None):
        if schalter:
            r = self.befehl(op="taeuschung", schalter=schalter)
            return "Täuschungsansicht " + ("AUS" if r.get("aus") else "EIN")
        if not token:
            raise SLFehler("TOKEN fehlt (oder: schalter ein|aus)")
        if weg:
            r = self.befehl(op="taeuschung", id=token, weg=True, fuer=fuer or None)
        else:
            if not fuer:
                raise SLFehler("fuer (CHAR-IDs) fehlt")
            r = self.befehl(op="taeuschung", id=token, fuer=fuer, name=name, symbol=symbol, farbe=farbe,
                            x=x, y=y, groesse=groesse, sichtbar=True if sichtbar else None, art=art)
        aus = [f"  {token} wirkt auf {cid}: {e}" for cid, e in (r.get("taeuschung") or {}).items()]
        return "\n".join(aus) or f"  {token}: keine Täuschung"

    def angriff(self, angreifer, ziel, bonus, schaden, waffe="Angriff", krit=None, beruehrung=False,
                fernkampf=False, mods=None, gelegenheitsangriff=None):
        """mods: {"Flankieren": 2} oder ["Flankieren=2"]. gelegenheitsangriff: "bewegung" (Beweglichkeit des Ziels
        zählt) oder "andere" (z. B. Zaubern im bedrohten Feld)."""
        if gelegenheitsangriff not in (None, "", False, True, "bewegung", "andere"):
            raise SLFehler("gelegenheitsangriff: bewegung | andere")
        if isinstance(mods, (list, tuple)):
            mods = {m.split("=")[0]: int(m.split("=")[1]) for m in mods}
        self.befehl(op="angriff", angreifer=angreifer, ziel=ziel, bonus=int(bonus), schaden=schaden, krit=krit,
                    waffe=waffe, beruehrung=beruehrung, fernkampf=fernkampf,
                    mods=[(k, int(v)) for k, v in (mods or {}).items()],
                    gelegenheitsangriff=("bewegung" if gelegenheitsangriff is True else gelegenheitsangriff) or None)
        return self.log(1)

    def ini(self, aktion, name=None, wert=None, token=None, verborgen=False):
        if aktion in ("start", "los", "weiter", "ende"):
            self.befehl(op="initiative", aktion=aktion)
        elif aktion == "eintrag":
            if not name or wert is None:
                raise SLFehler("ini eintrag braucht name und wert")
            self.befehl(op="initiative", aktion="eintrag", name=name, wert=wert, tokenId=token, verborgen=verborgen)
        elif aktion in ("entfernen", "aufdecken"):
            self.befehl(op="initiative", aktion=aktion, name=name)
        else:
            raise SLFehler("aktion: start | los | eintrag | entfernen | aufdecken | weiter | ende")
        return ""

    def zug(self, werte):
        self.befehl(op="zug", werte=werte)
        return ""

    # ------------------------------------------------------------ Modi

    def modus(self, ziel, name, runden=None, minuten=None, stunden=None, groesse=None, wirkung=None, quelle=""):
        if isinstance(wirkung, (list, tuple)):
            wirkung = {k: int(v) for k, _, v in (w.partition("=") for w in wirkung)}
        r = self.befehl(op="modus", ziel=ziel, name=name, runden=_dauer(runden, minuten, stunden), groesse=groesse,
                        wirkung={k: int(v) for k, v in (wirkung or {}).items()}, quelle=quelle or "")
        return "\n".join([r.get("text", "")] + ["Hinweis: " + h for h in r.get("hinweise", [])])

    def modus_ende(self, ziel, name):
        return self.befehl(op="modus-ende", ziel=ziel, name=name).get("text", "")

    def modus_zeit(self, runden=0, minuten=0, stunden=0):
        r = self.befehl(op="modus-zeit", runden=_dauer(runden, minuten, stunden) or 0)
        return "Abgelaufen: " + ", ".join(r["abgelaufen"]) if r.get("abgelaufen") else "Nichts abgelaufen."

    def modi(self):
        return "\n".join(self.befehl(op="modi").get("zeilen", [])) or "(keine aktiven Modi)"

    # ------------------------------------------------------------ Karte / Nebel / Barrieren

    def nebel(self, auf, form, felder=None, karte=None):
        if form not in ("rechteck", "kreis", "alles"):
            raise SLFehler("form: rechteck | kreis | alles")
        self.befehl(op="aufdecken" if auf else "verdecken", form=form, felder=[int(f) for f in felder or []], karte=karte)
        return ""

    def abdecken(self, felder, entfernen=False, karte=None):
        self.befehl(op="abdecken", felder=[int(f) for f in felder], entfernen=entfernen, karte=karte)
        return ""

    def karte_neu(self, id, name, pdf=None, seite=1, ausschnitt=None, zelle_pt=None, bild=None, zelle_px=None,
                  leer=None, aktiv=False, versatz_erkennen=False):
        """Neue Karte aus PDF-Seite (Raster wird erkannt), Bilddatei (zelle_px = Feldgröße im Bild; mit
        versatz_erkennen wird die Lage des Rasters gesucht, sonst 0/0) oder leer [FELDER_X, FELDER_Y]."""
        from bereiche.karte import karten
        import pymupdf
        if not re.fullmatch(r"[\w-]+", id or ""):
            raise SLFehler("Karten-ID nur aus Buchstaben, Ziffern, - und _")
        ausschnitt = list(ausschnitt or [0, 0, 1, 1])
        datei = f"{id}.png"
        ziel = self.kamp["karten"] / datei
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if leer:
            meta = karten.leere_karte(str(ziel), int(leer[0]), int(leer[1]))
        elif bild:
            pb = self.pfad(bild)
            if not pb.is_file():
                raise SLFehler(f"Bild nicht gefunden: {pb}")
            try:
                pix = pymupdf.Pixmap(str(pb))
                s = karten.ZIEL_ZELLE / float(zelle_px) if zelle_px else 1
                if s != 1:
                    doc = pymupdf.open(str(pb))
                    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
                pix.save(str(ziel))
            except (RuntimeError, ValueError) as e:
                raise SLFehler(f"Bild nicht lesbar ({pb.name}): {e}") from None
            meta = {"w": pix.w, "h": pix.h, "zelle": karten.ZIEL_ZELLE if zelle_px else 50, "ox": 0, "oy": 0}
            if zelle_px and versatz_erkennen:  # Lage des Rasters (Versatz) bei bekannter Feldgröße suchen
                ox, oy = karten.phase_verfeinern(pix, karten.ZIEL_ZELLE)
                meta.update(ox=round(ox, 2), oy=round(oy, 2))
        elif pdf:
            pp = self.pfad(pdf)
            if not pp.is_file():
                raise SLFehler(f"PDF nicht gefunden: {pp}")
            meta = karten.ausschneiden(str(pp), int(seite), ausschnitt, str(ziel), zelle_pt)
        else:
            raise SLFehler("Quelle fehlt: pdf (+seite, ausschnitt), bild oder leer [FELDER_X, FELDER_Y]")
        karte = {"id": id, "name": name, "datei": datei, **{k: float(v) for k, v in meta.items()}}
        karte["waendeSperren"] = not leer
        karte["quelle"] = {"pdf": pdf, "seite": seite, "ausschnitt": ausschnitt} if pdf else ({"bild": bild} if bild else None)
        self.befehl(op="karte-registrieren", karte=karte)
        x0, y0, x1, y1 = karten.zellbereich(karte)
        aus = json.dumps(karte, ensure_ascii=False) + f"\nFelder: x {x0}..{x1}, y {y0}..{y1}"
        if aktiv:
            self.befehl(op="karte-aktiv", id=id)
        return aus

    def karte_import(self, datei=None, daten=None, id=None, name=None, aktiv=False, sc=None):
        """Karte mit exakten Wänden importieren: Spieltisch-Kartenformat (JSON, siehe kartenformat.py) oder
        Universal VTT (.dd2vtt/.uvtt). Legt Bild, Karte und Barrieren an und schaltet den Sichtnebel ein."""
        from bereiche.karte import karten
        from bereiche.karte import kartenformat as KF
        if datei:
            p = self.pfad(datei)
            if not p.is_file():
                raise SLFehler(f"Datei nicht gefunden: {p}")
            daten = KF.laden_text(p.read_text(encoding="utf-8-sig"))
        if isinstance(daten, str):
            daten = KF.laden_text(daten)
        if not isinstance(daten, dict):
            raise SLFehler("datei oder daten (Kartenformat als JSON-Objekt) angeben")
        quellbild = None
        if KF.ist_uvtt(daten):
            daten, quellbild = KF.aus_uvtt(daten)
        k = dict(daten)
        k["id"] = id or k.get("id")
        k["name"] = name or k.get("name") or k["id"]
        if not k["id"] or not re.fullmatch(r"[\w-]+", k["id"]):
            raise SLFehler("Karten-ID fehlt oder ungültig (Buchstaben, Ziffern, - und _)")
        kid = k["id"]
        ziel = self.kamp["karten"] / f"{kid}.png"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        try:
            if quellbild is not None:
                k["bild"] = "(uvtt)"
            KF.pruefen(k)
            waende = KF.waende_berechnen(k)
            if k.get("bild"):
                import pymupdf
                if quellbild is not None:
                    pix = pymupdf.Pixmap(quellbild)
                else:
                    pb = self.pfad(k["bild"])
                    if not pb.is_file():
                        raise SLFehler(f"Bild nicht gefunden: {pb}")
                    pix = pymupdf.Pixmap(str(pb))
                zpx = float(k.get("zelle_px") or karten.ZIEL_ZELLE)
                s = karten.ZIEL_ZELLE / zpx
                if pix.alpha:
                    pix = pymupdf.Pixmap(pix, 0)
                if abs(s - 1) > 1e-6:
                    pix = pymupdf.Pixmap(pix, int(round(pix.w * s)), int(round(pix.h * s)), None)
                pix.save(str(ziel))
                w, h = pix.w, pix.h
                vx, vy = (float(v) for v in (k.get("versatz") or [0, 0]))
                ox, oy = vx * s, vy * s
            else:
                w, h = KF.zeichnen(k, waende, str(ziel))
                ox = oy = 0.0
            barr = KF.barrieren_daten(k, waende, w, h, karten.ZIEL_ZELLE, ox, oy)
        except KF.FormatFehler as e:
            raise SLFehler(f"Kartenformat: {e}") from None
        karte = {"id": kid, "name": k["name"], "datei": ziel.name, "w": float(w), "h": float(h),
                 "zelle": float(karten.ZIEL_ZELLE), "ox": round(ox, 2), "oy": round(oy, 2),
                 "meterProFeld": float(k.get("meterProFeld") or 1.5), "waendeSperren": False,
                 "quelle": {"import": datei or "daten"}}
        self.befehl(op="karte-registrieren", karte=karte)
        self.befehl(op="barrieren-setzen", karte=kid, daten=barr)
        self.befehl(op="nebel-modus", modus="sicht", karte=kid)
        self.befehl(op="raster", karte=kid, autoNebel=True, waendeSperren=False)
        aus = [f"Karte {kid} »{k['name']}« importiert: {w}×{h} px, Felder {karten.zellbereich(karte)}, "
               f"{len(barr['waende'])} Wandstücke, {len(barr['extra'])} Türen/Fenster; Nebelmodus sicht, Auto-Nebel ein"]
        if aktiv or sc:
            self.befehl(op="karte-aktiv", id=kid)
            aus.append(f"Karte {kid} aktiv")
            for s_ in sc or []:
                self.sc_platzieren(s_["char_id"], s_["x"], s_["y"])
                aus.append(f"{s_['char_id']} bei ({s_['x']},{s_['y']})")
            aus.append(self.sicht(kid) or "Sicht aufgedeckt")
        return "\n".join(aus)

    def karte_export(self, id):
        """Karte samt Wänden/Türen ins Spieltisch-Kartenformat schreiben (sl/karten/<id>.karte.json)."""
        from bereiche.karte import barrieren as B
        from bereiche.karte import kartenformat as KF
        z = self.zustand()
        if id not in z["karten"]:
            raise SLFehler(f"Karte {id!r} unbekannt")
        k = KF.exportieren(z["karten"][id], B.laden(self.kamp["sl"], id))
        p = self.kamp["karten"] / f"{id}.karte.json"
        p.write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
        return f"exportiert: sl/karten/{p.name} ({len(k['waende'])} Wände, {len(k['tueren'])} Türen/Fenster)"

    def karte(self, id):
        self.befehl(op="karte-aktiv", id=id)
        return ""

    def karten_liste(self):
        from bereiche.karte import karten
        z = self.zustand()
        aus = []
        for kid, k in z["karten"].items():
            x0, y0, x1, y1 = karten.zellbereich(k)
            barr = (self.kamp["sl"] / "barrieren" / f"{kid}.json").exists()
            aus.append(f"{'*' if kid == z['karteAktiv'] else ' '} {kid:14} {k['name'][:30]:30} Felder x {x0}..{x1}, y {y0}..{y1} "
                       f"| Zelle {k['zelle']:.1f}px | Nebel {k.get('nebelModus', 'raster')}"
                       f"{' auto' if k.get('autoNebel') else ''} | Barrieren {'ja' if barr else 'nein'}"
                       f"{' | bekannt' if k.get('bekannt') else ''}")
        return "\n".join(aus) or "(keine Karten)"

    def bekannt(self, id, nein=False, legende=None):
        b = {"op": "karte-bekannt", "id": id, "bekannt": not nein}
        if legende:
            b["legende"] = legende
        self.befehl(**b)
        return ""

    def sicht(self, karte=None):
        r = self.befehl(op="sicht", karte=karte)
        n = r.get("aufgedeckt")
        return f"Aufgedeckt: {n}" if n is not None else ""

    def sichtteilen(self, char, partner=None, weg=False):
        if weg:
            self.befehl(op="char-setzen", charId=char, werte={"sichtVon": None})
            return f"  {char}: Sicht nicht mehr geteilt"
        if not partner:
            raise SLFehler("PARTNER fehlt (oder weg)")
        self.befehl(op="char-setzen", charId=char, werte={"sichtVon": partner})
        self.befehl(op="sicht", karte=None)
        return f"  {char} sieht jetzt auch, was {partner} sieht"

    def raster(self, karte=None, zelle=None, ox=None, oy=None, meter=None, waende=None, nebel_auto=None, sicht_felder=None):
        b = {"op": "raster", "karte": karte}
        for k, v in (("zelle", zelle), ("ox", ox), ("oy", oy)):
            if v is not None:
                b[k] = v
        if meter is not None:
            b["meterProFeld"] = meter
        if waende is not None:
            b["waendeSperren"] = waende in ("ein", True)
        if nebel_auto is not None:
            b["autoNebel"] = None if nebel_auto == "standard" else nebel_auto in ("ein", True)
        if sicht_felder is not None:
            b["sichtFelder"] = sicht_felder
        self.befehl(**b)
        return ""

    def nebel_modus(self, modus, karte=None):
        if modus not in ("sicht", "raster"):
            raise SLFehler("modus: sicht | raster")
        self.befehl(op="nebel-modus", modus=modus, karte=karte)
        return f"Nebelmodus: {modus}"

    def barrieren(self, aktion, karte=None, ids=None, typ=None, von=None, bis=None, einseitig=None, id=None, bereich=None,
                  erzwingen=False):
        b = {"karte": karte}
        if aktion == "erkennen":
            r = self.befehl(op="barrieren-erkennen", erzwingen=erzwingen, **b)
            return f"Erkannt: {r['waende']} Wandstücke, {r['tueren']} Türen. Kontrolle: vorschau mit barrieren und bereich"
        if aktion == "liste":
            r = self.befehl(op="barriere-liste", **b)
            aus = [f"Karte {r['karte']}: {r['waende']} Wandstücke, Nebelmodus: {r['nebelModus']}"]
            for e in r["extra"]:
                aus.append(f"  {e['id']:5} {e['typ']:10} {'offen' if e['offen'] else 'zu':6} von {e['von']} bis {e['bis']}"
                           f"{' einseitig ' + e['blockiertVon'] if e['blockiertVon'] else ''} ({e['quelle']})")
            return "\n".join(aus)
        if aktion == "neu":
            if not (typ and von and bis):
                raise SLFehler("barrieren neu braucht typ (wand|tuer|geheimtuer|fenster), von [X, Y], bis [X, Y]")
            return str(self.befehl(op="barriere-neu", typ=typ, von=list(von), bis=list(bis), blockiertVon=einseitig, id=id, **b))
        if aktion == "aendern":
            if not ids:
                raise SLFehler("barrieren aendern braucht eine ID")
            w = {k: v for k, v in (("typ", typ), ("blockiertVon", einseitig)) if v}
            self.befehl(op="barriere-aendern", id=ids[0], **w, **b)
            return ""
        if aktion == "weg":
            if not ids and not bereich:
                raise SLFehler("barrieren weg braucht ids oder bereich [X0, Y0, X1, Y1]")
            return str(self.befehl(op="barriere-weg", ids=ids or None, bereich=list(bereich) if bereich else None, **b))
        if aktion == "frei":
            self.befehl(op="barriere-bereiche-frei", **b)
            return ""
        raise SLFehler("aktion: erkennen | liste | neu | aendern | weg | frei")

    def tuer(self, ids=None, bei=None, auf=False, zu=False, karte=None):
        offen = True if auf else (False if zu else None)
        return str(self.befehl(op="tuer", ids=list(ids or []), bei=list(bei) if bei else None, offen=offen, karte=karte))

    def vorschau(self, karte=None, bereich=None, spieler=False, raster=5, barrieren=False, zoom=0.6,
                 max_kante=None, format="png"):
        """Rendert eine Karte mit Feldkoordinaten und Tokens. Gibt (Bilddaten, Info) zurück.
        max_kante: längste Bildkante in Pixeln begrenzen (verringert zoom)."""
        from bereiche.karte import karten
        import pymupdf
        z = self.zustand()
        kid = karte or z["karteAktiv"]
        if not kid or kid not in z["karten"]:
            raise SLFehler(f"Karte {kid!r} unbekannt")
        k = z["karten"][kid]
        bild = karten.bild_laden(str(self.kamp["karten"] / k["datei"]))
        pm = None
        if k.get("nebelModus") == "sicht" and k.get("nebelMaske") and spieler:
            from bereiche.karte import barrieren as B
            pm = B.maske_in_pixel(B.maske_dekodieren(k["nebelMaske"]), bild.shape[1], bild.shape[0])
        jpg = karten.maskiert_jpeg(bild, k, [tuple(c) for c in k.get("aufgedeckt", [])], ganz=not spieler, pixelmaske=pm)
        zl, ox, oy = k["zelle"], k["ox"], k["oy"]
        x0, y0, x1, y1 = [int(v) for v in bereich] if bereich else karten.zellbereich(k)
        clip = pymupdf.Rect(ox + x0 * zl, oy + y0 * zl, ox + (x1 + 1) * zl, oy + (y1 + 1) * zl) & pymupdf.Rect(0, 0, k["w"], k["h"])
        if clip.is_empty:
            raise SLFehler("Bereich liegt außerhalb der Karte")
        doc = pymupdf.open()
        pg = doc.new_page(width=k["w"], height=k["h"])
        pg.insert_image(pg.rect, stream=jpg)
        offen = {tuple(c) for c in k.get("aufgedeckt", [])}
        sh = pg.new_shape()
        if not spieler and k.get("nebelModus") == "sicht" and k.get("nebelMaske"):  # Sichtpolygon: Nebel pixelgenau andeuten
            from bereiche.karte import barrieren as B
            import numpy as np
            m = B.maske_in_pixel(B.maske_dekodieren(k["nebelMaske"]), bild.shape[1], bild.shape[0])
            dim = bild.copy()
            dim[~m[:dim.shape[0], :dim.shape[1]]] = (dim[~m[:dim.shape[0], :dim.shape[1]]] * 0.6).astype(np.uint8)
            pg.insert_image(pg.rect, stream=pymupdf.Pixmap(pymupdf.csRGB, dim.shape[1], dim.shape[0], np.ascontiguousarray(dim).tobytes(), 0).tobytes("jpg"))
        elif not spieler:  # Nebel halbtransparent andeuten
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    if (x, y) not in offen:
                        sh.draw_rect(pymupdf.Rect(ox + x * zl, oy + y * zl, ox + (x + 1) * zl, oy + (y + 1) * zl))
            sh.finish(fill=(0, 0, 0), fill_opacity=0.35, width=0)
        for x in range(x0, x1 + 2):
            sh.draw_line((ox + x * zl, oy + y0 * zl), (ox + x * zl, oy + (y1 + 1) * zl))
        for y in range(y0, y1 + 2):
            sh.draw_line((ox + x0 * zl, oy + y * zl), (ox + (x1 + 1) * zl, oy + y * zl))
        sh.finish(color=(1, 0, 0), width=0.6, stroke_opacity=0.5)
        sh.commit()
        if barrieren and not spieler:  # erkannte Barrieren einzeichnen (nur SL)
            from bereiche.karte import barrieren as B
            d = B.laden(self.kamp["sl"], kid)
            if d:
                sb = pg.new_shape()
                for q in B.aktive_waende(d).tolist():
                    sb.draw_line((q[0], q[1]), (q[2], q[3]))
                sb.finish(color=(1, 0, 1), width=1.2)
                sb.commit()
                for e in d["extra"]:
                    sb = pg.new_shape()
                    sb.draw_line((e["p"][0], e["p"][1]), (e["p"][2], e["p"][3]))
                    sb.finish(color={"tuer": (0, 0.5, 1), "geheimtuer": (0.6, 0, 0.8), "fenster": (0, 0.7, 0)}.get(e["typ"], (1, 0.5, 0)) if not e.get("offen") else (0.4, 1, 0.4), width=3)
                    sb.commit()
                    pg.insert_text(((e["p"][0] + e["p"][2]) / 2 + 3, (e["p"][1] + e["p"][3]) / 2 - 3), e["id"], fontsize=9, color=(0, 0.3, 1))
        raster = max(1, int(raster or 5))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if x % raster == 0 and y % raster == 0 or x == x0 and y % raster == 0 or y == y0 and x % raster == 0:
                    pg.insert_text((ox + x * zl + 2, oy + y * zl + 11), f"{x},{y}", fontsize=10, color=(1, 0, 0))
        farben = {"sc": (0.2, 0.45, 0.9), "gegner": (0.85, 0.1, 0.1), "nsc": (0.9, 0.7, 0.1), "objekt": (0.5, 0.5, 0.5)}
        for t in z["tokens"].values():
            if t.get("karte") != kid or (spieler and t["art"] != "sc" and (not t.get("sichtbar", True) or (t["x"], t["y"]) not in offen)):
                continue
            g = t.get("groesse", 1)
            r = pymupdf.Rect(ox + t["x"] * zl, oy + t["y"] * zl, ox + (t["x"] + g) * zl, oy + (t["y"] + g) * zl)
            s = pg.new_shape()
            s.draw_oval(r + (4, 4, -4, -4))
            s.finish(fill=farben.get(t["art"], (0.5, 0.5, 0.5)), color=(1, 1, 1), width=2,
                     fill_opacity=1 if t.get("sichtbar", True) else 0.45)
            s.commit()
            pg.insert_text((r.x0 + 4, r.y1 + 12), t["name"][:16], fontsize=11, color=(1, 1, 0.6))
            pg.insert_text((r.x0 + zl * g / 2 - 9, r.y0 + zl * g / 2 + 5), t["id"][:4], fontsize=12, color=(1, 1, 1))
        zoom = float(zoom or 0.6)
        info = ""
        if max_kante and max(clip.width, clip.height) * zoom > max_kante:
            zoom = max_kante / max(clip.width, clip.height)
            info = f" (verkleinert auf Zoom {zoom:.2f}; für Details einen kleineren bereich wählen)"
        pix = pg.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom))
        daten = pix.tobytes("jpg", jpg_quality=85) if format == "jpg" else pix.tobytes("png")
        return daten, f"Karte {kid}, Felder x {x0}..{x1}, y {y0}..{y1}, {pix.w}×{pix.h} px{info}"

    # ------------------------------------------------------------ Charaktere / EP / Aufstieg

    def charaktere(self):
        try:
            liste = self.anfrage("/api/charaktere")
        except SLFehler:
            liste = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.kamp["charaktere"].glob("*.json"))]
        aus = []
        for c in liste:
            tp = c.get("tp") or {}
            aus.append(f"{c['id']:18} {c.get('name', '')[:24]:24} {c.get('klasse', '')[:28]:28} TP {tp.get('aktuell')}/{tp.get('max')}"
                       f"  EP {c.get('ep', '-')}")
        return "\n".join(aus) or "(keine Charaktere)"

    def charakter(self, id, felder=None):
        """Charakterdaten (wirksame Werte inkl. Modi, wie das Tool sie rechnet) als dict."""
        cid = id[3:] if id.startswith("sc-") else id
        try:
            liste = self.anfrage("/api/charaktere")
            c = next((c for c in liste if c["id"] == cid), None)
        except SLFehler:
            p = self.kamp["charaktere"] / f"{cid}.json"
            c = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        if c is None:
            raise SLFehler(f"Charakter {cid!r} nicht gefunden ({', '.join(p.stem for p in self.kamp['charaktere'].glob('*.json'))})")
        for e in c.get("zauberliste", []):
            e.pop("_d", None)
        if felder:
            c = {k: c.get(k) for k in ["id", "name", *felder] if k in c}
        return c

    def char(self, id, werte):
        self.befehl(op="char-setzen", charId=id, werte=werte)
        return ""

    def ep(self, gegner=None, hg=None, ep=0, an=None, grund="Begegnung"):
        return str(self.befehl(op="ep", gegner=gegner or [], hg=[str(h) for h in hg or []], ep=int(ep or 0), an=an, grund=grund))

    def aufstieg(self, id):
        return self.befehl(op="aufstieg-zeigen", charId=id).get("text", "")

    def aufstieg_fertig(self, id, klasse=None, erzwingen=False):
        self.befehl(op="aufstieg-fertig", charId=id, klasse=klasse, erzwingen=erzwingen)
        return ""

    def aufstieg_zurueck(self, id, grund=""):
        self.befehl(op="aufstieg-zurueck", charId=id, grund=grund)
        return ""

    def aufstieg_abbrechen(self, id):
        self.befehl(op="aufstieg-abbrechen", charId=id)
        return ""

    def rast(self, char=None):
        self.befehl(op="rast", charId=char)
        return ""

    def charaktere_importieren(self, pdfs, ueberschreiben=False):
        import import_charaktere
        aus = []
        for i, pfad in enumerate(pdfs):
            pp = self.pfad(pfad)
            if not pp.is_file():
                raise SLFehler(f"PDF nicht gefunden: {pp}")
            c = import_charaktere.aus_pdf(str(pp), farbe_index=i)
            p = self.kamp["charaktere"] / f"{c['id']}.json"
            if p.exists() and not ueberschreiben:
                aus.append(f"übersprungen (existiert): {p.name}")
                continue
            self.anfrage("/api/charakter", c)
            aus.append(f"importiert: {c['name']} -> {p.name}")
        return "\n".join(aus)

    # ------------------------------------------------------------ Kasse / Beute / Ausrüstung / Zauberbuch

    def kasse(self, kp=None, sp=None, gp=None, pp=None, setze=False, grund=""):
        werte = {m: v for m, v in (("kp", kp), ("sp", sp), ("gp", gp), ("pp", pp)) if v is not None}
        self.befehl(op="kasse", **({"setzen": werte} if setze else {"delta": werte}), grund=grund)
        return self.ausruestung()

    def beute(self, name, an="gruppe", ort="dabei", anzahl=1, notiz=""):
        r = self.befehl(op="item-neu", name=name, traeger=an, ort=ort, anzahl=anzahl, notiz=notiz)
        return f"Gegenstand {r.get('id')} -> {an} ({ort})"

    def item(self, id, an=None, ort=None, anzahl=None, name=None, notiz=None, weg=False):
        b = {"op": "item-weg" if weg else "item-aendern", "id": int(id)}
        for k, v in (("traeger", an), ("ort", ort), ("anzahl", anzahl), ("name", name), ("notiz", notiz)):
            if v is not None:
                b[k] = v
        self.befehl(**b)
        return ""

    def buch(self, char, zauber, grad=0, weg=False):
        for name in zauber:
            self.befehl(op="buch-weg" if weg else "buch-add", charId=char, name=name, grad=grad)
        return ""

    # -------------------------------------------------------------- Zauberdatenbank (PRD, ohne Server)

    def zauber_suchen(self, text=None, klasse=None, grad=None, schule=None, volltext=False, max_treffer=40):
        """Zauber nach Name (Teilwort), Klasse, Grad, Schule; eine Zeile je Zauber."""
        if not zauber_db.prd_liste():
            raise SLFehler("Zauberdatenbank fehlt (daten/zauber_prd.json)")
        treffer, n = zauber_db.suchen(text, klasse, grad, schule, volltext, max(1, min(int(max_treffer or 40), 500)))
        if not treffer:
            return "Keine Zauber gefunden."
        aus = [zauber_db.zeile(z, klasse) for z in treffer]
        if n > len(treffer):
            aus.append(f"… {n - len(treffer)} weitere (genauer suchen oder max_treffer erhöhen)")
        return "\n".join(aus)

    def zauber_info(self, name, langtext=True):
        """Vollständige Zauberbeschreibung (Werteblock, Klassen/Grade, Text, Quelle)."""
        z = zauber_db.prd_finden(name)
        if not z:
            treffer, _ = zauber_db.suchen(name, max_treffer=8)
            raise SLFehler(f"Zauber „{name}“ nicht gefunden" + (
                ". Meintest du: " + ", ".join(t["name"] for t in treffer) if treffer else ""))
        return zauber_db.info(z, langtext)

    # -------------------------------------------------------------- Regeldatenbank (PRD-Grundregeln + Hausregeln)

    @property
    def hausregeln_datei(self):
        return self.kamp["sl"] / "hausregeln.md"

    def regel_suchen(self, frage, kategorie=None, buch=None, typ=None, max_treffer=5):
        """Top-Treffer (kurze Abschnitte mit Quelle) aus Hausregeln und PRD-Regeldatenbank."""
        if not (frage or "").strip():
            raise SLFehler("frage fehlt")
        return regeln_db.suche_text(frage, kategorie, buch, typ, max_treffer, self.hausregeln_datei)

    def regel_lesen(self, eintrag=None, seite=None, abschnitt=None, ab=0, max_zeichen=4000):
        """Volltext: Eintrags-ID aus regel_suchen, H<n> = Hausregel, oder Titel; nur seite = Inhaltsverzeichnis."""
        if eintrag in (None, "") and not seite and not abschnitt:
            return regeln_db.info_text()
        return regeln_db.lesen_text(eintrag, seite, abschnitt, ab, max_zeichen, self.hausregeln_datei)

    def regel_schnell(self, art, name=None, voraussetzung=None, kategorie=None):
        """Talent / Zustand / Fertigkeit nachschlagen (ohne Namen: Liste)."""
        return regeln_db.schnell_text(art, name, voraussetzung, kategorie, self.hausregeln_datei)

    def monster_info(self, name=None, hg=None, art=None):
        """Monster-Werteblock aus dem Monsterhandbuch (PRD); ohne Namen: Liste nach HG/Art."""
        return regeln_db.monster_text(name, hg, art)

    def regeln_aktualisieren(self, nur_index=False, meldung=None):
        """Regeldatenbank aus dem PRD aktualisieren (nur geänderte/neue Seiten per ETag), danach Index neu."""
        from bereiche.wissen import regeln_abruf
        log = []

        def m(t):
            log.append(str(t))
            if meldung:
                meldung(str(t))
        try:
            if nur_index:
                con = regeln_db.verbinden(schreiben=True)
                con.executescript(regeln_db.SCHEMA)
                regeln_abruf.rollen_bestimmen(con)
                regeln_abruf.index_bauen(con, m)
                con.close()
            else:
                regeln_abruf.aufbauen(pruefen=regeln_db.DB_DATEI.exists(), meldung=m)
        except Exception as e:  # Netz/DB-Fehler als Meldung
            raise SLFehler(f"Aktualisierung fehlgeschlagen: {e}\n" + "\n".join(log[-5:])) from None
        return "\n".join(log[-4:]) + "\n" + regeln_db.info_text()

    def ausruestung(self):
        d = self.anfrage("/api/stand")["ausruestung"]
        k = d["kasse"]
        aus = ["Kasse: " + "  ".join(f"{k[m]} {m}" for m in ("pp", "gp", "sp", "kp"))]
        chars = {c["id"]: c["name"] for c in self.anfrage("/api/charaktere")}
        traeger = {}
        for g in d["gegenstaende"]:
            traeger.setdefault(g["traeger"], []).append(g)
        for t, liste in traeger.items():
            aus.append(f"\n{chars.get(t, t)}:")
            for g in liste:
                aus.append(f"  [{g['id']}] {g['anzahl']}× {g['name']} ({g['ort']})" + (f" – {g['notiz']}" if g.get("notiz") else ""))
        return "\n".join(aus)

    # ------------------------------------------------------------ Dateien: Notizen, Quellen, Material

    def _textdatei(self, ordner, name, endung):
        if not name or any(c in name for c in "/\\:") or name.startswith("."):
            raise SLFehler(f"Ungültiger Dateiname {name!r} (nur Name, ohne Pfad)")
        if not name.lower().endswith(TEXT_ENDUNGEN):
            name += endung
        p = (ordner / name).resolve()
        if p.parent != ordner.resolve():
            raise SLFehler("Datei außerhalb des Ordners")
        return p

    def _liste(self, ordner):
        if not ordner.is_dir():
            return "(Ordner fehlt)"
        aus = []
        for p in sorted(ordner.iterdir()):
            if p.is_file() and p.suffix.lower() in TEXT_ENDUNGEN:
                with p.open(encoding="utf-8", errors="replace") as f:
                    n = sum(1 for _ in f)
                aus.append(f"{p.name:40} {n:7} Zeilen  {p.stat().st_size // 1024:6} KB")
        return "\n".join(aus) or "(leer)"

    def _lesen(self, p, von=1, bis=None, max_zeilen=400):
        if not p.exists():
            raise SLFehler(f"{p.name} gibt es nicht")
        zeilen = p.read_text(encoding="utf-8", errors="replace").splitlines()
        von = max(1, int(von or 1))
        bis = min(len(zeilen), int(bis) if bis else von + max_zeilen - 1, von + max_zeilen - 1)
        teil = [f"{i:6}\t{zeilen[i - 1]}" for i in range(von, bis + 1)]
        kopf = f"{p.name}: Zeilen {von}–{bis} von {len(zeilen)}"
        if bis < len(zeilen):
            kopf += f" (weiter mit von={bis + 1})"
        return kopf + "\n" + "\n".join(teil)

    def notizen_liste(self):
        return self._liste(self.kamp["notizen"])

    def notiz_lesen(self, datei, von=1, bis=None):
        return self._lesen(self._textdatei(self.kamp["notizen"], datei, ".md"), von, bis, max_zeilen=600)

    def notiz_schreiben(self, datei, text, ueberschreiben=False):
        p = self._textdatei(self.kamp["notizen"], datei, ".md")
        if p.exists() and not ueberschreiben:
            raise SLFehler(f"{p.name} existiert schon: ueberschreiben=true setzen, oder notiz_anhaengen/notiz_ersetzen nutzen")
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            (p.parent / ".sicherung").mkdir(exist_ok=True)
            (p.parent / ".sicherung" / f"{p.stem}-{time.strftime('%Y%m%d-%H%M%S')}{p.suffix}").write_bytes(p.read_bytes())
        p.write_text(text, encoding="utf-8")
        return f"{p.name} geschrieben ({len(text.splitlines())} Zeilen)"

    def notiz_anhaengen(self, datei, text, abschnitt=None):
        """Text ans Ende anhängen, oder ans Ende des Abschnitts mit dieser Überschrift (z. B. „Laufende Notizen“)."""
        p = self._textdatei(self.kamp["notizen"], datei, ".md")
        alt = p.read_text(encoding="utf-8") if p.exists() else ""
        text = text.rstrip("\n") + "\n"
        if abschnitt:
            zeilen = alt.splitlines(keepends=True)
            start = next((i for i, z in enumerate(zeilen) if z.lstrip().startswith("#") and abschnitt.lower() in z.lower()), None)
            if start is None:
                raise SLFehler(f"Abschnitt {abschnitt!r} nicht gefunden")
            ebene = len(zeilen[start].lstrip()) - len(zeilen[start].lstrip().lstrip("#"))
            ende = len(zeilen)
            for i in range(start + 1, len(zeilen)):
                s = zeilen[i].lstrip()
                if s.startswith("#") and len(s) - len(s.lstrip("#")) <= ebene:
                    ende = i
                    break
            while ende > start + 1 and not zeilen[ende - 1].strip():
                ende -= 1
            if ende and not zeilen[ende - 1].endswith("\n"):
                zeilen[ende - 1] += "\n"
            neu = "".join(zeilen[:ende]) + text + ("\n" if ende < len(zeilen) else "") + "".join(zeilen[ende:])
        else:
            neu = alt + ("" if not alt or alt.endswith("\n") else "\n") + text
        p.write_text(neu, encoding="utf-8")
        return f"angehängt an {p.name}" + (f" (Abschnitt {abschnitt})" if abschnitt else "")

    def notiz_ersetzen(self, datei, alt, neu, alle=False):
        p = self._textdatei(self.kamp["notizen"], datei, ".md")
        if not p.exists():
            raise SLFehler(f"{p.name} gibt es nicht")
        inhalt = p.read_text(encoding="utf-8")
        n = inhalt.count(alt)
        if n == 0:
            raise SLFehler("Text nicht gefunden (genau so, wie er in der Datei steht)")
        if n > 1 and not alle:
            raise SLFehler(f"Text kommt {n}× vor: mehr Kontext angeben oder alle=true")
        p.write_text(inhalt.replace(alt, neu) if alle else inhalt.replace(alt, neu, 1), encoding="utf-8")
        return f"{p.name}: {n if alle else 1} Stelle(n) ersetzt"

    def quellen_liste(self):
        return self._liste(self.kamp["quellen"])

    def quelle_lesen(self, datei, von=1, bis=None):
        return self._lesen(self._textdatei(self.kamp["quellen"], datei, ".txt"), von, bis, max_zeilen=400)

    def suchen(self, muster, wo="quellen", datei=None, regex=False, kontext=1, max_treffer=40):
        """Volltextsuche (ohne Groß/Klein) in Quellen und/oder Notizen, mit Zeilennummern."""
        ordner = {"quellen": [self.kamp["quellen"]], "notizen": [self.kamp["notizen"]],
                  "alle": [self.kamp["quellen"], self.kamp["notizen"]]}.get(wo)
        if ordner is None:
            raise SLFehler("wo: quellen | notizen | alle")
        try:
            rx = re.compile(muster if regex else re.escape(muster), re.IGNORECASE)
        except re.error as e:
            raise SLFehler(f"Ungültiger regulärer Ausdruck: {e}") from None
        dateien = []
        for o in ordner:
            if datei:
                dateien.append(self._textdatei(o, datei, ".txt" if o == self.kamp["quellen"] else ".md"))
            elif o.is_dir():
                dateien += sorted(p for p in o.iterdir() if p.is_file() and p.suffix.lower() in TEXT_ENDUNGEN)
        aus, n = [], 0
        kontext = max(0, min(int(kontext or 0), 10))
        for p in dateien:
            if not p.exists():
                continue
            zeilen = p.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, z in enumerate(zeilen):
                if rx.search(z):
                    n += 1
                    if n > max_treffer:
                        continue
                    a, b = max(0, i - kontext), min(len(zeilen), i + kontext + 1)
                    aus.append(f"--- {p.name}:{i + 1}")
                    aus += [f"{j + 1:6}{'>' if j == i else ' '}\t{zeilen[j]}" for j in range(a, b)]
        if not n:
            return "Keine Treffer."
        return "\n".join(aus) + (f"\n… {n} Treffer insgesamt, {max_treffer} gezeigt (genauer suchen)" if n > max_treffer else f"\n{n} Treffer")

    def quelle_aus_pdf(self, pdf, datei=None, seiten=None, ueberschreiben=False):
        """Text einer PDF (Abenteuerband) nach sl/quellen/<datei>.txt, mit Seitenmarken „=== Seite N ===“
        (Seitenzahl der PDF, passt zu material_vorschau/karte_neu)."""
        import pymupdf
        pp = self.pfad(pdf)
        if not pp.is_file():
            raise SLFehler(f"PDF nicht gefunden: {pp}")
        name = datei or re.sub(r"[^\w-]+", "_", pp.stem).strip("_").lower() or "quelle"
        ziel = self._textdatei(self.kamp["quellen"], name, ".txt")
        if ziel.exists() and not ueberschreiben:
            raise SLFehler(f"{ziel.name} existiert schon (ueberschreiben=true)")
        try:
            doc = pymupdf.open(str(pp))
        except Exception as e:  # noqa: BLE001
            raise SLFehler(f"PDF nicht lesbar: {e}") from None
        von, bis = (list(seiten) + [None, None])[:2] if seiten else (1, doc.page_count)
        von, bis = max(1, int(von or 1)), min(doc.page_count, int(bis or doc.page_count))
        if von > bis:
            raise SLFehler(f"Seitenbereich leer (PDF hat {doc.page_count} Seiten)")
        teile, leer = [], 0
        for i in range(von - 1, bis):
            t = doc[i].get_text()
            if not t.strip():
                leer += 1
            teile.append(f"=== Seite {i + 1} ===\n{t}")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text("\n".join(teile), encoding="utf-8")
        zeilen = sum(t.count("\n") + 1 for t in teile)
        hinweis = (f"; {leer} Seiten ohne Text (Scan/Bild – ggf. OCR nötig)" if leer else "")
        return f"{ziel.name}: Seiten {von}–{bis} von {doc.page_count}, {zeilen} Zeilen{hinweis}"

    def material_liste(self):
        """PDFs und Bilder im Kampagnenordner (außer sl/), für karte_neu und material_vorschau."""
        o = self.kamp["ordner"]
        aus = []
        for p in sorted(o.rglob("*")):
            rel = p.relative_to(o)
            if not p.is_file() or rel.parts[0] in ("sl", "daten", ".claude") or any(t.startswith(".") for t in rel.parts):
                continue
            if p.suffix.lower() == ".pdf" or p.suffix.lower() in BILD_ENDUNGEN:
                extra = ""
                if p.suffix.lower() == ".pdf":
                    try:
                        import pymupdf
                        with pymupdf.open(str(p)) as d:
                            extra = f"{d.page_count} Seiten"
                    except Exception:  # noqa: BLE001
                        extra = "nicht lesbar"
                aus.append(f"{rel.as_posix():50} {p.stat().st_size // 1024:8} KB  {extra}")
        return "\n".join(aus) or "(kein Material gefunden)"

    def material_vorschau(self, datei, seite=1, ausschnitt=None, max_kante=1400, gitter=True, probe_raster=None):
        """PDF-Seite oder Bild (Ausschnitt in Bruchteilen 0..1) als JPEG, mit 0,1er-Hilfsgitter für karte_neu.
        probe_raster [zelle, ox, oy]: Kandidatenraster (Bild: px des Originalbilds, PDF: pt) in Grün einzeichnen,
        um die Feldgröße für karte_neu (zelle_px / zelle_pt) zu prüfen."""
        import pymupdf
        p = self.pfad(datei)
        if not p.is_file():
            raise SLFehler(f"Datei nicht gefunden: {p}")
        x0, y0, x1, y1 = ausschnitt or [0, 0, 1, 1]
        try:
            doc = pymupdf.open(str(p))
        except Exception as e:  # noqa: BLE001
            raise SLFehler(f"Nicht lesbar: {e}") from None
        einheit = "pt"
        if not doc.is_pdf:  # Bild -> als PDF-Seite behandeln (1 pt = 1 px des Originalbilds)
            pix0 = pymupdf.Pixmap(str(p))
            doc = pymupdf.open()
            neu = doc.new_page(width=pix0.w, height=pix0.h)
            neu.insert_image(neu.rect, filename=str(p))
            einheit = "px"
        n = doc.page_count
        if not 1 <= int(seite) <= n:
            raise SLFehler(f"Seite {seite} gibt es nicht (1..{n})")
        pg = doc[int(seite) - 1]
        r = pg.rect
        clip = pymupdf.Rect(r.x0 + x0 * r.width, r.y0 + y0 * r.height, r.x0 + x1 * r.width, r.y0 + y1 * r.height)
        if probe_raster:
            zl, pox, poy = (list(probe_raster) + [0, 0])[:3]
            zl = float(zl)
            if zl < 2:
                raise SLFehler("probe_raster: Feldgröße zu klein")
            sh = pg.new_shape()
            x = r.x0 + float(pox) % zl
            while x < r.x1:
                sh.draw_line((x, r.y0), (x, r.y1))
                x += zl
            y = r.y0 + float(poy) % zl
            while y < r.y1:
                sh.draw_line((r.x0, y), (r.x1, y))
                y += zl
            sh.finish(color=(0, 0.8, 0), width=max(0.3, zl / 25), stroke_opacity=0.7)
            sh.commit()
        if gitter:
            sh = pg.new_shape()
            for i in range(11):
                f = i / 10
                sh.draw_line((r.x0 + f * r.width, r.y0), (r.x0 + f * r.width, r.y1))
                sh.draw_line((r.x0, r.y0 + f * r.height), (r.x1, r.y0 + f * r.height))
            sh.finish(color=(0, 0.7, 1), width=max(r.width, r.height) / 900, stroke_opacity=0.8)
            sh.commit()
            fs = max(r.width, r.height) / 70
            for i in range(10):
                pg.insert_text((r.x0 + (i / 10) * r.width + 2, r.y0 + fs), f".{i}", fontsize=fs, color=(0, 0.5, 1))
                pg.insert_text((r.x0 + 2, r.y0 + (i / 10) * r.height + fs * 2), f".{i}", fontsize=fs, color=(0, 0.5, 1))
        zoom = min(12.0, max_kante / max(clip.width, clip.height))
        pix = pg.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("jpg", jpg_quality=85), (
            f"{p.name} Seite {seite}/{n} ({r.width:.0f}×{r.height:.0f} {einheit}), Ausschnitt {[x0, y0, x1, y1]}, "
            f"{pix.w}×{pix.h} px, Zoom {zoom:.2f}; blaues Hilfsgitter = Bruchteile der ganzen Seite"
            + (f"; grünes Probe-Raster {probe_raster} in {einheit}" if probe_raster else ""))


# ------------------------------------------------------------------ Kampagnen verwalten (ohne laufende Kampagne)

def kampagne_neu(wurzel, name, ordner=None, port=None, pdfs=None, quellen=True, sperre=False, ep_tempo="mittel"):
    """Neue Kampagne unter `wurzel` anlegen: Ordnerstruktur (aus der Vorlage), kampagne.json mit freiem Port,
    .mcp.json und .claude/launch.json mit den Pfaden dieses Rechners, CLAUDE.md (MCP-Leitfaden), optional
    Abenteuer-PDFs nach Material/ kopieren und ihren Text nach sl/quellen/ übernehmen; sperre=True legt
    .claude/settings.json mit der Datei-Sperre an."""
    import shutil
    wurzel = Path(wurzel)
    if not wurzel.is_dir():
        raise SLFehler(f"Kampagnen-Wurzel fehlt: {wurzel}")
    if not (name or "").strip():
        raise SLFehler("Name fehlt")
    ordner = (ordner or re.sub(r"[^\w -]+", "", name)).strip()
    if not ordner or any(c in ordner for c in "/\\:") or ordner.startswith((".", "_")):
        raise SLFehler(f"Ungültiger Ordnername {ordner!r}")
    ziel = wurzel / ordner
    if ziel.exists():
        raise SLFehler(f"Ordner existiert schon: {ziel}")
    port = int(port) if port else _freier_port(wurzel)
    vorlage = vorlage_ordner(wurzel)
    if vorlage is not None:
        shutil.copytree(vorlage, ziel, ignore=shutil.ignore_patterns(
            ".claude", ".mcp.json", "CLAUDE.md", "kampagne.json", "__pycache__", ".gitkeep"))
        for md in ziel.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if "{{" in text:
                md.write_text(_platzhalter(text, ziel), encoding="utf-8")
    for d in ("sl/karten", "sl/notizen", "sl/quellen", "sl/barrieren", "daten/charaktere", "Material"):
        (ziel / d).mkdir(parents=True, exist_ok=True)
    (ziel / "kampagne.json").write_text(json.dumps({"name": name, "port": port, "epTempo": ep_tempo},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    entwurf = BASIS / "mcp" / "CLAUDE-entwurf.md"
    if entwurf.is_file():
        text = entwurf.read_text(encoding="utf-8").replace("<Kampagnenname>", name)
        text = re.sub(r"\A(# .*\n)\n> \*\*Entwurf.*?\n\n", r"\1\n", text, flags=re.S)
        (ziel / "CLAUDE.md").write_text(_platzhalter(text, ziel), encoding="utf-8")
    (ziel / "sl" / "notizen" / "kapitel1.md").write_text(
        f"# {name} – SL-Notizen\n\n## Gruppe\n\n## Laufende Notizen\n\n", encoding="utf-8")
    if sperre:
        (ziel / ".claude").mkdir(exist_ok=True)
        (ziel / ".claude" / "settings.json").write_text(json.dumps({
            "enabledMcpjsonServers": ["spieltisch"], "env": {"MCP_TOOL_TIMEOUT": "3700000"},
            "permissions": {"allow": ["mcp__spieltisch"], "deny": ["Bash", "PowerShell", "NotebookEdit"] + [
                f"{t}({_sperre_pfad(ziel)}/**)" for t in ("Read", "Edit", "Write", "Glob", "Grep")]}}, indent=2),
            encoding="utf-8")
    pfade_schreiben(ziel, port)
    aus = [f"Kampagne »{name}« angelegt: {ziel} (Port {port})"]
    st = Spieltisch(ziel, basis=ziel)
    for pdf in pdfs or []:
        q = Path(pdf).expanduser()
        if not q.is_absolute():
            q = wurzel / q
        if not q.is_file():
            aus.append(f"PDF nicht gefunden: {q}")
            continue
        kopie = ziel / "Material" / q.name
        shutil.copy2(q, kopie)
        aus.append(f"Material/{q.name} kopiert")
        if quellen:
            try:
                aus.append("Quelle: " + st.quelle_aus_pdf(f"Material/{q.name}"))
            except SLFehler as e:
                aus.append(f"Quelle {q.name}: {e}")
    aus.append("Weiter: neue Claude-Sitzung im Ordner öffnen und als vertrauenswürdig bestätigen (dann sind die "
               "spieltisch-Tools da), server_starten, Charaktere mit charaktere_importieren, Notizen in "
               "sl/notizen/kapitel1.md aufbauen (notiz_anhaengen/notiz_schreiben), Karten mit karte_neu/karte_import.")
    return "\n".join(aus)
