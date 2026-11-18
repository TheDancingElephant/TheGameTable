"""Bereich Tisch: Szene, Erzählung, Protokoll, SL-Status und Wecken (`warte`), Handouts, Gruppennotizen, freie Würfe,
Sichten (was Spieler bzw. SL sehen).

Öffentlich: erzaehlen, notiz, status, szene, handout, handout_weg, eintrag_loeschen, verarbeitet, sl_wurf,
spieler_aktion, spieler_wurf, anstupsen, zeigen, gruppennotizen, weckende_ereignisse, spieler_sicht, sl_sicht,
unterlagen, charaktere_ansicht.
"""
from bereiche import besitz as BE, charakter as CH, kampf as KM, karte as KA, magie as MA
from bereiche.kern import Fehler

# ---------------------------------------------------------------- Erzählung und Status


def erzaehlen(kx, text, titel=None):
    kx.protokoll("sl", text, titel=titel)
    kx.z["slStatus"] = "bereit"


def notiz(kx, text):
    """SL-Notiz: nur im SL-Protokoll."""
    kx.protokoll("sl-notiz", text, verborgen=True)


def status(kx, wert):
    kx.z["slStatus"] = wert


def szene(kx, titel="", untertitel=""):
    kx.z["szene"] = {"titel": titel, "untertitel": untertitel}
    kx.protokoll("system", f"Szene: {titel}")


def handout(kx, hid, text, titel=None):
    """Text-Handout anlegen oder ersetzen (gleiche id)."""
    hs = kx.z.setdefault("handouts", [])
    h = {"id": hid, "titel": titel or hid, "text": text}
    alt = next((i for i, x in enumerate(hs) if x["id"] == hid), None)
    if alt is None:
        hs.append(h)
        kx.protokoll("system", f"Neue Unterlage: {h['titel']}")
    else:
        hs[alt] = h


def handout_weg(kx, hid):
    kx.z["handouts"] = [x for x in kx.z.get("handouts", []) if x["id"] != hid]


def eintrag_loeschen(kx, eid):
    kx.log[:] = [e for e in kx.log if e["id"] != int(eid)]
    kx.log_neu_schreiben = True


def verarbeitet(kx, bis):
    kx.z["letzteVerarbeitet"] = int(bis)


def sl_wurf(kx, ausdruck, grund="", wer="SL", verborgen=False):
    summe, detail, besonders = kx.wuerfeln(ausdruck)
    kx.protokoll("wurf", grund, wer=wer, ausdruck=ausdruck, ergebnis=summe, detail=detail, besonders=besonders,
                 verborgen=verborgen)
    return {"ergebnis": summe, "detail": detail, "besonders": besonders}


def weckende_ereignisse(kx):
    """Gibt es unverarbeitete Ereignisse, die den SL wecken (Spieleraktion, Zugende …)?"""
    lv = kx.z["letzteVerarbeitet"]
    for e in reversed(kx.log):
        if e["id"] <= lv:
            return False
        if e.get("wecken", e["art"] == "spieler"):
            return True
    return False


# ---------------------------------------------------------------- Spieler


def spieler_aktion(kx, text, wer=None):
    """Ansage der Spieler; im laufenden Kampf Teil des Zuges (der SL liest sie am Zugende), sonst weckt sie den SL."""
    text = (text or "").strip()
    if not text:
        raise Fehler("Leere Aktion")
    ini = kx.z["initiative"]
    im_zug = ini.get("aktiv") and ini.get("phase") == "laeuft"
    kx.protokoll("spieler", text, wer=wer or "Gruppe", wecken=not im_zug)
    if not im_zug:
        kx.z["slStatus"] = "wartet"


def spieler_wurf(kx, b):
    """Probe eines Spielers; Initiative-Würfe tragen sich in die Initiative ein."""
    z = kx.z
    ini = z["initiative"]
    if b.get("initiative") and ini["aktiv"] and any(e["name"] == b.get("wer") for e in ini["eintraege"]):
        raise Fehler(f"{b.get('wer')} hat schon Initiative gewürfelt")
    summe, detail, besonders = kx.wuerfeln(b["ausdruck"])
    # Proben außerhalb eines Kampfes wecken den SL (der Nachlauf von `warte` sammelt mehrere Würfe ein)
    wecken = not ini.get("aktiv")
    e = kx.protokoll("wurf", b.get("grund", ""), wer=b.get("wer") or "Gruppe", ausdruck=b["ausdruck"],
                     ergebnis=summe, detail=detail, besonders=besonders, wecken=wecken)
    if wecken:
        z["slStatus"] = "wartet"
    if b.get("initiative") and ini["aktiv"]:
        KM.wurf_initiative(kx, b.get("wer"), b.get("charId"), summe)
    return {"ergebnis": summe, "detail": detail, "besonders": besonders, "id": e["id"]}


def anstupsen(kx):
    """Spieler bitten den Spielleiter, zu handeln (weckt `warte`)."""
    kx.protokoll("system", "Die Spieler bitten den Spielleiter zu handeln.", wecken=True)
    if kx.z["slStatus"] == "bereit":
        kx.z["slStatus"] = "wartet"


def zeigen(kx, x, y, wer=None):
    kx.protokoll("zeigen", f"{wer or 'Gruppe'} zeigt auf Feld ({x},{y})", wer=wer or "Gruppe", feld=[x, y])


def gruppennotizen(kx, text):
    kx.z["gruppennotizen"] = str(text or "")[:50000]


# ---------------------------------------------------------------- Sichten


def unterlagen(kx):
    """Was die Spieler jederzeit nachschlagen dürfen: bekannte Karten, Handouts, Gruppennotizen."""
    z = kx.z
    karten = [{"id": kid, "name": k["name"], "nebelVersion": k.get("nebelVersion", 0), "w": k["w"], "h": k["h"],
               "aktiv": kid == z["karteAktiv"], "legende": k.get("legende")}
              for kid, k in z["karten"].items() if k.get("bekannt") or kid == z["karteAktiv"]]
    return {"karten": karten, "handouts": z.get("handouts", []), "notizen": z.get("gruppennotizen", "")}


def spieler_sicht(kx):
    """Spielersicht: nur Wahrgenommenes (Token auf aufgedeckten Feldern, Täuschungen, keine Gegner-TP …)."""
    z = kx.z
    k = KA.aktive(kx)
    offen = KA.offen(k) if k else set()
    tokens = []
    faelschungen = {}  # tokenId -> angezeigter Name (für die Initiativliste)
    for t in z["tokens"].values():
        if k is None or t.get("karte") != z["karteAktiv"]:
            continue
        td = KA.taeuschung_fuer(kx, t)
        if td is None:
            if not KA.sichtbar(t, offen):
                continue
            o = {key: t.get(key) for key in ("id", "name", "art", "x", "y", "groesse", "farbe", "zustaende", "charId",
                                             "symbol", "reichweite")}
        else:
            if not td.get("sichtbar") and not KA.sichtbar(t, offen):
                continue
            o = {key: td.get(key, t.get(key)) for key in ("name", "x", "y", "groesse", "farbe", "symbol")}
            o.update({key: t.get(key) for key in ("id", "art", "zustaende", "charId")})  # charId bleibt (Kartenlogik)
            faelschungen[t["id"]] = o["name"]
            if td.get("art") in ("sc", "gegner", "nsc"):
                o["art"] = td["art"]
        if td is not None:
            pass  # keine TP/Gesundheit der echten Gestalt preisgeben
        elif t["art"] == "sc":
            o["tp"], o["tpMax"] = t.get("tp"), t.get("tpMax")
        else:
            o["gesundheit"] = KM.gesundheit_text(t)
        tokens.append(o)
    ini = dict(z["initiative"])
    ini["eintraege"] = [
        {"name": faelschungen.get(e.get("tokenId"), e["name"]), "wert": e["wert"], "tokenId": e.get("tokenId"),
         "aktuell": i == ini["index"]}
        for i, e in enumerate(z["initiative"]["eintraege"])
        if not e.get("verborgen")
    ]
    aktuell = z["initiative"]["eintraege"][ini["index"]] if z["initiative"]["eintraege"] else None
    ini["amZug"] = (aktuell["name"] if aktuell and not aktuell.get("verborgen") else "???") if aktuell else None
    karte = None
    if k:
        karte = {key: k[key] for key in ("id", "name", "w", "h", "zelle", "ox", "oy")}
        karte["meterProFeld"] = k.get("meterProFeld", 1.5)
        karte["nebelVersion"] = k.get("nebelVersion", 0)
        karte["aufgedeckt"] = k.get("aufgedeckt", [])
    return {
        "version": z["version"],
        "kampagne": kx.einst.get("name"),
        "szene": z["szene"],
        "karte": karte,
        "tokens": tokens,
        "initiative": ini,
        "zug": KM.zug_info(kx),
        "angriffAusserhalb": z.get("angriffAusserhalb", False),
        "slStatus": z["slStatus"],
        "protokoll": [e for e in kx.log if not e.get("verborgen")][-300:],
        "zustaende": KM.ZUSTAENDE,
        "unterlagen": unterlagen(kx),
        "ausruestung": BE.ausruestung(kx),
    }


def sl_sicht(kx):
    """SL-Sicht: Spielersicht plus alle Token der aktiven Karte, volle Initiative, ganzes Protokoll."""
    s = spieler_sicht(kx)
    z = kx.z
    k = KA.aktive(kx)
    s["tokens"] = [t for t in z["tokens"].values() if k and t.get("karte") == z["karteAktiv"]]
    s["initiative"] = dict(z["initiative"])
    s["protokoll"] = kx.log[-300:]
    s["karten"] = {kid: {"name": kk["name"]} for kid, kk in z["karten"].items()}
    s["sl"] = True
    return s


def charaktere_ansicht(kx):
    """Alle Charaktere mit wirksamen Werten und berechneten Angaben für die Oberfläche (_d, _ep …)."""
    liste = [CH.wirksam(kx, c) for c in CH.alle(kx)]
    for c in liste:  # Fernkampf/Reichweite ergänzen, wo nicht angegeben
        for a in c.get("angriffe", []):
            info = CH.waffe_info(a)
            a.setdefault("fernkampf", info["fernkampf"])
            if info["inkrement"] and not a.get("inkrement"):
                a["inkrement"] = info["inkrement"]
            a["beruehrung"] = info["beruehrung"]
        MA.ansicht(kx, c)
        c["_ep"] = CH.ep_info(kx, c)
    return liste
