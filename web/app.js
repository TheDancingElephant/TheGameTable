// Einstieg der Spieltisch-Oberfläche: lädt alle Bereichsmodule (ES-Module, kein Build-Schritt) und startet
// die Server-Schleife. Aufbau: siehe ARCHITEKTUR.md (Frontend) und STYLEGUIDE.md.
import "./grundlagen.js";
import "./zustand.js";
import "./karte.js";
import "./tisch.js";
import "./kampf.js";
import "./magie.js";
import "./charakter.js";
import "./besitz.js";
import "./aufstieg.js";
import { schleife } from "./tisch.js";

schleife();
