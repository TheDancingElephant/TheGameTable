"""Magie: Zauberplätze, spontanes Zaubern, Domäne, Zauberpools (Barde), Rast, Zauberbuch, Vorbereiten."""
import unittest

from tests.hilfen import FEHLER, HTTPFehler, Testkampagne


def index(c, name):
    return next(i for i, e in enumerate(c["zauberliste"]) if e["name"] == name)


class MagieTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()
        self.tk.karte_leer()
        self.brak = self.tk.sc("brak", 5, 5)
        self.mira = self.tk.sc("mira", 6, 5)
        self.lied = self.tk.sc("lied", 5, 6)

    def tearDown(self):
        self.tk.beenden()

    def zaubern(self, tid, cid, name, ziel=None):
        c = self.tk.charakter(cid)
        b = {"id": tid, "zauber": index(c, name)}
        if ziel:
            b["ziel"] = ziel
        return self.tk.spieler("/api/zaubern", b)

    def verbraucht(self, cid, name):
        return self.tk.datei_charakter(cid)["zauberliste"][index(self.tk.datei_charakter(cid), name)].get("verbraucht", 0)

    def test_zauberplatz_wird_verbraucht_und_ist_irgendwann_leer(self):
        self.zaubern(self.mira, "mira", "Göttliche Gunst")
        self.assertEqual(self.verbraucht("mira", "Göttliche Gunst"), 1)
        self.assertEqual(self.tk.charakter("mira")["zauberliste"][1]["_d"]["frei"], 0)
        with self.assertRaises(HTTPFehler) as f:
            self.zaubern(self.mira, "mira", "Göttliche Gunst")
        self.assertIn("keine Zauberplätze", f.exception.text)

    def test_spontan_heilen_verbraucht_vorbereiteten_platz_nicht_domaene(self):
        self.tk.st.tp(self.brak, -10)
        self.zaubern(self.mira, "mira", "Leichte Wunden heilen", ziel=self.brak)
        self.assertGreater(self.tk.z()["tokens"][self.brak]["tp"], 20)
        self.assertEqual(self.verbraucht("mira", "Segen"), 1)
        self.assertEqual(self.verbraucht("mira", "Schild des Glaubens"), 0)
        e = [e for e in self.tk.log() if e["art"] == "zauber"][-1]
        self.assertIn("spontan anstelle von Segen", e["text"])

    def test_heilung_nicht_ueber_maximum(self):
        self.zaubern(self.mira, "mira", "Leichte Wunden heilen", ziel=self.brak)
        self.assertEqual(self.tk.z()["tokens"][self.brak]["tp"], 30)

    def test_barde_pool(self):
        self.zaubern(self.lied, "lied", "Federfall", ziel=self.brak)
        self.zaubern(self.lied, "lied", "Leichte Wunden heilen", ziel=self.brak)
        self.assertEqual(self.tk.datei_charakter("lied")["zauberpools"]["grad1"]["verbraucht"], 2)
        with self.assertRaises(FEHLER):
            self.zaubern(self.lied, "lied", "Federfall", ziel=self.brak)

    def test_rast_setzt_plaetze_und_pools_zurueck_und_beendet_modi(self):
        self.zaubern(self.mira, "mira", "Göttliche Gunst")
        self.zaubern(self.lied, "lied", "Federfall", ziel=self.brak)
        self.tk.st.modus(self.brak, "Hast", runden=10)
        self.tk.st.modus(self.brak, "Ewig", wirkung={"rk": 1})
        self.tk.st.rast()
        self.assertEqual(self.verbraucht("mira", "Göttliche Gunst"), 0)
        self.assertEqual(self.tk.datei_charakter("lied")["zauberpools"]["grad1"]["verbraucht"], 0)
        modi = [m["name"] for m in self.tk.datei_charakter("brak").get("modi") or []]
        self.assertEqual(modi, ["Ewig"])

    def test_nicht_sichtbares_ziel(self):
        gid = self.tk.gegner("Schatten", 7, 5)
        self.tk.st.zeige(gid, verbergen=True)
        with self.assertRaises(FEHLER):
            self.zaubern(self.mira, "mira", "Leichte Wunden heilen", ziel=gid)

    def test_faehigkeiten(self):
        g1 = self.tk.gegner("Zombie", 8, 5, tp=30, wil=0)
        g2 = self.tk.gegner("Fernes Skelett", 19, 14, tp=30, wil=0)
        self.tk.st.ini("start")
        self.tk.st.ini("eintrag", name="Mira", wert=20, token=self.mira)
        self.tk.st.ini("los")
        seit = self.tk.letzte_id()
        self.tk.spieler("/api/faehigkeit", {"id": self.mira, "index": 0})
        lg = self.tk.log(seit)
        self.assertIn("1 Ziel(e) im Umkreis von 9 m", [e.get("ergebnisText") for e in lg if e["art"] == "zauber"][0])
        self.assertLess(self.tk.z()["tokens"][g1]["tp"], 30)
        self.assertEqual(self.tk.z()["tokens"][g2]["tp"], 30)
        self.assertFalse(self.tk.stand()["zug"]["standardFrei"])
        self.tk.spieler("/api/faehigkeit", {"id": self.mira, "index": 1})  # schnelle Aktion
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/faehigkeit", {"id": self.mira, "index": 2, "ziel": self.brak})  # Standard verbraucht

    def test_faehigkeit_heilung_ausserhalb_des_kampfes(self):
        self.tk.st.tp(self.brak, -5)
        self.tk.spieler("/api/faehigkeit", {"id": self.mira, "index": 2, "ziel": self.brak})
        self.assertGreater(self.tk.z()["tokens"][self.brak]["tp"], 25)
        self.assertEqual(self.tk.stand()["slStatus"], "wartet")

    def test_zauberbuch(self):
        self.tk.st.buch("lied", ["Schlaf", "Federfall"], grad=1)
        self.tk.st.buch("lied", ["Schlaf"], grad=1)
        self.assertEqual([e["name"] for e in self.tk.datei_charakter("lied")["zauberbuch"]], ["Schlaf", "Federfall"])
        self.tk.st.buch("lied", ["schlaf"], weg=True)
        self.assertEqual(len(self.tk.datei_charakter("lied")["zauberbuch"]), 1)

    def test_vorbereiten_plan_und_speichern(self):
        p = self.tk.spieler("/api/zauber-vorbereiten", {"op": "plan", "charId": "mira"})
        self.assertEqual(p["klasse"], "Kleriker")
        self.assertTrue(p["plaetze"])
        namen = ["Segen", "Segen", "Göttliche Gunst", "Schild des Glaubens"]
        self.tk.spieler("/api/zauber-vorbereiten", {"op": "speichern", "charId": "mira", "stand": p["stand"],
                                                    "namen": namen[:len(p["plaetze"])]})
        with self.assertRaises(FEHLER):  # alter Stand wird abgelehnt
            self.tk.spieler("/api/zauber-vorbereiten", {"op": "speichern", "charId": "mira", "stand": "alt", "namen": []})


if __name__ == "__main__":
    unittest.main()
