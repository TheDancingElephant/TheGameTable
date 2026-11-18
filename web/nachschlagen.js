// Nachschlage-Seite: Suche und Leseansicht für Regeln (PRD), Zauber, Monster (nur SL) und Hausregeln.
// Zustand steht in der Adresse (?q=…&art=…&e=zauber:Hast), damit Zurück/Vor und Lesezeichen funktionieren.
import { $, $$, SL, api, esc } from "./grundlagen.js";
import { hervorheben, mdHtml } from "./markdown.js";

const ARTEN = ["alle", "regeln", "zauber", "monster", "inhalt"];
const FILTER = ["buch", "typ", "klasse", "grad", "schule", "quelle", "volltext", "hg", "monsterart"];
const TYP_NAMEN = { falle: "Falle", fertigkeit: "Fertigkeit", gegenstand: "Gegenstand", klasse: "Klasse",
  klassenmerkmal: "Klassenmerkmal", monster: "Monster", prestigeklasse: "Prestigeklasse", regel: "Regel",
  tabelle: "Tabelle", talent: "Talent", volk: "Volk", zustand: "Zustand" };
const N = { filter: null, zauber: new Map(), zustaende: new Map(), suchNr: 0 };

// ------------------------------------------------------------------ Adresse <-> Zustand
function lesenAdresse() {
  const p = new URLSearchParams(location.search);
  const s = { q: p.get("q") || "", art: ARTEN.includes(p.get("art")) ? p.get("art") : "alle", e: p.get("e") || "" };
  for (const f of FILTER) s[f] = p.get(f) || "";
  return s;
}

function adresse(s) {
  const p = new URLSearchParams();
  if (SL) p.set("sl", SL);
  if (s.q) p.set("q", s.q);
  if (s.art && s.art !== "alle") p.set("art", s.art);
  for (const f of FILTER) if (s[f]) p.set(f, s[f]);
  if (s.e) p.set("e", s.e);
  return "?" + p.toString();
}

function setzen(neu, { push = false, suchen = true } = {}) {
  const s = { ...lesenAdresse(), ...neu };
  history[push ? "pushState" : "replaceState"](null, "", adresse(s));
  zeigen(s, suchen);
}

// ------------------------------------------------------------------ Kopf: Arten und Filter
const wahl = (id, titel, werte, aktuell, namen = (x) => x) =>
  `<label>${esc(titel)} <select id="${id}"><option value="">alle</option>${werte.map((w) =>
    `<option value="${esc(w)}"${String(w) === String(aktuell) ? " selected" : ""}>${esc(namen(w))}</option>`).join("")}</select></label>`;

function filterZeichnen(s) {
  const f = N.filter;
  $$("#ns-arten button").forEach((b) => b.classList.toggle("aktiv", b.dataset.art === s.art));
  let h = "";
  if (s.art === "regeln") {
    h = wahl("f-buch", "Buch", f.buecher, s.buch) + wahl("f-typ", "Typ", f.typen, s.typ, (t) => TYP_NAMEN[t] || t);
  } else if (s.art === "zauber") {
    h = wahl("f-klasse", "Klasse", f.zauberKlassen, s.klasse) + wahl("f-grad", "Grad", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], s.grad)
      + wahl("f-schule", "Schule", f.zauberSchulen, s.schule) + wahl("f-quelle", "Quelle", f.zauberQuellen, s.quelle)
      + `<label><input type="checkbox" id="f-volltext"${s.volltext ? " checked" : ""}> auch im Text</label>`;
  } else if (s.art === "monster") {
    h = wahl("f-hg", "HG", f.monsterHg || [], s.hg) + wahl("f-monsterart", "Art", f.monsterArten || [], s.monsterart);
  }
  const box = $("#ns-filter");
  box.innerHTML = h;
  box.hidden = !h;
  $$("select", box).forEach((el) => (el.onchange = () => setzen({ [el.id.slice(2)]: el.value })));
  const vt = $("#f-volltext");
  if (vt) vt.onchange = () => setzen({ volltext: vt.checked ? "1" : "" });
}

// ------------------------------------------------------------------ Trefferliste
const kennung = (t) => `${t.art}:${t.id}`;

function trefferHtml(t, s) {
  const marke = t.art === "hausregel" ? `<span class="marke haus">Hausregel</span>`
    : t.art === "zauber" ? `<span class="marke zauber">Zauber</span>`
      : t.art === "monster" ? `<span class="marke monster">Monster</span>`
        : `<span class="marke">${esc(t.kuerzel || "")}</span>${t.typ && t.typ !== "regel" ? `<span class="marke typ">${esc(TYP_NAMEN[t.typ] || t.typ)}</span>` : ""}`;
  const aktiv = s.e === kennung(t) ? " aktiv" : "";
  return `<a class="treffer${aktiv}" href="${esc(adresse({ ...s, e: kennung(t) }))}" data-e="${esc(kennung(t))}">
    <div class="t-kopf"><b>${esc(t.titel)}</b>${marke}</div>
    ${t.untertitel ? `<div class="t-unter">${esc(t.untertitel)}</div>` : ""}
    ${t.schnipsel ? `<div class="t-text">${hervorheben(t.schnipsel, s.q)}</div>` : ""}</a>`;
}

async function listeZeichnen(s) {
  const liste = $("#ns-liste");
  if (s.art === "inhalt" || (!s.q && s.art !== "zauber" && s.art !== "monster")) return inhaltZeichnen(s);
  const nr = ++N.suchNr;
  liste.innerHTML = `<div class="hinweis">Suche …</div>`;
  const p = new URLSearchParams({ q: s.q, art: s.art });
  for (const f of FILTER) if (s[f]) p.set(f, s[f]);
  let d;
  try {
    d = await api("/api/wissen/suche?" + p);
  } catch {
    liste.innerHTML = `<div class="hinweis">Suche fehlgeschlagen.</div>`;
    return;
  }
  if (nr !== N.suchNr) return;  // eine neuere Suche läuft schon
  const mehr = d.gesamt > d.treffer.length ? ` (die ersten ${d.treffer.length})` : "";
  liste.innerHTML = (d.hinweis ? `<div class="hinweis">${esc(d.hinweis)}</div>`
    : `<div class="anzahl">${d.gesamt} Treffer${mehr}</div>`)
    + d.treffer.map((t) => trefferHtml(t, s)).join("")
    + (!d.treffer.length && !d.hinweis ? `<div class="hinweis">Nichts gefunden. Andere Begriffe oder einen anderen Bereich versuchen.</div>` : "");
}

async function inhaltZeichnen(s) {
  const d = await api("/api/wissen/inhalt").catch(() => null);
  if (!d) return;
  $("#ns-liste").innerHTML = `<div class="anzahl">Inhalt</div>` + d.buecher.map((b) =>
    `<details class="buch"${b.titel !== "Monsterhandbuch" ? " open" : ""}><summary><a href="${esc(adresse({ ...s, e: `seite:${b.id}` }))}" data-e="seite:${b.id}">${esc(b.titel)}</a></summary>
    ${b.kapitel.map((k) => `<a class="kapitel${s.e === `seite:${k.id}` ? " aktiv" : ""}" href="${esc(adresse({ ...s, e: `seite:${k.id}` }))}" data-e="seite:${k.id}">${esc(k.titel)}</a>`).join("")}</details>`).join("");
}

// ------------------------------------------------------------------ Leseansicht
// Kursive Begriffe in Texten: Zauber und Zustände werden zu Verweisen
function verweis(text) {
  const k = text.trim().toLowerCase().replace(/[.,;:]$/, "");
  if (N.zauber.has(k)) return `zauber:${N.zauber.get(k)}`;
  if (N.zustaende.has(k)) return `zustand:${N.zustaende.get(k)}`;
  return null;
}

const link = (e, text, s, klasse = "") =>
  `<a class="${klasse}" href="${esc(adresse({ ...s, e }))}" data-e="${esc(e)}">${esc(text)}</a>`;

function eintragHtml(d, s) {
  const pfad = [d.buch ? `<span>${esc(d.buch)}</span>` : "", d.seite ? link(`seite:${d.seite.id}`, d.seite.titel, s) : "",
    ...(d.eltern || []).filter((e) => e.titel !== d.seite?.titel).map((e) => link(`regel:${e.id}`, e.titel, s))].filter(Boolean);
  let h = `<nav class="pfad">${pfad.join(" › ")}</nav><h2>${esc(d.titel)}</h2>`;
  if (d.untertitel && d.art !== "zauber") h += `<div class="unter">${esc(d.untertitel)}</div>`;
  if (d.felder?.length) {
    h += `<dl class="felder">${d.felder.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
    if (d.wie) {
      const ziel = verweis(d.wie) || `zauber:${d.wie}`;
      h += `<p class="hinweis">Funktioniert wie ${link(ziel, d.wie, s, "verweis")}.</p>`;
    }
    if (d.kurz) h += `<p class="kurz">${esc(d.kurz)}</p>`;
  }
  for (const r of d.hausregeln || []) {
    h += `<aside class="hausregel"><b>⚑ Hausregel dieser Kampagne: ${link(`hausregel:${r.id}`, r.titel, s)}</b>${mdHtml(r.text, verweis, 4)}</aside>`;
  }
  if (d.art === "hausregel") h += `<aside class="hausregel"><b>⚑ Hausregel dieser Kampagne (hat Vorrang vor dem Regelwerk)</b></aside>`;
  for (const a of d.abschnitte || []) {
    if (a.titel) {
      const ht = Math.min(6, 2 + a.ebene);
      h += `<h${ht} id="a-${a.id}">${esc(a.titel)}</h${ht}>`;
    }
    h += a.text === null ? `<p>${link(`regel:${a.id}`, "→ weiterlesen", s, "verweis")}</p>` : mdHtml(a.text, verweis, 3 + (a.ebene || 0));
  }
  h += `<footer class="quelle">${esc(d.quelle || "")}${d.url ? ` · <a href="${esc(d.url)}" target="_blank" rel="noopener">im PRD öffnen ↗</a>` : ""}${d.art !== "hausregel" ? " · Open Game Content (OGL 1.0a)" : ""}</footer>`;
  return h;
}

async function seiteHtml(id, s) {
  const d = await api(`/api/wissen/inhalt?seite=${encodeURIComponent(id)}`);
  const kette = [...d.kette.map((k) => link(`seite:${k.id}`, k.titel, s))];
  let h = `<nav class="pfad">${kette.join(" › ")}</nav><h2>${esc(d.seite.titel)}</h2>`;
  if (d.abschnitte.length) {
    const oben = Math.min(...d.abschnitte.map((a) => a.stufe));
    h += `<ul class="toc">${d.abschnitte.map((a) => `<li style="margin-left:${(a.stufe - oben) * 14}px">${link(`regel:${a.id}`, a.titel, s)}${a.typ === "monster" ? ` <span class="marke monster">Monster</span>` : ""}</li>`).join("")}</ul>`;
  }
  if (d.unterseiten.length) {
    h += `<h3>Unterseiten (${d.unterseiten.length})</h3><div class="unterseiten">${d.unterseiten.map((u) => link(`seite:${u.id}`, u.titel, s)).join("")}</div>`;
  }
  h += `<footer class="quelle">PRD ${esc(d.seite.buch)} · <a href="${esc(d.seite.url)}" target="_blank" rel="noopener">im PRD öffnen ↗</a> · Open Game Content (OGL 1.0a)</footer>`;
  return h;
}

function startHtml(s) {
  const f = N.filter;
  return `<h2>Regeln, Zauber${f.sl ? ", Monster" : ""} nachschlagen</h2>
    <p>Suche oben im ganzen Regelwerk (Grundregelwerk, Expertenregeln${f.sl ? ", Monsterhandbuch" : ""}), in den Zaubern${f.hausregeln ? " und in den Hausregeln dieser Kampagne" : ""}.
    Unter <b>Zauber</b> lassen sich alle Zauber einer Klasse und eines Grades auflisten${f.sl ? ", unter <b>Monster</b> alle Monster nach HG und Art" : ""}; <b>Inhalt</b> zeigt die Kapitel der Bücher.</p>
    ${f.zustaende.length ? `<h3>Zustände</h3><div class="unterseiten">${f.zustaende.map((z) => link(`zustand:${z}`, z, s)).join("")}</div>` : ""}
    ${f.datenbank ? "" : `<p class="hinweis">Die Regeldatenbank fehlt (regeln/regeln.sqlite); nur Zauber sind verfügbar.</p>`}
    <footer class="quelle">Texte aus dem deutschen Pathfinder-PRD (prd.5footstep.de), Open Game Content (OGL 1.0a)${f.stand ? ` · Stand ${esc(f.stand)}` : ""}</footer>`;
}

async function lesenZeichnen(s) {
  const el = $("#ns-lesen");
  document.body.classList.toggle("liest", !!s.e);
  if (!s.e) {
    el.innerHTML = startHtml(s);
    document.title = "Nachschlagen – Spieltisch";
    return;
  }
  const i = s.e.indexOf(":");
  const art = s.e.slice(0, i);
  const wert = s.e.slice(i + 1);
  el.innerHTML = `<div class="hinweis">Lade …</div>`;
  try {
    if (art === "seite") {
      el.innerHTML = await seiteHtml(wert, s);
    } else {
      const p = new URLSearchParams({ art });
      p.set(/^\d+$/.test(wert) || art === "hausregel" ? "id" : "name", wert);
      const d = await fetch("/api/wissen/eintrag?" + p, { headers: SL ? { "X-SL": SL } : {} });
      const j = await d.json().catch(() => ({}));
      if (!d.ok) throw new Error(j.fehler || `Fehler ${d.status}`);
      el.innerHTML = eintragHtml(j, s);
      document.title = `${j.titel} – Nachschlagen`;
    }
    el.scrollTop = 0;
  } catch (err) {
    el.innerHTML = `<h2>Nicht gefunden</h2><p class="hinweis">${esc(err.message)}</p>`;
  }
  const zurueck = document.createElement("button");
  zurueck.className = "ns-zur-liste";
  zurueck.textContent = "← Treffer";
  zurueck.onclick = () => setzen({ e: "" }, { push: true, suchen: false });
  el.prepend(zurueck);
}

// ------------------------------------------------------------------ Ablauf
function zeigen(s, suchen = true) {
  $("#ns-q").value = s.q;
  filterZeichnen(s);
  if (suchen) listeZeichnen(s);
  else $$("#ns-liste [data-e]").forEach((a) => a.classList.toggle("aktiv", a.dataset.e === s.e));
  lesenZeichnen(s);
}

let tippen = null;
$("#ns-q").addEventListener("input", () => {
  clearTimeout(tippen);
  tippen = setTimeout(() => {
    const s = lesenAdresse();
    const q = $("#ns-q").value.trim();
    if (q === s.q) return;
    setzen({ q, art: s.art === "inhalt" ? "alle" : s.art, e: q ? "" : s.e });
  }, 350);
});
$("#ns-suche").addEventListener("submit", (ev) => {
  ev.preventDefault();
  clearTimeout(tippen);
  const s = lesenAdresse();
  setzen({ q: $("#ns-q").value.trim(), art: s.art === "inhalt" ? "alle" : s.art, e: "" }, { push: true });
});
$("#ns-arten").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-art]");
  if (!b) return;
  const neu = { art: b.dataset.art };
  for (const f of FILTER) neu[f] = "";
  setzen(neu, { push: true });
});
document.addEventListener("click", (ev) => {
  const a = ev.target.closest("a[data-e]");
  if (!a || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) return;
  ev.preventDefault();
  setzen({ e: a.dataset.e }, { push: true, suchen: false });
});
window.addEventListener("popstate", () => zeigen(lesenAdresse()));

async function start() {
  N.filter = await api("/api/wissen/filter").catch(() => ({ sl: false, buecher: [], typen: [], zustaende: [],
    zauberKlassen: [], zauberSchulen: [], zauberQuellen: [], zauberNamen: [], datenbank: false }));
  document.body.classList.toggle("sl", !!N.filter.sl);  // nur mit gültigem Schlüssel
  for (const n of N.filter.zauberNamen) N.zauber.set(n.toLowerCase(), n);
  for (const z of N.filter.zustaende) N.zustaende.set(z.toLowerCase(), z);
  $("#ns-zurueck").href = "/" + (SL ? `?sl=${encodeURIComponent(SL)}` : "");
  const s = lesenAdresse();
  if (s.art === "monster" && !N.filter.sl) s.art = "alle";
  zeigen(s);
}
start();
