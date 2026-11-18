"""Besitz: Gruppenkasse, Gegenstände, Beute; Übernahme aus den Charakterbögen."""
import unittest

from tests.hilfen import FEHLER, HTTPFehler, Testkampagne


class BesitzTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()

    def tearDown(self):
        self.tk.beenden()

    def a(self):
        return self.tk.stand()["ausruestung"]

    def test_uebernahme_aus_charakterboegen(self):
        namen = [(g["name"], g["traeger"]) for g in self.a()["gegenstaende"]]
        self.assertIn(("Langschwert", "brak"), namen)

    def test_kasse(self):
        self.tk.st.kasse(gp=100, sp=5, grund="Belohnung")
        self.assertEqual(self.a()["kasse"], {"kp": 0, "sp": 5, "gp": 100, "pp": 0})
        with self.assertRaises(FEHLER):
            self.tk.st.kasse(gp=-200)
        self.tk.spieler("/api/ausruestung", {"op": "kasse", "delta": {"gp": -30}, "grund": "Seil"})
        self.assertEqual(self.a()["kasse"]["gp"], 70)
        self.tk.st.kasse(gp=7, setze=True)
        self.assertEqual(self.a()["kasse"]["gp"], 7)

    def test_beute_und_gegenstand(self):
        r = self.tk.st.beute("Heiltrank", an="mira", ort="Gürtel", anzahl=2)
        iid = int(r.split()[1])
        g = next(g for g in self.a()["gegenstaende"] if g["id"] == iid)
        self.assertEqual((g["traeger"], g["ort"], g["anzahl"]), ("mira", "Gürtel", 2))
        self.tk.st.item(iid, an="gruppe", anzahl=1)
        g = next(g for g in self.a()["gegenstaende"] if g["id"] == iid)
        self.assertEqual((g["traeger"], g["anzahl"]), ("gruppe", 1))
        self.tk.st.item(iid, weg=True)
        self.assertNotIn(iid, [g["id"] for g in self.a()["gegenstaende"]])
        with self.assertRaises(FEHLER):
            self.tk.st.item(iid, weg=True)
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/ausruestung", {"op": "item-neu", "name": " "})


if __name__ == "__main__":
    unittest.main()
