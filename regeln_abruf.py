"""Regeldatenbank aus dem PRD abrufen/aktualisieren (Code: bereiche/wissen/regeln_abruf.py).

    python regeln_abruf.py aufbauen | aktualisieren | index
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bereiche.wissen import regeln_abruf  # noqa: E402

if __name__ == "__main__":
    regeln_abruf.main()
