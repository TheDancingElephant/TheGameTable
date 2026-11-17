"""Karten aus PDFs ausschneiden, Raster erkennen, Nebel-Masken rendern."""
import math
import numpy as np
import pymupdf

ZIEL_ZELLE = 50  # Pixel pro Feld im extrahierten Bild
NEBEL_FARBE = (27, 23, 18)


RASTER_MIN_PT, RASTER_MAX_PT = 14, 45  # Feldgröße auf den A3-Plänen variiert je Karte (19–34 pt)


def _linienprofil(a, achse):
    """Profil quer zu den Rasterlinien. Jede Pixelreihe wird einzeln hochpassgefiltert
    (dunkler als die Umgebung), dann der Median über alle Reihen: Rasterlinien laufen
    durch fast jede Reihe, Wände und Möbel nur durch wenige."""
    if achse == 0:  # x-Profil: Spalten werden zu Zeilen
        a = a.T
    k = 9
    c = np.cumsum(np.pad(a, ((k // 2 + 1, k // 2), (0, 0)), mode="edge"), axis=0)
    glatt = (c[k:] - c[:-k]) / k
    dunkler = np.clip(glatt - a, 0, None)
    return np.percentile(dunkler, 60, axis=1)


def _kamm(profil, periode, schritt=0.5):
    """Beste Phase und Stärke eines Kamms mit gegebener Periode.
    Stärke = Mittel auf den Kammzähnen minus stärkstes Mittel an den Zwischenstellen
    (1/2, 1/3, 2/3 Periode); so verlieren Vielfache der echten Periode, weil dort
    dazwischen weitere Linien liegen."""
    phasen = np.arange(0, periode, schritt)
    k = np.arange(0, (len(profil) - 1 - 2 * periode) / periode)  # Platz für Phase + Versatz
    pos = phasen[:, None] + k[None, :] * periode
    n = max(len(k), 1)

    def mittel(versatz):
        return profil[np.round(pos + versatz).astype(int)].sum(axis=1) / n

    luecke = np.max([mittel(periode * f) for f in (1 / 3, 1 / 2, 2 / 3)], axis=0)
    s = mittel(0) - luecke
    i = int(np.argmax(s))
    return s[i], phasen[i]


def _graustufen(pix):
    grau = pymupdf.Pixmap(pymupdf.csGRAY, pix) if pix.n != 1 else pix
    return np.frombuffer(grau.samples, np.uint8).reshape(grau.h, grau.stride)[:, :grau.w].astype(float)


def _raster_in(a, lo, hi):
    px, py = _linienprofil(a, 0), _linienprofil(a, 1)
    ergebnisse = []
    for p in np.arange(lo, hi, 0.05):  # der Treffer ist sehr scharf, daher feine Schritte
        sx, fx = _kamm(px, p)
        sy, fy = _kamm(py, p)
        ergebnisse.append((sx + sy, p, fx, fy))
    return max(ergebnisse)


def raster_erkennen(pix, lo, hi):
    """Sucht ein quadratisches Raster mit Periode in [lo, hi] Pixeln.
    Erkennung je Kachel, dann Mehrheitsentscheid: große dunkle Flächen oder viele
    Wände verfälschen sonst das Gesamtbild, freie Bodenkacheln liefern klare Werte.
    Gibt (zelle, ox, oy) in Pixeln des Pixmaps zurück."""
    a = _graustufen(pix)
    kachel = int(hi * 8)
    stimmen = []
    for y in range(0, max(1, a.shape[0] - kachel // 2), kachel):
        for x in range(0, max(1, a.shape[1] - kachel // 2), kachel):
            t = a[y:y + kachel, x:x + kachel]
            if min(t.shape) < hi * 3:
                continue
            s, p, _, _ = _raster_in(t, lo, hi)
            if s > 0:
                stimmen.append((p, s))
    if not stimmen:
        _, p, fx, fy = _raster_in(a, lo, hi)
        return p, fx, fy
    # Perioden innerhalb ±1 % zusammenfassen, Gewicht = Summe der Stärken
    stimmen.sort()
    gruppen = []
    for p, s in stimmen:
        if gruppen and p - gruppen[-1][-1][0] <= p * 0.01:
            gruppen[-1].append((p, s))
        else:
            gruppen.append([(p, s)])
    beste = max(gruppen, key=lambda g: sum(s for _, s in g))
    p = sum(p * s for p, s in beste) / sum(s for _, s in beste)
    fx, fy = phase_verfeinern_array(a, p, 0.25)
    return p, fx, fy


def phase_verfeinern_array(a, zelle, schritt):
    _, ox = _kamm(_linienprofil(a, 0), zelle, schritt)
    _, oy = _kamm(_linienprofil(a, 1), zelle, schritt)
    return ox, oy


def phase_verfeinern(pix, zelle):
    return phase_verfeinern_array(_graustufen(pix), zelle, 0.25)


def ausschneiden(pdf, seite, ausschnitt, ziel_pfad, zelle_vorgabe=None):
    """ausschnitt = (fx0, fy0, fx1, fy1) als Anteile der Seite.
    zelle_vorgabe = Feldgröße in Punkt (pt), falls die Erkennung versagt."""
    d = pymupdf.open(pdf)
    p = d[seite - 1]
    R = p.rect
    clip = pymupdf.Rect(R.width * ausschnitt[0], R.height * ausschnitt[1],
                        R.width * ausschnitt[2], R.height * ausschnitt[3])
    if zelle_vorgabe:
        zelle_pt = zelle_vorgabe
    else:
        probe = p.get_pixmap(dpi=150, clip=clip)
        z, _, _ = raster_erkennen(probe, RASTER_MIN_PT * 150 / 72, RASTER_MAX_PT * 150 / 72)
        zelle_pt = z * 72 / 150
    s = ZIEL_ZELLE / zelle_pt
    pix = p.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
    ox, oy = phase_verfeinern(pix, ZIEL_ZELLE)
    pix.save(ziel_pfad)
    return {"w": pix.w, "h": pix.h, "zelle": ZIEL_ZELLE,
            "ox": round(ox, 2), "oy": round(oy, 2), "zelle_pt": round(zelle_pt, 2)}


def leere_karte(ziel_pfad, felder_x, felder_y):
    w, h = felder_x * ZIEL_ZELLE, felder_y * ZIEL_ZELLE
    a = np.empty((h, w, 3), np.uint8)
    a[:] = (222, 205, 170)
    rng = np.random.default_rng(1)
    a = np.clip(a.astype(int) + rng.integers(-8, 8, (h, w, 1)), 0, 255).astype(np.uint8)
    pymupdf.Pixmap(pymupdf.csRGB, w, h, a.tobytes(), 0).save(ziel_pfad)
    return {"w": w, "h": h, "zelle": ZIEL_ZELLE, "ox": 0, "oy": 0}


def bild_laden(pfad):
    pix = pymupdf.Pixmap(pfad)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.stride)[:, :pix.w * 3].reshape(pix.h, pix.w, 3)


def zellbereich(karte):
    z, ox, oy = karte["zelle"], karte["ox"], karte["oy"]
    x0 = math.floor(-ox / z)
    y0 = math.floor(-oy / z)
    x1 = math.floor((karte["w"] - 1 - ox) / z)
    y1 = math.floor((karte["h"] - 1 - oy) / z)
    return x0, y0, x1, y1


def maskiert_jpeg(bild, karte, aufgedeckt, ganz=False, qualitaet=85, pixelmaske=None):
    """Rendert das Spielerbild: alles außer aufgedeckten Feldern im Nebel,
    Abdeckungen (SL-Infos) immer übermalt. Mit `pixelmaske` (Bool-Array in Bildgröße, Sichtpolygon-Modus)
    wird statt der Felder stufenlos nach Pixeln aufgedeckt."""
    a = bild.copy()
    h, w, _ = a.shape
    z, ox, oy = karte["zelle"], karte["ox"], karte["oy"]
    if not ganz and pixelmaske is not None:
        a[~pixelmaske[:h, :w]] = NEBEL_FARBE
    elif not ganz:
        x0, y0, x1, y1 = zellbereich(karte)
        offen = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
        for x, y in aufgedeckt:
            if x0 <= x <= x1 and y0 <= y <= y1:
                offen[y - y0, x - x0] = True
        cx = (np.floor((np.arange(w) - ox) / z).astype(int) - x0).clip(0, x1 - x0)
        cy = (np.floor((np.arange(h) - oy) / z).astype(int) - y0).clip(0, y1 - y0)
        maske = offen[cy[:, None], cx[None, :]]
        a[~maske] = NEBEL_FARBE
    for ab in karte.get("abdeckungen", []):
        # Abdeckung in Feldern: x0, y0, x1, y1 (inklusive)
        px0 = int(max(0, ox + ab[0] * z)); py0 = int(max(0, oy + ab[1] * z))
        px1 = int(min(w, ox + (ab[2] + 1) * z)); py1 = int(min(h, oy + (ab[3] + 1) * z))
        if px1 <= px0 or py1 <= py0:
            continue
        rand = np.concatenate([bild[py0, px0:px1], bild[py1 - 1, px0:px1]])
        farbe = np.median(rand, axis=0).astype(np.uint8)
        bereich = a[py0:py1, px0:px1]
        sichtbar = (bereich != NEBEL_FARBE).any(axis=2)
        bereich[sichtbar] = farbe
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, np.ascontiguousarray(a).tobytes(), 0)
    return pix.tobytes("jpg", jpg_quality=qualitaet)


WAND_BLOCK = 10      # Pixel pro Block der Wandkarte
WAND_SCHWELLE = 75   # dunkler als dies = Wandlinie


def _kreise_entfernen(dunkel, zelle_bl):
    """Nummernkreise (dunkle Ringe, Durchmesser ~1,6 Felder) per Kreis-Abstimmung finden und aus dem Dunkel-Raster tilgen."""
    h, w = dunkel.shape
    ys, xs = np.nonzero(dunkel)
    winkel = np.linspace(0, 2 * np.pi, 36, endpoint=False)
    acc = np.zeros(h * w, np.int32)
    beste_r = np.zeros(h * w, np.int16)
    for r in range(int(0.65 * zelle_bl), int(0.95 * zelle_bl) + 1):
        a = np.zeros(h * w, np.int32)
        for t in winkel:
            cy = (ys - r * np.sin(t)).round().astype(int)
            cx = (xs - r * np.cos(t)).round().astype(int)
            ok = (cy >= 0) & (cy < h) & (cx >= 0) & (cx < w)
            a += np.bincount(cy[ok] * w + cx[ok], minlength=h * w).clip(max=1)
        besser = a > acc
        acc = np.where(besser, a, acc)
        beste_r = np.where(besser, r, beste_r)
    kandidaten = np.nonzero(acc >= 26)[0]
    kandidaten = kandidaten[np.argsort(-acc[kandidaten])]
    angenommen = []
    for i in kandidaten:
        cy, cx = divmod(int(i), w)
        if all((cy - y) ** 2 + (cx - x) ** 2 > (1.2 * zelle_bl) ** 2 for y, x, _ in angenommen):
            angenommen.append((cy, cx, int(beste_r[i])))
    for cy, cx, r in angenommen:
        rr = r + 3
        y1, y2, x1, x2 = max(0, cy - rr), min(h, cy + rr + 1), max(0, cx - rr), min(w, cx + rr + 1)
        yy, xx = np.ogrid[y1:y2, x1:x2]
        dunkel[y1:y2, x1:x2] &= ~((yy - cy) ** 2 + (xx - cx) ** 2 <= rr * rr)
    return dunkel


def wandkarte(bild, zelle_px=50):
    """Bool-Raster (True = Wand), 1 Block = WAND_BLOCK Pixel; ein Block gilt als Wand, wenn irgendein Pixel dunkel ist.
    Nummernkreise der Karte werden nicht als Wand gewertet."""
    grau = (bild[..., 0] * 0.299 + bild[..., 1] * 0.587 + bild[..., 2] * 0.114).astype(np.uint8)
    b = 5
    h, w = grau.shape[0] // b, grau.shape[1] // b
    dunkel = grau[:h * b, :w * b].reshape(h, b, w, b).min(axis=(1, 3)) < WAND_SCHWELLE
    dunkel = _kreise_entfernen(dunkel, zelle_px // b)
    k = WAND_BLOCK // b
    h2, w2 = h // k, w // k
    return dunkel[:h2 * k, :w2 * k].reshape(h2, k, w2, k).any(axis=(1, 3))


def weg_felder(wand, karte, von, nach, max_felder=80, erlaubt=None):
    """Kürzester Weg (in Feldern, Diagonalen 1,5) zwischen zwei Feldern ohne Wände zu durchqueren; None = kein Weg."""
    import heapq
    z, ox, oy = karte["zelle"], karte["ox"], karte["oy"]
    b = WAND_BLOCK
    pro_feld = z / b
    if erlaubt is not None:  # nur auf aufgedeckten Feldern gehen
        wand = wand.copy()
        frei = np.zeros_like(wand)
        n = max(1, int(round(z / b)))
        for cx, cy in erlaubt:
            y0, x0 = int((oy + cy * z) // b), int((ox + cx * z) // b)
            if y0 >= 0 and x0 >= 0:
                frei[y0:y0 + n, x0:x0 + n] = True
        wand |= ~frei
    h, w = wand.shape

    def block(f):
        return (int((oy + (f[1] + 0.5) * z) // b), int((ox + (f[0] + 0.5) * z) // b))

    def frei_nahe(y, x, r=4):
        for rr in range(r + 1):
            for dy in range(-rr, rr + 1):
                for dx in range(-rr, rr + 1):
                    if 0 <= y + dy < h and 0 <= x + dx < w and not wand[y + dy, x + dx]:
                        return (y + dy, x + dx)
        return None

    s = frei_nahe(*block(von))
    t = frei_nahe(*block(nach))
    if s is None or t is None:
        return None
    marge = int(max_felder * pro_feld)
    y0, y1 = max(0, min(s[0], t[0]) - marge), min(h, max(s[0], t[0]) + marge + 1)
    x0, x1 = max(0, min(s[1], t[1]) - marge), min(w, max(s[1], t[1]) + marge + 1)
    grenze = max_felder * pro_feld
    best = {s: 0.0}
    heap = [(0.0, s)]
    schritte = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.5), (1, -1, 1.5), (-1, 1, 1.5), (-1, -1, 1.5))
    while heap:
        d, (y, x) = heapq.heappop(heap)
        if (y, x) == t:
            return int(round(d / pro_feld))
        if d > best.get((y, x), 1e18) or d > grenze:
            continue
        for dy, dx, k in schritte:
            ny, nx = y + dy, x + dx
            if not (y0 <= ny < y1 and x0 <= nx < x1) or wand[ny, nx]:
                continue
            if dy and dx and (wand[y + dy, x] or wand[y, x + dx]):
                continue  # nicht um Wandecken quetschen
            nd = d + k
            if nd < best.get((ny, nx), 1e18):
                best[(ny, nx)] = nd
                heapq.heappush(heap, (nd, (ny, nx)))
    return None


def sicht_felder(wand, karte, feld, radius_felder, schliessen=5):
    """Felder (cx, cy), die von `feld` aus per echter Sichtlinie (Strahlen, Wandblöcke blockieren) in
    `radius_felder` Feldern zu sehen sind. Rechnet nur in einem Fenster um das Token (schnell)."""
    z, ox, oy = karte["zelle"], karte["ox"], karte["oy"]
    B = WAND_BLOCK
    h, w = wand.shape
    cb = max(1, int(z // B))
    by, bx = int((oy + (feld[1] + .5) * z) // B), int((ox + (feld[0] + .5) * z) // B)
    start = None
    for r in range(8):  # nächster freier Block (Token steht evtl. auf der Wandlinie)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                y, x = by + dy, bx + dx
                if 0 <= y < h and 0 <= x < w and not wand[y, x]:
                    start = (y, x)
                    break
            if start:
                break
        if start:
            break
    if not start:
        return []
    lim = int(radius_felder * cb)
    pad = lim + schliessen + 2
    y0, x0 = start[0] - pad, start[1] - pad
    n = 2 * pad + 1
    # Fenster mit Wand-Rand (außerhalb der Karte = Wand)
    fenster = np.ones((n, n), bool)
    ya, yb, xa, xb = max(0, y0), min(h, y0 + n), max(0, x0), min(w, x0 + n)
    fenster[ya - y0:yb - y0, xa - x0:xb - x0] = wand[ya:yb, xa:xb]
    sy = sx = pad
    strahlen = int(max(360, lim * 8))
    ang = np.linspace(0, 2 * np.pi, strahlen, endpoint=False)
    d = np.arange(0, lim + 0.01, 0.5)
    yy = np.rint(sy + np.sin(ang)[:, None] * d[None, :]).astype(int)
    xx = np.rint(sx + np.cos(ang)[:, None] * d[None, :]).astype(int)
    blockiert = fenster[yy, xx]
    frei = np.cumsum(blockiert, axis=1) == 0   # bis zur ersten Wand
    gesehen = np.zeros((n, n), bool)
    gesehen[yy[frei], xx[frei]] = True
    r = schliessen

    def box(a):
        c = np.cumsum(np.cumsum(np.pad(a.astype(np.int32), ((r + 1, r), (r + 1, r))), 0), 1)
        m = 2 * r + 1
        return c[m:, m:] - c[:-m, m:] - c[m:, :-m] + c[:-m, :-m]
    gesehen = box(box(gesehen) > 0) == (2 * r + 1) ** 2
    felder = []
    cx0 = int(np.floor((x0 * B - ox) / z)); cx1 = int(np.floor(((x0 + n) * B - ox) / z))
    cy0 = int(np.floor((y0 * B - oy) / z)); cy1 = int(np.floor(((y0 + n) * B - oy) / z))
    for cy in range(cy0, cy1 + 1):
        for cx in range(cx0, cx1 + 1):
            ys, xs = int((oy + cy * z) // B) - y0, int((ox + cx * z) // B) - x0
            if ys < 0 or xs < 0 or ys >= n or xs >= n:
                continue
            if (oy + cy * z) < 0 or (ox + cx * z) < 0:
                continue
            sub = gesehen[ys:ys + cb, xs:xs + cb]
            if sub.size and sub.mean() > 0.12:
                felder.append((cx, cy))
    return felder
