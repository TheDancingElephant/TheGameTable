"""Stufenaufstiegs-Assistent (Regeln und Berechnung), unabhängig vom Server.

Ablauf: Spieler wählt im Assistenten TP, Fertigkeitsränge, Talent, Attribut, Zauber -> Antrag.
Der Spielleiter prüft und gibt frei (`anwenden`). Erst dann ändert sich der Charakter.
"""
import math
import re
from fractions import Fraction

ATTRIBUTE = ["ST", "GE", "KO", "IN", "WE", "CH"]

# Klassenvorlagen (PF1): TW, Fertigkeitspunkte, GAB (voll/dreiviertel/halb), gute Rettungswürfe, Zauber
KLASSEN = {
    "Barbar":       {"tw": 12, "fp": 4, "gab": "voll",        "gut": ["ZAEH"]},
    "Barde":        {"tw": 8,  "fp": 6, "gab": "dreiviertel", "gut": ["REF", "WIL"], "attr": "CH"},
    "Druide":       {"tw": 8,  "fp": 4, "gab": "dreiviertel", "gut": ["ZAEH", "WIL"], "attr": "WE", "tabelle": "voll"},
    "Hexenmeister": {"tw": 6,  "fp": 2, "gab": "halb",        "gut": ["WIL"], "attr": "CH"},
    "Kämpfer":      {"tw": 10, "fp": 2, "gab": "voll",        "gut": ["ZAEH"], "bonustalent": "gerade"},
    "Kleriker":     {"tw": 8,  "fp": 2, "gab": "dreiviertel", "gut": ["ZAEH", "WIL"], "attr": "WE", "tabelle": "voll",
                     "domaene": True},
    # Alternativregeln „Entfesselte Klassen“ (prd.5footstep.de/Alternativregeln/Klassen)
    "Entfesselter Mönch":   {"tw": 10, "fp": 4, "gab": "voll",        "gut": ["ZAEH", "REF", "WIL"]},
    "Entfesselter Schurke": {"tw": 8,  "fp": 8, "gab": "dreiviertel", "gut": ["REF"]},
    "Magier":       {"tw": 6,  "fp": 2, "gab": "halb",        "gut": ["WIL"], "attr": "IN", "tabelle": "voll", "buch": True,
                     "bonustalent": [5, 10, 15, 20]},
    "Mönch":        {"tw": 8,  "fp": 4, "gab": "dreiviertel", "gut": ["ZAEH", "REF", "WIL"]},
    "Paladin":      {"tw": 10, "fp": 2, "gab": "voll",        "gut": ["ZAEH", "WIL"], "attr": "CH"},
    "Schurke":      {"tw": 8,  "fp": 8, "gab": "dreiviertel", "gut": ["REF"]},
    "Waldläufer":   {"tw": 10, "fp": 6, "gab": "voll",        "gut": ["ZAEH", "REF"], "attr": "WE"},
}

# Grundzauberplätze pro Tag, Grad 1..9, für Klassen mit voller Zaubertabelle (Magier, Kleriker, Druide)
VOLL = {
    1: [1], 2: [2], 3: [2, 1], 4: [3, 2], 5: [3, 2, 1], 6: [3, 3, 2], 7: [4, 3, 2, 1], 8: [4, 3, 3, 2],
    9: [4, 4, 3, 2, 1], 10: [4, 4, 3, 3, 2], 11: [4, 4, 4, 3, 2, 1], 12: [4, 4, 4, 3, 3, 2],
    13: [4, 4, 4, 4, 3, 2, 1], 14: [4, 4, 4, 4, 3, 3, 2], 15: [4, 4, 4, 4, 4, 3, 2, 1],
    16: [4, 4, 4, 4, 4, 3, 3, 2], 17: [4, 4, 4, 4, 4, 4, 3, 2, 1], 18: [4, 4, 4, 4, 4, 4, 3, 3, 2],
    19: [4, 4, 4, 4, 4, 4, 4, 3, 3], 20: [4, 4, 4, 4, 4, 4, 4, 4, 4],
}

# Fertigkeit -> Attribut (Präfix-Vergleich)
FERT_ATTR = {
    "Akrobatik": "GE", "Auftreten": "CH", "Beruf": "WE", "Bluffen": "CH", "Diplomatie": "CH", "Einschüchtern": "CH",
    "Entfesselungskunst": "GE", "Fingerfertigkeit": "GE", "Fliegen": "GE", "Handwerk": "IN", "Heilkunde": "WE",
    "Heimlichkeit": "GE", "Klettern": "ST", "Magischen Gegenstand benutzen": "CH", "Mechanismus ausschalten": "GE",
    "Mit Tieren umgehen": "CH", "Motiv erkennen": "WE", "Reiten": "GE", "Schätzen": "IN", "Schwimmen": "ST",
    "Sprachenkunde": "IN", "Überlebenskunst": "WE", "Verkleiden": "CH", "Wahrnehmung": "WE", "Wissen": "IN",
    "Zauberkunde": "IN",
}

# Talente: (Name, Voraussetzungen als Text, maschinenprüfbar: {"attr": {...}, "gab": n, "stufe": n})
TALENTE = [
    ("Abhärtung", "", {}), ("Ausweichen", "GE 13", {"attr": {"GE": 13}}),
    ("Beweglichkeit", "GE 13, Ausweichen", {"attr": {"GE": 13}}),
    ("Blitzschnelle Reflexe", "", {}), ("Eiserner Wille", "", {}), ("Große Zähigkeit", "", {}),
    ("Fertigkeitsfokus", "", {}), ("Kampfreflexe", "", {}), ("Verbesserte Initiative", "", {}),
    ("Waffenfokus", "Waffenkenntnis, GAB +1", {"gab": 1}),
    ("Mächtiger Waffenfokus", "Waffenfokus, Kämpfer 8", {"stufe": 8}),
    ("Waffenspezialisierung", "Waffenfokus, Kämpfer 4", {"stufe": 4}),
    ("Kritischen Treffer verbessern", "Waffenkenntnis, GAB +8", {"gab": 8}),
    ("Machtvoller Angriff", "ST 13, GAB +1", {"attr": {"ST": 13}, "gab": 1}),
    ("Verbesserter Entwaffnen", "IN 13, Kampfreflexe", {"attr": {"IN": 13}}),
    ("Doppelschlag", "GAB +6, Waffenfokus (beide Waffen)", {"gab": 6}),
    ("Punktgenauer Schuss", "", {}), ("Präzisionsschuss", "Punktgenauer Schuss", {}),
    ("Mehrfachschuss", "GE 17, Punktgenauer Schuss, GAB +6", {"attr": {"GE": 17}, "gab": 6}),
    ("Schnelles Nachladen", "Waffenkenntnis", {}), ("Kernschuss", "Punktgenauer Schuss, GAB +1", {"gab": 1}),
    ("Zauberfokus", "", {}), ("Mächtiger Zauberfokus", "Zauberfokus", {}),
    ("Zauberdurchdringung", "", {}), ("Mächtige Zauberdurchdringung", "Zauberdurchdringung", {}),
    ("Kampfzauberei", "", {}), ("Zauber verstärken", "", {}), ("Zauber maximieren", "", {}),
    ("Zauber ausdehnen", "", {}), ("Zauber still wirken", "", {}), ("Zauber ohne Gesten", "", {}),
    ("Wundersame Gegenstände herstellen", "Zauberstufe 3", {"stufe": 3}),
    ("Zauberstab herstellen", "Zauberstufe 5", {"stufe": 5}),
    ("Magische Waffen und Rüstungen herstellen", "Zauberstufe 5", {"stufe": 5}),
    ("Ring herstellen", "Zauberstufe 7", {"stufe": 7}), ("Zepter herstellen", "Zauberstufe 9", {"stufe": 9}),
    ("Stab herstellen", "Zauberstufe 11", {"stufe": 11}),
]


def attr_mod(w):
    return (int(w) - 10) // 2 if w is not None else 0


def klasse_erkennen(text):
    """Liefert (Klassenname laut Vorlage oder None, erster Klassenname im Text)."""
    t = (text or "").strip()
    erster = re.sub(r"\s*\d+.*$", "", t.split("/")[0].strip())
    for n in sorted(KLASSEN, key=len, reverse=True):  # „Entfesselter Mönch“ vor „Mönch“
        if n.lower() in t.lower():
            return n, erster
    return None, erster


def klassen_liste(text):
    """'Mönch 5 / Schurke 3' -> [('Mönch', 5), ('Schurke', 3)]"""
    erg = []
    for teil in re.split(r"[/,]", text or ""):
        name = re.sub(r"\s*\d+.*$", "", teil.strip()).strip()
        if name:
            m = re.search(r"\d+", teil)
            erg.append((name, int(m.group()) if m else 1))
    return erg


def vorlage_fuer(name, vorlagen=None):
    v = (vorlagen or {}).get(name)
    if v in KLASSEN:
        return v
    if v == "":
        return None
    return klasse_erkennen(name)[0]


def anteile(klassen, vorlagen):
    """Anteilige Boni (Alternativregeln): GAB als Bruch, Rettungswürfe je Klasse als Bruch + einmalig 2.
    klassen: [(name, stufe)]. Liefert (GAB, {ZAEH, REF, WIL}) als Fraction, oder None, wenn eine Klasse keine Vorlage hat."""
    gab = Fraction(0)
    rw = {k: Fraction(0) for k in ("ZAEH", "REF", "WIL")}
    gut_irgendwo = {k: False for k in rw}
    for name, st in klassen:
        v = KLASSEN.get(vorlage_fuer(name, vorlagen) or "")
        if not v:
            return None
        gab += Fraction({"voll": 4, "dreiviertel": 3, "halb": 2}[v["gab"]], 4) * st
        for k in rw:
            if k in v["gut"]:
                rw[k] += Fraction(st, 2)
                gut_irgendwo[k] = True
            else:
                rw[k] += Fraction(st, 3)
    for k in rw:
        if gut_irgendwo[k] and klassen:
            rw[k] += 2
    return gab, rw


def boni_delta(klassen_alt, klassen_neu, vorlagen):
    """Zuwachs von GAB/Rettungswürfen (abgerundete Summen vorher/nachher) oder None."""
    a = anteile(klassen_alt, vorlagen) if klassen_alt else (Fraction(0), {k: Fraction(0) for k in ("ZAEH", "REF", "WIL")})
    n = anteile(klassen_neu, vorlagen)
    if a is None or n is None:
        return None
    return math.floor(n[0]) - math.floor(a[0]), {k: math.floor(n[1][k]) - math.floor(a[1][k]) for k in n[1]}


def gab_delta(vorlage, ziel_klassenstufe):
    f = {"voll": lambda n: n, "dreiviertel": lambda n: n * 3 // 4, "halb": lambda n: n // 2}[vorlage]
    return f(ziel_klassenstufe) - f(ziel_klassenstufe - 1)


def rw_delta(gut, ziel_klassenstufe):
    def w(n, g):
        return (2 + n // 2) if g else n // 3
    return {k: w(ziel_klassenstufe, k in gut) - w(ziel_klassenstufe - 1, k in gut) for k in ("ZAEH", "REF", "WIL")}


def klassenstufe(klassentext, name):
    for teil in re.split(r"[/,]", klassentext or ""):
        if name.lower() in teil.lower():
            m = re.search(r"\d+", teil)
            return int(m.group()) if m else 1
    return 0


def klasse_hochzaehlen(klassentext, name):
    """'Magier 10' -> 'Magier 11'; neue Klasse wird mit ' / Name 1' angehängt."""
    teile = [t.strip() for t in re.split(r"/", klassentext or "") if t.strip()]
    for i, teil in enumerate(teile):
        if name.lower() in teil.lower():
            m = re.search(r"(\d+)", teil)
            n = int(m.group(1)) + 1 if m else 2
            teile[i] = re.sub(r"\d+", str(n), teil, count=1) if m else f"{teil} {n}"
            return " / ".join(teile)
    teile.append(f"{name} 1")
    return " / ".join(teile)


def fert_attr(name):
    for k, a in FERT_ATTR.items():
        if name.startswith(k):
            return a
    return None


def fert_raenge(c, f):
    """Bekannte Ränge (c['raenge']) oder Schätzung aus Gesamtbonus; (Wert, geschätzt?)."""
    r = (c.get("raenge") or {}).get(f["name"])
    if r is not None:
        return int(r), False
    a = fert_attr(f["name"])
    rest = int(f.get("bonus") or 0) - attr_mod((c.get("attribute") or {}).get(a)) if a else int(f.get("bonus") or 0)
    if f.get("klasse"):
        return (rest - 3 if rest >= 4 else 0), True
    return max(0, rest), True


def zauberattribut(c, vorlage):
    return c.get("zauberattribut") or (KLASSEN.get(vorlage or "", {}).get("attr")) or "IN"


def plaetze(c, vorlage, stufe):
    """Zauberplätze pro Grad (1..9) für die Stufe: {grad: gesamt} oder None, wenn unbekannt."""
    v = KLASSEN.get(vorlage or "")
    if not v or v.get("tabelle") != "voll":
        return None
    mod = attr_mod((c.get("attribute") or {}).get(zauberattribut(c, vorlage)))
    ergebnis = {}
    for g, basis in enumerate(VOLL[min(stufe, 20)], start=1):
        bonus = (1 + (mod - g) // 4) if mod >= g else 0
        ergebnis[g] = basis + bonus + (1 if v.get("domaene") else 0)
    return ergebnis


def talentzahl(vorlage, ziel_stufe, gesamt_stufe):
    n = 1 if gesamt_stufe % 2 == 1 else 0
    b = (KLASSEN.get(vorlage or "") or {}).get("bonustalent")
    kl = ziel_stufe
    if b == "gerade" and kl % 2 == 0:
        n += 1
    elif isinstance(b, list) and kl in b:
        n += 1
    return n


def ist_attributsstufe(ziel):
    return ziel % 4 == 0


def plan(c, ziel, klasse=None, vorlage=None, vorlagen=None):
    """Alle Angaben, die der Assistent braucht. klasse = Klassenname, der steigt; vorlage = Regelvorlage dafür
    (z. B. 'Kleriker'); vorlagen = {Klassenname: Vorlage} für die übrigen Klassen des Charakters."""
    klassentext = c.get("klasse") or ""
    vorlagen = {**(c.get("klassenVorlagen") or {}), **(vorlagen or {})}
    liste = klassen_liste(klassentext)
    erkannt, erster = klasse_erkennen(klasse or klassentext)
    name = (klasse or erster or "").strip()
    # vorhandenen Klassennamen exakt treffen (z. B. 'Mönch' in 'Mönch 5')
    for kn, _ in liste:
        if name and (name.lower() == kn.lower()):
            name = kn
    if vorlage in KLASSEN:
        pass
    elif vorlage == "":
        vorlage = None
    else:
        vorlage = vorlage_fuer(name, vorlagen)
    vorlagen[name] = vorlage or ""
    kl_alt = klassenstufe(klassentext, name)
    kl_stufe = kl_alt + 1 if name else ziel
    neue_klasse = name != "" and kl_alt == 0 and bool(liste)
    klassen_neu = [(n, s + (1 if n == name else 0)) for n, s in liste]
    if name and kl_alt == 0:
        klassen_neu.append((name, 1))
    delta = boni_delta(liste, klassen_neu, vorlagen)
    v = KLASSEN.get(vorlage or "", {})
    attrs = c.get("attribute") or {}
    fp_klasse = v.get("fp", 2)
    ist_mensch = "mensch" in (c.get("volk") or "").lower()
    fertigkeiten = []
    for f in c.get("fertigkeiten") or []:
        r, geschaetzt = fert_raenge(c, f)
        a = fert_attr(f["name"])
        fertigkeiten.append({"name": f["name"], "bonus": f.get("bonus", 0), "klasse": bool(f.get("klasse")),
                             "attr": a, "raenge": r, "geschaetzt": geschaetzt})
    slots_alt = plaetze(c, vorlage, kl_stufe - 1)
    slots_neu = plaetze(c, vorlage, kl_stufe)
    return {
        "zielStufe": ziel, "klasse": name, "vorlage": vorlage, "erkannt": erkannt, "klassenStufe": kl_stufe,
        "klassenStufeAlt": kl_alt, "neueKlasse": neue_klasse,
        "klassen": [{"name": n, "stufe": s, "vorlage": vorlage_fuer(n, vorlagen) or ""} for n, s in liste],
        "vorlagenMap": vorlagen, "anteilig": delta is not None and len(klassen_neu) > 1,
        "tw": v.get("tw", 8), "fp": {"klasse": fp_klasse, "intMod": attr_mod(attrs.get("IN")),
                                                      "volk": 1 if ist_mensch else 0},
        "koMod": attr_mod(attrs.get("KO")),
        "gab": delta[0] if delta else 0,
        "rw": delta[1] if delta else {"ZAEH": 0, "REF": 0, "WIL": 0},
        "vorlageBekannt": bool(v),
        "talente": talentzahl(vorlage, kl_stufe, ziel),
        "attributPunkt": ist_attributsstufe(ziel),
        "attribute": attrs, "gabGesamt": c.get("gab", 0),
        "fertigkeiten": fertigkeiten,
        "plaetzeAlt": slots_alt, "plaetzeNeu": slots_neu, "zauberattribut": zauberattribut(c, vorlage),
        "hatBuch": bool(v.get("buch") or c.get("zauberbuch")), "maxGrad": max(slots_neu) if slots_neu else 9,
        "zauberliste": [{"name": e["name"], "grad": e["grad"], "proTag": e.get("proTag")}
                        for e in c.get("zauberliste") or []],
        "talenteKatalog": [{"name": n, "voraus": t, "pruef": p} for n, t, p in TALENTE],
        "vorlagen": sorted(KLASSEN),
    }


def tp_wurf(tw, ko_mod, art, wuerfel):
    """art 'wurf' oder 'schnitt'; wuerfel: Funktion tw -> Zufallszahl. Liefert (TP-Zuwachs, Text)."""
    if art == "wurf":
        w = wuerfel(tw)
        text = f"1W{tw}[{w}]"
    else:
        w = tw // 2 + 1
        text = f"Durchschnitt {w}"
    return max(1, w + ko_mod), f"{text} {ko_mod:+d} KO"


def pruefen(c, p, a, tp):
    """Prüft den Antrag a gegen den Plan p. Liefert (Fehler, Warnungen)."""
    fehler, warn = [], []
    if not tp:
        fehler.append("Trefferpunkte wurden noch nicht gewürfelt/gewählt.")
    ziel = p["zielStufe"]
    # Fertigkeiten
    budget = max(1, p["fp"]["klasse"] + p["fp"]["intMod"]) + p["fp"]["volk"] + (1 if a.get("bevorzugt") == "fertigkeit" else 0) \
        + int(a.get("extraFp") or 0)
    raenge = {k: int(v) for k, v in (a.get("raenge") or {}).items() if int(v) != 0}
    bekannt = {f["name"]: f for f in p["fertigkeiten"]}
    summe = 0
    for n, v in raenge.items():
        if n not in bekannt:
            fehler.append(f"Unbekannte Fertigkeit: {n}")
            continue
        if v < 0:
            fehler.append(f"Negative Ränge bei {n}")
        summe += v
        if bekannt[n]["raenge"] + v > ziel:
            (fehler if not bekannt[n]["geschaetzt"] else warn).append(
                f"{n}: Ränge {bekannt[n]['raenge']}+{v} überschreiten die Obergrenze Stufe {ziel}"
                + (" (Ränge geschätzt)" if bekannt[n]["geschaetzt"] else ""))
    if summe > budget:
        fehler.append(f"Zu viele Fertigkeitspunkte verteilt: {summe} von {budget}")
    elif summe < budget:
        warn.append(f"{budget - summe} Fertigkeitspunkt(e) nicht verteilt")
    # Talente
    tal = [t for t in (a.get("talente") or []) if str(t).strip()]
    if len(tal) > p["talente"]:
        fehler.append(f"Zu viele Talente: {len(tal)} von {p['talente']}")
    elif len(tal) < p["talente"]:
        warn.append(f"{p['talente'] - len(tal)} Talent(e) noch nicht gewählt")
    kat = {t["name"].lower(): t for t in p["talenteKatalog"]}
    gab_neu = int(c.get("gab") or 0) + int(a.get("gab", p["gab"]))
    attrs = dict(c.get("attribute") or {})
    if a.get("attribut"):
        attrs[a["attribut"]] = attrs.get(a["attribut"], 10) + 1
    for t in tal:
        k = kat.get(str(t).split("(")[0].strip().lower())
        if not k:
            warn.append(f"Talent „{t}“ nicht im Katalog – Voraussetzungen prüft der Spielleiter")
            continue
        pr = k["pruef"]
        for at, mn in (pr.get("attr") or {}).items():
            if attrs.get(at, 0) < mn:
                fehler.append(f"{k['name']}: {at} {mn} nötig (hat {attrs.get(at, 0)})")
        if pr.get("gab") and gab_neu < pr["gab"]:
            fehler.append(f"{k['name']}: GAB +{pr['gab']} nötig (hat +{gab_neu})")
        if pr.get("stufe") and ziel < pr["stufe"]:
            fehler.append(f"{k['name']}: Stufe {pr['stufe']} nötig")
    # Attribut
    if p["attributPunkt"]:
        if a.get("attribut") not in ATTRIBUTE:
            fehler.append("Attributspunkt (Stufe %d) noch nicht gewählt." % ziel)
    elif a.get("attribut"):
        fehler.append("Auf dieser Stufe gibt es keinen Attributspunkt.")
    # Zauber
    z = a.get("zauber") or {}
    for e in z.get("neu") or []:
        if not 0 <= int(e.get("grad", -1)) <= p["maxGrad"]:
            fehler.append(f"Zauber {e.get('name')}: Grad {e.get('grad')} nicht verfügbar (max. {p['maxGrad']})")
    if p["plaetzeNeu"]:
        summen = {}
        for e in c.get("zauberliste") or []:
            g = int(e["grad"])
            neu = (z.get("proTag") or {}).get(e["name"], e.get("proTag"))
            if g >= 1 and neu not in (None, ""):
                summen[g] = summen.get(g, 0) + int(neu)
        for e in z.get("neu") or []:
            if int(e["grad"]) >= 1 and e.get("proTag") not in (None, ""):
                summen[int(e["grad"])] = summen.get(int(e["grad"]), 0) + int(e["proTag"])
        for g, mx in p["plaetzeNeu"].items():
            s = summen.get(g, 0)
            if s > mx:
                fehler.append(f"Grad {g}: {s} Zauber vorbereitet, aber nur {mx} Plätze")
            elif s < mx:
                warn.append(f"Grad {g}: {mx - s} Platz/Plätze frei")
    return fehler, warn


def zusammenfassung(c, p, a, tp):
    z = []
    z.append(f"{c['name']}: {p['klasse']} {p['klassenStufeAlt']} → {p['klassenStufe']} (Charakterstufe {p['zielStufe']}), "
             f"neu: {klasse_hochzaehlen(c.get('klasse'), p['klasse'])}")
    if tp:
        z.append(f"TP +{tp['plus']} ({tp['text']}{', +1 bevorzugte Klasse' if a.get('bevorzugt') == 'tp' else ''})")
    z.append(f"GAB {a.get('gab', p['gab']):+d}, RW " + ", ".join(
        f"{k} {v:+d}" for k, v in (a.get('rw') or p['rw']).items()))
    r = {k: v for k, v in (a.get("raenge") or {}).items() if int(v)}
    if r:
        z.append("Ränge: " + ", ".join(f"{k} +{v}" for k, v in r.items()))
    if a.get("talente"):
        z.append("Talente: " + ", ".join(a["talente"]))
    if a.get("attribut"):
        z.append(f"Attribut: +1 {a['attribut']}")
    zz = a.get("zauber") or {}
    if zz.get("neu"):
        z.append("Neue Zauber: " + ", ".join(f"{e['name']} (Grad {e['grad']}" + (f", {e['proTag']}×/Tag" if e.get("proTag") else "") + ")"
                                             for e in zz["neu"]))
    if zz.get("proTag"):
        z.append("Zauberplätze geändert: " + ", ".join(f"{k} → {v}×" for k, v in zz["proTag"].items()))
    if zz.get("buch"):
        z.append("Ins Zauberbuch: " + ", ".join(f"{e['name']} ({e['grad']})" for e in zz["buch"]))
    if a.get("notiz"):
        z.append("Anmerkung: " + a["notiz"])
    return z


def anwenden(c, p, a, tp):
    """Schreibt den freigegebenen Antrag in den Charakter (c wird verändert)."""
    ziel = p["zielStufe"]
    mod_alt = {k: attr_mod(v) for k, v in (c.get("attribute") or {}).items()}
    # Klasse, Stufe
    c["klasse"] = klasse_hochzaehlen(c.get("klasse"), p["klasse"])
    c["klassenVorlagen"] = {**(c.get("klassenVorlagen") or {}), **(p.get("vorlagenMap") or {})}
    c["stufe"] = ziel
    # TP
    plus = tp["plus"] + (1 if a.get("bevorzugt") == "tp" else 0)
    t = c.setdefault("tp", {})
    t["max"] = (t.get("max") or 0) + plus
    t["aktuell"] = (t.get("aktuell") if t.get("aktuell") is not None else t["max"] - plus) + plus
    # GAB, Rettungswürfe
    gab = int(a.get("gab", p["gab"]))
    c["gab"] = int(c.get("gab") or 0) + gab
    c["kmb"] = int(c.get("kmb") or 0) + gab
    c["kmv"] = int(c.get("kmv") or 0) + gab
    rw = c.setdefault("rw", {})
    for k, v in (a.get("rw") or p["rw"]).items():
        rw[k] = int(rw.get(k) or 0) + int(v)
    # Fertigkeiten
    bekannt = {f["name"]: f for f in p["fertigkeiten"]}
    raenge = c.setdefault("raenge", {})
    for f in c.get("fertigkeiten") or []:
        info = bekannt[f["name"]]
        raenge.setdefault(f["name"], info["raenge"])
    for n, v in (a.get("raenge") or {}).items():
        v = int(v)
        if not v:
            continue
        f = next(x for x in c["fertigkeiten"] if x["name"] == n)
        erste = f.get("klasse") and raenge.get(n, 0) == 0
        f["bonus"] = int(f.get("bonus") or 0) + v + (3 if erste else 0)
        raenge[n] = raenge.get(n, 0) + v
    # Attribut (rückwirkend: abgeleitete Werte)
    if a.get("attribut"):
        at = a["attribut"]
        c["attribute"][at] = int(c["attribute"].get(at, 10)) + 1
        d = attr_mod(c["attribute"][at]) - mod_alt.get(at, 0)
        if d:
            for f in c.get("fertigkeiten") or []:
                if fert_attr(f["name"]) == at:
                    f["bonus"] = int(f.get("bonus") or 0) + d
            if at == "KO":
                c["tp"]["max"] += d * ziel
                c["tp"]["aktuell"] += d * ziel
                c.setdefault("rw", {})["ZAEH"] = int(c["rw"].get("ZAEH") or 0) + d
            elif at == "GE":
                c["rw"]["REF"] = int(c["rw"].get("REF") or 0) + d
                c["ini"] = int(c.get("ini") or 0) + d
                for k in ("normal", "beruehrung"):
                    if k in (c.get("rk") or {}):
                        c["rk"][k] += d
                c["kmv"] = int(c.get("kmv") or 0) + d
            elif at == "WE":
                c["rw"]["WIL"] = int(c["rw"].get("WIL") or 0) + d
            elif at == "ST":
                c["kmb"] = int(c.get("kmb") or 0) + d
                c["kmv"] = int(c.get("kmv") or 0) + d
    # Talente
    if a.get("talente"):
        neu = ", ".join(a["talente"])
        c["talente"] = ((c.get("talente") or "").rstrip() + f"\nStufe {ziel}: {neu}").strip()
    # Zauber
    z = a.get("zauber") or {}
    liste = c.setdefault("zauberliste", [])
    for name, wert in (z.get("proTag") or {}).items():
        for e in liste:
            if e["name"] == name:
                e["proTag"] = int(wert) if wert not in (None, "") else None
    for e in z.get("neu") or []:
        vorh = next((x for x in liste if x["name"].lower() == e["name"].lower() and x["grad"] == int(e["grad"])), None)
        pt = int(e["proTag"]) if e.get("proTag") not in (None, "") else None
        if vorh:
            vorh["proTag"] = (vorh.get("proTag") or 0) + (pt or 0) if pt else vorh.get("proTag")
        else:
            liste.append({"name": e["name"], "grad": int(e["grad"]), "proTag": pt, "verbraucht": 0})
    liste.sort(key=lambda e: e["grad"])
    if z.get("buch"):
        buch = c.setdefault("zauberbuch", [])
        for e in z["buch"]:
            if not any(x["name"].lower() == e["name"].lower() for x in buch):
                buch.append({"name": e["name"], "grad": int(e["grad"])})
    if a.get("notiz"):
        c["notizen"] = ((c.get("notizen") or "") + f"\nAufstieg Stufe {ziel}: {a['notiz']}").strip()
    return c
