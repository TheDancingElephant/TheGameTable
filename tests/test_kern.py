"""Kern-Tests ohne Server: Fachfunktionen mit Kontext im Speicher und festem Würfel."""
import json
import unittest

from tests.hilfen import FIXTURES  # noqa: F401  (setzt den Programmordner in sys.path)

import speicher
from bereiche import REAKTIONEN, charakter as CH, kern


def leerer_stand():
    return {"version": 1, "szene": {"titel": "", "untertitel": ""}, "karteAktiv": None, "karten": {}, "tokens": {},
            "initiative": {"aktiv": False, "runde": 0, "index": 0, "eintraege": []}, "slStatus": "bereit",
            "letzteVerarbeitet": 0, "naechsteLogId": 1}


def kontext(*cids, wuerfel=(), z=None):
    chars = {c: json.loads((FIXTURES / "charaktere" / f"{c}.json").read_text(encoding="utf-8")) for c in cids}
    return kern.Kontext(z or leerer_stand(), [], speicher.Charakterspeicher(None, chars), {"modi": True}, None,
                        kern.FesterWuerfel(wuerfel), lambda: "12:00", REAKTIONEN)


class KernTest(unittest.TestCase):
    def test_wuerfeln_mit_festem_wuerfel(self):
        self.assertEqual(kern.wuerfeln("2W6+1W4-1", kern.FesterWuerfel([6, 5, 2])), (12, "2W6[6,5] +1W4[2] -1", None))
        self.assertEqual(kern.wuerfeln("1W20", kern.FesterWuerfel([20]))[2], "nat20")
        with self.assertRaises(ValueError):
            kern.wuerfeln("W")

    def test_protokoll_vergibt_ids_aus_dem_spielstand(self):
        kx = kontext()
        e = kx.protokoll("system", "Hallo", wecken=True)
        self.assertEqual((e["id"], e["zeit"], kx.z["naechsteLogId"]), (1, "12:00", 2))
        self.assertEqual(kx.neue, [e])

    def test_hast_wirkt_ohne_die_datei_zu_aendern(self):
        kx = kontext("brak")
        CH.modus_befehl(kx, "modus", {"ziel": "brak", "name": "Hast", "runden": 3})
        w = CH.wirksam(kx, CH.laden(kx, "brak"))
        self.assertEqual((w["rk"]["normal"], w["rk"]["adff"], w["angriffe"][0]["bonus"], w["bewegung"]), (19, 16, 8, 18))
        self.assertEqual(w["angriffe"][2]["serie"], [8, 8])  # zusätzlicher Angriff beim Vollangriff
        roh = CH.laden(kx, "brak")
        self.assertEqual(roh["rk"]["normal"], 18)
        self.assertEqual(roh["modi"][0]["rest"], 3)
        self.assertEqual(CH.modi_zeit(kx, 3), ["Brak: Hast"])
        self.assertEqual(CH.laden(kx, "brak")["modi"], [])

    def test_ep_und_aufstiegsmeldung(self):
        kx = kontext("lern", "brak")
        r = CH.ep_befehl(kx, {"ep": 400, "an": ["lern", "brak"], "grund": "Test"})
        self.assertEqual(r["je"], 200)
        self.assertEqual(CH.laden(kx, "lern")["ep"], 2100)
        self.assertIn("Lern kann auf Stufe 2", kx.neue[0]["text"])

    def test_aufstieg_tp_wurf_genau(self):
        kx = kontext("lern", wuerfel=[7])
        CH.char_setzen(kx, "lern", {"ep": 2000})
        r = CH.aufstieg_spieler(kx, "tp", {"charId": "lern", "art": "wurf"})
        self.assertEqual(r["aufstieg"]["tp"], {"plus": 9, "text": "1W10[7] +2 KO"})


if __name__ == "__main__":
    unittest.main()
