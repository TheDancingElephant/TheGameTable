"""Wissen: Regelsuche (PRD + Hausregeln), Zaubersuche, Zauberkatalog über die API, Nachschlage-Seite, MCP-Toolliste."""
import json
import subprocess
import sys
import unittest
from urllib.parse import urlencode

from tests.hilfen import TOOL, HTTPFehler, Testkampagne

# regeln/regeln.sqlite ist nicht im Git (zu groß); fehlt sie (frischer Klon), werden diese Tests übersprungen
braucht_regeln = unittest.skipUnless((TOOL / "regeln" / "regeln.sqlite").is_file(),
                                     "regeln/regeln.sqlite fehlt (aus dem ZIP kopieren oder sl.py regeln-aktualisieren)")


class WissenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tk = Testkampagne().starten()
        (cls.tk.ordner / "sl" / "hausregeln.md").write_text(
            "# Hausregeln\n\n## Heldenpunkte\nJeder SC hat 2 Heldenpunkte je Stufe.\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tk.beenden()

    @braucht_regeln
    def test_regel_suchen(self):
        t = self.tk.st.regel_suchen("Gelegenheitsangriff Bewegung verlassen")
        self.assertIn("Gelegenheitsangriff", t)
        # Grundregeln bleiben trotz vieler Zusatzbücher vorn (erster Treffer, nicht ein Talent der Ausbauregeln)
        erster = next(z for z in t.splitlines() if z.startswith("[") and z[1:2].isdigit())
        self.assertIn("] Gelegenheitsangriffe —", erster)
        self.assertIn("Kritische Treffer —", self.tk.st.regel_suchen("Kritischer Treffer bestätigen", max_treffer=3))
        self.assertIn("Beweglichkeit", self.tk.st.regel_schnell("talent", "Beweglichkeit"))
        # Ausbauregeln III: Völker (Volkstalente) und IV: Kampagnen
        self.assertIn("Ausbauregeln III: Völker", self.tk.st.regel_schnell("talent", "Elfisches Kampftraining"))
        self.assertIn("Kampagnenwesenszug", self.tk.st.regel_suchen("Kampagnenwesenszug"))
        # Ausbauregeln V–VII: legendäre Talente, Hybrid- und okkulte Klassen, legendäre Monster (HG/LG)
        self.assertIn("Ausbauregeln V: Legenden", self.tk.st.regel_schnell("talent", "Alkoholische Lebenskraft"))
        self.assertIn("Ausbauregeln VI: Klassen", self.tk.st.regel_schnell("talent", "Amateurdraufgänger"))
        self.assertIn("Zehrung", self.tk.st.regel_suchen("Kinetiker burn"))
        self.assertIn("LG 3", self.tk.st.monster_info("Legendärer Aboleth"))
        # Alternativregeln: eigene Themen finden, Schnellzugriff bleibt beim Grundregelwerk
        self.assertIn("Verletzungsstufen", self.tk.st.regel_suchen("Verletzungsstufen"))
        self.assertIn("Grundregelwerk", self.tk.st.regel_schnell("fertigkeit", "Akrobatik"))
        self.assertIn("Expertenregeln", self.tk.st.regel_schnell("talent", "Heldenglück"))  # Heldenpunkt-Talente
        self.assertIn("Abenteurerkompendium", self.tk.st.regel_schnell("talent", "Wesen ohne Namen"))
        # Ausbauregeln VIII: Intrigen
        self.assertIn("Wortgefechte", self.tk.st.regel_suchen("Gesellschaftlicher Kampf Wortgefecht"))
        self.assertIn("Vigilant", self.tk.st.regel_suchen("Vigilant", typ="klasse"))
        # Spielleiterhandbuch: Spielleitungsregeln und NSC-Werteblöcke
        self.assertIn("Verfolgungsjagden", self.tk.st.regel_suchen("Verfolgungsjagd"))
        self.assertIn("Spielleiterhandbuch", self.tk.st.monster_info("Dorftrottel"))
        # Ausrüstungskompendium; geläufige Umschreibung „Ring des Schutzes“ -> „Schutzring“
        self.assertIn("Tragballon (gegenstand, AUS)", self.tk.st.regel_suchen("Tragballon"))
        self.assertIn("Schutzring", self.tk.st.regel_suchen("Ring des Schutzes", max_treffer=3))

    @braucht_regeln
    def test_monster_info(self):
        t = self.tk.st.monster_info("Lehmgolem")
        self.assertIn("HG 10", t)
        self.assertIn("SR** 10/Adamant", t)
        liste = self.tk.st.monster_info(hg="10", art="Konstrukt")
        self.assertIn("Lehmgolem", liste)
        gug = self.tk.st.monster_info("Gug")  # Monsterhandbuch II
        self.assertIn("Gug (HG", gug)
        self.assertIn("Monsterhandbuch II", gug)
        vettel = self.tk.st.monster_info("Annisvettel")  # Monsterhandbuch III („** TP**“ im PRD-HTML)
        self.assertIn("Annisvettel (HG 6)", vettel)
        self.assertIn("Monsterhandbuch III", vettel)
        self.assertIn("**TP** 66", vettel)
        self.assertIn("Cthulhu (HG 30)", self.tk.st.monster_info("Cthulhu"))  # MHB IV, „**TP 774**“
        self.assertIn("Argus (HG 13, LG 6)", self.tk.st.monster_info("Argus"))  # MHB IV, „(LR 6)“
        self.assertIn("Monsterhandbuch V", self.tk.st.monster_info("Aatheriexa"))
        soeldner = self.tk.st.monster_info("Wilder Söldner")  # NSC-Kompendium („**EP** 200“)
        self.assertIn("NSC-Kompendium", soeldner)
        self.assertIn("Wilder Söldner", self.tk.st.monster_info(hg="1/2", art="Humanoider"))
        self.assertIn("MHB", self.tk.st.regel_suchen("Schwarm Flächenschaden"))

    def test_hausregel_hat_vorrang(self):
        t = self.tk.st.regel_suchen("Heldenpunkte")
        self.assertIn("HAUSREGEL", t.splitlines()[0] + t.splitlines()[1] if len(t.splitlines()) > 1 else t)

    def test_zauber_suchen_und_info(self):
        self.assertIn("Feuerball", self.tk.st.zauber_suchen("Feuerball"))
        info = self.tk.st.zauber_info("Hast")
        self.assertIn("Hast", info)
        self.assertIn("Verwandlung", info)

    def test_zauberkatalog_api(self):
        liste = self.tk.http("/api/zauber")
        self.assertGreater(len(liste), 1500)
        self.assertEqual(len({z["name"] for z in liste}), len(liste))
        z = self.tk.http("/api/zauber?name=Leichte%20Wunden%20heilen")
        self.assertEqual(z["modus"], "heilung")
        self.assertTrue(z["prdText"])

    # -- Nachschlage-Seite (/api/wissen/…)
    def wissen(self, pfad, sl=False, **par):
        return self.tk.http(f"/api/wissen/{pfad}?{urlencode(par)}", sl=sl)

    @braucht_regeln
    def test_nachschlagen_suche_mit_hausregel_zuerst(self):
        t = self.wissen("suche", q="Heldenpunkte")["treffer"]
        self.assertEqual((t[0]["art"], t[0]["id"]), ("hausregel", "H1"))
        h = self.wissen("eintrag", art="hausregel", id="H1")
        self.assertIn("2 Heldenpunkte", h["abschnitte"][0]["text"])
        t = self.wissen("suche", q="Ringkampf", art="regeln")["treffer"]
        self.assertTrue(any(x["titel"].startswith("Ringkampf") and x["kuerzel"] == "GRW" for x in t))
        self.assertTrue(all(x["art"] in ("regel", "hausregel") for x in t))

    @braucht_regeln
    def test_nachschlagen_zauber_und_zustand(self):
        z = self.wissen("eintrag", art="zauber", name="Hast")
        self.assertIn(["Schule", "Verwandlung"], z["felder"])
        self.assertIn("schneller", z["abschnitte"][0]["text"])
        self.assertTrue(z["url"].startswith("https://prd.5footstep.de"))
        liegend = self.wissen("eintrag", art="zustand", name="Liegend")
        self.assertEqual(liegend["titel"], "Liegend")
        self.assertIn("-4", liegend["abschnitte"][0]["text"])
        with self.assertRaises(HTTPFehler) as f:
            self.wissen("eintrag", art="zauber", name="Gibtsnichtzauber")
        self.assertEqual(f.exception.code, 404)

    def test_nachschlagen_zauberfilter_klasse_und_grad(self):
        d = self.wissen("suche", art="zauber", klasse="Barde", grad="1")
        self.assertGreater(d["gesamt"], 50)
        self.assertTrue(all("Barde 1" in x["untertitel"] for x in d["treffer"]))
        self.assertIn("hinweis", self.wissen("suche", art="zauber"))  # ohne Suchwort und Filter keine Liste

    @braucht_regeln
    def test_nachschlagen_monster_nur_fuer_sl(self):
        for par in ({"art": "monster", "q": "Golem"}, {"art": "monster", "hg": "10"}):
            with self.assertRaises(HTTPFehler) as f:
                self.wissen("suche", **par)
            self.assertEqual(f.exception.code, 403)
        with self.assertRaises(HTTPFehler) as f:
            self.wissen("eintrag", art="monster", name="Lehmgolem")
        self.assertEqual(f.exception.code, 403)
        m = self.wissen("eintrag", sl=True, art="monster", name="Lehmgolem")
        self.assertIn("HG 10", m["untertitel"])
        self.assertTrue(any("10/Adamant" in (a["text"] or "") for a in m["abschnitte"]))
        with self.assertRaises(HTTPFehler) as f:  # auch über die Abschnitts-ID nicht
            self.wissen("eintrag", art="regel", id=m["id"])
        self.assertEqual(f.exception.code, 403)
        # Spieler: keine Monsterseiten in Suche und Inhalt, allgemeine Monsterregeln schon
        t = self.wissen("suche", q="Golem")["treffer"]
        self.assertFalse(any(x["art"] == "monster" or x["titel"] == "Golem" or x["titel"].startswith("Golem,")
                             for x in t))  # „Golemkonstrukteur“ (Regel aus Ausbauregeln: Magie) darf erscheinen
        self.assertFalse(self.wissen("suche", q="Gug")["treffer"] and any(  # Monsterhandbuch II ebenso
            x["titel"].startswith("Gug") for x in self.wissen("suche", q="Gug")["treffer"]))
        self.assertFalse(any(x["titel"].startswith("Annisvettel")  # Monsterhandbuch III
                             for x in self.wissen("suche", q="Annisvettel")["treffer"]))
        self.assertFalse(any(x["titel"].startswith("Cthulhu")  # Monsterhandbuch IV
                             for x in self.wissen("suche", q="Cthulhu")["treffer"]))
        self.assertFalse(any(x["titel"].startswith("Wilder Söldner")  # NSC-Kompendium
                             for x in self.wissen("suche", q="Wilder Söldner")["treffer"]))
        self.assertFalse(any(x["titel"].startswith("Dorftrottel")  # NSC-Galerie (Spielleiterhandbuch)
                             for x in self.wissen("suche", q="Dorftrottel")["treffer"]))
        self.assertFalse(any(x["titel"].startswith("Legendärer Aboleth")  # legendäre Monster (Ausbauregeln V)
                             or "Legendäre Monster" in (x.get("untertitel") or "")
                             for x in self.wissen("suche", q="Legendärer Aboleth")["treffer"]))
        self.assertTrue(any(x["titel"].startswith("Legendärer Aboleth")
                            for x in self.wissen("suche", sl=True, q="Legendärer Aboleth")["treffer"]))
        self.assertTrue(any(x["titel"] == "Golem" for x in self.wissen("suche", sl=True, q="Golem")["treffer"]))
        self.assertTrue(self.wissen("suche", q="Regeneration")["treffer"])
        buecher = {b["titel"]: b for b in self.wissen("inhalt")["buecher"]}
        mhb = [k["titel"] for k in buecher["Monster"]["kapitel"]]  # alle Monsterhandbücher als ein Bereich
        self.assertFalse(any(t.startswith("Monsterhandbuch") for t in buecher))
        self.assertFalse(buecher["Monster"]["monsterTabelle"])
        self.assertIn("Kreaturenarten", mhb)
        self.assertNotIn("Golem", mhb)
        self.assertNotIn("Monster nach HG", mhb)
        # SL: auch im Inhalt keine einzelnen Monster (die stehen in der Monster-Liste), aber der Verweis darauf
        sl_monster = {b["titel"]: b for b in self.wissen("inhalt", sl=True)["buecher"]}["Monster"]
        self.assertTrue(sl_monster["monsterTabelle"])
        self.assertNotIn("Golem", [k["titel"] for k in sl_monster["kapitel"]])
        # Buchfilter: „Monster“ statt einzelner Bände, trifft alle Monsterhandbücher
        self.assertIn("Monster", self.wissen("filter")["buecher"])
        self.assertNotIn("Monsterhandbuch II", self.wissen("filter")["buecher"])
        t = self.wissen("suche", sl=True, q="Gug", buch="Monster")["treffer"]
        self.assertTrue(t and all(x["buch"].startswith("Monsterhandbuch") for x in t))

    @braucht_regeln
    def test_nachschlagen_filterlisten_und_seite(self):
        f = self.wissen("filter")
        self.assertFalse(f["sl"])
        self.assertNotIn("monsterArten", f)
        self.assertNotIn("monster", f["typen"])
        self.assertIn("Liegend", f["zustaende"])
        self.assertIn("Barde", f["zauberKlassen"])
        self.assertTrue(f["hausregeln"])
        fs = self.wissen("filter", sl=True)
        self.assertTrue(fs["sl"])
        self.assertIn("Konstrukt", fs["monsterArten"])
        kampf = next(k for b in self.wissen("inhalt")["buecher"] for k in b["kapitel"] if k["titel"] == "Kampf")
        s = self.wissen("inhalt", seite=kampf["id"])
        self.assertTrue(any(a["titel"] == "Gelegenheitsangriffe" for a in s["abschnitte"]))
        self.assertIn(b"Nachschlagen", self.tk.http("/nachschlagen.html", roh=True))

    @braucht_regeln
    def test_nachschlagen_talent_tabelle(self):
        t = self.wissen("talente")
        self.assertGreater(len(t["zeilen"]), 300)
        self.assertIn("Kampf", t["arten"])
        self.assertIn("Allgemein", t["arten"])  # Talente ohne Art
        bw = next(z for z in t["zeilen"] if z["name"] == "Beweglichkeit")
        self.assertIn("Ausweichen", bw["voraussetzungen"])
        self.assertIn("Kampf", bw["arten"])
        self.assertEqual(bw["kuerzel"], "GRW")
        self.assertIn("Beweglichkeit", self.wissen("eintrag", art="regel", id=bw["id"])["titel"])  # Klick → Volltext

    def test_nachschlagen_zauber_tabelle(self):
        t = self.wissen("zauber", klasse="Magier", grad="3")
        fb = next(z for z in t["zeilen"] if z["name"] == "Feuerball")
        self.assertEqual(fb["grad"], 3)
        self.assertEqual(fb["schule"], "Hervorrufung [Feuer]")
        self.assertTrue(fb["reichweite"].startswith("Lang"))
        self.assertTrue(fb["rettungswurf"] and fb["zauberresistenz"] and fb["wirkungsdauer"] and fb["kurz"])
        self.assertTrue(all(z["grad"] == 3 for z in t["zeilen"]))
        self.assertEqual(t["gesamt"], len(t["zeilen"]))
        self.assertGreater(self.wissen("zauber")["gesamt"], 1500)  # ohne Filter alle Zauber
        self.assertEqual([z["name"] for z in self.wissen("zauber", q="Feuerball")["zeilen"]][0], "Feuerball")


class PDFIndexTest(unittest.TestCase):
    """Privater PDF-Index: kleines Test-PDF mit Lesezeichen einlesen und durchsuchen (eigene Datei, nicht privat.sqlite)."""

    def test_pdf_einlesen_und_suchen(self):
        import tempfile
        from pathlib import Path

        import pymupdf

        from bereiche.wissen import regeln_db, regeln_pdf
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "Testbuch.pdf"
            doc = pymupdf.open()
            for i, (titel, text) in enumerate([("Die Drachenküste", "Am Rand der Drachenküste liegt Feuerhafen. " * 30),
                                                ("Der Glutberg", "Der Glutberg speit jedes Jahr Asche. " * 30)]):
                seite = doc.new_page()
                seite.insert_text((72, 72), titel, fontsize=18)
                seite.insert_textbox(pymupdf.Rect(72, 100, 520, 760), text, fontsize=9)
            doc.set_toc([[1, "Die Drachenküste", 1], [1, "Der Glutberg", 2]])
            doc.save(pdf)
            doc.close()
            ziel = Path(tmp) / "privat.sqlite"
            bericht = regeln_pdf.einlesen([tmp], ziel=ziel, meldung=lambda t: None)
            self.assertIn("1 PDFs", bericht)
            treffer = regeln_db.suchen("Glutberg Asche", datei=ziel)
            self.assertTrue(treffer)
            self.assertEqual(treffer[0]["titel"], "Der Glutberg")
            self.assertTrue(treffer[0]["url"].startswith("pdf:Testbuch.pdf#S. 2"))
            # unverändertes PDF wird beim zweiten Lauf nicht neu gelesen
            self.assertIn("unverändert 1", regeln_pdf.einlesen(None, ziel=ziel, meldung=lambda t: None))
            regeln_db.db(ziel).close()


class MCPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tk = Testkampagne().starten()

    @classmethod
    def tearDownClass(cls):
        cls.tk.beenden()

    def mcp(self, nachrichten):
        eingabe = "".join(json.dumps(m) + "\n" for m in nachrichten)
        r = subprocess.run([sys.executable, str(TOOL / "mcp_server.py"), "--kampagne", str(self.tk.ordner)],
                           input=eingabe.encode("utf-8"), capture_output=True, timeout=60, cwd=str(TOOL))
        return [json.loads(z) for z in r.stdout.decode("utf-8").splitlines() if z.strip()]

    def test_toolliste_eindeutig(self):
        antw = self.mcp([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        tools = next(a for a in antw if a.get("id") == 2)["result"]["tools"]
        namen = [t["name"] for t in tools]
        self.assertEqual(len(namen), len(set(namen)))
        self.assertGreaterEqual(len(namen), 80)
        for n in ("stand", "erzaehle", "warte", "angriff", "ini", "modus", "zauber_info", "regel_suchen", "kasse",
                  "monster_info", "regeln_pdf"):
            self.assertIn(n, namen)


if __name__ == "__main__":
    unittest.main()
