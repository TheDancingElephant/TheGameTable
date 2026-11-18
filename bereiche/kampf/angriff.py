"""Kampf: Angriff gegen die (verdeckte) RK, Kritische Treffer, Flankieren, Sturmangriff, Rettungswürfe,
Betäubender Schlag, Warnung vor Gelegenheitsangriffen."""
import json
import math
import re

from bereiche import charakter as CH, karte as KA
from bereiche.kern import Fehler
from .initiative import darf_handeln, tempo_felder, zug_info
from .zustaende import UNFAEHIG, schaden as schaden_nehmen, unfaehig, zustand_an

RW_NAMEN = {"REF": "Reflex", "WIL": "Willen", "ZAEH": "Zähigkeit"}


def krit_info(krit):
    """'19-20/x2' -> (19, 2); ohne Angabe (20, 2)."""
    k = (krit or "").replace(" ", "").lower()
    m = re.search(r"(\d+)-20", k)
    m2 = re.search(r"[x×](\d)", k)
    return (int(m.group(1)) if m else 20), (int(m2.group(1)) if m2 else 2)


def flankiert(kx, angreifer, ziel):
    """Verbündeter steht auf der gegenüberliegenden Seite des Ziels (vereinfacht für mittelgroße Ziele)."""
    if ziel.get("groesse", 1) != 1 or KA.abstand(angreifer, ziel) > 1:
        return False
    gegenueber = (2 * ziel["x"] - angreifer["x"], 2 * ziel["y"] - angreifer["y"])
    for t in kx.z["tokens"].values():
        if (t is not angreifer and t["art"] == angreifer["art"] and t.get("karte") == ziel.get("karte")
                and gegenueber in KA.token_felder(t) and not unfaehig(t)):
            return True
    return False


def ziel_rk(kx, ziel, beruehrung):
    """RK des Ziels: normal, Berührung, auf dem falschen Fuß (auch bei Hilflosigkeit u. ä.)."""
    zs = ziel.get("zustaende", [])
    if ziel["art"] == "sc":
        rk = (CH.von_token(kx, ziel) or {}).get("rk", {})
        normal, ber, ff = rk.get("normal"), rk.get("beruehrung"), rk.get("adff")
    else:
        normal, ber, ff = ziel.get("rk"), ziel.get("rkBeruehrung"), ziel.get("rkAdff")
    if beruehrung:
        return ber if ber is not None else normal
    if ("Auf dem falschen Fuß" in zs or set(zs) & set(UNFAEHIG)) and ff is not None:
        return ff
    return normal


def ga_bonus(kx, ziel, art):
    """RK-Boni des Ziels gegen einen Gelegenheitsangriff: Talent Beweglichkeit (+4, nur wenn der GA durch Bewegung
    provoziert wurde) und Modus-Wirkung `rkga`. Beides sind Ausweichboni und entfallen, wenn das Ziel auf dem
    falschen Fuß oder hilflos ist (GRW: Talente, Beweglichkeit). Gibt [(Text, Wert)] zurück."""
    zs = set(ziel.get("zustaende", []))
    if "Auf dem falschen Fuß" in zs or zs & set(UNFAEHIG):
        return []
    if ziel["art"] == "sc":
        c = CH.von_token(kx, ziel) or {}
        talente, summe = c.get("talente"), (c.get("_wirkung") or {}).get("summe", {})
    else:
        talente, summe = ziel.get("talente"), CH.MODI.summe(CH.MODI.aktive(ziel))
    text = (talente if isinstance(talente, str) else json.dumps(talente or "", ensure_ascii=False)).lower()
    teile = []
    if art == "bewegung" and re.search(r"\bbeweglichkeit\b", text):
        teile.append(("Beweglichkeit", 4))
    if summe.get("rkga"):
        teile.append(("Modus gegen GA", int(summe["rkga"])))
    return teile


def aufloesen(kx, wer, ziel, waffe, bonus, schaden, krit, beruehrung, nahkampf, mods, gelegenheitsangriff=None):
    """Würfelt einen Angriff gegen die (verdeckte) RK, inkl. Kritischem Treffer, und zieht Schaden ab.
    gelegenheitsangriff: None (normaler Angriff), "bewegung"/True (GA durch Bewegung: Beweglichkeit zählt) oder
    "andere" (GA aus anderem Grund). Gibt True/False (Treffer) zurück, None, wenn keine RK bekannt ist."""
    zs = ziel.get("zustaende", [])
    if "Liegend" in zs:
        mods.append(("Ziel liegt", 4 if nahkampf else -4))
    if nahkampf and set(zs) & set(UNFAEHIG):
        mods.append(("Ziel hilflos", 4))
    summe_mods = sum(v for _, v in mods)
    rk = ziel_rk(kx, ziel, beruehrung)
    rk_extra = []
    if gelegenheitsangriff and rk is not None:
        rk_extra = ga_bonus(kx, ziel, "andere" if gelegenheitsangriff == "andere" else "bewegung")
        rk += sum(v for _, v in rk_extra)
    d20 = kx.w(20)
    gesamt = d20 + bonus + summe_mods
    detail = f"1W20[{d20}] {bonus:+d}" + "".join(f" {v:+d} {t}" for t, v in mods)
    titel = f"{wer} greift {ziel['name']} an ({'Gelegenheitsangriff, ' if gelegenheitsangriff else ''}{waffe})"
    besonders = "nat20" if d20 == 20 else "nat1" if d20 == 1 else None
    if rk is None:  # keine RK hinterlegt: der SL wertet aus
        kx.protokoll("angriff", titel, wer=wer, ergebnis=gesamt, detail=detail, besonders=besonders,
                     treffer=None, schadenAusdruck=schaden, wecken=True)
        kx.z["slStatus"] = "wartet"
        return None
    treffer = d20 == 20 or (d20 != 1 and gesamt >= rk)
    bereich, mult = krit_info(krit)
    kritisch, bestaetigung = False, None
    if treffer and d20 >= bereich:
        b20 = kx.w(20)
        bsum = b20 + bonus + summe_mods
        kritisch = b20 == 20 or (b20 != 1 and bsum >= rk)
        bestaetigung = f"Bestätigung 1W20[{b20}] = {bsum}"
    schaden_summe, sdetail = None, []
    if treffer and schaden:
        schaden_summe = 0
        for _ in range(mult if kritisch else 1):
            s, d, _ = kx.wuerfeln(schaden)
            schaden_summe += s
            sdetail.append(d)
        schaden_summe = max(1, schaden_summe)
        schaden_nehmen(kx, ziel, schaden_summe)
    kx.protokoll("angriff", titel, wer=wer, ergebnis=gesamt, detail=detail, besonders=besonders,
                 treffer=treffer, kritisch=kritisch, bestaetigung=bestaetigung, schaden=schaden_summe,
                 schadenDetail=" + ".join(sdetail), zielId=ziel["id"])
    extra = f" ({', '.join(f'{t} {v:+d}' for t, v in rk_extra)})" if rk_extra else ""
    kx.protokoll("sl-notiz", f"{titel}: {gesamt} gegen RK {rk}{extra} → {'Treffer' if treffer else 'daneben'}"
                 f"{', kritisch' if kritisch else ''}; {ziel['name']} TP {ziel.get('tp')}/{ziel.get('tpMax')}",
                 verborgen=True)
    return treffer


def rettungswurf_bonus(kx, ziel, rw):
    if ziel["art"] == "sc":
        return (CH.von_token(kx, ziel) or {}).get("rw", {}).get(rw)
    return ziel.get({"REF": "ref", "WIL": "wil", "ZAEH": "zaeh"}[rw])


def rettungswurf(kx, t, ziel, d, titel, verdeckt=False):
    """Rettungswurf des Ziels gegen d['sg'] (d['rettungswurf'] = REF/WIL/ZAEH), dann Schaden (ggf. halbiert)
    und Zustand. Ohne bekannten Bonus wertet der SL aus."""
    rw = d["rettungswurf"]
    bonus = rettungswurf_bonus(kx, ziel, rw)
    if bonus is None:
        kx.protokoll("zauber", titel, wer=t["name"], ergebnisText=f"{RW_NAMEN[rw]}-Wurf gegen SG {d['sg']}",
                     detail=f"{d.get('schaden') or ''} {d.get('effekt', '')}".strip(), wecken=True)
        kx.z["slStatus"] = "wartet"
        return
    w = kx.w(20)
    gelungen = w == 20 or (w != 1 and w + int(bonus) >= d["sg"])
    schaden = None
    if d.get("schaden"):
        schaden, _, _ = kx.wuerfeln(d["schaden"])
        if gelungen:
            schaden = schaden // 2 if d.get("beiErfolg") == "halb" else 0
        if schaden:
            schaden_nehmen(kx, ziel, schaden)
    zustand = d.get("zustandBeiErfolg") if gelungen else d.get("zustand")
    zustand_an(ziel, zustand)
    ergebnis = ("widersteht" if gelungen else "erliegt dem Zauber") + (f" – {zustand}" if zustand else "") \
        + (f" – {schaden} Schaden" if schaden else "")
    rw_text = f"{RW_NAMEN[rw]}-Wurf 1W20[{w}]{int(bonus):+d} = {w + int(bonus)}. {d.get('effekt', '')}"
    kx.protokoll("zauber", titel, wer=t["name"], ergebnisText=f"{ziel['name']} {ergebnis}",
                 detail="" if verdeckt else rw_text)
    kx.protokoll("sl-notiz", f"{titel}: SG {d['sg']}, {ziel['name']}: {rw_text}" if verdeckt
                 else f"{titel}: SG {d['sg']}, Wurf {w + int(bonus)}", verborgen=True)


def gelegenheitsangriff_warnung(kx, t):
    """Vor dem Bewegen eines Gegners: welche SC bedrohen sein Feld? (Das Tool warnt nur.)"""
    z = kx.z
    if t["art"] == "sc" or not z["initiative"].get("aktiv"):
        return []
    return [s["name"] for s in z["tokens"].values()
            if s["art"] == "sc" and s.get("karte") == t.get("karte") and KA.abstand(s, t) <= 1 and not unfaehig(s)]


def sl_bewegen(kx, tid, x, y):
    """SL zieht ein Token; Warnung, wenn ein Gegner ein von SC bedrohtes Feld verlässt."""
    t = KA.finden(kx, tid)
    bedroht = gelegenheitsangriff_warnung(kx, t)
    KA.bewegen(kx, t, x, y)
    if bedroht:
        return {"warnung": f"Gelegenheitsangriff möglich für: {', '.join(bedroht)} ({t['name']} verließ ein bedrohtes Feld)"}
    return {}


def sl_angriff(kx, b):
    """Angriff eines Gegners/NSC, ohne Regelprüfung (der SL entscheidet); Modi des Angreifers zählen mit.
    b["gelegenheitsangriff"]: "bewegung" (Beweglichkeit des Ziels zählt) oder "andere"."""
    a = KA.finden(kx, b["angreifer"])
    ziel = KA.finden(kx, b["ziel"])
    fern = b.get("fernkampf", False)
    mods = [(t, int(v)) for t, v in b.get("mods", [])]
    if kx.einst.get("modi", True) and not a.get("charId"):
        mods += CH.MODI.token_angriff_mods(a, fern)
    aufloesen(kx, a["name"], ziel, b.get("waffe", "Angriff"), int(b["bonus"]), b.get("schaden"),
              b.get("krit"), b.get("beruehrung", False), not fern, mods, b.get("gelegenheitsangriff"))


def _serie(a):
    """Einträge eines (Voll-)Angriffs: Zahl (nur Bonus) oder {"bonus", "schaden", "name"} je Angriff."""
    serie = a.get("serie")
    return [x if isinstance(x, dict) else {"bonus": int(x)} for x in serie] if serie else [{"bonus": int(a.get("bonus") or 0)}]


def _angreifer_und_ziel(kx, b):
    t = KA.finden(kx, b["id"])
    ziel = KA.finden(kx, b["ziel"])
    if t["art"] != "sc" or ziel["art"] == "sc":
        raise Fehler("Angreifen können nur eure Charaktere – und zwar Gegner")
    if not KA.sichtbar(ziel, KA.offen(KA.aktive(kx))):
        raise Fehler("Ziel nicht sichtbar")
    return t, ziel


def sc_angriff(kx, b):
    """Spieler greift mit einem Angriff seines SC an (Einzelangriff oder Vollangriff/Serie)."""
    z = kx.z
    t, ziel = _angreifer_und_ziel(kx, b)
    k = KA.aktive(kx)
    ini = z["initiative"]
    c = CH.von_token(kx, t) or {}
    a = c.get("angriffe", [])[int(b["angriff"])]
    serie = a.get("serie")
    if ini.get("aktiv"):
        darf_handeln(kx, t)
        zi = zug_info(kx)
        if serie:
            if not (zi["standardFrei"] and zi["bewegungFrei"]) or z["zug"]["bewegt"] > 1:
                raise Fehler("Ein Vollangriff braucht Standard- und Bewegungsaktion (nur ein 1,5-m-Schritt davor erlaubt)")
        elif not zi["standardFrei"]:
            raise Fehler("Keine Standard-Aktion mehr frei")
    elif z.get("angriffAusserhalb"):
        raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
    if unfaehig(t):
        raise Fehler(f"{t['name']} kann nicht handeln")
    info = CH.waffe_info(a)
    d = KA.abstand(t, ziel)
    mods = []
    if info["fernkampf"]:
        n = max(1, math.ceil(d * k.get("meterProFeld", 1.5) / info["inkrement"]))
        if n > 10:
            raise Fehler(f"{ziel['name']} ist außer Reichweite")
        if n > 1:
            mods.append(("Entfernung", -2 * (n - 1)))
        if any(s["art"] == "sc" and s is not t and s.get("karte") == ziel.get("karte") and KA.abstand(s, ziel) <= 1
               for s in z["tokens"].values()):
            mods.append(("in den Nahkampf", -4))
    else:
        reichweite = KA.reichweite_felder(t)
        if d > reichweite:
            raise Fehler(f"{ziel['name']} steht nicht neben {t['name']}" if reichweite == 1
                         else f"{ziel['name']} ist außerhalb der Reichweite von {t['name']} "
                              f"({reichweite * CH.meter_pro_feld(kx):g} m)")
        if flankiert(kx, t, ziel):
            mods.append(("Flankieren", 2))
    eintraege = _serie(a)
    # Betäubender Schlag je Angriff: am Eintrag der Serie ("betaeubend": SG oder false), sonst Wert der Waffe
    stuns = [e["betaeubend"] if "betaeubend" in e else a.get("betaeubend") for e in eintraege]
    anzahl = sum(1 for x in stuns if x)
    if anzahl:
        pool = c.setdefault("betaeubendPool", {"max": 5, "verbraucht": 0})
        if pool["max"] - pool["verbraucht"] < anzahl:
            raise Fehler(f"Betäubender Schlag: nur noch {pool['max'] - pool['verbraucht']} Anwendung(en) heute, "
                         f"dieser Angriff braucht {anzahl}")
        pool["verbraucht"] += anzahl
        CH.speichern(kx, c)
    for i, e in enumerate(eintraege):
        name = e.get("name") or (a.get("name", "Angriff") + (f" ({i + 1}. Schlag)" if serie else ""))
        if stuns[i]:
            name += " · Betäubender Schlag"
        treffer = aufloesen(kx, t["name"], ziel, name, int(e["bonus"]), e.get("schaden") or a.get("schaden"),
                            a.get("krit"), info["beruehrung"], not info["fernkampf"], list(mods))
        if stuns[i] and treffer:
            _betaeubend(kx, ziel, int(stuns[i]))
    if ini.get("aktiv"):
        z["zug"]["standard"] = True
        if serie:
            z["zug"]["bewegung"] = True
    else:
        z["angriffAusserhalb"] = True
        kx.protokoll("zugende", f"{t['name']} greift überraschend an – der Kampf beginnt!", wecken=True)
        z["slStatus"] = "wartet"


def _betaeubend(kx, ziel, sg):
    """Betäubender Schlag getroffen: Zähigkeitswurf, sonst Betäubt (und Erschöpft, wie im Tool üblich)."""
    bonus_rw = rettungswurf_bonus(kx, ziel, "ZAEH")
    if bonus_rw is None:
        kx.protokoll("sl-notiz", f"Betäubender Schlag trifft {ziel['name']}: ZÄH SG {sg}, der SL wertet aus",
                     verborgen=True, wecken=True)
        kx.z["slStatus"] = "wartet"
        return
    w20 = kx.w(20)
    erg = w20 + int(bonus_rw)
    geschafft = erg >= sg
    kx.protokoll("zauber", f"{ziel['name']}: Zähigkeitswurf gegen Betäubenden Schlag (SG {sg})",
                 wer=ziel["name"], ergebnis=erg, ergebnisText="widersteht" if geschafft else "betäubt",
                 detail=f"1W20[{w20}] {int(bonus_rw):+d} gegen SG {sg}")
    if not geschafft:
        for zn in ("Betäubt", "Erschöpft"):
            zustand_an(ziel, zn)


def sturmangriff_feld(kx, t, ziel):
    """Landefeld für einen Sturmangriff: angrenzend ans Ziel, mindestens 2 Felder (3 m) und höchstens das
    Doppelte der Bewegungsrate entfernt, auf freiem, aufgedecktem Boden, ohne Umweg. Gibt (x, y, weg) zurück."""
    z = kx.z
    k = KA.aktive(kx)
    offen = KA.offen(k)
    tempo = tempo_felder(kx, t)
    g = t.get("groesse", 1)
    start = (t["x"], t["y"])
    wand = k.get("waendeSperren") and t.get("karte", z["karteAktiv"]) == z["karteAktiv"]
    besetzt = KA.belegt(kx, t)
    besser = None
    gz = ziel.get("groesse", 1)
    for x in range(ziel["x"] - g, ziel["x"] + gz + 1):
        for y in range(ziel["y"] - g, ziel["y"] + gz + 1):
            probe = {"x": x, "y": y, "groesse": g}
            felder = KA.token_felder(probe)
            if KA.abstand(probe, ziel) > 1 or any(f in besetzt for f in felder):
                continue
            if KA.abstand(probe, ziel) == 0 or any(f not in offen for f in felder):
                continue
            luft = KA.pf_distanz(start[0], start[1], x, y)
            if luft < 2 or luft > 2 * tempo:
                continue
            weg = luft
            if wand:
                weg = KA.weg(kx, k, start, (x, y), erlaubt=offen)
                if weg is None or weg > luft * 1.25 + 1:
                    continue
            if weg > 2 * tempo:
                continue
            if besser is None or (weg, luft) < (besser[2], besser[3]):
                besser = (x, y, weg, luft)
    if besser is None:
        raise Fehler("Sturmangriff nicht möglich: kein freies Feld neben dem Ziel in gerader Linie, mindestens 3 m und "
                     f"höchstens {2 * tempo * 1.5:g} m entfernt")
    return besser[0], besser[1], besser[2]


def sturmangriff(kx, b):
    """Spieler: Sturmangriff (volle Aktion, +2 Angriff, −2 RK bis zum nächsten Zug; Anspringen erlaubt Vollangriff)."""
    z = kx.z
    t, ziel = _angreifer_und_ziel(kx, b)
    k = KA.aktive(kx)
    if not z["initiative"].get("aktiv"):
        raise Fehler("Einen Sturmangriff gibt es nur im Kampf")
    darf_handeln(kx, t)
    info = zug_info(kx)
    if not (info["standardFrei"] and info["bewegungFrei"]) or z["zug"]["bewegt"] > 0:
        raise Fehler("Für den Sturmangriff werden Standard- und Bewegungsaktion gebraucht (volle Aktion, vorher nicht bewegt)")
    if unfaehig(t):
        raise Fehler(f"{t['name']} kann nicht handeln")
    c = CH.von_token(kx, t) or {}
    a = c.get("angriffe", [])[int(b["angriff"])]
    winfo = CH.waffe_info(a)
    anspringen = "anspringen" in json.dumps({k: c.get(k) for k in ("talente", "faehigkeiten", "notizen")},
                                            ensure_ascii=False).lower()
    if a.get("betaeubend"):
        raise Fehler("Für den Sturmangriff bitte den Einzelschlag ohne Betäubenden Schlag wählen")
    if a.get("serie") and not anspringen:
        raise Fehler("Ein Vollangriff beim Sturmangriff geht nur mit Anspringen (Pounce)")
    if winfo["fernkampf"] or winfo["beruehrung"]:
        raise Fehler("Ein Sturmangriff geht nur mit einer Nahkampfwaffe")
    x, y, weg = sturmangriff_feld(kx, t, ziel)
    alt = (t["x"], t["y"])
    t["x"], t["y"] = x, y
    z["zug"]["bewegt"] = weg
    z["zug"]["bewegung"] = True
    meter = weg * (k.get("meterProFeld", 1.5) if k else 1.5)
    kx.protokoll("bewegung", f"{t['name']} stürmt {weg} Felder ({meter:g} m) nach ({x},{y}) – Sturmangriff auf {ziel['name']}",
                 wer=t["name"], von=list(alt), nach=[x, y])
    mods = [("Sturmangriff", 2)]
    if flankiert(kx, t, ziel):
        mods.append(("Flankieren", 2))
    serie = a.get("serie")
    for i, e in enumerate(_serie(a)):
        name = e.get("name") or (a.get("name", "Angriff") + (f" ({i + 1}. Angriff)" if serie else ""))
        aufloesen(kx, t["name"], ziel, f"{name} · Sturmangriff" + (" (Anspringen)" if serie else ""), int(e["bonus"]),
                  e.get("schaden") or a.get("schaden"), a.get("krit"), False, True, list(mods))
    z["zug"]["standard"] = True
    kx.protokoll("system", f"{t['name']}: Sturmangriff – RK −2 bis zum nächsten Zug")
