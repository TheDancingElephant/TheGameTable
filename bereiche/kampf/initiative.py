"""Kampf: Initiative, Runden, Zug und Aktionen (Standard, Bewegung, Schnell), Bewegungsbudget."""
from bereiche import charakter as CH, karte as KA, reaktion
from bereiche.kern import Fehler
from .zustaende import ist_tot, tot_abgleich


def tempo_felder(kx, t):
    """Bewegungsrate in Feldern (wirksame Bewegung des Charakters, Standard 9 m)."""
    c = CH.von_token(kx, t) or {}
    k = KA.aktive(kx)
    return int((c.get("bewegung") or 9) // ((k or {}).get("meterProFeld", 1.5)))


def bewegungsbedarf(felder, tempo):
    """Wie viele Bewegungsaktionen kostet eine Strecke? 1 Feld = 1,5-m-Schritt (kostet keine)."""
    if felder <= 1:
        return 0
    return 1 if felder <= tempo else 2 if felder <= 2 * tempo else 3


def zug_info(kx):
    """Zug des aktuellen Initiative-Eintrags; für SC mit freien Aktionen und restlichen Feldern."""
    z = kx.z
    zug = z.get("zug")
    if not zug or not z["initiative"].get("aktiv"):
        return None
    t = z["tokens"].get(zug.get("tokenId") or "")
    eintrag = next((e for e in z["initiative"]["eintraege"] if e["name"] == zug["name"]), {})
    info = {"tokenId": zug.get("tokenId"), "name": "???" if eintrag.get("verborgen") else zug["name"],
            "art": t["art"] if t else "gegner"}
    if t and t["art"] == "sc":
        tempo = tempo_felder(kx, t)
        n = bewegungsbedarf(zug["bewegt"], tempo) + (1 if zug["bewegung"] else 0)
        aktionen = (0 if zug["bewegung"] else 1) + (0 if zug["standard"] else 1)
        grenze = max(tempo * aktionen, 1 if zug["bewegt"] == 0 else 0)
        info.update({
            "standardFrei": not zug["standard"] and n <= 1,
            "bewegungFrei": n == 0,
            "schnellFrei": not zug["schnell"],
            "tempo": tempo, "bewegt": zug["bewegt"], "restFelder": max(0, grenze - zug["bewegt"]),
        })
    return info


def aktion_frei(kx, aktion):
    """Ist die Aktion (standard, bewegung, schnell, voll, keine) im laufenden Zug noch frei?"""
    if aktion == "keine":
        return True
    info = zug_info(kx)
    if aktion == "voll":
        return info["standardFrei"] and info["bewegungFrei"]
    return {"schnell": info["schnellFrei"], "bewegung": info["bewegungFrei"]}.get(aktion, info["standardFrei"])


def aktion_verbrauchen(kx, aktion):
    """Zauber: verbraucht die Aktion im Zug (schnell; sonst Standard, voll = Standard + Bewegung)."""
    zug = kx.z["zug"]
    if aktion == "schnell":
        zug["schnell"] = True
    else:
        zug["standard"] = True
        if aktion == "voll":
            zug["bewegung"] = True


def zug_starten(kx):
    z = kx.z
    ini = z["initiative"]
    if not ini["eintraege"]:
        z["zug"] = None
        return
    e = ini["eintraege"][ini["index"]]
    z["zug"] = {"tokenId": e.get("tokenId"), "name": e["name"], "bewegt": 0,
                "standard": False, "bewegung": False, "schnell": False}
    kx.protokoll("system", f"Runde {ini['runde']}: {'Ein unbekannter Gegner' if e.get('verborgen') else e['name']} ist am Zug")


def weiter(kx):
    """Nächster Eintrag (tote Gegner/NSC werden übersprungen); neue Runde meldet `runde_vorbei`."""
    z = kx.z
    ini = z["initiative"]
    if not ini["eintraege"]:
        return
    tot_abgleich(z)
    n = len(ini["eintraege"])
    for _ in range(n):  # höchstens eine volle Runde
        ini["index"] += 1
        if ini["index"] >= n:
            ini["index"] = 0
            ini["runde"] += 1
            kx.ereignis("runde_vorbei", runden=1)
        if not ist_tot(z, ini["eintraege"][ini["index"]]):
            break
    zug_starten(kx)


def darf_handeln(kx, t):
    """Im Kampf darf nur der aktive Charakter handeln – und nur, wenn der SL nicht gerade dran ist."""
    z = kx.z
    ini = z["initiative"]
    if not ini.get("aktiv"):
        return
    if ini.get("phase") != "laeuft":
        raise Fehler("Erst Initiative würfeln – der Kampf beginnt gleich")
    if z["slStatus"] != "bereit":
        raise Fehler("Der Spielleiter ist gerade am Zug – bitte warten")
    zug = z.get("zug") or {}
    if zug.get("tokenId") != t["id"]:
        raise Fehler(f"{t['name']} ist nicht am Zug")


def entfernen(ini, weg):
    """Entfernt Initiative-Einträge, ohne den Zeiger auf den aktuellen Zug zu verschieben:
    wer vor dem aktuellen Eintrag entfernt wird, lässt den Index mitwandern."""
    idx = ini.get("index", 0)
    neu, neuer_index, gesetzt = [], 0, False
    for i, e in enumerate(ini["eintraege"]):
        if weg(e):
            continue
        if i >= idx and not gesetzt:
            neuer_index, gesetzt = len(neu), True
        neu.append(e)
    ini["eintraege"] = neu
    ini["index"] = neuer_index if gesetzt else 0


@reaktion("token_entfernt")
def _token_entfernt(kx, token_id):
    entfernen(kx.z["initiative"], lambda e: e.get("tokenId") == token_id)


def sortieren(ini):
    aktuell = ini["eintraege"][ini["index"]]["name"] if ini["eintraege"] and ini["index"] < len(ini["eintraege"]) else None
    ini["eintraege"].sort(key=lambda e: -float(e["wert"]))
    if aktuell and ini.get("phase") == "laeuft":
        ini["index"] = next(i for i, e in enumerate(ini["eintraege"]) if e["name"] == aktuell)


def befehl(kx, b):
    """SL-Befehl initiative: start, los, eintrag, entfernen, aufdecken, weiter, ende."""
    z = kx.z
    ini = z["initiative"]
    aktion = b["aktion"]
    if aktion == "start":
        ini.update({"aktiv": True, "phase": "wuerfeln", "runde": 0, "index": 0, "eintraege": []})
        z["zug"] = None
        z["angriffAusserhalb"] = False
        kx.protokoll("system", "Kampf! Würfelt Initiative.")
    elif aktion == "los":  # alle haben gewürfelt: erster Zug beginnt
        sortieren(ini)
        ini.update({"phase": "laeuft", "runde": 1, "index": 0})
        zug_starten(kx)
    elif aktion == "eintrag":
        entfernen(ini, lambda e: e["name"] == b["name"])
        wert = float(b["wert"])
        ini["eintraege"].append({"name": b["name"], "wert": int(wert) if wert.is_integer() else wert,
                                 "tokenId": b.get("tokenId"), "verborgen": b.get("verborgen", False)})
        sortieren(ini)
    elif aktion == "entfernen":
        entfernen(ini, lambda e: e["name"] == b["name"])
    elif aktion == "aufdecken":
        for e in ini["eintraege"]:
            if e["name"] == b["name"]:
                e["verborgen"] = False
    elif aktion == "weiter":
        weiter(kx)
    elif aktion == "ende":
        ini.update({"aktiv": False, "phase": None, "runde": 0, "index": 0, "eintraege": []})
        z["zug"] = None
        z["angriffAusserhalb"] = False
        kx.protokoll("system", "Der Kampf ist vorbei.")


def zug_aendern(kx, werte):
    """SL: Aktionen des aktuellen Zuges anpassen."""
    if not kx.z.get("zug"):
        raise Fehler("Kein Zug aktiv")
    for key, wert in werte.items():
        kx.z["zug"][key] = wert


def wurf_initiative(kx, wer, char_id, summe):
    """Spieler hat Initiative gewürfelt: Eintrag setzen; wenn alle SC der Karte da sind, SL wecken."""
    z = kx.z
    ini = z["initiative"]
    t = CH.sc_token(kx, char_id) if char_id else None
    befehl(kx, {"aktion": "eintrag", "name": wer, "wert": summe, "tokenId": t["id"] if t else None})
    namen = {e["name"] for e in ini["eintraege"]}
    fehlend = [t["name"] for t in z["tokens"].values()
               if t["art"] == "sc" and t.get("karte") == z["karteAktiv"] and t["name"] not in namen]
    if ini.get("phase") == "wuerfeln" and not fehlend:
        kx.protokoll("zugende", "Alle Charaktere haben Initiative gewürfelt.", wecken=True)
        z["slStatus"] = "wartet"


def zug_beenden(kx, tid):
    t = KA.finden(kx, tid)
    darf_handeln(kx, t)
    if not kx.z["initiative"].get("aktiv"):
        raise Fehler("Kein Kampf")
    kx.protokoll("zugende", f"{t['name']} beendet den Zug.", wer=t["name"], wecken=True)
    weiter(kx)
    kx.z["slStatus"] = "wartet"


def aktion_nutzen(kx, tid, aktion, wofuer=None):
    """Spieler: eine Aktion ohne Wirkung im Tool verbrauchen (z. B. Trank trinken)."""
    t = KA.finden(kx, tid)
    darf_handeln(kx, t)
    if not kx.z["initiative"].get("aktiv"):
        raise Fehler("Kein Kampf")
    info = zug_info(kx)
    frei = {"standard": info["standardFrei"], "bewegung": info["bewegungFrei"], "schnell": info["schnellFrei"]}
    if not frei.get(aktion):
        raise Fehler("Diese Aktion ist schon verbraucht")
    kx.z["zug"][aktion] = True
    name = {"standard": "Standard-Aktion", "bewegung": "Bewegungsaktion", "schnell": "Schnelle Aktion"}[aktion]
    kx.protokoll("system", f"{t['name']} nutzt die {name}{': ' + wofuer if wofuer else ''}")


def bewegen_spieler(kx, tid, x, y):
    """Spieler bewegt seinen SC: Wände/unerforschtes Gebiet, im Kampf Bewegungsbudget; außerhalb weckt es den SL."""
    z = kx.z
    t = KA.finden(kx, tid)
    if t["art"] != "sc":
        raise Fehler("Nur eigene Charaktere können bewegt werden")
    alt = (t["x"], t["y"])
    felder = KA.pf_distanz(*alt, int(x), int(y))
    k = KA.aktive(kx)
    if k and k.get("waendeSperren") and t.get("karte", z["karteAktiv"]) == z["karteAktiv"]:
        weg = KA.weg(kx, k, alt, (int(x), int(y)), erlaubt=KA.offen(k))
        if weg is None or weg > felder * 1.5 + 2:
            raise Fehler("Dort geht es nicht direkt hin: eine Wand oder unerforschtes Gebiet ist im Weg. "
                         "Zieht Schritt für Schritt um die Ecke.")
        felder = max(felder, weg)
    if z["initiative"].get("aktiv"):
        darf_handeln(kx, t)
        info = zug_info(kx)
        if felder > info["restFelder"]:
            raise Fehler(f"Zu weit: {t['name']} kann noch {info['restFelder']} Felder gehen")
        z["zug"]["bewegt"] += felder
    KA.bewegen(kx, t, x, y)
    meter = felder * (k.get("meterProFeld", 1.5) if k else 1.5)
    # Außerhalb eines Kampfes weckt Bewegung den SL (der Nachlauf von `warte` sammelt mehrere Züge ein)
    wecken = not z["initiative"].get("aktiv")
    kx.protokoll("bewegung", f"{t['name']} bewegt sich {felder} Felder ({meter:g} m) nach ({t['x']},{t['y']})",
                 wer=t["name"], von=list(alt), nach=[t["x"], t["y"]], wecken=wecken)
    if wecken:
        z["slStatus"] = "wartet"
