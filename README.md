# Spieltisch – gemeinsames Tool

**Dokumentation**
- [ANLEITUNG.md](ANLEITUNG.md) – Anleitung für Anwender (Zentrale, Spielen, SL-Sitzung, Fehlerbehebung, Sicherungen)
- [AGENT.md](AGENT.md) – Anweisungen für den SL-Agenten (Grundlage für die `CLAUDE.md` jeder Kampagne)
- [mcp/AGENTS.md](mcp/AGENTS.md) – modellunabhängige SL-Anweisung für andere KI-Programme (Kampagnen bekommen sie aus `vorlage/` mit ihren Pfaden)
- Vorlagen: [mcp/beispiel.mcp.json](mcp/beispiel.mcp.json), [mcp/beispiel-settings.json](mcp/beispiel-settings.json),
  [mcp/beispiel-verwaltung.mcp.json](mcp/beispiel-verwaltung.mcp.json), [mcp/kartenformat-beispiel.json](mcp/kartenformat-beispiel.json)
- Technische Details zu Server, `sl.py`, MCP, Kartenformat und Zentrale: die Abschnitte unten in dieser Datei.
- Für Entwickler: [ARCHITEKTUR.md](ARCHITEKTUR.md) (Fachbereiche, Functional Core / Imperative Shell, Dateiformate,
  Tests, Entwicklungsablauf, Glossar) und [STYLEGUIDE.md](STYLEGUIDE.md) (Schreibweise im Code).
- Quellcode: https://github.com/TheDancingElephant/TheGameTable (Tests: `python -m unittest` oder `tests.bat`).

Ein Tool, mehrere Kampagnen. Jede Kampagne ist ein Ordner mit `kampagne.json` (`{"name": "...", "port": 8777}`),
darin `sl/` (Spielstand, Karten, Notizen, Quellen, Schlüssel) und `daten/` (Charaktere, Protokoll).
Regeldaten und Code liegen hier im Tool: `daten/zauber_prd.json` (alle Zauber aus dem deutschen PRD, OGL – siehe
`daten/LIZENZ-ZAUBER.txt`) und `daten/zauber.json` (Spielmechanik für die Zauber, die das Tool selbst auswertet;
eine kampagneneigene `daten/zauber.json` ersetzt sie). `bereiche/wissen/zauber_db.py` vereint beides (siehe Abschnitt Zauberdatenbank).
Dazu die Regeldatenbank `regeln/regeln.sqlite` (PF1-Grundregelwerk ohne Zauber, OGL – siehe `regeln/LIZENZ-REGELN.txt`;
Abschnitt Regeldatenbank).

Kampagnenordner wird gefunden über: `--kampagne PFAD` → Umgebungsvariable `SPIELTISCH_KAMPAGNE` → Suche aufwärts
vom aktuellen Verzeichnis nach `kampagne.json`.

```
python <Programmordner>\server.py --kampagne "<Kampagnenordner>"
python <Programmordner>\sl.py --kampagne "<Kampagnenordner>" stand
```
Aus dem Kampagnenordner heraus (Claude-Sitzung dort) genügt `python <Programmordner>\sl.py stand`.
Verschiedene Kampagnen brauchen verschiedene Ports (in `kampagne.json`), dann können sie parallel laufen.
Neue Kampagne: Zentrale „+ Neue Kampagne“ oder MCP `kampagne_neu` (Gerüst aus `vorlage/`, ältere Installationen: `<Kampagnen-Ordner>/_Vorlage`).

## Aufbau des Programms (Kurzfassung, Details in ARCHITEKTUR.md)
- `server.py` (Shell: HTTP, Sperre, Speichern), `sl_api.py` / `sl.py` / `mcp_server.py` (SL-Zugriff), `zentrale.py`.
- `bereiche/` – Fachbereiche: `tisch`, `kampf`, `karte` (inkl. `karten.py`, `barrieren.py`, `kartenformat.py`),
  `charakter` (inkl. `modi.py`, `aufstieg.py`), `magie`, `besitz`, `wissen` (Zauber-/Regeldatenbank), `kampagne`;
  `bereiche/kern.py` (Fehler, Würfel, Kontext), `speicher.py` (Charakterdateien).
- `web/` – Oberfläche als ES-Module: `app.js` (Einstieg), `grundlagen.js`, `zustand.js`, `tisch.js`, `kampf.js`,
  `karte.js`, `magie.js`, `charakter.js`, `besitz.js`, `aufstieg.js`.
- `tests/` – Testsammlung (`python -m unittest`), `tests/demo_kampagne.py` für Oberflächentests.

## Installation, Pfade, Paket
- **`einrichten.bat`** (→ `einrichten.py`): Python suchen, Pakete installieren (PyMuPDF, numpy, pywebview),
  Kampagnen-Ordner festlegen (Standard `..\Kampagnen`, gespeichert in `zentrale.json`), `python-pfad.txt` schreiben,
  Verknüpfung „Spieltisch-Zentrale“ (Desktop + Programmordner), Pfade vorhandener Kampagnen reparieren.
  Optionen: `--wurzel ORDNER`, `--ja`, `--ohne-pakete`, `--ohne-verknuepfung`, `--verknuepfung-ordner ORDNER`.
- **Python finden** (`python_finden.bat`, genutzt von `start.bat`, `zentrale.bat`, `einrichten.bat`): `SPIELTISCH_PYTHON`
  → `python-pfad.txt` → `py -3` → `python` im PATH → `%LOCALAPPDATA%\Programs\Python\Python3*`, `%ProgramFiles%\Python3*`;
  Mindestversion 3.10 (`python_pruefen.py`).
- **Pfade erzeugen** (`sl_api.pfade_schreiben`): `.mcp.json` (Server `spieltisch`) und `.claude/launch.json`
  (Konfiguration `spieltisch`) mit laufendem Python, Programmordner und Kampagnenordner; andere Einträge bleiben,
  eine Datei-Sperre bekommt den neuen Kampagnenpfad. `pfade_ok` prüft, `pfade_reparieren` schreibt neu (Zentrale-Knopf,
  MCP-Tool `pfade_reparieren` im Verwaltungsmodus, `einrichten.bat`). Platzhalter `{{PYTHON}}`, `{{SPIELTISCH}}`,
  `{{KAMPAGNE}}` in `.md`-Dateien der Vorlage werden beim Anlegen ersetzt.
- **`paket_bauen.py`**: ZIP zum Weitergeben (`dist/Spieltisch-<Datum>.zip`) mit Programm, Vorlage, Doku, `mcp/`,
  Einrichtungsskripten – ohne Kampagnen, `_sicherung-*`, `__pycache__`, `*.bak*`, Logs, Schlüssel, `zentrale.json`,
  `python-pfad.txt`, Verknüpfungen; prüft das Ergebnis auf Pfade dieses Rechners.

## Automatischer Nebel des Krieges (Sichtlinie)
Nach jeder Bewegung eines SC-Tokens (Spieler oder `sl.py zieh`) deckt der Server per echter Sichtlinie auf (Strahlen vom Token, Wandblöcke aus `karten.wandkarte` blockieren; nur aufdecken, nie verdecken). Geschlossene Türen sind Wandlinien und blockieren; Räume dahinter und Geheimtüren deckt der SL von Hand auf. Sichtweite: `sicht`-Feld am Token, sonst „Dunkelsicht N m“ aus den Charakterdaten (N / `meterProFeld` Felder), sonst `sichtFelder` der Karte (Standard 8).
- **Standard: aus.** Pro Karte: `sl.py raster --nebel-auto ein|aus|standard` (`standard` = Kampagnenvorgabe); Kampagnenvorgabe: `"autoNebel": true` in `kampagne.json`.
- `sl.py raster --sicht-felder N`: Standardsichtweite der Karte; `sl.py sicht`: einmalig für alle SC aufdecken (unabhängig vom Schalter).
- Die Wandkarte wird pro Karte im Speicher gehalten und neu berechnet, wenn sich die Bilddatei ändert. Bei falsch erkannten Wänden (Höhlen) für diese Karte abschalten.

## Illusionen / Täuschungsansicht pro aktivem SC
Ist ein SC in der Initiative am Zug, zeigt die Spieleransicht Token so, wie **dieser** Charakter sie wahrnimmt. Ohne Initiative/ohne Täuschungsdaten ändert sich nichts; die SL-Ansicht zeigt immer die Wahrheit. Der aktive Token selbst wird nie getäuscht; TP/Gesundheit getäuschter Token werden nicht gesendet.

```
sl.py taeuschung sc-aritian --fuer elofin --name Vrock --symbol V --farbe "#aa0000" --art gegner
sl.py taeuschung scramge --fuer kalador harold --name Aritian --symbol A --sichtbar   # --sichtbar: auch wenn sonst verborgen/im Nebel
sl.py taeuschung sc-aritian --weg [--fuer elofin]      # Täuschung entfernen
sl.py taeuschung --schalter aus|ein                    # global abschalten (Daten bleiben)
```
Felder je Charakter-ID: `name, symbol, farbe, x, y, groesse, art (sc|gegner|nsc), sichtbar`. Wer die Illusion durchschaut, bekommt einfach keinen Eintrag. Die Initiativliste zeigt den Scheinnamen. Grenze: Protokolltexte (Angriffe, Würfe) nennen weiter den echten Namen.

## Tote und kampfunfähige Token
Token mit Zustand „Tot“ werden auf der Karte grau, halbtransparent, mit ☠ und durchgestrichenem Namen gezeichnet und bekommen keinen Zugkranz mehr. „Sterbend“, „Kampfunfähig“, „Bewusstlos“ erscheinen abgeschwächt (halbtransparent). Reine Frontend-Änderung in `web/karte.js` (`tokenZeichnen`); Kampagnen ohne diese Zustände sehen keinen Unterschied. Setzen: `sl.py zustand ID +Tot`.

## Modi: Buffs, Größe, Reichweite (Hast, Person vergrößern, Heldenmut …)
Gelegenheitsangriffe: `sl.py angriff … --ga [bewegung|andere]` (MCP `angriff` mit `gelegenheitsangriff`). Bei `bewegung` zählt das Talent **Beweglichkeit** des Ziels (+4 RK, Talentliste des Charakters bzw. Feld `talente` am Token), dazu Modi mit `rkga`; beides entfällt, wenn das Ziel auf dem falschen Fuß oder hilflos ist.

Zeitlich begrenzte Wirkungen liegen als Liste `modi` am Charakter (oder am Token bei Gegnern/NSC ohne Charakterdatei). Die gespeicherten Basiswerte bleiben unverändert; der Server rechnet die wirksamen Werte beim Lesen drauf (`bereiche/charakter/modi.py`). Ende = Eintrag entfällt, nichts muss zurückgerechnet werden. Abschaltbar: `"modi": false` in `kampagne.json`; ohne Einträge in `modi` ändert sich nichts.

```
sl.py modus sc-nuramon-andokai "Person vergrößern" --minuten 1      # bekannte Vorlage (Größe +1, ST +2, GE −2)
sl.py modus aritian Hast --runden 4
sl.py modus kalador Rindenhaut --stunden 10 --wirkung rkr=3         # eigene Wirkung (Schlüssel siehe unten)
sl.py modus ghul1 Verlangsamt --runden 5 --wirkung rk=-1 angriff=-1
sl.py modus-ende aritian Hast ; sl.py modi ; sl.py modus-zeit --minuten 10
```
Vorlagen: Hast/Massenhast, Heldenmut, (Person) vergrößern/verkleinern, Stierstärke, Katzenanmut, Bärenausdauer, Fuchslist, Eulenweisheit, Adlerprunk. Gleicher Name ersetzt den alten Modus (kein Stapeln). Dauer: im Kampf −1 Runde je neuer Kampfrunde; sonst `modus-zeit`; `rast` zählt 8 Stunden ab.

Wirkungsschlüssel (ganze Zahlen, additiv): `groesse` (Stufen), `ST GE KO IN WE CH`, `rk` (normal + Berührung, z. B. Hast), `rkr` (normal + auf dem falschen Fuß, z. B. Rindenhaut), `rkb`, `rkf`, `rkga` (nur gegen Gelegenheitsangriffe), `angriff`, `nahangriff`, `fernangriff`, `schaden` (Nahkampf), `ref wil zaeh rw`, `ini kmb kmv`, `tempo` (Meter), `reichweite` (Felder), `extraangriff` (Hast: zusätzlicher Angriff in Serien), `fert:NAME`.
- **Größe**: Größenmodifikator auf Angriff, RK, KMB/KMV, Heimlichkeit/Fliegen; Waffenschaden steigt/sinkt um Würfelstufen; Token wächst auf 2×2 (3×3 …) mit Platzsuche, Nahkampf-/Berührungsreichweite aus Größe und `koerperbau` (`hoch` Standard, `lang`): Mittel 1,5 m, Groß hoch 3 m / lang 1,5 m, Riesig 4,5/3 m usw. Basisgröße: Feld `groesse` ("Mittel", "Groß" …) am Charakter, sonst aus `groesseFelder`.
- **Attribute** leiten ab: ST → Nahkampfangriff/-schaden, KMB, KMV; GE → RK (normal/Berührung; adFF nur bei Malus), Fernkampfangriff, REF, Ini, KMV; KO → ZÄH (TP-Änderung durch KO nicht: dafür TP von Hand).
- Der Token trägt `reichweite` (Felder) nur solange ein Größen-/Reichweitenmodus aktiv ist; Nahkampf, Berührungszauber und -fähigkeiten prüfen dagegen. Ohne Modus gilt „angrenzend“ wie bisher. Gegner-Token: `sl.py angriff` addiert `angriff`-Modi (und Größe) automatisch.
- Speichern aus dem Bogeneditor ist sicher: unveränderte berechnete Werte werden beim Speichern wieder durch die Basiswerte ersetzt, von Hand geänderte bleiben. Grenzen: kein Typ-Stapelverbot (Ausweichen/Verbesserung …), SG-Änderungen und Fertigkeiten aus Attributen (außer Heimlichkeit/Fliegen) rechnet der SL von Hand; Zweihand-Schadensfaktor wird nicht berücksichtigt.
- `sl.py char ID pfad=JSON` versteht jetzt Listenindizes (`zauberliste.23.verbraucht=1`).
- Der laufende Server muss nach dem Update neu gestartet werden (Code wird nur beim Start geladen).

## MCP-Server für den SL-Agenten (`mcp_server.py`)
Der SL-Agent (Claude) greift nur noch über MCP auf das Tool zu: keine Bash-Warteschleifen, keine Heredocs, kein direkter
Dateizugriff im Kampagnenordner (Spoilerschutz). Eine Instanz pro Kampagne, stdio, keine Zusatzpakete:
```
python <Programmordner>\mcp_server.py "<Kampagnenordner>"
```
- **Gemeinsame Bibliothek `sl_api.py`**: die ganze Befehlslogik; `sl.py` (CLI für Handarbeit, Verhalten unverändert) und
  `mcp_server.py` sind dünne Hüllen darum. Fehler kommen als `SLFehler` mit lesbarer Meldung statt `sys.exit`.
- **Schlüssel** bleibt im MCP-Prozess (Header `X-SL`), der Agent sieht ihn nie.
- **Tools** (77 je Kampagne): Tisch (`stand`, `protokoll`, `erzaehle`, `warte`, `status_setzen`, `szene`, `handout`, `sl_notiz`,
  `streiche`, `wurf`), Token/Kampf (`token_neu`, `token_aendern`, `token_zeigen`, `token_entfernen`, `zieh`, `tp`, `zustand`,
  `sc_platzieren`, `angriff`, `taeuschung`), Initiative (`ini`, `zug`), Modi (`modus`, `modus_ende`, `modus_zeit`, `modi`),
  Karte/Nebel/Barrieren (`karten_liste`, `material_liste`, `material_vorschau`, `karte_neu`, `karte_import`, `karte_export`, `karte_aktivieren`,
  `karte_bekannt`, `raster`, `vorschau`, `karte_einrichten`, `nebel`, `abdecken`, `sicht`, `sicht_teilen`, `nebel_modus`,
  `barrieren_erkennen`, `barrieren_liste`, `barriere_neu`, `barriere_aendern`, `barrieren_entfernen`,
  `barrieren_bereiche_frei`, `tuer`), Charakter/EP/Aufstieg (`charaktere`, `charakter`, `char_setzen`, `ep`,
  `aufstieg_zeigen`, `aufstieg_fertig`, `aufstieg_zurueck`, `aufstieg_abbrechen`, `rast`, `charaktere_importieren`),
  Kasse (`kasse`, `beute`, `item`, `ausruestung`, `zauberbuch`), Zauber (`zauber_suchen`, `zauber_info`), Regeln
  (`regel_suchen`, `regel_lesen`, `talent_info`, `zustand_info`, `fertigkeit_info`, `regeln_aktualisieren`), Dateien (`notizen_liste`, `notiz_lesen`,
  `notiz_anhaengen`, `notiz_ersetzen`, `notiz_schreiben`, `quellen_liste`, `quelle_lesen`, `quelle_aus_pdf`, `suchen`), Server
  (`server_status`, `server_starten`).
- **`warte`** blockiert (Timeout Standard 540 s, max. 3600 s) und gibt die neuen Ereignisse zurück; nutzt den Long-Poll
  `GET /api/sl/ereignisse?seit=N&warten=S` (Server wartet bis zu 120 s auf ein weckendes Ereignis). Ältere Server ohne
  Long-Poll funktionieren weiter (dann fragt die Bibliothek sekündlich). Abbrechbar (MCP `notifications/cancelled`),
  dabei wird nichts als verarbeitet markiert.
- **Notizen/Quellen** liest der MCP-Server direkt aus `sl/notizen/*.md` bzw. `sl/quellen/*.txt` (nur Dateinamen, keine
  Pfade; Zeilenbereiche; `notiz_schreiben` sichert die alte Fassung nach `sl/notizen/.sicherung/`). Dafür ist kein
  Server-Endpunkt nötig, es geht auch, wenn der Server nicht läuft.
- **Bilder** (`vorschau`, `material_vorschau`) kommen als JPEG direkt im Tool-Ergebnis (längste Kante begrenzt).
- **Neue Karte komplett per MCP**: `material_vorschau` (Seite/Ausschnitt; `probe_raster` prüft eine Feldgröße) →
  `karte_neu` → `vorschau` → `karte_einrichten` (Barrieren erkennen, Nebelmodus sicht, Auto-Nebel, aktivieren,
  SC platzieren, Sicht) → Korrekturen mit `barrieren_entfernen`/`barriere_neu` → `vorschau spieler`.
- Neu in `sl.py`/`sl_api`: `karte-neu --bild` mit `versatz_erkennen` (nur API/MCP) sucht den Rasterversatz.

**Einrichtung pro Kampagne** (Vorlagen in `mcp/`):
1. `mcp/beispiel.mcp.json` als `.mcp.json` in den Kampagnenordner kopieren, Pfad anpassen (Servername `spieltisch`).
2. Optional die Sperre `mcp/beispiel-settings.json` als `.claude/settings.json` (Bash/PowerShell aus, Read/Edit/Write/
   Glob/Grep im Kampagnenordner gesperrt, `MCP_TOOL_TIMEOUT` 1 h für `warte`). Pfade in der Form `//d/Pfad/**`.
   Projekt-Einstellungen und `.mcp.json` greifen erst, wenn der Ordner einmal als vertrauenswürdig bestätigt wurde.
3. Leitfaden: `mcp/CLAUDE-entwurf.md` als Grundlage für die `CLAUDE.md` der Kampagne.
4. Server neu starten, damit der Long-Poll aktiv ist.

Windows-Hinweis: `mcp_server.py` lädt numpy/pymupdf beim Start im Hauptthread vor; DLL-Nachladen in einem Worker-Thread
hängt sonst, solange der Hauptthread auf stdin liest.

## Karten mit exakten Wänden importieren (`bereiche/karte/kartenformat.py`)
Statt Wände aus dem Bild zu erkennen, kann eine Karte mit fertigen Wänden/Türen importiert werden
(MCP `karte_import` / `karte_export`, CLI `sl.py karte-import DATEI [--id] [--name] [--aktiv]`, `sl.py karte-export ID`):
- **Spieltisch-Kartenformat** (JSON, Koordinaten in Feldern = Gitterpunkte; Beispiel `mcp/kartenformat-beispiel.json`,
  Beschreibung im Kopf von `bereiche/karte/kartenformat.py`): `raeume` (Rechtecke/Vielecke mit `boden`; Umrisse werden Wände,
  überlappende Räume verschmelzen, aneinanderstoßende bekommen eine Wand), `waende` (Linienzüge), `tueren`
  (`tuer|geheimtuer|fenster`, `offen`), `oeffnungen` (Durchgänge), `beschriftungen`. Türen und Öffnungen schneiden die
  Wand darunter auf. **Ohne `bild`** zeichnet das Tool die Karte selbst (Bild und Wände passen exakt; Geheimtüren sehen
  wie Wand aus). **Mit `bild`** + `zelle_px` + `versatz` werden die Wände über ein vorhandenes Bild gelegt.
- **Universal VTT** (`.dd2vtt`/`.uvtt` aus Dungeondraft, DungeonFog, Dungeon Alchemist …): Bild, Raster, `line_of_sight`
  und `portals` (Türen) werden übernommen.
- Der Import legt Bild (`sl/karten/ID.png`), Karte und Barrieren (`sl/barrieren/ID.json`, `"quelle": "import"`) an
  und schaltet Nebelmodus `sicht` und Auto-Nebel ein. Neuer Server-Befehl `barrieren-setzen`.
  `barrieren erkennen` verweigert bei importierten Karten (sonst würden die exakten Wände ersetzt; `--erzwingen`).
- `karte_export` schreibt eine (auch per Erkennung + Korrektur entstandene) Karte nach `sl/karten/ID.karte.json`;
  damit lässt sie sich sichern oder in eine andere Kampagne übernehmen.

## Neue Kampagne komplett per MCP
- **`quelle_aus_pdf`** (in jeder Kampagne): Text einer Abenteuer-PDF nach `sl/quellen/<name>.txt`, mit Seitenmarken
  `=== Seite N ===` (= PDF-Seite, passend zu `material_vorschau`/`karte_neu`). Seitenbereich wählbar. Gescannte Seiten
  ohne Textebene werden gemeldet (dafür bräuchte es OCR).
- **Verwaltungsmodus**: `mcp_server.py --verwaltung <Kampagnen-Ordner>` (oder ein Ordner ohne `kampagne.json`)
  bietet nur `kampagnen_liste`, `kampagne_neu` und `pfade_reparieren` (Vorlage: `mcp/beispiel-verwaltung.mcp.json`, z. B. als `.mcp.json`
  im Kampagnen-Hauptordner). Beide Tools gibt es auch in jeder Kampagnen-Instanz (dann für die Geschwisterordner).
- **`kampagne_neu`**: legt den Ordner aus `vorlage/` an, `kampagne.json` mit dem nächsten freien Port (ab 8780; Ports
  aller Kampagnen und belegte Ports werden gemieden), `.mcp.json` für diesen Server, `CLAUDE.md` aus
  `mcp/CLAUDE-entwurf.md`, `.claude/launch.json` (Browser-Vorschau), `sl/notizen/kapitel1.md`; kopiert Abenteuer-PDFs
  nach `Material/` und übernimmt ihren Text nach `sl/quellen/`. `sperre: true` legt zusätzlich `.claude/settings.json`
  mit der Datei-Sperre an. Danach: neue Claude-Sitzung im neuen Ordner (einmal vertrauen), `server_starten`,
  `charaktere_importieren`, Notizen und Karten aufbauen.

## Spieltisch-Zentrale (Desktop-Anwendung, `zentrale.py`)
Ein Fenster zum Verwalten aller Kampagnen, ohne Konsole:
```
pythonw <Programmordner>\zentrale.py [--wurzel <Kampagnen-Ordner>]
```
(Verknüpfung legt `einrichten.bat` an: Ziel `pythonw.exe`, Argument `"…\zentrale.py"`; nutzt pywebview mit dem in
Windows eingebauten Edge WebView2, ohne pywebview öffnet sie sich im Standardbrowser.)
- Karte je Kampagne: Name, Port, Status (läuft / läuft extern / aus), MCP/Sperre, Zahl der Charaktere/Karten/Quellen,
  bei laufendem Server Szene, SL-Status und **unbeantwortete Spieleraktionen**; Warnung bei doppeltem Port und bei
  Fehlern im Server-Protokoll.
- **Starten/Stoppen** (Server ohne Konsolenfenster, Ausgabe nach `sl/server.log`; Stoppen auch für extern gestartete
  Server, nach Prüfung, dass auf dem Port wirklich `server.py` dieser Kampagne läuft).
- **Spieleransicht / SL-Ansicht** in eigenen Fenstern (oder „Im Browser“), Ordner/Material im Explorer, Protokoll.
- **Neue Kampagne** (Dialog mit Datei-Auswahl für PDFs) über `sl_api.kampagne_neu`; **MCP einrichten** legt bei
  bestehenden Kampagnen `.mcp.json` und `.claude/launch.json` an; **Pfade reparieren** schreibt beide mit den Pfaden
  dieses Rechners neu (Marke „Pfade veraltet“, wenn Python/Programm/Kampagnenpfad in `.mcp.json` nicht stimmen).
- Server, die die Zentrale gestartet hat, werden beim Schließen des Hauptfensters gestoppt (abschaltbar unten links).
  Einstellungen in `zentrale.json` (Kampagnen-Ordner, Stopp-Verhalten).
- Technik: lokaler Dienst auf `127.0.0.1:8770` (`--port`) + `web/zentrale.html`; `--ohne-fenster [--browser]` zum
  Testen ohne Desktop-Fenster. Am Spieltisch-Server, an der Weboberfläche, `sl.py` und MCP ändert sich nichts.
- `server.py` verweigert jetzt den Start, wenn der Port schon belegt ist (unter Windows konnte sonst ein zweiter Server
  denselben Port belegen).

## Zauberdatenbank

- `daten/zauber_prd.json`: alle Zauber des deutschen PRD (https://prd.5footstep.de/ZauberlistenIndex), je Zauber
  `name`, `url`, `schule`/`unterschule`/`kategorie`, `klassen` (Klasse → Grad; „Hexenmeister/Magier“ aufgeteilt,
  Skalde = Bardenliste), `klassenText`, `zeitaufwand`, `komponenten`, `reichweite`, `ziel`/`effekt`/`bereich`,
  `wirkungsdauer`, `rettungswurf`, `zauberresistenz`, `kurz`, `text`, `quelle`, `seite`. Lizenz: `daten/LIZENZ-ZAUBER.txt`.
- Katalog des Servers (`/api/zauber`): jeder PRD-Zauber ist bekannt (Modus `sl` = SL wertet aus, Tooltip zeigt
  Zeitaufwand/Dauer/RW); Einträge aus `zauber.json` liefern die Mechanik und haben Vorrang. Alte Namen aus
  `zauber.json` (z. B. „Segen“ → „Segnen“) und Zusätze wie „(D)“ werden erkannt. `/api/zauber?name=X` liefert einen
  Zauber vollständig (mit `prd` und `prdText`). Fehlt der Grad eines Listeneintrags, gilt der Grad der Charakterklasse.
- Nachschlagen: `sl.py zauber "Feuerball"` (vollständig, `--kurz` ohne Text), `sl.py zauber --klasse Barde --grad 3`,
  `sl.py zauber trugbild --liste`, `--volltext` sucht auch im Text; MCP: `zauber_info`, `zauber_suchen`.
- Zauberliste eines Charakters: Feld `zauberKlasse` (Editor „Zauberliste“, z. B. Kleriker); leer = aus `klasse`
  erraten (auch Archetypen wie Separatist → Kleriker, Archivar → Barde, Ermittler → Alchemist, Stabmagus → Kampfmagus).
  Der Server liefert `_zauberKlasse` und `_vorbereiten` (werden nicht gespeichert).
- **Zauber vorbereiten** (Knopf an der Charakterkarte, nur außerhalb des Kampfes, nur vorbereitende Zauberlisten:
  Kleriker, Druide, Magier, Paladin, Antipaladin, Waldläufer, Hexe, Alchemist, Kampfmagus, Schamane, oder mit
  Zauberbuch): je Platz eine Auswahl aus der Klassenliste des Grades bzw. aus dem Zauberbuch. Plätze = Einträge mit
  „pro Tag“ N → N Plätze, Einträge ohne „pro Tag“ (Zaubertricks, Pool) → je einer; spontane Einträge und „pro Tag“ 0
  bleiben unverändert. Domänenplätze (`domaene` oder Name mit „(D)“) bleiben Domänenplätze. Gleiche Zauber werden
  zusammengefasst, die Liste nach Grad sortiert, unveränderte Zauber behalten ihre Angaben. `POST /api/zauber-vorbereiten`
  (`op: "plan"` → Plätze/Stand, `op: "speichern"` mit `namen` je Platz und `stand`); Protokolleintrag „… bereitet die
  Zauber neu vor (neu: …)“.

## Regeldatenbank (PF1-Grundregelwerk, lokal)

Damit der SL-Agent Regeln nicht im Web suchen muss: `regeln/regeln.sqlite` enthält aus dem deutschen PRD
(https://prd.5footstep.de, OGL) jeweils **ohne** die Kapitel Zauber/Zauberlisten (die stehen in `daten/zauber_prd.json`):
- **Grundregelwerk:** Einführung, Völker, Klassen, Fertigkeiten, Talente, Ausrüstung, Zusätzliche Regeln, Kampf,
  Magie (allgemein), Prestigeklassen, Spielleitung, Umgebung, NSC, Magische Gegenstände, Anhang (Besondere Fähigkeiten, Zustände).
- **Expertenregeln:** Völker, Basisklassen (Alchemist, Hexe, Inquisitor, Mystiker, Paktmagier, Ritter), Optionen und
  Archetypen der Grundklassen (u. a. Kleriker-Unterdomänen), Talente, Ausrüstung, Prestigeklassen, Magische
  Gegenstände, Neue Regeln. Treffer daraus sind mit „EXP“ markiert; `buch`/`--buch` grenzt ein.
- **Monsterhandbuch:** alle Monster mit vollständigem Werteblock (Typ `monster`, Tabelle `monster` mit Name, HG,
  EP, Art), Allgemeine Monsterregeln (Blickangriff, Ergreifen, Regeneration …), Kreaturenarten und Unterarten
  (z. B. Schwarm, Untote), Monster-Talente, Monster erschaffen/verbessern, Monster als SC/Gefolgsleute/Tiergefährten,
  Begegnungstabellen. Markierung „MHB“. Schnellabfrage: MCP `monster_info` (name | hg, art) bzw.
  `sl.py regel --monster Lehmgolem` · `sl.py regel --monster --hg 3 --art Untoter`. Fallen aus dem Grundregelwerk
  haben den Typ `falle`. Monsterhandbuch II–V sind (noch) nicht enthalten.
- Weitere Bücher: Eintrag in `regeln_abruf.BUECHER` (+ Kürzel in `regeln_db.BUCH_KURZ`), dann `python regeln_abruf.py aufbauen`.

- Dateien (in `bereiche/wissen/`): `regeln_md.py` (HTML → Markdown), `regeln_abruf.py` (Abruf mit 1 s Pause, Cache
  `regeln/cache/`, ETag, Aufbau; Kommandozeile `python regeln_abruf.py` im Programmordner), `regeln_db.py` (Index, Suche, Textausgaben). Lesbare Kopie: `regeln/md/<Buch>/<Seite>.md` (mit Kopfdaten).
- Einträge entlang der Überschriften; lange Abschnitte zusätzlich an fett gesetzten Stichworten geteilt (jedes Talent,
  jede Fertigkeit, jeder Zustand, jedes Klassenmerkmal ein Eintrag). Tabellen `talente`, `zustaende`, `fertigkeiten`.
- Suche: SQLite FTS5 über deutsch gestemmten Text (Snowball, Umlaute/ß normalisiert, Präfixsuche) + Trigramm-Index über
  Titel + Synonymliste (GA, RK, KMB, KMV, TP, SG, GAB/BAB, RW, ZR, SR, englische Begriffe …) in `regeln_db.SYNONYME`.
  Zaubernamen in der Frage werden erkannt und auf `zauber_info` verwiesen. Tabelle `vektoren` ist für eine spätere
  Vektorsuche reserviert (Abschnitts-IDs und Texte sind schon da).
- **Hausregeln:** `<Kampagne>/sl/hausregeln.md` (Vorlage `vorlage/sl/hausregeln.md`), je Regel eine Überschrift.
  Wird bei jeder Suche mit durchsucht, Treffer als `[H<n>] HAUSREGEL (hat Vorrang)` oben; `regel_lesen H<n>`.
- Befehle: `sl.py regel Gelegenheitsangriff verlassen` · `sl.py regel --lesen ID|Titel` · `sl.py regel --seite Kampf` ·
  `sl.py regel --talent Beweglichkeit` · `--zustand Hilflos` · `--fertigkeit Akrobatik` · `sl.py regel` (Stand).
  MCP: `regel_suchen`, `regel_lesen`, `talent_info`, `zustand_info`, `fertigkeit_info`.
- **Aktualisieren:** `sl.py regeln-aktualisieren` bzw. MCP `regeln_aktualisieren` (läuft im Hintergrund, erneuter Aufruf
  zeigt den Stand): ruft jede Inhaltsseite erneut ab (bedingt per ETag, wo der Server eins liefert – er tut das nur
  für Seiten in seinem 3-Stunden-Cache), vergleicht den Inhalt per Hash, folgt neuen Links und baut den Index nur
  bei Änderungen neu. Unterseiten, deren Inhalt schon im Kapitel steht (Alias), werden nicht erneut geholt.
  Dauer ca. 10–15 Minuten (ca. 300 Seiten, 1 s Pause). `--nur-index` baut nur Index/Markdown aus der Datenbank neu. Der Seiteninhalt steht in
  der Datenbank, daher funktioniert das auch ohne Cache (z. B. nach Installation aus dem ZIP). Erstaufbau ohne
  Datenbank: ca. 1900 Seiten, ca. 2,5 Stunden. Aktualisierung prüft ca. 730 Inhaltsseiten (ca. 30 Minuten).
- Im ZIP (`paket_bauen.py`): `regeln/regeln.sqlite` + `regeln/LIZENZ-REGELN.txt` (nicht `regeln/cache`, `regeln/md`).

## Lizenz und Rechtliches
- **Programmcode und Dokumentation:** MIT-Lizenz (siehe [LICENSE](LICENSE)), © 2026 TheDancingElephant.
  Ausgenommen sind die OGL-Dateien unten.
- **Spielmechanik der Zauber** (`daten/zauber.json`): von Open Game Content abgeleitet, daher ebenfalls OGL 1.0a.
- **Regel- und Zaubertexte:** Open Game Content aus dem deutschen PRD (https://prd.5footstep.de) unter der Open Game
  License 1.0a. Volltext der OGL und Abschnitt 15 (Urheberrechtsvermerke): `regeln/LIZENZ-REGELN.txt` (für
  `regeln/regeln.sqlite`) und `daten/LIZENZ-ZAUBER.txt` (für `daten/zauber_prd.json` und `daten/zauber.json`). Diese Dateien gehören zu jeder
  Weitergabe (`paket_bauen.py` erzwingt das).
- **Product Identity / Marken:** Der Spieltisch ist ein inoffizielles, kostenloses Fan-Werkzeug, *kompatibel mit dem
  Pathfinder-Rollenspiel (1. Edition)*. Pathfinder ist eine Marke von Paizo Inc., die deutsche Übersetzung stammt von
  Ulisses Spiele; das Tool ist von beiden weder veröffentlicht noch unterstützt. Eigennamen der Spielwelt (Orte,
  Gottheiten, Figuren) sind kein Open Content und gehören nicht in Code, Vorlagen oder Beispiele; Kampagnendaten
  liegen außerhalb des Repos.
- Abruf der PRD-Seiten nur mit Pause (1 s) und lokalem Cache, siehe `bereiche/wissen/regeln_abruf.py`.
