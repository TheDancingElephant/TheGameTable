"""Karte: Nebel des Krieges (Feldraster oder Sichtpolygon), Sichtweite, Auto-Nebel, Raster/Abdeckungen."""
import re

from bereiche import charakter as CH, reaktion
from bereiche.kern import Fehler
from . import barrieren, karten
from .geometrie import zellen_kreis, zellen_rechteck
from .token import aktive, mit_sichtpartnern, offen


def sichtmodus(k):
    """Stufenloser Nebel nach Sichtpolygon (statt Feldraster) für diese Karte aktiv?"""
    return bool(k) and k.get("nebelModus") == "sicht"


def auto_nebel_aktiv(kx, k):
    return bool(k.get("autoNebel", kx.einst.get("autoNebel", False)))


def _version(k):
    k["nebelVersion"] = k.get("nebelVersion", 0) + 1


def aendern(kx, k, zellen, auf):
    """Felder auf- oder zudecken (im Sichtmodus auch in der Pixelmaske)."""
    if sichtmodus(k):  # Maske für die Darstellung mitführen (Felder: ganze Feldfläche)
        m = kx.res.maske(k["id"])
        for cx, cy in zellen:
            barrieren.maske_rechteck(m, (k["ox"] + cx * k["zelle"], k["oy"] + cy * k["zelle"],
                                         k["ox"] + (cx + 1) * k["zelle"], k["oy"] + (cy + 1) * k["zelle"]), auf)
        kx.res.maske_sichern(k["id"])
    o = offen(k)
    if auf:
        o |= set(zellen)
    else:
        o -= set(zellen)
    k["aufgedeckt"] = sorted([list(c) for c in o])
    _version(k)


def sicht_radius(kx, t, k):
    """Sichtweite in Feldern: Token-Feld `sicht`, sonst Dunkelsicht aus den Charakterdaten, sonst Karten-/Standardwert (8)."""
    if t.get("sicht"):
        return int(t["sicht"])
    c = CH.von_token(kx, t) or {}
    m = re.search(r"Dunkelsicht\D{0,12}?(\d+(?:[.,]\d+)?)\s*m", str(c.get("faehigkeiten", "")))
    if m:
        return max(1, int(float(m.group(1).replace(",", ".")) // k.get("meterProFeld", 1.5)))
    return int(k.get("sichtFelder", 8))


def sicht(kx, tokens, k=None, kid=None):
    """Deckt per Sichtlinie auf (nur aufdecken). Gibt die Anzahl neu aufgedeckter Felder zurück."""
    kid = kid or kx.z["karteAktiv"]
    k = k or aktive(kx, kid)
    if not k or "zelle" not in k:
        return 0
    tokens = mit_sichtpartnern(kx, tokens)
    if sichtmodus(k) and kx.res.barr(kid) is not None:
        return _sichtpolygon(kx, tokens, k, kid)
    wand = kx.res.wand(kid)
    neu = set()
    for t in tokens:
        if t["art"] != "sc" or t.get("karte", kid) != kid:
            continue
        neu.update(karten.sicht_felder(wand, k, (t["x"], t["y"]), sicht_radius(kx, t, k)))
    neu -= offen(k)
    if neu:
        aendern(kx, k, neu, True)
    return len(neu)


def _sichtpolygon(kx, tokens, k, kid):
    """Sichtpolygon-Nebel: Strahlen vom Mittelpunkt jeder Spielfigur bis zur nächsten Barriere (höchstens Sichtweite);
    das Polygon wird stufenlos in die Aufdeck-Maske eingetragen. Pflegt zusätzlich die Feldliste (Mittelpunkt sichtbar),
    damit Tokensichtbarkeit und Altfunktionen weiterlaufen. Gibt die Zahl neu aufgedeckter Felder zurück."""
    seg, seite = kx.res.barr(kid, blockierend=True)
    maske = kx.res.maske(kid)
    z, ox, oy = k["zelle"], k["ox"], k["oy"]
    M = barrieren.MASKE_B
    geaendert = False
    neue_felder = set()
    for t in tokens:
        if t["art"] != "sc" or t.get("karte", kid) != kid:
            continue
        r = (sicht_radius(kx, t, k) + 0.5) * z
        mitte = (ox + (t["x"] + 0.5) * z, oy + (t["y"] + 0.5) * z)
        beste = None
        for dx, dy in [(0, 0)] + [(a * 14, b * 14) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]:
            o = (mitte[0] + dx, mitte[1] + dy)
            winkel, dist = barrieren.sichtpolygon(seg, seite, o, r)
            if beste is None or dist.sum() > beste[2].sum():
                beste = (o, winkel, dist)
            if (dx, dy) == (0, 0) and dist.max() > 0.3 * z:
                break  # Mittelpunkt sieht normal; Ausweichpunkte nur, wenn die Figur praktisch in einer Wand steht
        o, winkel, dist = beste
        y0, x0, neu = barrieren.sicht_zeichnen(maske, o, winkel, dist)
        if neu.any():
            geaendert = True
        rmax = float(dist.max()) + z
        for cy in range(int((o[1] - rmax - oy) // z), int((o[1] + rmax - oy) // z) + 1):
            for cx in range(int((o[0] - rmax - ox) // z), int((o[0] + rmax - ox) // z) + 1):
                px, py = ox + (cx + 0.5) * z, oy + (cy + 0.5) * z
                if 0 <= px < k["w"] and 0 <= py < k["h"] and maske[int(py // M), int(px // M)]:
                    neue_felder.add((cx, cy))
    neue_felder -= offen(k)
    if geaendert or neue_felder:
        kx.res.maske_sichern(kid)
        k["aufgedeckt"] = sorted([list(c) for c in offen(k) | neue_felder])
        _version(k)
    return len(neue_felder)


@reaktion("token_bewegt")
def _auto_nebel(kx, token, von=None):
    """SC bewegt: bei Auto-Nebel auf der aktiven Karte aufdecken, was er jetzt sieht."""
    if token["art"] != "sc":
        return None
    k = aktive(kx)
    if k and token.get("karte", kx.z["karteAktiv"]) == kx.z["karteAktiv"] and auto_nebel_aktiv(kx, k):
        sicht(kx, [token], k)
    return None


def auf_zu(kx, op, b):
    """SL: aufdecken/verdecken (form rechteck, kreis, liste, alles)."""
    k = aktive(kx, b.get("karte"))
    form = b.get("form", "rechteck")
    if form == "rechteck":
        zellen = zellen_rechteck(*b["felder"])
    elif form == "kreis":
        zellen = zellen_kreis(*b["felder"])
    elif form == "liste":
        zellen = [tuple(c) for c in b["felder"]]
    elif form == "alles":
        x0, y0, x1, y1 = karten.zellbereich(k)
        zellen = zellen_rechteck(x0, y0, x1, y1)
    else:
        raise Fehler(f"Form {form!r} unbekannt")
    aendern(kx, k, zellen, op == "aufdecken")


def abdecken(kx, b):
    k = aktive(kx, b.get("karte"))
    if b.get("entfernen"):
        k["abdeckungen"] = [a for a in k["abdeckungen"] if a != b["felder"]]
    else:
        k["abdeckungen"].append(list(b["felder"]))
    _version(k)


def raster(kx, b):
    """Raster und Kartenschalter ändern (zelle, ox, oy, meterProFeld, waendeSperren, autoNebel, sichtFelder)."""
    k = aktive(kx, b.get("karte"))
    for key in ("zelle", "ox", "oy", "meterProFeld"):
        if key in b:
            k[key] = float(b[key])
    if "waendeSperren" in b:
        k["waendeSperren"] = bool(b["waendeSperren"])
    if "autoNebel" in b:
        if b["autoNebel"] is None:
            k.pop("autoNebel", None)
        else:
            k["autoNebel"] = bool(b["autoNebel"])
    if "sichtFelder" in b:
        k["sichtFelder"] = int(b["sichtFelder"])
    _version(k)


def modus(kx, b, erkennen):
    """Nebelmodus „sicht“ (Sichtpolygon, erkennt fehlende Barrieren mit `erkennen`) oder „raster“."""
    kid = b.get("karte") or kx.z["karteAktiv"]
    k = aktive(kx, kid)
    kx.res.maske_verwerfen(kid)
    k.pop("nebelMaske", None)
    if b["modus"] == "sicht":
        if kx.res.barr(kid) is None:
            erkennen(kx, {"karte": kid})
        k["nebelModus"] = "sicht"
        kx.res.maske(kid)
        kx.res.maske_sichern(kid)
    else:
        k.pop("nebelModus", None)
    _version(k)
