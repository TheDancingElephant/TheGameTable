"""Kampf: Initiative (inkl. Entfernen, Tote überspringen), Zug/Bewegungsbudget, Angriff gegen RK mit Modi."""
import unittest

from tests.hilfen import FEHLER, HTTPFehler, Testkampagne, letzter_angriff, w20


class InitiativeTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()
        self.tk.karte_leer()
        self.brak = self.tk.sc("brak", 2, 2)
        self.mira = self.tk.sc("mira", 3, 2)
        self.ork = self.tk.gegner("Ork", 10, 10, tp=10, rk=13)
        self.wolf = self.tk.gegner("Wolf", 12, 10, tp=8, rk=14)
        st = self.tk.st
        st.ini("start")
        for name, wert, tok in (("Brak", 20, self.brak), ("Ork", 15, self.ork), ("Mira", 10, self.mira),
                                ("Wolf", 5, self.wolf)):
            st.ini("eintrag", name=name, wert=wert, token=tok)

    def tearDown(self):
        self.tk.beenden()

    def ini(self):
        return self.tk.z()["initiative"]

    def am_zug(self):
        i = self.ini()
        return i["eintraege"][i["index"]]["name"]

    def test_reihenfolge_und_weiter(self):
        self.tk.st.ini("los")
        self.assertEqual([e["name"] for e in self.ini()["eintraege"]], ["Brak", "Ork", "Mira", "Wolf"])
        self.assertEqual((self.am_zug(), self.ini()["runde"]), ("Brak", 1))
        self.tk.spieler("/api/zug-beenden", {"id": self.brak})
        self.assertEqual(self.am_zug(), "Ork")
        for _ in range(3):
            self.tk.st.ini("weiter")
        self.assertEqual((self.am_zug(), self.ini()["runde"]), ("Brak", 2))

    def test_spieler_wuerfeln_initiative_nur_einmal(self):
        self.tk.st.ini("start")
        self.tk.spieler("/api/wurf", {"ausdruck": "1W20+2", "grund": "Initiative", "wer": "Brak", "initiative": True,
                                      "charId": "brak"})
        self.assertEqual(self.ini()["eintraege"][0]["tokenId"], self.brak)
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/wurf", {"ausdruck": "1W20+2", "wer": "Brak", "initiative": True, "charId": "brak"})

    def test_entfernen_vor_dem_aktuellen_behaelt_den_zug(self):
        self.tk.st.ini("los")
        self.tk.st.ini("weiter")
        self.tk.st.ini("weiter")
        self.assertEqual(self.am_zug(), "Mira")
        self.tk.st.ini("entfernen", name="Ork")
        self.assertEqual(self.am_zug(), "Mira")
        self.tk.st.weg([self.brak])  # Token entfernen nimmt ihn auch aus der Initiative
        self.assertEqual([e["name"] for e in self.ini()["eintraege"]], ["Mira", "Wolf"])
        self.assertEqual(self.am_zug(), "Mira")

    def test_entfernen_des_aktuellen_gibt_den_zug_weiter(self):
        self.tk.st.ini("los")
        self.tk.st.ini("weiter")
        self.tk.st.ini("entfernen", name="Ork")
        self.assertEqual(self.am_zug(), "Mira")

    def test_tote_gegner_werden_uebersprungen(self):
        self.tk.st.ini("los")
        self.tk.st.tp(self.ork, -12)
        self.assertIn("Tot", self.tk.z()["tokens"][self.ork]["zustaende"])
        self.tk.st.ini("weiter")
        self.assertEqual(self.am_zug(), "Mira")
        self.tk.st.tp(self.ork, 5)  # wiederbelebt: automatisches „Tot“ verschwindet
        self.assertNotIn("Tot", self.tk.z()["tokens"][self.ork]["zustaende"])

    def test_ende(self):
        self.tk.st.ini("los")
        self.tk.st.ini("ende")
        i = self.ini()
        self.assertFalse(i["aktiv"])
        self.assertEqual(i["eintraege"], [])

    def test_bewegungsbudget_und_nur_wer_dran_ist(self):
        self.tk.st.ini("los")
        with self.assertRaises(FEHLER):
            self.tk.spieler("/api/bewegen", {"id": self.mira, "x": 3, "y": 3})
        self.tk.spieler("/api/bewegen", {"id": self.brak, "x": 8, "y": 2})   # 6 Felder = Bewegungsaktion
        zug = self.tk.stand()["zug"]
        self.assertEqual((zug["bewegt"], zug["restFelder"], zug["standardFrei"]), (6, 6, True))  # Standard-Aktion bleibt
        with self.assertRaises(HTTPFehler) as f:
            self.tk.spieler("/api/bewegen", {"id": self.brak, "x": 15, "y": 2})
        self.assertIn("Zu weit", f.exception.text)

    def test_gelegenheitsangriff_warnung(self):
        self.tk.st.ini("los")
        self.tk.st.zieh(self.ork, 3, 3)
        warnung = self.tk.st.zieh(self.ork, 6, 6)
        self.assertIn("Gelegenheitsangriff", warnung)
        self.assertIn("Brak", warnung)


class AngriffTest(unittest.TestCase):
    def setUp(self):
        self.tk = Testkampagne().starten()
        self.tk.karte_leer()
        self.brak = self.tk.sc("brak", 5, 5)
        self.ork = self.tk.gegner("Ork", 6, 5, tp=200, rk=15, rkBeruehrung=10, rkAdff=13, ref=1, wil=0, zaeh=3)

    def tearDown(self):
        self.tk.beenden()

    def gegner_greift_an(self, **extra):
        seit = self.tk.letzte_id()
        self.tk.st.angriff(self.ork, self.brak, 4, "1W6", waffe="Axt", **extra)
        return letzter_angriff(self.tk, seit)

    def test_gegner_gegen_sc_rk(self):
        _, rk = self.gegner_greift_an()
        self.assertEqual(rk, 18)
        _, rk = self.gegner_greift_an(beruehrung=True)
        self.assertEqual(rk, 12)
        self.tk.st.zustand_setzen(self.brak, ["Auf dem falschen Fuß"])
        _, rk = self.gegner_greift_an()
        self.assertEqual(rk, 16)

    def test_hast_und_rindenhaut_auf_sc(self):
        self.tk.st.modus(self.brak, "Hast", runden=5)
        _, rk = self.gegner_greift_an()
        self.assertEqual(rk, 19)                      # Ausweichbonus +1
        self.tk.st.modus(self.brak, "Rindenhaut", minuten=30, wirkung={"rkr": 2})
        _, rk = self.gegner_greift_an()
        self.assertEqual(rk, 21)                      # +1 Hast, +2 natürliche Rüstung
        _, rk = self.gegner_greift_an(beruehrung=True)
        self.assertEqual(rk, 13)                      # natürliche Rüstung zählt nicht gegen Berührung
        self.tk.st.zustand_setzen(self.brak, ["Auf dem falschen Fuß"])
        _, rk = self.gegner_greift_an()
        self.assertEqual(rk, 18)                      # ohne Ausweichen, mit natürlicher Rüstung
        self.assertEqual(self.tk.datei_charakter("brak")["rk"]["normal"], 18)  # Basiswert bleibt in der Datei

    def test_beweglichkeit_gegen_gelegenheitsangriff(self):
        _, rk = self.gegner_greift_an(gelegenheitsangriff="bewegung")
        self.assertEqual(rk, 22)                      # Brak hat Beweglichkeit: +4 nur gegen GA durch Bewegung
        a, _ = letzter_angriff(self.tk)
        self.assertIn("Gelegenheitsangriff", a["text"])
        _, rk = self.gegner_greift_an(gelegenheitsangriff="andere")
        self.assertEqual(rk, 18)
        _, rk = self.gegner_greift_an(gelegenheitsangriff="bewegung", beruehrung=True)
        self.assertEqual(rk, 16)                      # Ausweichbonus zählt auch gegen Berührung
        self.tk.st.zustand_setzen(self.brak, ["Auf dem falschen Fuß"])
        _, rk = self.gegner_greift_an(gelegenheitsangriff="bewegung")
        self.assertEqual(rk, 16)                      # auf dem falschen Fuß: kein Ausweichbonus

    def test_modus_rkga_auf_gegner(self):
        self.tk.st.modus(self.ork, "Schutz vor GA", wirkung={"rkga": 2})
        seit = self.tk.letzte_id()
        self.tk.st.angriff(self.brak, self.ork, 7, "1W8", gelegenheitsangriff="andere")
        _, rk = letzter_angriff(self.tk, seit)
        self.assertEqual(rk, 17)
        seit = self.tk.letzte_id()
        self.tk.st.angriff(self.brak, self.ork, 7, "1W8")
        _, rk = letzter_angriff(self.tk, seit)
        self.assertEqual(rk, 15)

    def test_modus_auf_gegner_token(self):
        self.tk.st.modus(self.ork, "Hast", runden=3)
        self.assertEqual(self.tk.z()["tokens"][self.ork]["rk"], 16)
        a, _ = self.gegner_greift_an()
        self.assertIn("Hast", a["detail"])
        self.assertEqual(a["ergebnis"], w20(a) + 4 + 1)
        self.tk.st.modus_ende(self.ork, "Hast")
        self.assertEqual(self.tk.z()["tokens"][self.ork]["rk"], 15)

    def test_sc_angriff_bonus_und_kampfbeginn(self):
        seit = self.tk.letzte_id()
        self.tk.spieler("/api/angriff", {"id": self.brak, "ziel": self.ork, "angriff": 0})
        a, rk = letzter_angriff(self.tk, seit)
        self.assertEqual(rk, 15)
        self.assertEqual(a["ergebnis"], w20(a) + 7)
        self.assertTrue(self.tk.z()["angriffAusserhalb"])
        with self.assertRaises(FEHLER):  # bis der SL den Kampf startet, keine weiteren Angriffe
            self.tk.spieler("/api/angriff", {"id": self.brak, "ziel": self.ork, "angriff": 0})

    def test_sc_angriff_mit_hast_und_flankieren(self):
        self.tk.st.modus(self.brak, "Hast", runden=5)
        self.tk.sc("mira", 7, 5)
        seit = self.tk.letzte_id()
        self.tk.spieler("/api/angriff", {"id": self.brak, "ziel": self.ork, "angriff": 0})
        a, _ = letzter_angriff(self.tk, seit)
        self.assertIn("Flankieren", a["detail"])
        self.assertEqual(a["ergebnis"], w20(a) + 8 + 2)

    def test_fernkampf_in_den_nahkampf(self):
        self.tk.sc("mira", 7, 5)
        self.tk.st.zieh(self.brak, 2, 5)
        seit = self.tk.letzte_id()
        self.tk.spieler("/api/angriff", {"id": self.brak, "ziel": self.ork, "angriff": 1})
        a, _ = letzter_angriff(self.tk, seit)
        self.assertEqual(a["ergebnis"], w20(a) + 5 - 4)

    def test_sturmangriff(self):
        self.tk.st.zieh(self.brak, 1, 5)
        self.tk.st.ini("start")
        self.tk.st.ini("eintrag", name="Brak", wert=20, token=self.brak)
        self.tk.st.ini("eintrag", name="Ork", wert=5, token=self.ork)
        self.tk.st.ini("los")
        seit = self.tk.letzte_id()
        self.tk.spieler("/api/sturmangriff", {"id": self.brak, "ziel": self.ork, "angriff": 0})
        t = self.tk.z()["tokens"][self.brak]
        self.assertEqual(max(abs(t["x"] - 6), abs(t["y"] - 5)), 1)  # neben dem Ork gelandet
        a, _ = letzter_angriff(self.tk, seit)
        self.assertIn("+2 Sturmangriff", a["detail"])
        zug = self.tk.stand()["zug"]
        self.assertFalse(zug["standardFrei"] or zug["bewegungFrei"])
        with self.assertRaises(FEHLER):  # Vollangriff nur mit Anspringen
            self.tk.st.zug({"standard": False, "bewegung": False, "bewegt": 0})
            self.tk.st.zieh(self.brak, 1, 5)
            self.tk.spieler("/api/sturmangriff", {"id": self.brak, "ziel": self.ork, "angriff": 2})

    def test_nahkampf_ausser_reichweite(self):
        self.tk.st.zieh(self.brak, 1, 1)
        with self.assertRaises(HTTPFehler) as f:
            self.tk.spieler("/api/angriff", {"id": self.brak, "ziel": self.ork, "angriff": 0})
        self.assertIn("neben", f.exception.text)

    def test_schaden_trifft_sc_und_landet_in_der_datei(self):
        for _ in range(30):
            a, _ = self.gegner_greift_an()
            if a["treffer"]:
                break
        else:
            self.skipTest("30 Mal daneben")
        tp = self.tk.z()["tokens"][self.brak]["tp"]
        self.assertEqual(tp, 30 - a["schaden"])
        self.assertEqual(self.tk.datei_charakter("brak")["tp"]["aktuell"], tp)


if __name__ == "__main__":
    unittest.main()
