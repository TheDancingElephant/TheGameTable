"""Charakter: Ablauf des Stufenaufstiegs (Spieler-Assistent → Antrag → Freigabe durch den SL).

Die Regeln (Plan, Prüfung, Anwenden) stehen in `aufstieg.py`.
"""
from bereiche.kern import Fehler
from . import aufstieg as AUF
from .ep import ep_info
from .werte import laden, sc_token, speichern


def _laden(kx, b):
    """Charakter für den Assistenten holen und Voraussetzungen prüfen."""
    c = laden(kx, b["charId"])
    info = ep_info(kx, c)
    if kx.z["initiative"].get("aktiv"):
        raise Fehler("Stufenaufstiege erst nach dem Kampf")
    if c.get("aufstieg") or info["aufstiegMoeglich"]:
        return c, info
    raise Fehler(f"{c['name']} hat noch nicht genug Erfahrung")


def spieler(kx, schritt, b):
    """schritt: 'plan', 'tp' oder 'senden' (Pfade /api/aufstieg-plan|-tp|-senden)."""
    c, info = _laden(kx, b)
    auf = c.get("aufstieg")
    if auf is None:
        auf = {"zielStufe": info["stufe"] + 1, "status": "entwurf"}
    if auf.get("status") == "freigegeben":
        raise Fehler("Dieser Aufstieg ist schon abgeschlossen")
    klasse = (b.get("klasse") or auf.get("klasse") or "").strip() or None
    vorlage = b["vorlage"] if "vorlage" in b else auf.get("vorlage")
    vorlagen = b["vorlagen"] if "vorlagen" in b else auf.get("vorlagen")
    p = AUF.plan(c, auf["zielStufe"], klasse, vorlage, vorlagen)
    if schritt == "plan":
        return {"plan": p, "aufstieg": auf, "tpWuerfelbar": not auf.get("tp")}
    if auf.get("status") == "eingereicht":
        raise Fehler("Der Aufstieg liegt schon beim Spielleiter")
    if schritt == "tp":
        if not auf.get("tp"):  # nur einmal: Ergebnis bleibt, auch wenn der Dialog neu geöffnet wird
            plus, text = AUF.tp_wurf(p["tw"], p["koMod"], "wurf" if b.get("art") == "wurf" else "schnitt", kx.w)
            auf["tp"] = {"plus": plus, "text": text}
            auf["klasse"] = p["klasse"]
            auf["vorlage"] = p["vorlage"] or ""
            auf["vorlagen"] = p["vorlagenMap"]
            kx.protokoll("system", f"{c['name']} bestimmt die Trefferpunkte für Stufe {auf['zielStufe']}: +{plus} ({text}).")
        c["aufstieg"] = auf
        speichern(kx, c)
        return {"aufstieg": auf}
    antrag = b.get("antrag") or {}
    fehler, warn = AUF.pruefen(c, p, antrag, auf.get("tp"))
    if fehler:
        raise Fehler("Nicht abschickbar: " + " · ".join(fehler))
    auf.update({"status": "eingereicht", "antrag": antrag, "klasse": p["klasse"], "vorlage": p["vorlage"] or "",
                "vorlagen": p["vorlagenMap"], "warnungen": warn, "kommentar": ""})
    c["aufstieg"] = auf
    speichern(kx, c)
    zus = AUF.zusammenfassung(c, p, antrag, auf["tp"])
    kx.protokoll("aufstieg", f"{c['name']} steigt auf: {p['klasse']} (Stufe {auf['zielStufe']})", wer=c["name"],
                 detail=" · ".join(zus[1:]) + (f" · Hinweise: {'; '.join(warn)}" if warn else ""),
                 wuensche="Antrag wartet auf Freigabe (sl.py aufstieg-fertig " + c["id"] + ")", wecken=True)
    kx.z["slStatus"] = "wartet"
    return {}


def sl(kx, op, b):
    """SL-Befehle aufstieg-zeigen, -zurueck, -fertig, -abbrechen."""
    c = laden(kx, b["charId"])
    auf = c.get("aufstieg")
    if not auf:
        raise Fehler("Kein Aufstieg offen")
    if op == "aufstieg-abbrechen":
        c.pop("aufstieg")
        speichern(kx, c)
        return {}
    p = AUF.plan(c, auf["zielStufe"], auf.get("klasse"), auf.get("vorlage", ""), auf.get("vorlagen"))
    antrag = auf.get("antrag")
    if op == "aufstieg-zeigen":
        if not antrag:
            return {"text": f"Aufstieg auf Stufe {auf['zielStufe']}: Status {auf.get('status')}, noch kein Antrag."}
        f, w = AUF.pruefen(c, p, antrag, auf.get("tp"))
        return {"text": "\n".join(AUF.zusammenfassung(c, p, antrag, auf["tp"])
                                  + [f"FEHLER: {x}" for x in f] + [f"Hinweis: {x}" for x in w])}
    if op == "aufstieg-zurueck":
        if not antrag:
            raise Fehler("Kein Antrag eingereicht")
        auf["status"] = "entwurf"
        auf["kommentar"] = b.get("grund") or ""
        speichern(kx, c)
        kx.protokoll("system", f"Der Spielleiter gibt den Aufstieg von {c['name']} zurück: "
                               f"{auf['kommentar'] or 'bitte überarbeiten'}")
        return {}
    # aufstieg-fertig
    if antrag and auf.get("status") == "eingereicht":
        f, w = AUF.pruefen(c, p, antrag, auf.get("tp"))
        if f:
            raise Fehler("Antrag fehlerhaft: " + " · ".join(f))
        c.pop("aufstieg")
        AUF.anwenden(c, p, antrag, auf["tp"])
        if b.get("klasse"):
            c["klasse"] = b["klasse"]
        speichern(kx, c)
        t = sc_token(kx, c["id"])
        if t:
            t.update({"name": c["name"], "tpMax": c["tp"]["max"], "tp": c["tp"]["aktuell"]})
        kx.protokoll("system", f"⬆ {c['name']} ist jetzt Stufe {c['stufe']} ({c.get('klasse')}).")
        return {}
    if auf.get("status") == "entwurf" and not b.get("erzwingen"):
        raise Fehler("Der Spieler hat den Aufstieg noch nicht abgeschickt (mit --erzwingen trotzdem abschließen)")
    c.pop("aufstieg")  # alter Ablauf: Werte hat der SL von Hand eingetragen
    c["stufe"] = auf["zielStufe"]
    if b.get("klasse"):
        c["klasse"] = b["klasse"]
    speichern(kx, c)
    kx.protokoll("system", f"⬆ {c['name']} ist jetzt Stufe {c['stufe']} ({c.get('klasse')}).")
    return {}
