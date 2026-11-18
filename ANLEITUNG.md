# Spieltisch – Anleitung für Anwender

Der **Spieltisch** ist ein virtueller Spieltisch für Pathfinder 1 (deutsch). Die Spieler steuern ihre Charaktere in einer
Browser-Oberfläche (Karte, Charakterkarten, Würfel, Protokoll); die Spielleitung übernimmt **Claude** als SL-Agent.
Mehrere Kampagnen können nebeneinander bestehen und parallel laufen, jede mit eigenem Ordner und eigenem Port.

Diese Anleitung richtet sich an Spieler und an den, der den Spieltisch betreibt. Programmierkenntnisse braucht man nicht.
Weitere Dokumente: [README.md](README.md) (technische Details), [AGENT.md](AGENT.md) (Anweisungen für den SL-Agenten),
[mcp/AGENTS.md](mcp/AGENTS.md) (Spielleitung durch andere KI-Programme).

---

## 1. Installation auf einem neuen Rechner

**Was man braucht**
- Windows 10 oder 11 (Edge WebView2 ist dort vorinstalliert)
- **Python 3.12** (3.10 bis 3.13 gehen auch) – kostenlos von <https://www.python.org/downloads/windows/>
- **Claude Desktop** (oder Claude Code) mit einem Claude-Konto – für den SL-Agenten
- Internet nur bei der Einrichtung (zum Laden der Python-Pakete)

**Schritt für Schritt**
1. **Python installieren** (falls noch nicht vorhanden): Installer „Windows installer (64-bit)“ laden und starten,
   unten den Haken **„Add python.exe to PATH“** setzen, dann „Install Now“.
   Alternativ in einer Eingabeaufforderung: `winget install Python.Python.3.12`
2. **ZIP entpacken**, z. B. nach `C:\Spiele\` – es entsteht der Programmordner `C:\Spiele\Spieltisch\`.
   (Nicht nach `C:\Programme\`, dort fehlen die Schreibrechte.)
3. Im Programmordner **`einrichten.bat`** doppelklicken. Das Skript
   - sucht Python (Python-Launcher `py`, `python` im PATH, übliche Installationsorte) und meldet sich mit einem
     Download-Hinweis, falls keins da ist,
   - installiert die Pakete **PyMuPDF, numpy, pywebview**,
   - fragt nach dem **Kampagnen-Ordner** (Enter = Vorschlag `..\Kampagnen` neben dem Programmordner, also z. B.
     `C:\Spiele\Kampagnen\`) und legt ihn an,
   - legt die Verknüpfung **„Spieltisch-Zentrale“** auf dem Desktop und im Programmordner an,
   - prüft vorhandene Kampagnen im Kampagnen-Ordner und trägt dort die Pfade dieses Rechners ein.
4. **Zentrale starten** (Desktop-Verknüpfung) → „+ Neue Kampagne“ (Abschnitt 3).

`einrichten.bat` kann man jederzeit erneut ausführen – z. B. nach einem Python-Update, nach dem Verschieben des
Programmordners oder wenn man Kampagnen von einem anderen Rechner mitbringt (Kampagnenordner in den Kampagnen-Ordner
kopieren, dann `einrichten.bat` oder in der Zentrale „Pfade reparieren“).

**Ordner**

| Was | Wo (Beispiel) |
|---|---|
| Das Tool (Programm, gemeinsam für alle Kampagnen) | `C:\Spiele\Spieltisch\` (dort, wo das ZIP entpackt wurde) |
| Vorlage für neue Kampagnen | `<Programmordner>\vorlage\` |
| Die Kampagnen (je ein Ordner) | `C:\Spiele\Kampagnen\<Name>\` (bei der Einrichtung gewählt, in der Zentrale änderbar) |
| Python | wird automatisch gefunden; der gewählte Pfad steht in `<Programmordner>\python-pfad.txt` |

Fehlt später ein Python-Paket, `einrichten.bat` erneut ausführen (oder von Hand:
`python -m pip install pymupdf numpy pywebview`). Lässt sich pywebview nicht installieren (z. B. mit einem sehr neuen
Python), öffnet sich die Zentrale im Standardbrowser statt im eigenen Fenster.

**Aufbau eines Kampagnenordners**
```
<Kampagne>\
  kampagne.json      Name und Port (z. B. {"name": "Rappan Athuk", "port": 8781})
  CLAUDE.md          Leitfaden für den SL-Agenten dieser Kampagne
  .mcp.json          Verbindung des SL-Agenten zum Spieltisch (MCP) – Pfade dieses Rechners
  .claude\           launch.json (Server-Start aus Claude), optional settings.json (Datei-Sperre)
  Material\          Abenteuer-PDFs, Kartenbilder
  daten\             Charaktere (charaktere\*.json) und Protokoll – für alle sichtbar
  sl\                NUR für die Spielleitung: Spielstand, Karten, Notizen, Abenteuertexte, Schlüssel
```
Der Ordner `sl\` enthält Spoiler. Spieler sollten dort nicht hineinschauen.

---

## 2. Die Zentrale (Kampagnen verwalten)

Die **Spieltisch-Zentrale** ist das Programmfenster für alles Organisatorische.

**Starten:** Doppelklick auf **„Spieltisch-Zentrale“** auf dem Desktop (oder `Spieltisch-Zentrale.lnk` bzw.
`zentrale.bat` im Programmordner). Oben steht der Kampagnen-Ordner; „ändern“ wählt einen anderen.

Jede Kampagne erscheint als Karte mit:
- **Status**: „aus“, „läuft“ (von der Zentrale gestartet) oder „läuft (extern)“ (anders gestartet, z. B. von Claude).
- Port, Merkmale (MCP, Sperre), Anzahl Charaktere/Karten/Quellen.
- Bei laufendem Server: aktuelle Szene, SL-Status und **unbeantwortete Spieleraktionen** – so sieht man sofort, ob der
  Spielleiter noch etwas beantworten muss.
- Rote Hinweise bei doppelt vergebenem Port, Fehlern im Server-Protokoll oder veralteten Pfaden.

**Knöpfe**
| Knopf | Wirkung |
|---|---|
| Starten / Stoppen | Server der Kampagne an- bzw. ausschalten |
| Spieleransicht | Spieltisch für die Spieler in eigenem Fenster |
| SL-Ansicht | Spieltisch mit allen Informationen (Nebel, verborgene Gegner) – nur für die Spielleitung |
| Im Browser | Spieleransicht im normalen Browser öffnen |
| Ordner / Material | Kampagnenordner bzw. Material-Ordner im Explorer |
| Protokoll | Ausgaben des Servers (bei Problemen) |
| MCP einrichten | legt die Verbindung für den SL-Agenten an (siehe Abschnitt 5) |
| Pfade reparieren | schreibt `.mcp.json` und `.claude\launch.json` mit den Pfaden dieses Rechners neu (nach Verschieben des Ordners, Umzug auf einen anderen Rechner, Python-Update). Rot hervorgehoben, wenn die Kampagnenkarte „Pfade veraltet“ zeigt. |

Unten links: **„Von hier gestartete Server beim Schließen stoppen“**. Ist das an, gehen beim Schließen des
Hauptfensters alle Spielfenster zu, und die Server, die die Zentrale gestartet hat, werden beendet.

---

## 3. Neue Kampagne anlegen

1. Zentrale → **„+ Neue Kampagne“**.
2. **Name** eintragen. Ordnername und Port sind optional (der Port wird automatisch frei gewählt).
3. **Abenteuer-PDFs** mit „PDFs auswählen …“ hinzufügen. Sie werden nach `Material\` kopiert; ihr Text wird für den
   SL-Agenten nach `sl\quellen\` übernommen (mit Seitenzahlen).
4. Optional **„Datei-Sperre“**: Der SL-Agent darf dann nur über die Spieltisch-Werkzeuge arbeiten, nicht direkt in den
   Dateien lesen (Spoilerschutz, siehe Abschnitt 5).
5. **Anlegen**. Die Kampagne erscheint in der Übersicht.

Danach: Charaktere anlegen (Spieler im Reiter „Charaktere“ oder der SL-Agent importiert ausfüllbare PDF-Bögen), und
den SL-Agenten das Abenteuer vorbereiten lassen (Notizen, Karten).

---

## 4. Spielen

### Server starten und Spieler-Adresse
- Zentrale → **Starten**, dann **Spieleransicht**.
- Die Spieler-Adresse ist `http://localhost:<Port>/` (Port steht auf der Kampagnenkarte).
- **Hinweis:** Der Server ist derzeit nur auf diesem Rechner erreichbar (nicht von Tablet/Handy im Heimnetz).
- Die SL-Ansicht hat den geheimen Schlüssel in der Adresse (`?sl=…`) – nicht an Spieler weitergeben.

### Der Bildschirm
- **Oben:** Szenentitel, im Kampf die Initiativeleiste, rechts der **SL-Status**:
  - „Der Spielleiter wartet auf euch“ – ihr seid dran. **Ein Klick darauf stupst den Spielleiter an**, falls er auf etwas
    reagieren soll, ohne dass ihr eine Aktion schreibt.
  - „Gesendet – der Spielleiter liest gleich“ – eure Aktion ist angekommen.
  - „Der Spielleiter schreibt …“ – bitte warten.
- **Links:** die Karte mit Werkzeugleiste.
- **Rechts:** Reiter *Erzählung, Gruppe, Charaktere, Ausrüstung, Unterlagen*.
- **📖 Nachschlagen** (oben rechts): Regeln, Zauber und Zustände in einem eigenen Tab nachlesen (siehe unten).

### Karte
| Werkzeug | Bedienung |
|---|---|
| ✥ Bewegen | eigene Figur ziehen; leere Fläche ziehen = Karte verschieben |
| 📏 Messen | Entfernung messen (auch Umschalt + Ziehen) |
| ☝ Zeigen | auf ein Feld zeigen (auch Rechtsklick auf leeres Feld) |
| # | Raster ein/aus |
| ＋ / － / Mausrad | zoomen |
| ◎ | auf die Gruppe zentrieren |
| ⚙ | Raster nur in diesem Browser feinjustieren |

Der **Nebel des Krieges** deckt automatisch auf, was eure Figuren sehen (Sichtlinie, Wände und geschlossene Türen
blockieren, Sichtweite nach Dunkelsicht). Bereiche hinter Türen erscheinen, sobald die Tür offen ist.

### Erzählung und Aktionen (Reiter „Erzählung“)
- Im **Protokoll** stehen Erzählungen des Spielleiters, eure Aktionen und alle Würfe.
- **🔊 Erzählstimme**: Erzählungen vorlesen lassen (Stimme, Tempo, automatisch vorlesen).
- **Aktion senden**: unten „als …“ den Charakter wählen, beschreiben, was ihr tut, **„An den Spielleiter senden“**
  (oder Strg+Enter). Rechtsklick auf die Karte fügt eine Koordinate ein.
- **Würfel**: W4 bis W%, eigener Ausdruck (z. B. `2W6+3` mit „wofür?“), **Gruppenprobe** (alle würfeln dieselbe
  Fertigkeit, z. B. Wahrnehmung) und im Kampf **Gruppenprobe Initiative**.

### Charakterkarten (Reiter „Gruppe“)
Pro Charakter eine Karte:
- **Trefferpunkte**: Betrag eingeben, **−** für Schaden, **+** für Heilung.
- **Werte und Würfe**: Angriffe, Rettungswürfe usw. per Klick würfeln.
- **Probe**: Fertigkeit wählen → **Probe**.
- **Zustände**: „+ Zustand…“ (Liegend, Wankend …); anklicken zum Entfernen, **?** zeigt die Regel.
- **Zauber** und **★ Fähigkeiten** (z. B. Klassenfähigkeiten): antippen, dann bei Bedarf das Ziel auf der Karte
  anklicken. Ausgegraute Knöpfe sind gerade nicht möglich (Grund im Tooltip). Das kleine **?** im Zauberknopf
  schlägt den Zauber nach.
- **Auf Karte setzen**: Figur auf ein Feld der aktuellen Karte stellen.
- **⬆ Stufenaufstieg**: erscheint, sobald genug Erfahrung da ist (siehe unten).

### Kampf
1. Der Spielleiter ruft den Kampf aus – alle würfeln **Initiative** (Gruppenprobe Initiative oder einzeln).
2. Wer am Zug ist, sieht oben rechts die **Zugleiste** mit den Aktionen (Standard-, Bewegungs-, Schnelle Aktion).
   - **Bewegen**: Figur ziehen; das Bewegungsbudget wird mitgerechnet (grün = ohne Standardaktion erreichbar,
     gelb = nur mit Doppelbewegung).
   - **Angreifen / Zaubern**: **Rechtsklick auf den Gegner** → Angriff, Zauber oder Sturmangriff wählen. Die Rüstungsklasse
     des Gegners bleibt verborgen; Treffer und Schaden rechnet das Tool.
   - Aktion für etwas anderes nutzen (z. B. Trank): Aktionsknopf in der Zugleiste antippen und kurz beschreiben.
3. **„Zug beenden“** – dann ist der Nächste dran; die Gegner führt der Spielleiter.
Im Kampf kann nur bewegen, wer am Zug ist.

### Ausrüstung (Reiter „Ausrüstung“)
- **Gruppenkasse**: Betrag und Münzart, **Einzahlen** / **Auszahlen**, optional mit Grund.
- **Gegenstände** je Träger; neue Gegenstände unten hinzufügen (Name, Anzahl, Träger, Ort).
- **Zauberbücher** der Magier.

### Stufenaufstieg
Reicht die Erfahrung, erscheint auf der Charakterkarte **„⬆ Stufenaufstieg auf Stufe N“**. Der Assistent führt durch:
Klasse für die Stufe, Trefferpunkte (würfeln oder Durchschnitt), Bonus der bevorzugten Klasse und eure Wünsche
(Fertigkeitsränge, Talente, neue Zauber). Nach dem Absenden prüft der Spielleiter den Antrag und trägt den Rest ein
(„wartet auf die Freigabe des Spielleiters“). Gibt er ihn zurück, kann man ihn überarbeiten.

### Unterlagen (Reiter „Unterlagen“)
Bekannte **Karten** (zum Nachschauen), **Handouts** des Spielleiters und **Gruppennotizen** (werden automatisch
gespeichert und sind für alle Spieler gleich).

### Nachschlagen (📖 oben rechts)
Öffnet in einem eigenen Tab das Regelwerk (Grundregelwerk, Expertenregeln, allgemeine Monsterregeln), alle Zauber und
die Hausregeln eurer Kampagne:
- **Suchfeld**: Begriff eingeben (z. B. „Ringkampf“, „Gelegenheitsangriff verlassen“, „Hast“). Hausregeln stehen oben.
- **Bereiche**: *Alle, Regeln, Talente, Zauber, Inhalt*. *Inhalt* zeigt die Kapitel der Bücher zum Blättern.
- **Talente** und **Zauber** sind Tabellen: oben filtern (z. B. Klasse „Barde“ und Grad 1, oder Talent-Art „Kampf“),
  das Suchfeld filtert mit, ein Klick auf den Spaltenkopf sortiert (zweiter Klick: umgekehrt). Ein Klick auf eine
  Zeile zeigt den ganzen Text rechts daneben; **✕ schließen** blendet ihn wieder aus.
- Im Text sind kursive Zauber- und Zustandsnamen anklickbar; „im PRD öffnen“ führt zur Originalseite.
- Unter *Inhalt* stehen alle Monsterhandbücher zusammen als **Monster** (allgemeine Monsterregeln, Kreaturenarten …).
  Monster und ihre Werte sieht nur der Spielleiter.

---

## 5. Spielleitung mit Claude (SL-Agent)

Claude leitet das Spiel über die **Spieltisch-Werkzeuge (MCP)**: Erzählen, auf Spieleraktionen warten, Gegner führen,
Karten einrichten, Notizen pflegen. Claude antwortet am Spieltisch, im Chat gibt es nur kurze Meldungen.

### Einmal pro Kampagne einrichten
1. Zentrale → bei der Kampagne **„MCP einrichten“** (bei neu angelegten Kampagnen schon erledigt).
   Das legt `.mcp.json` im Kampagnenordner an – mit den echten Pfaden dieses Rechners (Python, Programmordner,
   Kampagnenordner). Von Hand muss man dort nichts eintragen.
2. Leitfaden prüfen: `CLAUDE.md` im Kampagnenordner. Grundlage für neue Leitfäden ist `<Programmordner>\AGENT.md`
   (kampagnenspezifische Regeln wie Hausregeln oder EP-Empfänger dort ergänzen).
3. Optional **Datei-Sperre** (`.claude\settings.json`, beim Anlegen per Haken oder nach dem Muster
   `<Programmordner>\mcp\beispiel-settings.json`):
   Claude darf dann kein Bash benutzen und keine Dateien im Kampagnenordner direkt lesen oder schreiben – nur über die
   Werkzeuge. Das schützt vor Spoilern und macht den Ablauf stabiler.

**Andere KI-Programme als Spielleiter:** Jede Kampagne kann zusätzlich eine `AGENTS.md` haben (Vorlage
`<Programmordner>\vorlage\AGENTS.md`, neue Kampagnen bekommen sie automatisch mit ihren Pfaden). Diese Datei lesen
auch andere KI-Programme (z. B. Codex, Cursor, Gemini); sie erklärt die Spielleitung modellunabhängig. Das Programm muss
den MCP-Server `spieltisch` anbinden (Befehl und Argumente stehen in der Datei) und sollte keinen direkten Dateizugriff
auf den Kampagnenordner haben.

### Sitzung starten
1. In Claude Desktop eine **neue Sitzung im Kampagnenordner** öffnen (Ordner `<Kampagnen-Ordner>\<Name>` wählen).
2. Beim ersten Mal fragt Claude, ob man dem Ordner **vertraut** – bestätigen. Erst dann werden `.mcp.json` und die
   Sperre geladen; die Werkzeuge heißen `mcp__spieltisch__…`.
3. Claude bitten, die Sitzung zu beginnen („Lass uns weiterspielen“). Claude startet bei Bedarf den Server selbst,
   liest Notizen und Protokoll ein und wartet dann auf eure Aktionen.
4. Ihr spielt in der Spieleransicht; Claude antwortet dort.

### Sitzung beenden
Claude bitten, die Sitzung zu beenden: Es hält den Stand in den Notizen fest. Danach in der Zentrale stoppen
(oder die Zentrale schließen).

---

## 6. Karten und Nebel (kurz)

Karten legt der SL-Agent an:
- aus einer **PDF-Seite** des Abenteuers (Ausschnitt, Raster wird erkannt),
- aus einer **Bilddatei**,
- aus einer **Universal-VTT-Datei** (`.dd2vtt`/`.uvtt` aus Dungeondraft, DungeonFog, Dungeon Alchemist) mit exakten Wänden,
- oder **selbst gezeichnet** im Spieltisch-Kartenformat (Räume, Türen, Durchgänge).

Wände und Türen werden erkannt bzw. übernommen; der **Sichtnebel** stoppt an Wänden und geschlossenen Türen.
In der SL-Ansicht zeigt der Knopf **▦** die erkannten Wände (magenta) und Türen (blau).
Kartenbilder mit eigenen Wänden: Dateien in `Material\` legen und dem SL-Agenten sagen, welche Karte er einrichten soll.

---

## 7. Fehlerbehebung

| Problem | Lösung |
|---|---|
| „Keine Verbindung zum Spieltisch“ | Server läuft nicht → Zentrale: Starten. Steht er auf „läuft“, Seite neu laden (F5). |
| Server startet nicht / „Port belegt“ | Ein anderer Server nutzt den Port (oft derselbe, schon gestartet, z. B. von Claude). In der Zentrale steht dann „läuft (extern)“ – einfach weiterspielen oder erst Stoppen. Bei „Port doppelt!“ in `kampagne.json` einer Kampagne einen anderen Port eintragen. |
| Server hängt / reagiert nicht | Zentrale: Stoppen, dann Starten. **Protokoll** zeigt Fehlermeldungen. |
| SL-Status bleibt auf „Der Spielleiter schreibt …“ | Der SL-Agent hat ohne Erzählung reagiert oder wurde unterbrochen. In Claude schreiben: „Setz den Status auf bereit und warte auf uns.“ |
| Claude reagiert nicht auf Aktionen | In der Claude-Sitzung nachsehen, ob es noch auf Spieler wartet (`warte`). Sonst „Warte auf die Spieler“ schreiben. Am Spieltisch den SL-Status anklicken (anstupsen). |
| Claude hat keine Spieltisch-Werkzeuge | Sitzung im richtigen Kampagnenordner? `.mcp.json` vorhanden (Zentrale: „MCP einrichten“)? Zeigt die Karte „Pfade veraltet“, **„Pfade reparieren“** drücken. Ordner als vertrauenswürdig bestätigt? Claude-Sitzung neu öffnen. |
| `einrichten.bat` meldet „Python wurde nicht gefunden“ | Python 3.12 installieren (Haken „Add python.exe to PATH“), Eingabeaufforderung/Explorer neu öffnen, `einrichten.bat` erneut starten. |
| Paketinstallation schlägt fehl | Internetverbindung prüfen; `einrichten.bat` erneut ausführen. Hinter einem Firmen-Proxy ggf. von Hand: `python -m pip install pymupdf numpy pywebview`. |
| Zentrale öffnet sich im Browser statt im Fenster | pywebview fehlt oder passt nicht zur Python-Version – funktioniert trotzdem. Für das eigene Fenster Python 3.12 verwenden und `einrichten.bat` erneut ausführen. Beenden: Browser-Tab schließen und im Task-Manager „pythonw“ beenden. |
| Programm- oder Kampagnen-Ordner verschoben | `einrichten.bat` erneut ausführen (repariert alle Kampagnen im Kampagnen-Ordner) oder in der Zentrale „Pfade reparieren“. |
| Karte/Nebel falsch | Dem SL-Agenten sagen, was nicht stimmt (z. B. „hinter der Tür im Osten sieht man durch die Wand“) – er korrigiert Wände/Türen. |
| Rote Meldung „Fehler im Protokoll“ | Zentrale → Protokoll ansehen; die letzte Fehlermeldung an den SL-Agenten oder in eine Tool-Sitzung geben. |

---

## 8. Sicherungen

Alles Wichtige steckt im Kampagnenordner:
- `sl\zustand.json` (Spielstand: Karten, Token, Nebel, Initiative), `daten\protokoll.jsonl` (Protokoll),
  `daten\charaktere\` (Charaktere), `sl\notizen\` (SL-Notizen), `sl\karten\`, `sl\barrieren\` (Wände/Türen).

**Sichern:** Server stoppen, dann den ganzen Kampagnenordner kopieren (z. B. als ZIP mit Datum). Am besten vor jeder
größeren Änderung am Tool und regelmäßig nach Spielabenden.
**Zurückspielen:** Server stoppen, Ordner durch die Sicherung ersetzen, Server starten.

Notizen, die der SL-Agent komplett neu schreibt, werden automatisch in `sl\notizen\.sicherung\` aufbewahrt.
Vor Updates am Programm den Programmordner sichern (z. B. als `_sicherung-<Datum>\` daneben oder darin).

**Auf einen anderen Rechner umziehen:** Spieltisch dort einrichten (Abschnitt 1), die Kampagnenordner in den neuen
Kampagnen-Ordner kopieren, dann `einrichten.bat` erneut ausführen oder je Kampagne „Pfade reparieren“.

---

## Anhang: Ohne Zentrale

- Server von Hand: `<Programmordner>\start.bat "<Kampagnenordner>"`
- Kommandozeile für die Spielleitung: `python <Programmordner>\sl.py --kampagne "<Kampagnenordner>" stand`
  (alle Befehle: `sl.py --help`; Beschreibung in [README.md](README.md)).
- Ein ZIP zum Weitergeben baut `python <Programmordner>\paket_bauen.py` (ohne Kampagnen, Sicherungen und persönliche
  Einstellungen).
