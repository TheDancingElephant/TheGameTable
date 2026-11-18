// Besitz: Gruppenkasse und Gegenstände (Reiter Ausrüstung).
import { vz } from "./charakter.js";
import { $, $$, api, esc } from "./grundlagen.js";
import { nachschlagenZeichen } from "./wissen.js";
import { G } from "./zustand.js";

// ------------------------------------------------------------------ Ausrüstung

let ausruestungSig = "";
function traegerName(id) {
  return id === "gruppe" ? "Gruppe (Gepäck)" : G.charaktere.find((c) => c.id === id)?.name || id;
}
export function ausruestungZeichnen() {
  const a = G.stand.ausruestung;
  if (!a) return;
  const sig = JSON.stringify([a, G.charaktere.map((c) => [c.id, c.name, c.zauberbuch, c.zauberliste])]);
  if (sig === ausruestungSig) return;
  if (document.activeElement && document.activeElement.closest("#ausruestung-liste")) return;
  ausruestungSig = sig;
  const k = a.kasse;
  $("#kasse").innerHTML = `<div class="kasse">${["pp", "gp", "sp", "kp"].map((m) => `<span><b>${k[m]}</b> ${m.toUpperCase()}</span>`).join("")}</div>`;
  const traeger = [...G.charaktere.map((c) => c.id), "gruppe"];
  $("#item-traeger").innerHTML = traeger.map((t) => `<option value="${esc(t)}">${esc(traegerName(t))}</option>`).join("");
  const gruppiert = {};
  for (const g of a.gegenstaende) (gruppiert[g.traeger] ||= []).push(g);
  $("#ausruestung-liste").innerHTML = traeger.map((t) => {
    const liste = (gruppiert[t] || []).slice().sort((x, y) => x.ort.localeCompare(y.ort) || x.name.localeCompare(y.name));
    if (!liste.length) return "";
    const orte = [...new Set(liste.map((g) => g.ort))];
    return `<details open><summary>${esc(traegerName(t))} (${liste.length})</summary>${orte.map((o) => `<div class="ort"><b>${esc(o)}</b>` +
      liste.filter((g) => g.ort === o).map((g) => `<div class="item" data-id="${g.id}"><span>${g.anzahl > 1 ? g.anzahl + "× " : ""}${esc(g.name)}${g.notiz ? ` <small>${esc(g.notiz)}</small>` : ""}</span>` +
        `<select class="item-an">${traeger.map((x) => `<option value="${esc(x)}"${x === g.traeger ? " selected" : ""}>${esc(traegerName(x))}</option>`).join("")}</select>` +
        `<input class="item-ort" value="${esc(g.ort)}" size="10"><button class="item-weg" title="entfernen">✕</button></div>`).join("") + `</div>`).join("")}</details>`;
  }).join("") || `<div class="hinweis">Noch keine Gegenstände.</div>`;
  const buecher = G.charaktere.filter((c) => c.zauberbuch);
  $("#zauberbuecher").innerHTML = buecher.map((c) => {
    const vorbereitet = new Set((c.zauberliste || []).map((z) => z.name.toLowerCase()));
    const grade = [...new Set(c.zauberbuch.map((z) => z.grad))].sort((x, y) => x - y);
    return `<details open data-char="${esc(c.id)}"><summary>Zauberbuch von ${esc(c.name)} (${c.zauberbuch.length})</summary>` +
      grade.map((g) => `<div class="ort"><b>Grad ${g}</b><div class="buch-zeilen">` + c.zauberbuch.filter((z) => z.grad === g).sort((x, y) => x.name.localeCompare(y.name))
        .map((z) => `<span class="buch-zauber${vorbereitet.has(z.name.toLowerCase()) ? " vorbereitet" : ""}" title="${vorbereitet.has(z.name.toLowerCase()) ? "vorbereitet" : "im Buch"}">${esc(z.name)}<button class="buch-weg" data-name="${esc(z.name)}" title="entfernen">✕</button></span>`).join("") + `</div></div>`).join("") +
      `<form class="buch-form zeile"><input class="buch-name" type="text" placeholder="Zauber eintragen" required><select class="buch-grad">${[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option value="${g}">Grad ${g}</option>`).join("")}</select><button type="submit">Eintragen</button></form></details>`;
  }).join("") || `<div class="hinweis">Keine Zauberbücher.</div>`;
  $$("#zauberbuecher .buch-zauber").forEach((sp) =>
    sp.insertBefore(nachschlagenZeichen("zauber", sp.querySelector(".buch-weg").dataset.name), sp.querySelector(".buch-weg")));
  $$("#zauberbuecher details").forEach((d) => {
    const charId = d.dataset.char;
    d.querySelector(".buch-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await api("/api/zauberbuch", { charId, op: "add", name: d.querySelector(".buch-name").value, grad: Number(d.querySelector(".buch-grad").value) });
      G.charaktere = await (await fetch("/api/charaktere")).json();
      ausruestungSig = "";
      ausruestungZeichnen();
    });
    d.querySelectorAll(".buch-weg").forEach((b) => b.addEventListener("click", async () => {
      await api("/api/zauberbuch", { charId, op: "weg", name: b.dataset.name });
      G.charaktere = await (await fetch("/api/charaktere")).json();
      ausruestungSig = "";
      ausruestungZeichnen();
    }));
  });
  $$("#ausruestung-liste .item").forEach((el) => {
    const id = Number(el.dataset.id);
    el.querySelector(".item-an").addEventListener("change", (e) => api("/api/ausruestung", { op: "item-aendern", id, traeger: e.target.value }));
    el.querySelector(".item-ort").addEventListener("change", (e) => api("/api/ausruestung", { op: "item-aendern", id, ort: e.target.value }));
    el.querySelector(".item-weg").addEventListener("click", () => confirm("Gegenstand entfernen?") && api("/api/ausruestung", { op: "item-weg", id }));
  });
}
$("#kasse-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const vz = Number(e.submitter?.dataset.vz || 1);
  const betrag = Math.abs(parseInt($("#kasse-betrag").value, 10) || 0) * vz;
  if (!betrag) return;
  await api("/api/ausruestung", { op: "kasse", delta: { [$("#kasse-art").value]: betrag }, grund: $("#kasse-grund").value || (vz > 0 ? "Einzahlung" : "Auszahlung") });
  $("#kasse-betrag").value = "";
  $("#kasse-grund").value = "";
});
$("#item-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/ausruestung", { op: "item-neu", name: $("#item-name").value, anzahl: Number($("#item-anzahl").value) || 1, traeger: $("#item-traeger").value, ort: $("#item-ort").value });
  $("#item-name").value = "";
});
