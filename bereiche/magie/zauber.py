"""Magie: Zauberdaten am Charakter, Zauberplätze/Pools/spontanes Zaubern, Zauber wirken, Rast, Zauberbuch."""
import json
import re

from bereiche import charakter as CH, kampf as KM, karte as KA, wissen as WI
from bereiche.kern import Fehler
from . import vorbereiten as VB

ATTRIBUT_NACH_KLASSE = [("kleriker", "WE"), ("druide", "WE"), ("waldläufer", "WE"), ("inquisitor", "WE"),
                        ("schamane", "WE"), ("hexenmeister", "CH"), ("barde", "CH"), ("paladin", "CH"),
                        ("orakel", "CH"), ("skalde", "CH")]
FORMEL_RE = re.compile(r"\{([^{}]+)\}")


def zauberstufe(c):
    if c.get("zauberstufe"):
        return int(c["zauberstufe"])
    m = re.search(r"\d+", c.get("klasse") or "")
    return int(m.group()) if m else 1


def zauberattribut(c):
    if c.get("zauberattribut"):
        return c["zauberattribut"]
    klasse = (c.get("klasse") or "").lower()
    return next((a for k, a in ATTRIBUT_NACH_KLASSE if k in klasse), "IN")


def formel(text, stufe):
    """Ersetzt {…} durch das Ergebnis (nur Zahlen, stufe, min, max, Grundrechenarten)."""
    def ersetzen(m):
        ausdruck = m.group(1)
        if not re.fullmatch(r"[\d\s+\-*/(),stufeminax]+", ausdruck):
            raise Fehler(f"Ungültige Formel {ausdruck!r}")
        return str(int(eval(ausdruck, {"__builtins__": {}}, {"stufe": stufe, "min": min, "max": max})))
    return FORMEL_RE.sub(ersetzen, str(text)) if text is not None else None


def reichweite_m(r, stufe):
    """Reichweite in Metern (PF1: nah 7,5 m + 1,5 m je 2 Stufen usw.); 'beruehrung' = angrenzend, 'selbst' = 0."""
    if isinstance(r, (int, float)):
        return float(r)
    return {"nah": 7.5 + 1.5 * (stufe // 2), "mittel": 30 + 3 * stufe, "fern": 120 + 12 * stufe,
            "beruehrung": 1.5, "selbst": 0}.get(r, 7.5)


def zauber_def(kx, c, eintrag):
    """Vollständige Zauberdaten: Katalog + Angaben am Charakter, Formeln ausgerechnet, SG nach PF1."""
    d = dict(WI.zauber_finden(kx, eintrag.get("name")) or {"modus": "sl", "ziel": "keins", "reichweite": "nah"})
    if eintrag.get("grad") in (None, "") and d.get("klassen"):  # Grad passend zur Klasse des Charakters
        g = WI.grad_fuer(d, VB.zauberklasse(c))
        if g is not None:
            d["grad"] = g
    d.update({k: v for k, v in eintrag.items() if k not in ("verbraucht",) and v not in (None, "")})
    stufe = zauberstufe(c)
    for k in ("schaden", "effekt", "rkBonus"):
        if k in d:
            d[k] = formel(d[k], stufe)
    d["reichweiteM"] = reichweite_m(d.get("reichweite", "nah"), stufe)
    fokus = (c.get("zauberfokus") or {}).get(d.get("schule"), 0)  # Zauberfokus: SG-Bonus je Schule
    d["sg"] = 10 + int(d.get("grad") or 0) + CH.attr_mod((c.get("attribute") or {}).get(zauberattribut(c))) + int(fokus or 0)
    d["stufe"] = stufe
    d.setdefault("aktion", "standard")
    return d


def beruehrungsbonus(c, fern):
    """Bonus für Berührungsangriffe: Eintrag aus der Angriffsliste, sonst GAB + GE/ST."""
    for a in c.get("angriffe", []):
        n = (a.get("name") or "").lower()
        if ("berührungslos" in n) == fern and "berührung" in n:
            return int(a.get("bonus") or 0)
    attr = c.get("attribute") or {}
    return int(c.get("gab") or 0) + CH.attr_mod(attr.get("GE" if fern else "ST"))


def _spontan_quelle(c, eintrag):
    """Für spontanes Zaubern (z. B. Wunden heilen): ein vorbereiteter Zauber gleichen Grades
    mit freiem Platz, der kein Domänenzauber ist."""
    for e in c.get("zauberliste", []):
        if (e is not eintrag and not e.get("spontan") and not e.get("domaene") and e.get("grad") == eintrag.get("grad")
                and e.get("proTag") not in (None, "") and int(e.get("verbraucht") or 0) < int(e["proTag"])):
            return e
    return None


def frei(c, eintrag):
    """Wie oft der Zauber heute noch gewirkt werden kann (None = beliebig oft)."""
    if eintrag.get("spontan"):
        return sum(int(e["proTag"]) - int(e.get("verbraucht") or 0) for e in c.get("zauberliste", [])
                   if not e.get("spontan") and not e.get("domaene") and e.get("grad") == eintrag.get("grad")
                   and e.get("proTag") not in (None, ""))
    if eintrag.get("pool"):
        p = (c.get("zauberpools") or {}).get(eintrag["pool"], {})
        return max(0, int(p.get("max") or 0) - int(p.get("verbraucht") or 0))
    if eintrag.get("proTag") in (None, ""):
        return None
    return max(0, int(eintrag["proTag"]) - int(eintrag.get("verbraucht") or 0))


def platz_verbrauchen(c, eintrag):
    """Verbraucht den passenden Platz; Rückgabe: Hinweistext für das Protokoll."""
    if frei(c, eintrag) == 0:
        raise Fehler(f"{eintrag['name']}: heute keine Zauberplätze mehr")
    if eintrag.get("spontan"):
        quelle = _spontan_quelle(c, eintrag)
        quelle["verbraucht"] = int(quelle.get("verbraucht") or 0) + 1
        return f" (spontan anstelle von {quelle['name']})"
    if eintrag.get("pool"):
        p = c["zauberpools"][eintrag["pool"]]
        p["verbraucht"] = int(p.get("verbraucht") or 0) + 1
        return ""
    if eintrag.get("proTag") not in (None, ""):
        eintrag["verbraucht"] = int(eintrag.get("verbraucht") or 0) + 1
    return ""


def ziel_pruefen(kx, t, ziel, art, reichweite, reichweite_m_wert, was="Zauber"):
    """Ziel eines Zaubers/einer Fähigkeit: vorhanden, richtige Seite, sichtbar, in Reichweite."""
    if ziel is None:
        raise Fehler("Bitte ein Ziel wählen")
    if art == "gegner" and ziel["art"] == "sc":
        raise Fehler(f"{'Dieser Zauber' if was == 'Zauber' else 'Diese Fähigkeit'} richtet sich gegen Gegner")
    k = KA.aktive(kx)
    if not KA.sichtbar(ziel, KA.offen(k)):
        raise Fehler("Ziel nicht sichtbar")
    d_felder = KA.abstand(t, ziel)
    if reichweite == "beruehrung":
        if d_felder > KA.reichweite_felder(t):
            raise Fehler(f"{ziel['name']} ist nicht in Berührungsreichweite")
    elif d_felder * k.get("meterProFeld", 1.5) > reichweite_m_wert:
        raise Fehler(f"{ziel['name']} ist außer Reichweite ({reichweite_m_wert:g} m)")


def wirken(kx, t, c, index, ziel=None, feld=None):
    """SC wirkt den Zauber Nr. `index` seiner Zauberliste (c: wirksame Charakterdaten)."""
    z = kx.z
    liste = c.get("zauberliste") or []
    if not 0 <= index < len(liste):
        raise Fehler("Zauber nicht gefunden")
    eintrag = liste[index]
    d = zauber_def(kx, c, eintrag)
    ini = z["initiative"]
    if ini.get("aktiv"):
        KM.darf_handeln(kx, t)
        if not KM.aktion_frei(kx, d["aktion"] if d["aktion"] in ("schnell", "voll") else "standard"):
            raise Fehler("Dafür ist keine passende Aktion mehr frei")
    if KM.unfaehig(t):
        raise Fehler(f"{t['name']} kann nicht zaubern")
    if frei(c, eintrag) == 0:
        raise Fehler(f"{d['name']}: heute keine Zauberplätze mehr")

    zielart = d.get("ziel", "keins")
    if not ini.get("aktiv") and z.get("angriffAusserhalb") and zielart in ("gegner", "feld"):
        raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
    if zielart == "selbst":
        ziel = t
    if zielart in ("gegner", "verbuendet"):
        ziel_pruefen(kx, t, ziel, zielart, d.get("reichweite"), d["reichweiteM"])
    if zielart == "feld" and feld is None:
        raise Fehler("Bitte ein Zielfeld wählen")

    # Platz und Aktion verbrauchen
    hinweis = platz_verbrauchen(c, eintrag)
    CH.speichern(kx, c)
    if ini.get("aktiv"):
        KM.aktion_verbrauchen(kx, d["aktion"])

    wo = f" auf {ziel['name']}" if ziel is not None and ziel is not t else f" auf Feld ({feld[0]},{feld[1]})" if feld else ""
    titel = f"{t['name']} wirkt {d['name']}{wo}{hinweis}"
    modus = d.get("modus", "sl")
    wecken = False
    if modus in ("angriff-fern", "angriff-nah"):
        fern = modus == "angriff-fern"
        mods = []
        if fern and any(s["art"] == "sc" and s is not t and KA.abstand(s, ziel) <= 1 for s in z["tokens"].values()
                        if s.get("karte") == ziel.get("karte")):
            mods.append(("in den Nahkampf", -4))
        if not fern and KM.flankiert(kx, t, ziel):
            mods.append(("Flankieren", 2))
        mit_rw = bool(d.get("rettungswurf"))  # z. B. Wunden verursachen: Berührung trifft, Wille halbiert
        treffer = KM.aufloesen(kx, t["name"], ziel, f"✦ {d['name']}{hinweis}", beruehrungsbonus(c, fern),
                               None if mit_rw else d.get("schaden"), "x2", True, not fern, mods)
        if mit_rw and treffer:
            KM.rettungswurf(kx, t, ziel, d, titel)
    elif modus == "automatisch":
        s, detail, _ = kx.wuerfeln(d["schaden"])
        if ziel.get("tp") is not None:
            ziel["tp"] -= s
        kx.protokoll("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"{s} Schaden ({d.get('art', '')})",
                     detail=f"{d['schaden']}: {detail} – trifft automatisch")
    elif modus == "rettungswurf":
        KM.rettungswurf(kx, t, ziel, d, titel)
    elif modus == "heilung":
        s, detail, _ = kx.wuerfeln(d["schaden"])
        KM.heilen(kx, ziel, s)
        kx.protokoll("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"heilt {s} TP", detail=f"{d['schaden']}: {detail}")
    else:  # effekt oder sl
        if ziel is not None:
            if d.get("entferntZustand") in ziel.get("zustaende", []):
                ziel["zustaende"].remove(d["entferntZustand"])
            KM.zustand_an(ziel, d.get("setztZustand"))
        wecken = modus == "sl" and not ini.get("aktiv")
        kx.protokoll("zauber", titel, wer=t["name"],
                     ergebnisText="der Spielleiter wertet aus" if modus == "sl" else "wirkt",
                     detail=d.get("effekt", ""), feld=list(feld) if feld else None, wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"

    # Offensiver Zauber außerhalb des Kampfes: der Kampf beginnt
    if not ini.get("aktiv") and zielart in ("gegner", "feld") and modus != "effekt":
        z["angriffAusserhalb"] = True
        kx.protokoll("zugende", f"{t['name']} zaubert überraschend – der Kampf beginnt!", wecken=True)
        z["slStatus"] = "wartet"
    elif not ini.get("aktiv") and not wecken:
        kx.protokoll("zugende", f"{t['name']} hat gezaubert.", wecken=True)
        z["slStatus"] = "wartet"


def wirken_spieler(kx, b):
    """/api/zaubern: {id, zauber (Index), ziel?, feld?}."""
    t = KA.finden(kx, b["id"])
    if t["art"] != "sc":
        raise Fehler("Nur eure Charaktere zaubern")
    c = CH.von_token(kx, t)
    if not c:
        raise Fehler("Charakter nicht gefunden")
    ziel = KA.finden(kx, b["ziel"]) if b.get("ziel") else None
    wirken(kx, t, c, int(b["zauber"]), ziel, tuple(b["feld"]) if b.get("feld") else None)


def rast(kx, cid=None):
    """Rast (8 Stunden): Zauberplätze, Pools, Betäubender Schlag zurücksetzen; Modi laufen 8 Stunden weiter."""
    for c in CH.alle(kx):
        if cid in (None, c["id"]):
            for e in c.get("zauberliste", []):
                e["verbraucht"] = 0
            for p in (c.get("zauberpools") or {}).values():
                p["verbraucht"] = 0
            if c.get("betaeubendPool"):
                c["betaeubendPool"]["verbraucht"] = 0
            CH.speichern(kx, c)
    kx.ereignis("zeit_vergeht", runden=4800)  # 8 Stunden: Modi mit kürzerer Dauer enden
    kx.protokoll("system", "Nach der Rast sind die Zauberplätze wieder frei.")


def ansicht(kx, c):
    """Berechnete Zauberwerte je Eintrag für die Oberfläche (Feld _d, wird nicht gespeichert)."""
    for e in c.get("zauberliste", []):
        try:
            d = zauber_def(kx, c, e)
        except Fehler:
            continue
        d["beruehrungsbonus"] = beruehrungsbonus(c, d.get("modus") == "angriff-fern")
        d["frei"] = frei(c, e)
        if e.get("pool"):
            d["poolMax"] = (c.get("zauberpools") or {}).get(e["pool"], {}).get("max")
        e["_d"] = d
    c["_zauberKlasse"] = VB.zauberklasse(c)  # Zauberliste (Feld oder aus der Klasse erraten)
    c["_vorbereiten"] = VB.kann_vorbereiten(c)  # Knopf „Zauber vorbereiten“ zeigen


def _liste_stand(c):
    return json.dumps([{k: v for k, v in e.items() if k != "_d"} for e in c.get("zauberliste") or []], sort_keys=True)


def vorbereiten(kx, b):
    """Zauber neu vorbereiten (nach der Rast). op "plan": Plätze und Auswahl; op "speichern": namen je Platz."""
    c = CH.laden(kx, b["charId"])
    if kx.z["initiative"].get("aktiv"):
        raise Fehler("Zauber erst nach dem Kampf vorbereiten")
    liste = c.get("zauberliste") or []
    if b.get("op") == "plan":
        buch = c.get("zauberbuch") or []
        return {"klasse": VB.zauberklasse(c), "plaetze": VB.plaetze(liste), "stand": _liste_stand(c),
                "aliase": WI.ALIASE,
                "buch": [{"name": e["name"], "grad": e["grad"]} for e in buch] if buch else None}
    if b.get("stand") != _liste_stand(c):
        raise Fehler("Die Zauberliste wurde inzwischen geändert – bitte den Dialog neu öffnen")
    try:
        neu = VB.neu_vorbereiten(liste, b.get("namen") or [])
    except ValueError as e:
        raise Fehler(str(e)) from None
    alt = {e["name"].lower() for e in liste}
    dazu = sorted({e["name"] for e in neu if e["name"].lower() not in alt})
    c["zauberliste"] = neu
    CH.speichern(kx, c)
    kx.protokoll("system", f"{c['name']} bereitet die Zauber neu vor"
                 + (f" (neu: {', '.join(dazu)})" if dazu else " (unverändert)" if neu == liste else "") + ".")
    return {}


def zauberbuch(kx, b):
    """Zauberbuch eines Charakters: Einträge {name, grad} hinzufügen ('add') oder entfernen ('weg')."""
    c = CH.laden(kx, b["charId"])
    buch = c.setdefault("zauberbuch", [])
    name = (b.get("name") or "").strip()
    if not name:
        raise Fehler("Zaubername fehlt")
    if b.get("op") == "weg":
        c["zauberbuch"] = [e for e in buch if e["name"].lower() != name.lower()]
    else:
        grad = int(b.get("grad", 0))
        if not 0 <= grad <= 9:
            raise Fehler("Grad muss zwischen 0 und 9 liegen")
        if not any(e["name"].lower() == name.lower() for e in buch):
            buch.append({"name": name[:80], "grad": grad})
    CH.speichern(kx, c)
    return {}
