"""Beispielkampagnen (beispiele/): Inhalt vollständig und ohne Spielstand-Reste, Anlegen per kampagne_neu(beispiel=…),
Startszene spielbar, Sichtnebel an den importierten Wänden, Spoilerschutz der Spieleransicht."""
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.hilfen import TOOL, freier_port, server_starten, server_stoppen

import sl_api
from bereiche import kampagne
from bereiche.karte import kartenformat as KF

PRAXISJAHR = TOOL / "beispiele" / "Das Praxisjahr"
VERBOTEN = ("schluessel.txt", "protokoll.jsonl", "server.log", "server-test.log", ".mcp.json")


class BeispielInhaltTest(unittest.TestCase):
    """Statische Prüfung jedes Beispielordners (ohne Server)."""

    def test_liste(self):
        namen = [b["ordner"] for b in kampagne.beispiele_liste()]
        self.assertIn("Das Praxisjahr", namen)
        b = next(b for b in kampagne.beispiele_liste() if b["ordner"] == "Das Praxisjahr")
        self.assertTrue(b["beschreibung"])
        self.assertEqual(kampagne.beispiel_ordner("das praxisjahr"), PRAXISJAHR)
        with self.assertRaises(sl_api.SLFehler):
            kampagne.beispiel_ordner("gibt es nicht")

    def test_ordner_vollstaendig_und_sauber(self):
        for b in kampagne.beispiele_liste():
            o = kampagne.BEISPIELE / b["ordner"]
            with self.subTest(beispiel=b["ordner"]):
                for name in VERBOTEN:
                    self.assertEqual(list(o.rglob(name)), [], f"{name} gehört nicht ins Beispiel")
                self.assertTrue((o / "sl" / "notizen").is_dir())
                notizen = "".join(p.read_text(encoding="utf-8") for p in (o / "sl" / "notizen").glob("*.md"))
                self.assertIn("## Laufende Notizen", notizen)
                z = json.loads((o / "sl" / "zustand.json").read_text(encoding="utf-8"))
                self.assertEqual((z["letzteVerarbeitet"], z["naechsteLogId"]), (0, 1))
                self.assertIn(z["karteAktiv"], z["karten"])
                for kid, k in z["karten"].items():
                    self.assertTrue((o / "sl" / "karten" / k["datei"]).is_file(), f"Kartenbild {k['datei']} fehlt")
                    if k.get("nebelModus") == "sicht":
                        self.assertTrue((o / "sl" / "barrieren" / f"{kid}.json").is_file(), f"Barrieren {kid} fehlen")
                chars = {p.stem for p in (o / "daten" / "charaktere").glob("*.json")}
                for p in (o / "daten" / "charaktere").glob("*.json"):
                    c = json.loads(p.read_text(encoding="utf-8"))
                    self.assertEqual(c["id"], p.stem)
                for t in z["tokens"].values():
                    self.assertIn(t["karte"], z["karten"])
                    if t["art"] == "sc":
                        self.assertIn(t["charId"], chars)
                for h in z.get("handouts", []):
                    self.assertTrue(h["text"].strip())
                for p in (o / "Material" / "karten").glob("*.karte.json"):
                    daten = KF.laden_text(p.read_text(encoding="utf-8"))
                    KF.pruefen(daten)
                    self.assertTrue(KF.waende_berechnen(daten))
                    self.assertTrue((o / daten["bild"]).is_file())

    def test_praxisjahr_startzustand(self):
        z = json.loads((PRAXISJAHR / "sl" / "zustand.json").read_text(encoding="utf-8"))
        self.assertEqual(z["karteAktiv"], "torstadt")
        self.assertEqual({"zisternen", "wachhaus"} & set(z["karten"]), {"zisternen", "wachhaus"})
        self.assertFalse(z["karten"]["zisternen"].get("bekannt"), "Zisternen dürfen nicht in den Spielerunterlagen sein")
        gegner = [t for t in z["tokens"].values() if t["art"] != "sc"]
        self.assertTrue(gegner)
        self.assertTrue(all(not t["sichtbar"] and t["karte"] == "zisternen" for t in gegner))
        self.assertEqual(sorted(t["charId"] for t in z["tokens"].values() if t["art"] == "sc"),
                         ["grimbar", "ilvaen", "nissa", "zikko"])


class BeispielAnlegenTest(unittest.TestCase):
    """kampagne_neu mit beispiel= und ein echter Server auf der neuen Kampagne."""

    @classmethod
    def setUpClass(cls):
        cls.wurzel = Path(tempfile.mkdtemp(prefix="spieltisch-beispiel-"))
        cls.text = sl_api.kampagne_neu(cls.wurzel, "", beispiel="Das Praxisjahr", port=freier_port())
        cls.ordner = cls.wurzel / "Das Praxisjahr"
        cls.port = freier_port()
        cls.proc = server_starten(cls.ordner, cls.port)
        os.environ.pop("SPIELTISCH_PORT", None)
        cls.st = sl_api.Spieltisch(str(cls.ordner), basis=str(cls.ordner))
        cls.st.port, cls.st.url = cls.port, f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        server_stoppen(cls.proc)
        shutil.rmtree(cls.wurzel, ignore_errors=True)

    def get(self, pfad, sl=False, roh=False):
        req = urllib.request.Request(self.st.url + pfad, headers={"X-SL": self.st.key} if sl else {})
        with urllib.request.urlopen(req, timeout=30) as r:
            inhalt = r.read()
        return inhalt if roh else json.loads(inhalt)

    def test_1_ordner_und_leitfaden(self):
        self.assertIn("Beispielkampagne", self.text)
        k = kampagne.laden(str(self.ordner))
        self.assertEqual(k["name"], "Das Praxisjahr")
        self.assertNotEqual(k["port"], 8790)  # freier Port, nicht der aus dem Beispiel
        for md in ("CLAUDE.md", "AGENTS.md"):
            text = (self.ordner / md).read_text(encoding="utf-8")
            self.assertIn("Beispielkampagne „Das Praxisjahr“", text, md)
            self.assertNotIn("{{", text, md)
        self.assertFalse((self.ordner / "kampagnenregeln.md").exists())
        self.assertTrue((self.ordner / "sl" / "notizen" / "kapitel1.md").read_text(encoding="utf-8").startswith(
            "# Das Praxisjahr"))
        self.assertTrue((self.ordner / ".mcp.json").is_file())
        with self.assertRaises(sl_api.SLFehler):
            sl_api.kampagne_neu(self.wurzel, "", beispiel="Das Praxisjahr")  # Ordner existiert schon

    def test_2_spieleransicht_ohne_spoiler(self):
        s = self.get("/api/stand")
        self.assertEqual(s["szene"]["titel"], "Die Kaserne")
        self.assertEqual(s["karte"]["id"], "torstadt")
        self.assertEqual({t["art"] for t in s["tokens"]}, {"sc"})
        roh = json.dumps(s, ensure_ascii=False)
        # („Schreckensratten“ steht im öffentlichen Spielerhandout, daher nicht in dieser Liste)
        for geheim in ("Rattenmutter", "Rattenschwarm", "Tamla", "Vanthe", "Gegenanker", "Runenstein", "Kalte Kraft"):
            self.assertNotIn(geheim, roh)
        bekannt = {k["id"] for k in s["unterlagen"]["karten"]}
        self.assertNotIn("zisternen", bekannt)
        self.assertNotIn("wachhaus", bekannt)
        self.assertIn("hoehlen", bekannt)
        with self.assertRaises(urllib.error.HTTPError):  # SL-Zustand nur mit Schlüssel
            self.get("/api/sl/zustand")

    def test_3_zisternen_sichtnebel(self):
        self.st.karte("zisternen")
        for cid, x, y in (("grimbar", 11, 1), ("nissa", 12, 1), ("ilvaen", 13, 1), ("zikko", 12, 2)):
            self.st.sc_platzieren(cid, x, y)
        self.st.sicht()
        s = self.get("/api/stand")
        auf = {tuple(f) for f in s["karte"]["aufgedeckt"]}
        self.assertIn((12, 2), auf)       # Einstieg
        self.assertIn((12, 8), auf)       # Pumpenkammer durch den Treppenfuß
        self.assertNotIn((24, 8), auf)    # Geräteraum hinter Wand und geschlossener Tür
        self.assertNotIn((10, 25), auf)   # Hauptzisterne
        self.assertNotIn((3, 12), auf)    # Überlaufbecken
        self.assertEqual({t["art"] for t in s["tokens"]}, {"sc"})  # Ratten bleiben verborgen
        bild = self.get("/api/karte/zisternen.jpg", roh=True)
        self.assertTrue(bild.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
