"""Karte: Token finden, setzen, bewegen, Größe; Sichtbarkeit für Spieler; Täuschungen (Illusionsansicht)."""
from bereiche import charakter as CH, reaktion
from bereiche.kern import Fehler
from .geometrie import token_felder


def aktive(kx, kid=None):
    """Karte nach ID (Standard: aktive Karte) oder None."""
    kid = kid or kx.z["karteAktiv"]
    return kx.z["karten"].get(kid) if kid else None


def offen(k):
    """Aufgedeckte Felder einer Karte als Menge."""
    return {tuple(c) for c in (k or {}).get("aufgedeckt", [])}


def sichtbar(t, offene_felder):
    """Sehen die Spieler dieses Token? SC immer; andere nur sichtbar gesetzt und auf aufgedecktem Feld."""
    if t["art"] == "sc":
        return True
    if not t.get("sichtbar", True):
        return False
    return (t["x"], t["y"]) in offene_felder


def finden(kx, tid):
    """Token nach ID oder Name (ohne Groß/Klein)."""
    t = kx.z["tokens"].get(tid)
    if not t:
        for kandidat in kx.z["tokens"].values():
            if kandidat["name"].lower() == str(tid).lower():
                return kandidat
        raise Fehler(f"Token {tid!r} nicht gefunden")
    return t


def neue_id(praefix, vorhanden):
    i = 1
    while f"{praefix}{i}" in vorhanden:
        i += 1
    return f"{praefix}{i}"


def sicht_partner(kx, t):
    """Geteilte Sicht: SC-Token, dessen Sicht `t` zusätzlich nutzt (Feld `sichtVon` = Charakter-ID, am Token oder
    in den Charakterdaten; Vereinigung mit der eigenen Sicht). Ohne Feld: None (jeder sieht für sich)."""
    if t.get("art") != "sc":
        return None
    cid = t.get("sichtVon")
    if not cid and t.get("charId"):
        try:
            cid = CH.laden(kx, t["charId"]).get("sichtVon")
        except Fehler:
            cid = None
    if not cid or cid == t.get("charId"):
        return None
    p = CH.sc_token(kx, cid)
    if p is None or p.get("karte") != t.get("karte"):
        return None
    return p


def mit_sichtpartnern(kx, tokens):
    """Erweitert eine Tokenliste um die Sichtpartner (ohne Doppelte)."""
    ids = {t["id"] for t in tokens}
    out = list(tokens)
    for t in tokens:
        p = sicht_partner(kx, t)
        if p and p["id"] not in ids:
            ids.add(p["id"])
            out.append(p)
    return out


def taeuschung_fuer(kx, t):
    """Illusionsansicht: Eintrag aus t['taeuschung'] für den SC, der gerade in der Initiative dran ist.
    Nur im Kampf, nur wenn global nicht abgeschaltet, nie für den aktiven Token selbst. Sonst None."""
    z = kx.z
    td = t.get("taeuschung")
    if not td or z.get("taeuschungAus"):
        return None
    ini = z["initiative"]
    if not ini.get("aktiv") or ini.get("phase") == "wuerfeln" or not z.get("zug"):
        return None
    akt = z["tokens"].get(z["zug"].get("tokenId") or "")
    if not akt or akt["art"] != "sc" or akt["id"] == t["id"]:
        return None
    r = td.get(akt.get("charId") or "")
    if r is None:  # geteilte Sicht: Golem o. ä. sieht, was sein Sichtpartner sieht (eigener Eintrag hat Vorrang)
        p = sicht_partner(kx, akt)
        if p:
            r = td.get(p.get("charId") or "")
    return r


def belegt(kx, t):
    """Felder, die andere Token auf derselben Karte belegen."""
    return {f for s in kx.z["tokens"].values() if s is not t and s.get("karte") == t.get("karte")
            for f in token_felder(s)}


def umgroessern(kx, t, g):
    """Setzt die Tokengröße; beim Wachsen wird ein freier Platz in der Nähe gesucht. Gibt einen Hinweis zurück oder None."""
    alt = t.get("groesse", 1)
    if g <= alt:
        t["groesse"] = g
        return None
    besetzt = belegt(kx, t)
    wachs = g - alt
    kandidaten = sorted(((dx, dy) for dx in range(-wachs, 1) for dy in range(-wachs, 1)),
                        key=lambda d: (abs(d[0]) + abs(d[1]), d))
    for dx, dy in kandidaten:
        x, y = t["x"] + dx, t["y"] + dy
        if x < 0 or y < 0:
            continue
        if not any(f in besetzt for f in token_felder({"x": x, "y": y, "groesse": g})):
            t.update({"x": x, "y": y, "groesse": g})
            return None
    t["groesse"] = g
    return f"{t['name']} wächst, aber es ist zu eng – das Token überlappt andere"


def modi_token_sync(kx, t, c):
    """Überträgt Größe/Reichweite der wirksamen Charakterdaten c auf das Token t."""
    w = (c or {}).get("_wirkung") or {}
    g_neu, reich, hinweis = w.get("tokenGroesse"), w.get("reichweite"), None
    if g_neu or reich:
        t.setdefault("modiToken", {"groesse": t.get("groesse", 1)})
        ziel = g_neu or t["modiToken"]["groesse"]
        if ziel != t.get("groesse", 1):
            hinweis = umgroessern(kx, t, ziel)
        if reich:
            t["reichweite"] = reich
        else:
            t.pop("reichweite", None)
    elif "modiToken" in t:
        basis = t.pop("modiToken")["groesse"]
        if basis != t.get("groesse", 1):
            hinweis = umgroessern(kx, t, basis)
        t.pop("reichweite", None)
    return hinweis


@reaktion("charakter_modi")
def _modi_tokens(kx, cid, eff):
    hinweise = [h for t in kx.z["tokens"].values() if t.get("charId") == cid if (h := modi_token_sync(kx, t, eff))]
    return "; ".join(hinweise) or None


@reaktion("token_groesse")
def _token_groesse(kx, token, groesse):
    return umgroessern(kx, token, groesse)


def setzen(kx, token):
    """Neues Token (SL): Standardwerte ergänzen, ID vergeben."""
    z = kx.z
    t = dict(token)
    t.setdefault("id", neue_id({"gegner": "g", "nsc": "n", "objekt": "o", "sc": "sc"}.get(t.get("art", "gegner"), "t"),
                               z["tokens"]))
    t.setdefault("art", "gegner")
    t.setdefault("groesse", 1)
    t.setdefault("zustaende", [])
    t.setdefault("sichtbar", True)
    t.setdefault("karte", z["karteAktiv"])
    if "tpMax" in t:
        t.setdefault("tp", t["tpMax"])
    z["tokens"][t["id"]] = t
    return {"id": t["id"]}


def aendern(kx, tid, werte):
    t = finden(kx, tid)
    for key, wert in werte.items():
        if wert is None:
            t.pop(key, None)
        else:
            t[key] = wert


def entfernen(kx, tid):
    t = finden(kx, tid)
    del kx.z["tokens"][t["id"]]
    kx.ereignis("token_entfernt", token_id=t["id"])


def bewegen(kx, t, x, y):
    """Setzt ein Token auf ein Feld und meldet `token_bewegt` (z. B. für den Auto-Nebel)."""
    von = (t["x"], t["y"])
    t["x"], t["y"] = int(x), int(y)
    kx.ereignis("token_bewegt", token=t, von=von)


def sc_platzieren(kx, cid, x, y):
    """SC-Token auf die aktive Karte setzen (neu oder vorhanden)."""
    z = kx.z
    c = CH.laden(kx, cid)
    if not z["karteAktiv"]:
        raise Fehler("Keine Karte aktiv")
    t = CH.sc_token(kx, c["id"])
    if t is None:
        t = {"id": "sc-" + c["id"], "art": "sc", "charId": c["id"], "zustaende": [], "sichtbar": True}
        z["tokens"][t["id"]] = t
    t.update({"name": c["name"], "farbe": c.get("farbe", "#3a7bd5"), "karte": z["karteAktiv"],
              "x": int(x), "y": int(y), "groesse": c.get("groesseFelder", 1),
              "tpMax": c.get("tp", {}).get("max"), "tp": c.get("tp", {}).get("aktuell", c.get("tp", {}).get("max"))})
    kx.protokoll("system", f"{c['name']} betritt die Karte bei ({t['x']},{t['y']})")


def sc_entfernen(kx, cid):
    t = CH.sc_token(kx, cid)
    if t:
        del kx.z["tokens"][t["id"]]


def taeuschung(kx, b):
    """Illusionsansicht je SC setzen/entfernen oder global ein-/ausschalten (siehe README „Illusionen“)."""
    z = kx.z
    if b.get("schalter") in ("ein", "aus"):
        z["taeuschungAus"] = b["schalter"] == "aus"
        return {"aus": z["taeuschungAus"]}
    t = finden(kx, b["id"])
    td = t.setdefault("taeuschung", {})
    if b.get("weg"):
        for cid in (b.get("fuer") or list(td)):
            td.pop(cid, None)
    else:
        eintrag = {k: b[k] for k in ("name", "symbol", "farbe", "x", "y", "groesse", "sichtbar", "art")
                   if b.get(k) is not None}
        if not eintrag:
            raise Fehler("Täuschung ohne Angaben (name/symbol/farbe/x/y/groesse/sichtbar/art)")
        for cid in b["fuer"]:
            td[cid] = dict(eintrag)
    if not td:
        t.pop("taeuschung", None)
    return {"taeuschung": t.get("taeuschung", {})}
