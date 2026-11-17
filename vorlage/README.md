# Kampagnenordner

Diesen Ordner hat der Spieltisch angelegt (Zentrale „+ Neue Kampagne“ oder MCP-Werkzeug `kampagne_neu`).
Programmordner: `{{SPIELTISCH}}` · Python: `{{PYTHON}}`

- `kampagne.json` – Name, Port, EP-Tempo
- `Material/` – Abenteuer-PDFs; ihr Text landet in `sl/quellen/*.txt`
- `sl/` – nur für die Spielleitung (Notizen, Karten, Quellen, SL-Schlüssel) – **Spoiler**
- `daten/` – Charaktere und Spielprotokoll
- `.mcp.json`, `.claude/launch.json` – Verbindung für den SL-Agenten (Claude) und den Server-Start; die Pfade darin
  passen zu diesem Rechner. Nach dem Verschieben des Ordners oder auf einem anderen Rechner in der Zentrale
  **„Pfade reparieren“** drücken (oder `einrichten.bat` im Programmordner erneut ausführen).
- `CLAUDE.md` / `AGENTS.md` – Leitfaden für den SL-Agenten

Server von Hand starten: `{{SPIELTISCH}}/start.bat "{{KAMPAGNE}}"` – Spieler-URL `http://localhost:<port>`.
Gespielt wird mit einer Claude-Sitzung in diesem Ordner (einmal als vertrauenswürdig bestätigen).
