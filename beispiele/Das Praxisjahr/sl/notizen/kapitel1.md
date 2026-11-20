# Das Praxisjahr – SL-Notizen

> Beispielkampagne des Spieltischs. Abenteuertexte in `sl/quellen/` (Markdown als .txt), Hausregeln in
> `sl/hausregeln.md`. Diese Notiz bündelt, was am Tisch schnell gebraucht wird: Karten, Koordinaten, SG, Gegner als
> fertige `token_neu`-Angaben. Unten **„Laufende Notizen“** = aktueller Stand.

## Überblick (Spoiler, nur SL)
- SC = Wehrpflichtige im 4. Jahr (Praxisjahr), Truppe von **Hauptfeldwebelin Brakka Steinfaust** (Duergar). Jahr 170 n. B.
- Roter Faden: **Erzmagistra Oriel Vanthe** (Munavri, Pfeilerwacht, Ethikrat) ist von **Fürst Casimir Drevan** (Vampir,
  Varikanum) beherrscht. Sie lässt **Gegenanker** (schwarze Runensteine) an die Zentralpfeiler setzen, um den Großen
  Steinwall von Torstadt beim Angriff der Untotenarmee einstürzen zu lassen. Falsche Spuren: erst die Drow, dann
  **Obermagister Bastrin Kieselgrund** (Schmuggler, kein Verräter). Hinweiskette: Kampagnenbuch 3.2 (`suchen` „Hinweiskette“).
- Abenteuer: 1 Ratten unter dem Wall (Torstadt, St. 1) · 2 Geleit nach Grovaristadt (St. 2) · 3 Der Schatten über dem
  Hochsee (Illiatist, St. 2–3) · 4 Feuer aus der Tiefe (Skizze) · Zwischenspiel Das Abkommen (Skizze) · 5 Bastion der
  Lebenden (Skizze) · 6 + Finale Die fünf Säulen (Skizze).
- Meilenstein-Aufstieg (Hausregel), keine EP. Ehrenmarken zählen (3 = „herausragend“).

## Quellen
| Datei | Inhalt |
|---|---|
| `00_Kampagnenbuch_Das_Praxisjahr.txt` | Eckdaten, Welt, Verschwörung, alle Abenteuer (4–6 als Skizze), Zufallsbegegnungen W12, NSC-Liste |
| `01_Spielerhandout.txt` | Spielerwissen (liegt als Unterlage „Willkommen in den Grovari-Höhlen“ am Tisch) |
| `02_Abenteuer1_Ratten_unter_dem_Wall.txt` | Abenteuer 1 vollständig, Werte Ratten |
| `03_NSC_Werte.txt` | Werteblöcke Brakka, Seren, Kell, Ilvrae, Bleicher Hund, Vanthe, Bastrin … |
| `04_Abenteuer2_Geleit_nach_Grovaristadt.txt` | Abenteuer 2 vollständig |
| `05_Umgebung_der_Hoehlen.txt` · `06_…` · `07_Staedte_der_Enklave.txt` | Regionen, Wirtschaft/Völker, Städte mit Ortslisten zu den Stadtplänen |
| `08_Abenteuer3_Der_Schatten_ueber_dem_Hochsee.txt` | Abenteuer 3 vollständig |

## Karten
| ID | Karte | Einrichtung |
|---|---|---|
| `torstadt` | Stadtplan Torstadt (1 Feld = 40 m), Ziffern = Orte aus `07_…` (Torstadt/Orte) | ohne Nebel, Start-Karte, bekannt mit Legende `orte-torstadt` |
| `zisternen` | Abenteuer 1, 1 Feld = 1,5 m | exakte Wände (Import), Sichtnebel, Auto-Nebel; Ratten verborgen gesetzt |
| `wachhaus` | Abenteuer 3, Wachhaus am Hochsee, 1 Feld = 1,5 m | exakte Wände (Import), Sichtnebel, Auto-Nebel |
| `grovaristadt` | Stadtplan Grovaristadt (1 Feld = 40 m) | ohne Nebel, bekannt mit Legende `orte-grovaristadt` |
| `hoehlen` | Übersichtskarte der Grovari-Höhlen | ohne Nebel, bekannt (Spielerwissen) |
| `tiefenburg`, `illiatist` | Stadtpläne (Bilder); Legenden in `04_…` bzw. `07_…` | ohne Nebel, noch nicht bekannt |

Originale (mit Raumnummern, nur SL): `Material/*.svg`. Kartenquellen für einen Neu-Import: `Material/karten/*.karte.json`
(`karte_import` mit `datei`), Bauskript `Material/karten/karten_bauen.py`.

## Abenteuer 1 – Ratten unter dem Wall
**Ablauf:** Szene 1 Kaserne (Brakka, Rivale Seren Halvaris) → Szene 2 Quartiermeisterin Pipra Zwirn (Ausrüstung,
Alchemistenfeuer bei Diplomatie/WE SG 10) → Szene 3 Wasserwerk (Vorarbeiter Dorrin Kalkbart; Auftrag mit Bastrins
Unterschrift = falsche Spur) → Szene 4 Zisternen → Szene 5 Brakka nimmt den Stein (verschwindet später).
Orte auf `torstadt`: Kaserne 3, Quartiermeisterei 4, Mauer der Namen 5, Wasserwerk 6, Kanzlei der Pfeilerwacht 7,
Hospiz 8, Taverne 12.

**Kartenwechsel in die Zisternen:** `karte_aktivieren` zisternen, dann `sc_platzieren` grimbar 11 1, nissa 12 1,
ilvaen 13 1, zikko 12 2, dann `sicht`. (Alternativ `karte_einrichten` nur mit `sc`, ohne Barrieren-Erkennung.)

**Bereiche (Felder x, y; Karte `zisternen`):**
| Nr. | Bereich | Felder | Kurz |
|---|---|---|---|
| 1 | Einstiegsschacht (Wendeltreppe 9 m) | x 11–13, y 1–3; Treppenfuß x 12, y 4–5 | Akrobatik SG 8 oder 1W3 nichttödlich + Lärm (Ratten in 2 gewarnt); zerbissene Laterne (Tamlas) |
| 2 | Pumpenkammer (HG 1) | x 8–16, y 6–11; Pumpe x 12–13, y 8–9 | 3 Schreckensratten auf Rohren, greifen in Raummitte an; Hebel: Mechanismus ausschalten SG 12 / ST SG 14 → in 10 min Wasser −1 m |
| – | Gang West / Ost | West x 3–7, y 8; Ost x 17–21, y 8 | |
| 3 | Überlaufbecken | Sims x 0–6, y 9; tiefes Wasser x 0–6, y 10–16 | tote, bereifte Ratten: Heilkunde/Wissen (Natur) SG 12, Wissen (Religion) SG 15 = Nekromantie (Hinweis 1); Gedenktafel Tamrin Kalkbart (Geschichte/Lokales SG 10) |
| – | gefluteter Durchgang | x 3, y 17–19 | 6 m tauchen: Schwimmen SG 10, Luft anhalten KO×2 Runden; Pumpe läuft: hüfthoch |
| 4 | Geräteraum | x 22–26, y 6–10; Tür `t-geraete` bei (22, 8) | Tamla Grünschiefer (26, 9), fiebrig; Lampenöl, Fischernetz, Spikestiefel |
| 5 | enger Schacht (HG 2) | x 12, y 12–19 | Mittelgroße gequetscht (−4 Angriff/RK, halbe Bewegung); Rattenschwarm (12, 15); Pfeilerwacht-Stoffstreifen (Lokales SG 10, Hinweis 2) |
| 6 | Hauptzisterne | x 2–19, y 20–29; Kanal x 14–15; Steg (14–15, 25) | Steg Akrobatik SG 10 (um 5 verfehlt: Lärm); Kreide an Säule (18, 23): Wahrnehmung SG 12, Wissen (Arkanes) SG 15 (Hinweis 3) |
| 7 | Pfeilerfundament (HG 2) | x 20–27, y 21–29; Nest x 22–25, y 24–26 | Rattenmutter (24, 25) + 2 Schreckensratten; Stein entfernen = Bewegungsaktion daneben, provoziert GA; Runen-Flackern Wahrnehmung SG 15 |

**Allgemein:** völlige Dunkelheit; Wände Klettern SG 20; Rennen/Sturmangriff Akrobatik SG 10 sonst liegend; flaches Wasser
= schwieriges Gelände; tiefes Wasser Schwimmen SG 10; Flussrauschen −2 auf Hören; jeder Biss: Schmutzfieber.

**Gegner (verborgen gesetzt; sonst so anlegen):**
- `token_neu` gegner „Schreckensratte“ 9 7 id rat1 tp 5 rk 14 rkb 14 rkf 11 ref 5 wil 1 zaeh 3 hg 1/3 symbol R verborgen
- `token_neu` gegner „Schreckensratte“ 15 7 id rat2 … · „Schreckensratte“ 14 10 id rat3 … (gleiche Werte)
- `token_neu` gegner „Rattenschwarm“ 12 15 id schwarm tp 16 rk 14 rkb 14 rkf 12 ref 5 wil 2 zaeh 4 hg 2 symbol S verborgen
- `token_neu` gegner „Rattenmutter“ 24 25 id mutter tp 18 rk 15 rkb 12 rkf 13 ref 5 wil 1 zaeh 6 hg 1 symbol M verborgen
- `token_neu` gegner „Schreckensratte“ 22 23 id rat4 … · „Schreckensratte“ 23 27 id rat5 … (gleiche Werte wie rat1)
- `token_neu` nsc „Tamla Grünschiefer“ 26 9 id tamla tp 6 symbol T verborgen (aktuell 2 TP: `tp` tamla −4 beim Aufdecken)

**Angriffe:** Schreckensratte Biss +1, 1W4 + Schmutzfieber (ZÄH SG 11). Rattenschwarm Schwarm 1W6, automatisch im eigenen
Feld, + Schmutzfieber (SG 12) und Ablenkung (ZÄH SG 12 oder 1 Runde übelkeitserregt); halber Schaden durch Hieb/Stich,
+50 % durch Flächen. Rattenmutter Biss +3, 1W6+3 + Schmutzfieber (SG 14); *Kalte Kraft* im Nest: Schnelle Heilung 1,
+1 Kälte; Stein weg: +2 Angriff, −2 RK, jagt den Träger. Schmutzfieber: Inkubation 1W3 Tage, 1W3 GE + 1W3 KO.

**Belohnungen:** 50 GM pro Kopf (Gilde); Nest (Wahrnehmung SG 12): 63 GM, Spinell 100 GM, Trank Leichte Wunden heilen,
Trank Krankheit kurieren; Tamlas Familie: Meisterarbeits-Diebeswerkzeug oder -Dolch. Ehrenmarke, wenn Tamla vor dem
Boss sicher nach oben gebracht wird. Danach Stufe 2.

**Der schwarze Runenstein:** Magie entdecken: schwach Nekromantie + Bannmagie. Zauberkunde SG 20: umgekehrte Bannmagie,
saugt Schutz ab (Test/Prototyp). SG 25: Signatur wie eine Handschrift (Vanthes, im Finale). >1 Stunde am Körper:
WIL SG 11 oder 1 WE-Schaden + Albträume („Bald“). Härte 10, 20 TP.

## Abenteuer 3 – Wachhaus (Karte `wachhaus`)
| Bereich | Felder |
|---|---|
| Hof (1) | x 9–18, y 19–23; Tor `t-tor` (12–13, 24) zur Hafengasse (y 25–26) |
| Wachstube (2) | x 2–8, y 12–17; Tür zum Zellengang `t-wachstube-gang` (9, 13) |
| Zellengang (3) | x 9–18, y 12–14; Zellen Z1–Z4 y 15–18 (Gitter + Zellentür je Zelle `zelle-z1` … `zelle-z4`); Velrith in Z3 (15, 17); Tür Hof–Z2 `t-hof-z2` |
| Dachluke (4) | über dem Zellengang bei (17–18, 13) – Ilvraes Weg |
| Wehrturm (5) | Kreis um (22, 10.5), Tür `t-turm` im Westen; Treppe in den Keller (Keller nicht auf der Karte) |
| Turmkeller (6) | unter dem Turm; Fuge mit dem zweiten Gegenanker am Pfeilerfuß (≈ 24, 8) |
| Steg (7) | x 13, y 4–8 |
| Waffenkammer (8) | x 2–8, y 18–23; Türen zur Wachstube (5, 18) und zum Hof (9, 20.5) |

## Laufende Notizen
- **Stand:** Kampagnenbeginn. Szene „Die Kaserne“ (Abenteuer 1, Szene 1), aktive Karte `torstadt`. SC noch nicht auf
  einer Kampfkarte; Ratten und Tamla auf `zisternen` verborgen vorbereitet.
- **Gruppe (Test-SC, Stufe 1):** Grimbar Aschbart (Duergar, Kämpfer), Nissa Moosgrund (Svirfneblin, Druidin),
  Ilvaen Mondweiß (Munavri, Magier), Zikko Flinkfell (Rattenvolk, Schurke).
- **Ehrenmarken:** 0
