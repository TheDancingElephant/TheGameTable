"""Modi: zeitlich begrenzte Wirkungen (Hast, Person vergrößern, Heldenmut …) auf Charaktere und Token.

Grundidee: Die gespeicherten Werte (Basiswerte) bleiben unverändert. Aktive Modi stehen als Liste `modi`
am Charakter (Datei) bzw. am Token. Die wirksamen Werte werden beim Lesen berechnet (`char_wirksam`,
`token_anwenden`). Ende eines Modus = Eintrag entfernen, es muss nichts zurückgerechnet werden.

Ein Modus: {"name", "wirkung": {…}, "rest": Runden|None, "quelle": Text}
Wirkung (alles ganze Zahlen, additiv):
  groesse        Größenstufen (+1 = eine Kategorie größer); steuert Größenmodifikator (Angriff, RK, KMB, KMV,
                 Heimlichkeit, Fliegen), Waffenschaden (Würfel), Tokengröße und Reichweite
  ST GE KO IN WE CH   Attributsänderung; leitet ab: ST → Nahkampf-Angriff/-Schaden, KMB, KMV;
                 GE → RK (normal/Berührung; ad. FF nur bei Malus), Fernkampf-Angriff, REF, Initiative, KMV; KO → ZÄH
  rk             RK-Bonus gegen normale und Berührungsangriffe (Ausweichen/Ablenkung, z. B. Hast)
  rkr            RK-Bonus normal und auf dem falschen Fuß (Rüstung/natürliche Rüstung, z. B. Rindenhaut)
  rkb rkf        nur RK gegen Berührung / nur RK auf dem falschen Fuß
  rkga           RK-Bonus nur gegen Gelegenheitsangriffe (Ausweichbonus; entfällt auf dem falschen Fuß)
  angriff nahangriff fernangriff schaden (Nahkampfschaden)
  ref wil zaeh rw (rw = alle Rettungswürfe)  ini kmb kmv
  tempo          Bewegungsrate in Metern
  reichweite     zusätzliche Nahkampfreichweite in Feldern
  extraangriff   zusätzlicher Angriff (mit höchstem Bonus) in Serien/Vollangriffen
  fert:NAME      Fertigkeitsbonus (z. B. fert:Heimlichkeit)
"""
import copy
import math
import re

GROESSEN = ["Fein", "Mini", "Winzig", "Klein", "Mittel", "Groß", "Riesig", "Gigantisch", "Kolossal"]
_ALIAS = {"fein": 0, "mini": 1, "winzig": 2, "klein": 3, "mittel": 4, "gross": 5, "groß": 5, "riesig": 6,
          "gigantisch": 7, "kolossal": 8, "gewaltig": 8}
MOD_ANGRIFF = [8, 4, 2, 1, 0, -1, -2, -4, -8]      # Angriff und RK
MOD_KMB = [-8, -4, -2, -1, 0, 1, 2, 4, 8]          # KMB und KMV
MOD_HEIMLICH = [16, 12, 8, 4, 0, -4, -8, -12, -16]
MOD_FLIEGEN = [8, 6, 4, 2, 0, -2, -4, -6, -8]
FELDER = [1, 1, 1, 1, 1, 2, 3, 4, 6]                # Token-Kantenlänge
# natürliche Nahkampfreichweite in Metern: (hoch, lang)
REICHWEITE_HOCH = [0, 0, 0, 1.5, 1.5, 3, 4.5, 6, 9]
REICHWEITE_LANG = [0, 0, 0, 1.5, 1.5, 1.5, 3, 4.5, 6]

# Waffenschaden eine Größe höher (PF1-Tabelle); abwärts ist die Umkehrung
_HOCH = {"1W2": "1W3", "1W3": "1W4", "1W4": "1W6", "1W6": "1W8", "1W8": "2W6", "1W10": "2W8", "1W12": "3W6",
         "2W4": "2W6", "2W6": "3W6", "2W8": "3W8", "2W10": "4W8", "3W6": "4W6", "3W8": "4W8", "4W6": "6W6",
         "4W8": "6W8", "6W6": "8W6", "6W8": "8W8", "8W6": "12W6", "8W8": "12W8"}
_RUNTER = {v: k for k, v in _HOCH.items()}

VORLAGEN = {
    "person vergrößern": {"groesse": 1, "ST": 2, "GE": -2},
    "vergrößern": {"groesse": 1, "ST": 2, "GE": -2},
    "person verkleinern": {"groesse": -1, "ST": -2, "GE": 2},
    "verkleinern": {"groesse": -1, "ST": -2, "GE": 2},
    "hast": {"angriff": 1, "rk": 1, "ref": 1, "tempo": 9, "extraangriff": 1},
    "massenhast": {"angriff": 1, "rk": 1, "ref": 1, "tempo": 9, "extraangriff": 1},
    "heldenmut": {"angriff": 2, "rw": 2},
    "stierstärke": {"ST": 4}, "katzenanmut": {"GE": 4}, "bärenausdauer": {"KO": 4}, "ausdauer des bären": {"KO": 4},
    "fuchslist": {"IN": 4}, "eulenweisheit": {"WE": 4}, "adlerprunk": {"CH": 4},
}
ATTRIBUTE = ("ST", "GE", "KO", "IN", "WE", "CH")
SCHLUESSEL = {"groesse", "rk", "rkr", "rkb", "rkf", "rkga", "angriff", "nahangriff", "fernangriff", "schaden", "ref", "wil", "zaeh",
              "rw", "ini", "kmb", "kmv", "tempo", "reichweite", "extraangriff", *ATTRIBUTE}


def groesse_index(name_oder_zahl, standard=4):
    if isinstance(name_oder_zahl, int):
        return max(0, min(8, name_oder_zahl))
    return _ALIAS.get(str(name_oder_zahl or "").strip().lower(), standard)


def wirkung_pruefen(w):
    """Normalisiert eine Wirkung (Werte → int) und meldet unbekannte Schlüssel als ValueError."""
    aus = {}
    for k, v in w.items():
        k2 = k if k.startswith("fert:") else (k.upper() if k.upper() in ATTRIBUTE else k.lower())
        if not (k2 in SCHLUESSEL or k2.startswith("fert:")):
            raise ValueError(f"Unbekannte Wirkung {k!r} (erlaubt: {', '.join(sorted(SCHLUESSEL))}, fert:NAME)")
        aus[k2] = int(v)
    return aus


def vorlage(name):
    return dict(VORLAGEN.get((name or "").strip().lower(), {}))


def aktive(obj):
    return [m for m in (obj.get("modi") or []) if isinstance(m, dict) and m.get("wirkung")]


def summe(mods):
    s = {}
    for m in mods:
        for k, v in m["wirkung"].items():
            s[k] = s.get(k, 0) + int(v)
    return s


def setzen(liste, name, wirkung, rest=None, quelle=""):
    """Fügt einen Modus hinzu; gleicher Name (ohne Beachtung der Groß-/Kleinschreibung) ersetzt den alten."""
    neu = [m for m in liste if not (isinstance(m, dict) and str(m.get("name", "")).lower() == name.lower())]
    neu.append({"name": name, "wirkung": wirkung, "rest": rest, "quelle": quelle})
    return neu


def entfernen(liste, name):
    neu = [m for m in liste if not (isinstance(m, dict) and str(m.get("name", "")).lower() == name.lower())]
    return neu, len(neu) != len(liste)


def zeit(liste, runden):
    """Zieht Runden ab; gibt (neue Liste, Namen der abgelaufenen) zurück. `rest` None = unbegrenzt."""
    neu, aus = [], []
    for m in liste:
        if isinstance(m, dict) and m.get("rest") is not None and m.get("wirkung"):
            r = int(m["rest"]) - int(runden)
            if r <= 0:
                aus.append(m["name"])
                continue
            m = {**m, "rest": r}
        neu.append(m)
    return neu, aus


def dauer_text(m):
    r = m.get("rest")
    if r is None:
        return "unbegrenzt"
    if r >= 600 and r % 600 == 0:
        return f"{r // 600} Std."
    if r >= 10 and r % 10 == 0:
        return f"{r // 10} Min. ({r} Rd.)"
    return f"{r} Rd."


def wirkung_text(w):
    teile = []
    for k, v in w.items():
        if k == "groesse":
            teile.append(f"Größe {v:+d} Stufe(n)")
        else:
            teile.append(f"{k} {v:+d}")
    return ", ".join(teile)


# ---------------------------------------------------------------- Größe und Reichweite

def _mod(v):
    return (int(v) - 10) // 2


def basis_groesse(c):
    """Größenkategorie (Index) eines Charakters: Feld `groesse` (Name), sonst aus `groesseFelder`, sonst Mittel."""
    if c.get("groesse"):
        return groesse_index(c["groesse"])
    f = int(c.get("groesseFelder") or 1)
    return {1: 4, 2: 5, 3: 6, 4: 7}.get(f, 8 if f >= 5 else 4)


def neue_groesse(basis_idx, stufen):
    return max(0, min(8, basis_idx + int(stufen)))


def reichweite_felder(idx, koerperbau="hoch", extra=0, meter_pro_feld=1.5):
    tab = REICHWEITE_LANG if str(koerperbau).lower().startswith("lang") else REICHWEITE_HOCH
    return max(1, math.ceil(tab[idx] / meter_pro_feld)) + int(extra)


def token_felder_groesse(idx, basis_felder):
    """Tokengröße in Feldern: unveränderte Kategorie behält die eingetragene Größe."""
    return FELDER[idx]


def _wuerfel_stufen(schaden, stufen):
    m = re.match(r"^(\s*\d+W\d+)(.*)$", schaden or "")
    if not m or stufen == 0:
        return schaden
    kopf = m.group(1).replace(" ", "")
    for _ in range(abs(stufen)):
        tab = _HOCH if stufen > 0 else _RUNTER
        if kopf not in tab:
            return schaden  # unbekannte Würfelkombination: unverändert lassen
        kopf = tab[kopf]
    return kopf + m.group(2)


def _schaden_plus(schaden, plus):
    """Addiert einen festen Wert auf den ersten Würfelausdruck, z. B. 1W6+2 → 1W6+4."""
    if not schaden or not plus:
        return schaden
    m = re.match(r"^(\s*\d+W\d+)\s*([+-]\s*\d+)?(.*)$", schaden)
    if not m:
        return schaden
    fest = int((m.group(2) or "0").replace(" ", "")) + plus
    return m.group(1) + (f"{fest:+d}" if fest else "") + m.group(3)


# ---------------------------------------------------------------- wirksame Werte

def _baue(c, s, ist_fern, mpf):
    """Gemeinsamer Kern: aus Basis c und Summe s die Änderungen als Dict {Schlüssel: neuer Wert} + Meta."""
    attr = c.get("attribute") or {}
    d_attr = {k: s.get(k, 0) for k in ATTRIBUTE}
    dm = {}
    for k in ("ST", "GE", "KO"):
        v = attr.get(k)
        dm[k] = (_mod(v + d_attr[k]) - _mod(v)) if v is not None and d_attr[k] else 0
    ge_alt = _mod(attr["GE"]) if attr.get("GE") is not None else 0
    ge_neu = _mod(attr["GE"] + d_attr["GE"]) if attr.get("GE") is not None else 0
    d_adff_ge = min(0, ge_neu) - min(0, ge_alt)
    b_idx = basis_groesse(c)
    n_idx = neue_groesse(b_idx, s.get("groesse", 0))
    d_ang_g = MOD_ANGRIFF[n_idx] - MOD_ANGRIFF[b_idx]
    d_kmb_g = MOD_KMB[n_idx] - MOD_KMB[b_idx]
    wuerfel = n_idx - b_idx
    return {"attr": d_attr, "dm": dm, "d_adff_ge": d_adff_ge, "b_idx": b_idx, "n_idx": n_idx,
            "d_ang_g": d_ang_g, "d_kmb_g": d_kmb_g, "wuerfel": wuerfel}


def char_wirksam(c, ist_fern=lambda a: False, mpf=1.5):
    """Gibt c mit angewendeten Modi zurück (c selbst bleibt unverändert).

    Geänderte Spitzenschlüssel werden als Kopie ersetzt; die Originale stehen in `_basis`, der berechnete Stand in
    `_eff` (zum Erkennen von Handänderungen beim Speichern). `_wirkung` beschreibt Größe/Reichweite für Server und
    Oberfläche. Alle drei Schlüssel werden nie in die Datei geschrieben (siehe `speicherbar`)."""
    mods = aktive(c)
    if not mods:
        return c
    s = summe(mods)
    k = _baue(c, s, ist_fern, mpf)
    dm, dg, dk = k["dm"], k["d_ang_g"], k["d_kmb_g"]
    eff = dict(c)
    basis = {}

    def aender(key):
        if key not in basis and key in c:
            basis[key] = c[key]
            eff[key] = copy.deepcopy(c[key])
        return eff.get(key)

    if any(k["attr"].values()) and isinstance(c.get("attribute"), dict):
        a = aender("attribute")
        for n, v in k["attr"].items():
            if v and a.get(n) is not None:
                a[n] = a[n] + v
    rk = aender("rk")
    if isinstance(rk, dict):
        for n, extra in (("normal", s.get("rk", 0) + s.get("rkr", 0) + dm["GE"]),
                         ("beruehrung", s.get("rk", 0) + s.get("rkb", 0) + dm["GE"]),
                         ("adff", s.get("rkr", 0) + s.get("rkf", 0) + k["d_adff_ge"])):
            if rk.get(n) is not None:
                rk[n] += extra + dg
    rw = aender("rw")
    if isinstance(rw, dict):
        for n, extra in (("REF", s.get("ref", 0) + dm["GE"]), ("WIL", s.get("wil", 0)), ("ZAEH", s.get("zaeh", 0) + dm["KO"])):
            if rw.get(n) is not None:
                rw[n] += extra + s.get("rw", 0)
    for key, extra in (("kmb", s.get("kmb", 0) + dm["ST"] + dk), ("kmv", s.get("kmv", 0) + dm["ST"] + dm["GE"] + dk),
                       ("ini", s.get("ini", 0) + dm["GE"]), ("bewegung", s.get("tempo", 0))):
        if extra and isinstance(c.get(key), (int, float)):
            aender(key)
            eff[key] = c[key] + extra
    if isinstance(c.get("angriffe"), list) and (s.get("angriff") or s.get("nahangriff") or s.get("fernangriff")
                                               or s.get("schaden") or s.get("extraangriff") or any(dm.values())
                                               or dg or k["wuerfel"]):
        aender("angriffe")
        for a in eff["angriffe"]:
            fern = bool(ist_fern(a))
            d_ang = s.get("angriff", 0) + dg + (s.get("fernangriff", 0) + dm["GE"] if fern else s.get("nahangriff", 0) + dm["ST"])
            d_sch = 0 if fern else s.get("schaden", 0) + dm["ST"]
            stufen = 0 if fern else k["wuerfel"]

            def bearbeite(x):
                if isinstance(x, dict):
                    y = dict(x)
                    if "bonus" in y:
                        y["bonus"] = int(y["bonus"]) + d_ang
                    if y.get("schaden"):
                        y["schaden"] = _schaden_plus(_wuerfel_stufen(y["schaden"], stufen), d_sch)
                    return y
                return int(x) + d_ang

            if a.get("bonus") is not None:
                a["bonus"] = int(a["bonus"]) + d_ang
            if a.get("schaden"):
                a["schaden"] = _schaden_plus(_wuerfel_stufen(a["schaden"], stufen), d_sch)
            if isinstance(a.get("serie"), list):
                alt = list(a["serie"])
                a["serie"] = [bearbeite(x) for x in alt]
                if s.get("extraangriff") and a["serie"]:
                    a["serie"] = [a["serie"][0]] * max(0, s["extraangriff"]) + a["serie"]
                zahlen = [x for x in a["serie"] if not isinstance(x, dict)]
                if zahlen and len(zahlen) == len(a["serie"]) and a.get("name"):
                    a["name"] = re.sub(r"\(\s*[+-]?\d+(?:\s*/\s*[+-]?\d+)*\s*\)",
                                       "(" + "/".join(f"{int(x):+d}" for x in a["serie"]) + ")", a["name"], count=1)
    if isinstance(c.get("fertigkeiten"), list):
        aender_f = False
        for f in c["fertigkeiten"]:
            nm = (f.get("name") or "")
            extra = sum(v for key, v in s.items() if key.startswith("fert:") and nm.lower().startswith(key[5:].lower()))
            if nm.lower().startswith("heimlichkeit"):
                extra += MOD_HEIMLICH[k["n_idx"]] - MOD_HEIMLICH[k["b_idx"]]
            if nm.lower().startswith("fliegen"):
                extra += MOD_FLIEGEN[k["n_idx"]] - MOD_FLIEGEN[k["b_idx"]]
            if extra:
                if not aender_f:
                    aender("fertigkeiten")
                    aender_f = True
                for g in eff["fertigkeiten"]:
                    if g.get("name") == nm and g.get("bonus") is not None:
                        g["bonus"] = int(g["bonus"]) + extra
    groesse_aendert = s.get("groesse", 0) != 0
    wirk = {"groesse": GROESSEN[k["n_idx"]], "groesseIdx": k["n_idx"], "groesseBasis": GROESSEN[k["b_idx"]],
            "groesseAendert": groesse_aendert, "summe": s}
    if groesse_aendert or s.get("reichweite"):
        wirk["reichweite"] = reichweite_felder(k["n_idx"], c.get("koerperbau", "hoch"), s.get("reichweite", 0), mpf)
    if groesse_aendert:
        wirk["tokenGroesse"] = FELDER[k["n_idx"]]
    eff["_basis"] = basis
    eff["_eff"] = {key: copy.deepcopy(eff[key]) for key in basis}
    eff["_wirkung"] = wirk
    return eff


def speicherbar(c):
    """Entfernt abgeleitete Schlüssel und stellt die Basiswerte wieder her, die nicht von Hand geändert wurden."""
    if "_basis" not in c:
        for k in ("_eff", "_wirkung"):
            c.pop(k, None)
        return c
    aus = {k: v for k, v in c.items() if k not in ("_basis", "_eff", "_wirkung")}
    eff = c.get("_eff") or {}
    for key, orig in (c.get("_basis") or {}).items():
        if key in aus and key in eff:
            aus[key] = _zurueck(aus[key], eff[key], orig)
    return aus


def _zurueck(neu, eff, orig):
    """Unverändert gebliebene Teile (gleich dem berechneten Stand) werden wieder zum Basiswert;
    von Hand geänderte Teile bleiben erhalten."""
    if neu == eff:
        return orig
    if isinstance(neu, dict) and isinstance(eff, dict) and isinstance(orig, dict):
        return {k: (_zurueck(v, eff[k], orig[k]) if k in eff and k in orig else v) for k, v in neu.items()}
    if isinstance(neu, list) and isinstance(eff, list) and isinstance(orig, list) and len(neu) == len(eff) == len(orig):
        return [_zurueck(n, e, o) for n, e, o in zip(neu, eff, orig)]
    return neu


# ---------------------------------------------------------------- Token (Gegner/NSC ohne Charakterdatei)

TOKEN_BASIS = ("rk", "rkBeruehrung", "rkAdff", "ref", "wil", "zaeh", "groesse", "reichweite")


def _token_idx(t, basis, s):
    b = groesse_index(t["groesseKat"]) if t.get("groesseKat") else {1: 4, 2: 5, 3: 6, 4: 7}.get(int(basis.get("groesse") or 1), 4)
    return b, neue_groesse(b, s.get("groesse", 0))


def token_angriff_mods(t, fern=False):
    """Angriffsmodifikatoren aus Modi eines Tokens ohne Charakterdatei: [(Text, Wert)] (Hast, Größe …)."""
    out = []
    for m in aktive(t):
        w = m["wirkung"]
        v = w.get("angriff", 0) + w.get("fernangriff" if fern else "nahangriff", 0)
        if v:
            out.append((m["name"], v))
    basis = t.get("modiBasis")
    if basis is not None:
        b, n = _token_idx(t, basis, summe(aktive(t)))
        if MOD_ANGRIFF[n] != MOD_ANGRIFF[b]:
            out.append(("Größe", MOD_ANGRIFF[n] - MOD_ANGRIFF[b]))
    return out


def token_anwenden(t, mpf=1.5):
    """Berechnet die Werte eines Tokens aus `modiBasis` (bzw. sichert sie beim ersten Modus) und seinen Modi.
    Gibt den Summen-Dict zurück. Ohne Modi werden die Basiswerte zurückgeschrieben und `modiBasis` entfernt."""
    mods = aktive(t)
    if mods and "modiBasis" not in t:
        t["modiBasis"] = {k: t.get(k) for k in TOKEN_BASIS}
    basis = t.get("modiBasis")
    if basis is None:
        return {}
    s = summe(mods)
    b_idx, n_idx = _token_idx(t, basis, s)
    dg = MOD_ANGRIFF[n_idx] - MOD_ANGRIFF[b_idx]

    def setze(key, wert):
        if wert is None:
            t.pop(key, None)
        else:
            t[key] = wert

    for key, extra in (("rk", s.get("rk", 0) + s.get("rkr", 0) + dg), ("rkBeruehrung", s.get("rkb", 0) + s.get("rk", 0) + dg),
                       ("rkAdff", s.get("rkr", 0) + s.get("rkf", 0) + dg),
                       ("ref", s.get("ref", 0) + s.get("rw", 0)), ("wil", s.get("wil", 0) + s.get("rw", 0)),
                       ("zaeh", s.get("zaeh", 0) + s.get("rw", 0))):
        b = basis.get(key)
        setze(key, None if b is None else b + extra)
    if s.get("groesse"):
        t["groesse"] = FELDER[n_idx] if n_idx != b_idx else (basis.get("groesse") or 1)
        t["reichweite"] = reichweite_felder(n_idx, t.get("koerperbau", "hoch"), s.get("reichweite", 0), mpf)
    elif s.get("reichweite"):
        t["groesse"] = basis.get("groesse") or 1
        t["reichweite"] = reichweite_felder(b_idx, t.get("koerperbau", "hoch"), s["reichweite"], mpf)
    else:
        t["groesse"] = basis.get("groesse") or 1
        setze("reichweite", basis.get("reichweite"))
    if not mods:
        t.pop("modiBasis", None)
        t.pop("modi", None)
    return s
