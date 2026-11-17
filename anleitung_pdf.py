"""ANLEITUNG.md -> ANLEITUNG.pdf (eigener kleiner Markdown-Umsetzer + Edge headless --print-to-pdf).

    python anleitung_pdf.py [ANLEITUNG.md] [ANLEITUNG.pdf]

Kann: Überschriften, Absätze, Listen (auch geschachtelt/nummeriert), Tabellen, Codeblöcke, **fett**, *kursiv*,
`code`, Links, <https://…>, Trennlinien.
"""
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASIS = Path(__file__).resolve().parent

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.45 "Segoe UI", system-ui, sans-serif; color: #1d1a16; }
h1 { font: 600 21pt Georgia, serif; color: #7a5212; border-bottom: 2px solid #d6a84b; padding-bottom: 4px; margin: 0 0 10px; }
h2 { font: 600 15pt Georgia, serif; color: #7a5212; margin: 20px 0 6px; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 14px 0 4px; page-break-after: avoid; }
p { margin: 5px 0; }
ul, ol { margin: 4px 0 6px; padding-left: 22px; } li { margin: 2px 0; }
code { font: 9pt Consolas, monospace; background: #f3eee4; padding: 0 3px; border-radius: 3px; }
pre { background: #f3eee4; border: 1px solid #e2d8c4; border-radius: 5px; padding: 7px 9px; font: 9pt/1.35 Consolas, monospace; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 9.5pt; page-break-inside: auto; }
th, td { border: 1px solid #d9cfbd; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #efe6d3; } tr { page-break-inside: avoid; }
hr { border: 0; border-top: 1px solid #d9cfbd; margin: 14px 0; }
a { color: #7a5212; }
"""


def inline(t):
    codes = []

    def merken(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"
    s = html.escape(re.sub(r"`([^`]+)`", merken, t), quote=False)
    s = re.sub(r"&lt;(https?://[^&\s]+)&gt;", r'<a href="\1">\1</a>', s)
    # nur Web-Links verlinken; relative Links (README.md …) würden im PDF zu absoluten Dateipfaden dieses Rechners
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<u>\1</u>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def umsetzen(md):
    zeilen = md.splitlines()
    aus, i, absatz = [], 0, []
    listen = []  # Stapel [(typ, einrueckung)]

    def absatz_ende():
        if absatz:
            aus.append(f"<p>{inline(' '.join(absatz))}</p>")
            absatz.clear()

    def listen_ende(bis=-1):
        while listen and listen[-1][1] > bis:
            aus.append(f"</li></{listen.pop()[0]}>")

    while i < len(zeilen):
        z = zeilen[i]
        if z.startswith("```"):
            absatz_ende(); listen_ende()
            j = i + 1
            while j < len(zeilen) and not zeilen[j].startswith("```"):
                j += 1
            aus.append("<pre><code>" + html.escape("\n".join(zeilen[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)", z)
        if m:
            absatz_ende(); listen_ende()
            n = len(m.group(1))
            aus.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
            continue
        if re.fullmatch(r"\s*-{3,}\s*", z):
            absatz_ende(); listen_ende()
            aus.append("<hr>")
            i += 1
            continue
        if z.startswith("|") and i + 1 < len(zeilen) and re.fullmatch(r"\|[\s:|-]+\|?", zeilen[i + 1].strip()):
            absatz_ende(); listen_ende()
            zellen = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]  # noqa: E731
            aus.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in zellen(z)) + "</tr>")
            i += 2
            while i < len(zeilen) and zeilen[i].startswith("|"):
                aus.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in zellen(zeilen[i])) + "</tr>")
                i += 1
            aus.append("</table>")
            continue
        m = re.match(r"(\s*)([-*]|\d+\.)\s+(.*)", z)
        if m:
            absatz_ende()
            ein, typ = len(m.group(1)), "ol" if m.group(2)[0].isdigit() else "ul"
            if listen and ein > listen[-1][1]:
                aus.append(f"<{typ}>"); listen.append((typ, ein))
            else:
                listen_ende(ein)
                if listen and listen[-1][1] == ein:
                    aus.append("</li>")
                else:
                    aus.append(f"<{typ}>"); listen.append((typ, ein))
            aus.append(f"<li>{inline(m.group(3))}")
            i += 1
            continue
        if not z.strip():
            absatz_ende()
            if listen and not (i + 1 < len(zeilen) and re.match(r"\s+\S", zeilen[i + 1])):
                listen_ende()
            i += 1
            continue
        if listen and re.match(r"\s+\S", z):  # Fortsetzung eines Listenpunkts
            aus.append(" " + inline(z.strip()))
            i += 1
            continue
        listen_ende()
        absatz.append(z.strip())
        i += 1
    absatz_ende(); listen_ende()
    return "\n".join(aus)


def edge():
    for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        p = Path(os.environ.get(v, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if p.is_file():
            return p
    sys.exit("Microsoft Edge nicht gefunden")


def main():
    quelle = Path(sys.argv[1]) if len(sys.argv) > 1 else BASIS / "ANLEITUNG.md"
    ziel = Path(sys.argv[2]) if len(sys.argv) > 2 else quelle.with_suffix(".pdf")
    md = quelle.read_text(encoding="utf-8")
    titel = re.search(r"^# (.*)", md, re.M)
    titel = titel.group(1) if titel else quelle.stem
    seite = (f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{html.escape(titel.split(" – ")[0])} – '
             f'Anleitung</title><style>{CSS}</style></head><body>{umsetzen(md)}</body></html>')
    if ziel.exists():
        ziel.unlink()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        h = Path(t) / "anleitung.html"
        h.write_text(seite, encoding="utf-8")
        r = subprocess.run([str(edge()), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={Path(t) / 'profil'}", f"--print-to-pdf={ziel.resolve()}",
                            h.resolve().as_uri()], capture_output=True, timeout=120)
    if not ziel.is_file():
        sys.exit(f"PDF nicht erzeugt: {r.stderr.decode(errors='replace')[-500:]}")
    print(f"{ziel} ({ziel.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
