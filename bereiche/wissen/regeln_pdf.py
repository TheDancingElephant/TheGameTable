"""Privater PDF-Index: eigene Regel- und Weltbücher (gekaufte PDFs) durchsuchbar machen.

Die Texte stammen aus gekauften PDFs und sind KEIN frei weitergebbarer Open Game Content. Der Index liegt deshalb
in einer eigenen Datei `regeln/privat.sqlite` (gleiches Schema wie `regeln.sqlite`), die nicht ins Git-Repo
(.gitignore) und nicht ins Weitergabe-ZIP kommt. Treffer erscheinen bei `regel_suchen` getrennt unter
„Private PDFs“ mit Buch und PDF-Seite; Einträge heißen P<n> (`regel_lesen(eintrag="P12")`).

Gliederung: Inhaltsverzeichnis des PDFs (Lesezeichen) plus große Schriftgrade als Überschriften, Werteblöcke
(„Name HG 4“) als eigene Einträge; lange Abschnitte werden an Seitenwechseln fortgesetzt. Kopf-/Fußzeilen und
Seitenzahlen werden entfernt, Silbentrennung am Zeilenende zusammengefügt.

    python regeln_abruf.py pdf "<Ordner oder PDF>" [...] [--ohne Muster]   (oder sl.py regeln-pdf …)
Erneuter Aufruf ohne Ordner: dieselben Quellen, nur geänderte PDFs werden neu gelesen.
"""
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

from . import regeln_db

PRIVAT = regeln_db.PRIVAT_DATEI
NEU_ABSCHNITT_AB = 3000  # Zeichen: danach beginnt an einem Seitenwechsel ein Fortsetzungs-Abschnitt


def _titel(pfad, doc):
    t = ((doc.metadata or {}).get("title") or "").strip()
    if t and not re.search(r"\.indd$|cover|kaufpdf", t, re.I):
        return t
    toc = doc.get_toc()
    if toc and toc[0][0] == 1 and len(toc[0][1]) > 3:
        return toc[0][1].strip()
    n = re.sub(r"^US\d+(?:PDF)?[_-]*", "", Path(pfad).stem)
    n = re.sub(r"(?i)[_-]*(LZ|meta|neu|komprimiert|kauf|pdf|kaufpdf|v\d)\b", "", n)
    n = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", n.replace("_", " "))
    return re.sub(r"\s+", " ", n).strip() or Path(pfad).stem


LIGATUREN = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def _ligaturen(t):
    """„Käﬁ g“ -> „Käfig“ (Ligatur aufgelöst, eingeschobenes Leerzeichen entfernt)."""
    t = re.sub("([ﬀ-ﬄ]) (?=[a-zäöüß])", r"\1", t)
    for lig, ers in LIGATUREN.items():
        t = t.replace(lig, ers)
    return t


def _zeilen(doc):
    """Je Seite: Liste (größe, fett, text, blocknummer)."""
    seiten = []
    for page in doc:
        zeilen = []
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = _ligaturen("".join(s["text"] for s in line["spans"]).replace("­", "")).strip()
                groesse = round(max(s["size"] for s in spans), 1)
                fett = all(("Bold" in s.get("font", "") or s.get("flags", 0) & 16) for s in spans)
                zeilen.append((groesse, fett, text, b.get("number", 0)))
        seiten.append(zeilen)
    return seiten


def bloecke_aus_pdf(doc):
    """PDF -> Blöcke im Format von regeln_md: ("h", stufe, text, anker) / ("p", text); anker = „S. <nr>“."""
    seiten = _zeilen(doc)
    groessen = Counter()
    haeufig = Counter()
    for zeilen in seiten:
        for g, _, t, _ in zeilen:
            groessen[g] += len(t)
        for t in {t for _, _, t, _ in zeilen}:
            haeufig[t] += 1
    if not groessen:
        return []
    text_groesse = groessen.most_common(1)[0][0]
    kopfzeilen = {t for t, n in haeufig.items() if n >= max(4, len(seiten) * 0.2)}
    toc = doc.get_toc()
    toc_tiefe = max((lv for lv, _, _ in toc), default=0)
    font_stufen = sorted({g for g, n in groessen.items() if g >= text_groesse + 3 and n >= 20}, reverse=True)[:2]
    # gleiche Großschrift-Zeile auf vielen Seiten = Zier-Kopfzeile, keine Überschrift
    gross_haeufig = Counter(t for zeilen in seiten for g, _, t, _ in zeilen if g >= text_groesse + 3)
    kopfzeilen |= {t for t, n in gross_haeufig.items() if n >= 5}
    stufe_fuer = {g: toc_tiefe + 2 + i for i, g in enumerate(font_stufen)}
    toc_je_seite = {}
    for lv, titel, s in toc:
        toc_je_seite.setdefault(s, []).append((lv + 1, titel.strip()))

    bloecke, absatz, letzter_block, abschnitt_len, letzter_titel = [], [], None, 0, ""
    tiefe_aktuell = 2

    def absatz_fertig():
        nonlocal absatz, abschnitt_len
        if absatz:
            t = ""
            for z in absatz:
                if t.endswith("-") and z[:1].islower():
                    t = t[:-1] + z  # Silbentrennung
                else:
                    t = (t + " " + z) if t else z
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                bloecke.append(("p", t))
                abschnitt_len += len(t)
            absatz = []

    def kopf(stufe, titel, seite):
        nonlocal abschnitt_len, letzter_titel, tiefe_aktuell
        absatz_fertig()
        bloecke.append(("h", stufe, titel, f"S. {seite}"))
        abschnitt_len, letzter_titel, tiefe_aktuell = 0, titel, stufe

    for nr, zeilen in enumerate(seiten, 1):
        toc_titel = [t.lower() for _, t in toc_je_seite.get(nr, [])]
        for stufe, titel in toc_je_seite.get(nr, []):
            kopf(stufe, titel, nr)
        if abschnitt_len > NEU_ABSCHNITT_AB and not toc_je_seite.get(nr):
            kopf(min(6, tiefe_aktuell + (0 if "(Forts." in letzter_titel else 1)),
                 re.sub(r"\s*\(Forts\..*\)$", "", letzter_titel) + f" (Forts. S. {nr})", nr)
        i = 0
        while i < len(zeilen):
            g, fett, t, blk = zeilen[i]
            if t in kopfzeilen or re.fullmatch(r"\d{1,3}", t):
                i += 1
                continue
            if regeln_db.MONSTER_KOPF.match(t) and fett and len(t) < 70:
                kopf(min(6, toc_tiefe + 4), t, nr)
                i += 1
                continue
            if g in stufe_fuer and len(t) < 90:
                teile = [t]
                while i + 1 < len(zeilen) and zeilen[i + 1][0] == g and len(" ".join(teile)) < 90:
                    i += 1
                    teile.append(zeilen[i][2])
                titel = re.sub(r"\s+", " ", " ".join(teile)).strip()
                if titel.lower() not in toc_titel:
                    kopf(stufe_fuer[g], titel, nr)
                letzter_block = None
                i += 1
                continue
            if blk != letzter_block:
                absatz_fertig()
                letzter_block = blk
            absatz.append(("**" + t + "**") if fett and len(t) < 60 and not absatz else t)
            i += 1
        absatz_fertig()
        letzter_block = None
    return bloecke


def _pdfs(quellen, ohne):
    dateien = []
    for q in quellen:
        q = Path(q)
        dateien += sorted(q.glob("*.pdf")) if q.is_dir() else ([q] if q.suffix.lower() == ".pdf" else [])
    namen = {d.stem for d in dateien}
    aus = []
    for d in dateien:
        if any(m.lower() in d.name.lower() for m in ohne):
            continue
        if not re.search(r"_V\d+$", d.stem) and any(n.startswith(d.stem + "_V") for n in namen):
            continue  # ältere Fassung, wenn eine _V2 daneben liegt
        aus.append(d)
    return aus


def einlesen(quellen=None, ohne=(), meldung=print, ziel=None, neu=False):
    """PDFs in den privaten Index übernehmen; nur neue/geänderte PDFs werden gelesen (neu=True: alle), Index danach neu."""
    import pymupdf
    ziel = Path(ziel or PRIVAT)
    con = regeln_db.verbinden(ziel, schreiben=True)
    con.executescript(regeln_db.SCHEMA)
    meta = {r["schluessel"]: r["wert"] for r in con.execute("SELECT * FROM meta")}
    if not quellen:
        quellen = json.loads(meta.get("quellen", "[]"))
        ohne = json.loads(meta.get("ohne", "[]"))
    if not quellen:
        raise ValueError("Keine PDF-Quellen angegeben (Ordner oder PDF-Dateien).")
    dateien = _pdfs(quellen, ohne)
    bekannt = {r["pfad"]: r["hash"] for r in con.execute("SELECT pfad, hash FROM seiten")}
    gelesen, gleich, leer = 0, 0, []
    behalten = set()
    for d in dateien:
        pfad = "pdf/" + d.name
        behalten.add(pfad)
        st = d.stat()
        kenn = hashlib.sha1(f"{d.name}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()
        if bekannt.get(pfad) == kenn and not neu:
            gleich += 1
            continue
        t0 = time.time()
        with pymupdf.open(d) as doc:
            titel = _titel(d, doc)
            bl = bloecke_aus_pdf(doc)
            seitenzahl = doc.page_count
        if sum(len(b[-2] if b[0] == "h" else b[1]) for b in bl) < 500:
            leer.append(d.name)
            continue
        con.execute("""INSERT INTO seiten(pfad, buch, kapitel, titel, url, etag, abgerufen, rolle, bloecke, anker, hash)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(pfad) DO UPDATE SET buch=excluded.buch, kapitel=excluded.kapitel,
                       titel=excluded.titel, url=excluded.url, abgerufen=excluded.abgerufen, bloecke=excluded.bloecke,
                       anker=excluded.anker, hash=excluded.hash, rolle='inhalt'""",
                    (pfad, titel, titel, titel, "pdf:" + d.name, None, time.strftime("%Y-%m-%d %H:%M"), "inhalt",
                     json.dumps(bl, ensure_ascii=False), "[]", kenn))
        gelesen += 1
        meldung(f"  {titel}: {seitenzahl} Seiten, {sum(1 for b in bl if b[0] == 'h')} Abschnitte "
                f"({time.time() - t0:.0f} s)")
    for pfad in set(bekannt) - behalten:
        con.execute("DELETE FROM seiten WHERE pfad=?", (pfad,))
    for k, v in (("quellen", json.dumps([str(q) for q in quellen], ensure_ascii=False)),
                 ("ohne", json.dumps(list(ohne), ensure_ascii=False)), ("art", "privat"),
                 ("hinweis", "Private Auszüge aus gekauften PDFs – nur für den eigenen Gebrauch, nicht weitergeben."),
                 ("gebaut", time.strftime("%Y-%m-%d %H:%M")), ("schema", str(regeln_db.SCHEMA_VERSION))):
        con.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))
    con.commit()
    n = regeln_db.index_neu_bauen(con)
    con.execute("VACUUM")
    con.close()
    bericht = f"Privater PDF-Index: {len(behalten) - len(leer)} PDFs, {n} Einträge (neu gelesen {gelesen}, unverändert {gleich})"
    if leer:
        bericht += f"; ohne Text übersprungen: {', '.join(leer)}"
    meldung(bericht)
    return bericht
