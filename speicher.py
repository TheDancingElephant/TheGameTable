"""Shell: Dateizugriff für Charaktere (daten/charaktere/<id>.json).

Ein Charakterspeicher lebt genau einen Befehl lang. Er liest Dateien bei Bedarf, gibt immer Kopien heraus
(wie früher das Lesen von der Platte) und schreibt Änderungen erst mit `schreiben()` – nur wenn der Befehl
gelungen ist. Ohne Ordner arbeitet er rein im Speicher (für Kern-Tests).
"""
import copy
import json
from pathlib import Path

from bereiche.kern import Fehler


class Charakterspeicher:
    def __init__(self, ordner=None, daten=None):
        self.ordner = Path(ordner) if ordner else None
        self._cache = {}          # id -> Dict (Stand nach letztem Speichern in diesem Befehl)
        self._geaendert = set()
        self._geloescht = set()
        self._alle_geladen = False
        for c in (daten or {}).values() if isinstance(daten, dict) else (daten or []):
            self._cache[c["id"]] = copy.deepcopy(c)
        if self.ordner is None:
            self._alle_geladen = True

    def _datei(self, cid):
        return self.ordner / f"{cid}.json"

    def _holen(self, cid):
        if cid in self._geloescht:
            return None
        if cid not in self._cache and self.ordner is not None:
            p = self._datei(cid)
            if not p.is_file():
                return None
            self._cache[cid] = json.loads(p.read_text(encoding="utf-8"))
        return self._cache.get(cid)

    def existiert(self, cid):
        return bool(cid) and self._holen(str(cid)) is not None

    def laden(self, cid):
        c = self._holen(str(cid))
        if c is None:
            raise Fehler(f"Charakter {cid!r} nicht gefunden")
        return copy.deepcopy(c)

    def speichern(self, c):
        """Übernimmt die (schon bereinigten) Basisdaten; geschrieben wird erst in schreiben()."""
        self._cache[c["id"]] = copy.deepcopy(c)
        self._geaendert.add(c["id"])
        self._geloescht.discard(c["id"])

    def loeschen(self, cid):
        self._cache.pop(cid, None)
        self._geaendert.discard(cid)
        self._geloescht.add(cid)

    def ids(self):
        if not self._alle_geladen:
            for p in sorted(self.ordner.glob("*.json")):
                self._holen(p.stem)
            self._alle_geladen = True
        return sorted(cid for cid in self._cache if cid not in self._geloescht)

    def alle(self):
        """Kopien aller Charaktere, nach ID sortiert (wie die Dateinamen)."""
        return [self.laden(cid) for cid in self.ids()]

    def schreiben(self):
        if self.ordner is None:
            return
        self.ordner.mkdir(parents=True, exist_ok=True)
        for cid in sorted(self._geaendert):
            self._datei(cid).write_text(json.dumps(self._cache[cid], ensure_ascii=False, indent=1), encoding="utf-8")
        for cid in self._geloescht:
            p = self._datei(cid)
            if p.exists():
                p.unlink()
        self._geaendert.clear()
        self._geloescht.clear()
