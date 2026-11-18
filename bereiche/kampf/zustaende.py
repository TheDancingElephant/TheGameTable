"""Kampf: Zustände, Trefferpunkte, Tod von Gegnern, Gesundheitstext für die Spieler."""
from bereiche import charakter as CH, karte as KA
from bereiche.kern import Fehler

ZUSTAENDE = [
    "Auf dem falschen Fuß", "Benommen", "Betäubt", "Bewusstlos", "Blind", "Entkräftet",
    "Erschöpft", "Erschüttert", "Fasziniert", "Festgehalten", "Gelähmt", "Geblendet",
    "Hilflos", "Im Ringkampf", "In Panik", "Kränkelnd", "Liegend", "Sterbend", "Stabil",
    "Taub", "Tot", "Übelkeit", "Unsichtbar", "Verängstigt", "Verstrickt", "Verwirrt", "Wankend",
]
UNFAEHIG = ("Bewusstlos", "Sterbend", "Hilflos", "Gelähmt", "Betäubt")


def unfaehig(t):
    """Kann das Token nicht handeln (bewusstlos, gelähmt …)?"""
    return bool(set(t.get("zustaende", [])) & set(UNFAEHIG))


def gesundheit_text(t):
    """Was Spieler über die TP eines Gegners erfahren."""
    if t.get("tpMax") in (None, 0):
        return None
    if t.get("tp", 0) <= 0:
        return "kampfunfähig"
    q = t["tp"] / t["tpMax"]
    if q >= 1:
        return "unverletzt"
    if q > 0.5:
        return "leicht verletzt"
    if q > 0.25:
        return "schwer verletzt"
    return "dem Tode nah"


def tot_abgleich(z):
    """Gegner/NSC: Zustand „Tot“ automatisch setzen (TP <= 0) bzw. wieder entfernen (TP > 0).
    Nur automatisch gesetzte Markierungen (Feld totAuto) werden wieder entfernt; von Hand gesetztes „Tot“ bleibt.
    SC bleiben unberührt (Sterbend/Bewusstlos)."""
    for t in z["tokens"].values():
        if t.get("art") not in ("gegner", "nsc") or t.get("tp") is None:
            continue
        zs = t.setdefault("zustaende", [])
        if t["tp"] <= 0 and "Tot" not in zs:
            zs.append("Tot")
            t["totAuto"] = True
        elif t["tp"] > 0 and "Tot" in zs and t.get("totAuto"):
            zs.remove("Tot")
            del t["totAuto"]
        elif t["tp"] > 0 and "Tot" not in zs:
            t.pop("totAuto", None)


def ist_tot(z, eintrag):
    t = z["tokens"].get(eintrag.get("tokenId") or "")
    return bool(t and t.get("art") in ("gegner", "nsc") and "Tot" in t.get("zustaende", []))


def schaden(kx, ziel, n):
    """Zieht Schaden von den TP ab (SC: auch in der Charakterdatei)."""
    if ziel.get("tp") is not None:
        ziel["tp"] -= n
        if ziel["art"] == "sc":
            CH.tp_uebernehmen(kx, ziel)


def heilen(kx, ziel, n):
    """Heilt bis höchstens zum Maximum (SC: auch in der Charakterdatei)."""
    if ziel.get("tp") is not None:
        ziel["tp"] = min(ziel["tp"] + n, ziel.get("tpMax") or ziel["tp"] + n)
        if ziel["art"] == "sc":
            CH.tp_uebernehmen(kx, ziel)


def zustand_an(ziel, name):
    if name and name not in ziel.setdefault("zustaende", []):
        ziel["zustaende"].append(name)


def tp_sl(kx, tid, delta):
    """SL: TP eines Tokens ändern (ohne Obergrenze)."""
    t = KA.finden(kx, tid)
    t["tp"] = t.get("tp", 0) + int(delta)
    if t["art"] == "sc" and t.get("charId"):
        CH.tp_uebernehmen(kx, t)


def zustand_sl(kx, tid, name, an=True):
    t = KA.finden(kx, tid)
    zs = t.setdefault("zustaende", [])
    if an and name not in zs:
        zs.append(name)
    elif not an and name in zs:
        zs.remove(name)


def tp_spieler(kx, tid, delta):
    """Spieler: TP des eigenen SC ändern (Heilung nicht über das Maximum)."""
    t = KA.finden(kx, tid)
    if t["art"] != "sc":
        raise Fehler("Nur eigene Charaktere")
    t["tp"] = t.get("tp", 0) + int(delta)
    if t.get("tpMax") is not None:
        t["tp"] = min(t["tp"], t["tpMax"])
    CH.tp_uebernehmen(kx, t)
    kx.protokoll("system", f"{t['name']}: TP {'+' if int(delta) >= 0 else ''}{delta} → {t['tp']}/{t.get('tpMax')}")


def zustand_spieler(kx, tid, name):
    """Spieler: Zustand des eigenen SC umschalten."""
    t = KA.finden(kx, tid)
    if t["art"] != "sc":
        raise Fehler("Nur eigene Charaktere")
    zs = t.setdefault("zustaende", [])
    if name in zs:
        zs.remove(name)
    else:
        zs.append(name)
