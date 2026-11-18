// Wissen: Verweise aus dem Spieltisch auf die Nachschlage-Seite (Zauber, Zustände, Regeln).
import { SL } from "./grundlagen.js";

// Adresse der Nachschlage-Seite; eintrag z. B. „zauber:Hast“, „zustand:Liegend“, „regel:123“
export function nachschlagenUrl(eintrag = null, frage = null) {
  const p = new URLSearchParams();
  if (SL) p.set("sl", SL);
  if (frage) p.set("q", frage);
  if (eintrag) p.set("e", eintrag);
  const q = p.toString();
  return "/nachschlagen.html" + (q ? "?" + q : "");
}

// Öffnet die Seite in einem eigenen Tab (immer demselben, damit nicht für jeden Klick ein neuer entsteht)
export function nachschlagen(art = null, name = null) {
  const w = window.open(nachschlagenUrl(art && name ? `${art}:${name}` : null), "spieltisch-nachschlagen");
  w?.focus();
}

// Kleines „?“ zum Nachschlagen in Knöpfen (Zauber, Zustände); Klick wirkt nur als Verweis, nicht als Knopf
export function nachschlagenZeichen(art, name) {
  const s = document.createElement("span");
  s.className = "nachschlagen-zeichen";
  s.textContent = "?";
  s.title = `„${name}“ nachschlagen`;
  s.addEventListener("click", (ev) => {
    ev.stopPropagation();
    ev.preventDefault();
    nachschlagen(art, name);
  });
  return s;
}
