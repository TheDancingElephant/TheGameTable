"""Liest ausfüllbare deutsche PF1-Charakterbögen (PDF-Formular) in das Spieltisch-Format."""
import re
import pymupdf

FERTIGKEITEN = [
    "Akrobatik", "Auftreten 1", "Auftreten 2", "Beruf 1", "Beruf 2", "Bluffen", "Diplomatie", "Einschüchtern",
    "Entfesselungskunst", "Fingerfertigkeit", "Fliegen", "Handwerk 1", "Handwerk 2", "Handwerk 3", "Heilkunde",
    "Heimlichkeit", "Klettern", "Magischen Gegenstand benutzen", "Mechanismus ausschalten", "Mit Tieren umgehen",
    "Motiv erkennen", "Reiten", "Schätzen", "Schwimmen", "Sprachenkunde", "Überlebenskunst", "Verkleiden",
    "Wahrnehmung", "Wissen (Adel und Königshäuser)", "Wissen (Arkanes)", "Wissen (Baukunst)", "Wissen (Die Ebenen)",
    "Wissen (Geographie)", "Wissen (Geschichte)", "Wissen (Gewölbekunde)", "Wissen (Lokales)", "Wissen (Natur)",
    "Wissen (Religion)", "Zauberkunde",
]
FARBEN = ["#3a7bd5", "#2e9e6a", "#b8642f", "#8e4bc2", "#c23b6e", "#2a9bb0"]


def _zahl(v):
    if v is None:
        return None
    m = re.search(r"-?\d+", str(v).replace("−", "-").replace(" ", ""))
    return int(m.group()) if m else None


def _text(v):
    return (v or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def felder(pfad):
    werte = {}
    for p in pymupdf.open(pfad):
        for w in p.widgets():
            v = w.field_value
            if w.field_name not in werte and v not in (None, "", "Off", False):
                werte[w.field_name] = v
    return werte


NAMENS_KORREKTUR = {"sleep": "Schlaf", "gött": "Göttliche", "göttliche": "Göttliche Führung", "götttliche gunst": "Göttliche Gunst",
                    "geringere verwirrung": "Schwächere Verwirrung", "federall": "Federfall",
                    "l. wunden heilen": "Leichte Wunden heilen", "fürchterlicher lachanfall": "Fürchterlicher Lachanfall",
                    "katzenhafte anmut": "Katzenhafte Anmut", "sengender strahl (+ 50%)": "Sengender Strahl"}


def zauberliste_aus_text(text):
    """'Grad 1: Magisches Geschoß 1x, Sleep' -> [{name, grad, proTag, verbraucht}]"""
    liste = []
    for zeile in (text or "").splitlines():
        m = re.match(r"Grad (\d+):\s*(.*)", zeile)
        if not m:
            continue
        grad = int(m.group(1))
        for teil in m.group(2).split(","):
            teil = teil.strip()
            if not teil:
                continue
            anzahl = re.search(r"(\d+)\s*x\b", teil)
            name = " ".join(re.sub(r"\(D\)|\(\s*SG\s*\d+\s*\)|\d+\s*x\b", "", teil.lstrip("-")).split()).replace("Geschoß", "Geschoss")
            name = re.sub(r"(\w)\(", r"\1 (", name)
            name = NAMENS_KORREKTUR.get(name.lower(), name)
            name = name[:1].upper() + name[1:]
            liste.append({"name": name, "grad": grad,
                          "proTag": None if grad == 0 else int(anzahl.group(1)) if anzahl else 1,
                          "verbraucht": 0})
    return liste


def aus_pdf(pfad, farbe_index=None):
    f = felder(pfad)
    name = _text(f.get("Charaktername")) or "Unbenannt"
    cid = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")

    angriffe = []
    for i in range(1, 6):
        if f.get(f"Waffe{i}"):
            angriffe.append({
                "name": _text(f.get(f"Waffe{i}")),
                "bonus": _zahl(f.get(f"Angriffsbonus{i}")) or 0,
                "schaden": _text(f.get(f"Schaden{i}")).replace(" ", "").replace("w", "W"),
                "krit": _text(f.get(f"Kritischer Treffer{i}")),
                "art": _text(f.get(f"Art{i}")),
                "reichweite": _text(f.get(f"Reichweite{i}")),
            })

    fertigkeiten = []
    for i, n in enumerate(FERTIGKEITEN, start=1):
        wert = _zahl(f.get(f"G.{i}"))
        if wert is not None:
            fertigkeiten.append({"name": n, "bonus": wert, "klasse": f.get(f"KK{i:02d}") == "Ja"})

    zauber = []
    for g in range(0, 10):
        t = _text(f.get(f"Grad {g} Zauber"))
        if t:
            zauber.append(f"Grad {g}: " + ", ".join(x.strip() for x in t.split("\n") if x.strip()))
    faehigkeiten = [_text(f[k]) for k in sorted((k for k in f if k.startswith("Besondere Fähigkeit.")),
                                                 key=lambda k: int(k.split(".")[1])) if _text(f[k])]
    talente = [_text(f[k]).lstrip("-") for k in sorted((k for k in f if k.startswith("Talent.")),
                                                        key=lambda k: int(k.split(".")[1])) if _text(f[k])]
    ausruestung = [_text(f[k]) for k in sorted((k for k in f if k.startswith("Gegenstand.")),
                                                key=lambda k: int(k.split(".")[1])) if _text(f[k])]

    tp = _zahl(f.get("TP"))
    hinweise = []
    if tp is None:
        hinweise.append("TP fehlen im Bogen – bitte eintragen.")

    return {
        "id": cid,
        "name": name,
        "klasse": _text(f.get("Klasse und Stufe")),
        "volk": _text(f.get("Volk")),
        "gesinnung": _text(f.get("Gesinnung")),
        "gottheit": _text(f.get("Gottheit")),
        "farbe": FARBEN[(farbe_index if farbe_index is not None else sum(map(ord, cid))) % len(FARBEN)],
        "attribute": {k: _zahl(f.get(k)) for k in ("ST", "GE", "KO", "IN", "WE", "CH")},
        "tp": {"max": tp, "aktuell": tp},
        "rk": {"normal": _zahl(f.get("RK")), "beruehrung": _zahl(f.get("Berührung")), "adff": _zahl(f.get("ADFF"))},
        "ini": _zahl(f.get("INI")) or 0,
        "gab": _zahl(f.get("GAB")) or 0,
        "kmb": _zahl(f.get("KMB")) or 0,
        "kmv": _zahl(f.get("KMV")) or 0,
        "rw": {"REF": _zahl(f.get("REF")) or 0, "WIL": _zahl(f.get("WIL")) or 0, "ZAEH": _zahl(f.get("ZÄH")) or 0},
        "bewegung": _zahl(f.get("MitRüstung_meter")) or _zahl(f.get("Grundbewegungsrate_meter")) or 9,
        "angriffe": angriffe,
        "fertigkeiten": fertigkeiten,
        "zauber": "\n".join(zauber),
        "zauberliste": zauberliste_aus_text("\n".join(zauber)),
        "faehigkeiten": "\n".join(faehigkeiten),
        "talente": "\n".join(talente),
        "ausruestung": "\n".join(ausruestung),
        "notizen": "\n".join(hinweise + [f"Importiert aus {pfad.split('/')[-1].split(chr(92))[-1]} – Werte bitte prüfen."]),
    }
