"""Hilfen für die Ablauf-Tests: Testkampagne im Temp-Ordner, echter Server auf freiem Port.

    with Testkampagne() as tk:          # oder in setUpClass/tearDownClass
        tk.st.erzaehle("Hallo")         # sl_api.Spieltisch dieser Kampagne
        tk.spieler("/api/aktion", {"text": "Wir gehen los", "wer": "Brak"})
        tk.stand()                      # Spielersicht, tk.stand(sl=True) SL-Sicht

Die Live-Kampagnen werden nie angefasst: alles liegt in einem eigenen Temp-Ordner.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))

import sl_api  # noqa: E402


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HTTPFehler(Exception):
    def __init__(self, code, text):
        super().__init__(f"{code}: {text}")
        self.code, self.text = code, text


def server_starten(ordner, port, warten=30):
    """Startet server.py für den Kampagnenordner; gibt den Prozess zurück, sobald der Port antwortet."""
    log = open(Path(ordner) / "server-test.log", "w", encoding="utf-8")
    umg = dict(os.environ, SPIELTISCH_PORT=str(port), PYTHONIOENCODING="utf-8")
    umg.pop("SPIELTISCH_KAMPAGNE", None)
    p = subprocess.Popen([sys.executable, str(TOOL / "server.py"), "--kampagne", str(ordner)], cwd=str(TOOL),
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=umg)
    ende = time.time() + warten
    while time.time() < ende:
        if p.poll() is not None:
            log.close()
            raise RuntimeError("Server beendet sich sofort:\n" + (Path(ordner) / "server-test.log").read_text("utf-8"))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                p._log = log
                return p
        except OSError:
            time.sleep(0.15)
    p.kill()
    log.close()
    raise RuntimeError("Server antwortet nicht")


def server_stoppen(p):
    if p is None:
        return
    p.kill()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        pass
    getattr(p, "_log", None) and p._log.close()


class Testkampagne:
    """Frische Kampagne (kampagne.json, Charaktere aus fixtures/charaktere) mit laufendem Server."""

    def __init__(self, charaktere=("brak", "mira", "lied", "lern"), name="Testkampagne", extra=None):
        self.tmp = Path(tempfile.mkdtemp(prefix="spieltisch-test-"))
        self.ordner = self.tmp / "kampagne"
        (self.ordner / "daten" / "charaktere").mkdir(parents=True)
        (self.ordner / "sl").mkdir()
        self.port = freier_port()
        cfg = {"name": name, "port": self.port, **(extra or {})}
        (self.ordner / "kampagne.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        for cid in charaktere:
            shutil.copy(FIXTURES / "charaktere" / f"{cid}.json", self.ordner / "daten" / "charaktere")
        self.proc = None
        self.st = None

    # -- Lebenszyklus
    def starten(self):
        self.proc = server_starten(self.ordner, self.port)
        os.environ.pop("SPIELTISCH_PORT", None)
        self.st = sl_api.Spieltisch(str(self.ordner), basis=str(self.ordner))
        self.st.port = self.port
        self.st.url = f"http://127.0.0.1:{self.port}"
        return self

    def neu_starten(self):
        server_stoppen(self.proc)
        return self.starten()

    def beenden(self):
        server_stoppen(self.proc)
        self.proc = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self.starten()

    def __exit__(self, *a):
        self.beenden()

    # -- HTTP
    def http(self, pfad, daten=None, sl=False, roh=False):
        kopf = {"Content-Type": "application/json"}
        if sl:
            kopf["X-SL"] = self.st.key
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", headers=kopf,
                                     data=None if daten is None else json.dumps(daten).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                inhalt = r.read()
                return inhalt if roh else json.loads(inhalt or b"{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                text = json.loads(text).get("fehler", text)
            except (json.JSONDecodeError, AttributeError):
                pass
            raise HTTPFehler(e.code, text) from None

    def spieler(self, pfad, daten):
        """POST als Spieler (ohne SL-Schlüssel)."""
        return self.http(pfad, daten)

    def sl(self, **b):
        return self.http("/api/sl/befehl", b, sl=True)

    def stand(self, sl=False):
        return self.http("/api/stand", sl=sl)

    def z(self):
        return self.http("/api/sl/zustand", sl=True)

    def log(self, seit=0):
        return self.http(f"/api/sl/ereignisse?seit={seit}", sl=True)["eintraege"]

    def letzte_id(self):
        lg = self.log()
        return lg[-1]["id"] if lg else 0

    def charakter(self, cid):
        return next(c for c in self.http("/api/charaktere") if c["id"] == cid)

    def datei_charakter(self, cid):
        return json.loads((self.ordner / "daten" / "charaktere" / f"{cid}.json").read_text(encoding="utf-8"))

    # -- Aufbau
    def karte_leer(self, kid="test", felder=(20, 15), aufdecken=True):
        self.st.karte_neu(kid, "Testkarte", leer=list(felder), aktiv=True)
        if aufdecken:
            self.sl(op="aufdecken", form="alles")

    def sc(self, cid, x, y):
        self.spieler("/api/sc-platzieren", {"charId": cid, "x": x, "y": y})
        return "sc-" + cid

    def gegner(self, name, x, y, **werte):
        t = {"art": "gegner", "name": name, "x": x, "y": y, **werte}
        if "tp" in t:
            t["tpMax"] = t.pop("tp")
        return self.sl(op="token-setzen", token=t)["id"]


RK_RE = re.compile(r": (-?\d+) gegen RK (-?\d+)(?: \([^)]*\))? → (Treffer|daneben)")


def letzter_angriff(tk, seit=0):
    """(Angriffseintrag, RK aus der SL-Notiz) des letzten Angriffs seit Protokoll-ID `seit`."""
    lg = [e for e in tk.log(seit)]
    angriff = [e for e in lg if e["art"] == "angriff"][-1]
    notiz = [e for e in lg if e["art"] == "sl-notiz" and " gegen RK " in e["text"]]
    rk = int(RK_RE.search(notiz[-1]["text"]).group(2)) if notiz else None
    return angriff, rk


def w20(angriff):
    """Natürlicher W20-Wurf aus dem Angriffsdetail („1W20[17] +7 …“)."""
    return int(re.match(r"1W20\[(\d+)\]", angriff["detail"]).group(1))


FEHLER = (HTTPFehler, sl_api.SLFehler)  # Fehlermeldung vom Server, egal ob über HTTP direkt oder sl_api
