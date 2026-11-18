"""Charakter: Modi setzen, beenden, ablaufen lassen (Charaktere und Token ohne Charakterdatei).

Größe/Reichweite der Token passt der Bereich Karte an (Fachereignisse `charakter_modi`, `token_groesse`).
"""
from bereiche import reaktion
from bereiche.kern import Fehler
from . import modi as MODI
from .werte import alle, existiert, laden, meter_pro_feld, sc_token, speichern, wirksam


def _token_finden(kx, kennung):
    t = kx.z["tokens"].get(kennung)
    if t is None:
        t = next((k for k in kx.z["tokens"].values() if k["name"].lower() == str(kennung).lower()), None)
    if t is None:
        raise Fehler(f"Token {kennung!r} nicht gefunden")
    return t


def ziel(kx, kennung):
    """Ziel eines Modus: ('char', Charakterdaten roh) oder ('token', Token ohne Charakterdatei)."""
    t = kx.z["tokens"].get(kennung)
    if t is None and existiert(kx, kennung):
        return "char", laden(kx, kennung)
    if t is None:
        t = _token_finden(kx, kennung)
    if t.get("charId"):
        return "char", laden(kx, t["charId"])
    return "token", t


def syncen(kx, art, obj):
    """Nach einer Änderung der Modi: speichern, Token angleichen lassen. Gibt Hinweise zurück."""
    if art == "char":
        speichern(kx, obj)
        return kx.ereignis("charakter_modi", cid=obj["id"], eff=wirksam(kx, laden(kx, obj["id"])))
    vorher = obj.get("groesse", 1)
    MODI.token_anwenden(obj, meter_pro_feld(kx))
    neu = obj.get("groesse", 1)
    if neu != vorher:
        obj["groesse"] = vorher
        return kx.ereignis("token_groesse", token=obj, groesse=neu)
    return []


def _log(kx, obj, text):
    if obj.get("art") != "gegner" and obj.get("sichtbar", True):
        kx.protokoll("system", text)
    else:
        kx.protokoll("sl-notiz", text, verborgen=True)


def zeit(kx, runden):
    """Zieht Runden von allen Modi ab (Kampfrunde = 1, Rast = 4800 usw.) und meldet Abgelaufenes."""
    if not kx.einst.get("modi", True):
        return []
    aus_liste = []
    for c in alle(kx):
        if not MODI.aktive(c):
            continue
        c["modi"], aus = MODI.zeit(c["modi"], runden)
        syncen(kx, "char", c)
        aus_liste += [({"name": c["name"], "art": "sc"}, n) for n in aus]
    for t in list(kx.z["tokens"].values()):
        if not t.get("charId") and MODI.aktive(t):
            t["modi"], aus = MODI.zeit(t["modi"], runden)
            syncen(kx, "token", t)
            aus_liste += [(t, n) for n in aus]
    for o, n in aus_liste:
        _log(kx, o, f"{o['name']}: {n} endet.")
    return [f"{o['name']}: {n}" for o, n in aus_liste]


@reaktion("runde_vorbei")
def _runde_vorbei(kx, runden=1):
    zeit(kx, runden)


@reaktion("zeit_vergeht")
def _zeit_vergeht(kx, runden):
    zeit(kx, runden)


def befehl(kx, op, b):
    """SL-Befehle `modus` und `modus-ende`."""
    art, obj = ziel(kx, b["ziel"])
    name = (b.get("name") or "").strip()
    tok = obj if art == "token" else (sc_token(kx, obj["id"]) or {"art": "sc"})
    if op == "modus":
        if not name:
            raise Fehler("Name des Modus fehlt")
        wirk = MODI.vorlage(name)
        try:
            wirk.update(MODI.wirkung_pruefen(b.get("wirkung") or {}))
            if b.get("groesse") is not None:
                wirk["groesse"] = int(b["groesse"])
        except ValueError as e:
            raise Fehler(str(e))
        if not wirk:
            raise Fehler(f"{name!r} ist keine bekannte Vorlage – Wirkung angeben (--wirkung rk=1 …)")
        rest = b.get("runden")
        obj["modi"] = MODI.setzen(list(obj.get("modi") or []), name, wirk, None if rest is None else int(rest),
                                  b.get("quelle", ""))
        hinweise = syncen(kx, art, obj)
        modus = obj["modi"][-1]
        _log(kx, tok, f"{obj['name']}: {name} ({MODI.wirkung_text(wirk)}; {MODI.dauer_text(modus)})")
        return {"text": f"{obj['name']}: {name} aktiv – {MODI.wirkung_text(wirk)}; {MODI.dauer_text(modus)}",
                "hinweise": hinweise}
    if op == "modus-ende":
        neu, gefunden = MODI.entfernen(list(obj.get("modi") or []), name)
        if not gefunden:
            raise Fehler(f"{obj['name']} hat keinen Modus {name!r}")
        obj["modi"] = neu
        hinweise = syncen(kx, art, obj)
        _log(kx, tok, f"{obj['name']}: {name} endet.")
        return {"text": f"{obj['name']}: {name} beendet", "hinweise": hinweise}
    raise Fehler("Unbekannter Modus-Befehl")


def liste(kx):
    zeilen = []
    for c in alle(kx):
        for m in MODI.aktive(c):
            zeilen.append(f"{c['name']}: {m['name']} – {MODI.wirkung_text(m['wirkung'])}; {MODI.dauer_text(m)}")
    for t in kx.z["tokens"].values():
        if not t.get("charId"):
            for m in MODI.aktive(t):
                zeilen.append(f"{t['name']} ({t['id']}): {m['name']} – {MODI.wirkung_text(m['wirkung'])}; "
                              f"{MODI.dauer_text(m)}")
    return zeilen
