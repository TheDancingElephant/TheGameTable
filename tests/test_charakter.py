"""Charakter: EP (HG, geteilt), Aufstieg, char-setzen, Modi (Vorlagen, Dauer, Größe), Charakter speichern."""
import unittest

from tests.hilfen import FEHLER, HTTPFehler, Testkampagne


class CharakterTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()
        self.tk.karte_leer()
        self.brak = self.tk.sc("brak", 5, 5)
        self.lern = self.tk.sc("lern", 8, 8)

    def tearDown(self):
        self.tk.beenden()

    def test_ep_aus_hg_wird_geteilt(self):
        gid = self.tk.gegner("Oger", 2, 2, hg=3)
        r = self.tk.sl(op="ep", gegner=[gid], hg=["1"], an=["brak", "lern"], grund="Oger")
        self.assertEqual((r["gesamt"], r["je"]), (1200, 600))
        self.assertEqual(self.tk.datei_charakter("brak")["ep"], 5600)
        with self.assertRaises(FEHLER):
            self.tk.sl(op="ep", hg=["99"], an=["brak"])

    def test_ep_ohne_empfaenger_an_alle_sc_der_karte(self):
        r = self.tk.sl(op="ep", ep=100, grund="Rätsel")
        self.assertEqual(r["je"], 50)

    def test_aufstieg_moeglich_und_ablauf(self):
        self.tk.sl(op="ep", ep=200, an=["lern"], grund="Übung")
        self.assertTrue(any("Lern kann auf Stufe 2" in e["text"] for e in self.tk.log()))
        self.assertTrue(self.tk.charakter("lern")["_ep"]["aufstiegMoeglich"])
        p = self.tk.spieler("/api/aufstieg-plan", {"charId": "lern"})
        self.assertEqual(p["plan"]["zielStufe"], 2)
        self.assertEqual(p["plan"]["tw"], 10)
        r = self.tk.spieler("/api/aufstieg-tp", {"charId": "lern", "art": "schnitt"})
        self.assertEqual(r["aufstieg"]["tp"]["plus"], 6 + 2)  # 10/2+1 + KO-Mod
        with self.assertRaises(FEHLER):  # noch nicht abgeschickt
            self.tk.st.aufstieg_fertig("lern")
        self.tk.st.aufstieg_fertig("lern", erzwingen=True)
        self.assertEqual(self.tk.datei_charakter("lern")["stufe"], 2)
        self.assertNotIn("aufstieg", self.tk.datei_charakter("lern"))

    def test_kein_aufstieg_ohne_ep(self):
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/aufstieg-plan", {"charId": "lern"})

    def test_char_setzen_mit_punktpfad(self):
        self.tk.st.char("brak", {"rw.REF": 4, "tp.max": 33, "name": "Brak der Starke"})
        c = self.tk.datei_charakter("brak")
        self.assertEqual((c["rw"]["REF"], c["tp"]["max"]), (4, 33))
        t = self.tk.z()["tokens"][self.brak]
        self.assertEqual((t["name"], t["tpMax"]), ("Brak der Starke", 33))

    def test_modus_vorlage_dauer_und_ablauf_im_kampf(self):
        self.tk.st.modus(self.brak, "Stierstärke", runden=2)
        c = self.tk.charakter("brak")
        self.assertEqual(c["attribute"]["ST"], 20)
        self.assertEqual(c["angriffe"][0]["bonus"], 9)
        self.assertEqual(c["angriffe"][0]["schaden"], "1W8+5")
        self.assertEqual(self.tk.datei_charakter("brak")["attribute"]["ST"], 16)
        self.tk.st.ini("start")
        self.tk.st.ini("eintrag", name="Brak", wert=10, token=self.brak)
        self.tk.st.ini("los")
        self.tk.st.ini("weiter")
        self.assertIn("Stierstärke", self.tk.st.modi())
        self.tk.st.ini("weiter")
        self.assertEqual(self.tk.st.modi(), "(keine aktiven Modi)")

    def test_person_vergroessern_aendert_token(self):
        self.tk.st.modus(self.brak, "Person vergrößern", minuten=3)
        t = self.tk.z()["tokens"][self.brak]
        self.assertEqual((t["groesse"], t["reichweite"]), (2, 2))
        c = self.tk.charakter("brak")
        self.assertEqual(c["rk"]["normal"], 18 - 1 - 1)  # Größe −1, GE −2 → −1
        self.assertEqual(c["angriffe"][0]["schaden"], "2W6+4")
        self.tk.st.modus_ende(self.brak, "Person vergrößern")
        t = self.tk.z()["tokens"][self.brak]
        self.assertEqual(t["groesse"], 1)
        self.assertNotIn("reichweite", t)

    def test_unbekannter_modus_ohne_wirkung(self):
        with self.assertRaises(FEHLER):
            self.tk.st.modus(self.brak, "Fantasie")
        with self.assertRaises(FEHLER):
            self.tk.st.modus(self.brak, "Falsch", wirkung={"quatsch": 1})

    def test_modus_zeit(self):
        self.tk.st.modus(self.brak, "Heldenmut", minuten=1)
        self.assertIn("Heldenmut", self.tk.st.modus_zeit(runden=10))

    def test_charakter_speichern_und_loeschen(self):
        c = self.tk.datei_charakter("lern")
        c["notizen"] = "neu"
        c["_ep"] = {"x": 1}
        self.tk.http("/api/charakter", c)
        d = self.tk.datei_charakter("lern")
        self.assertEqual(d["notizen"], "neu")
        self.assertNotIn("_ep", d)
        self.tk.http("/api/charakter-loeschen", {"id": "lern"})
        self.assertNotIn(self.lern, self.tk.z()["tokens"])
        self.assertFalse((self.tk.ordner / "daten" / "charaktere" / "lern.json").exists())


if __name__ == "__main__":
    unittest.main()
