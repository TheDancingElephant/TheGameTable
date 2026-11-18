"""Legt eine Vorführ-/Testkampagne an (für Oberflächentests im Browser), ohne Server zu starten.

    python tests/demo_kampagne.py ZIELORDNER [--port 8799]

Danach: python server.py --kampagne ZIELORDNER, dann  python tests/demo_kampagne.py ZIELORDNER --fuellen
(setzt Karte, SC, Gegner, Initiative über die SL-API).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.hilfen import FIXTURES  # noqa: E402

import sl_api  # noqa: E402


def anlegen(ziel, port):
    ziel = Path(ziel)
    (ziel / "daten" / "charaktere").mkdir(parents=True, exist_ok=True)
    (ziel / "sl").mkdir(exist_ok=True)
    (ziel / "kampagne.json").write_text(json.dumps({"name": "Vorführkampagne", "port": port}, ensure_ascii=False),
                                       encoding="utf-8")
    for p in (FIXTURES / "charaktere").glob("*.json"):
        shutil.copy(p, ziel / "daten" / "charaktere" / p.name)


def fuellen(ziel):
    st = sl_api.Spieltisch(str(ziel), basis=str(ziel))
    st.karte_neu("halle", "Halle", leer=[20, 14], aktiv=True)
    st.befehl(op="aufdecken", form="rechteck", felder=[0, 0, 12, 13])
    for cid, x, y in (("brak", 3, 4), ("mira", 3, 6), ("lied", 2, 5)):
        st.sc_platzieren(cid, x, y)
    ork = st.token("gegner", "Ork", 7, 5, tp=15, rk=13)
    st.token("gegner", "Lauerer", 16, 8, tp=10, verborgen=True)
    st.ini("start")
    for name, wert, tok in (("Brak", 18, "sc-brak"), ("Ork", 12, ork), ("Mira", 9, "sc-mira"), ("Lied", 7, "sc-lied")):
        st.ini("eintrag", name=name, wert=wert, token=tok)
    st.ini("los")
    st.erzaehle("Die Halle riecht nach Rauch.\n> „Wer da?“ ruft eine raue Stimme.", titel="Die Halle")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ziel")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--fuellen", action="store_true")
    a = ap.parse_args()
    fuellen(a.ziel) if a.fuellen else anlegen(a.ziel, a.port)
