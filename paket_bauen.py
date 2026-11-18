"""Baut ein ZIP zum Weitergeben des Spieltischs an einen anderen Rechner.

    python paket_bauen.py [--ziel dist] [--name Spieltisch-JJJJ-MM-TT]

Enthalten (Ordner „Spieltisch/“ im ZIP): Programmdateien (*.py ohne dieses Skript), web/, mcp/ (ohne Entwickler-Patches),
daten/ (Regeldaten: zauber.json, zauber_prd.json mit LIZENZ-ZAUBER.txt), regeln/regeln.sqlite mit
regeln/LIZENZ-REGELN.txt (Regeldatenbank; ohne regeln/cache und regeln/md), vorlage/, ANLEITUNG.md/.pdf, AGENT.md, README.md, einrichten.bat, start.bat, zentrale.bat,
python_finden.bat. Nicht enthalten: Kampagnen, _sicherung-*, __pycache__, *.bak*, Logs, Schlüssel, zentrale.json,
python-pfad.txt, Verknüpfungen (*.lnk), dist/. Das Ergebnis wird auf Pfade/Namen dieses Rechners geprüft.

    python paket_bauen.py --pruefen   nur prüfen (alle Dateien im Git-Repo bzw. im Paket), nichts bauen
"""
import argparse
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

BASIS = Path(__file__).resolve().parent

DATEIEN = ["ANLEITUNG.md", "ANLEITUNG.pdf", "AGENT.md", "README.md", "LICENSE", "ARCHITEKTUR.md", "STYLEGUIDE.md",
           "einrichten.bat", "start.bat", "zentrale.bat", "python_finden.bat"]
ORDNER = ["web", "mcp", "daten", "vorlage", "bereiche"]
# Regeldatenbank: nur Datenbank + Lizenz (Cache und Markdown-Ausgabe entstehen auf dem Zielrechner bei Bedarf)
REGELN = ["regeln/regeln.sqlite", "regeln/LIZENZ-REGELN.txt"]
# Ohne diese Dateien wird nicht gebaut (die PRD-Daten dürfen nur mit Lizenztext weitergegeben werden)
PFLICHT = ["bereiche/wissen/zauber_db.py", "daten/zauber.json", "daten/zauber_prd.json", "daten/LIZENZ-ZAUBER.txt",
           "bereiche/wissen/regeln_db.py", "bereiche/wissen/regeln_abruf.py", "bereiche/wissen/regeln_md.py",
           "regeln_abruf.py"] + REGELN
OHNE_PY = {"paket_bauen.py", "anleitung_pdf.py"}
AUSSCHLUSS = [r"(^|/)__pycache__/", r"(^|/)_sicherung", r"\.bak", r"\.log$", r"\.lnk$", r"(^|/)Thumbs\.db$",
              r"(^|/)desktop\.ini$", r"(^|/)schluessel\.txt$", r"(^|/)zentrale\.json$", r"(^|/)python-pfad\.txt$",
              r"\.patch$", r"(^|/)\.~lock", r"\.pyc$", r"(^|/)\.claude/", r"(^|/)\.mcp\.json$"]
TEXT = {".py", ".md", ".json", ".bat", ".html", ".js", ".css", ".txt"}


def sammeln():
    aus = [p for p in sorted(BASIS.glob("*.py")) if p.name not in OHNE_PY]
    fehlt = []
    for n in DATEIEN:
        (aus.append(BASIS / n) if (BASIS / n).is_file() else fehlt.append(n))
    for o in ORDNER:
        if not (BASIS / o).is_dir():
            fehlt.append(o + "/")
            continue
        aus += [p for p in sorted((BASIS / o).rglob("*")) if p.is_file()]
    for n in REGELN:
        (aus.append(BASIS / n) if (BASIS / n).is_file() else fehlt.append(n))
    rel = lambda p: p.relative_to(BASIS).as_posix()  # noqa: E731
    return [p for p in aus if not any(re.search(m, rel(p)) for m in AUSSCHLUSS)], fehlt


def pdf_text(p):
    """Text, Metadaten und Link-Ziele einer PDF (dort landen z. B. absolute Dateipfade relativer Links)."""
    try:
        import pymupdf
    except ImportError:
        return p.read_bytes().decode("latin-1")
    with pymupdf.open(p) as d:
        teile = [str(d.metadata)]
        for s in d:
            teile.append(s.get_text())
            teile += [str(link.get("uri") or link.get("file") or "") for link in s.get_links()]
    return "\n".join(teile)


def verdaechtig(dateien):
    """Persönliche Pfade/Namen dieses Rechners in Text- und PDF-Dateien finden."""
    muster = {re.escape(str(BASIS.parent)), re.escape(BASIS.parent.as_posix()), r"file:///"}
    benutzer = os.environ.get("USERNAME")
    if benutzer:
        muster.add(r"Users[\\/]+" + re.escape(benutzer))
    rx = re.compile("|".join(sorted(muster)), re.I)
    funde = []
    for p in dateien:
        if p.name == Path(__file__).name:  # enthält die Suchmuster selbst
            continue
        if p.suffix.lower() == ".pdf":
            text = pdf_text(p)
        elif p.suffix.lower() in TEXT:
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            continue
        for i, z in enumerate(text.splitlines(), 1):
            if rx.search(z):
                funde.append(f"{p.relative_to(BASIS).as_posix()}:{i}: {z.strip()[:110]}")
    return funde


def git_dateien():
    """Alle Dateien, die Git einchecken würde (verfolgte + neue, nicht ignorierte); None ohne Git-Repo."""
    if not (BASIS / ".git").exists():
        return None
    try:
        r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=BASIS, capture_output=True)
    except OSError:
        return None
    if r.returncode:
        return None
    return [BASIS / n for n in r.stdout.decode("utf-8").split("\0") if n and (BASIS / n).is_file()]


def main():
    ap = argparse.ArgumentParser(description="ZIP zum Weitergeben bauen")
    ap.add_argument("--ziel", default=str(BASIS / "dist"))
    ap.add_argument("--name", default="Spieltisch-" + time.strftime("%Y-%m-%d"))
    ap.add_argument("--trotzdem", action="store_true", help="auch bauen, wenn persönliche Pfade gefunden wurden")
    ap.add_argument("--pruefen", action="store_true", help="nur auf Pfade/Namen dieses Rechners prüfen (Git-Dateien)")
    a = ap.parse_args()
    if a.pruefen:
        dateien = git_dateien() or sammeln()[0]
        funde = verdaechtig(dateien)
        print("\n".join(funde) if funde else f"ok: {len(dateien)} Dateien ohne Pfade/Namen dieses Rechners")
        sys.exit(1 if funde else 0)
    dateien, fehlt = sammeln()
    if fehlt:
        print("Fehlt im Programmordner:", ", ".join(fehlt))
    pflicht_fehlt = [n for n in PFLICHT if not (BASIS / n).is_file()]
    if pflicht_fehlt:
        sys.exit("Abgebrochen, Pflichtdateien fehlen: " + ", ".join(pflicht_fehlt))
    funde = verdaechtig(dateien)
    if funde:
        print("Pfade/Namen dieses Rechners in:")
        print("\n".join("  " + f for f in funde))
        if not a.trotzdem:
            sys.exit("Abgebrochen (mit --trotzdem trotzdem bauen).")
    ziel = Path(a.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    zipdatei = ziel / f"{a.name}.zip"
    with zipfile.ZipFile(zipdatei, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in dateien:
            daten = p.read_bytes()
            if p.suffix.lower() == ".bat":  # cmd braucht CRLF
                daten = re.sub(rb"\r?\n", b"\r\n", daten)
            z.writestr(zipfile.ZipInfo.from_file(p, "Spieltisch/" + p.relative_to(BASIS).as_posix()), daten,
                       zipfile.ZIP_DEFLATED)
        for leer in ("vorlage/Material", "vorlage/daten/charaktere", "vorlage/sl/karten", "vorlage/sl/quellen"):
            if not any(d.relative_to(BASIS).as_posix().startswith(leer + "/") for d in dateien):
                z.writestr(f"Spieltisch/{leer}/", b"")
    print(f"{zipdatei}  ({len(dateien)} Dateien, {zipdatei.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
