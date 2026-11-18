"""Karte: SL-Befehle für Karten (registrieren, aktivieren, Unterlagen) und Barrieren (Wände, Türen, Fenster)."""
import math

from bereiche.kern import Fehler
from . import barrieren
from .nebel import auto_nebel_aktiv, sicht, sichtmodus
from .token import aktive


def registrieren(kx, k):
    k.setdefault("aufgedeckt", [])
    k.setdefault("abdeckungen", [])
    k.setdefault("meterProFeld", 1.5)
    k["nebelVersion"] = k.get("nebelVersion", 0) + 1
    kx.z["karten"][k["id"]] = k
    kx.res.karte_neu_geladen(k["id"])


def aktivieren(kx, kid):
    z = kx.z
    if kid not in z["karten"]:
        raise Fehler(f"Karte {kid!r} unbekannt")
    z["karteAktiv"] = kid
    z["karten"][kid]["bekannt"] = True
    kx.protokoll("system", f"Karte: {z['karten'][kid]['name']}")


def bekannt(kx, b):
    """Karte in den Unterlagen der Spieler anzeigen (oder wieder entfernen), optional mit Legende."""
    k = aktive(kx, b["id"])
    k["bekannt"] = bool(b.get("bekannt", True))
    if "legende" in b:
        k["legende"] = b["legende"]


def barrieren_befehl(kx, op, b):
    """SL-Befehle rund um Barrieren (Wände, Türen, Fenster); Koordinaten in Feldern (Gitterpunkte, auch halbe)."""
    z = kx.z
    kid = b.get("karte") or z["karteAktiv"]
    k = aktive(kx, kid)
    if k is None:
        raise Fehler("Keine Karte")
    zl, ox, oy = k["zelle"], k["ox"], k["oy"]

    def px(x, y):
        return [ox + float(x) * zl, oy + float(y) * zl]

    def feld(p):
        return [round((p[0] - ox) / zl * 2) / 2, round((p[1] - oy) / zl * 2) / 2]

    def mitte(e):
        return (e["p"][0] + e["p"][2]) / 2, (e["p"][1] + e["p"][3]) / 2

    if op == "barrieren-setzen":  # fertige Barrieren (z. B. aus dem Kartenimport) übernehmen
        d = b.get("daten")
        if not isinstance(d, dict) or not isinstance(d.get("waende"), list) or not isinstance(d.get("extra"), list):
            raise Fehler("barrieren-setzen: daten mit waende und extra erwartet")
        d.setdefault("loeschen", [])
        kx.res.barr_speichern(kid, d)
        return {"waende": len(d["waende"]), "tueren": sum(1 for e in d["extra"] if e["typ"] in ("tuer", "geheimtuer"))}
    if op == "barrieren-erkennen":
        alt = kx.res.barr(kid)
        if alt and alt.get("quelle") == "import" and not b.get("erzwingen"):
            raise Fehler("Die Wände dieser Karte stammen aus einem Import und sind exakt; Erkennung würde sie ersetzen "
                         "(erzwingen=true, falls gewollt)")
        neu = barrieren.erkennen(kx.res.bild(kid), int(zl))
        if alt:  # Korrekturen und Türzustände behalten
            neu["loeschen"] = alt.get("loeschen", [])
            alte = [e for e in alt["extra"] if e.get("quelle") == "auto"]
            for e in neu["extra"]:
                m = mitte(e)
                for a in alte:
                    if math.hypot(mitte(a)[0] - m[0], mitte(a)[1] - m[1]) < 12:
                        e["offen"], e["typ"], e["blockiertVon"] = a.get("offen", False), a["typ"], a.get("blockiertVon")
            neu["extra"] += [e for e in alt["extra"] if e.get("quelle") != "auto"]
        kx.res.barr_speichern(kid, neu)
        return {"waende": len(neu["waende"]), "tueren": sum(1 for e in neu["extra"] if e["typ"] in ("tuer", "geheimtuer"))}
    d = kx.res.barr(kid)
    if d is None:
        raise Fehler("Für diese Karte gibt es noch keine Barrieren (sl.py barrieren erkennen)")
    ids = [e["id"] for e in d["extra"]]
    if op == "barriere-liste":
        return {"karte": kid, "waende": len(barrieren.aktive_waende(d)), "nebelModus": k.get("nebelModus", "raster"),
                "extra": [{"id": e["id"], "typ": e["typ"], "offen": bool(e.get("offen")), "von": feld(e["p"][:2]),
                           "bis": feld(e["p"][2:]), "blockiertVon": e.get("blockiertVon"), "quelle": e.get("quelle")}
                          for e in d["extra"]]}
    if op == "tuer":
        ziele = list(b.get("ids") or [])
        if b.get("bei"):  # nächste Tür zu einem Feld (Gitterpunkt oder Feldmitte, z. B. 12.5 7)
            c = px(*b["bei"])
            tueren = [e for e in d["extra"] if e["typ"] in ("tuer", "geheimtuer")]
            if tueren:
                e = min(tueren, key=lambda e: math.hypot(mitte(e)[0] - c[0], mitte(e)[1] - c[1]))
                if math.hypot(mitte(e)[0] - c[0], mitte(e)[1] - c[1]) <= 1.6 * zl:
                    ziele.append(e["id"])
        if not ziele:
            raise Fehler("Keine Tür gefunden (ID oder Feld prüfen: sl.py barrieren liste)")
        res = []
        for i in ziele:
            if i not in ids:
                raise Fehler(f"Barriere {i!r} unbekannt")
            e = d["extra"][ids.index(i)]
            if e["typ"] not in ("tuer", "geheimtuer"):
                raise Fehler(f"{i} ist keine Tür")
            e["offen"] = (not e.get("offen")) if b.get("offen") is None else bool(b["offen"])
            res.append(f"{i}: {'offen' if e['offen'] else 'geschlossen'}")
        kx.res.barr_speichern(kid, d)
        if sichtmodus(k) and auto_nebel_aktiv(kx, k):  # Sicht durch die Tür sofort nachziehen
            sicht(kx, [t for t in z["tokens"].values() if t["art"] == "sc"], k, kid)
        return {"tueren": res}
    if op == "barriere-neu":
        typ = b.get("typ", "wand")
        if typ not in barrieren.TYPEN:
            raise Fehler(f"Typ {typ!r} unbekannt ({', '.join(barrieren.TYPEN)})")
        i = 1
        while f"m{i}" in ids:
            i += 1
        e = {"id": b.get("id") or f"m{i}", "typ": typ, "p": px(*b["von"]) + px(*b["bis"]),
             "offen": bool(b.get("offen", False)), "blockiertVon": b.get("blockiertVon"), "quelle": "manuell"}
        if e["id"] in ids:
            raise Fehler(f"ID {e['id']} existiert schon")
        d["extra"].append(e)
        kx.res.barr_speichern(kid, d)
        return {"id": e["id"]}
    if op == "barriere-aendern":
        if b["id"] not in ids:
            raise Fehler(f"Barriere {b['id']!r} unbekannt")
        e = d["extra"][ids.index(b["id"])]
        for key in ("typ", "blockiertVon"):
            if key in b:
                e[key] = b[key]
        kx.res.barr_speichern(kid, d)
        return {}
    if op == "barriere-weg":
        n = 0
        for i in b.get("ids") or []:
            if i not in ids:
                raise Fehler(f"Barriere {i!r} unbekannt")
        if b.get("ids"):
            n = len(b["ids"])
            d["extra"] = [e for e in d["extra"] if e["id"] not in b["ids"]]
        if b.get("bereich"):  # erkannte Wandstücke (und manuelle Barrieren) in diesem Feldbereich ignorieren
            x0, y0, x1, y1 = b["bereich"]
            r = px(min(x0, x1), min(y0, y1)) + px(max(x0, x1), max(y0, y1))
            vor = len(barrieren.aktive_waende(d))
            d.setdefault("loeschen", []).append(r)
            n += vor - len(barrieren.aktive_waende(d))
            behalten = [e for e in d["extra"] if not (e.get("quelle") == "manuell" and r[0] <= mitte(e)[0] <= r[2]
                                                      and r[1] <= mitte(e)[1] <= r[3])]
            n += len(d["extra"]) - len(behalten)
            d["extra"] = behalten
        kx.res.barr_speichern(kid, d)
        return {"entfernt": n}
    if op == "barriere-bereiche-frei":  # alle Löschbereiche wieder aufheben
        d["loeschen"] = []
        kx.res.barr_speichern(kid, d)
        return {}
    raise Fehler(f"Unbekannter Barrieren-Befehl {op!r}")


def erkennen(kx, b):
    return barrieren_befehl(kx, "barrieren-erkennen", b)
