"""Wissen: Regelsuche (PRD + Hausregeln), Zaubersuche, Zauberkatalog über die API, MCP-Toolliste."""
import json
import subprocess
import sys
import unittest

from tests.hilfen import TOOL, Testkampagne


class WissenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tk = Testkampagne().starten()
        (cls.tk.ordner / "sl" / "hausregeln.md").write_text(
            "# Hausregeln\n\n## Heldenpunkte\nJeder SC hat 2 Heldenpunkte je Stufe.\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tk.beenden()

    def test_regel_suchen(self):
        t = self.tk.st.regel_suchen("Gelegenheitsangriff Bewegung verlassen")
        self.assertIn("Gelegenheitsangriff", t)
        self.assertIn("Beweglichkeit", self.tk.st.regel_schnell("talent", "Beweglichkeit"))

    def test_monster_info(self):
        t = self.tk.st.monster_info("Lehmgolem")
        self.assertIn("HG 10", t)
        self.assertIn("SR** 10/Adamant", t)
        liste = self.tk.st.monster_info(hg="10", art="Konstrukt")
        self.assertIn("Lehmgolem", liste)
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
