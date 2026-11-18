"""Magie: Zauber neu vorbereiten (nach der Rast) – welche Klassen vorbereiten, Plätze einer Zauberliste,
Domänenplätze, neue Zauberliste aus der Auswahl je Platz."""
import re

from bereiche.wissen import klasse_der_liste


# Zauberlisten, deren Klassen ihre Zauber täglich vorbereiten (Spontanzauberer wie Barde, Hexenmeister, Orakel nicht)
VORBEREITEND = {"Kleriker", "Druide", "Magier", "Paladin", "Antipaladin", "Waldläufer", "Hexe", "Alchemist",
                "Kampfmagus", "Schamane"}
SPONTAN_WOERTER = ("orakel", "oracle", "hexenmeister", "sorcerer", "barde", "skalde", "inquisitor")


def zauberklasse(c):
    """Zauberliste eines Charakters: Feld „zauberKlasse“, sonst aus der Klassenangabe erraten."""
    return c.get("zauberKlasse") or klasse_der_liste(c.get("klasse"))


def kann_vorbereiten(c):
    k = zauberklasse(c)
    spontan = any(w in (c.get("klasse") or "").lower() for w in SPONTAN_WOERTER) and not c.get("zauberKlasse")
    return bool(c.get("zauberliste")) and (k in VORBEREITEND or bool(c.get("zauberbuch"))) and not spontan


def plaetze(liste):
    """Vorbereitbare Plätze einer Zauberliste: je Eintrag mit „pro Tag“ N so viele Plätze, Einträge ohne
    „pro Tag“ (Zaubertricks, Pool-Zauber) je einer. Spontane Einträge und solche mit „pro Tag“ 0 bleiben außen vor."""
    erg = []
    for i, e in enumerate(liste):
        if e.get("spontan"):
            continue
        n = e.get("proTag")
        dom = ist_domaene(e)
        if n in (None, ""):
            erg.append({"quelle": i, "grad": int(e.get("grad") or 0), "name": e.get("name", ""), "art": "einzeln",
                        "domaene": dom, "pool": e.get("pool")})
        elif int(n) > 0:
            erg += [{"quelle": i, "grad": int(e.get("grad") or 0), "name": e.get("name", ""), "art": "platz",
                     "domaene": dom, "pool": e.get("pool")} for _ in range(int(n))]
    return erg


def ist_domaene(e):
    """Domänenzauber: Feld „domaene“ oder Namenszusatz „(D)“."""
    return bool(e.get("domaene")) or bool(re.search(r"\((?:d|dom|domäne)\)\s*$", e.get("name") or "", re.I))


def neu_vorbereiten(liste, namen):
    """Zauberliste mit neuen Namen für die Plätze aus plaetze(liste) (gleiche Reihenfolge) neu aufbauen.
    Unveränderte Zauber behalten ihre Angaben; neue Zauber bekommen nur Name/Grad/pro Tag (Mechanik aus dem Katalog)."""
    pl = plaetze(liste)
    if len(namen) != len(pl):
        raise ValueError("Anzahl der Plätze passt nicht (Zauberliste wurde inzwischen geändert)")
    je_quelle = {}
    for p, n in zip(pl, namen):
        n = re.sub(r"\s+", " ", (n or "").strip())[:80]
        if not n:
            raise ValueError(f"Grad {p['grad']}: leerer Platz")
        je_quelle.setdefault(p["quelle"], []).append((p, n))
    neu = []
    for i, e in enumerate(liste):
        if i not in je_quelle:
            neu.append(e)  # spontan oder pro Tag 0: unverändert
            continue
        for p, n in [x for x in je_quelle[i] if x[0]["art"] == "einzeln"]:
            neu.append(e if n.lower() == e["name"].lower() else _neuer_eintrag(e, n, None))
        zaehler = {}
        for p, n in [x for x in je_quelle[i] if x[0]["art"] == "platz"]:
            zaehler[n] = zaehler.get(n, 0) + 1
        for n, anzahl in zaehler.items():
            if n.lower() == e["name"].lower():
                neu.append({**e, "proTag": anzahl, "verbraucht": min(int(e.get("verbraucht") or 0), anzahl)})
            else:
                neu.append(_neuer_eintrag(e, n, anzahl))
    # gleiche Zauber desselben Grades (z. B. aus zwei alten Einträgen) zusammenfassen
    erg = []
    for e in neu:
        k = (e["name"].lower(), e.get("grad"), bool(e.get("domaene")), e.get("pool"), bool(e.get("spontan")))
        ziel = next((x for x in erg if (x["name"].lower(), x.get("grad"), bool(x.get("domaene")), x.get("pool"),
                                        bool(x.get("spontan"))) == k and x.get("proTag") not in (None, "")
                     and e.get("proTag") not in (None, "")), None)
        if ziel:
            ziel["proTag"] = int(ziel["proTag"]) + int(e["proTag"])
            ziel["verbraucht"] = int(ziel.get("verbraucht") or 0) + int(e.get("verbraucht") or 0)
        else:
            erg.append(dict(e))
    return sorted(erg, key=lambda e: int(e.get("grad") or 0))  # stabil: Reihenfolge je Grad bleibt


def _neuer_eintrag(alt, name, pro_tag):
    e = {"name": name, "grad": int(alt.get("grad") or 0), "proTag": pro_tag, "verbraucht": 0}
    if ist_domaene(alt):
        e["domaene"] = True  # Domänenplatz bleibt Domänenplatz (zählt nicht für spontanes Zaubern)
    if alt.get("pool"):
        e["pool"] = alt["pool"]
    return e
