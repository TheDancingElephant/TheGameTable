"""Kampagne: Ordner finden/laden, neue Kampagne aus der Vorlage, Kampagnenliste, Pfade prüfen/reparieren."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.hilfen import TOOL  # noqa: F401  (setzt den Programmordner in sys.path)

import sl_api
from bereiche import kampagne


class KampagneTest(unittest.TestCase):
    def setUp(self):
        self.wurzel = Path(tempfile.mkdtemp(prefix="spieltisch-kampagnen-"))

    def tearDown(self):
        shutil.rmtree(self.wurzel, ignore_errors=True)

    def test_neue_kampagne_liste_und_pfade(self):
        text = sl_api.kampagne_neu(self.wurzel, "Die Grüne Mühle", port=8899, quellen=False)
        self.assertIn("Grüne Mühle", text)
        ordner = next(p for p in self.wurzel.iterdir() if p.is_dir())
        k = kampagne.laden(str(ordner))
        self.assertEqual((k["name"], k["port"], k["epTempo"]), ("Die Grüne Mühle", 8899, "mittel"))
        self.assertTrue((ordner / "sl" / "notizen" / "kapitel1.md").is_file())
        self.assertTrue((ordner / "sl" / "hausregeln.md").is_file())
        mcp = json.loads((ordner / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("spieltisch", mcp["mcpServers"])
        self.assertIs(kampagne.pfade_ok(ordner), True)
        liste = kampagne.kampagnen_liste(self.wurzel)
        self.assertIn("Die Grüne Mühle", liste)
        self.assertIn("Port 8899", liste)
        # Umzug simulieren: Pfade in .mcp.json verbiegen, dann reparieren
        mcp["mcpServers"]["spieltisch"]["command"] = "X:/gibtsnicht/python.exe"
        (ordner / ".mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
        self.assertIs(kampagne.pfade_ok(ordner), False)
        kampagne.pfade_reparieren(ordner)
        self.assertIs(kampagne.pfade_ok(ordner), True)
        with self.assertRaises(sl_api.SLFehler):
            sl_api.kampagne_neu(self.wurzel, "Die Grüne Mühle", ordner=ordner.name)

    def test_ordner_finden_ohne_kampagne(self):
        with self.assertRaises(SystemExit):
            kampagne.ordner_finden(str(self.wurzel))
        self.assertEqual(kampagne.TOOL, TOOL)


if __name__ == "__main__":
    unittest.main()
