"""Spieltisch-Zentrale: Desktop-Anwendung zum Verwalten der Kampagnen.

Start:  pythonw zentrale.py [--wurzel <Kampagnen-Ordner>] [--port 8770] [--ohne-fenster]

Ein Fenster (pywebview, Edge WebView2) mit der Kampagnenübersicht: Server starten/stoppen, Spieler- und SL-Ansicht
in eigenen Fenstern öffnen, neue Kampagne anlegen, MCP einrichten, Ordner und Server-Protokoll öffnen.
Technisch: kleiner lokaler HTTP-Dienst (nur 127.0.0.1) + Oberfläche web/zentrale.html; das Fenster zeigt diese Seite.
Spieltisch-Server, Weboberfläche, sl.py und MCP bleiben unverändert. Server, die die Zentrale gestartet hat, werden
beim Schließen gestoppt (abschaltbar in den Einstellungen).
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASIS = Path(__file__).resolve().parent
sys.path.insert(0, str(BASIS))
import sl_api  # noqa: E402

EINSTELLUNGEN = BASIS / "zentrale.json"
PY = sl_api.python_exe()  # Server ohne Fenster, aber mit normalem Interpreter (Ausgabe ins Log)
OHNE_FENSTER = 0x08000000 if sys.platform == "win32" else 0

FENSTER = {"haupt": None, "webview": None}
GESTARTET = {}  # Ordnername -> subprocess.Popen (von der Zentrale gestartete Server)
ESTELL = {"wurzel": str(BASIS.parent / "Kampagnen"), "beimBeendenStoppen": True}


class ZFehler(Exception):
    pass


# ------------------------------------------------------------------ Einstellungen / Kampagnen

def einstellungen_laden(wurzel=None):
    if EINSTELLUNGEN.is_file():
        try:
            ESTELL.update(json.loads(EINSTELLUNGEN.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    if wurzel:
        ESTELL["wurzel"] = str(Path(wurzel).resolve())


def einstellungen_speichern():
    EINSTELLUNGEN.write_text(json.dumps(ESTELL, ensure_ascii=False, indent=2), encoding="utf-8")


def wurzel():
    return Path(ESTELL["wurzel"])


def kampagne(ordner):
    """Ordnername -> Pfad (nur direkte Unterordner der Wurzel mit kampagne.json)."""
    if not ordner or any(c in ordner for c in "/\\:") or ordner in (".", ".."):
        raise ZFehler("Ungültiger Ordner")
    p = wurzel() / ordner
    if not (p / "kampagne.json").is_file():
        raise ZFehler(f"Keine Kampagne: {ordner}")
    return p


def cfg(p):
    try:
        return json.loads((p / "kampagne.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def port_offen(port):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.25):
            return True
    except (OSError, TypeError, ValueError):
        return False


def sl_info(p, port):
    """SL-Status und Zahl unbeantworteter Spieleraktionen einer laufenden Kampagne."""
    key = (p / "sl" / "schluessel.txt").read_text(encoding="utf-8").strip() if (p / "sl" / "schluessel.txt").exists() else ""

    def get(pfad):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{pfad}", headers={"X-SL": key})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return json.loads(r.read())
    try:
        r = get("/api/sl/ereignisse?seit=999999999999")
        lv = r["letzteVerarbeitet"]
        neu = get(f"/api/sl/ereignisse?seit={lv}")["eintraege"]
        offen = [e for e in neu if e.get("wecken", e["art"] == "spieler")]
        z = get("/api/sl/zustand")
        return {"slStatus": r.get("slStatus"), "offen": len(offen),
                "letztes": (offen[-1].get("text") or "")[:120] if offen else "",
                "szene": (z.get("szene") or {}).get("titel", ""), "karte": z.get("karteAktiv")}
    except Exception:  # noqa: BLE001
        return {}


def liste():
    w = wurzel()
    if not w.is_dir():
        raise ZFehler(f"Kampagnen-Ordner fehlt: {w}")
    aus = []
    ports = {}
    for p in sorted(w.iterdir(), key=lambda q: q.name.lower()):
        if not (p / "kampagne.json").is_file() or p.name.startswith(("_", ".")):
            continue
        c = cfg(p)
        port = c.get("port")
        ports.setdefault(port, []).append(p.name)
        proc = GESTARTET.get(p.name)
        if proc is not None and proc.poll() is not None:
            GESTARTET.pop(p.name, None)
            proc = None
        laeuft = port_offen(port)
        e = {"ordner": p.name, "name": c.get("name", p.name), "port": port, "laeuft": laeuft,
             "vonZentrale": proc is not None, "mcp": (p / ".mcp.json").is_file(), "pfadeOk": sl_api.pfade_ok(p) is not False,
             "sperre": (p / ".claude" / "settings.json").is_file(),
             "charaktere": len(list((p / "daten" / "charaktere").glob("*.json"))),
             "karten": len(list((p / "sl" / "karten").glob("*.png"))),
             "quellen": len(list((p / "sl" / "quellen").glob("*.txt"))),
             "logFehler": False}
        log = p / "sl" / "server.log"
        if proc is None and not laeuft and log.exists():
            try:
                e["logFehler"] = "Traceback" in log.read_text(encoding="utf-8", errors="replace")[-3000:]
            except OSError:
                pass
        if laeuft:
            e.update(sl_info(p, port))
        aus.append(e)
    for e in aus:
        e["portDoppelt"] = len(ports.get(e["port"], [])) > 1
    return {"wurzel": str(w), "kampagnen": aus, "beimBeendenStoppen": ESTELL["beimBeendenStoppen"],
            "fenster": FENSTER["webview"] is not None}


# ------------------------------------------------------------------ Server starten / stoppen

def pid_auf_port(port):
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, timeout=10,
                             creationflags=OHNE_FENSTER).stdout.decode("cp850", "replace")
    except (OSError, subprocess.SubprocessError):
        return None
    for z in out.splitlines():
        t = z.split()  # lauschende Verbindungen haben die Gegenadresse 0.0.0.0:0 (sprachunabhängig)
        if len(t) >= 5 and t[2] in ("0.0.0.0:0", "[::]:0") and t[1].endswith(f":{port}") and t[4].isdigit():
            return int(t[4])
    return None


def befehlszeile(pid):
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                              f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                             capture_output=True, timeout=15, creationflags=OHNE_FENSTER).stdout
        return (out or b"").decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def starten(ordner):
    p = kampagne(ordner)
    port = cfg(p).get("port")
    if not port:
        raise ZFehler("Kein Port in kampagne.json")
    if port_offen(port):
        raise ZFehler(f"Port {port} ist schon belegt (läuft der Server schon, oder eine andere Kampagne mit gleichem Port?)")
    log = open(p / "sl" / "server.log", "a", encoding="utf-8")
    log.write(f"\n--- gestartet von der Zentrale {time.strftime('%d.%m.%Y %H:%M:%S')} ---\n")
    log.flush()
    proc = subprocess.Popen([str(PY), str(BASIS / "server.py"), "--kampagne", str(p)], cwd=str(BASIS), stdout=log,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=OHNE_FENSTER,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    GESTARTET[ordner] = proc
    ende = time.time() + 20
    while time.time() < ende:
        if port_offen(port):
            return f"{cfg(p).get('name', ordner)} läuft auf Port {port}"
        if proc.poll() is not None:
            GESTARTET.pop(ordner, None)
            raise ZFehler("Server ist beim Start abgebrochen – Protokoll ansehen")
        time.sleep(0.3)
    raise ZFehler("Server antwortet nicht – Protokoll ansehen")


def stoppen(ordner):
    p = kampagne(ordner)
    port = cfg(p).get("port")
    proc = GESTARTET.pop(ordner, None)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return "gestoppt"
    pid = pid_auf_port(port)
    if not pid:
        return "lief nicht"
    zeile = befehlszeile(pid)
    if "server.py" not in zeile or p.name not in zeile:
        raise ZFehler(f"Auf Port {port} läuft ein anderes Programm (PID {pid}) – nicht gestoppt")
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=OHNE_FENSTER)
    return "gestoppt"


def alle_stoppen():
    for ordner, proc in list(GESTARTET.items()):
        if proc.poll() is None:
            proc.terminate()
    GESTARTET.clear()


# ------------------------------------------------------------------ Fenster, Ordner, Protokoll

def url(ordner, sl):
    p = kampagne(ordner)
    port = cfg(p).get("port")
    u = f"http://localhost:{port}/"
    if sl:
        key = (p / "sl" / "schluessel.txt").read_text(encoding="utf-8").strip()
        u += f"?sl={key}"
    return u, port


def oeffnen(ordner, sl, im_browser=False):
    u, port = url(ordner, sl)
    if not port_offen(port):
        raise ZFehler("Server läuft nicht – erst starten")
    wv = FENSTER["webview"]
    if im_browser or wv is None:
        webbrowser.open(u)
        return "im Browser geöffnet"
    name = cfg(kampagne(ordner)).get("name", ordner)
    wv.create_window(f"{name} – {'SL-Ansicht' if sl else 'Spieleransicht'}", u, width=1400, height=900,
                     min_size=(800, 500), text_select=True)
    return "Fenster geöffnet"


def ordner_oeffnen(ordner, unter=""):
    p = kampagne(ordner)
    ziel = p / unter if unter in ("", "Material", "sl/notizen", "sl/karten") else p
    os.startfile(str(ziel))  # noqa: S606
    return "ok"


def protokoll(ordner, n=120):
    log = kampagne(ordner) / "sl" / "server.log"
    if not log.exists():
        return "(noch kein Server-Protokoll)"
    zeilen = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(zeilen[-n:])


def mcp_einrichten(ordner):
    p = kampagne(ordner)
    if (p / ".mcp.json").exists():
        raise ZFehler(".mcp.json gibt es schon")
    sl_api.pfade_schreiben(p)
    return ".mcp.json angelegt (Server »spieltisch«); CLAUDE.md und Sperre bleiben unverändert"


def pfade_reparieren(ordner):
    return sl_api.pfade_reparieren(kampagne(ordner))


def dateien_waehlen():
    wv = FENSTER["webview"]
    if wv is None or FENSTER["haupt"] is None:
        raise ZFehler("Dateiauswahl nur im Desktop-Fenster – Pfade bitte eintragen")
    r = FENSTER["haupt"].create_file_dialog(wv.FileDialog.OPEN, allow_multiple=True,
                                            file_types=("PDF (*.pdf)", "Alle Dateien (*.*)"))
    return list(r or [])


def wurzel_waehlen():
    wv = FENSTER["webview"]
    if wv is None or FENSTER["haupt"] is None:
        raise ZFehler("Ordnerauswahl nur im Desktop-Fenster")
    r = FENSTER["haupt"].create_file_dialog(wv.FileDialog.FOLDER, directory=ESTELL["wurzel"])
    if r:
        ESTELL["wurzel"] = str(Path(r[0] if isinstance(r, (list, tuple)) else r).resolve())
        einstellungen_speichern()
    return ESTELL["wurzel"]


# ------------------------------------------------------------------ HTTP

class Dienst(ThreadingHTTPServer):
    allow_reuse_address = False  # unter Windows würde sonst ein zweiter Prozess denselben Port belegen
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def senden(self, code, daten, typ="application/json; charset=utf-8"):
        if not isinstance(daten, (bytes, bytearray)):
            daten = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(daten)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/zentrale.html"):
                return self.senden(200, (BASIS / "web" / "zentrale.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/z/liste":
                return self.senden(200, liste())
            if u.path == "/api/z/protokoll":
                return self.senden(200, {"text": protokoll(q.get("ordner", [""])[0])})
            return self.senden(404, {"fehler": "nicht gefunden"})
        except (ZFehler, sl_api.SLFehler) as e:
            return self.senden(400, {"fehler": str(e)})
        except Exception as e:  # noqa: BLE001
            return self.senden(500, {"fehler": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        if self.headers.get("X-Zentrale") != "1":  # nur die eigene Seite (einfacher Schutz gegen fremde Seiten)
            return self.senden(403, {"fehler": "verboten"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n) or b"{}") if n else {}
            o = b.get("ordner", "")
            if u.path == "/api/z/starten":
                return self.senden(200, {"text": starten(o)})
            if u.path == "/api/z/stoppen":
                return self.senden(200, {"text": stoppen(o)})
            if u.path == "/api/z/oeffnen":
                return self.senden(200, {"text": oeffnen(o, bool(b.get("sl")), bool(b.get("browser")))})
            if u.path == "/api/z/ordner":
                return self.senden(200, {"text": ordner_oeffnen(o, b.get("unter", ""))})
            if u.path == "/api/z/mcp":
                return self.senden(200, {"text": mcp_einrichten(o)})
            if u.path == "/api/z/pfade":
                return self.senden(200, {"text": pfade_reparieren(o)})
            if u.path == "/api/z/dateien":
                return self.senden(200, {"dateien": dateien_waehlen()})
            if u.path == "/api/z/wurzel":
                return self.senden(200, {"wurzel": wurzel_waehlen()})
            if u.path == "/api/z/einstellung":
                if "beimBeendenStoppen" in b:
                    ESTELL["beimBeendenStoppen"] = bool(b["beimBeendenStoppen"])
                einstellungen_speichern()
                return self.senden(200, {"text": "gespeichert"})
            if u.path == "/api/z/neu":
                pdfs = [x for x in (b.get("pdfs") or []) if str(x).strip()]
                text = sl_api.kampagne_neu(wurzel(), b.get("name", ""), b.get("ordnerName") or None, b.get("port") or None,
                                           pdfs, True, bool(b.get("sperre")), b.get("epTempo") or "mittel")
                return self.senden(200, {"text": text})
            return self.senden(404, {"fehler": "nicht gefunden"})
        except (ZFehler, sl_api.SLFehler) as e:
            return self.senden(400, {"fehler": str(e)})
        except Exception as e:  # noqa: BLE001
            return self.senden(500, {"fehler": f"{type(e).__name__}: {e}"})


def main():
    ap = argparse.ArgumentParser(description="Spieltisch-Zentrale")
    ap.add_argument("--wurzel", help="Ordner mit den Kampagnenordnern (Standard: ..\\Kampagnen bzw. gespeichert)")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--ohne-fenster", action="store_true", help="nur der Dienst, ohne Desktop-Fenster")
    ap.add_argument("--browser", action="store_true", help="mit --ohne-fenster: Seite im Standardbrowser öffnen")
    a = ap.parse_args()
    einstellungen_laden(a.wurzel)
    try:
        srv = Dienst(("127.0.0.1", a.port), Handler)
    except OSError:
        srv = None  # Zentrale läuft schon: nur ein weiteres Fenster darauf öffnen
    if srv is not None:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    adresse = f"http://127.0.0.1:{a.port}/"
    if a.ohne_fenster:
        print(f"Zentrale: {adresse}", flush=True)
        if a.browser:
            webbrowser.open(adresse)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        try:
            import webview
        except ImportError:  # pywebview fehlt (z. B. sehr neues Python ohne passendes pythonnet): Browser statt Fenster
            webview = None
    if not a.ohne_fenster and webview is None:
        print(f"pywebview fehlt – Zentrale im Browser: {adresse}", flush=True)
        webbrowser.open(adresse)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    elif not a.ohne_fenster:
        FENSTER["webview"] = webview
        FENSTER["haupt"] = webview.create_window("Spieltisch – Kampagnen", adresse, width=1180, height=760,
                                                 min_size=(820, 520))

        def haupt_zu():  # Hauptfenster zu -> alle Spielfenster schließen, damit die App endet
            for w in list(webview.windows):
                if w is not FENSTER["haupt"]:
                    try:
                        w.destroy()
                    except Exception:  # noqa: BLE001
                        pass
        FENSTER["haupt"].events.closed += haupt_zu
        webview.start()
    if ESTELL["beimBeendenStoppen"]:
        alle_stoppen()


if __name__ == "__main__":
    main()
