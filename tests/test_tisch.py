"""Tisch: Stand laden, Erzählen, Status, Sichtfilter, Wecken, Schlüssel."""
import unittest

from tests.hilfen import FEHLER, HTTPFehler, Testkampagne


class TischTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tk = Testkampagne().starten()

    @classmethod
    def tearDownClass(cls):
        cls.tk.beenden()

    def test_stand_laedt_fuer_spieler_und_sl(self):
        s = self.tk.stand()
        self.assertEqual(s["kampagne"], "Testkampagne")
        self.assertNotIn("sl", s)
        self.assertIn("Tot", s["zustaende"])
        self.assertTrue(self.tk.stand(sl=True)["sl"])

    def test_sl_api_ohne_schluessel_verboten(self):
        with self.assertRaises(HTTPFehler) as f:
            self.tk.http("/api/sl/zustand")
        self.assertEqual(f.exception.code, 403)
        with self.assertRaises(HTTPFehler) as f:
            self.tk.http("/api/sl/befehl", {"op": "notiz", "text": "x"})
        self.assertEqual(f.exception.code, 403)

    def test_erzaehle_setzt_status_bereit(self):
        self.tk.sl(op="status", status="denkt")
        self.tk.st.erzaehle("Der Regen fällt.", titel="Am Tor")
        s = self.tk.stand()
        self.assertEqual(s["slStatus"], "bereit")
        e = s["protokoll"][-1]
        self.assertEqual((e["art"], e["text"], e["titel"]), ("sl", "Der Regen fällt.", "Am Tor"))

    def test_sl_notiz_unsichtbar_fuer_spieler(self):
        self.tk.st.notiz("Geheim: Falle bei 3,3")
        self.assertFalse(any("Geheim" in e["text"] for e in self.tk.stand()["protokoll"]))
        self.assertTrue(any("Geheim" in e["text"] for e in self.tk.stand(sl=True)["protokoll"]))

    def test_spieleraktion_weckt_und_warte_liefert_sie(self):
        self.tk.st.erzaehle("Was tut ihr?")
        self.tk.spieler("/api/aktion", {"text": "Wir öffnen die Tür", "wer": "Brak"})
        self.assertEqual(self.tk.stand()["slStatus"], "wartet")
        text = self.tk.st.warte(nachlauf=0, timeout=10)
        self.assertIn("Wir öffnen die Tür", text)
        self.assertEqual(self.tk.stand()["slStatus"], "denkt")
        self.assertIsNone(self.tk.st.warte(nachlauf=0, timeout=1))

    def test_szene_handout_und_streichen(self):
        self.tk.st.szene("Die Mühle", "Abends")
        self.assertEqual(self.tk.stand()["szene"], {"titel": "Die Mühle", "untertitel": "Abends"})
        self.tk.sl(op="handout", id="brief", titel="Ein Brief", text="Kommt allein.")
        self.assertEqual(self.tk.stand()["unterlagen"]["handouts"][-1]["text"], "Kommt allein.")
        self.tk.sl(op="handout-weg", id="brief")
        self.assertFalse(self.tk.stand()["unterlagen"]["handouts"])
        self.tk.st.erzaehle("Wird gestrichen")
        eid = self.tk.letzte_id()
        self.tk.sl(op="eintrag-loeschen", id=eid)
        self.assertNotIn(eid, [e["id"] for e in self.tk.log()])

    def test_sl_wurf_verdeckt(self):
        r = self.tk.sl(op="wurf", ausdruck="2W6+3", grund="Heimlichkeit", verborgen=True)
        self.assertTrue(5 <= r["ergebnis"] <= 15)
        self.assertFalse(any(e.get("text") == "Heimlichkeit" for e in self.tk.stand()["protokoll"]))

    def test_unbekannter_befehl_400(self):
        with self.assertRaises(HTTPFehler) as f:
            self.tk.sl(op="gibtsnicht")
        self.assertEqual(f.exception.code, 400)

    def test_oberflaeche_es_module_werden_ausgeliefert(self):
        import re
        html = self.tk.http("/", roh=True).decode("utf-8")
        self.assertIn('<script type="module" src="app.js"></script>', html)
        offen, gesehen = ["app.js"], set()
        while offen:  # allen relativen Importen folgen
            datei = offen.pop()
            if datei in gesehen:
                continue
            gesehen.add(datei)
            js = self.tk.http("/" + datei, roh=True).decode("utf-8")
            offen += re.findall(r'^import (?:[^"]*from )?"\./([\w-]+\.js)";', js, re.M)
        self.assertGreaterEqual(len(gesehen), 10)

    def test_fehler_nimmt_den_ganzen_befehl_zurueck(self):
        vorher = self.tk.z()
        n = len(self.tk.log())
        with self.assertRaises(FEHLER):
            self.tk.http("/api/sl/befehl", [{"op": "token-setzen", "token": {"name": "Geist", "x": 1, "y": 1, "id": "g99"}},
                                            {"op": "notiz", "text": "halb"}, {"op": "gibtsnicht"}], sl=True)
        nachher = self.tk.z()
        self.assertNotIn("g99", nachher["tokens"])
        self.assertEqual(nachher["naechsteLogId"], vorher["naechsteLogId"])
        self.assertEqual(len(self.tk.log()), n)
        self.tk.neu_starten()  # auch auf der Platte nichts Halbes
        self.assertNotIn("g99", self.tk.z()["tokens"])
        self.assertEqual(len(self.tk.log()), n)

    def test_gruppennotizen_und_anstupsen(self):
        self.tk.spieler("/api/gruppennotizen", {"text": "Schlüssel im Brunnen"})
        self.assertEqual(self.tk.stand()["unterlagen"]["notizen"], "Schlüssel im Brunnen")
        self.tk.sl(op="status", status="bereit")
        self.tk.spieler("/api/anstupsen", {})
        self.assertEqual(self.tk.stand()["slStatus"], "wartet")


if __name__ == "__main__":
    unittest.main()
