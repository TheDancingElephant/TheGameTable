"""Regel-Wissensdatenbank des Spieltisches (Pathfinder 1, deutsches PRD prd.5footstep.de, OGL).

Datei: <Programm>/regeln/regeln.sqlite (wird von `regeln_abruf.py` gebaut/aktualisiert).
Tabellen:
  meta(schluessel, wert)            Version, Baudatum, Quelle
  seiten(...)                       eine Zeile je abgerufener Wiki-Seite, Inhalt als Blöcke (JSON) -> Neuaufbau ohne Netz
  abschnitte(...)                   Einträge entlang der Überschriften (jedes Talent, jede Fertigkeit, jeder Zustand …)
  abschnitte_fts                    FTS5 über normalisierten, deutsch gestemmten Text (Titel stark gewichtet)
  titel_tri                         FTS5-Trigramm über Titel (Teilwort-Treffer, z. B. „angriff“ in „Gelegenheitsangriff“)
  talente / zustaende / fertigkeiten  strukturierte Schnellzugriffe
  vektoren(abschnitt_id, modell, dim, vektor)  reserviert für spätere Vektorsuche (Embeddings), derzeit leer

Hausregeln: <Kampagne>/sl/hausregeln.md wird bei jeder Suche mit durchsucht (eigener Index im Speicher,
neu bei Änderung der Datei) und hat Vorrang (Treffer stehen oben, markiert mit HAUSREGEL).
"""
import json
import re
import sqlite3
import threading
from pathlib import Path

BASIS = Path(__file__).resolve().parents[2]  # Programmordner
DB_DATEI = BASIS / "regeln" / "regeln.sqlite"
# Privater Index aus eigenen (gekauften) PDFs – nie ins Repo/ZIP, siehe regeln_pdf.py
PRIVAT_DATEI = BASIS / "regeln" / "privat.sqlite"
HOST = "https://prd.5footstep.de"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------- Normalisierung / Stemming (Snowball, deutsch)
_VOK = set("aeiouyäöü")
_S_END = set("bdfghklmnrt")
_ST_END = set("bdfghklmnt")


def _r1r2(w):
    def reg(start):
        for i in range(start + 1, len(w)):
            if w[i] not in _VOK and w[i - 1] in _VOK:
                return i + 1
        return len(w)
    r1 = reg(0)
    r2 = reg(r1) if r1 < len(w) else len(w)
    return max(r1, 3), r2


def stamm(wort):
    """Deutscher Snowball-Stemmer (vereinfacht korrekt nach snowballstem.org/algorithms/german)."""
    w = wort.lower().replace("ß", "ss")
    if len(w) <= 3:
        return w.replace("ä", "a").replace("ö", "o").replace("ü", "u")
    # u/y zwischen Vokalen markieren
    z = list(w)
    for i in range(1, len(z) - 1):
        if z[i] in "uy" and z[i - 1] in _VOK and z[i + 1] in _VOK:
            z[i] = z[i].upper()
    w = "".join(z)
    # Ergänzung: Partizip/3. Person auf -iert/-ierst wie Infinitiv -ieren behandeln (provoziert ~ provozieren)
    for suf in ("ierst", "iert", "ierte", "ierten"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            w = w[:-len(suf)] + "ieren"
            break
    r1, r2 = _r1r2(w)
    # Schritt 1
    for suf in ("ern", "em", "er"):
        if w.endswith(suf) and len(w) - len(suf) >= r1:
            w = w[:-len(suf)]
            break
    else:
        for suf in ("en", "es", "e"):
            if w.endswith(suf):
                if len(w) - len(suf) >= r1:
                    w = w[:-len(suf)]
                    if w.endswith("niss"):
                        w = w[:-1]
                break
        else:
            if w.endswith("s") and len(w) - 1 >= r1 and len(w) > 1 and w[-2] in _S_END:
                w = w[:-1]
    # Schritt 2
    for suf in ("est", "en", "er"):
        if w.endswith(suf) and len(w) - len(suf) >= r1:
            w = w[:-len(suf)]
            break
    else:
        if w.endswith("st") and len(w) - 2 >= r1 and len(w) > 5 and w[-3] in _ST_END:
            w = w[:-2]
    # Schritt 3
    def in_r2(n):
        return len(w) - n >= r2

    if w.endswith(("end", "ung")) and in_r2(3):
        w = w[:-3]
        if w.endswith("ig") and in_r2(2) and not w.endswith("eig"):
            w = w[:-2]
    elif w.endswith(("isch",)) and in_r2(4) and not w.endswith("eisch"):
        w = w[:-4]
    elif w.endswith(("ig", "ik")) and in_r2(2) and not w.endswith(("eig", "eik")):
        w = w[:-2]
    elif w.endswith(("lich", "heit")) and in_r2(4):
        w = w[:-4]
        if w.endswith(("er", "en")) and len(w) - 2 >= r1:
            w = w[:-2]
    elif w.endswith("keit") and in_r2(4):
        w = w[:-4]
        if w.endswith("lich") and in_r2(4):
            w = w[:-4]
        elif w.endswith("ig") and in_r2(2):
            w = w[:-2]
    return w.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u")


_WORT = re.compile(r"[0-9a-zäöüß]+", re.I)


def woerter(text):
    return _WORT.findall((text or "").lower())


def norm(text):
    """Text -> Folge gestemmter Wörter (für den FTS-Index)."""
    return " ".join(stamm(w) for w in woerter(text))


STOPP = set("""der die das den dem des ein eine einen einem einer eines und oder aber auch als am an auf aus bei bis
durch für gegen hat haben ich ihr im in ist kann können mit muss nach nicht noch nur ob sich sie so um unter vom von
vor was wann wer wie wird werden wo zu zum zur über man mein dein sein seine wenn dann es er gibt welche welcher welches
darf dürfen soll sollte bekommt erhält beim kein keine ja nein bitte regel regeln pathfinder pf1 prd""".split())

# Abkürzungen / Synonyme / englische Begriffe -> deutsche PRD-Begriffe (Ausdrücke mit Leerzeichen = Phrase)
SYNONYME = {
    "ga": ["gelegenheitsangriff"], "aoo": ["gelegenheitsangriff"], "rk": ["rüstungsklasse", "rk"],
    "kmb": ["kampfmanöverbonus", "kmb"], "kmv": ["kampfmanöververteidigung", "kmv"],
    "tp": ["trefferpunkte", "tp"], "tw": ["trefferwürfel", "tw"], "sg": ["schwierigkeitsgrad", "sg"],
    "gab": ["grund-angriffsbonus", "grundangriffsbonus", "gab"], "bab": ["grund-angriffsbonus", "grundangriffsbonus"],
    "rw": ["rettungswurf"], "zs": ["zauberstufe"], "zr": ["zauberresistenz"], "sr": ["schadensreduzierung"],
    "hg": ["herausforderungsgrad", "hg"], "ep": ["erfahrungspunkte", "ep"], "gm": ["goldmünzen", "gm"],
    "zm": ["zaubermerkmal"], "zäh": ["zähigkeitswurf", "zähigkeit"], "ref": ["reflexwurf", "reflex"],
    "wil": ["willenswurf", "willen"], "sl": ["spielleiter"], "sc": ["spielercharakter"], "nsc": ["nichtspielercharakter", "nsc"],
    "krit": ["kritischer treffer", "kritisch"], "flankieren": ["in die zange nehmen", "zange"],
    "flanke": ["in die zange nehmen", "zange"], "flanking": ["in die zange nehmen"],
    "5-fuß-schritt": ["1,50 m-schritt"], "fünf-fuß-schritt": ["1,50 m-schritt"],
    "flat-footed": ["auf dem falschen fuß erwischt"], "überrascht": ["überraschung", "auf dem falschen fuß erwischt"],
    "sneak": ["hinterhältiger angriff"], "hinterhältig": ["hinterhältiger angriff"],
    "full attack": ["voller angriff"], "haste": ["hast"], "mobility": ["beweglichkeit"],
    "stunning fist": ["betäubender schlag"], "helpless": ["hilflos"], "paralyzed": ["gelähmt"],
    "holy water": ["weihwasser"], "grapple": ["ringkampf"], "charge": ["sturmangriff"],
    "withdraw": ["rückzug"], "touch": ["berührungsangriff"], "dr": ["schadensreduzierung"],
    "concealment": ["tarnung"], "cover": ["deckung"], "prone": ["liegend"], "stunned": ["betäubt"],
    "staggered": ["wankend"], "nauseated": ["übelkeit"], "sickened": ["kränkelnd"], "shaken": ["erschüttert"],
    "frightened": ["verängstigt"], "panicked": ["panisch"], "dazed": ["benommen"], "fatigued": ["erschöpft"],
    "exhausted": ["entkräftet"], "entangled": ["verstrickt"], "grappled": ["im haltegriff", "ringend"],
    "pinned": ["festgehalten"], "blinded": ["blind"], "dazzled": ["geblendet"], "deafened": ["taub"],
    "confused": ["verwirrt"], "disabled": ["kampfunfähig"], "dying": ["sterbend"], "stable": ["stabilisiert"],
    "energy drain": ["negative stufen"], "ability damage": ["attributsschaden"], "swarm": ["schwarm"],
    "readied": ["vorbereiten"], "delay": ["abwarten"], "burn": ["zehrung"], "mythic": ["legendär"], "verzögern": ["abwarten", "verzögern"],
    "tragkraft": ["traglast", "tragkraft"], "belastung": ["traglast", "belastung"], "aid another": ["jemand anderem helfen"],
    "take 10": ["10 nehmen"], "take 20": ["20 nehmen"], "spell resistance": ["zauberresistenz"],
    "concentration": ["konzentration"], "defensiv zaubern": ["defensiv zaubern", "konzentration"],
    "coup de grace": ["coup de grace", "gnadenstoß"], "gnadenstoss": ["coup de grace"], "gnadenstoß": ["coup de grace"],
    "nat 20": ["natürliche 20"], "rüstungsmalus": ["rüstungsmalus", "rüstungsmalus auf fertigkeiten"],
}
PHRASEN = sorted((k for k in SYNONYME if " " in k), key=len, reverse=True)
GROSS_ABK = {"ST": "stärke", "GE": "geschicklichkeit", "KO": "konstitution", "IN": "intelligenz", "WE": "weisheit",
             "CH": "charisma"}


def _alt_ausdruck(text):
    """Ein Begriff -> FTS-Ausdruck über gestemmte Wörter (einzeln mit Präfix, mehrere als Phrase)."""
    ws = [stamm(w) for w in woerter(text)]
    ws = [w for w in ws if w]
    if not ws:
        return None
    if len(ws) == 1:
        return f'"{ws[0]}"*' if len(ws[0]) >= 3 else f'"{ws[0]}"'
    return '"' + " ".join(ws) + '"'


def anfrage_gruppen(frage):
    """Frage -> Liste von Gruppen (jede Gruppe = Liste alternativer FTS-Ausdrücke) + Liste der Kernstämme."""
    roh = frage or ""
    gruppen, stamme = [], []
    for k, v in GROSS_ABK.items():
        roh = re.sub(rf"\b{k}\b", v, roh)
    t = roh.lower()
    for ph in PHRASEN:
        if ph in t:
            t = t.replace(ph, " ")
            alts = [a for a in (_alt_ausdruck(x) for x in SYNONYME[ph]) if a]
            gruppen.append(list(dict.fromkeys(alts)))
            stamme += [stamm(w) for x in SYNONYME[ph][:1] for w in woerter(x)]
    for tok in re.findall(r"[0-9a-zäöüß][0-9a-zäöüß,\-]*", t):
        tok = tok.strip("-,")
        if not tok or tok in STOPP:
            continue
        if tok in SYNONYME:
            alts = [_alt_ausdruck(x) for x in SYNONYME[tok]] + [_alt_ausdruck(tok)]
            stamme += [stamm(w) for w in woerter(SYNONYME[tok][0])]
        else:
            alts = [_alt_ausdruck(tok)]
            stamme += [stamm(w) for w in woerter(tok)]
        alts = [a for a in dict.fromkeys(alts) if a]
        if alts:
            gruppen.append(alts)
    return gruppen, [s for s in stamme if s and s not in STOPP]


# ---------------------------------------------------------------- Abschnitte aus Seitenblöcken
# Fett gesetzte Stichworte, an denen lange Abschnitte NICHT geteilt werden (Feldnamen von Talenten, Fertigkeiten, Giften …)
FELD_LABELS = {"voraussetzung", "voraussetzungen", "vorteil", "normal", "speziell", "spezial", "art", "rettungswurf",
               "inkubationszeit", "frequenz", "effekt", "heilung", "preis", "gewicht", "probe", "aktion",
               "wiederholungsversuch", "ungeübt", "synergie", "hinweis", "beispiel", "aura", "zs", "ausrüstungsplatz",
               "herstellung", "kosten", "erschaffungsvoraussetzungen", "erschaffung", "beschreibung", "anforderungen",
               "fertigkeiten", "trefferwürfel", "fertigkeitspunkte pro stufe", "klassenfertigkeiten", "gesinnung",
               "attribute", "hg", "ep", "zauber", "reichweite", "ziel", "wirkungsdauer", "fertigkeitsränge",
               "format"}  # „Format:“ = Schreibweise im Werteblock (Allgemeine Monsterregeln)
_LABEL = re.compile(r"^\s*(\*\*|\*)([^*\n]{2,80}?)\1\s*")
TEILEN_AB = 1200  # Zeichen: längere Abschnitte werden an Stichworten in Unter-Einträge geteilt


def _label(absatz):
    """„**Stichwort:** Text“ bzw. „*Stichwort:* Text“ -> Stichwort (ohne Doppelpunkt), sonst None."""
    m = _LABEL.match(absatz)
    if not m:
        return None
    innen, rest = m.group(2).strip(), absatz[m.end():]
    if innen.endswith(":"):
        t = innen[:-1].strip()
    elif rest.startswith(":"):
        t = innen
    else:
        return None
    if len(t) < 3 or t.lower() in FELD_LABELS:
        return None
    return t


def abschnitte_aus_bloecken(bloecke, seiten_titel, teilen=True):
    """Blöcke -> Liste von Abschnitten {stufe, titel, anker, eltern(index), pfad[list], text, label}.
    Lange Abschnitte mit mehreren fett gesetzten Stichworten („**Hinterhältiger Angriff (AF):** …“) werden in
    Unter-Einträge geteilt; der Abschnitt behält den Text vor dem ersten Stichwort."""
    aus, stapel, cur = [], [], None
    for b in bloecke:
        if b[0] == "h":
            stufe, titel, anker = b[1], b[2], (b[3] if len(b) > 3 else None)
            while stapel and aus[stapel[-1]]["stufe"] >= stufe:
                stapel.pop()
            eltern = stapel[-1] if stapel else None
            cur = {"stufe": stufe, "titel": titel, "anker": anker, "eltern": eltern,
                   "pfad": [aus[i]["titel"] for i in stapel], "teile": []}
            aus.append(cur)
            stapel.append(len(aus) - 1)
        else:
            if cur is None:  # Text vor der ersten Überschrift = Einleitung der Seite (kein Elternteil)
                cur = {"stufe": 1, "titel": seiten_titel, "anker": None, "eltern": None, "pfad": [], "teile": []}
                aus.append(cur)
            cur["teile"].append(b[1])
    if not teilen:
        for a in aus:
            a["text"] = "\n\n".join(a.pop("teile"))
            a["label"] = False
        return aus
    neu, umbau = [], {}
    for alt_i, a in enumerate(aus):
        teile = a.pop("teile")
        a["eltern"] = umbau.get(a["eltern"]) if a["eltern"] is not None else None
        a["label"] = False
        labels = [(i, _label(p)) for i, p in enumerate(teile)]
        labels = [(i, t) for i, t in labels if t]
        # Listen je Klasse („Optionen zur bevorzugten Klasse“: **Alchemist:** …) bleiben ein Eintrag
        if sum(len(p) for p in teile) > TEILEN_AB and len(labels) >= 2 and "bevorzugte" not in a["titel"].lower():
            erster = labels[0][0]
            a["text"] = "\n\n".join(teile[:erster])
            neu.append(a)
            umbau[alt_i] = len(neu) - 1
            ich = len(neu) - 1
            for k, (i, t) in enumerate(labels):
                ende = labels[k + 1][0] if k + 1 < len(labels) else len(teile)
                neu.append({"stufe": a["stufe"] + 1, "titel": t, "anker": a["anker"], "eltern": ich,
                            "pfad": a["pfad"] + [a["titel"]], "text": "\n\n".join(teile[i:ende]), "label": True})
        else:
            a["text"] = "\n\n".join(teile)
            neu.append(a)
            umbau[alt_i] = len(neu) - 1
    return neu


def _hg_wert(hg):
    try:
        z, _, n = hg.partition("/")
        return float(z) / float(n) if n else float(z)
    except ValueError:
        return None


def _monster_kopf(text):
    """EP und Art (z. B. „Großes Konstrukt“) aus dem Kopf des Werteblocks."""
    m = re.search(r"\*\*EP\s*([\d.]+)\*\*", text)
    ep = int(m.group(1).replace(".", "")) if m else None
    art = ""
    rest = text[m.end():] if m else text
    for zeile in rest.split("\n")[:3]:
        z = zeile.replace("*", "").strip()
        m2 = re.match(r"^(RG|NG|CG|RN|N|CN|RB|NB|CB|Beliebig|Jede|immer \S+)\s+(.+)$", z)
        if m2:
            art = m2.group(2).strip()
            break
    return ep, art


def _feld(text, name):
    m = re.search(rf"\*\*{name}[^*:]*:\*\*\s*(.*?)(?=\n\*\*[A-ZÄÖÜ][^*\n]{{0,40}}:\*\*|\n\n|$)", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


TALENTART_KLAMMER = re.compile(r"\s*\(((?:Kampf|Metamagie|Metamagisch|Erschaffung|Gegenstandserschaffung|Kritischer[- ]Treffer"
                               r"|Gemeinschaft|Gemeinschaftstalent|Stil|Leistung|Gruppe|Legende)(?:\s*,\s*[^)]+)?)\s*\)\s*$")


# „Name HG 5“, legendär „Name HG 9 (LG 3)“ (Ausbauregeln V: Legenden)
MONSTER_KOPF = re.compile(r"^(.+?)\s+HG\s+(\d+(?:/\d+)?)(?:\s*\(LG\s*(\d+)\))?\s*$")


# Klassen, die in einem Buch als eigenes Kapitel stehen (Ausbauregeln: Magie / II: Kampf)
KLASSEN_KAPITEL = ("Kampfmagus", "Ninja", "Samurai", "Schütze")
# Ausbauregeln III: Völker – je Volk eine Seite unter diesen Kapiteln
VOLK_KAPITEL = ("Grundvölker", "Ungewöhnliche Völker", "Seltene Völker")


def typ_bestimmen(kapitel, a, seiten_titel=""):
    pf = " / ".join(a["pfad"])
    t = a["titel"]
    # erster Abschnitt einer Einzelseite (Klasse, Fertigkeit, Gegenstand …); Titel weicht manchmal ab („Wissenhüter“)
    kopf = not a["pfad"] and (t.lower() == (seiten_titel or "").lower() or a.get("erster"))
    seitenkopf = a.get("seiten_ebene") == 2 and kopf
    if kapitel in KLASSEN_KAPITEL and not a["pfad"] and t == kapitel:  # Ausbauregeln: Klasse als eigenes Kapitel
        return "klasse"
    if kapitel == "Klassen" and kopf and a.get("eltern_seite") == "Basisklassen":  # Expertenregeln: neue Klassen
        return "klasse"
    if t.startswith("Tabelle"):
        return "tabelle"
    if MONSTER_KOPF.match(t):  # Werteblock: Kreatur (mit TP) oder Falle (Fallen im Kapitel Spielleitung)
        return "monster" if "**TP**" in (a.get("text") or "") else "falle"
    if kapitel == "Talente" and "Talentbeschreibungen" in pf:
        return "talent"
    if kapitel in ("Talente", "Legendäre Talente") and a["pfad"] and "Talentarten" not in a["pfad"] \
            and re.search(r"\*\*(Vorteil|Voraussetzung)", a.get("text") or ""):
        return "talent"  # Ausbauregeln III–VII: nach Volk gruppiert bzw. ohne Überschrift „Talentbeschreibungen“
    if "Zustände" in a["pfad"] and kapitel == "Anhang":
        return "zustand"
    if kapitel == "Fertigkeiten" and seitenkopf:
        return "fertigkeit"
    if kapitel == "Klassen" and seitenkopf and t not in ("Grundklassen", "Basisklassen"):
        return "klasse"
    if kapitel == "Prestigeklassen" and seitenkopf:
        return "prestigeklasse"
    if kapitel in VOLK_KAPITEL and seitenkopf:
        return "volk"
    if kapitel == "Völker" and (seitenkopf or (a["stufe"] == 2 and a.get("seiten_ebene") == 1 and not a["pfad"]
                                              and t not in ("Völker", "Grundvölker"))):
        return "volk"
    if kapitel in ("Klassen", "Prestigeklassen", "NSC Klassen", *KLASSEN_KAPITEL) and a.get("label"):
        return "klassenmerkmal"
    if kapitel == "Ausrüstung" and seitenkopf:
        return "gegenstand"
    return "regel"


# ---------------------------------------------------------------- Datenbank
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(schluessel TEXT PRIMARY KEY, wert TEXT);
CREATE TABLE IF NOT EXISTS seiten(
  id INTEGER PRIMARY KEY, pfad TEXT UNIQUE, buch TEXT, kapitel TEXT, titel TEXT, url TEXT, etag TEXT,
  abgerufen TEXT, rolle TEXT, alias_von TEXT, anker TEXT, bloecke TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS abschnitte(
  id INTEGER PRIMARY KEY, seite_id INTEGER, nr INTEGER, stufe INTEGER, titel TEXT, pfad TEXT, typ TEXT,
  buch TEXT, kapitel TEXT, url TEXT, eltern_id INTEGER, text TEXT, zeichen INTEGER);
CREATE INDEX IF NOT EXISTS abschnitte_seite ON abschnitte(seite_id, nr);
CREATE INDEX IF NOT EXISTS abschnitte_eltern ON abschnitte(eltern_id);
CREATE VIRTUAL TABLE IF NOT EXISTS abschnitte_fts USING fts5(titel, pfad, text, content='', columnsize=1,
  tokenize='unicode61 remove_diacritics 0');
CREATE VIRTUAL TABLE IF NOT EXISTS titel_tri USING fts5(titel, tokenize='trigram');
CREATE VIRTUAL TABLE IF NOT EXISTS abschnitte_vocab USING fts5vocab(abschnitte_fts, 'row');
CREATE TABLE IF NOT EXISTS talente(abschnitt_id INTEGER PRIMARY KEY, name TEXT, arten TEXT, voraussetzungen TEXT,
  vorteil TEXT);
CREATE TABLE IF NOT EXISTS zustaende(abschnitt_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS fertigkeiten(abschnitt_id INTEGER PRIMARY KEY, name TEXT, attribut TEXT, zusatz TEXT);
CREATE TABLE IF NOT EXISTS monster(abschnitt_id INTEGER PRIMARY KEY, name TEXT, hg TEXT, hg_wert REAL, ep INTEGER,
  art TEXT);
CREATE TABLE IF NOT EXISTS vektoren(abschnitt_id INTEGER, modell TEXT, dim INTEGER, vektor BLOB,
  PRIMARY KEY(abschnitt_id, modell));
"""


def verbinden(pfad=None, schreiben=False):
    pfad = Path(pfad or DB_DATEI)
    if not schreiben and not pfad.exists():
        return None
    if schreiben:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(pfad))
    else:
        con = sqlite3.connect(f"file:{pfad.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def index_neu_bauen(con):
    """abschnitte + FTS + Schnelltabellen aus seiten (rolle='inhalt') komplett neu aufbauen."""
    cur = con.cursor()
    for t in ("abschnitte", "talente", "zustaende", "fertigkeiten", "monster"):
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM vektoren")  # IDs ändern sich beim Neuaufbau
    cur.execute("INSERT INTO abschnitte_fts(abschnitte_fts) VALUES('delete-all')")
    cur.execute("DELETE FROM titel_tri")
    # Anker der Alias-Seiten -> deren URL (genauere Quellenangabe, z. B. Zustand „Hilflos“ als eigene Seite)
    alias_url = {}
    for r in cur.execute("SELECT url, anker FROM seiten WHERE rolle='alias' AND anker IS NOT NULL"):
        for an in json.loads(r["anker"] or "[]")[:1]:
            alias_url.setdefault(an, r["url"])
    seiten = cur.execute("SELECT * FROM seiten WHERE rolle='inhalt' ORDER BY pfad").fetchall()
    aid = 0
    for s in seiten:
        bloecke = json.loads(s["bloecke"])
        teile = s["pfad"].strip("/").split("/")
        ebene = len(teile) - 1
        ab = abschnitte_aus_bloecken(bloecke, s["titel"])
        ids = []
        for nr, a in enumerate(ab):
            aid += 1
            ids.append(aid)
            a["seiten_ebene"] = ebene
            a["erster"] = nr == 0
            a["eltern_seite"] = teile[-2] if len(teile) > 2 else ""
            if ebene >= 2 and not a["pfad"] and a["titel"] != s["titel"] and nr == 0:
                pass
            seitenpfad = [x.replace("-", " ") for x in teile[1:-1]] if ebene >= 2 else []
            teile_pfad = []
            for x in seitenpfad + [s["titel"]] + a["pfad"]:
                if not teile_pfad or teile_pfad[-1].lower() != x.lower():  # „Schurke › Schurke“ zusammenfassen
                    teile_pfad.append(x)
            if teile_pfad and teile_pfad[-1] == a["titel"]:
                teile_pfad.pop()
            pfad = " › ".join(teile_pfad)
            typ = typ_bestimmen(s["kapitel"], a, s["titel"])
            mk = MONSTER_KOPF.match(a["titel"]) if typ in ("monster", "falle") else None
            if mk:
                a["titel"] = f"{mk.group(1).strip()} (HG {mk.group(2)}" + (f", LG {mk.group(3)})" if mk.group(3) else ")")
            if typ == "klasse" and a["titel"].isupper():  # Ausbauregeln VI: „ATTENTÄTER“ -> Seitentitel
                a["titel"] = s["titel"]
            url = alias_url.get(a["anker"]) or (s["url"] + ("#" + a["anker"] if a["anker"] else ""))
            eltern = ids[a["eltern"]] if a["eltern"] is not None else None
            cur.execute("INSERT INTO abschnitte VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, s["id"], nr, a["stufe"], a["titel"], pfad, typ, s["buch"], s["kapitel"], url, eltern,
                         a["text"], len(a["text"])))
            cur.execute("INSERT INTO abschnitte_fts(rowid, titel, pfad, text) VALUES(?,?,?,?)",
                        (aid, norm(a["titel"]), norm(pfad), norm(a["text"])))
            cur.execute("INSERT INTO titel_tri(rowid, titel) VALUES(?,?)", (aid, a["titel"].lower()))
            name = re.sub(r"\s*\[[^\]]*\]\s*", " ", a["titel"]).strip()
            if typ == "talent":
                arten = [x.strip() for x in re.findall(r"\[([^\]]+)\]", a["titel"])]
                m = TALENTART_KLAMMER.search(name)  # Expertenregeln: „Abschiedsschuss (Kampf)“
                if m:
                    arten.append(m.group(1).strip())
                    name = name[:m.start()].strip()
                arten = ", ".join(arten)
                cur.execute("INSERT INTO talente VALUES(?,?,?,?,?)",
                            (aid, name, arten, _feld(a["text"], "Voraussetzung"), _feld(a["text"], "Vorteil")))
            elif typ == "zustand":
                cur.execute("INSERT INTO zustaende VALUES(?,?)", (aid, name))
            elif typ == "fertigkeit":
                m = re.match(r"(.*?)\s*\((.*)\)\s*$", a["titel"])
                nm, zus = (m.group(1), m.group(2)) if m else (a["titel"], "")
                m2 = re.match(r"\s*\*{0,2}\(([^)]*)\)", a["text"])  # „**(GE; Rüstungsmalus)**“ am Textanfang
                if m2 and not zus:
                    zus = m2.group(1).strip()
                attr = (re.match(r"\s*([A-ZÄÖÜa-zäöü]+)", zus).group(1) if zus else "")
                cur.execute("INSERT INTO fertigkeiten VALUES(?,?,?,?)", (aid, nm.strip(), attr, zus))
            elif typ == "monster" and mk:
                cur.execute("INSERT INTO monster VALUES(?,?,?,?,?,?)", (aid, mk.group(1).strip(), mk.group(2),
                                                                         _hg_wert(mk.group(2)), *_monster_kopf(a["text"])))
    con.commit()
    return aid


# ---------------------------------------------------------------- Suche
_tls = threading.local()


def db(datei=None):
    """Lesende Verbindung (Standard: PRD-Datenbank; datei=PRIVAT_DATEI: privater PDF-Index), neu bei Änderung."""
    datei = Path(datei or DB_DATEI)
    if not datei.exists():
        return None
    mt = datei.stat().st_mtime
    alle = getattr(_tls, "c", None)  # je Thread und Datei eine Verbindung (MCP ruft Tools in eigenen Threads auf)
    if not isinstance(alle, dict):
        alle = _tls.c = {}
    c = alle.get(str(datei))
    if c is None or c[0] != mt:
        if c is not None:
            try:
                c[1].close()
            except Exception:
                pass
        c = alle[str(datei)] = (mt, verbinden(datei))
    return c[1]


def _praefix(datei):
    return "P" if datei and Path(datei) == PRIVAT_DATEI else ""


def _fts_ausdruck(gruppen, und=True):
    teile = ["(" + " OR ".join(g) + ")" for g in gruppen if g]
    return (" AND " if und else " OR ").join(teile)


def _schnipsel(text, stamme, laenge=320):
    """Absatz mit den meisten Treffern, gekürzt um die erste Fundstelle."""
    absaetze = [p for p in re.split(r"\n\n+|\n(?=\s*[-*] |\s*\d+\. )", text or "") if p.strip()]
    if not absaetze:
        return ""
    sset = set(stamme)

    def punkte(p):
        st = [stamm(w) for w in woerter(p)]
        return sum(1 for s in st if s in sset or any(s.startswith(x) for x in sset if len(x) >= 4))
    best = max(absaetze, key=punkte)
    best = re.sub(r"\s+", " ", best.replace("*", "")).strip()
    if len(best) <= laenge:
        return best
    ws = list(re.finditer(r"[0-9A-Za-zÄÖÜäöüß]+", best))
    pos = 0
    for m in ws:
        s = stamm(m.group(0))
        if s in sset or any(s.startswith(x) for x in sset if len(x) >= 4):
            pos = m.start()
            break
    start = max(0, pos - laenge // 3)
    if start:
        start = best.rfind(" ", 0, start) + 1
    teil = best[start:start + laenge]
    teil = teil[:teil.rfind(" ")] if len(best) > start + laenge else teil
    return ("…" if start else "") + teil + ("…" if start + laenge < len(best) else "")


def _idf(con, stamme):
    """Gewicht je Suchstamm: log(N/df) über die FTS-Wortliste (seltene Wörter zählen mehr)."""
    import math
    n = con.execute("SELECT count(*) FROM abschnitte").fetchone()[0] or 1
    gew = {}
    for s in set(stamme):
        try:
            r = con.execute("SELECT doc FROM abschnitte_vocab WHERE term = ?", (s,)).fetchone()
        except sqlite3.OperationalError:  # ältere Datenbank ohne Wortliste
            r = None
        gew[s] = math.log((n + 1) / ((r[0] if r else 1) + 0.5))
    return gew


ZUSATZ_KENNZEICHEN = re.compile(r"^(?:[A-ZÄÖÜ]{2,3}|HG\b.*|Archetyp|Kampf|Metamagie|Legende|Stil|Gemeinschaft|"
                                r"Erschaffung|Gegenstandserschaffung|Kritischer[- ]Treffer|Leistung|Gruppe|Elan|Blick)"
                                r"(?:\s*[,;].*)?$")


def _endung_gleich(a, b):
    """Gleiches Wort bis auf die Flexionsendung: gleicher Stamm und eines ist Anfang des anderen."""
    return stamm(a) == stamm(b) and (a.startswith(b) or b.startswith(a))


def _bewerten(con, ids_rang, stamme, typ_wunsch=None, frage=""):
    """Nachgewichtung: Titeltreffer (nach Seltenheit der Wörter gewichtet), exakter Titel, Typ, Buch."""
    if not ids_rang:
        return []
    frage_klein = (frage or "").lower()
    qfolge = [w for w in woerter(frage or "") if w not in STOPP]
    zeilen = {r["id"]: r for r in con.execute(
        f"SELECT id, titel, pfad, typ, zeichen, buch FROM abschnitte WHERE id IN ({','.join('?' * len(ids_rang))})",
        [i for i, _ in ids_rang])}
    sset = set(stamme)
    gew = _idf(con, sset)
    summe = sum(gew.values()) or 1.0
    aus = []
    for i, rang in ids_rang:
        r = zeilen.get(i)
        if not r:
            continue
        p = -rang  # bm25: kleiner = besser -> positiv machen
        tst = {stamm(w) for w in woerter(r["titel"])}
        if sset:
            gedeckt = [s for s in sset if s in tst or any(t.startswith(s) for t in tst if len(s) >= 4)]
            abdeckung = sum(gew[s] for s in gedeckt) / summe
            p *= 1 + 2.0 * abdeckung
        # Titel ohne Zusätze ([Kampf], (AF), (ÜF) …): alle Wortstämme kommen in der Frage vor -> Bonus nach Seltenheit
        kern = re.sub(r"\s*[\[(][^\])]*[\])]", "", r["titel"]).strip().lower()
        kst = {stamm(w) for w in woerter(kern)} - {"tabell"}
        if kst and sset and kst <= sset:
            p *= 1 + 1.0 * sum(gew.get(s, 0) for s in kst) / summe
        # wörtlich gleicher Titel, z. B. „Beweglichkeit“ -> Talent Beweglichkeit (nicht „Bewegung“)
        if kern and len(kern) >= 4 and re.search(r"(?<![\wäöüß])" + re.escape(kern) + r"(?![\wäöüß])", frage_klein):
            p *= 1.6
        else:  # gleiche Wörter bis auf die Endung, gleiche Reihenfolge („Kritische Treffer“ – „kritischer Treffer …“;
            # nicht „Bewegung“ – „Beweglichkeit“)
            kf = [w for w in woerter(kern) if w not in STOPP]
            if kf and any(all(_endung_gleich(a, b) for a, b in zip(kf, qfolge[j:j + len(kf)]))
                          for j in range(len(qfolge) - len(kf) + 1)):
                p *= 1.3
        # Zusatz in runden Klammern, der nicht gefragt ist: „Kritischer Treffer (Verwirrt)“ hinter „Kritische Treffer“
        # (Kennzeichen wie (AF), (ÜF), (Kampf), (Archetyp), (HG 5) zählen nicht)
        for zusatz in re.findall(r"\(([^)]*)\)", r["titel"]):
            zst = {stamm(w) for w in woerter(zusatz)}
            if zst and not zst & sset and not ZUSATZ_KENNZEICHEN.match(zusatz.strip()):
                p *= 0.85
                break
        if typ_wunsch and r["typ"] == typ_wunsch:
            p *= 1.5
        if r["zeichen"] < 40:
            p *= 0.6
        if r["buch"] == "Grundregelwerk":
            p *= 1.2  # Grundregeln werden am häufigsten gebraucht
        aus.append((p, i))
    aus.sort(reverse=True)
    # Abwechslung: gleicher Titel aus demselben Buch (z. B. dreimal „Gelegenheitsangriffe“ im GRW) zählt je Wiederholung
    # weniger, damit andere passende Einträge nicht aus den ersten Treffern fallen
    schon = {}
    for n, (p, i) in enumerate(aus):
        k = (zeilen[i]["titel"].lower(), zeilen[i]["buch"])
        aus[n] = (p * 0.8 ** schon.get(k, 0), i)
        schon[k] = schon.get(k, 0) + 1
    aus.sort(reverse=True)
    return aus


# Bücher: Kürzel für die Ausgabe, Rang bei gleichnamigen Einträgen (Grundregelwerk zuerst)
BUCH_KURZ = {"Grundregelwerk": "GRW", "Expertenregeln": "EXP", "Monsterhandbuch": "MHB", "Abenteurerkompendium": "AK",
             "Monsterhandbuch II": "MHB2", "Ausbauregeln: Magie": "ARM", "Ausbauregeln II: Kampf": "ARK",
             "Ausbauregeln III: Völker": "ARV", "Ausbauregeln IV: Kampagnen": "ARKa",
             "Ausbauregeln V: Legenden": "ARL", "Ausbauregeln VI: Klassen": "ARKl", "Ausbauregeln VII: Okkultes": "ARO",
             "Monsterhandbuch III": "MHB3"}
BUCH_RANG = {"Grundregelwerk": 0, "Expertenregeln": 1, "Monsterhandbuch": 2, "Abenteurerkompendium": 3,
             "Monsterhandbuch II": 4, "Ausbauregeln: Magie": 5, "Ausbauregeln II: Kampf": 6,
             "Ausbauregeln III: Völker": 7, "Ausbauregeln IV: Kampagnen": 8,
             "Ausbauregeln V: Legenden": 9, "Ausbauregeln VI: Klassen": 10, "Ausbauregeln VII: Okkultes": 11,
             "Monsterhandbuch III": 12}


TYP_WOERTER = {"monster": "monster", "kreatur": "monster", "talent": "talent", "talente": "talent", "zustand": "zustand", "zustände": "zustand",
               "fertigkeit": "fertigkeit", "fertigkeiten": "fertigkeit", "klasse": "klasse"}


def suchen(frage, kategorie=None, buch=None, typ=None, max_treffer=5, datei=None):
    """Liste von dicts (id, titel, pfad, typ, kapitel, buch, url, schnipsel, zeichen, punkte, seite);
    datei=PRIVAT_DATEI: private PDFs."""
    con = db(datei)
    if con is None:
        return []
    gruppen, stamme = anfrage_gruppen(frage)
    typ_wunsch = typ or next((TYP_WOERTER[w] for w in woerter(frage) if w in TYP_WOERTER), None)
    if not gruppen:
        return []
    filt, par = "", []
    if kategorie:
        filt += " AND (lower(a.kapitel) LIKE ? OR lower(a.pfad) LIKE ?)"
        par += [f"%{kategorie.lower()}%"] * 2
    if buch:
        filt += " AND lower(a.buch) LIKE ?"
        par.append(f"%{buch.lower()}%")
    if typ:
        filt += " AND a.typ = ?"
        par.append(typ)
    gefunden = {}
    sql = ("SELECT a.id, bm25(abschnitte_fts, 8.0, 2.0, 1.0) AS r FROM abschnitte_fts JOIN abschnitte a "
           "ON a.id = abschnitte_fts.rowid WHERE abschnitte_fts MATCH ?" + filt + " ORDER BY r LIMIT 150")
    # alle Wörter; dann je ein Wort weggelassen; zuletzt irgendeines
    versuche = [(_fts_ausdruck(gruppen, True), 1.0)]
    if 2 < len(gruppen) <= 6:
        versuche += [(_fts_ausdruck(gruppen[:k] + gruppen[k + 1:], True), 0.6) for k in range(len(gruppen))]
    if len(gruppen) > 1:
        versuche.append((_fts_ausdruck(gruppen, False), 0.35))
    for ausdruck, faktor in versuche:
        try:
            for r in con.execute(sql, [ausdruck] + par):
                if r["id"] not in gefunden:
                    gefunden[r["id"]] = r["r"] * faktor
        except sqlite3.OperationalError:
            continue
        if len(gefunden) >= 150 or (faktor < 1.0 and len(gefunden) >= max_treffer * 3):
            break
    # Titeltreffer immer als Kandidaten (bei vielen Büchern fallen Grundregeln sonst aus den 150 besten heraus)
    try:
        for r in con.execute(sql, ["{titel} : (" + _fts_ausdruck(gruppen, False) + ")"] + par):
            gefunden.setdefault(r["id"], r["r"] * 0.5)
    except sqlite3.OperationalError:
        pass
    # Teilwort-Treffer im Titel (Trigramm), z. B. „Weihwasser“ in „Fläschchen mit Weihwasser“
    for w in woerter(frage):
        if len(w) >= 4 and w not in STOPP:
            try:
                for r in con.execute("SELECT t.rowid AS id FROM titel_tri t JOIN abschnitte a ON a.id=t.rowid "
                                     "WHERE titel_tri MATCH ?" + filt + " LIMIT 20", ['"' + w + '"'] + par):
                    gefunden.setdefault(r["id"], -2.0)
            except sqlite3.OperationalError:
                pass
    rang = _bewerten(con, list(gefunden.items()), stamme, typ_wunsch, frage)[:max_treffer * 3]
    if not rang:
        return []
    zeilen = {r["id"]: r for r in con.execute(
        f"SELECT * FROM abschnitte WHERE id IN ({','.join('?' * len(rang))})", [i for _, i in rang])}
    aus, gesehen = [], set()
    for p, i in rang:
        r = zeilen[i]
        text = r["text"]
        if not text.strip():
            unter = con.execute("SELECT titel FROM abschnitte WHERE eltern_id=? ORDER BY nr LIMIT 12", (i,)).fetchall()
            text = "Unterabschnitte: " + ", ".join(u["titel"] for u in unter)
        sn = _schnipsel(text, stamme)
        schluessel = re.sub(r"\W+", "", sn.lower())[:160]
        if schluessel in gesehen:  # gleicher Text auf Kapitel- und Einzelseite (z. B. Gegenstände)
            continue
        gesehen.add(schluessel)
        aus.append({"id": i, "titel": r["titel"], "pfad": r["pfad"], "typ": r["typ"], "kapitel": r["kapitel"],
                    "buch": r["buch"], "url": r["url"], "schnipsel": sn, "zeichen": r["zeichen"], "punkte": round(p, 2),
                    "seite": r["seite_id"]})
        if len(aus) >= max_treffer:
            break
    return aus


def zauber_hinweis(frage):
    """Zaubernamen in der Frage erkennen -> Hinweis auf die Zauberdatenbank (zauber_info)."""
    try:
        from bereiche.wissen import zauber_db
    except ImportError:
        return []
    ws = re.findall(r"[A-Za-zÄÖÜäöüß]+", frage or "")
    namen = []
    for n in (3, 2, 1):
        for i in range(len(ws) - n + 1):
            kand = " ".join(ws[i:i + n])
            if len(kand) < 4 or kand.lower() in STOPP:
                continue
            z = zauber_db.prd_finden(kand)
            if z and z["name"] not in namen and not any(z["name"].lower() in x.lower() for x in namen):
                namen.append(z["name"])
    return namen[:3]


def abschnitt(id_, datei=None):
    con = db(datei)
    return con.execute("SELECT * FROM abschnitte WHERE id=?", (int(id_),)).fetchone() if con else None


def unterabschnitte(id_, tiefe=6, datei=None):
    """Alle Nachfahren in Dokumentreihenfolge."""
    con = db(datei)
    a = abschnitt(id_, datei)
    if not a:
        return []
    rows = con.execute("SELECT * FROM abschnitte WHERE seite_id=? AND nr>? ORDER BY nr", (a["seite_id"], a["nr"]))
    aus = []
    for r in rows:
        if r["stufe"] <= a["stufe"]:
            break
        if r["stufe"] - a["stufe"] <= tiefe:
            aus.append(r)
    return aus


def titel_finden(name, typ=None, tabelle=None):
    """Bester Abschnitt zu einem Namen: exakt -> beginnt mit -> enthält -> ähnlich."""
    con = db()
    if con is None or not name:
        return None, []
    n = name.strip().lower()
    if tabelle:
        rows = con.execute(f"SELECT t.name AS name, a.* FROM {tabelle} t JOIN abschnitte a ON a.id=t.abschnitt_id").fetchall()
    else:
        q = "SELECT titel AS name, * FROM abschnitte" + (" WHERE typ=?" if typ else "")
        rows = con.execute(q, (typ,) if typ else ()).fetchall()

    def schl(s):
        return re.sub(r"\s*\[[^\]]*\]|\s*\([^)]*\)", "", s or "").strip().lower()
    for prüf in (lambda s: schl(s) == n, lambda s: (s or "").lower() == n, lambda s: schl(s).startswith(n),
                 lambda s: n in (s or "").lower()):
        treffer = [r for r in rows if prüf(r["name"])]
        if treffer:
            treffer.sort(key=lambda r: (r["typ"] == "tabelle", BUCH_RANG.get(r["buch"], 9), r["stufe"],
                                        len(r["name"])))
            return treffer[0], [r["name"] for r in treffer[1:6]]
    import difflib
    namen = {schl(r["name"]): r for r in rows}
    nah = difflib.get_close_matches(n, list(namen), n=5, cutoff=0.72)
    if nah:
        return namen[nah[0]], [namen[x]["name"] for x in nah[1:]]
    return None, []


def meta():
    con = db()
    if con is None:
        return {}
    return {r["schluessel"]: r["wert"] for r in con.execute("SELECT * FROM meta")}


# ---------------------------------------------------------------- Hausregeln (pro Kampagne)
_haus = {}


def hausregeln_abschnitte(datei):
    datei = Path(datei)
    if not datei.exists():
        return None
    mt = datei.stat().st_mtime
    c = _haus.get(str(datei))
    if c and c[0] == mt:
        return c[1]
    text = datei.read_text(encoding="utf-8")
    bloecke = []
    for teil in re.split(r"\n\s*\n", text):
        teil = teil.strip()
        if not teil:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", teil.split("\n")[0])
        if m:
            bloecke.append(("h", len(m.group(1)), m.group(2).strip(), None))
            rest = "\n".join(teil.split("\n")[1:]).strip()
            if rest:
                bloecke.append(("p", rest))
        else:
            bloecke.append(("p", teil))
    ab = [a for a in abschnitte_aus_bloecken(bloecke, "Hausregeln") if a["text"].strip() and a["stufe"] > 1
          or (a["text"].strip() and not a["text"].lstrip().startswith(">"))]
    # Erklärtexte der Vorlage (Zitatblöcke „> …“) nicht als Regeln werten
    ab = [a for a in ab if re.sub(r"(?m)^>.*$", "", a["text"]).strip()]
    for i, a in enumerate(ab):
        a["_nr"] = i + 1
        a["text"] = re.sub(r"(?m)^>.*\n?", "", a["text"]).strip()
    # kleine Datei: Vergleich über normalisierte Texte (Teilwort-Treffer, z. B. „aktion“ in „bewegungsaktion“)
    m = [(" " + norm(a["titel"]) + " ", " " + norm(a["text"]) + " ") for a in ab]
    _haus[str(datei)] = (mt, (ab, m))
    return ab, m


def hausregeln_suchen(datei, frage, max_treffer=3):
    r = hausregeln_abschnitte(datei)
    if not r:
        return []
    ab, m = r
    gruppen, stamme = anfrage_gruppen(frage)
    if not gruppen or not ab:
        return []
    # Gruppen -> Alternativen als normalisierte Zeichenfolgen ('"stamm"*' -> 'stamm', Phrase -> 'a b')
    alt_gruppen = [[x.strip('"*') for x in g] for g in gruppen]
    n = len(alt_gruppen)
    bewertet = []
    for i, (t, x) in enumerate(m):
        im_titel = sum(1 for g in alt_gruppen if any(a and a in t for a in g))
        if n == 1:  # ein einzelnes Wort: nur ganze Wörter im Text zählen (sonst passt „angriff“ überall)
            passend = sum(1 for g in alt_gruppen if any(a and (a in t or f" {a} " in x) for a in g))
        else:
            passend = sum(1 for g in alt_gruppen if any(a and (a in t or a in x) for a in g))
        # alle Begriffe; bei mehreren Begriffen genügt alle bis auf einen, wenn einer im Titel steht
        if passend == n or (n >= 2 and passend >= n - 1 and im_titel):
            bewertet.append((passend + im_titel, -i))
    bewertet.sort(reverse=True)
    aus = [ab[-i] for _, i in bewertet[:max_treffer]]
    return [dict(a, schnipsel=_schnipsel(a["text"], stamme, 400)) for a in aus]


# ---------------------------------------------------------------- Textausgaben (knapp, für SL-Agent und sl.py)
FEHLT = ("Regeldatenbank fehlt (regeln/regeln.sqlite). Aufbauen mit `sl.py regeln-aktualisieren` "
         "bzw. MCP regeln_aktualisieren (dauert beim ersten Mal ca. 30–60 Minuten).")


def _quelle(r):
    if (r["url"] or "").startswith("pdf:"):
        seite = r["url"].partition("#")[2]
        return f"Quelle: eigenes PDF „{r['buch']}“{', ' + seite if seite else ''} (privat, nicht weitergeben)"
    return f"Quelle: PRD {r['buch']} › {r['kapitel']} – {r['url']}"


def _haus_text(h):
    pf = " › ".join(h["pfad"][1:] + [h["titel"]]) if h["pfad"] else h["titel"]
    return f"[H{h['_nr']}] HAUSREGEL (hat Vorrang): {pf}\n    {h['schnipsel']}"


def suche_text(frage, kategorie=None, buch=None, typ=None, max_treffer=5, hausregeln=None):
    teile = []
    if hausregeln:
        for h in hausregeln_suchen(hausregeln, frage):
            teile.append(_haus_text(h))
    if db() is None:
        teile.append(FEHLT)
        return "\n".join(teile)
    zn = zauber_hinweis(frage)
    if zn:
        teile.append("Zauber erkannt: " + ", ".join(zn) + " → Wirkung mit zauber_info(name=…) nachschlagen "
                     "(Zauber stehen nicht in der Regeldatenbank).")
    treffer = suchen(frage, kategorie, buch, typ, max(1, min(int(max_treffer or 5), 20)))
    for t in treffer:
        kuerzel = BUCH_KURZ.get(t["buch"], t["buch"])
        art = ", ".join(x for x in (None if t["typ"] == "regel" else t["typ"],
                                    None if t["buch"] == "Grundregelwerk" else kuerzel) if x)
        typ_ = f" ({art})" if art else ""
        pf = f" — {t['pfad']}" if t["pfad"] else ""
        teile.append(f"[{t['id']}] {t['titel']}{typ_}{pf}\n    {t['schnipsel']}\n    {t['url']}")
    privat = suchen(frage, kategorie, buch, typ, 3, PRIVAT_DATEI) if PRIVAT_DATEI.exists() else []
    if privat:
        teile.append("Private PDFs (eigene Bücher, nicht weitergeben):")
        for t in privat:
            seite = t["url"].partition("#")[2]
            teile.append(f"[P{t['id']}] {t['titel']} — {t['buch']}{', ' + seite if seite else ''}"
                         f"{' (' + t['typ'] + ')' if t['typ'] != 'regel' else ''}\n    {t['schnipsel']}")
    if not treffer and not privat:
        teile.append("Keine Treffer in der Regeldatenbank (andere Begriffe/Synonyme versuchen; erst dann Websuche).")
    else:
        teile.append("Volltext: regel_lesen(eintrag=ID)")
    return "\n".join(teile)


def _abschnitt_text(r, ab=0, max_zeichen=4000, unter=True, datei=None):
    vor = _praefix(datei)
    kopf = f"## {r['titel']}" + (f"  ({r['pfad']})" if r["pfad"] else "") + f"\n{_quelle(r)}\n"
    text = r["text"] or ""
    subs = unterabschnitte(r["id"], datei=datei) if unter else []
    for s in subs:
        text += ("\n\n" if text else "") + "#" * min(6, s["stufe"] + 1) + f" {s['titel']} [{vor}{s['id']}]\n\n" + s["text"]
    text = text.strip()
    if ab:
        text = text[ab:]
    if len(text) > max_zeichen:
        schnitt = text.rfind("\n\n", 0, max_zeichen)
        if schnitt < max_zeichen // 2:
            schnitt = max_zeichen
        rest = len(text) - schnitt
        text = text[:schnitt] + (f"\n\n… gekürzt ({rest} Zeichen fehlen). Weiter: regel_lesen(eintrag={vor}{r['id']}, "
                                 f"ab={ab + schnitt}) oder einen Unterabschnitt [ID] lesen.")
    return kopf + "\n" + text


def _seite_finden(con, seite):
    n = seite.strip().strip("/").lower()
    for r in con.execute("SELECT * FROM seiten WHERE rolle='inhalt' ORDER BY length(pfad)"):
        if r["pfad"].strip("/").lower() in (n, "grundregelwerk/" + n) or r["titel"].lower() == n \
                or (r["kapitel"].lower() == n and r["pfad"].count("/") == 2):
            return r
    return None


def lesen_text(eintrag=None, seite=None, abschnitt=None, ab=0, max_zeichen=4000, hausregeln=None):
    con = db()
    e = str(eintrag).strip() if eintrag not in (None, "") else ""
    if re.fullmatch(r"[Hh]\d+", e):
        r = hausregeln_abschnitte(hausregeln) if hausregeln else None
        if not r:
            return "Keine Hausregeln-Datei (sl/hausregeln.md)."
        treffer = [a for a in r[0] if a["_nr"] == int(e[1:])]
        if not treffer:
            return f"Hausregel {e} nicht gefunden."
        a = treffer[0]
        return f"## HAUSREGEL: {' › '.join(a['pfad'][1:] + [a['titel']])}\n(Hausregel dieser Kampagne, hat Vorrang)\n\n{a['text']}"
    mz = int(max_zeichen or 4000)
    if re.fullmatch(r"[Pp]\d+", e):  # Eintrag aus dem privaten PDF-Index
        r = globals()["abschnitt"](int(e[1:]), PRIVAT_DATEI)
        if not r:
            return f"Eintrag {e} nicht gefunden (privater PDF-Index)."
        return _abschnitt_text(r, int(ab or 0), mz, datei=PRIVAT_DATEI)
    if con is None:
        return FEHLT
    if e.isdigit():
        r = globals()["abschnitt"](int(e))  # Parameter „abschnitt“ verdeckt die Funktion
        if not r:
            return f"Eintrag {e} nicht gefunden."
        return _abschnitt_text(r, int(ab or 0), mz)
    if seite and not (abschnitt or e):
        s = _seite_finden(con, seite)
        if not s:
            return f"Seite „{seite}“ nicht gefunden. Kapitel: " + ", ".join(
                sorted({r["kapitel"] for r in con.execute("SELECT kapitel FROM seiten WHERE rolle='inhalt'")}))
        zeilen = [f"## {s['titel']} – Inhalt ({s['url']})"]
        for r in con.execute("SELECT id, stufe, titel FROM abschnitte WHERE seite_id=? ORDER BY nr", (s["id"],)):
            zeilen.append("  " * max(0, r["stufe"] - 2) + f"[{r['id']}] {r['titel']}")
        unter = con.execute("SELECT titel FROM seiten WHERE rolle='inhalt' AND pfad LIKE ? ORDER BY pfad",
                            (s["pfad"] + "/%",)).fetchall()
        if unter:
            zeilen.append("Unterseiten: " + ", ".join(u["titel"] for u in unter))
        return "\n".join(zeilen[:400])
    name = abschnitt or e
    if seite:
        s = _seite_finden(con, seite)
        if s:
            rows = con.execute("SELECT * FROM abschnitte WHERE seite_id=? ORDER BY nr", (s["id"],)).fetchall()
            n = name.lower()
            for pruef in (lambda t: t == n, lambda t: t.startswith(n), lambda t: n in t):
                tr = [r for r in rows if pruef(r["titel"].lower())]
                if tr:
                    return _abschnitt_text(tr[0], int(ab or 0), mz)
    r, weitere = titel_finden(name)
    if not r:
        return f"„{name}“ nicht gefunden. Tipp: regel_suchen(frage=…)."
    aus = _abschnitt_text(r, int(ab or 0), mz)
    if weitere:
        aus += "\n\nÄhnliche Einträge: " + ", ".join(weitere)
    return aus


def _haus_hinweis(hausregeln, name):
    if not hausregeln:
        return ""
    return "".join(f"\n\n{_haus_text(x)}" for x in hausregeln_suchen(hausregeln, name, 2))


def schnell_text(art, name=None, voraussetzung=None, kategorie=None, hausregeln=None, max_zeichen=4000):
    """art: talent | zustand | fertigkeit. Ohne Namen: Liste; mit Namen: Volltext."""
    con = db()
    if con is None:
        return FEHLT
    tab = {"talent": "talente", "zustand": "zustaende", "fertigkeit": "fertigkeiten"}[art]
    if name:
        r, weitere = titel_finden(name, tabelle=tab)
        if not r:
            r, weitere = titel_finden(name)  # z. B. Begriff, der nur im Kampfkapitel steht
        if not r:
            return f"{art.capitalize()} „{name}“ nicht gefunden. Liste: {art}_info ohne Namen; Suche: regel_suchen."
        aus = _abschnitt_text(r, 0, int(max_zeichen or 4000))
        if weitere:
            aus += "\n\nÄhnlich: " + ", ".join(weitere)
        return aus + _haus_hinweis(hausregeln, re.sub(r"\s*[\[(].*", "", r["titel"]))
    if art == "talent":
        q, par = ("SELECT t.name, t.arten, t.voraussetzungen, a.buch FROM talente t JOIN abschnitte a "
                  "ON a.id = t.abschnitt_id WHERE 1"), []
        if voraussetzung:
            q += " AND lower(voraussetzungen) LIKE ?"
            par.append(f"%{voraussetzung.lower()}%")
        if kategorie:
            q += " AND lower(arten) LIKE ?"
            par.append(f"%{kategorie.lower()}%")
        rows = con.execute(q + " ORDER BY name", par).fetchall()
        zeilen = [r["name"] + (f" [{r['arten']}]" if r["arten"] else "") +
                  (f" ({BUCH_KURZ.get(r['buch'], r['buch'])})" if r["buch"] != "Grundregelwerk" else "") +
                  (f" – {r['voraussetzungen'][:90]}" if r["voraussetzungen"] else "") for r in rows]
        return f"{len(rows)} Talente:\n" + "\n".join(zeilen[:150]) + ("\n…" if len(zeilen) > 150 else "")
    if art == "zustand":
        rows = con.execute("SELECT name FROM zustaende ORDER BY name").fetchall()
        return "Zustände: " + ", ".join(r["name"] for r in rows) + "\nVolltext: zustand_info(name=…)"
    rows = con.execute("SELECT name, zusatz FROM fertigkeiten ORDER BY name").fetchall()
    return "Fertigkeiten: " + "; ".join(f"{r['name']} ({r['zusatz']})" if r["zusatz"] else r["name"] for r in rows)


def monster_text(name=None, hg=None, art=None, max_zeichen=6000):
    """Monster nachschlagen: mit Namen der Werteblock (+ Beschreibung), sonst Liste nach HG/Art."""
    con = db()
    if con is None:
        return FEHLT
    if name:
        r, weitere = titel_finden(name, tabelle="monster")
        if not r:
            r, weitere = titel_finden(name, typ="monster")
        if not r:
            nah = suchen(name, typ="monster", max_treffer=5)
            return (f"Monster „{name}“ nicht gefunden." + (" Meintest du: " + ", ".join(t["titel"] for t in nah)
                                                         if nah else " Tipp: regel_suchen(frage=…, typ=\"monster\")."))
        aus = _abschnitt_text(r, 0, int(max_zeichen or 6000))
        return aus + ("\n\nÄhnlich: " + ", ".join(weitere) if weitere else "")
    q, par = ("SELECT m.name, m.hg, m.ep, m.art, a.buch FROM monster m JOIN abschnitte a ON a.id = m.abschnitt_id "
              "WHERE 1"), []
    if hg not in (None, ""):
        w = _hg_wert(str(hg))
        q += " AND abs(m.hg_wert - ?) < 0.001"
        par.append(w if w is not None else -1)
    if art:
        q += " AND lower(m.art) LIKE ?"
        par.append(f"%{art.lower()}%")
    rows = con.execute(q + " ORDER BY m.hg_wert, m.name", par).fetchall()
    if not rows:
        return "Keine Monster gefunden (hg z. B. 3 oder 1/2, art z. B. Untoter, Konstrukt, Drache)."
    zeilen = [f"{r['name']} (HG {r['hg']}, {r['ep'] or '?'} EP) – {r['art']}" +
              (f" [{BUCH_KURZ.get(r['buch'], r['buch'])}]" if r["buch"] != "Monsterhandbuch" else "") for r in rows]
    return f"{len(rows)} Monster:\n" + "\n".join(zeilen[:150]) + ("\n…" if len(zeilen) > 150 else "") + \
        "\nWerteblock: monster_info(name=…)"


def info_text():
    m = meta()
    con = db()
    if not m or con is None:
        return FEHLT
    n = {r[0]: r[1] for r in con.execute("SELECT typ, count(*) FROM abschnitte GROUP BY typ")}
    s = con.execute("SELECT count(*) FROM seiten WHERE rolle='inhalt'").fetchone()[0]
    aus = (f"Regeldatenbank: {m.get('buecher')} · {s} Seiten · {sum(n.values())} Einträge "
           f"({', '.join(f'{k} {v}' for k, v in sorted(n.items()))}) · Stand {m.get('gebaut')}\n{m.get('lizenz')}")
    pc = db(PRIVAT_DATEI)
    if pc is not None:
        buecher = [r[0] for r in pc.execute("SELECT titel FROM seiten WHERE rolle='inhalt' ORDER BY titel")]
        k = pc.execute("SELECT count(*) FROM abschnitte").fetchone()[0]
        aus += f"\nPrivater PDF-Index (nicht weitergeben): {len(buecher)} Bücher, {k} Einträge – {', '.join(buecher)}"
    return aus
