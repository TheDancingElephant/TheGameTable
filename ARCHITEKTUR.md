# Architektur des Spieltischs

> Verbindliche Leitlinie für alle Änderungen am Programm. Ergänzt [README.md](README.md) (Funktionen, Befehle),
> [AGENT.md](AGENT.md) (Leitfaden für den SL-Agenten) und [STYLEGUIDE.md](STYLEGUIDE.md) (Schreibweise im Code).
> Abschnitt 12 hält fest, wie weit der Umbau gediehen ist.

## 1. Zweck und Überblick

Der Spieltisch ist eine lokale Web-App für Pathfinder-1-Runden (deutsch). Die Spieler steuern ihre SC im Browser,
der Spielleiter (meist ein KI-Agent) arbeitet über MCP-Tools oder die Kommandozeile. Ein Programmordner bedient
beliebig viele Kampagnen; jede Kampagne ist ein eigener Ordner mit `kampagne.json` und eigenem Port.

```
 Spieler-Browser   SL-Browser (?sl=…)   SL-Agent (MCP)   Kommandozeile   Zentrale (Fenster)
        │                 │                   │                │               │
        └────── web/ (ES-Module, kein Build) ─┤   mcp_server.py   sl.py      zentrale.py
                          │                   └────────┬────────┘               │
                          │                        sl_api.py  (Client-Bibliothek, Kampagnenverwaltung)
                          ▼                            ▼
                 HTTP-API  /api/…   /api/sl/… (Schlüssel X-SL)
                          │
                    server.py  ── Shell: HTTP, Sperre, Laden/Speichern, Würfel, Uhr, Sichtfilter
                          │
                    bereiche/  ── Kern: Fachregeln als Funktionen (Tisch, Kampf, Karte, Charakter,
                          │        Magie, Besitz, Wissen, Kampagne)
                          ▼
     Kampagnenordner: sl/zustand.json · daten/protokoll.jsonl · daten/charaktere/*.json · sl/karten · sl/barrieren
```

## 2. Grundsätze

1. **Der Server ist die einzige Quelle der Wahrheit.** Nur `server.py` schreibt Spielstand, Protokoll und
   Charakterdateien (unter einer Sperre). `sl.py`, MCP und Browser schicken Befehle über HTTP, sie schreiben nie
   selbst in `sl/zustand.json` oder `daten/`. Ausnahme: Kampagnenverwaltung und SL-Dateien (Notizen, Quellen,
   Karten-Rohbilder) bearbeitet `sl_api.py` direkt, weil der Server sie nicht im Speicher hält.
2. **Schichten:** HTTP-API → `sl_api.py` → `sl.py` / `mcp_server.py`. Jede neue SL-Funktion hat genau einen
   Server-Befehl, eine `sl_api`-Methode, einen `sl.py`-Befehl und ein MCP-Tool.
3. **Spieler/SL-Trennung:** Der Server filtert, was Spieler sehen (`spieler_sicht`, maskierte Kartenbilder,
   verborgene Token/Einträge, Täuschungen). Nichts Geheimes verlässt den Server ohne SL-Schlüssel (`X-SL` oder
   `?sl=`). Der Sichtfilter ist eine eigene Lesesicht, kein zweites Datenmodell.
4. **Lesbare Dateiformate:** JSON (UTF-8, `ensure_ascii=False`) und Markdown. SQLite nur als Index, der sich neu
   bauen lässt (Regeln, Zauber). Kein Binärformat für Spielstände.
5. **Abwärtskompatibel:** Alte Spielstände, Charakterdateien, Kartenformate, API-Pfade, `sl.py`-Befehle und
   MCP-Toolnamen bleiben gültig. Neue Felder sind optional und haben Standardwerte.
6. **Keine festen Pfade:** Programmordner aus `__file__`, Kampagne aus `--kampagne`, `SPIELTISCH_KAMPAGNE` oder
   Suche aufwärts (`kampagne.py`). Rechnerspezifisches (`zentrale.json`, `python-pfad.txt`, `*.lnk`) wird nie
   eingecheckt.
7. **Minimale Abhängigkeiten:** Python-Standardbibliothek plus PyMuPDF, numpy, pywebview (optional). Kein
   Web-Framework, kein Build-Schritt fürs Frontend, keine Datenbank-Server.
8. **Portabilität:** `einrichten.bat`/`einrichten.py` richten einen fremden Rechner ein, `paket_bauen.py` baut
   das Weitergabe-ZIP und prüft es auf Pfade/Namen dieses Rechners.
9. **Lizenz der Regeltexte:** PRD-Inhalte (Regeln, Zauber) sind Open Game Content und werden nur mit
   `LIZENZ-REGELN.txt` / `LIZENZ-ZAUBER.txt` (OGL 1.0a) weitergegeben.

## 3. Fachbereiche (modularer Monolith)

Ein Prozess, ein Spielstand, aber der Code ist nach **fachlichen Bereichen** geschnitten, nicht nach Technik.
Jeder Bereich ist ein Paket unter `bereiche/` mit öffentlichen Funktionen in `__init__.py`. Andere Bereiche
benutzen **nur diese** (keine Unterstrich-Namen, keine Untermodule eines fremden Bereichs).

| Bereich | Verantwortung | Daten im Spielstand | Paket |
|---|---|---|---|
| **Tisch** | Szene, Erzählung, Protokoll, SL-Status, Warten (`warte`), Handouts, Gruppennotizen, freie Würfe, Spielersicht | `szene`, `slStatus`, `letzteVerarbeitet`, `naechsteLogId`, `handouts`, `gruppennotizen`; `protokoll.jsonl` | `bereiche/tisch` |
| **Kampf** | Initiative, Runde, Zug und Aktionen, Angriff gegen RK, Kritische Treffer, Flankieren, Sturmangriff, Gelegenheitsangriff (Warnung), TP, Zustände, Tod | `initiative`, `zug`, `angriffAusserhalb`; Token-Felder `tp`, `zustaende` | `bereiche/kampf` |
| **Karte** | Karten, Raster, Token, Bewegung und Wege, Barrieren (Wände/Türen), Nebel, Sicht, geteilte Sicht, Täuschungen/Illusionen, Kartenimport/-export | `karten`, `karteAktiv`, `tokens`, `taeuschungAus`; `sl/barrieren/*.json`, `sl/karten/*` | `bereiche/karte` |
| **Charakter** | Werte, Attributsmodifikatoren, Fertigkeiten, Modi (Buffs), wirksame Werte, EP, Stufenaufstieg | `daten/charaktere/*.json`; Token-`modi` | `bereiche/charakter` |
| **Magie** | Zauberplätze, Zauberpools (z. B. Barde), spontanes Zaubern, Domänen, Vorbereiten, Zauberbuch, Zauber wirken, Klassenfähigkeiten | Charakterfelder `zauberliste`, `zauberpools`, `zauberbuch`, `faehigkeitenListe` | `bereiche/magie` |
| **Besitz** | Gruppenkasse, Gegenstände, Beute, Träger/Ort | `ausruestung` | `bereiche/besitz` |
| **Wissen** | Regeldatenbank (PRD), Zauberkatalog (PRD + Mechanik), Hausregeln; **nur lesend** | `regeln/`, `daten/zauber*.json`, `sl/hausregeln.md` | `bereiche/wissen` |
| **Kampagne** | Kampagnenordner, Pfade, Vorlage, neue Kampagne, Pfadreparatur, Zentrale | `kampagne.json`, `.mcp.json`, `.claude/` | `bereiche/kampagne` |

Abhängigkeiten zwischen Bereichen laufen nur in eine Richtung:

```
            Magie ──► Kampf ──► Karte
              │         │         │
Tisch ──►     └─────────┴─────────┴──► Charakter ──► Wissen
  │  (Sichten: Kampf, Karte, Besitz)
  └──► Besitz                       Kampagne: von der Shell genutzt, nutzt keinen Bereich
```

Magie nutzt Kampf (Angriffswurf, Rettungswurf), Kampf nutzt Karte (Abstand, Sichtbarkeit, Wege), alle drei
nutzen Charakter (wirksame Werte), Charakter und Magie nutzen Wissen (Zauberkatalog).

Gemeinsame Kleinteile (Fehlerklasse `Fehler`, Würfelausdrücke, `Kontext`) liegen in `bereiche/kern.py`.
Rückwirkungen gegen die Pfeilrichtung (z. B. „Token bewegt → Nebel aufdecken“, „Runde vorbei → Modi laufen ab“)
gehen nicht über Importe, sondern über **Domänenereignisse** (Abschnitt 5).

## 4. Functional Core, Imperative Shell

**Kern (`bereiche/`)**: Fachregeln als Funktionen. Eingabe: der `Kontext` eines Befehls und die Befehlsdaten;
Ausgabe: Antwort-Dict. Unterwegs verändern sie **nur** die Daten im Kontext und melden Ereignisse.
Sie lesen und schreiben keine Dateien, kennen keine Uhrzeit, keinen globalen Zustand und würfeln nur über
`kx.w` (der Würfel des Kontexts). Damit lassen sie sich mit festen Würfelergebnissen testen.

**Shell (`server.py`)**: alles mit Nebenwirkungen. Ablauf eines Befehls:

```
HTTP-Anfrage ─► Sperre ─► Sicherung des Spielstands (pickle) ─► Kontext bauen
   (z, Charaktere der Kampagne, Einstellungen, Karten-Ressourcen, Würfel=random, Uhr=time)
 ─► Befehl im Kern ─► Ereignisse ─► Reaktionen anderer Bereiche (gleiche Sperre, gleicher Befehl)
 ─► Invarianten (z. B. Gegner mit TP ≤ 0 sind „Tot“)
 ─► Erfolg: Protokolleinträge anhängen, geänderte Charaktere und Spielstand speichern, Version +1, Wecken
 ─► Fehler: Spielstand aus der Sicherung zurück, nichts geschrieben, Meldung 400 an den Aufrufer
```

`sl_api.py`, `sl.py`, `mcp_server.py` und das Frontend sind ebenfalls Shell (Ein-/Ausgabe, Darstellung) und
enthalten keine Spielregeln. Was das Frontend vorab prüft (z. B. Reichweite im Angriffsmenü), ist nur Komfort;
die verbindliche Prüfung macht der Server.

**Karten-Ressourcen** (Kartenbild, Wandraster, Barrieren-Dateien, Aufdeck-Maske) sind teuer zu laden und werden
in der Shell zwischengespeichert. Der Kern bekommt sie über die Schnittstelle `kx.res` (`bild`, `wand`, `barr`,
`barr_speichern`, `maske`, `maske_sichern`); Tests setzen eine einfache Fälschung ein.

**Daten statt Klassenhierarchien:** Charaktere, Token, Modi, Zauber, Barrieren sind Dicts in dem Format, das auch
in den Dateien steht. Regeln stecken in Funktionen und Tabellen (z. B. `MODI.VORLAGEN`: Hast, Rindenhaut … als
Datensätze), nicht in Unterklassen. Klassen nur für technische Hüllen (`Kontext`, HTTP-Handler, Caches).

## 5. Domänenereignisse

Zwei Arten von Ereignissen, beide als Dicts:

- **Protokolleinträge** (`kx.protokoll(art, text, **extra)`): was am Tisch sichtbar wird bzw. für den SL im
  Protokoll steht (`daten/protokoll.jsonl`, Format unverändert). Felder `id` und `zeit` vergibt der Kontext
  (aus `naechsteLogId` und der Uhr der Shell). `wecken=True` weckt `warte`; `verborgen=True` nur für den SL.
- **Fachereignisse** (`kx.ereignis(name, **daten)`): interne Signale zwischen Bereichen. Sie werden nicht
  gespeichert (kein Event Sourcing); die Shell reicht sie sofort an die eingetragenen Reaktionen weiter.

| Ereignis | ausgelöst von | Reaktion |
|---|---|---|
| `token_bewegt` (token) | Karte (Bewegen, Sturmangriff) | Karte: Auto-Nebel/Sicht aufdecken |
| `tuer_geschaltet` (karte) | Karte (Tür) | Karte: Sicht neu, falls Auto-Nebel |
| `runde_vorbei` (runden) | Kampf (Initiative weiter) | Charakter: Modi laufen ab |
| `zeit_vergeht` (runden) | Magie (Rast), SL (`modus_zeit`) | Charakter: Modi laufen ab |
| `tp_geaendert` (token) | Kampf, Magie | Charakter: TP in die Charakterdatei übernehmen |

Reaktionen werden in `bereiche/__init__.py` verdrahtet (eine Liste je Ereignis). Ein Bereich, der ein Ereignis
auslöst, weiß nicht, wer reagiert.

## 6. Dateiformate (Kampagnenordner)

| Datei | Inhalt | Schreibt |
|---|---|---|
| `kampagne.json` | Name, Port, `epTempo`, `autoNebel`, `modi` | Zentrale/`kampagne_neu`, Nutzer |
| `sl/zustand.json` | Spielstand (Szene, Karten mit Nebel, Token, Initiative, Zug, Ausrüstung, Handouts …) | nur Server |
| `daten/protokoll.jsonl` | Protokoll, ein JSON-Objekt je Zeile, Felder `id zeit art text …` | nur Server |
| `daten/charaktere/<id>.json` | Charakterbogen (Basiswerte; Modi als Liste `modi`, wirksame Werte nie gespeichert) | nur Server |
| `sl/barrieren/<karte>.json` | Wände, Türen, Fenster, Löschbereiche (Pixelkoordinaten) | nur Server |
| `sl/karten/*` | Kartenbilder | `sl_api` (`karte_neu`) |
| `sl/notizen/*.md`, `sl/quellen/*` | SL-Notizen, Abenteuertexte | `sl_api` |
| `sl/hausregeln.md` | Hausregeln (eine Überschrift je Regel) | Nutzer |
| `sl/schluessel.txt` | SL-Schlüssel | Server (beim ersten Start) |

Neue Felder: optional, mit Standardwert beim Lesen; nie ein bestehendes Feld umdeuten. Abgeleitete Werte
(`_d`, `_ep`, `_wirkung`, `_basis` …) beginnen mit Unterstrich und werden nie gespeichert.

## 7. Spieler/SL-Trennung im Detail

- `/api/stand` ohne Schlüssel = Spielersicht: nur Token auf aufgedeckten Feldern, keine Gegner-TP (nur
  Gesundheitstext), verborgene Initiative-Einträge als „???“, keine verborgenen Protokolleinträge, Täuschungen
  statt echter Gestalt.
- `/api/karte/<id>.jpg` maskiert serverseitig (Nebel als Pixelmaske), ganze Karte nur mit Schlüssel.
- `/api/sl/*` verlangt den Schlüssel. Der SL-Agent bekommt Spoiler nur über MCP-Tools, nie über den Browser.

## 8. Tests

- `tests/` mit `unittest` (Standardbibliothek). Aufruf im Programmordner: `python -m unittest` oder `tests.bat`.
- Kern-Tests rufen Funktionen der Bereiche mit festem Würfel auf. Ablauf-Tests starten den echten Server mit
  einer Testkampagne in einem Temp-Ordner auf einem freien Port und sprechen ihn über `sl_api` bzw. HTTP an.
- Alte Spielstände: `tests/test_altstaende.py` lädt, falls vorhanden, Kopien echter Kampagnen (nur lokal,
  Umgebungsvariable `SPIELTISCH_ALTSTAENDE`, nie eingecheckt) und prüft, dass Stand und Sichten sich bauen lassen.
- **Pflicht:** Alle Tests grün vor jedem Commit, der Verhalten ändert, und vor jeder Live-Übernahme.

## 9. Entwicklungsablauf

1. Vor Änderungen am Tool den Nutzer fragen (gemeinsam genutzt von allen Kampagnen).
2. Arbeiten in einer Arbeitskopie (Git-Klon) mit eigener Testkampagne und eigenem Port; Live-Server nie stören.
3. Eine neue Funktion ist erst fertig, wenn sie vollständig ist: Server-Befehl, `sl_api`, `sl.py`, MCP-Tool,
   README/AGENT/Vorlagen, Paket (`paket_bauen.py`), Tests, Test mit echtem Durchlauf.
4. Kleine, thematische Commits (deutsch). Git ersetzt die früheren `_sicherung-*`-Ordner.
5. Live-Übernahme nur nach OK des Nutzers, mit grünen Tests und einem Git-Stand als Rücksicherung; laufende
   Server/MCP-Sitzungen danach neu starten, wenn `server.py` bzw. `sl_api`/`mcp_server` betroffen sind.

## 10. Bewusst nicht

Kein volles DDD (keine Aggregate-/Repository-Klassen), keine Microservices, kein CQRS (die Spielersicht ist ein
Filter, kein eigenes Modell), kein Event Sourcing (der Spielstand ist die Wahrheit, das Protokoll ist Erzählung),
keine Klassenhierarchien für Regeln, kein Web-Framework, kein Frontend-Build, keine Vektorsuche, kein
eingebettetes Python.

## 11. Entscheidungen

| Datum | Entscheidung |
|---|---|
| 2026-11 | Ein Programmordner für alle Kampagnen; Kampagnen in eigenen Ordnern mit eigenem Port |
| 2026-11 | Nebel als Sichtpolygon mit Wanderkennung (`nebelModus: sicht`), Feldraster bleibt möglich |
| 2026-11 | Der SL-Agent arbeitet nur über MCP (keine Dateizugriffe im Kampagnenordner) |
| 2026-11 | Regeln als SQLite-FTS5 mit deutschem Stemmer, ohne Vektorsuche |
| 2026-11 | Kein eingebettetes Python im Paket; `einrichten.bat` sucht/installiert Python |
| 2026-11-17 | Git (GitHub `TheGameTable`) statt Sicherungsordner; Umbau zum modularen Monolithen nach Fachbereichen mit Functional Core / Imperative Shell |

## 12. Stand des Umbaus

| Schritt | Stand |
|---|---|
| Git, `.gitignore`, Ausgangsstand | erledigt |
| ARCHITEKTUR.md, STYLEGUIDE.md | erledigt |
| Testsammlung `tests/` (61 Tests, ~80 s) | erledigt |
| Shell: Kontext, Sicherung je Befehl, Charakterspeicher | offen |
| Kampf + Modi | offen |
| Karte | offen |
| Magie | offen |
| Charakter | offen |
| Besitz | offen |
| Tisch | offen |
| Wissen, Kampagne (Module verschieben) | offen |
| Frontend `web/` in ES-Module | offen |

## 13. Glossar (PRD-Begriff = Name im Code)

Fachbegriffe folgen dem deutschen PRD (https://prd.5footstep.de). Im Code steht der deutsche Begriff ohne Umlaute
(`ae oe ue ss`), Abkürzungen wie im Regelwerk. Wo ältere Namen abweichen, bleiben sie wegen der Dateiformate.

| PRD-Begriff | Code | Anmerkung |
|---|---|---|
| Spielleiter (SL) | `sl` | |
| Spielercharakter (SC) | `sc`, Token-Art `sc` | Token-ID `sc-<charId>` |
| Nichtspielercharakter (NSC) | `nsc` | |
| Gegner | `gegner` | |
| Token, Spielfigur | `token`, `t` | auch Objekte (`objekt`) |
| Feld (1,5 m) | `feld`, `x y` | `meterProFeld` je Karte |
| Rüstungsklasse (RK) | `rk` | SC: `rk.normal`, `rk.beruehrung`, `rk.adff`; Token: `rk`, `rkBeruehrung`, `rkAdff` |
| Berührungsangriff | `beruehrung` | |
| auf dem falschen Fuß | `adff` | Zustand „Auf dem falschen Fuß“ |
| Trefferpunkte (TP) | `tp`, `tpMax` | Charakter: `tp.max`, `tp.aktuell` |
| Trefferwürfel (TW) | `tw` | |
| Grundangriffsbonus (GAB) | `gab` | |
| Kampfmanöverbonus/-verteidigung | `kmb`, `kmv` | |
| Rettungswurf: Reflex, Wille, Zähigkeit | `rw.REF`, `rw.WIL`, `rw.ZAEH`; Token `ref wil zaeh` | |
| Attribute ST GE KO IN WE CH | `attribute.ST` … | Modifikator `attr_mod` |
| Initiative | `ini`, `initiative` | Phasen `wuerfeln`, `laeuft` |
| Runde, Zug | `runde`, `zug` | |
| Standard-, Bewegungs-, Schnelle Aktion | `standard`, `bewegung`, `schnell` | volle Aktion = Standard + Bewegung |
| 1,5-m-Schritt | (1 Feld ohne Bewegungsaktion) | `bewegungsbedarf` |
| Voller Angriff | `serie` | Liste der Angriffsboni |
| Gelegenheitsangriff (GA) | `gelegenheitsangriff` | Tool warnt nur |
| bedrohtes Feld, Reichweite | `reichweite` (Felder) | |
| Flankieren | `flankiert` | +2 |
| Sturmangriff | `sturmangriff` | +2 Angriff, −2 RK |
| Kritischer Treffer: Bedrohungsbereich, Multiplikator | `krit` („19-20/x2“), `bereich`, `mult` | |
| Schwierigkeitsgrad (SG) | `sg` | |
| Zustand | `zustaende` (Liste von Namen) | Namen wie im PRD, `ZUSTAENDE` |
| Herausforderungsgrad (HG) | `hg` | |
| Erfahrungspunkte (EP) | `ep` | `epTempo` langsam/mittel/schnell |
| Stufe, Stufenaufstieg | `stufe`, `aufstieg` | |
| Fertigkeit | `fertigkeiten` | |
| Talent | `talente` | |
| Größenkategorie | `groesse` (Modi: Stufen), `GROESSEN` | Token: `groesse` = Kantenlänge in Feldern |
| Bewegungsrate | `bewegung` (m), `tempo` (Felder) | |
| Dunkelsicht, Sichtweite | `sicht`, `sichtFelder` | |
| Zaubergrad | `grad` | |
| Zauberstufe | `zauberstufe` | |
| Zauberplatz | `proTag`, `verbraucht` | je Eintrag der `zauberliste` |
| Zauber pro Tag eines Pools (z. B. Barde, Hexenmeister) | `zauberpools.<name>.max/verbraucht`, Eintrag `pool` | |
| spontanes Zaubern | `spontan` | |
| Domänenzauber | `domaene` | |
| Zauberbuch | `zauberbuch` | |
| Zauber vorbereiten | `vorbereiten` | |
| Klassenmerkmal / Fähigkeit | `faehigkeitenListe` | Aktionen im Kampf |
| Modus (zeitlich begrenzte Wirkung, „Buff“) | `modi`, `wirkung`, `rest` (Runden) | Vorlagen in `MODI.VORLAGEN` |
| Ausweichbonus | Wirkung `rk` | z. B. Hast |
| natürliche Rüstung / Rüstungsbonus | Wirkung `rkr` | z. B. Rindenhaut |
| Gruppenkasse | `ausruestung.kasse` | Münzen `kp sp gp pp` (= KM SM GM PM; alte Namen bleiben) |
| Gegenstand, Beute | `ausruestung.gegenstaende`, `beute` | `traeger`, `ort` |
| Szene | `szene` | |
| Handout (Unterlage) | `handouts`, `unterlagen` | |
| Nebel (des Krieges) | `aufgedeckt`, `nebelMaske`, `nebelModus` | |
| Barriere: Wand, Tür, Geheimtür, Fenster | `barrieren`, `typ` | |
| Täuschung (Illusionsansicht) | `taeuschung` | je SC eigene Ansicht |
| geteilte Sicht | `sichtVon` | |
| Spielstand | `z` (`sl/zustand.json`) | |
| Kontext eines Befehls | `kx` (`bereiche.kern.Kontext`) | technischer Begriff |
