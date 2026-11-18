"""Bereich Besitz: Gruppenkasse, Gegenstände und Beute (Träger: Charakter-ID oder 'gruppe', Ort frei wählbar).

Öffentlich: ausruestung (Stand, legt ihn beim ersten Aufruf aus den Charakterbögen an), aendern (kasse, item-neu,
item-aendern, item-weg), MUENZEN.
"""
from bereiche import charakter as CH
from bereiche.kern import Fehler

MUENZEN = ("kp", "sp", "gp", "pp")  # Kupfer-, Silber-, Gold-, Platinmünzen (alte Feldnamen)


def ausruestung(kx):
    """Gruppenkasse und Gegenstände je Träger; beim ersten Aufruf aus den Charakterbögen übernommen."""
    z = kx.z
    a = z.get("ausruestung")
    if a is None:
        a = {"kasse": {m: 0 for m in MUENZEN}, "gegenstaende": [], "naechsteId": 1}
        for c in CH.alle(kx):
            for zeile in (c.get("ausruestung") or "").splitlines():
                zeile = zeile.strip()
                if zeile:
                    a["gegenstaende"].append({"id": a["naechsteId"], "name": zeile, "anzahl": 1, "traeger": c["id"],
                                              "ort": "dabei", "notiz": ""})
                    a["naechsteId"] += 1
        z["ausruestung"] = a
    return a


def aendern(kx, b):
    """Spieler und SL: kasse (delta oder setzen), item-neu, item-aendern, item-weg."""
    a = ausruestung(kx)
    op = b.get("op")
    if op == "kasse":
        for m in MUENZEN:
            if m in (b.get("delta") or {}):
                neu = a["kasse"][m] + int(b["delta"][m])
                if neu < 0:
                    raise Fehler(f"Nicht genug {m.upper()} in der Kasse")
                a["kasse"][m] = neu
            if m in (b.get("setzen") or {}):
                a["kasse"][m] = max(0, int(b["setzen"][m]))
        teile = ", ".join(f"{int(v):+d} {m}" for m, v in (b.get("delta") or {}).items() if int(v))
        kx.protokoll("system", f"Gruppenkasse: {teile or 'geändert'} ({b.get('grund') or 'ohne Grund'})")
    elif op == "item-neu":
        name = (b.get("name") or "").strip()
        if not name:
            raise Fehler("Name fehlt")
        i = a["naechsteId"]
        a["naechsteId"] += 1
        a["gegenstaende"].append({"id": i, "name": name[:120], "anzahl": max(1, int(b.get("anzahl") or 1)),
                                  "traeger": b.get("traeger") or "gruppe", "ort": (b.get("ort") or "dabei")[:40],
                                  "notiz": (b.get("notiz") or "")[:300]})
        return {"id": i}
    elif op in ("item-aendern", "item-weg"):
        it = next((x for x in a["gegenstaende"] if x["id"] == int(b["id"])), None)
        if it is None:
            raise Fehler("Gegenstand nicht gefunden")
        if op == "item-weg":
            a["gegenstaende"].remove(it)
        else:
            for k in ("name", "traeger", "ort", "notiz"):
                if k in b:
                    it[k] = str(b[k])[:300]
            if "anzahl" in b:
                it["anzahl"] = max(1, int(b["anzahl"]))
    else:
        raise Fehler("Unbekannte Ausrüstungsaktion")
    return {}
