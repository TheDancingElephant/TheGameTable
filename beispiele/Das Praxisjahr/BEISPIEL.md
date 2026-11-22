# Beispielkampagne „Das Praxisjahr“

Selbst geschriebene PF1-Kampagne in den Grovari-Höhlen (Finsterlande): Wehrpflichtige im Praxisjahr, sechs spielfertige Abenteuer bis zum Finale für Stufe 1–5. Mit vier Test-SC, Startszene in Torstadt und fünf Einsatzkarten mit exakten Wänden (vier davon mit Sichtnebel).

## Anlegen
Zentrale → „+ Neue Kampagne“ → Feld „Beispiel“, oder MCP-Werkzeug `kampagne_neu` mit `beispiel: "Das Praxisjahr"`
(Kommandozeile: `sl_api.kampagne_neu(wurzel, "", beispiel="Das Praxisjahr")`). Die neue Kampagne bekommt einen freien
Port, `.mcp.json`, `CLAUDE.md`/`AGENTS.md` (mit den Kampagnenregeln aus `kampagnenregeln.md`) und eine Kopie dieses
Ordners ohne Spielstand-Reste. Danach Server starten und mit einer Claude-Sitzung im neuen Ordner spielen.

## Inhalt
- `sl/quellen/` – Kampagnenbuch, Abenteuer 1–6, NSC-Werte, Umgebung, Wirtschaft/Völker, Städte (Markdown als .txt)
- `sl/notizen/kapitel1.md` – SL-Notizen mit Kartenübersicht, Koordinaten der Bereiche, SG, Gegnern, „Laufende Notizen“
- `sl/hausregeln.md` – Munavri als Spielervolk, Bonus-Wesenszug, Meilenstein-Aufstieg, Ehrenmarken
- `sl/karten/`, `sl/barrieren/`, `sl/zustand.json` – Startzustand: Karten `torstadt` (aktiv), `zisternen`, `wachhaus`,
  `runenwerkstatt`, `gefangenenlager`, `torhaus`, `grovaristadt`, `hoehlen`, `tiefenburg`, `illiatist`; Unterlagen;
  Gegner in den Zisternen verborgen
- `daten/charaktere/` – vier Test-SC der Stufe 1 (Duergar-Kämpfer, Svirfneblin-Druidin, Munavri-Magier, Rattenvolk-Schurke)
- `Material/` – Original-Karten (SVG, mit Raumnummern: nur für die SL), Kartenquellen im Spieltisch-Kartenformat,
  Handout-Texte, Bauskripte

## Pflege (Entwickler)
- Kartenbilder neu bauen: `python Material/karten/karten_bauen.py <Quellordner mit Kampagne/*.svg und Karte2.png …> <dieser Ordner>`
- Startzustand neu aufbauen: `python Material/aufbauen.py <Arbeitsordner> [--port 8799]` (startet einen Testserver auf
  dem Port, importiert Karten, setzt Unterlagen/Gegner/Startszene und schreibt `sl/zustand.json`, `sl/karten/`,
  `sl/barrieren/` hierher zurück).
- Test: `tests/test_beispiele.py` prüft Notizen, Karten, Startzustand und den Spoilerschutz der Spieleransicht.

## Rechtliches
Kampagnentext und Karten: eigenes Werk des Autors, mit Erlaubnis im Repo. Die Kampagne spielt in Golarion und nutzt
Begriffe und Namen von Paizo Inc. (z. B. Finsterlande, Sekamina, Orv, Munavri, Svirfneblin, Nivi Rhombodazzle). Sie ist
inoffizielles Fan-Material im Sinne der Paizo Community Use Policy, nicht von Paizo veröffentlicht oder unterstützt;
Pathfinder und Golarion sind Marken von Paizo Inc. Die Regelwerte folgen dem PRD (OGL, siehe `regeln/LIZENZ-REGELN.txt`).
