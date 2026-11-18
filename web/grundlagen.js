// Grundlagen: SL-Modus, DOM-Helfer, API-Aufrufe, Meldungen, HTML-Escaping.
// ------------------------------------------------------------------ Grundlagen

export const SL = new URLSearchParams(location.search).get("sl");
if (SL) document.body.classList.add("sl");
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const schlaf = (ms) => new Promise((r) => setTimeout(r, ms));

export async function api(pfad, daten) {
  const r = await fetch(pfad, {
    method: daten === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", ...(SL ? { "X-SL": SL } : {}) },
    body: daten === undefined ? undefined : JSON.stringify(daten),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    meldung(j.fehler || `Fehler ${r.status}`);
    throw new Error(j.fehler);
  }
  return j;
}
export const slBefehl = (b) => api("/api/sl/befehl", b);

let toastTimer = null;
export function meldung(text, art = "fehler") {
  const t = $("#toast");
  t.textContent = text;
  t.className = art === "info" ? "info" : "";
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4500);
}

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
