"""Spieltisch-Kartenformat: Karten mit exakten Wänden/Türen importieren (statt sie aus dem Bild zu erkennen).

Format (JSON, alle Koordinaten in Feldern = Gitterpunkte, Bruchteile erlaubt; Feld (0,0) ist oben links):
{
  "format": "spieltisch-karte", "version": 1,
  "id": "keller", "name": "Keller der Mühle",
  "felder": [30, 20],                 # Kartengröße in Feldern (ohne Bild nötig, sonst aus dem Bild)
  "meterProFeld": 1.5,
  "bild": "Material/keller.png",      # optional: vorhandenes Bild (Pfad relativ zum Kampagnenordner)
  "zelle_px": 70, "versatz": [0, 0],  #   Feldgröße im Bild und Pixelposition von Feld (0,0) im Bild
  "hintergrund": "fels",              # ohne Bild: fels | erde | gras | wasser | schwarz
  "raeume": [                         # begehbare Flächen; ihr Umriss wird zur Wand
    {"rechteck": [2, 2, 10, 8], "boden": "stein"},          # x0 y0 x1 y1 (Gitterpunkte)
    {"vieleck": [[10, 4], [16, 4], [16, 6], [10, 6]], "boden": "holz"}
  ],                                  # Überlappende Räume verschmelzen (keine Wand im Inneren);
                                      # nur aneinanderstoßende Räume haben eine Wand dazwischen.
  "waende": [[[5, 2], [5, 5]], …],    # zusätzliche Wände als Linienzüge (Säulen, Zwischenwände)
  "tueren": [{"von": [10, 4.5], "bis": [10, 5.5], "typ": "tuer|geheimtuer|fenster", "offen": false, "id": "t1"}],
  "oeffnungen": [{"von": [10, 5], "bis": [10, 6]}],         # Durchgänge ohne Tür (schneiden Wände auf)
  "beschriftungen": [{"pos": [4, 3], "text": "Altar"}]      # nur ohne Bild; Spieler sehen sie!
}
Böden: stein, holz, erde, gras, wasser, sand, teppich, marmor.
Türen und Öffnungen schneiden die Wand unter sich heraus; geschlossene Türen blockieren Sicht, Geheimtüren
werden ohne Bild wie Wand gezeichnet (für Spieler unsichtbar), Fenster blockieren nie.

Universal VTT (.dd2vtt / .uvtt aus Dungeondraft, DungeonFog, Dungeon Alchemist …) wird mit `aus_uvtt` in dieses
Format umgewandelt (Bild, Raster, line_of_sight, portals).
"""
import base64
import json
import math

import numpy as np
import pymupdf

ZELLE = 50  # px pro Feld im Spieltisch
SCHRITT = 0.05  # Abtastschritt (Felder) für Wandstücke
TYPEN = ("tuer", "geheimtuer", "fenster")
BOEDEN = {"stein": (0.78, 0.76, 0.72), "holz": (0.70, 0.55, 0.38), "erde": (0.55, 0.45, 0.33),
          "gras": (0.45, 0.62, 0.35), "wasser": (0.35, 0.55, 0.75), "sand": (0.86, 0.80, 0.62),
          "teppich": (0.55, 0.20, 0.20), "marmor": (0.92, 0.92, 0.90)}
HINTERGRUND = {"fels": (0.22, 0.20, 0.18), "erde": (0.33, 0.27, 0.20), "gras": (0.28, 0.40, 0.22),
               "wasser": (0.15, 0.28, 0.42), "schwarz": (0.05, 0.05, 0.05)}


class FormatFehler(ValueError):
    pass


def _pt(p, wo):
    if not (isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)):
        raise FormatFehler(f"{wo}: Punkt [x, y] erwartet, bekommen {p!r}")
    return float(p[0]), float(p[1])


def raum_vieleck(r, i):
    if "rechteck" in r:
        q = r["rechteck"]
        if not (isinstance(q, list) and len(q) == 4):
            raise FormatFehler(f"raeume[{i}].rechteck: [x0, y0, x1, y1] erwartet")
        x0, y0, x1, y1 = (float(v) for v in q)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            raise FormatFehler(f"raeume[{i}]: Rechteck ohne Fläche")
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if "vieleck" in r:
        pts = [_pt(p, f"raeume[{i}].vieleck") for p in r["vieleck"]]
        if len(pts) < 3:
            raise FormatFehler(f"raeume[{i}].vieleck: mindestens 3 Punkte")
        return pts
    raise FormatFehler(f"raeume[{i}]: 'rechteck' oder 'vieleck' fehlt")


def _innen(pts, poly):
    """Punkt-in-Vieleck (Strahlverfahren) für viele Punkte (N,2)."""
    x, y = pts[:, 0], pts[:, 1]
    drin = np.zeros(len(pts), bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        kreuzt = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        drin ^= kreuzt
    return drin


def _auf_strecke(pts, a, b, tol=0.06):
    """Liegen die Punkte (N,2) auf der Strecke a–b (Abstand < tol, innerhalb der Enden)?"""
    a, b = np.array(a), np.array(b)
    d = b - a
    L2 = float(d @ d)
    if L2 == 0:
        return np.zeros(len(pts), bool)
    t = ((pts - a) @ d) / L2
    proj = a + np.clip(t, 0, 1)[:, None] * d
    return (np.hypot(*(pts - proj).T) < tol) & (t >= -1e-6) & (t <= 1 + 1e-6)


def waende_berechnen(k):
    """Wandstrecken (Felder) aus Räumen und zusätzlichen Wänden; Türen/Öffnungen ausgeschnitten.
    Gibt [[x0, y0, x1, y1], …] in Feldern zurück."""
    raeume = [raum_vieleck(r, i) for i, r in enumerate(k.get("raeume") or [])]
    kanten = []  # (a, b, raum-index oder None)
    for ri, poly in enumerate(raeume):
        for i in range(len(poly)):
            kanten.append((poly[i], poly[(i + 1) % len(poly)], ri))
    for wi, lz in enumerate(k.get("waende") or []):
        pts = [_pt(p, f"waende[{wi}]") for p in lz]
        if len(pts) < 2:
            raise FormatFehler(f"waende[{wi}]: Linienzug mit mindestens 2 Punkten erwartet")
        for i in range(len(pts) - 1):
            kanten.append((pts[i], pts[i + 1], None))
    schnitte = [(_pt(t["von"], "tueren/oeffnungen"), _pt(t["bis"], "tueren/oeffnungen"))
                for t in list(k.get("tueren") or []) + list(k.get("oeffnungen") or [])]
    seg = []
    for a, b, ri in kanten:
        a_, b_ = np.array(a), np.array(b)
        L = float(np.hypot(*(b_ - a_)))
        if L == 0:
            continue
        n = max(1, math.ceil(L / SCHRITT))
        t = (np.arange(n) + 0.5) / n
        p = a_ + t[:, None] * (b_ - a_)
        nv = np.array([-(b_ - a_)[1], (b_ - a_)[0]]) / L * 0.02
        behalten = np.ones(n, bool)
        if ri is not None:  # Raumkante im Inneren eines anderen Raums -> keine Wand (Räume verschmelzen)
            for rj, poly in enumerate(raeume):
                if rj != ri:
                    behalten &= ~(_innen(p + nv, poly) & _innen(p - nv, poly))
        richtung = (b_ - a_) / L
        for sa, sb in schnitte:  # nur Wände entlang der Tür aufschneiden, nicht quer anstoßende
            d = np.array(sb) - np.array(sa)
            if np.hypot(*d) == 0 or abs(richtung[0] * d[1] - richtung[1] * d[0]) / np.hypot(*d) > 0.2:
                continue
            behalten &= ~_auf_strecke(p, sa, sb)
        # zusammenhängende Läufe -> Strecken
        i = 0
        while i < n:
            if not behalten[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and behalten[j + 1]:
                j += 1
            s, e = a_ + (i / n) * (b_ - a_), a_ + ((j + 1) / n) * (b_ - a_)
            seg.append([round(float(v), 3) for v in (*s, *e)])
            i = j + 1
    return seg


def pruefen(k):
    if k.get("format") not in (None, "spieltisch-karte"):
        raise FormatFehler(f"Unbekanntes Format {k.get('format')!r} (erwartet spieltisch-karte)")
    for i, t in enumerate(k.get("tueren") or []):
        if t.get("typ", "tuer") not in TYPEN:
            raise FormatFehler(f"tueren[{i}].typ: {', '.join(TYPEN)}")
        _pt(t.get("von"), f"tueren[{i}].von")
        _pt(t.get("bis"), f"tueren[{i}].bis")
    for r in k.get("raeume") or []:
        if r.get("boden", "stein") not in BOEDEN:
            raise FormatFehler(f"Boden {r.get('boden')!r} unbekannt ({', '.join(BOEDEN)})")
    if not k.get("bild"):
        if not (isinstance(k.get("felder"), list) and len(k["felder"]) == 2):
            raise FormatFehler("Ohne bild ist felder [BREITE, HÖHE] nötig")
        if not k.get("raeume") and not k.get("waende"):
            raise FormatFehler("Weder raeume noch waende angegeben")


def zeichnen(k, waende, ziel):
    """Kartenbild aus dem Format zeichnen (ohne Bildvorlage). Gibt (w, h) zurück."""
    fx, fy = (int(math.ceil(float(v))) for v in k["felder"])
    if fx <= 0 or fy <= 0 or fx * fy > 250 * 250:
        raise FormatFehler("felder: 1..250 je Richtung")
    w, h = fx * ZELLE, fy * ZELLE
    doc = pymupdf.open()
    pg = doc.new_page(width=w, height=h)
    sh = pg.new_shape()
    sh.draw_rect(pg.rect)
    sh.finish(fill=HINTERGRUND.get(k.get("hintergrund", "fels"), HINTERGRUND["fels"]), width=0)
    sh.commit()
    for i, r in enumerate(k.get("raeume") or []):
        poly = [(x * ZELLE, y * ZELLE) for x, y in raum_vieleck(r, i)]
        sh = pg.new_shape()
        sh.draw_polyline(poly + [poly[0]])
        sh.finish(fill=BOEDEN.get(r.get("boden", "stein")), width=0, closePath=True)
        sh.commit()
    sh = pg.new_shape()  # Raster (dezent)
    for x in range(fx + 1):
        sh.draw_line((x * ZELLE, 0), (x * ZELLE, h))
    for y in range(fy + 1):
        sh.draw_line((0, y * ZELLE), (w, y * ZELLE))
    sh.finish(color=(0, 0, 0), width=1, stroke_opacity=0.18)
    sh.commit()
    sh = pg.new_shape()
    for s in waende:
        sh.draw_line((s[0] * ZELLE, s[1] * ZELLE), (s[2] * ZELLE, s[3] * ZELLE))
    sh.finish(color=(0.08, 0.07, 0.06), width=7, lineCap=1)
    sh.commit()
    for t in k.get("tueren") or []:
        (ax, ay), (bx, by) = _pt(t["von"], "tuer"), _pt(t["bis"], "tuer")
        a, b = np.array([ax, ay]) * ZELLE, np.array([bx, by]) * ZELLE
        typ = t.get("typ", "tuer")
        sh = pg.new_shape()
        if typ == "geheimtuer":  # sieht aus wie Wand
            sh.draw_line(tuple(a), tuple(b))
            sh.finish(color=(0.08, 0.07, 0.06), width=7, lineCap=1)
        elif typ == "fenster":
            sh.draw_line(tuple(a), tuple(b))
            sh.finish(color=(0.55, 0.75, 0.95), width=4)
        else:
            d = b - a
            n = np.array([-d[1], d[0]]) / max(np.hypot(*d), 1e-6) * ZELLE * 0.14
            ecken = [a + n, b + n, b - n, a - n]
            sh.draw_polyline([tuple(e) for e in ecken] + [tuple(ecken[0])])
            sh.finish(fill=(0.50, 0.32, 0.15), color=(0.08, 0.07, 0.06), width=2, closePath=True)
        sh.commit()
    for b in k.get("beschriftungen") or []:
        x, y = _pt(b.get("pos"), "beschriftungen")
        pg.insert_text((x * ZELLE, y * ZELLE), str(b.get("text", ""))[:40], fontsize=16, color=(0.1, 0.1, 0.1))
    pg.get_pixmap(alpha=False).save(ziel)
    return w, h


def barrieren_daten(k, waende, w, h, zelle, ox, oy):
    """Barrieren-Dict (Pixel, Format von barrieren.py) aus Wänden (Felder) und Türen."""
    def px(x, y):
        return [round(ox + x * zelle, 1), round(oy + y * zelle, 1)]
    extra = []
    ids = set()
    for i, t in enumerate(k.get("tueren") or [], 1):
        tid = str(t.get("id") or f"t{i}")
        if tid in ids:
            raise FormatFehler(f"Tür-ID {tid} doppelt")
        ids.add(tid)
        extra.append({"id": tid, "typ": t.get("typ", "tuer"), "p": px(*_pt(t["von"], "tuer")) + px(*_pt(t["bis"], "tuer")),
                      "offen": bool(t.get("offen", False)), "blockiertVon": t.get("blockiertVon"), "quelle": "import"})
    return {"version": 1, "quelle": "import", "bild": {"w": int(w), "h": int(h)},
            "waende": [px(s[0], s[1]) + px(s[2], s[3]) for s in waende], "extra": extra, "loeschen": []}


def aus_uvtt(d):
    """Universal-VTT-Dict -> (Spieltisch-Format-Dict ohne bild, Bildbytes)."""
    try:
        res = d["resolution"]
        ppg = float(res["pixels_per_grid"])
        o = res.get("map_origin") or {"x": 0, "y": 0}
        ox, oy = float(o.get("x", 0)), float(o.get("y", 0))
        bild = base64.b64decode(d["image"])
    except (KeyError, TypeError, ValueError) as e:
        raise FormatFehler(f"Keine gültige UVTT-Datei (resolution/pixels_per_grid/image): {e}") from None

    def p(q):
        return [round(float(q["x"]) - ox, 4), round(float(q["y"]) - oy, 4)]
    waende = [[p(q) for q in lz] for lz in (d.get("line_of_sight") or []) + (d.get("objects_line_of_sight") or [])
              if len(lz) >= 2]
    tueren = []
    for i, po in enumerate(d.get("portals") or [], 1):
        b = po.get("bounds") or []
        if len(b) == 2:
            tueren.append({"id": f"t{i}", "von": p(b[0]), "bis": p(b[1]), "typ": "tuer", "offen": not po.get("closed", True)})
    ms = res.get("map_size") or {}
    k = {"format": "spieltisch-karte", "version": 1, "zelle_px": ppg, "versatz": [0, 0], "waende": waende, "tueren": tueren,
         "felder": [ms.get("x"), ms.get("y")] if ms else None}
    return k, bild


def ist_uvtt(d):
    return isinstance(d, dict) and "resolution" in d and "image" in d


def exportieren(karte, barr):
    """Bestehende Spieltisch-Karte + Barrieren-Dict -> Format-Dict (Wände als Zweipunkt-Linien in Feldern)."""
    import barrieren as B
    zl, ox, oy = karte["zelle"], karte["ox"], karte["oy"]

    def f(x, y):
        return [round((x - ox) / zl, 3), round((y - oy) / zl, 3)]
    k = {"format": "spieltisch-karte", "version": 1, "id": karte["id"], "name": karte["name"],
         "meterProFeld": karte.get("meterProFeld", 1.5), "bild": f"sl/karten/{karte['datei']}", "zelle_px": zl,
         "versatz": [0, 0], "waende": [], "tueren": []}
    k["versatz"] = [ox, oy]  # Bild liegt schon mit 50 px/Feld vor: versatz = Lage von Feld (0,0) in px
    if barr:
        k["waende"] = [[f(s[0], s[1]), f(s[2], s[3])] for s in B.aktive_waende(barr).tolist()]
        for e in barr.get("extra", []):
            t = {"id": e["id"], "typ": e["typ"], "von": f(*e["p"][:2]), "bis": f(*e["p"][2:]), "offen": bool(e.get("offen"))}
            if e["typ"] == "wand":
                k["waende"].append([t["von"], t["bis"]])
            else:
                k["tueren"].append(t)
    return k


def laden_text(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatFehler(f"Kein gültiges JSON: {e}") from None
