# Styleguide

> Schreibweise im Code des Spieltischs. Architektur und Fachbereiche: [ARCHITEKTUR.md](ARCHITEKTUR.md).

## Sprache und Namen

- **Deutsch** für Bezeichner, Kommentare, Docstrings, Meldungen, Commit-Nachrichten. Fachbegriffe exakt wie im
  deutschen PRD (Glossar in ARCHITEKTUR.md, Abschnitt 13); keine englischen Regelbegriffe (`armor_class`,
  `hit_points`), keine D&D-5e- oder PF2-Begriffe.
- **Bezeichner ohne Umlaute:** `ae oe ue ss` (`zustaende`, `groesse`, `beruehrung`). In Texten für Menschen
  (Meldungen, Protokoll, Oberfläche, Markdown) echte Umlaute.
- Python: `snake_case` für Funktionen/Variablen, `GROSS_MIT_UNTERSTRICH` für Konstanten und Tabellen,
  `CamelCase` nur für die wenigen Klassen. Module/Pakete klein, ein Wort, wo es geht.
- JSON-Felder und JavaScript: `camelCase` (`tpMax`, `karteAktiv`, `nebelVersion`), wie in den bestehenden Dateien.
- Kurze Namen für die immer gleichen Dinge: `z` Spielstand, `kx` Kontext, `t` Token, `c` Charakter,
  `k` Karte, `kid` Karten-ID, `cid` Charakter-ID, `b` Befehls-/Anfragedaten, `e` Protokoll-/Listeneintrag.
- Abgeleitete, nie gespeicherte Werte beginnen mit Unterstrich (`_d`, `_ep`, `_wirkung`).
- Private Hilfsfunktionen eines Bereichs mit Unterstrich; was ohne Unterstrich in `__init__.py` steht, ist
  öffentlich und darf von anderen Bereichen benutzt werden.

## Python

- Python 3.10+, nur Standardbibliothek plus PyMuPDF/numpy (pywebview nur in der Zentrale). Neue Abhängigkeiten
  nur nach Rücksprache.
- Zeilen bis 120 Zeichen (ältere Zeilen bis ~130 dürfen bleiben). Vier Leerzeichen, keine Tabs.
- Docstring je öffentlicher Funktion: ein Satz, was sie tut; Regelbezug kurz nennen (*GRW: Flankieren*).
- **Funktionen statt Klassen.** Daten sind Dicts im Dateiformat. Keine Vererbung für Regeln; Varianten als
  Tabellen/Datensätze (z. B. `VORLAGEN` der Modi, `INKREMENTE` der Waffen).
- **Kernfunktionen** (in `bereiche/`): erstes Argument `kx` (Kontext), dann fachliche Parameter. Kein Zugriff
  auf Dateien, `time`, `random`, Umgebungsvariablen oder Modul-Globale mit Zustand. Würfeln nur über
  `kx.w(seiten)` bzw. `kern.wuerfeln(ausdruck, kx.w)`. Protokoll über `kx.protokoll(...)`, Signale an andere
  Bereiche über `kx.ereignis(...)`.
- Reine Hilfsfunktionen ohne Kontext (Geometrie, Tabellen, Formeln) bekommen nur, was sie brauchen
  (`pf_distanz(x0, y0, x1, y1)`), und verändern nichts.
- Fehler, die der Spieler oder SL sehen soll: `raise Fehler("Klartext, was nicht geht und warum")`. Die Shell
  macht daraus HTTP 400 und rollt den Spielstand zurück. Andere Ausnahmen gelten als Programmfehler (500).
- Prüfen vor Ändern: Erst alle Bedingungen prüfen, dann verändern (die Sicherung der Shell ist das Netz, nicht
  der Plan).
- JSON schreiben mit `ensure_ascii=False` (Spielstand `indent=1`, Charaktere `indent=1`).
- Dateien UTF-8, Zeilenende LF (`.gitattributes`), `.bat` mit CRLF.
- Keine Abkürzungstricks wie `eval` außer der vorhandenen, abgesicherten Zauberformel (`formel`).

## Tests

- `unittest`, Dateien `tests/test_<bereich>.py`, Testnamen beschreiben das Verhalten
  (`test_hast_erhoeht_rk_und_angriff`).
- Würfel im Test immer fest (`kern.FesterWuerfel([17, 3, …])`), nie vom Zufall abhängig.
- Testkampagnen entstehen im Temp-Ordner aus `tests/fixtures/`; keine echten Kampagnendaten einchecken.

## JavaScript (web/)

- ES-Module (`<script type="module">`), kein Build-Schritt, keine Frameworks, keine CDN-Abhängigkeiten.
- Ein Modul je Bereich (`web/kampf.js`, `web/karte.js` …) plus `web/grundlagen.js` (api, $, esc, meldung) und
  `web/zustand.js` (gemeinsamer Zustand `G`, nicht als lose `let`-Variablen: Importe sind schreibgeschützt).
- Benannte Importe am Dateianfang (`import { $, api } from "./grundlagen.js";`), keine Standard-Exporte.
- Code, der beim Laden läuft (Ereignis-Handler eintragen), darf nur Funktionen anderer Module verwenden, keine
  `const`-Werte aus Modulen, die sich gegenseitig importieren (sonst „Cannot access before initialization“).
- HTML immer über `esc()` zusammensetzen; keine Spieler- oder SL-Texte ungeprüft in `innerHTML`.
- Regeln werden im Browser höchstens vorgeprüft (Komfort); verbindlich entscheidet der Server.

## Commits

- Deutsch, erste Zeile ≤ 72 Zeichen, sagt was und wofür („Kampf: Angriff gegen RK als Kernfunktion“).
- Ein Thema je Commit; Umbau und Verhaltensänderung nicht mischen.
- Tests grün vor dem Commit (`python -m unittest`).
- Keine Kampagnendaten, keine Schlüssel, keine Pfade dieses Rechners (`paket_bauen.py --pruefen` hilft).
- Kleine, prüfbare Schritte: Umbau so, dass nach jedem Commit Tests grün sind und das Tool spielbar bleibt.
