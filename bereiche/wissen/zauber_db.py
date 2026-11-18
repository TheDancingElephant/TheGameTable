"""Zauberdatenbank des Spieltisches.

Zwei Dateien unter <Programm>/daten:
  zauber_prd.json  vollständige Zauberliste aus dem deutschen PRD (prd.5footstep.de, OGL) – Nachschlagewerk
  zauber.json      Spielmechanik (modus, ziel, schaden …) für die Zauber, die das Tool selbst auswertet

`katalog()` vereint beides für den Server: jeder PRD-Zauber ist bekannt (modus "sl" = Spielleiter wertet aus),
die Mechanik aus zauber.json hat Vorrang. Eine kampagneneigene daten/zauber.json ersetzt die des Programms.
"""
import json
import re
from pathlib import Path

BASIS = Path(__file__).resolve().parents[2]  # Programmordner
PRD_DATEI = BASIS / "daten" / "zauber_prd.json"

# Namen aus der alten Mechanik-Datei, die im PRD anders heißen
ALIASE = {
    "blutungen stoppen": "Stabilisieren",
    "wahrer schlag": "Zielsicherer Schlag",
    "farbenspiel": "Sprühende Farben",
    "segen": "Segnen",
    "monsterfesthalten": "Monster festhalten",
    "monster herbeizaubern": "Monster herbeizaubern I",
    "mächtige betäubende barriere": "Betäubende Barriere, Mächtige",
}
# PRD-Angaben, die im Katalog unter "prd" stehen (die Schlüssel reichweite/ziel/effekt gehören der Mechanik)
PRD_FELDER = ("zeitaufwand", "komponenten", "reichweite", "ziel", "effekt", "bereich", "wirkungsdauer",
              "rettungswurf", "zauberresistenz")
KLASSEN_WOERTER = {  # Wortteile in Klassenangaben von Charakteren -> Klasse der Zauberliste
    "magier": "Magier", "wizard": "Magier", "hexenmeister": "Hexenmeister", "sorcerer": "Hexenmeister",
    "kleriker": "Kleriker", "cleric": "Kleriker", "druide": "Druide", "druid": "Druide", "barde": "Barde",
    "bard": "Barde", "skalde": "Skalde", "paladin": "Paladin", "antipaladin": "Antipaladin",
    "waldläufer": "Waldläufer", "ranger": "Waldläufer", "hexe": "Hexe", "witch": "Hexe", "inquisitor": "Inquisitor",
    "orakel": "Kleriker", "oracle": "Kleriker", "alchemist": "Alchemist", "kampfmagus": "Kampfmagus",
    "magus": "Kampfmagus", "paktmagier": "Paktmagier", "summoner": "Paktmagier",
    "arkanist": "Magier", "arcanist": "Magier", "schamane": "Schamane", "shaman": "Schamane",
    "blutwüter": "Blutwüter", "bloodrager": "Blutwüter", "jäger": "Jäger", "hunter": "Jäger",
    "mentalist": "Mentalist", "mesmerist": "Mesmerist", "okkultist": "Okkultist", "medium": "Medium",
    "spiritist": "Spiritist", "spiritualist": "Spiritist",
    # häufige Archetypen/Hybridklassen mit fremder Zauberliste
    "separatist": "Kleriker", "archivar": "Barde", "ermittler": "Alchemist", "investigator": "Alchemist",
    "stabmagus": "Kampfmagus",
}

_cache = {}


def _json(pfad):
    """JSON-Datei laden, neu einlesen nur bei Änderung."""
    pfad = Path(pfad)
    if not pfad.exists():
        return None
    mt = pfad.stat().st_mtime
    c = _cache.get(pfad)
    if not c or c[0] != mt:
        c = (mt, json.loads(pfad.read_text(encoding="utf-8")))
        _cache[pfad] = c
    return c[1]


def prd_liste():
    d = _json(PRD_DATEI)
    return d["zauber"] if d else []


def schluessel(name):
    """Vergleichsform eines Zaubernamens: klein, ohne Zusatz in Klammern wie „(D)“ für Domänenzauber."""
    n = re.sub(r"\s*\((?:d|dom|domäne|s|m)\)\s*$", "", (name or "").strip(), flags=re.I).lower()
    return re.sub(r"\s+", " ", n)


def prd_index():
    """name (Vergleichsform) -> PRD-Eintrag; doppelte Namen: Eintrag aus dem älteren Regelwerk zuerst."""
    d = _json(PRD_DATEI)
    if not d:
        return {}
    idx = d.get("_idx")
    if idx is None:
        idx = {}
        for z in d["zauber"]:
            idx.setdefault(schluessel(z["name"]), z)
        for alt, neu in ALIASE.items():
            if schluessel(neu) in idx:
                idx.setdefault(alt, idx[schluessel(neu)])
        d["_idx"] = idx
    return idx


def prd_finden(name):
    idx = prd_index()
    k = schluessel(name)
    if k in idx:
        return idx[k]
    k2 = re.sub(r"\s+verstärkt$|^verstärkte[rs]?\s+", "", k)  # „Sengender Strahl verstärkt“ (Metamagie)
    return idx.get(k2)


def klasse_der_liste(klassentext):
    """Erste Klasse aus einem Text wie „Barde 5“ oder „Kleriker 3/Magier 2“, für die es eine Zauberliste gibt."""
    t = (klassentext or "").lower()
    treffer = []
    # längere Wörter zuerst und Fundstelle ausblenden („antipaladin“ vor „paladin“, „paktmagier“ vor „magier“)
    for w in sorted(KLASSEN_WOERTER, key=len, reverse=True):
        pos = t.find(w)
        if pos >= 0:
            treffer.append((pos, KLASSEN_WOERTER[w]))
            t = t[:pos] + " " * len(w) + t[pos + len(w):]
    return min(treffer)[1] if treffer else None


def grad_fuer(z, klassentext):
    """Grad eines PRD-Zaubers für eine Charakterklasse (None, wenn nicht auf deren Liste)."""
    k = klasse_der_liste(klassentext)
    return (z.get("klassen") or {}).get(k) if k else None


def fuer_katalog(z):
    """PRD-Eintrag in Katalogform (ohne Langtext): Mechanik-Standard „sl“, PRD-Angaben unter "prd"."""
    e = {"name": z["name"], "grad": z.get("grad", 0), "schule": z.get("schule"), "klassen": z.get("klassen", {}),
         "klassenText": z.get("klassenText"), "modus": "sl", "ziel": "keins",
         "reichweite": z.get("reichweiteKurz", "nah"), "effekt": z.get("kurz", ""), "url": z.get("url"),
         "quelle": z.get("quelle"), "prd": {k: z[k] for k in PRD_FELDER if z.get(k)}}
    if z.get("unterschule"):
        e["unterschule"] = z["unterschule"]
    if z.get("kategorie"):
        e["kategorie"] = z["kategorie"]
    return e


def katalog(mechanik_datei):
    """name (klein) -> Katalogeintrag. PRD-Zauber als Grundlage, Mechanik aus zauber.json darüber."""
    mech = _json(mechanik_datei) or {"zauber": []}
    key = ("katalog", str(mechanik_datei))
    stand = (PRD_DATEI.stat().st_mtime if PRD_DATEI.exists() else 0, Path(mechanik_datei).stat().st_mtime
             if Path(mechanik_datei).exists() else 0)
    c = _cache.get(key)
    if c and c[0] == stand:
        return c[1]
    erg = {}
    for z in prd_liste():
        erg.setdefault(z["name"].lower(), fuer_katalog(z))
    for m in mech["zauber"]:
        p = prd_finden(m["name"])
        if p:
            basis = erg.get(p["name"].lower()) or fuer_katalog(p)
            neu = {**basis, **m, "schule": basis.get("schule") or m.get("schule")}
            erg[p["name"].lower()] = {**neu, "name": p["name"]}  # PRD-Name
            if m["name"].lower() != p["name"].lower():
                erg[m["name"].lower()] = {**neu, "aliasVon": p["name"]}  # alter Name bleibt nutzbar
        else:
            erg[m["name"].lower()] = dict(m)
    _cache[key] = (stand, erg)
    return erg


def katalog_finden(kat, name):
    """Eintrag im Katalog zu einem Namen aus einer Zauberliste (Alias, „(D)“, „verstärkt“ werden erkannt)."""
    n = (name or "").lower()
    if n in kat:
        return kat[n]
    p = prd_finden(name)
    return kat.get(p["name"].lower()) if p else None


# ------------------------------------------------------------------ Suche (für sl.py / MCP)

def suchen(text=None, klasse=None, grad=None, schule=None, volltext=False, max_treffer=40):
    """Zauber filtern. text: Teil des Namens (volltext=True: auch Kurz-/Langtext). klasse: z. B. „Barde“.
    grad: Zahl (mit klasse: Grad für diese Klasse, sonst irgendeine Klasse). Gibt (Treffer, Gesamtzahl) zurück."""
    t = (text or "").strip().lower()
    k = None
    if klasse:
        k = klasse_der_liste(klasse) or klasse.strip().capitalize()
    erg = []
    for z in prd_liste():
        if t:
            ort = z["name"].lower()
            if volltext:
                ort += " " + (z.get("kurz") or "").lower() + " " + (z.get("text") or "").lower()
            if t not in ort:
                continue
        kl = z.get("klassen") or {}
        if k and k not in kl:
            continue
        if grad is not None:
            if k and kl.get(k) != int(grad):
                continue
            if not k and int(grad) not in kl.values():
                continue
        if schule and schule.lower() not in (z.get("schule") or "").lower():
            continue
        erg.append(z)
    if t:  # exakte Treffer und Namensanfänge zuerst
        erg.sort(key=lambda z: (z["name"].lower() != t, not z["name"].lower().startswith(t), z["name"].lower()))
    elif k:
        erg.sort(key=lambda z: (z["klassen"].get(k, 0), z["name"].lower()))
    return erg[:max_treffer], len(erg)


def zeile(z, klasse=None):
    k = klasse_der_liste(klasse) if klasse else None
    grad = f"{k} {z['klassen'][k]}" if k and k in z.get("klassen", {}) else z.get("klassenText", "")
    sch = z.get("schule") or ""
    if z.get("unterschule"):
        sch += f" ({z['unterschule']})"
    if z.get("kategorie"):
        sch += f" [{z['kategorie']}]"
    return f"{z['name']} – {sch}; {grad}: {z.get('kurz', '')}"


def info(z, langtext=True):
    """Vollständiger Zauberblock als Text."""
    zeilen = [z["name"], f"Schule: {z.get('schule') or ''}"
              + (f" ({z['unterschule']})" if z.get("unterschule") else "")
              + (f" [{z['kategorie']}]" if z.get("kategorie") else ""),
              f"Grad: {', '.join(f'{k} {g}' for k, g in sorted(z.get('klassen', {}).items(), key=lambda x: (x[1], x[0])))}"]
    for k, t in (("zeitaufwand", "Zeitaufwand"), ("komponenten", "Komponenten"), ("reichweite", "Reichweite"),
                 ("ziel", "Ziel"), ("effekt", "Effekt"), ("bereich", "Wirkungsbereich"),
                 ("wirkungsdauer", "Wirkungsdauer"), ("rettungswurf", "Rettungswurf"),
                 ("zauberresistenz", "Zauberresistenz")):
        if z.get(k):
            zeilen.append(f"{t}: {z[k]}" + (f" (wie {z['wie']})" if k in (z.get("geerbt") or []) else ""))
    if z.get("wie"):
        zeilen.append(f"Funktioniert wie: {z['wie']}" + (" (fehlende Angaben von dort übernommen)" if z.get("geerbt") else ""))
    for k, v in (z.get("weitere") or {}).items():
        zeilen.append(f"{k.capitalize()}: {v}")
    zeilen.append(f"Kurz: {z.get('kurz', '')}")
    if langtext and z.get("text"):
        zeilen += ["", z["text"]]
    zeilen += ["", f"Quelle: {z.get('quelle') or '?'}" + (f", S. {z['seite']}" if z.get("seite") else "")
               + f" – {z.get('url', '')} (OGL)"]
    return "\n".join(zeilen)
