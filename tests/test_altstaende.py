"""Alte Spielstände echter Kampagnen müssen laden (nur lokal, nie eingecheckt).

Umgebungsvariable SPIELTISCH_ALTSTAENDE = Kampagnenordner, mehrere mit ';' getrennt. Die Ordner werden in einen
Temp-Ordner KOPIERT (kampagne.json, sl/zustand.json, sl/barrieren, sl/karten, daten/); das Original bleibt unberührt.
Ohne die Variable wird der Test übersprungen.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.hilfen import Testkampagne, freier_port, server_starten, server_stoppen

ORDNER = [Path(p) for p in os.environ.get("SPIELTISCH_ALTSTAENDE", "").split(";") if p.strip()]


@unittest.skipUnless(ORDNER, "SPIELTISCH_ALTSTAENDE nicht gesetzt")
class AltstaendeTest(unittest.TestCase):
    def test_kampagnen_laden(self):
        for quelle in ORDNER:
            with self.subTest(kampagne=quelle.name):
                self._pruefen(quelle)

    def _pruefen(self, quelle):
        tmp = Path(tempfile.mkdtemp(prefix="spieltisch-alt-"))
        ziel = tmp / "k"
        try:
            (ziel / "sl").mkdir(parents=True)
            cfg = json.loads((quelle / "kampagne.json").read_text(encoding="utf-8"))
            cfg["port"] = freier_port()
            (ziel / "kampagne.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            for teil in ("sl/zustand.json", "sl/schluessel.txt"):
                if (quelle / teil).exists():
                    shutil.copy(quelle / teil, ziel / teil)
            for teil in ("sl/barrieren", "sl/karten", "daten"):
                if (quelle / teil).is_dir():
                    shutil.copytree(quelle / teil, ziel / teil)
            proc = server_starten(ziel, cfg["port"], warten=60)
            try:
                tk = Testkampagne.__new__(Testkampagne)
                tk.ordner, tk.port, tk.proc = ziel, cfg["port"], proc
                import sl_api
                tk.st = sl_api.Spieltisch(str(ziel))
                s = tk.stand()
                self.assertEqual(s["kampagne"], cfg["name"])
                sl = tk.stand(sl=True)
                self.assertTrue(sl["sl"])
                tk.http("/api/charaktere")
                tk.st.stand()
                tk.st.modi()
                if s["karte"]:
                    self.assertEqual(tk.http(f"/api/karte/{s['karte']['id']}.jpg", roh=True)[:2], b"\xff\xd8")
            finally:
                server_stoppen(proc)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
