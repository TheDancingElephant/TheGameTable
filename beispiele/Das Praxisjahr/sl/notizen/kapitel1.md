# Das Praxisjahr – SL-Notizen

> Beispielkampagne des Spieltischs. Abenteuertexte in `sl/quellen/` (Markdown als .txt), Hausregeln in
> `sl/hausregeln.md`. Diese Notiz bündelt, was am Tisch schnell gebraucht wird: Karten, Koordinaten, SG, Gegner als
> fertige `token_neu`-Angaben. Unten **„Laufende Notizen“** = aktueller Stand.

## Überblick (Spoiler, nur SL)
- SC = Wehrpflichtige im 4. Jahr (Praxisjahr), Truppe von **Hauptfeldwebelin Brakka Steinfaust** (Duergar). Jahr 170 n. B.
- Roter Faden: **Erzmagistra Oriel Vanthe** (Munavri, Pfeilerwacht, Archum im Ethikrat) ist von **Fürst Casimir Drevan**
  (Vampir, Varikanum) beherrscht. Drevans Plan ist **„Die Spaltung“**: Er will die Enklave nicht zerstören, sondern
  unversehrt erobern, indem er die Völker gegeneinander aufbringt, bis der Bund sein Tor selbst öffnet
  (Kampagnenbuch 3.1).
  - **Lauschsteine** (schwarze Runensteine aus Lavaschmiede-Schwarzstein, Silberstaub-Tinte) stecken seit der Großen
    Pfeilerprüfung (169) in allen fünf Zentralpfeilern: Drevan **hört** durch den Pfeiler mit, der Stein strahlt eine
    **Aura der Zwietracht** aus.
  - Zwischenfälle werden je einem Volk angehängt (Silberstaub-Raub → Drow, Wehrturm → Drow, Lavaschmiede → Drow/Duergar,
    später Sonnensalz-Kugel, Dämonenpakt der Duergar).
  - Höhepunkt: Notstandsmaßnahme des Ethikrats sperrt Drow- und Duergar-Einheiten in Torstadt ein; verzweifelte Duergar
    sollen in der Nacht des Untotenangriffs das Tor öffnen.
- Falsche Spuren: erst die Drow, dann **Obermagister Bastrin Kieselgrund** (Schmuggler, kein Verräter).
  Hinweiskette: Kampagnenbuch 3.2 (`suchen` „Hinweiskette“). Fehlende Hinweise liefert ein späteres Abenteuer nach.
- Abenteuer (alle spielfertig): 1 Ratten unter dem Wall (Torstadt, St. 1) · 2 Geleit nach Grovaristadt (St. 2) ·
  3 Der Schatten über dem Hochsee (Illiatist, St. 2–3) · 4 Feuer aus der Tiefe (Drudanst, Finsterhöhlen, St. 3) ·
  Zwischenspiel Das Abkommen (nur Skizze im Kampagnenbuch) · 5 Bastion der Lebenden (St. 4) · 6 Die fünf Säulen
  (Grovaristadt → Torstadt, Finale, St. 5).
- Meilenstein-Aufstieg (Hausregel), keine EP. Ehrenmarken zählen (3 = „herausragend“).

## Quellen
| Datei | Inhalt |
|---|---|
| `00_Kampagnenbuch_Das_Praxisjahr.txt` | Eckdaten, Welt, Verschwörung (3.1 Die Spaltung), Hinweiskette, alle Abenteuer im Überblick, Zufallsbegegnungen W12, NSC-Liste |
| `01_Spielerhandout.txt` | Spielerwissen (liegt als Unterlage „Willkommen in den Grovari-Höhlen“ am Tisch) |
| `02_Abenteuer1_Ratten_unter_dem_Wall.txt` | Abenteuer 1 vollständig, Werte Ratten |
| `03_NSC_Werte.txt` | Werteblöcke Brakka, Seren, Kell, Ilvrae, Bleicher Hund, Vanthe, Bastrin … |
| `04_Abenteuer2_Geleit_nach_Grovaristadt.txt` | Abenteuer 2 vollständig |
| `05_Umgebung_der_Hoehlen.txt` · `06_…` · `07_Staedte_der_Enklave.txt` | Regionen, Wirtschaft/Völker, Städte mit Ortslisten zu den Stadtplänen |
| `08_Abenteuer3_Der_Schatten_ueber_dem_Hochsee.txt` | Abenteuer 3 vollständig |
| `09_Abenteuer4_Feuer_aus_der_Tiefe.txt` | Abenteuer 4 vollständig (Drudanst, Lavaschmiede, Bruch, Finsterhöhlen, Runenwerkstatt) |
| `10_Abenteuer5_Bastion_der_Lebenden.txt` | Abenteuer 5 vollständig (Bastion, Knochenwacht, Gefangenenlager, Flucht zum Klagebach) |
| `11_Abenteuer6_Die_fuenf_Saeulen.txt` | Finale vollständig (Grovaristadt: sechs Handlungen, Punktesystem der Notsitzung; Torstadt: Wellen-System, Aufgaben A–D, Epilog) |

## Karten
| ID | Karte | Einrichtung |
|---|---|---|
| `torstadt` | Stadtplan Torstadt (1 Feld = 40 m), Ziffern = Orte aus `07_…` (Torstadt/Orte) | ohne Nebel, Start-Karte, bekannt mit Legende `orte-torstadt` |
| `zisternen` | Abenteuer 1, 1 Feld = 1,5 m | exakte Wände (Import), Sichtnebel, Auto-Nebel; Ratten verborgen gesetzt |
| `wachhaus` | Abenteuer 3, Wachhaus am Hochsee, 1 Feld = 1,5 m | exakte Wände (Import), Sichtnebel, Auto-Nebel |
| `runenwerkstatt` | Abenteuer 4, Versteck in den Finsterhöhlen, 1 Feld = 1,5 m | exakte Wände (Höhlenumriss), Sichtnebel, Auto-Nebel |
| `gefangenenlager` | Abenteuer 5, Lager am Rand des Grauen Hofs, 1 Feld = 1,5 m | exakte Wände, Pferche als Gitter mit Gattertür, Geheimtür `spalt` (Spalt der Winzlinge), Sichtnebel, Auto-Nebel |
| `torhaus` | Abenteuer 6, Torhaus und Großer Steinwall, 1 Feld = 1,5 m | exakte Wände und Tore, **ohne Nebel** (aufgedeckt, Auto-Nebel aus: der Wall hat zwei Ebenen) |
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

**Der schwarze Runenstein (erster Lauschstein, ein Test):** Magie entdecken: schwach Nekromantie + Bannmagie.
Zauberkunde SG 20: Erkenntnismagie mit Verzauberung und etwas Nekromantie; der Stein nutzt den Pfeiler als
Resonanzkörper, er *lauscht* und gibt leise Unruhe zurück (darum die aggressiven Ratten). SG 25: Signatur wie eine
Handschrift (Vanthes, im Finale). >1 Stunde am Körper: WIL SG 11 oder 1 WE-Schaden + Albträume („Bald“). Härte 10, 20 TP.

## Abenteuer 3 – Wachhaus (Karte `wachhaus`)
| Bereich | Felder |
|---|---|
| Hof (1) | x 9–18, y 19–23; Tor `t-tor` (12–13, 24) zur Hafengasse (y 25–26) |
| Wachstube (2) | x 2–8, y 12–17; Tür zum Zellengang `t-wachstube-gang` (9, 13) |
| Zellengang (3) | x 9–18, y 12–14; Zellen Z1–Z4 y 15–18 (Gitter + Zellentür je Zelle `zelle-z1` … `zelle-z4`); Velrith in Z3 (15, 17); Tür Hof–Z2 `t-hof-z2` |
| Dachluke (4) | über dem Zellengang bei (17–18, 13) – Ilvraes Weg |
| Wehrturm (5) | Kreis um (22, 10.5), Tür `t-turm` im Westen; Treppe in den Keller (Keller nicht auf der Karte) |
| Turmkeller (6) | unter dem Turm; Fuge mit dem zweiten Lauschstein am Pfeilerfuß (≈ 24, 8) |
| Steg (7) | x 13, y 4–8 |
| Waffenkammer (8) | x 2–8, y 18–23; Türen zur Wachstube (5, 18) und zum Hof (9, 20.5) |

Gegner Szene 4 (Hof/Zellengang): `token_neu` gegner „Drow-Schläger“ 12 21 id schlaeger1 tp 5 rk 15 rkb 12 rkf 13 ref 2
wil 0 zaeh 1 hg 1/3 verborgen · „Drow-Schläger“ 14 21 id schlaeger2 (gleich) · Ilvrae Xun: Werte `03_NSC_Werte.txt` Nr. 5,
kommt über die Dachluke (17, 13).

## Abenteuer 4 – Runenwerkstatt (Karte `runenwerkstatt`)
**Allgemein:** Finsterhöhlen: Licht halber Radius, Dunkelsicht nur 9 m; im Kristallgang nur 4,5 m (Licht ein Viertel).
Dunkelsicht der SC deshalb mit `token_aendern` → `sicht` (Felder) begrenzen: 6 Felder, im Kristallgang 3.
Ankunft von Westen: `sc_platzieren` grimbar 1 3, nissa 1 4, ilvaen 2 3, zikko 2 4.

| Nr. | Bereich | Felder | Kurz |
|---|---|---|---|
| 1 | Zugang | x 0–7, y 2–5 | Säulenzeichen + „Willkommen“ in Drow-Schrift (Lokales SG 12: nachgemalt) |
| 2 | Kristallgang | x 8–15, y 2–5 | 1 Dunkelmantel an der Decke; 4 Schattenkristalle (10 min, Lärm) |
| 3 | Fresskammer | x 15–24, y 1–10 | 2 Ghule (rufen „Frisches Fleisch!“, Ghast kommt in Runde 2) |
| 4 | Ladeplatz | x 12–21, y 11–23; Karre x 14–17, y 13–14 | Barren: Tag 1: 10, Tag 2: 7, Tag 3: 5; Südtunnel x 16–17, y 21–28 (Gewölbe SG 15: Richtung Land der Untoten) |
| 5 | Runenwerkstatt | x 22–30, y 12–20; Werkbank x 25–28, y 14–15 | Ghast Grauzahn; 3 halbfertige Lauschsteine (Zauberkunde SG 18), Silberstaub-Tinte, Lieferliste, Werkzeugkasten „A. Vey“ |
| 6 | Schmugglerstollen | x 28–32, y 6–13; Kisten (31, 8) | 2 Kisten mit Säulenzeichen, 6 Schattenkristalle (Bastrins Schmuggler) |

- `token_neu` gegner „Dunkelmantel“ 12 3 id mantel tp 13 rk 14 hg 1 verborgen (Werte: `monster_info` Dunkelmantel)
- `token_neu` gegner „Ghul“ 21 5 id ghul1 tp 13 rk 14 rkb 12 rkf 12 ref 2 wil 5 zaeh 2 hg 1 symbol G verborgen · „Ghul“ 23 7 id ghul2 (gleich)
- `token_neu` gegner „Grauzahn“ 27 17 id grauzahn tp 17 rk 17 rkb 13 rkf 14 ref 3 wil 6 zaeh 4 hg 2 symbol G verborgen
- Angriffe: Ghul Biss +3 (1W6+1, Lähmung ZÄH SG 13, Elfen immun), 2 Klauen +3 (1W6+1); Grauzahn Biss +5 (1W8+3), 2 Klauen +5
  (1W6+3), Lähmung SG 15 (auch Elfen), Gestank 3 m ZÄH SG 15 oder kränkelnd; flieht unter 6 TP durch den Südtunnel.

## Abenteuer 5 – Gefangenenlager (Karte `gefangenenlager`)
Zugang über den Kammweg im Norden (`sc_platzieren` 14 0, 15 0, 14 1, 15 1) oder mit den Milben durch den Spalt im Osten
(Geheimtür `spalt` mit `tuer` öffnen, SC bei x 31–32, y 13–14; Überraschungsrunde).

| Nr. | Bereich | Felder | Wer |
|---|---|---|---|
| 1 | Kammweg | x 13–16, y 0–3 | Zugang |
| 2 | Lagertor, Wachfeuer | Torpfosten y 4,4; Feuer (14, 5) | 2 Ghule |
| 3 | Pferche (3) | x 3–7; y 9–12, 13–16, 18–21; Gatter `pferch1`–`pferch3` (Ostseite) | 19 Gefangene; Ilun und Szar im südlichen Pferch |
| 4 | Obelisk | (15–16, 13–15), Aura 9 m | Härte 8, 40 TP; Weihwasser ×4 oder *Weihen* löscht die Aura (Ehrenmarke) |
| 5 | Zelt | x 24–28, y 10–13; Eingang `zelt` im Westen; Feuer (22, 13) | Mutter Asch, Herold in Eisen (belauschtes Gespräch!) |
| 6 | Arbeitsplatz | x 8–16, y 21–25 | 6 Zombies |
| 7 | Südausgang | x 15–17, y 27–30 | Weg zum Grauen Hof; von hier kommt der Bleiche Hund |

- `token_neu` gegner „Ghul“ 13 6 id lghul1 tp 13 rk 14 rkb 12 rkf 12 ref 2 wil 5 zaeh 2 hg 1 verborgen · „Ghul“ 16 6 id lghul2
- `token_neu` gegner „Mutter Asch“ 26 12 id asch tp 29 rk 17 rkb 11 rkf 16 ref 2 wil 7 zaeh 6 hg 3 verborgen
- `token_neu` gegner „Herold in Eisen“ 27 13 id herold tp 26 rk 19 ref 2 wil 7 zaeh 3 hg 3 verborgen
- `token_neu` gegner „Zombie“ 9 23 id zombie1 tp 12 rk 12 rkb 10 rkf 12 ref 0 wil 3 zaeh 0 hg 1/2 verborgen (zombie2–6 bei
  (11, 22), (12, 24), (14, 23), (11, 24), (15, 24))
- Bleicher Hund (Szene 6): Werte `03_NSC_Werte.txt` Nr. 6 (RK 18, TP 30, Schnelle Heilung 2); folgt nicht über den Klagebach.

## Abenteuer 6 – Torhaus (Karte `torhaus`)
Teleport der Gruppe auf den Exerzierplatz (x 17–20, y 2–7). Karte ist aufgedeckt (Wall mit zwei Ebenen).

| Bereich | Felder |
|---|---|
| Vorhöhle (Untotenarmee, Sturmleitern bei (11, 6) und (11, 24)) | x 0–12 |
| Wehrgang (oben auf dem Wall, Aufgabe D) | x 12–14; nur über die Treppe im Torhaus (17, 17) |
| Torweg | x 11–18, y 15–16; Fallgitter `fallgitter` bei x 13 (Gitter; Hochziehen = `barrieren_entfernen` ids fallgitter), Tor `tor` bei x 16 |
| Windenraum (Aufgabe B: Gorm, Bleicher Hund) | x 13–17, y 12–14; Tür `windenraum` (offen) zum Torweg |
| Hof hinter dem Tor | x 18–24, y 14–17 |
| Kaserne (Aufgabe A, Drow und Duergar eingesperrt) | x 21–29, y 2–7; Tür `kaserne` (25, 8) |
| Mauer der Namen | x 15, y 20–24 |
| Wassertor (Gitter) am Grovarie | x 12–14, y 28–29 |

- `token_neu` gegner „Feldwebel Gorm Aschgrau“ 15 13 id gorm tp 42 rk 19 rkb 11 rkf 18 ref 2 wil 2 zaeh 7 hg 3
- `token_neu` gegner „Duergar-Soldat“ 14 13 id duergar1 tp 15 rk 17 ref 0 wil 1 zaeh 5 hg 1/2 (duergar2–6 bei (16, 13), (14, 14), (16, 14), (17, 13), (17, 14))
- `token_neu` gegner „Bleicher Hund“ 15 14 id hund tp 30 rk 18 rkb 13 rkf 15 hg 4
- `token_neu` gegner „Aldren Vey“ 18 15 id vey tp 14 rk 15 rkb 11 rkf 14 hg 1 · „Lehrling“ 18 16 id lehrling2 (gleich)
- `token_neu` gegner „Kalkzahn“ 11 6 id kalkzahn tp 55 rk 23 rkb 13 rkf 20 ref 5 wil 7 zaeh 8 hg 6 (Phase 4, Sturmleiter Nord)
- Wellen-System: Wallstärke (WS) startet bei 2; Wellen 3/4/5/6. Tabelle in `11_…` (`suchen` „Wellenstärke“). WS in den
  Laufenden Notizen mitführen.

## Laufende Notizen
- **Stand:** Kampagnenbeginn. Szene „Die Kaserne“ (Abenteuer 1, Szene 1), aktive Karte `torstadt`. SC noch nicht auf
  einer Kampfkarte; Ratten und Tamla auf `zisternen` verborgen vorbereitet.
- **Gruppe (Test-SC, Stufe 1):** Grimbar Aschbart (Duergar, Kämpfer), Nissa Moosgrund (Svirfneblin, Druidin),
  Ilvaen Mondweiß (Munavri, Magier), Zikko Flinkfell (Rattenvolk, Schurke).
- **Ehrenmarken:** 0
