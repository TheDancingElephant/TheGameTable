"""Charakter: Erfahrungspunkte (EP) und Stufe, Herausforderungsgrad (HG) → EP."""
import re

from bereiche.kern import Fehler
from .werte import alle, attr_mod, speichern, wirksam

# Erfahrungspunkte je Stufe (PF1), Index = Stufe; Aufstiegsgeschwindigkeit je Kampagne (kampagne.json: "epTempo")
EP_TABELLEN = {
    "langsam": [0, 0, 3000, 7500, 14000, 23000, 35000, 53000, 77000, 115000, 160000, 235000, 330000, 475000,
                665000, 955000, 1350000, 1900000, 2700000, 3850000, 5350000],
    "mittel": [0, 0, 2000, 5000, 9000, 15000, 23000, 35000, 51000, 75000, 105000, 155000, 220000, 315000,
               445000, 635000, 890000, 1300000, 1800000, 2550000, 3600000],
    "schnell": [0, 0, 1300, 3300, 6000, 10000, 15000, 23000, 34000, 50000, 71000, 105000, 145000, 210000,
                295000, 425000, 600000, 850000, 1200000, 1700000, 2400000],
}
# EP-Belohnung je Herausforderungsgrad
HG_EP = {"1/8": 50, "1/6": 65, "1/4": 100, "1/3": 135, "1/2": 200, "1": 400, "2": 600, "3": 800, "4": 1200,
         "5": 1600, "6": 2400, "7": 3200, "8": 4800, "9": 6400, "10": 9600, "11": 12800, "12": 19200,
         "13": 25600, "14": 38400, "15": 51200, "16": 76800, "17": 102400, "18": 153600, "19": 204800, "20": 307200}
TREFFERWUERFEL = [("barbar", 12), ("kämpfer", 10), ("paladin", 10), ("waldläufer", 10), ("gestaltwandler", 10),
                  ("schwertkämpfer", 10), ("kavalier", 10), ("antipaladin", 10), ("magus", 8), ("kleriker", 8),
                  ("druide", 8), ("schurke", 8), ("barde", 8), ("mönch", 8), ("alchemist", 8), ("inquisitor", 8),
                  ("orakel", 8), ("hexenjäger", 8), ("ninja", 8), ("schamane", 8), ("skalde", 8), ("investigator", 8),
                  ("magier", 6), ("hexenmeister", 6), ("hexe", 6), ("arkanist", 6)]
FERTIGKEITSPUNKTE = [("schurke", 8), ("ninja", 8), ("investigator", 6), ("barde", 6), ("waldläufer", 6), ("inquisitor", 6),
                     ("skalde", 4), ("gestaltwandler", 4), ("barbar", 4), ("druide", 4), ("mönch", 4), ("alchemist", 4),
                     ("orakel", 4), ("schwertkämpfer", 4), ("kavalier", 4), ("hexenjäger", 4)]


def tabelle(kx):
    return EP_TABELLEN.get(kx.einst.get("epTempo", "mittel"), EP_TABELLEN["mittel"])


def stufe_von(c):
    if c.get("stufe"):
        return int(c["stufe"])
    zahlen = re.findall(r"\d+", c.get("klasse") or "")  # Mehrklassig: "Mönch 5 Schurke 3" = Stufe 8
    return sum(int(z) for z in zahlen) if zahlen else 1


def trefferwuerfel(klasse):
    k = (klasse or "").lower()
    return next((w for n, w in TREFFERWUERFEL if n in k), 8)


def ep_info(kx, c):
    tab = tabelle(kx)
    stufe = stufe_von(c)
    ep = int(c.get("ep") or 0)
    naechste = tab[stufe + 1] if stufe + 1 < len(tab) else None
    return {"stufe": stufe, "ep": ep, "naechste": naechste, "basis": tab[stufe] if stufe < len(tab) else 0,
            "aufstiegMoeglich": naechste is not None and ep >= naechste and not c.get("aufstieg"),
            "tw": trefferwuerfel(c.get("klasse")),
            "fertigkeitspunkte": next((p for n, p in FERTIGKEITSPUNKTE if n in (c.get("klasse") or "").lower()), 2),
            "koMod": attr_mod((c.get("attribute") or {}).get("KO")),
            "inMod": attr_mod((c.get("attribute") or {}).get("IN"))}


def ep_vergeben(kx, char_ids, je, grund):
    for c in alle(kx):
        if c["id"] not in char_ids:
            continue
        c = wirksam(kx, c)
        vorher = ep_info(kx, c)["aufstiegMoeglich"]
        c["ep"] = int(c.get("ep") or 0) + je
        info = ep_info(kx, c)
        speichern(kx, c)
        if info["aufstiegMoeglich"] and not vorher:
            kx.protokoll("system", f"⬆ {c['name']} kann auf Stufe {info['stufe'] + 1} aufsteigen!")
    namen = ", ".join(c["name"] for c in alle(kx) if c["id"] in char_ids)
    kx.protokoll("ep", f"{grund}: {je} EP für {namen}", ep=je, grund=grund)


def ep_befehl(kx, b):
    """EP aus HG der Gegner-Token, HG-Liste oder festem Betrag, geteilt durch die Empfänger
    (Standard: alle SC auf der aktiven Karte)."""
    z = kx.z
    empfaenger = b.get("an") or [t["charId"] for t in z["tokens"].values()
                                 if t["art"] == "sc" and t.get("karte") == z["karteAktiv"] and t.get("charId")]
    if not empfaenger:
        raise Fehler("Keine Empfänger")
    gesamt = int(b.get("ep") or 0)
    hg_liste = list(b.get("hg") or [])
    for tid in b.get("gegner") or []:
        t = z["tokens"].get(tid) or next((t for t in z["tokens"].values() if t["name"].lower() == str(tid).lower()), None)
        if t is None:
            raise Fehler(f"Token {tid!r} nicht gefunden")
        if t.get("hg") is None:
            raise Fehler(f"{t['name']} hat keinen HG")
        hg_liste.append(str(t["hg"]))
    for hg in hg_liste:
        if str(hg) not in HG_EP:
            raise Fehler(f"Unbekannter HG {hg}")
        gesamt += HG_EP[str(hg)]
    je = gesamt // len(empfaenger)
    ep_vergeben(kx, set(empfaenger), je, b.get("grund") or "Erfahrung")
    return {"je": je, "gesamt": gesamt}
