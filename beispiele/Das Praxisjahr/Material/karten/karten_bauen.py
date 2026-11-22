"""Baut die Kartenbilder und Kartenformat-Dateien der Beispielkampagne „Das Praxisjahr“.

python karten_bauen.py QUELLORDNER BEISPIELORDNER
QUELLORDNER = Projektordner des Autors (Kampagne/*.svg sowie Karte2.png, Tiefenburg.png, Illiatist.png);
die SVGs liegen auch unter Material/ dieses Beispiels. Ergebnis: Material/karten/*.png und *.karte.json
(Zisternen, Wachhaus: Spielerfassung ohne Raumnummern) sowie sl/karten/*.png|jpg (Stadtpläne, Übersicht).
"""
import json
import math
import re
import sys
from pathlib import Path

import pymupdf

Q = Path(sys.argv[1])
B = Path(sys.argv[2])
MK = B / "Material" / "karten"
SK = B / "sl" / "karten"
MK.mkdir(parents=True, exist_ok=True)
SK.mkdir(parents=True, exist_ok=True)
ZOOM = 2.5  # 20 px/Feld im SVG -> 50 px/Feld


def text_fix(svg):
    """paint-order=stroke (Schrift mit Rand) rendert PyMuPDF nicht: als zwei Texte (Rand, dann Füllung) schreiben."""
    def ersetze(m):
        attrs, inhalt = m.group(1), m.group(2)
        if 'paint-order="stroke"' not in attrs:
            return m.group(0)
        attrs = attrs.replace(' paint-order="stroke"', "")
        strich = re.search(r'stroke="([^"]+)"', attrs).group(1)
        rand = re.sub(r'fill="[^"]+"', f'fill="{strich}"', attrs)
        fuell = re.sub(r' stroke="[^"]+"', "", re.sub(r' stroke-width="[^"]+"', "", attrs))
        return f"<text{rand}>{inhalt}</text><text{fuell}>{inhalt}</text>"
    return re.sub(r"<text([^>]*)>(.*?)</text>", ersetze, svg, flags=re.S)


def raster_linien(svg):
    """Musterfüllung (pattern) rendert PyMuPDF schwarz: das Raster-Rechteck durch einzelne Linien ersetzen."""
    def ersetze(m):
        x, y, w, h = (float(m.group(i)) for i in range(1, 5))
        op = re.search(r'id="grid".*?stroke-opacity="([\d.]+)"', svg, re.S).group(1)
        linien = [f'<line x1="{x + i}" y1="{y}" x2="{x + i}" y2="{y + h}"/>' for i in range(0, int(w) + 1, 20)]
        linien += [f'<line x1="{x}" y1="{y + j}" x2="{x + w}" y2="{y + j}"/>' for j in range(0, int(h) + 1, 20)]
        clip = f' clip-path="{m.group(5)}"' if m.group(5) else ""
        return (f'<g stroke="#000" stroke-opacity="{op}" stroke-width="1"{clip}>' + "".join(linien) + "</g>")
    return re.sub(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="url\(#grid\)"'
                  r'(?: clip-path="([^"]+)")?/>', ersetze, svg)


def ohne_gruppe(svg, kommentar):
    """Entfernt den <g>…</g>-Block direkt nach einem Kommentar (Nummern, Legende)."""
    return re.sub(r"<!--\s*" + kommentar + r"\s*-->\s*<g[^>]*>.*?</g>", "", svg, count=1, flags=re.S)


def rendern(svg_text, ziel, clip=None, zoom=ZOOM):
    svg_text = raster_linien(svg_text)
    doc = pymupdf.open(stream=svg_text.encode("utf-8"), filetype="svg")
    pg = doc[0]
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    pix.save(str(ziel))
    return pix.w, pix.h


def vieleck_kreis(cx, cy, r, n=16, start=0.0):
    return [[round(cx + r * math.cos(math.radians(start + i * 360 / n)), 3),
             round(cy + r * math.sin(math.radians(start + i * 360 / n)), 3)] for i in range(n)]


def quadrat(cx, cy, h=0.45):
    return [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h], [cx - h, cy - h]]


# ---------------------------------------------------------------- Zisternen (Abenteuer 1)
svg = (Q / "Kampagne" / "Karte_Zisternen_Torstadt.svg").read_text(encoding="utf-8")
svg = ohne_gruppe(svg, "Nummern")
svg = ohne_gruppe(svg, "Legende")
svg = re.sub(r'<text[^>]*>T</text>', "", svg)            # Tamla
svg = re.sub(r'<text[^>]*>K</text>', "", svg)            # Kreidemarkierungen
svg = re.sub(r'<circle cx="522" cy="552"[^>]*/>', "", svg)  # schwarzer Runenstein
w, h = rendern(svg, MK / "zisternen.png", clip=pymupdf.Rect(40, 40, 680, 640))
# Pfeiler im Bereich 7: Kreis (32, 25.5) r 5.5, sichtbar bis x = 28
bogen = [[round(32 - 5.5 * math.cos(math.radians(t)), 3), round(25.5 + 5.5 * math.sin(math.radians(t)), 3)]
         for t in range(-44, 45, 4)]
zisternen = {
    "format": "spieltisch-karte", "version": 1, "id": "zisternen", "name": "Die Zisternen unter dem Steinwall",
    "meterProFeld": 1.5, "bild": "Material/karten/zisternen.png", "zelle_px": 50, "versatz": [0, 0],
    "raeume": [
        {"rechteck": [11, 1, 14, 4]},   # 1 Einstieg (Wendeltreppe)
        {"rechteck": [12, 4, 13, 6]},   # Treppenfuß
        {"rechteck": [8, 6, 17, 12]},   # 2 Pumpenkammer
        {"rechteck": [3, 8, 8, 9]},     # Gang West
        {"rechteck": [17, 8, 22, 9]},   # Gang Ost
        {"rechteck": [0, 9, 7, 17]},    # 3 Überlaufbecken (Sims + Becken)
        {"rechteck": [3, 17, 4, 20]},   # gefluteter Durchgang
        {"rechteck": [22, 6, 27, 11]},  # 4 Geräteraum
        {"rechteck": [12, 12, 13, 20]}, # 5 enger Schacht
        {"rechteck": [2, 20, 20, 30]},  # 6 Hauptzisterne
        {"rechteck": [20, 21, 28, 30]}, # 7 Pfeilerfundament
    ],
    "waende": [bogen] + [quadrat(x, y) for x in (5.5, 9.5, 18.5) for y in (23.5, 27.5)],
    "tueren": [{"von": [22, 8], "bis": [22, 9], "typ": "tuer", "offen": False, "id": "t-geraete"}],
    "oeffnungen": [
        {"von": [12, 4], "bis": [13, 4]}, {"von": [12, 6], "bis": [13, 6]},
        {"von": [8, 8], "bis": [8, 9]}, {"von": [17, 8], "bis": [17, 9]},
        {"von": [3, 9], "bis": [7, 9]},
        {"von": [3, 17], "bis": [4, 17]}, {"von": [3, 20], "bis": [4, 20]},
        {"von": [12, 12], "bis": [13, 12]}, {"von": [12, 20], "bis": [13, 20]},
        {"von": [20, 21], "bis": [20, 30]},
    ],
}
(MK / "zisternen.karte.json").write_text(json.dumps(zisternen, ensure_ascii=False, indent=1), encoding="utf-8")
print("zisternen", w, h)

# ---------------------------------------------------------------- Wachhaus Illiatist (Abenteuer 3)
svg = (Q / "Kampagne" / "Karte_Wachhaus_Hochsee.svg").read_text(encoding="utf-8")
svg = ohne_gruppe(svg, "Nummern")
svg = re.sub(r"<!--\s*Legende\s*-->.*?</g>\s*(?=</svg>)", "", svg, flags=re.S)
svg = re.sub(r'<text[^>]*>Velrith</text>', "", svg)
svg = re.sub(r"<!-- Fuge mit Gegenanker -->\s*<circle[^>]*/>", "", svg)
svg = re.sub(r"<!-- Dachluke -->\s*<rect[^>]*/>", "", svg)
w, h = rendern(svg, MK / "wachhaus.png", clip=pymupdf.Rect(40, 40, 680, 580))
# Turm: Mittelpunkt (22, 10.5), r 2.3; 16-Eck mit einer Kante genau im Westen (Tür zum Kai)
turm = vieleck_kreis(22, 10.5, 2.3, 16, start=180 + 11.25)  # Punkt 0 = 191.25°, Punkt 15 = 168.75°
tuer_turm = {"von": turm[15], "bis": turm[0], "typ": "tuer", "offen": False, "id": "t-turm"}
pfeiler = vieleck_kreis(26.5, 5, 3.9, 20)
zellen = [(9, 11.5), (11.5, 14), (14, 16.5), (16.5, 19)]
tueren = [
    {"von": [9, 13], "bis": [9, 14], "typ": "tuer", "id": "t-wachstube-gang"},
    {"von": [9, 20.5], "bis": [9, 21.5], "typ": "tuer", "id": "t-waffenkammer-hof"},
    {"von": [5, 18], "bis": [6, 18], "typ": "tuer", "id": "t-wachstube-waffenkammer"},
    {"von": [12, 24], "bis": [14, 24], "typ": "tuer", "id": "t-tor"},
    {"von": [13, 19], "bis": [14, 19], "typ": "tuer", "id": "t-hof-z2"},
    tuer_turm,
]
for i, (a, b) in enumerate(zellen, 1):
    tueren.append({"von": [a, 15], "bis": [b - 1, 15], "typ": "fenster", "id": f"gitter-z{i}"})
    tueren.append({"von": [b - 1, 15], "bis": [b, 15], "typ": "tuer", "id": f"zelle-z{i}"})
wachhaus = {
    "format": "spieltisch-karte", "version": 1, "id": "wachhaus", "name": "Illiatist – Wachhaus am Hochsee",
    "meterProFeld": 1.5, "bild": "Material/karten/wachhaus.png", "zelle_px": 50, "versatz": [0, 0],
    "raeume": [
        {"rechteck": [0, 0, 32, 11]},   # Hochsee, Steg und Kaimauer
        {"rechteck": [2, 12, 19, 24]},  # Wachhaus
        {"rechteck": [12, 24, 14, 25]}, # Torweg
        {"rechteck": [0, 25, 32, 27]},  # Hafengasse
    ],
    "waende": [
        turm,  # Turmwand ohne die Türkante (Linienzug von Punkt 0 bis 15; Kante 15–0 ist die Tür)
        pfeiler + [pfeiler[0]],
        [[9, 12], [9, 24]], [[2, 18], [9, 18]], [[9, 15], [19, 15]], [[9, 19], [19, 19]],
        [[11.5, 15], [11.5, 19]], [[14, 15], [14, 19]], [[16.5, 15], [16.5, 19]],
    ],
    "tueren": tueren,
    "oeffnungen": [{"von": [19.8, 11], "bis": [24.2, 11]}, {"von": [12, 25], "bis": [14, 25]}],
}
(MK / "wachhaus.karte.json").write_text(json.dumps(wachhaus, ensure_ascii=False, indent=1), encoding="utf-8")
print("wachhaus", w, h)


def felder(punkte, x0=40, y0=40):
    """SVG-Punkte (20 px/Feld, Raster ab x0/y0) in Feldkoordinaten."""
    return [[round((x - x0) / 20, 3), round((y - y0) / 20, 3)] for x, y in punkte]


def pfad_punkte(d):
    return [(float(a), float(b)) for a, b in re.findall(r"([\d.]+)\s+([\d.]+)", d)]


def schreiben(k):
    (MK / f"{k['id']}.karte.json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- Runenwerkstatt (Abenteuer 4)
svg = (Q / "Kampagne" / "Karte_Runenwerkstatt.svg").read_text(encoding="utf-8")
boden = pfad_punkte(re.search(r'<clipPath id="floor">\s*<path d="([^"]+)"', svg).group(1))
svg = ohne_gruppe(svg, "Nummern")
svg = ohne_gruppe(svg, "Legende")
svg = re.sub(r'<circle cx="(556|574|592)" cy="345"[^>]*/>', "", svg)      # halbfertige Lauschsteine
svg = re.sub(r"<!-- Kreidezeichen am Zugang -->\s*<text[^>]*>[^<]*</text>", "", svg)
svg = re.sub(r"<!-- Richtungen -->\s*<text[^>]*>[^<]*</text>\s*<text[^>]*>[^<]*</text>", "", svg)
w, h = rendern(svg, MK / "runenwerkstatt.png", clip=pymupdf.Rect(40, 40, 700, 620))
schreiben({"format": "spieltisch-karte", "version": 1, "id": "runenwerkstatt", "name": "Finsterhöhlen – Versteck",
           "meterProFeld": 1.5, "bild": "Material/karten/runenwerkstatt.png", "zelle_px": 50, "versatz": [0, 0],
           "raeume": [{"vieleck": felder(boden)}]})
print("runenwerkstatt", w, h)

# ---------------------------------------------------------------- Gefangenenlager (Abenteuer 5)
svg = (Q / "Kampagne" / "Karte_Gefangenenlager.svg").read_text(encoding="utf-8")
boden = pfad_punkte(re.search(r'<clipPath id="floor">\s*<path d="([^"]+)"', svg).group(1))
svg = re.sub(r'<g font-size="14" font-weight="bold" text-anchor="middle" fill="#fff">.*?</g>', "", svg, flags=re.S)
svg = re.sub(r'<g transform="translate\(40,722\)".*?</g>', "", svg, flags=re.S)        # Legende
svg = re.sub(r'<g font-size="10" fill="#2a2622" text-anchor="middle">.*?</g>', "", svg, flags=re.S)  # Pferch-Namen
svg = re.sub(r'<text[^>]*>(Aura|Spalt der|Winzlinge)</text>', "", svg)
# radialGradient rendert PyMuPDF schwarz: grünes Licht vom Grauen Hof als halbtransparente Ellipsen
svg = re.sub(r'<rect[^>]*fill="url\(#glow\)"[^>]*/>',
             '<g clip-path="url(#floor)" fill="#7bd88a"><ellipse cx="370" cy="660" rx="90" ry="110" fill-opacity="0.25"/>'
             '<ellipse cx="370" cy="660" rx="50" ry="60" fill-opacity="0.3"/></g>', svg)
svg = re.sub(r'<text x="(372|400)" y="(60|660)"[^>]*>[^<]*</text>', "", svg)            # Richtungen
w, h = rendern(svg, MK / "gefangenenlager.png", clip=pymupdf.Rect(40, 40, 700, 660))
# Spalt der Winzlinge: geheimer Zugang (nur die Milben kennen ihn) – Geheimtür auf der Kante (650,230)–(660,360)
kante = lambda y: [round(30.5 + 0.5 * (y - 9.5) / 6.5, 3), y]  # noqa: E731
spalt_a, spalt_b = kante(13.0), kante(14.8)
pferche, tueren = [], []
for i, y0 in enumerate((9.0, 13.5, 18.0), 1):  # Pferche 3,5–8 × y0–y0+3,5: Gitter (Fenster) mit Gattertür im Osten
    tueren += [{"von": [3.5, y0], "bis": [8, y0], "typ": "fenster", "id": f"pferch{i}-n"},
               {"von": [3.5, y0 + 3.5], "bis": [8, y0 + 3.5], "typ": "fenster", "id": f"pferch{i}-s"},
               {"von": [3.5, y0], "bis": [3.5, y0 + 3.5], "typ": "fenster", "id": f"pferch{i}-w"},
               {"von": [8, y0], "bis": [8, y0 + 1.25], "typ": "fenster", "id": f"pferch{i}-o1"},
               {"von": [8, y0 + 1.25], "bis": [8, y0 + 2.25], "typ": "tuer", "offen": False, "id": f"pferch{i}"},
               {"von": [8, y0 + 2.25], "bis": [8, y0 + 3.5], "typ": "fenster", "id": f"pferch{i}-o2"}]
zelt = [[23.825, 11.725], [24, 10.5], [28, 10.5], [28.5, 14], [23.5, 14], [23.675, 12.775]]
tueren += [{"von": zelt[-1], "bis": zelt[0], "typ": "tuer", "offen": False, "id": "zelt"},
           {"von": spalt_a, "bis": spalt_b, "typ": "geheimtuer", "offen": False, "id": "spalt"}]
schreiben({"format": "spieltisch-karte", "version": 1, "id": "gefangenenlager", "name": "Das Lager am Grauen Hof",
           "meterProFeld": 1.5, "bild": "Material/karten/gefangenenlager.png", "zelle_px": 50, "versatz": [0, 0],
           "raeume": [{"vieleck": felder(boden)},
                      {"vieleck": [spalt_a, [32.5, 12.5], [33, 14.5], spalt_b]}],
           "waende": [zelt,
                      [[16, 12.8], [16.6, 14.5], [16, 16.2], [15.4, 14.5], [16, 12.8]],      # Obelisk
                      [[12.5, 4.4], [13.5, 4.4]], [[16, 4.4], [17, 4.4]]],                   # Torpfosten
           "tueren": tueren})
print("gefangenenlager", w, h)

# ---------------------------------------------------------------- Torhaus Torstadt (Abenteuer 6)
svg = (Q / "Kampagne" / "Karte_Torhaus_Torstadt.svg").read_text(encoding="utf-8")
svg = ohne_gruppe(svg, "Nummern")
svg = ohne_gruppe(svg, "Legende")
w, h = rendern(svg, MK / "torhaus.png", clip=pymupdf.Rect(40, 40, 680, 660))
# Wall x 12,5–15 (Wehrgang oben, nur über die Treppe im Torhaus), Torhaus 11,5–18,5 × 12–19,5,
# Torweg y 14,75–16,75 mit Fallgitter (x 13) und Tor (x 16), Windenraum 13,5–18 × 12,5–14,75, Treppe 17–18,5 × 16,75–18,5
schreiben({"format": "spieltisch-karte", "version": 1, "id": "torhaus", "name": "Torstadt – Torhaus und Wall",
           "meterProFeld": 1.5, "bild": "Material/karten/torhaus.png", "zelle_px": 50, "versatz": [0, 0],
           "raeume": [{"rechteck": [0, 0, 32, 31]}],
           "waende": [
               [[12.5, 0], [12.5, 12]], [[12.5, 19.5], [12.5, 28.5]], [[12.5, 30], [12.5, 31]],
               [[15, 0], [15, 12]], [[15, 19.5], [15, 28.5]], [[15, 30], [15, 31]],
               [[11.5, 14.75], [11.5, 12], [18.5, 12], [18.5, 14.75]],              # Torhaus Nordteil
               [[11.5, 16.75], [11.5, 19.5], [18.5, 19.5], [18.5, 16.75]],          # Torhaus Südteil
               [[11.5, 14.75], [18.5, 14.75]], [[11.5, 16.75], [18.5, 16.75]],      # Torweg
               [[13.5, 14.75], [13.5, 12.5], [18, 12.5], [18, 14.75]],              # Windenraum
               [[17, 16.75], [17, 18.5], [18.5, 18.5]],                             # Treppe
               [[21.5, 2], [30, 2], [30, 8], [21.5, 8], [21.5, 2]],                 # Kaserne
               [[15.5, 20.5], [16, 20.5], [16, 25], [15.5, 25], [15.5, 20.5]],      # Mauer der Namen
           ],
           "tueren": [
               {"von": [13, 14.75], "bis": [13, 16.75], "typ": "fenster", "id": "fallgitter"},
               {"von": [16, 14.75], "bis": [16, 16.75], "typ": "tuer", "offen": False, "id": "tor"},
               {"von": [16.5, 14.75], "bis": [17.5, 14.75], "typ": "tuer", "offen": True, "id": "windenraum"},
               {"von": [25, 8], "bis": [26.5, 8], "typ": "tuer", "offen": False, "id": "kaserne"},
               {"von": [12.5, 28.5], "bis": [12.5, 30], "typ": "fenster", "id": "wassertor-aussen"},
               {"von": [15, 28.5], "bis": [15, 30], "typ": "fenster", "id": "wassertor-innen"},
           ],
           "oeffnungen": [{"von": [17, 16.75], "bis": [18, 16.75]}]})
print("torhaus", w, h)

# ---------------------------------------------------------------- Stadtpläne (ohne Nebel) und große Bilder
for name in ("Torstadt", "Grovaristadt"):
    svg = text_fix((Q / "Kampagne" / f"{name}.svg").read_text(encoding="utf-8"))
    w, h = rendern(svg, SK / f"{name.lower()}.png", zoom=2.0)
    print(name, w, h)
for datei, ziel, kante in (("Karte2.png", "hoehlen.jpg", 2880), ("Tiefenburg.png", "tiefenburg.jpg", 2400),
                           ("Illiatist.png", "illiatist.jpg", 2400)):
    pix = pymupdf.Pixmap(str(Q / datei))
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    s = kante / max(pix.w, pix.h)
    if s < 1:
        pix = pymupdf.Pixmap(pix, int(round(pix.w * s)), int(round(pix.h * s)), None)
    pix.save(str(SK / ziel), jpg_quality=88)
    print(ziel, pix.w, pix.h, (SK / ziel).stat().st_size // 1000, "kB")
