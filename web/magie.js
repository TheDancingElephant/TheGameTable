// Magie: Zauberkatalog, Zauber vorbereiten, Zauber und Fähigkeiten wirken.
import { vz } from "./charakter.js";
import { $, SL, api, esc, meldung } from "./grundlagen.js";
import { abstandC, kampfSperre } from "./kampf.js";
import { canvas, meter } from "./karte.js";
import { kampfLaeuft } from "./tisch.js";
import { G } from "./zustand.js";

export let zauberDb = [];
fetch("/api/zauber").then((r) => r.json()).then((d) => (zauberDb = d)).catch(() => {});
// Grad eines Katalogzaubers für Klassenangaben wie „Kleriker“ oder „Barde 5“ (die erste passende zählt;
// längste Klassennamen zuerst: Hexenmeister vor Hexe)
export function zauberGradFuer(z, ...klassen) {
  for (const klasse of klassen) {
    const k = (klasse || "").toLowerCase();
    const treffer = Object.keys(z?.klassen || {}).sort((a, b) => b.length - a.length).find((n) => k.includes(n.toLowerCase()));
    if (treffer) return z.klassen[treffer];
  }
  return z?.grad;
}
// alle Zauberlisten (Klassen) im Katalog, für die Auswahl im Editor
export const zauberListen = () => [...new Set(zauberDb.flatMap((z) => Object.keys(z.klassen || {})))].sort((a, b) => a.localeCompare(b));

// Zauber vorbereiten: je Platz eine Auswahl aus der Zauberliste der Klasse (Magier: aus dem Zauberbuch)
export async function zauberVorbereiten(c) {
  const plan = await api("/api/zauber-vorbereiten", { charId: c.id, op: "plan" }).catch(() => null);
  if (!plan) return;
  const grade = [...new Set(plan.plaetze.map((p) => p.grad))].sort((a, b) => a - b);
  const quelle = (g, domaene) => domaene
    ? zauberDb.filter((z) => Object.values(z.klassen || {}).includes(g))
    : plan.buch ? plan.buch.filter((b) => b.grad === g).map((b) => zauberDb.find((z) => z.name.toLowerCase() === b.name.toLowerCase()) || b)
      : zauberDb.filter((z) => (z.klassen || {})[plan.klasse] === g);
  const listen = grade.flatMap((g) => [[`zv-${g}`, quelle(g, false)], [`zv-${g}-d`, quelle(g, true)]]);
  const namenVon = Object.fromEntries(listen.map(([id, l]) => [id, new Set(l.map((z) => z.name.toLowerCase()))]));
  const herkunft = plan.buch ? "aus dem Zauberbuch" : `Zauberliste ${plan.klasse || "?"}`;
  const dlg = document.createElement("dialog");
  dlg.id = "zauber-vorbereiten";
  dlg.innerHTML = `<form method="dialog" class="auf-form">
    <h2>${esc(c.name)}: Zauber vorbereiten</h2>
    <p class="hinweis">Je Platz einen Zauber wählen (${esc(herkunft)}; Vorschläge erscheinen beim Tippen oder per ▾).
      Derselbe Zauber darf mehrfach vorbereitet werden. Orange = nicht auf der Liste (z. B. Metamagie) – erlaubt, der SL prüft.</p>
    <div class="auf-körper">${grade.map((g) => {
      const pl = plan.plaetze.map((p, i) => [p, i]).filter(([p]) => p.grad === g);
      return `<fieldset><legend>Grad ${g} · ${pl.length} ${pl.length === 1 ? "Platz" : "Plätze"}</legend>
        <div class="zv-plaetze">${pl.map(([p, i]) => `<label class="zv-platz">${p.domaene ? "<b title=\"Domänenplatz\">D</b>" : ""}
          <input data-i="${i}" list="zv-${g}${p.domaene ? "-d" : ""}" value="${esc(p.name)}" required></label>`).join("")}</div></fieldset>`;
    }).join("")}</div>
    ${listen.map(([id, l]) => `<datalist id="${id}">${l.map((z) => `<option value="${esc(z.name)}">${esc((z.effekt || "").slice(0, 90))}</option>`).join("")}</datalist>`).join("")}
    <div class="auf-knöpfe"><span class="auf-platz hinweis">${plan.plaetze.length} Plätze · nach der Rast sind alle wieder frei</span>
      <button value="abbrechen" formnovalidate>Abbrechen</button><button value="ok" class="primaer">Vorbereiten</button></div>
  </form>`;
  document.body.append(dlg);
  // Vergleichsform: ohne „(D)“, alte Namen („Segen“) wie im PRD („Segnen“)
  const norm = (n) => { const k = n.trim().toLowerCase().replace(/\s*\((d|dom|domäne)\)\s*$/, ""); return (plan.aliase?.[k] || k).toLowerCase(); };
  const alleNamen = new Set(zauberDb.map((z) => z.name.toLowerCase()));
  const pruefen = (inp) => {
    const domaene = inp.getAttribute("list").endsWith("-d");  // Domänengrade weichen von den Klassengraden ab
    const fremd = inp.value.trim() && !(domaene ? alleNamen : namenVon[inp.getAttribute("list")]).has(norm(inp.value));
    inp.classList.toggle("fremd", !!fremd);
    inp.title = !fremd ? "" : domaene ? "unbekannter Zauber (nicht im PRD)"
      : `nicht ${plan.buch ? "im Zauberbuch" : "auf der Liste " + (plan.klasse || "")} für diesen Grad`;
  };
  dlg.querySelectorAll("input[data-i]").forEach((inp) => { pruefen(inp); inp.oninput = () => pruefen(inp); });
  // Enter im Eingabefeld würde den ersten Knopf (Abbrechen) auslösen
  dlg.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && ev.target.matches("input")) ev.preventDefault(); });
  dlg.addEventListener("close", async () => {
    if (dlg.returnValue === "ok") {
      const namen = [...dlg.querySelectorAll("input[data-i]")].sort((a, b) => a.dataset.i - b.dataset.i).map((i) => i.value.trim());
      const r = await api("/api/zauber-vorbereiten", { charId: c.id, op: "speichern", stand: plan.stand, namen }).catch(() => null);
      if (r) meldung(`${c.name}: Zauber vorbereitet`, "info");
    }
    dlg.remove();
  });
  dlg.showModal();
}
export const zauberOption = (z) => `<option value="${esc(z.name)}">${esc(z.klassenText || "Grad " + z.grad)}</option>`;
const RW_NAME = { REF: "Reflex", WIL: "Wille", ZAEH: "Zähigkeit" };

/** Anzeige der freien Plätze: "1/2", "Pool 2/3", "spontan 2" oder "" (beliebig oft) */
export function zauberPlaetze(e) {
  const d = e._d;
  if (!d || d.frei == null) return "";
  if (e.spontan) return ` spontan ${d.frei}`;
  if (e.pool) return ` ${d.frei}/${d.poolMax}`;
  return ` ${d.frei}/${e.proTag}`;
}

export function zauberBeschreibung(d) {
  const teile = [];
  if (d.modus === "angriff-fern") teile.push(`Fernkampf-Berührung ${vz(d.beruehrungsbonus)}`);
  if (d.modus === "angriff-nah") teile.push(`Nahkampf-Berührung ${vz(d.beruehrungsbonus)}`);
  if (d.modus === "automatisch") teile.push("trifft automatisch");
  if (d.rettungswurf) teile.push(`${RW_NAME[d.rettungswurf]} SG ${d.sg}${d.beiErfolg ? " " + d.beiErfolg : ""}`);
  if (d.schaden) teile.push(d.modus === "heilung" ? `heilt ${d.schaden}` : `${d.schaden}${d.art ? " " + d.art : ""}`);
  if (d.zustand) teile.push(d.zustand);
  teile.push(d.reichweite === "beruehrung" ? "Berührung" : d.reichweite === "selbst" ? "selbst" : `${d.reichweiteM} m`);
  return teile.join(" · ");
}

// Angaben aus dem PRD (Zeitaufwand, Dauer, Rettungswurf …) für den Tooltip
export function zauberPrdZeilen(d) {
  const p = d.prd || {};
  const z = [["zeitaufwand", "Zeitaufwand"], ["wirkungsdauer", "Dauer"], ["rettungswurf", "Rettungswurf"], ["zauberresistenz", "ZR"]]
    .filter(([k]) => p[k]).map(([k, t]) => `${t}: ${p[k]}`);
  return z.length ? "\n" + z.join(" · ") : "";
}

export function zauberPruefen(a, e, ziel) {
  const d = e._d;
  const nein = (text) => ({ ok: false, text });
  if (!d) return nein("unbekannter Zauber");
  if (d.frei === 0) return nein("heute keine Zauberplätze mehr");
  const sperre = kampfSperre(a, d.aktion || "standard", ["gegner", "feld"].includes(d.ziel));
  if (sperre) return nein(sperre);
  if (ziel) {
    const dist = abstandC(a, ziel);
    if (d.reichweite === "beruehrung" && dist > Math.max(1, a.reichweite || 1)) return nein(`nicht in Berührungsreichweite (${meter(dist)} m)`);
    if (d.reichweite !== "beruehrung" && meter(dist) > d.reichweiteM) return nein(`außer Reichweite (${meter(dist)} m, max. ${d.reichweiteM} m)`);
  }
  return { ok: true, text: zauberBeschreibung(d) };
}

// Zielauswahl für Zauber: nach Klick auf den Zauber das Ziel auf der Karte anklicken

export async function zauberWirken(t, index, ziel, feld) {
  G.zielModus = null;
  canvas.style.cursor = "";
  $("#koordinate").textContent = "";
  await api("/api/zaubern", { id: t.id, zauber: index, ziel: ziel?.id, feld });
}

export function zauberStarten(c, t, index) {
  const e = c.zauberliste[index];
  const d = e._d;
  if (!t) return meldung(`${c.name} steht nicht auf der Karte`);
  const p = zauberPruefen(t, e, null);
  if (!p.ok) return meldung(`${d?.name || e.name}: ${p.text}`);
  if (!["gegner", "verbuendet", "feld"].includes(d.ziel)) return zauberWirken(t, index, null, null);
  G.zielModus = { token: t, index, e };
  canvas.style.cursor = "crosshair";
  $("#koordinate").textContent = d.ziel === "feld" ? "Zielfeld anklicken …" : d.ziel === "gegner" ? "Gegner anklicken …" : "Verbündeten anklicken …";
}

const FAEHIGKEIT_AKTION = { standard: "Standard-Aktion", schnell: "Schnelle Aktion", bewegung: "Bewegungsaktion", keine: "keine Aktion" };

export function faehigkeitBeschreibung(f) {
  const teile = [FAEHIGKEIT_AKTION[f.aktion || "keine"]];
  if (f.modus === "bereich") teile.push(`${f.radius} m Umkreis`, `${RW_NAME[f.rettungswurf]} SG ${f.sg ?? 10}${f.beiErfolg ? " " + f.beiErfolg : ""}`, `${f.schaden} ${f.art || ""}`.trim());
  if (f.modus === "heilung") teile.push(`heilt ${f.schaden}`);
  if (f.modus === "wurf") teile.push(`würfelt ${f.wurf}`);
  if (f.modus === "sl" || !f.modus) teile.push("der Spielleiter wertet aus");
  if (f.pro) teile.push(f.pro);
  return teile.join(" · ");
}

export function faehigkeitPruefen(a, f) {
  const aktion = f.aktion || "keine";
  const sperre = kampfSperre(a, aktion === "schnell" ? "schnell" : aktion === "standard" ? "standard" : "keine",
    f.modus === "bereich" || f.ziel === "gegner");
  if (sperre) return { ok: false, text: sperre };
  if (aktion === "bewegung" && kampfLaeuft() && !G.stand.zug.bewegungFrei) return { ok: false, text: "Bewegungsaktion schon verbraucht" };
  return { ok: true, text: faehigkeitBeschreibung(f) };
}

export async function faehigkeitWirken(t, index, ziel) {
  G.zielModus = null;
  canvas.style.cursor = "";
  $("#koordinate").textContent = "";
  await api("/api/faehigkeit", { id: t.id, index, ziel: ziel?.id });
}

export function faehigkeitStarten(c, t, index) {
  const f = c.faehigkeitenListe[index];
  if (!t) return meldung(`${c.name} steht nicht auf der Karte`);
  const p = faehigkeitPruefen(t, f);
  if (!p.ok) return meldung(`${f.name}: ${p.text}`);
  if (!["gegner", "verbuendet"].includes(f.ziel)) return faehigkeitWirken(t, index, null);
  G.zielModus = { token: t, faeh: index, e: { name: f.name, _d: { ziel: f.ziel } }, f };
  canvas.style.cursor = "crosshair";
  $("#koordinate").textContent = f.ziel === "gegner" ? "Gegner anklicken …" : "Verbündeten anklicken …";
}
