"""Nachschlagen im Browser: Suche, Einträge, Inhaltsverzeichnis und Filterlisten für Regeln, Zauber, Monster und
Hausregeln (nur lesend, für die Seite web/nachschlagen.html über /api/wissen/…).

Spoilerschutz: Monster sind nur für den SL. Spieler sehen keine Seiten des Monsterhandbuchs, die einen Werteblock
enthalten (Beschreibung und Werte eines Monsters stehen dort zusammen), und keine Monsterlisten (Index,
Begegnungstabellen, Monster nach HG/Gelände). Allgemeine Monsterregeln, Kreaturenarten, Monster-Talente usw.
sind öffentlich. Ein gesperrter Eintrag löst `NurSL` aus (die Shell antwortet mit 403).
"""
import re

from bereiche.kern import Fehler

from . import regeln_db, zauber_db

# Seiten des Monsterhandbuchs ohne Werteblock, die trotzdem nur der SL sieht (Listen mit Monsternamen und HG)
SL_SEITEN = {"/Monsterhandbuch/Begegnungstabellen", "/Monsterhandbuch/Index", "/Monsterhandbuch/Index-der-Monstervarianten",
             "/Monsterhandbuch/Monster-nach-HG", "/Monsterhandbuch/Monster-nach-Geländeart",
             "/Monsterhandbuch/Monsterindex-nach-Art"}
MAX_ZEICHEN = 60000  # längere Einträge: Unterabschnitte danach nur noch als Verweis
MAX_TREFFER = 30
ZAUBER_FELDER = (("zeitaufwand", "Zeitaufwand"), ("komponenten", "Komponenten"), ("reichweite", "Reichweite"),
                 ("ziel", "Ziel"), ("effekt", "Effekt"), ("bereich", "Wirkungsbereich"),
                 ("wirkungsdauer", "Wirkungsdauer"), ("rettungswurf", "Rettungswurf"),
                 ("zauberresistenz", "Zauberresistenz"))
# Kreaturarten (MHB) und woran man sie in der Art-Zeile des Werteblocks erkennt („Großer Externar (Böse …)“)
KREATURARTEN = (("Monströser Humanoider", r"monstr\w* humanoid"), ("Magische Bestie", r"magisch\w* bestie"),
                ("Humanoider", r"humanoid"), ("Aberration", r"aberration"), ("Drache", r"drache"),
                ("Externar", r"externar"), ("Feenwesen", r"feenwesen"), ("Konstrukt", r"konstrukt"),
                ("Pflanze", r"pflanze"), ("Schlick", r"schlick"), ("Tier", r"\btiere?\b"), ("Ungeziefer", r"ungeziefer"),
                ("Untoter", r"untot"))


class NurSL(Fehler):
    """Eintrag ist nur für den SL (Spoilerschutz)."""


_gesperrt = {}


def gesperrte_seiten():
    """IDs der Seiten, die Spieler nicht sehen (Monsterseiten mit Werteblock und Monsterlisten)."""
    con = regeln_db.db()
    if con is None:
        return set()
    if id(con) not in _gesperrt:  # db() baut die Verbindung neu, wenn sich die Datei ändert
        ids = {r[0] for r in con.execute(
            "SELECT DISTINCT s.id FROM seiten s JOIN abschnitte a ON a.seite_id = s.id "
            "WHERE s.buch = 'Monsterhandbuch' AND a.typ = 'monster'")}
        ids |= {r[0] for r in con.execute("SELECT id FROM seiten WHERE pfad IN (%s)" % ",".join("?" * len(SL_SEITEN)),
                                          sorted(SL_SEITEN))}
        _gesperrt.clear()
        _gesperrt[id(con)] = ids
    return _gesperrt[id(con)]


def _sichtbar(seite_id, sl):
    return sl or seite_id not in gesperrte_seiten()


def _kuerzel(buch):
    return regeln_db.BUCH_KURZ.get(buch, buch)


# ---------------------------------------------------------------- Zauber

def _zauber_schule(z):
    s = z.get("schule") or ""
    if z.get("unterschule"):
        s += f" ({z['unterschule']})"
    if z.get("kategorie"):
        s += f" [{z['kategorie']}]"
    return s


def _zauber_grade(z, klasse=None):
    kl = z.get("klassen") or {}
    if klasse and klasse in kl:
        return f"{klasse} {kl[klasse]}"
    return ", ".join(f"{k} {g}" for k, g in sorted(kl.items(), key=lambda x: (x[1], x[0])))


def _zauber_treffer(z, klasse=None):
    return {"art": "zauber", "id": z["name"], "titel": z["name"], "untertitel": f"{_zauber_schule(z)} · {_zauber_grade(z, klasse)}",
            "buch": z.get("quelle") or "", "kuerzel": "Zauber", "schnipsel": z.get("kurz") or "", "url": z.get("url")}


def zauber_filtern(text=None, klasse=None, grad=None, schule=None, quelle=None, volltext=False):
    """Zauber nach Name (volltext: auch Kurz-/Langtext), Klasse (Name wie in der Zauberliste), Grad, Schule, Quelle."""
    t = (text or "").strip().lower()
    g = int(grad) if grad not in (None, "") else None
    erg = []
    for z in zauber_db.prd_liste():
        if t:
            ort = z["name"].lower()
            if volltext:
                ort += " " + (z.get("kurz") or "").lower() + " " + (z.get("text") or "").lower()
            if t not in ort:
                continue
        kl = z.get("klassen") or {}
        if klasse and klasse not in kl:
            continue
        if g is not None and (kl.get(klasse) != g if klasse else g not in kl.values()):
            continue
        if schule and schule.lower() != (z.get("schule") or "").lower():
            continue
        if quelle and quelle != (z.get("quelle") or ""):
            continue
        erg.append(z)
    if t:
        erg.sort(key=lambda z: (z["name"].lower() != t, not z["name"].lower().startswith(t), z["name"].lower()))
    else:
        erg.sort(key=lambda z: ((z.get("klassen") or {}).get(klasse, 0) if klasse else min((z.get("klassen") or {0: 0}).values()),
                                z["name"].lower()))
    return erg


def zauber_eintrag(name):
    """Vollständiger Zauber: Kopfzeilen (Schule, Grad, Zeitaufwand …), Langtext, Quelle."""
    z = zauber_db.prd_finden(name or "")
    if not z:
        raise Fehler(f"Zauber „{name}“ nicht gefunden")
    felder = [["Schule", _zauber_schule(z)], ["Grad", _zauber_grade(z)]]
    for k, titel in ZAUBER_FELDER:
        if z.get(k):
            felder.append([titel, z[k] + (f" (wie {z['wie']})" if k in (z.get("geerbt") or []) else "")])
    for k, v in (z.get("weitere") or {}).items():
        felder.append([k.capitalize(), v])
    return {"art": "zauber", "id": z["name"], "titel": z["name"], "felder": felder, "kurz": z.get("kurz") or "",
            "wie": z.get("wie"), "abschnitte": [{"id": None, "ebene": 0, "titel": None, "text": z.get("text") or ""}],
            "buch": z.get("quelle") or "", "quelle": (z.get("quelle") or "?") + (f", S. {z['seite']}" if z.get("seite") else ""),
            "url": z.get("url"), "eltern": [], "hausregeln": []}


# ---------------------------------------------------------------- Regeln und Monster

def _treffer_regel(t):
    art = "monster" if t["typ"] == "monster" else "regel"
    return {"art": art, "id": t["id"], "titel": t["titel"], "untertitel": t["pfad"] or t["kapitel"], "typ": t["typ"],
            "buch": t["buch"], "kuerzel": _kuerzel(t["buch"]), "schnipsel": t["schnipsel"], "url": t["url"]}


def kreaturart(art):
    """„Großer Externar (Böse, …)“ -> „Externar“ (Kreaturart ohne Größe und Unterarten), sonst ""."""
    a = re.sub(r"\s*\(.*", "", (art or "").lower())
    return next((name for name, muster in KREATURARTEN if re.search(muster, a)), "")


def monster_filtern(text=None, hg=None, art=None):
    """Monster aus der Tabelle des Monsterhandbuchs: Name enthält text, HG genau, art = Kreaturart (KREATURARTEN)."""
    con = regeln_db.db()
    if con is None:
        return []
    q, par = ("SELECT m.abschnitt_id AS id, m.name, m.hg, m.ep, m.art, a.buch, a.url, a.pfad FROM monster m "
              "JOIN abschnitte a ON a.id = m.abschnitt_id WHERE 1"), []
    if text:
        q += " AND lower(m.name) LIKE ?"
        par.append(f"%{text.strip().lower()}%")
    if hg not in (None, ""):
        w = regeln_db._hg_wert(str(hg))
        q += " AND abs(m.hg_wert - ?) < 0.001"
        par.append(w if w is not None else -1)
    rows = con.execute(q + " ORDER BY m.hg_wert, m.name", par).fetchall()
    if art:
        rows = [r for r in rows if kreaturart(r["art"]) == art or (art.lower() in (r["art"] or "").lower())]
    return [{"art": "monster", "id": r["id"], "titel": r["name"],
             "untertitel": f"HG {r['hg']} · {r['ep'] or '?'} EP · {r['art'] or ''}".strip(" ·"), "typ": "monster",
             "buch": r["buch"], "kuerzel": _kuerzel(r["buch"]), "schnipsel": "", "url": r["url"]} for r in rows]


def _abschnitte(r, max_zeichen=MAX_ZEICHEN):
    """Eintrag + Unterabschnitte als Liste {id, ebene, titel, text}; nach max_zeichen nur noch Titel (text None)."""
    aus = [{"id": r["id"], "ebene": 0, "titel": None, "text": r["text"] or ""}]
    summe = len(r["text"] or "")
    unter = regeln_db.unterabschnitte(r["id"])
    oben = min((s["stufe"] for s in unter), default=0) - 1  # oberste Unterüberschrift = Ebene 1
    for s in unter:
        voll = summe < max_zeichen
        aus.append({"id": s["id"], "ebene": s["stufe"] - oben, "titel": s["titel"],
                    "text": (s["text"] or "") if voll else None})
        summe += len(s["text"] or "") if voll else 0
    return aus


def _eltern(con, r):
    kette, e = [], r["eltern_id"]
    while e and len(kette) < 8:
        p = con.execute("SELECT id, titel, eltern_id FROM abschnitte WHERE id=?", (e,)).fetchone()
        if not p:
            break
        kette.insert(0, {"id": p["id"], "titel": p["titel"]})
        e = p["eltern_id"]
    return kette


def regel_eintrag(id_, sl=False, hausregeln=None):
    """Regel- oder Monstereintrag mit Unterabschnitten, Elternkette, Seite und passenden Hausregeln."""
    con = regeln_db.db()
    if con is None:
        raise Fehler(regeln_db.FEHLT)
    try:
        r = regeln_db.abschnitt(int(id_))
    except (TypeError, ValueError):
        r = None
    if not r:
        raise Fehler(f"Eintrag {id_} nicht gefunden")
    if not _sichtbar(r["seite_id"], sl):
        raise NurSL("Dieser Eintrag ist nur für den Spielleiter sichtbar (Monster).")
    anzeige = r
    if r["typ"] == "monster" and r["eltern_id"]:
        # Beschreibung steht oft neben dem Werteblock unter derselben Überschrift („Golem, Lehmgolem“)
        p = regeln_db.abschnitt(r["eltern_id"])
        if p and sum(1 for u in regeln_db.unterabschnitte(p["id"]) if u["typ"] == "monster") == 1:
            anzeige = p
    seite = con.execute("SELECT id, titel, pfad, url FROM seiten WHERE id=?", (r["seite_id"],)).fetchone()
    haus = []
    if hausregeln and r["typ"] != "monster":
        name = re.sub(r"\s*[\[(].*", "", r["titel"])
        haus = [{"id": f"H{h['_nr']}", "titel": h["titel"], "text": h["text"]}
                for h in regeln_db.hausregeln_suchen(hausregeln, name, 2)]
    m = con.execute("SELECT hg, ep, art FROM monster WHERE abschnitt_id=?", (r["id"],)).fetchone()
    return {"art": "monster" if r["typ"] == "monster" else "regel", "id": r["id"], "titel": r["titel"], "typ": r["typ"],
            "untertitel": (f"HG {m['hg']} · {m['ep'] or '?'} EP · {m['art']}" if m else (r["pfad"] or r["kapitel"])),
            "buch": r["buch"], "kuerzel": _kuerzel(r["buch"]), "kapitel": r["kapitel"], "url": r["url"],
            "quelle": f"PRD {r['buch']} › {r['kapitel']}",
            "seite": {"id": seite["id"], "titel": seite["titel"]} if seite else None,
            "eltern": _eltern(con, anzeige), "abschnitte": _abschnitte(anzeige), "hausregeln": haus,
            "anzeigeId": anzeige["id"]}


def name_eintrag(art, name, sl=False, hausregeln=None):
    """Eintrag zu einem Namen: art zustand | talent | fertigkeit | monster | regel."""
    tab = {"zustand": "zustaende", "talent": "talente", "fertigkeit": "fertigkeiten", "monster": "monster"}.get(art)
    if art == "monster" and not sl:
        raise NurSL("Monster sind nur für den Spielleiter sichtbar.")
    r, _ = regeln_db.titel_finden(name, tabelle=tab) if tab else (None, [])
    if not r:
        r, _ = regeln_db.titel_finden(name, typ="monster" if art == "monster" else None)
    if not r or not _sichtbar(r["seite_id"], sl):
        raise Fehler(f"„{name}“ nicht gefunden")
    return regel_eintrag(r["id"], sl, hausregeln)


def hausregel_eintrag(id_, hausregeln):
    r = regeln_db.hausregeln_abschnitte(hausregeln) if hausregeln else None
    nr = str(id_ or "").lstrip("Hh")
    treffer = [a for a in (r[0] if r else []) if str(a["_nr"]) == nr]
    if not treffer:
        raise Fehler(f"Hausregel {id_} nicht gefunden")
    a = treffer[0]
    return {"art": "hausregel", "id": f"H{a['_nr']}", "titel": a["titel"], "untertitel": " › ".join(a["pfad"][1:]),
            "buch": "Hausregeln", "kuerzel": "Hausregel", "quelle": "Hausregel dieser Kampagne (hat Vorrang)",
            "url": None, "eltern": [], "abschnitte": [{"id": None, "ebene": 0, "titel": None, "text": a["text"]}],
            "hausregeln": []}


def eintrag(art, id_=None, name=None, sl=False, hausregeln=None):
    """Ein Eintrag für die Leseansicht (art regel | monster | zauber | hausregel | zustand | talent | fertigkeit)."""
    if art == "zauber":
        return zauber_eintrag(name or id_)
    if art == "hausregel":
        return hausregel_eintrag(id_ or name, hausregeln)
    if art == "monster" and not sl:
        raise NurSL("Monster sind nur für den Spielleiter sichtbar.")
    if id_ not in (None, "") and str(id_).isdigit():
        return regel_eintrag(id_, sl, hausregeln)
    if name:
        return name_eintrag(art, name, sl, hausregeln)
    raise Fehler("Eintrag fehlt (id oder name)")


# ---------------------------------------------------------------- Suche

def suche(frage="", art="alle", buch=None, typ=None, sl=False, hausregeln=None, klasse=None, grad=None, schule=None,
          quelle=None, volltext=False, hg=None, monsterart=None):
    """Treffer für die Liste: Hausregeln zuerst, dann Zauber (Name), dann Regeln (Volltext). art alle | regeln |
    zauber | monster. Zauber und Monster lassen sich ohne Suchwort nur mit Filtern auflisten."""
    frage = (frage or "").strip()
    art = art or "alle"
    if art == "monster" and not sl:
        raise NurSL("Monster sind nur für den Spielleiter sichtbar.")
    treffer, gesamt = [], None
    if art == "zauber":
        if not (frage or klasse or grad not in (None, "") or schule or quelle):
            return {"treffer": [], "gesamt": 0, "hinweis": "Suchwort eingeben oder nach Klasse, Grad, Schule filtern."}
        zs = zauber_filtern(frage, klasse, grad, schule, quelle, volltext)
        return {"treffer": [_zauber_treffer(z, klasse) for z in zs[:500]], "gesamt": len(zs)}
    if art == "monster":
        ms = monster_filtern(frage, hg, monsterart)
        if frage and hg in (None, "") and not monsterart:  # dazu Volltext, z. B. „Gift Biss Spinne“
            ids = {m["id"] for m in ms}
            ms += [t for t in map(_treffer_regel, regeln_db.suchen(frage, typ="monster", max_treffer=MAX_TREFFER))
                   if t["id"] not in ids]
        return {"treffer": ms[:500], "gesamt": len(ms)}
    if not frage:
        return {"treffer": [], "gesamt": 0, "hinweis": "Suchwort eingeben."}
    if hausregeln and not buch:
        treffer += [{"art": "hausregel", "id": f"H{h['_nr']}", "titel": h["titel"], "untertitel": "Hausregel dieser Kampagne",
                     "buch": "Hausregeln", "kuerzel": "Hausregel", "schnipsel": h["schnipsel"], "url": None}
                    for h in regeln_db.hausregeln_suchen(hausregeln, frage, 3)]
    if art == "alle" and not buch and not typ:
        namen = regeln_db.zauber_hinweis(frage)
        zs = [zauber_db.prd_finden(n) for n in namen]
        zs += [z for z in zauber_filtern(frage)[:8] if z["name"] not in namen]
        treffer += [_zauber_treffer(z) for z in zs[:8] if z]
    gesperrt = set() if sl else gesperrte_seiten()
    for t in regeln_db.suchen(frage, buch=buch, typ=typ, max_treffer=MAX_TREFFER * (1 if sl else 2)):
        if t.get("seite") in gesperrt or (art == "regeln" and t["typ"] == "monster"):
            continue
        treffer.append(_treffer_regel(t))
        if sum(1 for x in treffer if x["art"] in ("regel", "monster")) >= MAX_TREFFER:
            break
    return {"treffer": treffer, "gesamt": gesamt if gesamt is not None else len(treffer)}


# ---------------------------------------------------------------- Inhaltsverzeichnis und Filter

def inhalt(seite_id=None, sl=False):
    """Ohne Seite: die Bücher mit ihren Kapiteln. Mit Seite: deren Abschnitte (Überschriften) und Unterseiten."""
    con = regeln_db.db()
    if con is None:
        raise Fehler(regeln_db.FEHLT)
    gesperrt = set() if sl else gesperrte_seiten()

    def unterseiten(pfad):
        rows = con.execute("SELECT id, titel, pfad FROM seiten WHERE rolle='inhalt' AND pfad LIKE ? ORDER BY titel",
                           (pfad.rstrip("/") + "/%",)).fetchall()
        tiefe = pfad.rstrip("/").count("/") + 1
        return [{"id": r["id"], "titel": r["titel"]} for r in rows
                if r["pfad"].count("/") == tiefe and r["id"] not in gesperrt]
    if not seite_id:
        buecher = con.execute("SELECT id, titel, pfad, buch FROM seiten WHERE rolle='inhalt' AND "
                              "length(pfad) - length(replace(pfad, '/', '')) = 1").fetchall()
        buecher = sorted(buecher, key=lambda r: regeln_db.BUCH_RANG.get(r["buch"], 9))
        return {"buecher": [{"id": b["id"], "titel": b["titel"], "kapitel": unterseiten(b["pfad"])} for b in buecher]}
    s = con.execute("SELECT * FROM seiten WHERE id=?", (int(seite_id),)).fetchone()
    if not s or s["rolle"] != "inhalt":
        raise Fehler("Seite nicht gefunden")
    if s["id"] in gesperrt:
        raise NurSL("Diese Seite ist nur für den Spielleiter sichtbar (Monster).")
    teile = s["pfad"].strip("/").split("/")
    kette = []
    for i in range(1, len(teile)):
        p = con.execute("SELECT id, titel FROM seiten WHERE pfad=?", ("/" + "/".join(teile[:i]),)).fetchone()
        if p:
            kette.append({"id": p["id"], "titel": p["titel"]})
    abschnitte = [{"id": r["id"], "stufe": r["stufe"], "titel": r["titel"], "typ": r["typ"]}
                  for r in con.execute("SELECT id, stufe, titel, typ FROM abschnitte WHERE seite_id=? ORDER BY nr", (s["id"],))]
    return {"seite": {"id": s["id"], "titel": s["titel"], "buch": s["buch"], "url": s["url"]}, "kette": kette,
            "abschnitte": abschnitte, "unterseiten": unterseiten(s["pfad"])}


def filter_listen(sl=False, hausregeln=None):
    """Auswahllisten der Seite: Bücher, Eintragstypen, Zauberklassen/-schulen/-quellen, Zustände, Zaubernamen;
    für den SL zusätzlich Kreaturenarten und HG der Monster."""
    con = regeln_db.db()
    zs = zauber_db.prd_liste()
    aus = {"sl": bool(sl), "datenbank": con is not None,
           "buecher": list(regeln_db.BUCH_KURZ),
           "typen": [], "zustaende": [], "zauberKlassen": sorted({k for z in zs for k in z.get("klassen") or {}}),
           "zauberSchulen": sorted({z["schule"] for z in zs if z.get("schule")}),
           "zauberQuellen": sorted({z["quelle"] for z in zs if z.get("quelle")}),
           "zauberNamen": sorted(z["name"] for z in zs),
           "hausregeln": bool(hausregeln and regeln_db.hausregeln_abschnitte(hausregeln)),
           "stand": regeln_db.meta().get("gebaut") if con is not None else None}
    if con is not None:
        aus["typen"] = sorted(r[0] for r in con.execute("SELECT DISTINCT typ FROM abschnitte")
                              if r[0] and (sl or r[0] != "monster"))
        aus["zustaende"] = sorted(r[0] for r in con.execute("SELECT name FROM zustaende"))
        if sl:
            aus["monsterArten"] = sorted({kreaturart(r[0]) for r in con.execute("SELECT art FROM monster")} - {""})
            aus["monsterHg"] = [r[0] for r in con.execute("SELECT hg FROM monster GROUP BY hg ORDER BY min(hg_wert)")]
    return aus
