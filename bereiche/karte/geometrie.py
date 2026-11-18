"""Karte: Felder und Abstände (reine Funktionen)."""


def pf_distanz(x0, y0, x1, y1):
    """Felder nach PF1-Diagonalregel (1-2-1-2 …)."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    return max(dx, dy) + min(dx, dy) // 2


def zellen_rechteck(x0, y0, x1, y1):
    return [(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]


def zellen_kreis(cx, cy, r):
    return [(x, y) for x in range(cx - r, cx + r + 1) for y in range(cy - r, cy + r + 1)
            if pf_distanz(cx, cy, x, y) <= r]


def token_felder(t):
    g = t.get("groesse", 1)
    return [(t["x"] + i, t["y"] + j) for i in range(g) for j in range(g)]


def abstand(t1, t2):
    """Kleinster Abstand in Feldern zwischen zwei Tokens (berücksichtigt Größe)."""
    return min(pf_distanz(a[0], a[1], b[0], b[1]) for a in token_felder(t1) for b in token_felder(t2))


def reichweite_felder(t):
    """Nahkampfreichweite eines Tokens in Feldern (1 = angrenzend; gesetzt durch Größenmodi)."""
    return max(1, int(t.get("reichweite") or 1))
