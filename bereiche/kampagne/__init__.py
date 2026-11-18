"""Bereich Kampagne: Kampagnenordner finden (der Ordner mit kampagne.json), Einstellungen laden, Kampagnen
auflisten, Pfade in .mcp.json/.claude dieses Rechners schreiben und prüfen, Vorlage, Python-Pfad.

Öffentlich: laden, ordner_finden, TOOL, kampagnen_liste, vorlage_ordner, python_exe, pfade_schreiben, pfade_ok,
pfade_reparieren. (Eine neue Kampagne legt sl_api.kampagne_neu an, weil dazu auch PDFs eingelesen werden.)

Kampagnenordner:

Reihenfolge: --kampagne PFAD, Umgebungsvariable SPIELTISCH_KAMPAGNE, sonst vom
aktuellen Verzeichnis aufwärts suchen.
"""
import json
import os
import re
import shutil
import socket
import sys
from pathlib import Path

from bereiche.kern import Fehler as SLFehler

TOOL = Path(__file__).resolve().parents[2]  # Programmordner
BASIS = TOOL
STANDARD = {"name": "Spieltisch", "port": 8777}


def ordner_finden(pfad=None):
    pfad = pfad or os.environ.get("SPIELTISCH_KAMPAGNE")
    if pfad:
        p = Path(pfad).expanduser().resolve()
        if not (p / "kampagne.json").is_file():
            sys.exit(f"Kein Kampagnenordner (kampagne.json fehlt): {p}")
        return p
    for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (p / "kampagne.json").is_file():
            return p
    sys.exit("Kein Kampagnenordner gefunden: --kampagne PFAD angeben, SPIELTISCH_KAMPAGNE setzen "
             "oder aus einem Ordner mit kampagne.json starten.")


def laden(pfad=None):
    """Gibt das Kampagnen-Objekt zurück: ordner, name, port, sl, daten, charaktere, protokoll, karten, notizen."""
    ordner = ordner_finden(pfad)
    cfg = dict(STANDARD)
    cfg.update(json.loads((ordner / "kampagne.json").read_text(encoding="utf-8")))
    port = int(os.environ.get("SPIELTISCH_PORT") or cfg["port"])
    sl = ordner / "sl"
    daten = ordner / "daten"
    return {
        "ordner": ordner, "name": cfg["name"], "port": port,
        "sl": sl, "daten": daten, "charaktere": daten / "charaktere", "protokoll": daten / "protokoll.jsonl",
        "karten": sl / "karten", "notizen": sl / "notizen", "quellen": sl / "quellen",
        "zustand": sl / "zustand.json", "schluessel": sl / "schluessel.txt",
        "autoNebel": bool(cfg.get("autoNebel", False)),  # automatisch aufdecken (Standard aus; pro Karte überschreibbar)
        "modi": bool(cfg.get("modi", True)),  # Modi (Hast, Größe …) auswerten; false = abgeschaltet
        "epTempo": str(cfg.get("epTempo", "mittel")).lower(),  # langsam | mittel | schnell
    }


def kampagnen_liste(wurzel):
    """Kampagnenordner unter `wurzel` mit Name, Port und ob der Server läuft."""
    wurzel = Path(wurzel)
    aus = []
    for p in sorted(wurzel.iterdir()):
        k = p / "kampagne.json"
        if not k.is_file():
            continue
        try:
            d = json.loads(k.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            aus.append(f"{p.name:32} (kampagne.json fehlerhaft)")
            continue
        port = d.get("port")
        laeuft = False
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.3):
                laeuft = True
        except (OSError, TypeError, ValueError):
            pass
        mcp = "MCP" if (p / ".mcp.json").is_file() else "-"
        aus.append(f"{p.name:32} {d.get('name', '')[:34]:34} Port {port}  {'läuft' if laeuft else 'aus':5}  {mcp}")
    return "\n".join(aus) or "(keine Kampagnen)"


def _freier_port(wurzel, start=8780):
    belegt = set()
    wurzeln = {Path(wurzel).resolve()}
    standard = BASIS.parent / "Kampagnen"  # auch die Ports der üblichen Kampagnen meiden (z. B. bei Testordnern)
    if standard.is_dir():
        wurzeln.add(standard.resolve())
    for k in [k for w in wurzeln for k in w.glob("*/kampagne.json")]:
        try:
            belegt.add(int(json.loads(k.read_text(encoding="utf-8-sig")).get("port")))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    port = start
    while True:
        if port not in belegt:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    pass
            except OSError:
                return port
        port += 1


# ------------------------------------------------------------------ Pfade (Python, Programm, Kampagne) erzeugen

VORLAGE = BASIS / "vorlage"


def vorlage_ordner(wurzel=None):
    """Vorlage für neue Kampagnen: `<Programm>/vorlage`, sonst (ältere Installationen) `<wurzel>/_Vorlage`."""
    for v in (VORLAGE, Path(wurzel) / "_Vorlage" if wurzel else None):
        if v is not None and v.is_dir():
            return v
    return None


def python_exe():
    """python.exe des laufenden Interpreters (bei pythonw.exe der Konsolen-Interpreter daneben)."""
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe" and py.with_name("python.exe").is_file():
        py = py.with_name("python.exe")
    return py


def _platzhalter(text, ziel):
    """{{PYTHON}}, {{SPIELTISCH}}, {{KAMPAGNE}} in Vorlagentexten durch die Pfade dieses Rechners ersetzen."""
    return (text.replace("{{PYTHON}}", python_exe().as_posix()).replace("{{SPIELTISCH}}", BASIS.as_posix())
            .replace("{{KAMPAGNE}}", Path(ziel).as_posix()))


def _sperre_pfad(ziel):
    z = Path(ziel).resolve().as_posix()
    return "//" + z[0].lower() + z[2:] if len(z) > 1 and z[1] == ":" else z


def _json_lesen(datei):
    try:
        d = json.loads(datei.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def pfade_schreiben(ziel, port=None):
    """`.mcp.json` (Server »spieltisch«) und `.claude/launch.json` (Konfiguration »spieltisch«) mit den echten Pfaden
    dieses Rechners schreiben; andere Einträge bleiben erhalten. Eine vorhandene Datei-Sperre
    (`.claude/settings.json`) bekommt den aktuellen Kampagnenpfad. Gibt die geänderten Dateien zurück."""
    ziel = Path(ziel).resolve()
    if port is None:
        port = _json_lesen(ziel / "kampagne.json").get("port")
    py = python_exe()
    geaendert = []

    def schreiben(datei, daten):
        neu = json.dumps(daten, ensure_ascii=False, indent=2) + "\n"
        try:
            if json.loads(datei.read_text(encoding="utf-8-sig")) == daten:
                return
        except (OSError, json.JSONDecodeError):
            pass
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(neu, encoding="utf-8")
        geaendert.append(datei.relative_to(ziel).as_posix())

    mcp = _json_lesen(ziel / ".mcp.json")
    if not isinstance(mcp.get("mcpServers"), dict):
        mcp["mcpServers"] = {}
    mcp["mcpServers"]["spieltisch"] = {
        "type": "stdio", "command": py.as_posix(), "args": [(BASIS / "mcp_server.py").as_posix(), ziel.as_posix()]}
    schreiben(ziel / ".mcp.json", mcp)

    launch = _json_lesen(ziel / ".claude" / "launch.json")
    launch.setdefault("version", "0.0.1")
    konf = [k for k in launch.get("configurations") or [] if isinstance(k, dict) and k.get("name") != "spieltisch"]
    eintrag = {"name": "spieltisch", "runtimeExecutable": str(py),
               "runtimeArgs": [str(BASIS / "server.py"), "--kampagne", str(ziel)]}
    if port:
        eintrag["port"] = int(port)
    launch["configurations"] = [eintrag] + konf
    schreiben(ziel / ".claude" / "launch.json", launch)

    settings = ziel / ".claude" / "settings.json"
    if settings.is_file():
        s = _json_lesen(settings)
        deny = (s.get("permissions") or {}).get("deny")
        if isinstance(deny, list):
            werkzeuge = ("Read", "Edit", "Write", "Glob", "Grep")
            rest = [d for d in deny if not (isinstance(d, str) and re.fullmatch(
                r"(%s)\(.*/\*\*\)" % "|".join(werkzeuge), d))]
            s["permissions"]["deny"] = rest + [f"{t}({_sperre_pfad(ziel)}/**)" for t in werkzeuge]
            schreiben(settings, s)
    return geaendert


def pfade_ok(ziel):
    """Stimmen die Pfade in `.mcp.json` (Python, Programm, Kampagne) auf diesem Rechner? None = keine .mcp.json."""
    ziel = Path(ziel)
    if not (ziel / ".mcp.json").is_file():
        return None
    s = (_json_lesen(ziel / ".mcp.json").get("mcpServers") or {}).get("spieltisch") or {}
    args = s.get("args") or []
    try:
        return bool(Path(s.get("command", "")).is_file() and len(args) >= 2
                    and Path(args[0]).resolve() == (BASIS / "mcp_server.py").resolve()
                    and Path(args[1]).resolve() == ziel.resolve())
    except (OSError, TypeError, ValueError):
        return False


def pfade_reparieren(ziel):
    """Pfade einer vorhandenen Kampagne neu erzeugen (z. B. nach Verschieben oder auf einem anderen Rechner)."""
    ziel = Path(ziel)
    if not (ziel / "kampagne.json").is_file():
        raise SLFehler(f"Keine Kampagne (kampagne.json fehlt): {ziel}")
    geaendert = pfade_schreiben(ziel)
    return (f"Pfade aktualisiert ({', '.join(geaendert)})" if geaendert else "Pfade waren schon richtig") + \
        f" – Python {python_exe()}, Programm {BASIS}"
