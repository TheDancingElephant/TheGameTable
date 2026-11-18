"""Charakter: Laden/Speichern über den Kontext, wirksame Werte (mit Modi), Waffenangaben, Attributsmodifikator."""
import re

from bereiche.kern import Fehler
from . import modi as MODI

FERN_RE = re.compile(r"bogen|armbrust|schleuder|blasrohr|wurf|berührungslos|strahl", re.I)
# Grundreichweite (Entfernungsinkrement) in Metern nach Waffenname
INKREMENTE = [("langbogen", 30), ("kurzbogen", 18), ("schwere armbrust", 36), ("armbrust", 24),
              ("schleuder", 15), ("blasrohr", 6), ("wurfspeer", 9), ("wurfaxt", 3), ("dolch", 3),
              ("berührungslos", 9)]
ABGELEITET = ("_ep", "_zauberKlasse", "_vorbereiten")  # nur für die Oberfläche, nie gespeichert


def attr_mod(wert):
    """Attributsmodifikator (PF1: (Wert − 10) / 2, abgerundet); None = 0."""
    return 0 if wert is None else (int(wert) - 10) // 2


def waffe_info(a):
    """Fernkampf? Grundreichweite (m)? Berührungsangriff? – aus Angaben oder Waffenname."""
    name = (a.get("name") or "").lower()
    fern = a.get("fernkampf")
    if fern is None:
        fern = bool(FERN_RE.search(name))
    ink = a.get("inkrement") or (next((m for n, m in INKREMENTE if n in name), 9) if fern else None)
    return {"fernkampf": fern, "inkrement": ink, "beruehrung": "berührung" in name}


def meter_pro_feld(kx):
    """Meter je Feld der aktiven Karte (Standard 1,5 m)."""
    k = kx.z["karten"].get(kx.z.get("karteAktiv") or "") or {}
    return k.get("meterProFeld", 1.5)


def laden(kx, cid):
    """Basiswerte eines Charakters (Kopie); Fehler, wenn es ihn nicht gibt."""
    return kx.chars.laden(cid)


def existiert(kx, cid):
    return kx.chars.existiert(cid)


def alle(kx):
    return kx.chars.alle()


def speicherbar(c):
    """Abgeleitete Werte (Modi, Oberfläche) entfernen; Basiswerte bleiben."""
    c = MODI.speicherbar(c)
    for e in c.get("zauberliste", []):
        e.pop("_d", None)
    for k in ABGELEITET:
        c.pop(k, None)
    return c


def speichern(kx, c):
    """Charakter speichern (auch wirksame Kopien: Modus-Werte werden auf die Basis zurückgerechnet)."""
    kx.chars.speichern(speicherbar(c))


def loeschen(kx, cid):
    kx.chars.loeschen(cid)


def wirksam(kx, c):
    """Charakter mit angewendeten Modi (Hast, Größe …); unverändert, wenn Modi in der Kampagne abgeschaltet sind."""
    if c is None or not kx.einst.get("modi", True):
        return c
    return MODI.char_wirksam(c, lambda a: waffe_info(a)["fernkampf"], meter_pro_feld(kx))


def von_token(kx, t):
    """Wirksame Charakterdaten zu einem SC-Token (None ohne Charakterdatei)."""
    try:
        return wirksam(kx, laden(kx, t["charId"])) if t.get("charId") else None
    except Fehler:
        return None


def sc_token(kx, cid):
    """Das SC-Token eines Charakters (oder None)."""
    for t in kx.z["tokens"].values():
        if t.get("charId") == cid and t["art"] == "sc":
            return t
    return None


def tp_uebernehmen(kx, t):
    """TP eines SC-Tokens in die Charakterdatei übernehmen."""
    try:
        c = laden(kx, t["charId"])
    except (Fehler, KeyError):
        return
    c.setdefault("tp", {})["aktuell"] = t["tp"]
    speichern(kx, c)


def pfad_setzen(o, pfad, wert):
    """Setzt einen Wert über einen Punktpfad; Zahlen im Pfad indizieren Listen (z. B. zauberliste.23.verbraucht)."""
    teile = pfad.split(".")
    for k in teile[:-1]:
        if isinstance(o, list):
            try:
                o = o[int(k)]
            except (ValueError, IndexError):
                raise Fehler(f"Pfad {pfad!r}: Listenindex {k!r} ungültig")
        else:
            o = o.setdefault(k, {})
    letzter = teile[-1]
    if isinstance(o, list):
        try:
            o[int(letzter)] = wert
        except (ValueError, IndexError):
            raise Fehler(f"Pfad {pfad!r}: Listenindex {letzter!r} ungültig")
    else:
        o[letzter] = wert


def token_angleichen(kx, c, farbe=False):
    """Name/TP (und auf Wunsch Farbe) des SC-Tokens an die Charakterdaten angleichen."""
    t = sc_token(kx, c["id"])
    if t:
        t.update({"name": c["name"], "tpMax": c.get("tp", {}).get("max"), "tp": c.get("tp", {}).get("aktuell")})
        if farbe:
            t["farbe"] = c.get("farbe", t.get("farbe"))


def char_setzen(kx, cid, werte):
    """Einzelne Werte eines Charakters ändern (Punktpfade, z. B. rw.REF)."""
    c = laden(kx, cid)
    for pfad, wert in werte.items():
        pfad_setzen(c, pfad, wert)
    speichern(kx, c)
    token_angleichen(kx, c)


def charakter_speichern(kx, c, neue_id):
    """Ganzer Charakterbogen aus der Oberfläche/dem Import (ID wird bei Bedarf vergeben)."""
    if not c.get("name"):
        raise Fehler("Name fehlt")
    c["id"] = c.get("id") or re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-") or neue_id
    speichern(kx, c)
    token_angleichen(kx, c, farbe=True)
    return c


def charakter_loeschen(kx, cid):
    loeschen(kx, cid)
    t = sc_token(kx, cid)
    if t:
        del kx.z["tokens"][t["id"]]
