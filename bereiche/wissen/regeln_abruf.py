"""Abruf und Aufbau der Regeldatenbank aus dem deutschen PRD (https://prd.5footstep.de, WackoWiki, OGL).

- Einfache HTTP-Abrufe mit Pause (1 s), Plattencache (regeln/cache/, nicht im ZIP) und ETag:
  bei der Aktualisierung bedingter Abruf → 304 = unverändert, nur geänderte/neue Seiten werden neu verarbeitet.
- robots.txt wird beachtet: keine Handler-Seiten (`/_…`, `/Seite/_…`), keine Systemseiten.
- Seitenbaum: ab der Startseite jedes Buchs, Links innerhalb des Buchpfads. Zauber/Zauberlisten ausgeschlossen
  (eigene Zauberdatenbank `zauber_db.py`).
- Viele Unterseiten (z. B. jeder Zustand, jede Waffe) sind im Kapitel bereits per Include enthalten. Sie werden an
  ihren Überschrift-Ankern erkannt und nur als „alias“ geführt (liefert die genauere Quellen-URL), nicht doppelt.
- Seiteninhalt wird als Blöcke in der Datenbank gespeichert → Index-Neuaufbau braucht kein Netz und keinen Cache.

Befehle:  python regeln_abruf.py aufbauen        (Erstaufbau; nutzt den Cache)
          python regeln_abruf.py aktualisieren   (bedingte Abrufe, nur Änderungen)
          python regeln_abruf.py index           (nur Index + Markdown aus der DB neu)
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bereiche.wissen import regeln_db
from bereiche.wissen import regeln_md

BASIS = Path(__file__).resolve().parents[2]  # Programmordner
REGELN = BASIS / "regeln"
CACHE = REGELN / "cache"
MD = REGELN / "md"
HOST = "https://prd.5footstep.de"
AGENT = "Spieltisch-Regeldatenbank/1.0 (privates Nachschlagewerk; robots.txt wird beachtet)"
PAUSE = 1.0
LIZENZ = ("Regeltexte: Pathfinder Referenzdokument (deutsch), https://prd.5footstep.de – Open Game Content "
          "unter der Open Game License 1.0a (siehe LIZENZ-REGELN.txt). Pathfinder ist eine Marke von Paizo Inc.; "
          "deutsche Übersetzung Ulisses Spiele. Inoffizielles, privates Nachschlagewerk.")

BUECHER = {
    "Grundregelwerk": {"start": "/Grundregelwerk",
                       "ohne": ["/Grundregelwerk/Zauber", "/Grundregelwerk/Zauberlisten"]},
    "Expertenregeln": {"start": "/Expertenregeln",
                       "ohne": ["/Expertenregeln/Zauber", "/Expertenregeln/Zauberlisten"]},
    "Monsterhandbuch": {"start": "/Monsterhandbuch", "ohne": []},
}
KAPITEL_NAMEN = {"Auf-Gehts": "Auf geht's", "WeitereRegeln": "Zusätzliche Regeln", "Spielleiten": "Spielleitung",
                 "Magische-Gegenstände": "Magische Gegenstände", "NSC-erschaffen": "NSC erschaffen",
                 "Fertigkeiten-erwerben": "Fertigkeiten erwerben"}
ROBOTS_VERBOTEN = ["/Einstellungen", "/Konto", "/Anmeldung", "/Registrierung", "/Passwort", "/Benutzer", "/Users",
                   "/Gruppen", "/Groups", "/LetzteKommentare", "/LetzteÄnderungen", "/LetzteAenderungen",
                   "/Kategorie", "/Template", "/Hilfe", "/Forum", "/admin.php", "/cache", "/lib"]


# ---------------------------------------------------------------- Pfade / robots
def pfad_norm(href):
    """Link -> normierter Seitenpfad (dekodiert, ohne Anker/Query, ohne Schrägstrich am Ende) oder None."""
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    href = href.replace("&amp;", "&")
    if href.startswith(HOST):
        href = href[len(HOST):]
    if not href.startswith("/") or "?" in href:
        return None
    p = urllib.parse.unquote(href.split("#")[0]).rstrip("/")
    return p or "/"


def erlaubt(pfad):
    if "/_" in pfad:
        return False
    return not any(pfad == v or pfad.startswith(v + "/") for v in ROBOTS_VERBOTEN)


def url(pfad):
    return HOST + urllib.parse.quote(pfad, safe="/-")


def im_buch(pfad, buch):
    b = BUECHER[buch]
    s = b["start"]
    if not (pfad == s or pfad.startswith(s + "/")):
        return False
    return erlaubt(pfad) and not any(pfad == o or pfad.startswith(o + "/") for o in b["ohne"])


# ---------------------------------------------------------------- HTTP
class Abrufer:
    """Holt Seiten mit Pause; Cache: regeln/cache/<hash>.html + cache/index.json (pfad -> etag, datei, zeit)."""

    def __init__(self, cache=CACHE, pause=PAUSE, meldung=print):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.idx_datei = self.cache / "index.json"
        self.idx = json.loads(self.idx_datei.read_text(encoding="utf-8")) if self.idx_datei.exists() else {}
        self.pause = pause
        self.meldung = meldung
        self._letzt = 0.0
        self.zaehler = {"abgerufen": 0, "unveraendert": 0, "cache": 0, "fehler": 0}

    def _speichern(self):
        tmp = self.idx_datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.idx, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.idx_datei)

    def datei(self, pfad):
        return self.cache / (hashlib.sha1(pfad.encode("utf-8")).hexdigest()[:20] + ".html")

    def holen(self, pfad, pruefen=False, etag=None):
        """-> (html|None, status) mit status 'cache' | 'neu' | 'gleich' (304) | 'fehlt'.
        Ohne `pruefen` aus dem Cache, falls vorhanden; mit `pruefen` bedingter Abruf per ETag."""
        e = self.idx.get(pfad)
        f = self.datei(pfad)
        if e and f.exists() and not pruefen:
            self.zaehler["cache"] += 1
            return f.read_text(encoding="utf-8"), "cache"
        warte = self.pause - (time.time() - self._letzt)
        if warte > 0:
            time.sleep(warte)
        kopf = {"User-Agent": AGENT, "Accept-Language": "de"}
        tag = etag or ((e or {}).get("etag") if f.exists() else None)
        if tag:
            kopf["If-None-Match"] = tag
        req = urllib.request.Request(url(pfad), headers=kopf)
        html = neu_tag = None
        for versuch in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    html = r.read().decode("utf-8", "replace")
                    neu_tag = r.headers.get("ETag")
                break
            except urllib.error.HTTPError as ex:
                self._letzt = time.time()
                if ex.code == 304:
                    self.zaehler["unveraendert"] += 1
                    return (f.read_text(encoding="utf-8") if f.exists() else None), "gleich"
                if ex.code in (403, 404, 410) or versuch == 2:
                    self.zaehler["fehler"] += 1
                    self.meldung(f"  Fehler {ex.code}: {pfad}")
                    return None, "fehlt"
            except (urllib.error.URLError, TimeoutError, ConnectionError) as ex:
                if versuch == 2:
                    self.zaehler["fehler"] += 1
                    self.meldung(f"  Netzfehler: {pfad}: {ex}")
                    return None, "fehlt"
            time.sleep(5 * (versuch + 1))
        self._letzt = time.time()
        f.write_text(html, encoding="utf-8")
        self.idx[pfad] = {"etag": neu_tag, "datei": f.name, "zeit": time.strftime("%Y-%m-%d %H:%M:%S")}
        self._speichern()
        self.zaehler["abgerufen"] += 1
        return html, "neu"


# ---------------------------------------------------------------- Seite zerlegen
def inhalt_html(html):
    """Nur der Seiteninhalt (section#section-content)."""
    m = re.search(r'<section id="section-content"[^>]*>(.*)</section>\s*<nav class="category"', html, re.S)
    if not m:
        m = re.search(r'<section id="section-content"[^>]*>(.*?)</section>', html, re.S)
    return m.group(1) if m else ""


def seite_zerlegen(pfad, html, buch):
    teile = pfad.strip("/").split("/")
    m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    titel = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else teile[-1].replace("-", " ")
    titel = regeln_md.text_norm(__import__("html").unescape(titel)).strip()
    bloecke = regeln_md.umwandeln(inhalt_html(html))
    anker = [b[3] for b in bloecke if b[0] == "h" and len(b) > 3 and b[3]]
    kap = teile[1] if len(teile) > 1 else ""
    js = json.dumps(bloecke, ensure_ascii=False)
    return {"pfad": pfad, "buch": buch, "kapitel": KAPITEL_NAMEN.get(kap, kap.replace("-", " ")) if kap else buch,
            "titel": titel, "url": url(pfad), "bloecke": js, "anker": json.dumps(anker),
            "hash": hashlib.sha1(js.encode("utf-8")).hexdigest()}


def links_im_buch(html, buch):
    return sorted({q for q in (pfad_norm(h) for h in re.findall(r'href="([^"]+)"', html)) if q and im_buch(q, buch)})


# ---------------------------------------------------------------- Aufbau / Aktualisierung
def _seite_speichern(con, s, etag):
    con.execute("""INSERT INTO seiten(pfad, buch, kapitel, titel, url, etag, abgerufen, rolle, bloecke, anker, hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(pfad) DO UPDATE SET buch=excluded.buch, kapitel=excluded.kapitel, titel=excluded.titel,
                   url=excluded.url, etag=excluded.etag, abgerufen=excluded.abgerufen, bloecke=excluded.bloecke,
                   anker=excluded.anker, hash=excluded.hash""",
                (s["pfad"], s["buch"], s["kapitel"], s["titel"], s["url"], etag, time.strftime("%Y-%m-%d %H:%M"),
                 "inhalt", s["bloecke"], s["anker"], s["hash"]))


def _klartext(bloecke_js):
    return re.sub(r"[^0-9a-zäöüß]+", "", " ".join(b[-1] if b[0] == "p" else "" for b in json.loads(bloecke_js)).lower())


def rollen_bestimmen(con):
    """Unterseiten, deren Inhalt (Anker bzw. Text) schon in einer anderen Seite steckt -> rolle 'alias'."""
    seiten = con.execute("SELECT id, pfad, anker, bloecke FROM seiten").fetchall()
    anker = {r["id"]: set(json.loads(r["anker"] or "[]")) for r in seiten}
    wo = {}  # anker -> Seiten-IDs
    for i, a in anker.items():
        for x in a:
            wo.setdefault(x, set()).add(i)
    pfad = {r["id"]: r["pfad"] for r in seiten}
    rolle = {}
    for r in seiten:
        i, a = r["id"], anker[r["id"]]
        if not json.loads(r["bloecke"]):
            rolle[i] = ("leer", None)
            continue
        if a:
            kand = set.intersection(*(wo[x] for x in a)) - {i}
            # Behälter: Seite mit mehr Ankern bzw. bei Gleichstand die mit kürzerem Pfad
            kand = [k for k in kand if len(anker[k]) > len(a) or (len(anker[k]) == len(a) and
                                                                  (len(pfad[k]), pfad[k]) < (len(pfad[i]), pfad[i]))]
            if kand:
                k = min(kand, key=lambda k: len(pfad[k]))
                rolle[i] = ("alias", pfad[k])
                continue
        rolle[i] = ("inhalt", None)
    # Seiten ohne Anker: Textvergleich mit den Inhaltsseiten
    texte = {r["id"]: _klartext(r["bloecke"]) for r in seiten if rolle[r["id"]][0] == "inhalt"}
    for r in seiten:
        i = r["id"]
        if rolle[i][0] == "inhalt" and not anker[i] and len(texte[i]) > 0:
            for k, t in texte.items():
                if k != i and len(t) > len(texte[i]) and texte[i] in t:
                    rolle[i] = ("alias", pfad[k])
                    break
    for i, (ro, von) in rolle.items():
        con.execute("UPDATE seiten SET rolle=?, alias_von=? WHERE id=?", (ro, von, i))
    con.commit()
    n = {}
    for ro, _ in rolle.values():
        n[ro] = n.get(ro, 0) + 1
    return n


def markdown_export(con, ziel=MD):
    """Inhaltsseiten als lesbare Markdown-Dateien mit Kopfdaten (regeln/md/<Buch>/<Pfad>.md)."""
    ziel = Path(ziel)
    alt = set(ziel.rglob("*.md")) if ziel.exists() else set()
    neu = set()
    for s in con.execute("SELECT * FROM seiten WHERE rolle='inhalt' ORDER BY pfad"):
        teile = s["pfad"].strip("/").split("/")
        f = ziel.joinpath(*teile[:-1], teile[-1] + ".md") if len(teile) > 1 else ziel / teile[0] / "index.md"
        if len(teile) > 1 and con.execute("SELECT 1 FROM seiten WHERE rolle='inhalt' AND pfad LIKE ? LIMIT 1",
                                          (s["pfad"] + "/%",)).fetchone():
            f = ziel.joinpath(*teile, "index.md")
        f.parent.mkdir(parents=True, exist_ok=True)
        kopf = (f"---\nbuch: {s['buch']}\nkategorie: {s['kapitel']}\ntitel: {s['titel']}\nurl: {s['url']}\n"
                f"abgerufen: {s['abgerufen']}\nlizenz: OGL 1.0a (Open Game Content, prd.5footstep.de)\n---\n\n")
        f.write_text(kopf + f"# {s['titel']}\n\n" + regeln_md.als_markdown(json.loads(s["bloecke"])), encoding="utf-8")
        neu.add(f)
    for f in alt - neu:
        f.unlink()
    return len(neu)


def index_bauen(con, meldung=print, md=True):
    n = regeln_db.index_neu_bauen(con)
    stand = time.strftime("%Y-%m-%d %H:%M")
    for k, v in (("schema", str(regeln_db.SCHEMA_VERSION)), ("gebaut", stand), ("quelle", HOST),
                 ("lizenz", LIZENZ), ("buecher", ", ".join(BUECHER))):
        con.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))
    con.commit()
    m = markdown_export(con) if md else 0
    con.execute("VACUUM")
    meldung(f"Index: {n} Abschnitte, {m} Markdown-Dateien")
    return n


def aufbauen(pruefen=False, meldung=print, db_datei=None, max_seiten=6000):
    """Seitenbaum abarbeiten. pruefen=False: Erstaufbau aus Cache/Netz. pruefen=True: Aktualisierung –
    Inhaltsseiten bedingt (ETag) abrufen, neue Links verfolgen, Alias-Seiten nicht erneut prüfen."""
    con = regeln_db.verbinden(db_datei or regeln_db.DB_DATEI, schreiben=True)
    con.executescript(regeln_db.SCHEMA)
    ab = Abrufer(meldung=meldung)
    bekannt = {r["pfad"]: r for r in con.execute("SELECT pfad, etag, rolle FROM seiten")}
    geaendert = 0
    for buch, b in BUECHER.items():
        start = b["start"]
        offen, gesehen, n = [start], {start}, 0
        while offen and n < max_seiten:
            p = offen.pop(0)
            alt = bekannt.get(p)
            if pruefen and alt and alt["rolle"] == "alias":
                continue  # Inhalt steckt in einer anderen Seite, die geprüft wird
            html, status = ab.holen(p, pruefen=pruefen and bool(alt), etag=(alt["etag"] if alt and pruefen else None))
            n += 1
            if n % 50 == 0:
                meldung(f"  {n} Seiten geprüft … {ab.zaehler}")
            if status == "fehlt":
                continue
            if html is not None and (status == "neu" or not alt or not pruefen):
                s = seite_zerlegen(p, html, buch)
                vorher = con.execute("SELECT hash FROM seiten WHERE pfad=?", (p,)).fetchone()
                if not vorher or vorher["hash"] != s["hash"]:
                    geaendert += 1
                _seite_speichern(con, s, (ab.idx.get(p) or {}).get("etag"))
            if html is not None:
                for q in links_im_buch(html, buch):
                    if q not in gesehen:
                        gesehen.add(q)
                        offen.append(q)
            elif pruefen and alt:
                # 304 ohne lokalen Cache: Kapitel-Seiten weiterverfolgen über die gespeicherten Unterseiten
                for q in bekannt:
                    if q.startswith(p + "/") and q.count("/") == p.count("/") + 1 and q not in gesehen:
                        gesehen.add(q)
                        offen.append(q)
        con.commit()
    rollen = rollen_bestimmen(con)
    meldung(f"Seiten: {rollen}; geändert/neu: {geaendert}; Abrufe: {ab.zaehler}")
    if geaendert or not pruefen or not con.execute("SELECT 1 FROM abschnitte LIMIT 1").fetchone():
        index_bauen(con, meldung)
    else:
        meldung("Keine Änderungen – Index unverändert.")
    con.close()
    return {"geaendert": geaendert, "rollen": rollen, **ab.zaehler}


def main():
    import sys
    befehl = sys.argv[1] if len(sys.argv) > 1 else "aufbauen"
    if befehl not in ("aufbauen", "aktualisieren", "index"):
        sys.exit("python regeln_abruf.py aufbauen | aktualisieren | index   (aufbauen/aktualisieren rufen das PRD ab)")
    if befehl == "index":
        c = regeln_db.verbinden(schreiben=True)
        c.executescript(regeln_db.SCHEMA)
        print(rollen_bestimmen(c))
        index_bauen(c)
    else:
        print(aufbauen(pruefen=(befehl == "aktualisieren")))


if __name__ == "__main__":
    main()
