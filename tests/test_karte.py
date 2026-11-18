"""Karte: Token, Bewegung, Nebel (Raster und Sichtpolygon mit Wänden/Türen), Spielersicht, Täuschung."""
import json
import unittest

from tests.hilfen import FEHLER, TOOL, Testkampagne


class KarteRasterTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()
        self.tk.karte_leer(aufdecken=False)

    def tearDown(self):
        self.tk.beenden()

    def offen(self):
        return {tuple(c) for c in self.tk.z()["karten"]["test"]["aufgedeckt"]}

    def test_aufdecken_und_verdecken(self):
        self.tk.st.nebel(True, "rechteck", [0, 0, 2, 1])
        self.assertEqual(self.offen(), {(x, y) for x in range(3) for y in range(2)})
        self.tk.st.nebel(False, "rechteck", [0, 0, 0, 1])
        self.assertEqual(len(self.offen()), 4)
        self.tk.st.nebel(True, "kreis", [10, 10, 2])
        self.assertIn((11, 11), self.offen())      # Diagonale: 1 Feld
        self.assertIn((12, 11), self.offen())      # 2 + 1//2 = 2
        self.assertNotIn((12, 12), self.offen())   # 2 Diagonalen = 3 Felder (1-2-1-Regel)
        self.tk.st.nebel(True, "alles")
        self.assertEqual(len(self.offen()), 20 * 15)

    def test_spieler_sieht_gegner_nur_auf_aufgedecktem_feld(self):
        gid = self.tk.gegner("Ork", 15, 12, tp=10, rk=13)
        self.assertNotIn(gid, [t["id"] for t in self.tk.stand()["tokens"]])
        self.assertIn(gid, [t["id"] for t in self.tk.stand(sl=True)["tokens"]])
        self.tk.st.nebel(True, "rechteck", [14, 11, 16, 13])
        t = next(t for t in self.tk.stand()["tokens"] if t["id"] == gid)
        self.assertNotIn("tp", t)  # Spieler sehen nur den Gesundheitstext
        self.assertEqual(t["gesundheit"], "unverletzt")
        self.tk.st.zeige(gid, verbergen=True)
        self.assertNotIn(gid, [t["id"] for t in self.tk.stand()["tokens"]])

    def test_sc_platzieren_und_bewegen(self):
        tid = self.tk.sc("brak", 2, 2)
        self.tk.spieler("/api/bewegen", {"id": tid, "x": 5, "y": 3})
        t = self.tk.z()["tokens"][tid]
        self.assertEqual((t["x"], t["y"]), (5, 3))
        e = [e for e in self.tk.log() if e["art"] == "bewegung"][-1]
        self.assertIn("3 Felder (4.5 m)", e["text"])
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/bewegen", {"id": self.tk.gegner("Ork", 1, 1), "x": 2, "y": 2})

    def test_sl_zieht_token_und_entfernt(self):
        gid = self.tk.gegner("Ork", 1, 1)
        self.tk.st.zieh(gid, 4, 4)
        self.assertEqual(self.tk.z()["tokens"][gid]["x"], 4)
        self.tk.st.weg([gid])
        self.assertNotIn(gid, self.tk.z()["tokens"])

    def test_kartenbild_maskiert_fuer_spieler(self):
        self.assertEqual(self.tk.http("/api/karte/test.jpg", roh=True)[:2], b"\xff\xd8")
        with self.assertRaises(FEHLER):
            self.tk.http("/api/karte/gibtsnicht.jpg", roh=True)

    def test_taeuschung_nur_im_zug_des_getaeuschten(self):
        self.tk.st.nebel(True, "alles")
        tid = self.tk.sc("brak", 2, 2)
        gid = self.tk.gegner("Spiegelbild", 6, 6)
        self.tk.st.taeuschung(token=gid, fuer=["brak"], name="Bauer")
        self.assertEqual(next(t for t in self.tk.stand()["tokens"] if t["id"] == gid)["name"], "Spiegelbild")
        self.tk.st.ini("start")
        self.tk.st.ini("eintrag", name="Brak", wert=20, token=tid)
        self.tk.st.ini("eintrag", name="Spiegelbild", wert=5, token=gid)
        self.tk.st.ini("los")
        self.assertEqual(next(t for t in self.tk.stand()["tokens"] if t["id"] == gid)["name"], "Bauer")


class KarteSichtTest(unittest.TestCase):
    """Importierte Karte mit exakten Wänden: Sichtpolygon-Nebel stoppt an Wänden und geschlossenen Türen."""

    def setUp(self):
        self.tk = Testkampagne().starten()
        daten = json.loads((TOOL / "mcp" / "kartenformat-beispiel.json").read_text(encoding="utf-8"))
        self.tk.st.karte_import(daten=daten, aktiv=True, sc=[{"char_id": "brak", "x": 4, "y": 5}])

    def tearDown(self):
        self.tk.beenden()

    def offen(self):
        return {tuple(c) for c in self.tk.z()["karten"]["imp-keller"]["aufgedeckt"]}

    def test_sicht_im_raum_und_nicht_hinter_der_tuer(self):
        k = self.tk.z()["karten"]["imp-keller"]
        self.assertEqual(k["nebelModus"], "sicht")
        offen = self.offen()
        self.assertIn((4, 5), offen)
        self.assertIn((7, 7), offen)
        self.assertNotIn((12, 5), offen)   # Gang hinter der geschlossenen Tür t1
        self.assertNotIn((18, 3), offen)   # anderer Raum

    def test_tuer_oeffnen_deckt_auf(self):
        vorher = len(self.offen())
        self.tk.st.tuer(ids=["t1"], auf=True)
        liste = self.tk.st.barrieren("liste")
        self.assertIn("t1", liste)
        self.tk.st.sicht()
        self.assertGreater(len(self.offen()), vorher)
        self.assertIn((10, 5), self.offen())

    def test_barriere_neu_und_weg(self):
        self.tk.st.barrieren("neu", typ="wand", von=[3, 3], bis=[3, 4], id="w9")
        self.assertIn("w9", self.tk.st.barrieren("liste"))
        self.tk.st.barrieren("weg", ids=["w9"])
        self.assertNotIn("w9", self.tk.st.barrieren("liste"))


if __name__ == "__main__":
    unittest.main()
