"""Barrieren (Wände, Türen, Fenster) aus dem Kartenbild erkennen, speichern und als Sichtpolygon auswerten.

Alles in Bildpixeln der Karte. Dateiformat (sl/barrieren/<karte>.json, nur SL):
  {"version": 1, "bild": {"w":…, "h":…}, "waende": [[x0,y0,x1,y1], …],       # automatisch erkannte Wandstücke
   "extra": [{"id": "t1", "typ": "tuer|wand|fenster|geheimtuer", "p": [x0,y0,x1,y1], "offen": false,
              "blockiertVon": null|"links"|"rechts", "quelle": "auto|manuell"}, …],
   "loeschen": [[x0,y0,x1,y1], …]}   # Pixelbereiche, in denen erkannte Wände ignoriert werden (Korrektur des SL)
Typen: wand blockiert immer; tuer/geheimtuer blockieren nur geschlossen; fenster blockiert nie.
blockiertVon: Barriere wirkt nur, wenn der Betrachter links/rechts der Linie p0→p1 steht (einseitig).
"""
import base64
import json
import math
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

B = 2             # Pixel pro Block bei der Erkennung
TUER_DUNKEL = 135  # Türrahmen sind dünn und oft nur mittelgrau
DUNKEL = 75       # dunkler als dies = Wandlinie (wie karten.WAND_SCHWELLE)
MASKE_B = 2       # Pixel pro Block der Aufdeck-Maske
TYPEN = ("wand", "tuer", "geheimtuer", "fenster")


# ---------------------------------------------------------------- Erkennung

def _dunkel(bild, schwelle=DUNKEL):
    grau = bild[..., 0] * 0.299 + bild[..., 1] * 0.587 + bild[..., 2] * 0.114
    h, w = grau.shape[0] // B, grau.shape[1] // B
    return grau[:h * B, :w * B].reshape(h, B, w, B).min(axis=(1, 3)) < schwelle


def _abstand_links(d):
    """Abstand (Blöcke) zum nächsten dunklen Block links davon (Zeilenrichtung); sehr groß, wenn keiner."""
    idx = np.where(d, np.arange(d.shape[1], dtype=np.int32)[None, :], -10 ** 6)
    return np.arange(d.shape[1], dtype=np.int32)[None, :] - np.maximum.accumulate(idx, axis=1)


def tueren_finden(d, zelle_px, wand=None):
    """Türen = kleine, ringsum von Wandlinie umschlossene helle Rechtecke (Türsymbol in der Wand).
    Gibt Liste von dicts: c (Mittelpunkt px), u (Richtung entlang der Wand), lang, kurz (px)."""
    z = zelle_px / B
    ud, lr = int(z * 0.6), int(z * 1.7)       # max. Summe der Wandabstände quer / längs (= Innenmaß des Türrechtecks)
    links = _abstand_links(d)
    rechts = _abstand_links(d[:, ::-1])[:, ::-1]
    oben = _abstand_links(d.T).T
    unten = _abstand_links(d.T[:, ::-1])[:, ::-1].T
    sh, sv = links + rechts, oben + unten     # waagerechte / senkrechte Innenmaße
    kand = ~d & (sh <= lr) & (sv <= lr) & (np.minimum(sh, sv) <= ud)
    ys, xs = np.nonzero(kand)
    punkte = set(zip(ys.tolist(), xs.tolist()))
    tueren = []
    while punkte:
        s = punkte.pop()
        komp, stapel = [s], [s]
        while stapel:
            y, x = stapel.pop()
            for n in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if n in punkte:
                    punkte.remove(n)
                    komp.append(n)
                    stapel.append(n)
        if len(komp) < 20:
            continue
        a = np.array(komp, float)[:, ::-1] + 0.5      # (x, y) in Blöcken
        c = a.mean(axis=0)
        ev, vec = np.linalg.eigh(np.cov((a - c).T))
        u = vec[:, 1]                                  # Hauptachse
        v = vec[:, 0]
        pu, pv = (a - c) @ u, (a - c) @ v
        lang, kurz = (pu.max() - pu.min() + 1) * B, (pv.max() - pv.min() + 1) * B
        if not (0.45 * zelle_px <= lang <= 1.7 * zelle_px and 0.1 * zelle_px <= kurz <= 0.6 * zelle_px):
            continue
        if lang / kurz < 1.5 or len(komp) * B * B < 0.55 * lang * kurz:
            continue
        if wand is not None:     # beide Türenden müssen an dicker Wand liegen
            ok = True
            for sg in (-1, 1):
                e = c + sg * u * (lang / 2 + 7) / B
                x, y = int(e[0]), int(e[1])
                ok &= bool(wand[max(0, y - 2):y + 3, max(0, x - 2):x + 3].mean() > 0.6)
            if not ok:
                continue
        # Beidseits der Tür muss freier Boden liegen (sonst ist es eine Engstelle zwischen dicken Höhlenwänden)
        if wand is not None:
            frei = True
            for sg in (-1, 1):
                p0 = c + sg * v * (kurz / 2 + 9) / B
                tt = np.linspace(-0.3 * lang, 0.3 * lang, 7) / B
                qx = np.clip((p0[0] + u[0] * tt).astype(int), 0, wand.shape[1] - 1)
                qy = np.clip((p0[1] + u[1] * tt).astype(int), 0, wand.shape[0] - 1)
                frei &= bool(wand[qy, qx].mean() < 0.3)
            if not frei:
                continue
        tueren.append({"c": (c * B).tolist(), "u": u.tolist(), "lang": float(lang), "kurz": float(kurz)})
    # Treppenstufen sehen wie Türen aus, liegen aber dicht gestapelt: Türen mit Nachbartür < 0,6 Feld entfernen
    cs = np.array([t["c"] for t in tueren]).reshape(-1, 2)
    nah = [i for i in range(len(tueren)) if (np.hypot(*(cs - cs[i]).T) < 0.6 * zelle_px).sum() > 1]
    return [t for i, t in enumerate(tueren) if i not in nah]


def _tueren_ausschneiden(d, tueren):
    """Wandpixel im Türdurchgang entfernen, damit dort eine Lücke bleibt (die Tür selbst ist eine eigene Barriere)."""
    h, w = d.shape
    for t in tueren:
        cx, cy = t["c"][0] / B, t["c"][1] / B
        ux, uy = t["u"]
        r = int((t["lang"] / 2 + 12) / B) + 2
        x0, x1, y0, y1 = max(0, int(cx - r)), min(w, int(cx + r) + 1), max(0, int(cy - r)), min(h, int(cy + r) + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        px, py = xx + 0.5 - cx, yy + 0.5 - cy
        pu = (px * ux + py * uy) * B
        pv = (-px * uy + py * ux) * B
        raus = (np.abs(pu) <= t["lang"] / 2 + 4) & (np.abs(pv) <= t["kurz"] / 2 + 6)
        d[y0:y1, x0:x1] &= ~raus


def _konturen(d):
    """Alle Umrisse des Bool-Rasters als geschlossene Punktfolgen (Blockkoordinaten, Ecken)."""
    h, w = d.shape
    p = np.pad(d, 1)
    m = p[1:-1, 1:-1]
    W1 = w + 1
    kanten = []
    for maske, (dx0, dy0, dx1, dy1) in (
        (m & ~p[:-2, 1:-1], (0, 0, 1, 0)),     # oben
        (m & ~p[1:-1, 2:], (1, 0, 1, 1)),      # rechts
        (m & ~p[2:, 1:-1], (1, 1, 0, 1)),      # unten
        (m & ~p[1:-1, :-2], (0, 1, 0, 0)),     # links
    ):
        ys, xs = np.nonzero(maske)
        a = (ys + dy0) * W1 + xs + dx0
        b = (ys + dy1) * W1 + xs + dx1
        kanten.append(np.stack([a, b], 1))
    kanten = np.concatenate(kanten)
    nach = defaultdict(list)
    for a, b in kanten.tolist():
        nach[a].append(b)
    loops = []
    for start in list(nach.keys()):
        while nach[start]:
            folge = [start]
            v = nach[start].pop()
            while True:
                folge.append(v)
                if v == start:
                    break
                v = nach[v].pop()
            arr = np.array(folge[:-1])
            loops.append(np.stack([arr % W1, arr // W1], 1).astype(float))
    return loops


def _dp(pts, eps):
    """Douglas-Peucker für eine offene Punktfolge; gibt Indizes der behaltenen Punkte zurück."""
    n = len(pts)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stapel = [(0, n - 1)]
    while stapel:
        i, j = stapel.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        e = b - a
        L = math.hypot(*e)
        q = pts[i + 1:j] - a
        dist = np.hypot(q[:, 0], q[:, 1]) if L == 0 else np.abs(q[:, 0] * e[1] - q[:, 1] * e[0]) / L
        k = int(np.argmax(dist))
        if dist[k] > eps:
            keep[i + 1 + k] = True
            stapel += [(i, i + 1 + k), (i + 1 + k, j)]
    return np.nonzero(keep)[0]


def _vereinfachen(loop, eps):
    """Geschlossene Punktfolge vereinfachen und als Streckenliste [[x0,y0,x1,y1]] zurückgeben."""
    # Punkte auf geraden Strecken vorab entfernen
    n = len(loop)
    if n < 4:
        return []
    nxt, prv = np.roll(loop, -1, 0), np.roll(loop, 1, 0)
    ecke = np.any((loop - prv) != (nxt - loop), axis=1)
    loop = loop[ecke]
    n = len(loop)
    if n < 3:
        return []
    j = int(np.argmax(np.hypot(*(loop - loop[0]).T)))
    h1 = loop[:j + 1]
    h2 = np.concatenate([loop[j:], loop[:1]])
    pts = []
    for h in (h1, h2):
        pts.extend(h[_dp(h, eps)][:-1].tolist())
    pts = np.array(pts)
    pts2 = np.roll(pts, -1, 0)
    return np.concatenate([pts, pts2], 1) * B


def erkennen(bild, zelle_px=50, klein_felder=2.4, eps=1.6, fortschritt=None):
    """Wände und Türen aus einem Kartenbild (RGB-Array) erkennen. Gibt das Barrieren-Dict (ohne `loeschen`) zurück."""
    def meld(s):
        if fortschritt:
            fortschritt(s)
    d = _dunkel(bild)
    meld("Türen suchen")
    tueren = tueren_finden(_dunkel(bild, TUER_DUNKEL), zelle_px, d)
    _tueren_ausschneiden(d, tueren)
    meld("Umrisse verfolgen")
    loops = _konturen(d)
    meld("Vereinfachen")
    waende = []
    klein = klein_felder * zelle_px / B
    for lp in loops:
        ext = lp.max(axis=0) - lp.min(axis=0)
        if ext.max() < klein:                 # Beschriftung, Ziffern, Verzierung, Säulchen
            continue
        s = _vereinfachen(lp, eps)
        if len(s):
            waende.extend(np.round(s, 1).tolist())
    extra = []
    for i, t in enumerate(tueren, 1):
        c = np.array(t["c"])
        u = np.array(t["u"])
        h = t["lang"] / 2 + 5.5
        a, b = c - u * h, c + u * h
        extra.append({"id": f"t{i}", "typ": "tuer", "p": np.round([*a, *b], 1).tolist(), "offen": False,
                      "blockiertVon": None, "quelle": "auto"})
    return {"version": 1, "bild": {"w": int(bild.shape[1]), "h": int(bild.shape[0])},
            "waende": waende, "extra": extra, "loeschen": []}


# ---------------------------------------------------------------- Speicher / Zugriff

def pfad(sl_ordner, kid):
    return Path(sl_ordner) / "barrieren" / f"{kid}.json"


def laden(sl_ordner, kid):
    p = pfad(sl_ordner, kid)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def speichern(sl_ordner, kid, daten):
    p = pfad(sl_ordner, kid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def _schneidet(seg, r):
    """Welche Strecken (N,4) berühren das Rechteck r = (x0,y0,x1,y1)? (Näherung: Bounding-Box)"""
    x0, y0, x1, y1 = r
    return ((np.maximum(seg[:, 0], seg[:, 2]) >= x0) & (np.minimum(seg[:, 0], seg[:, 2]) <= x1)
            & (np.maximum(seg[:, 1], seg[:, 3]) >= y0) & (np.minimum(seg[:, 1], seg[:, 3]) <= y1))


def aktive_waende(daten):
    """Erkannte Wandstücke ohne die vom SL gelöschten Bereiche, als (N,4)-Array."""
    seg = np.array(daten.get("waende", []), float).reshape(-1, 4)
    for r in daten.get("loeschen", []):
        seg = seg[~_mittelpunkt_in(seg, r)]
    return seg


def _mittelpunkt_in(seg, r):
    mx, my = (seg[:, 0] + seg[:, 2]) / 2, (seg[:, 1] + seg[:, 3]) / 2
    return (mx >= r[0]) & (mx <= r[2]) & (my >= r[1]) & (my <= r[3])


def blockierend(daten):
    """Aktuell sichtblockierende Strecken: (seg (N,4), seite (N,)); seite 0 = beidseitig, -1/+1 = nur von links/rechts."""
    w = aktive_waende(daten)
    segs = [w]
    seiten = [np.zeros(len(w), np.int8)]
    for e in daten.get("extra", []):
        if e["typ"] == "fenster" or (e["typ"] in ("tuer", "geheimtuer") and e.get("offen")):
            continue
        segs.append(np.array([e["p"]], float))
        seiten.append(np.array([{"links": -1, "rechts": 1}.get(e.get("blockiertVon"), 0)], np.int8))
    return np.concatenate(segs), np.concatenate(seiten)


# ---------------------------------------------------------------- Sichtpolygon

def sichtpolygon(seg, seite, o, radius, gleichmaessig=720):
    """Sichtbereich vom Punkt o = (x, y) aus: Strahlen bis zur ersten blockierenden Strecke, höchstens `radius` px.
    Gibt (Winkel, Abstände) sortiert zurück."""
    ox, oy = o
    if len(seg):
        k = _schneidet(seg, (ox - radius, oy - radius, ox + radius, oy + radius))
        seg, seite = seg[k], seite[k]
    if len(seg):
        e = seg[:, 2:] - seg[:, :2]
        kreuz = e[:, 0] * (oy - seg[:, 1]) - e[:, 1] * (ox - seg[:, 0])   # >0: Betrachter rechts (Bildkoordinaten)
        seg = seg[(seite == 0) | (np.sign(kreuz) == seite)]
    winkel = [np.linspace(-math.pi, math.pi, gleichmaessig, endpoint=False)]
    if len(seg):
        ends = np.concatenate([seg[:, :2], seg[:, 2:]])
        a = np.arctan2(ends[:, 1] - oy, ends[:, 0] - ox)
        winkel += [a - 1e-4, a, a + 1e-4]
    winkel = np.sort(np.concatenate(winkel))
    winkel = np.where(winkel > math.pi, winkel - 2 * math.pi, winkel)
    winkel = np.sort(winkel)
    dist = np.full(len(winkel), float(radius))
    if len(seg):
        ax, ay = seg[:, 0] - ox, seg[:, 1] - oy
        ex, ey = seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]
        for i in range(0, len(winkel), 400):
            dx, dy = np.cos(winkel[i:i + 400])[:, None], np.sin(winkel[i:i + 400])[:, None]
            nenner = dx * ey[None] - dy * ex[None]
            with np.errstate(divide="ignore", invalid="ignore"):
                t = (ax[None] * ey[None] - ay[None] * ex[None]) / nenner
                s = (ax[None] * dy - ay[None] * dx) / nenner
            ok = (np.abs(nenner) > 1e-12) & (t > 1e-6) & (s >= -1e-7) & (s <= 1 + 1e-7)
            t = np.where(ok, t, np.inf)
            dist[i:i + 400] = np.minimum(dist[i:i + 400], t.min(axis=1))
    return winkel, dist


def sicht_zeichnen(maske, o, winkel, dist):
    """Sichtpolygon in die Aufdeck-Maske (Bool-Array, MASKE_B px pro Block) eintragen. Gibt die neu aufgedeckten Blöcke (Bool-Fenster + Offset) zurück: (y0, x0, neu)."""
    M = MASKE_B
    r = float(dist.max()) + 2
    h, w = maske.shape
    x0, x1 = max(0, int((o[0] - r) // M)), min(w, int((o[0] + r) // M) + 2)
    y0, y1 = max(0, int((o[1] - r) // M)), min(h, int((o[1] + r) // M) + 2)
    if x1 <= x0 or y1 <= y0:
        return y0, x0, np.zeros((0, 0), bool)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dx, dy = (xx + 0.5) * M - o[0], (yy + 0.5) * M - o[1]
    th = np.arctan2(dy, dx)
    rr = np.hypot(dx, dy)
    wk = np.concatenate([winkel[-1:] - 2 * math.pi, winkel, winkel[:1] + 2 * math.pi])
    dk = np.concatenate([dist[-1:], dist, dist[:1]])
    drin = rr <= np.interp(th, wk, dk) + 0.5
    fenster = maske[y0:y1, x0:x1]
    neu = drin & ~fenster
    fenster |= drin
    return y0, x0, neu


def maske_neu(w, h):
    return np.zeros((h // MASKE_B + 1, w // MASKE_B + 1), bool)


def maske_kodieren(maske):
    return {"b": MASKE_B, "w": int(maske.shape[1]), "h": int(maske.shape[0]),
            "d": base64.b64encode(zlib.compress(np.packbits(maske).tobytes(), 6)).decode("ascii")}


def maske_dekodieren(m):
    n = m["w"] * m["h"]
    bits = np.unpackbits(np.frombuffer(zlib.decompress(base64.b64decode(m["d"])), np.uint8))[:n]
    return bits.reshape(m["h"], m["w"]).astype(bool)


def maske_rechteck(maske, px, wert):
    """Pixelrechteck (x0,y0,x1,y1) in der Maske setzen/löschen."""
    M = MASKE_B
    h, w = maske.shape
    x0, y0 = max(0, int(px[0] // M)), max(0, int(px[1] // M))
    x1, y1 = min(w, int(math.ceil(px[2] / M))), min(h, int(math.ceil(px[3] / M)))
    if x1 > x0 and y1 > y0:
        maske[y0:y1, x0:x1] = wert


def maske_in_pixel(maske, w, h):
    """Maske auf Bildgröße (h, w) hochskalieren."""
    M = MASKE_B
    return maske.repeat(M, 0).repeat(M, 1)[:h, :w]


# ---------------------------------------------------------------- Vorschau für den SL (nie für Spieler)

def vorschau(bild, daten, ziel, bereich=None, faktor=1):
    """Kartenbild mit eingezeichneten Barrieren als PNG (nur zur SL-Kontrolle)."""
    import pymupdf
    a = np.ascontiguousarray(bild).copy()
    h, w = a.shape[:2]
    farben = {"wand": (255, 0, 0), "tuer": (0, 160, 255), "geheimtuer": (255, 0, 255), "fenster": (0, 200, 0)}

    def linie(p, farbe, dick=1):
        n = int(max(abs(p[2] - p[0]), abs(p[3] - p[1]))) + 2
        xs = np.linspace(p[0], p[2], n).round().astype(int)
        ys = np.linspace(p[1], p[3], n).round().astype(int)
        for dy in range(-dick + 1, dick):
            for dx in range(-dick + 1, dick):
                ok = (xs + dx >= 0) & (xs + dx < w) & (ys + dy >= 0) & (ys + dy < h)
                a[ys[ok] + dy, xs[ok] + dx] = farbe
    for p in aktive_waende(daten):
        linie(p, farben["wand"])
    for e in daten.get("extra", []):
        linie(e["p"], farben[e["typ"]] if not e.get("offen") else (150, 255, 150), 2)
    if bereich:
        x0, y0, x1, y1 = [int(v) for v in bereich]
        a = np.ascontiguousarray(a[y0:y1, x0:x1])
        h, w = a.shape[:2]
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, a.tobytes(), 0)
    if faktor != 1:
        pix.shrink(int(faktor))
    pix.save(str(ziel))
