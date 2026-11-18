"""Magie: Klassenfähigkeiten aus faehigkeitenListe (Energie fokussieren im Umkreis, Heilung, Würfe, SL-Auswertung)."""
from bereiche import charakter as CH, kampf as KM, karte as KA
from bereiche.kern import Fehler
from .zauber import ziel_pruefen


def faehigkeit_def(e):
    """Fähigkeit mit Standardwerten (Aktion keine, Modus sl, Ziel keins)."""
    d = dict(e)
    d.setdefault("aktion", "keine")
    d.setdefault("modus", "sl")
    d.setdefault("ziel", "keins")
    return d


def bereich_ziele(kx, t, radius_m):
    """Nicht-SC-Token im Umkreis (Meter) um t auf derselben Karte."""
    m = KA.aktive(kx).get("meterProFeld", 1.5)
    return [s for s in kx.z["tokens"].values()
            if s["art"] != "sc" and s.get("karte") == t.get("karte") and KA.abstand(t, s) * m <= radius_m]


def nutzen(kx, t, c, index, ziel=None):
    z = kx.z
    liste = c.get("faehigkeitenListe") or []
    if not 0 <= index < len(liste):
        raise Fehler("Fähigkeit nicht gefunden")
    d = faehigkeit_def(liste[index])
    ini = z["initiative"]
    offensiv = d["modus"] == "bereich" or d["ziel"] == "gegner"
    if ini.get("aktiv"):
        KM.darf_handeln(kx, t)
        if not KM.aktion_frei(kx, d["aktion"] if d["aktion"] in ("keine", "schnell", "bewegung") else "standard"):
            raise Fehler("Dafür ist keine passende Aktion mehr frei")
    elif offensiv and z.get("angriffAusserhalb"):
        raise Fehler("Der Kampf beginnt – wartet auf den Spielleiter")
    if KM.unfaehig(t):
        raise Fehler(f"{t['name']} kann nicht handeln")
    if d["ziel"] in ("gegner", "verbuendet"):
        rw = d.get("reichweite", "beruehrung")
        ziel_pruefen(kx, t, ziel, d["ziel"], "beruehrung" if rw == "beruehrung" else None,
                     float(rw) if rw != "beruehrung" else 0, was="Fähigkeit")

    if ini.get("aktiv") and d["aktion"] != "keine":
        z["zug"][{"schnell": "schnell", "bewegung": "bewegung"}.get(d["aktion"], "standard")] = True

    wo = f" auf {ziel['name']}" if ziel is not None and ziel is not t else ""
    titel = f"{t['name']} nutzt {d['name']}{wo}"
    wecken = False
    if d["modus"] == "bereich":
        ziele = bereich_ziele(kx, t, float(d["radius"]))
        sg = int(d["sg"]) if d.get("sg") is not None else 10
        dd = {**d, "sg": sg}
        offen = KA.offen(KA.aktive(kx))
        sichtbar = [s for s in ziele if KA.sichtbar(s, offen)]
        kx.protokoll("zauber", titel, wer=t["name"],
                     ergebnisText=f"{len(ziele)} Ziel(e) im Umkreis von {d['radius']:g} m"
                     if sichtbar or not ziele else "Umkreis wird ausgewertet", detail=d.get("effekt", ""))
        for s in ziele:
            if d.get("untotHeilt") and s.get("untot"):
                h, detail, _ = kx.wuerfeln(d["schaden"])
                if s.get("tp") is not None:
                    s["tp"] = min(s["tp"] + h, s.get("tpMax") or s["tp"] + h)
                kx.protokoll("sl-notiz", f"{titel}: {s['name']} (Untot) heilt {h} TP ({detail})", verborgen=True)
                if s in sichtbar:
                    kx.protokoll("zauber", f"{s['name']} wird gestärkt", wer=t["name"])
            else:
                KM.rettungswurf(kx, t, s, dd, f"{titel} → {s['name']}", verdeckt=True)
        if not ziele:
            kx.protokoll("sl-notiz", f"{titel}: niemand im Umkreis", verborgen=True)
    elif d["modus"] == "heilung":
        s, detail, _ = kx.wuerfeln(d["schaden"])
        KM.heilen(kx, ziel, s)
        kx.protokoll("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"heilt {s} TP", detail=f"{d['schaden']}: {detail}")
    elif d["modus"] == "wurf":
        s, detail, _ = kx.wuerfeln(d["wurf"])
        kx.protokoll("zauber", titel, wer=t["name"], ergebnis=s, ergebnisText=f"{d['wurf']} = {s}",
                     detail=f"{detail}. {d.get('effekt', '')}")
    else:  # sl: der Spielleiter wertet aus
        wecken = not ini.get("aktiv")
        kx.protokoll("zauber", titel, wer=t["name"], ergebnisText="der Spielleiter wertet aus",
                     detail=d.get("effekt", ""), wecken=wecken)
        if wecken:
            z["slStatus"] = "wartet"

    if not ini.get("aktiv") and not wecken:
        kx.protokoll("zugende", f"{t['name']} hat {d['name']} genutzt.", wecken=True)
        z["slStatus"] = "wartet"


def nutzen_spieler(kx, b):
    """/api/faehigkeit: {id, index, ziel?}."""
    t = KA.finden(kx, b["id"])
    if t["art"] != "sc":
        raise Fehler("Nur eure Charaktere handeln")
    c = CH.von_token(kx, t)
    if not c:
        raise Fehler("Charakter nicht gefunden")
    ziel = KA.finden(kx, b["ziel"]) if b.get("ziel") else None
    nutzen(kx, t, c, int(b["index"]), ziel)
