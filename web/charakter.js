// Charakter: Charakterkarten (Gruppe), Proben, Aufstieg, Charakter-Editor.
import { aufstiegsAssistent } from "./aufstieg.js";
import { $, $$, SL, api, esc, meldung, slBefehl } from "./grundlagen.js";
import { faehigkeitBeschreibung, faehigkeitPruefen, faehigkeitStarten, zauberBeschreibung, zauberDb, zauberGradFuer, zauberListen, zauberOption, zauberPlaetze, zauberPrdZeilen, zauberPruefen, zauberStarten, zauberVorbereiten } from "./magie.js";
import { amZug, imKampf, wuerfeln } from "./tisch.js";
import { G } from "./zustand.js";

// ------------------------------------------------------------------ Gruppe

const mod = (w) => (w == null ? 0 : Math.floor((w - 10) / 2));
export const vz = (n) => (n >= 0 ? "+" : "") + n;
export const scToken = (cid) => G.stand?.tokens.find((t) => t.art === "sc" && t.charId === cid);

export function gruppeZeichnen() {
  const sig = JSON.stringify([G.charaktere, G.stand.tokens.filter((t) => t.art === "sc"), G.stand.zustaende, G.platzieren,
    !!G.stand.karte, G.stand.zug, G.stand.initiative.eintraege.map((e) => e.name), G.stand.initiative.aktiv]);
  const liste = $("#gruppe-liste");
  if (liste.dataset.sig === sig) return;
  liste.dataset.sig = sig;
  liste.innerHTML = G.charaktere.length ? "" : `<p class="hinweis">Noch keine Charaktere. Lege sie im Reiter „Charaktere“ an.</p>`;
  if (G.charaktere.length > 1) {
    const kopf = document.createElement("div");
    kopf.className = "zeile";
    kopf.innerHTML = `<button type="button" id="gr-zu">Alle einklappen</button><button type="button" id="gr-auf">Alle ausklappen</button>`;
    liste.append(kopf);
    $("#gr-zu", kopf).onclick = () => scKartenEinklappen(true);
    $("#gr-auf", kopf).onclick = () => scKartenEinklappen(false);
  }
  for (const c of G.charaktere) liste.append(scKarte(c));
}

function scZu() {
  try { return JSON.parse(localStorage.getItem("gruppeZu") || "{}"); } catch (e) { return {}; }
}
function scZuSpeichern(m) {
  try { localStorage.setItem("gruppeZu", JSON.stringify(m)); } catch (e) { /* ignorieren */ }
}
function scKartenEinklappen(zu) {
  const m = scZu();
  $$("#gruppe-liste .sc-karte").forEach((el) => {
    el.classList.toggle("zu", zu);
    $(".einklappen", el).textContent = zu ? "▸" : "▾";
    m[el.dataset.char] = zu;
  });
  scZuSpeichern(m);
}

function scKarte(c) {
  const el = $("#tpl-karte-sc").content.firstElementChild.cloneNode(true);
  const t = scToken(c.id);
  el.dataset.char = c.id;
  const istZu = !!scZu()[c.id];
  el.classList.toggle("zu", istZu);
  $(".einklappen", el).textContent = istZu ? "▸" : "▾";
  $(".einklappen", el).onclick = () => {
    const zu = !el.classList.contains("zu");
    el.classList.toggle("zu", zu);
    $(".einklappen", el).textContent = zu ? "▸" : "▾";
    const m = scZu();
    m[c.id] = zu;
    scZuSpeichern(m);
  };
  el.classList.toggle("am-zug", !!t && amZug(t));
  $(".farbpunkt", el).style.background = c.farbe || "#3a7bd5";
  $(".name", el).textContent = c.name;
  $(".klasse", el).textContent = [c.volk, c.klasse].filter(Boolean).join(" · ");

  const knopf = $(".platzieren", el);
  if (t) {
    knopf.textContent = "Von Karte nehmen";
    knopf.onclick = () => api("/api/sc-entfernen", { charId: c.id });
  } else {
    knopf.textContent = G.platzieren === c.id ? "Feld anklicken …" : "Auf Karte setzen";
    knopf.disabled = !G.stand.karte;
    knopf.onclick = () => {
      G.platzieren = G.platzieren === c.id ? null : c.id;
      gruppeZeichnen();
      $("#karte").style.cursor = G.platzieren ? "crosshair" : "";
    };
  }

  const tp = t ? t.tp : c.tp?.aktuell;
  const tpMax = t ? t.tpMax : c.tp?.max;
  const anteil = tpMax ? Math.max(0, Math.min(1, tp / tpMax)) : 0;
  $(".tp-balken > div", el).style.width = anteil * 100 + "%";
  $(".tp-balken > div", el).style.background = anteil > 0.5 ? "var(--gruen)" : anteil > 0.25 ? "var(--gold)" : "var(--rot)";
  $(".tp-balken > span", el).textContent = tpMax ? `${tp ?? "?"} / ${tpMax} TP` : "TP fehlen";
  const tpAendern = async (vorzeichen) => {
    const n = vorzeichen * Math.abs(parseInt($(".tp-betrag", el).value || "1", 10));
    if (t) {
      if (SL) await slBefehl({ op: "tp", id: t.id, delta: n });
      else await api("/api/sc-tp", { id: t.id, delta: n });
    } else if (tpMax != null) {
      await api("/api/charakter", { ...c, tp: { ...c.tp, aktuell: (c.tp.aktuell ?? tpMax) + n } });
    }
  };
  $(".tp-minus", el).onclick = () => tpAendern(-1);
  $(".tp-plus", el).onclick = () => tpAendern(1);

  // Erfahrung und Stufenaufstieg
  const ep = c._ep;
  if (ep) {
    const zeile = document.createElement("div");
    zeile.className = "ep-zeile";
    const anteil = ep.naechste ? Math.min(1, (ep.ep - ep.basis) / (ep.naechste - ep.basis)) : 1;
    zeile.innerHTML = `<span>Stufe ${ep.stufe} · ${ep.ep.toLocaleString("de-DE")} EP${ep.naechste
      ? ` · Stufe ${ep.stufe + 1} ab ${ep.naechste.toLocaleString("de-DE")}` : ""}</span>
      <div class="ep-balken"><div style="width:${anteil * 100}%"></div></div>`;
    if (c.aufstieg && c.aufstieg.status === "eingereicht") {
      zeile.insertAdjacentHTML("beforeend", `<span class="offen">Aufstieg auf Stufe ${c.aufstieg.zielStufe} – wartet auf die Freigabe des Spielleiters …</span>`);
    } else if (ep.aufstiegMoeglich || c.aufstieg) {
      const b = document.createElement("button");
      b.className = "aufsteigen";
      b.textContent = c.aufstieg ? `⬆ Aufstieg auf Stufe ${c.aufstieg.zielStufe} fortsetzen` : `⬆ Stufenaufstieg auf Stufe ${ep.stufe + 1}`;
      b.disabled = imKampf();
      b.title = imKampf() ? "Erst nach dem Kampf" : "";
      b.onclick = () => aufstiegsAssistent(c);
      zeile.append(b);
    }
    $(".tp-zeile", el).after(zeile);
  }

  const rk = c.rk || {};
  $(".werte", el).innerHTML = [
    ["RK", rk.normal], ["Ber.", rk.beruehrung], ["adFF", rk.adff], ["KMB", c.kmb != null ? vz(c.kmb) : null],
    ["KMV", c.kmv], ["Bew.", c.bewegung ? c.bewegung + " m" : null],
  ].filter(([, w]) => w != null).map(([k, w]) => `<span>${k} <b>${esc(w)}</b></span>`).join("")
    + (c.modi || []).filter((m) => m && m.wirkung).map((m) => {
      const r = m.rest == null ? "" : m.rest >= 10 ? ` · ${Math.round(m.rest / 10)} Min.` : ` · ${m.rest} Rd.`;
      return `<span class="modus" title="${esc(JSON.stringify(m.wirkung))}">✦ <b>${esc(m.name)}</b>${r}</span>`;
    }).join("")
    + (c._wirkung && c._wirkung.groesseAendert ? `<span>Größe <b>${esc(c._wirkung.groesse)}</b></span>` : "");

  const wuerfe = $(".wuerfe", el);
  const knopfWurf = (text, ausdruck, grund, klasse = "", extra = {}) => {
    const b = document.createElement("button");
    b.textContent = text;
    b.className = klasse;
    b.title = ausdruck;
    b.onclick = () => wuerfeln(ausdruck, grund, c.name, extra);
    wuerfe.append(b);
    return b;
  };
  const w20 = (bonus) => `1W20${bonus ? vz(bonus) : ""}`;
  const ini = knopfWurf(`Initiative ${vz(c.ini || 0)}`, w20(c.ini || 0), "Initiative", "", { initiative: true, charId: c.id });
  if (imKampf() && G.stand.initiative.eintraege.some((e) => e.name === c.name)) {
    ini.disabled = true;
    ini.title = "schon gewürfelt";
  }
  const rw = c.rw || {};
  knopfWurf(`REF ${vz(rw.REF || 0)}`, w20(rw.REF || 0), "Reflexwurf");
  knopfWurf(`WIL ${vz(rw.WIL || 0)}`, w20(rw.WIL || 0), "Willenswurf");
  knopfWurf(`ZÄH ${vz(rw.ZAEH || 0)}`, w20(rw.ZAEH || 0), "Zähigkeitswurf");
  // Angriffe laufen über den Rechtsklick auf einen Gegner (mit Regelprüfung und Auswertung)
  if ((c.angriffe || []).length) {
    const liste = document.createElement("div");
    liste.className = "angriffe";
    liste.innerHTML = (c.angriffe || []).map((a) =>
      `⚔ ${esc(a.name)} ${vz(a.bonus || 0)}${a.schaden ? ` (${esc(a.schaden)})` : ""}${a.fernkampf ? ` · Fernkampf ${esc(a.inkrement)} m` : ""}`
    ).join("<br>") + `<br><i>Angreifen: Rechtsklick auf einen Gegner auf der Karte.</i>`;
    wuerfe.after(liste);
  }

  // Zauber: antippen, dann (falls nötig) das Ziel auf der Karte anklicken
  if ((c.zauberliste || []).length) {
    const box = document.createElement("div");
    box.className = "zauber";
    if (c._vorbereiten) {  // vorbereitende Zauberkundige (Kleriker, Druide, Magier …): Zauber neu auswählen
      const vb = document.createElement("button");
      vb.className = "vorbereiten";
      vb.textContent = "✎ Zauber vorbereiten";
      vb.disabled = imKampf();
      vb.title = imKampf() ? "Erst nach dem Kampf" : `Zauber neu auswählen (Liste: ${c._zauberKlasse || "?"})`;
      vb.onclick = () => zauberVorbereiten(c);
      box.append(vb);
    }
    let grad = null;
    c.zauberliste.forEach((e, i) => {
      if (e.grad !== grad) {
        grad = e.grad;
        box.insertAdjacentHTML("beforeend", `<span class="grad">Grad ${esc(grad ?? "?")}</span>`);
      }
      const b = document.createElement("button");
      const plaetze = zauberPlaetze(e);
      b.innerHTML = `✦ ${esc(e.name)}<small>${plaetze}</small>`;
      const p = t ? zauberPruefen(t, e, null) : { ok: false, text: "nicht auf der Karte" };
      b.className = p.ok ? "" : "gesperrt";
      b.title = (e._d ? `${zauberBeschreibung(e._d)}\n${e._d.effekt || ""}${zauberPrdZeilen(e._d)}` : "Unbekannter Zauber – der SL wertet aus")
        + (p.ok ? "" : `\n⚠ ${p.text}`);
      b.onclick = () => zauberStarten(c, t, i);
      box.append(b);
    });
    $(".fertigkeit-zeile", el).before(box);
  }

  // Klassenfähigkeiten: antippen, dann (falls nötig) das Ziel auf der Karte anklicken
  if ((c.faehigkeitenListe || []).length) {
    const box = document.createElement("div");
    box.className = "zauber faehigkeiten";
    box.insertAdjacentHTML("beforeend", `<span class="grad">Fähigkeiten</span>`);
    c.faehigkeitenListe.forEach((f, i) => {
      const b = document.createElement("button");
      b.innerHTML = `★ ${esc(f.name)}${f.pro ? `<small>${esc(f.pro)}</small>` : ""}`;
      const p = t ? faehigkeitPruefen(t, f) : { ok: false, text: "nicht auf der Karte" };
      b.className = p.ok ? "" : "gesperrt";
      b.title = `${faehigkeitBeschreibung(f)}
${f.effekt || ""}` + (p.ok ? "" : `
⚠ ${p.text}`);
      b.onclick = () => faehigkeitStarten(c, t, i);
      box.append(b);
    });
    $(".fertigkeit-zeile", el).before(box);
  }

  const fsel = $(".fertigkeit", el);
  const fert = [...(c.fertigkeiten || [])];
  const attr = c.attribute || {};
  ["ST", "GE", "KO", "IN", "WE", "CH"].forEach((k) => attr[k] != null && fert.push({ name: `${k}-Wurf`, bonus: mod(attr[k]) }));
  fsel.innerHTML = fert.map((f, i) => `<option value="${i}">${esc(f.name)} ${vz(f.bonus || 0)}</option>`).join("");
  $(".fertigkeit-wurf", el).onclick = () => {
    const f = fert[fsel.value];
    if (f) wuerfeln(w20(f.bonus || 0), f.name, c.name);
  };

  const zbox = $(".zustaende", el);
  const zsel = $(".zustand-neu", el);
  if (t) {
    for (const z of t.zustaende || []) {
      const b = document.createElement("button");
      b.textContent = z + " ✕";
      b.title = "Zustand entfernen";
      b.onclick = () => zustandUmschalten(t, z);
      zbox.append(b);
    }
    zsel.innerHTML += G.stand.zustaende.filter((z) => !(t.zustaende || []).includes(z)).map((z) => `<option>${esc(z)}</option>`).join("");
    zsel.onchange = () => zsel.value && zustandUmschalten(t, zsel.value);
  } else {
    zsel.parentElement.remove();
  }
  return el;
}

function aufstiegsDialog(c) {
  const ep = c._ep;
  const ziel = ep.stufe + 1;
  const klasse = (c.klasse || "").replace(/\s*\d+\s*$/, "");
  $("#aufstieg-titel").textContent = `${c.name} steigt auf Stufe ${ziel}`;
  $("#a-klasse").value = klasse;
  $("#a-wurf").textContent = `Würfeln: 1W${ep.tw} ${vz(ep.koMod)} KO`;
  $("#a-schnitt").textContent = `Durchschnitt: ${Math.floor(ep.tw / 2) + 1} ${vz(ep.koMod)} KO`;
  const faellig = [`Fertigkeitsränge: ${ep.fertigkeitspunkte} ${vz(ep.inMod)} IN = ${Math.max(1, ep.fertigkeitspunkte + ep.inMod)} (+1 mit Bonus der bevorzugten Klasse)`];
  if (ziel % 2 === 1) faellig.push("Neues Talent (jede ungerade Stufe)");
  if (ziel % 4 === 0) faellig.push("+1 auf ein Attribut (jede 4. Stufe)");
  if ((c.zauberliste || []).length) faellig.push("Neue Zauber bzw. Zauberplätze laut Klassentabelle");
  faellig.push("Neue Klassenmerkmale laut Klassentabelle (trägt der SL ein)");
  $("#a-faellig").innerHTML = faellig.map((f) => `<li>${esc(f)}</li>`).join("");
  $("#a-wuensche").value = "";
  const dlg = $("#aufstieg-dialog");
  dlg.returnValue = "";
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    const f = $("#aufstieg-form");
    await api("/api/aufstieg", {
      charId: c.id,
      klasse: $("#a-klasse").value,
      tpArt: f.tpArt.value,
      bevorzugt: f.bevorzugt.value,
      wuensche: $("#a-wuensche").value,
    });
    meldung(`${c.name}: Aufstieg gesendet – der Spielleiter trägt die Werte ein.`, "info");
  };
  dlg.showModal();
}

function zustandUmschalten(t, name) {
  if (SL) return slBefehl({ op: "zustand", id: t.id, name, an: !(t.zustaende || []).includes(name) });
  return api("/api/sc-zustand", { id: t.id, name });
}

// ------------------------------------------------------------------ Charakter-Editor

let editorId = null;

export function charAuswahlFuellen() {
  const sel = $("#char-auswahl");
  const sig = G.charaktere.map((c) => c.id + ":" + c.name).join("|");
  if (sel.dataset.sig !== sig) {
    sel.innerHTML = G.charaktere.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("") ||
      `<option value="">(keine)</option>`;
    sel.dataset.sig = sig;
  }
  if (editorId === null && G.charaktere.length) editorLaden(G.charaktere[0].id);
  else if (editorId !== null) sel.value = editorId;
}
$("#char-auswahl").addEventListener("change", (ev) => editorLaden(ev.target.value));
$("#char-neu").addEventListener("click", () => editorLaden(""));

const LEER = {
  name: "", klasse: "", volk: "", gesinnung: "", gottheit: "", farbe: "#3a7bd5",
  attribute: { ST: 10, GE: 10, KO: 10, IN: 10, WE: 10, CH: 10 },
  tp: { max: 8, aktuell: 8 }, rk: { normal: 10, beruehrung: 10, adff: 10 },
  ini: 0, gab: 0, kmb: 0, kmv: 10, rw: { REF: 0, WIL: 0, ZAEH: 0 }, bewegung: 9,
  angriffe: [], fertigkeiten: [], zauber: "", faehigkeiten: "", talente: "", ausruestung: "", notizen: "",
};

function editorLaden(id) {
  editorId = id;
  const c = structuredClone(G.charaktere.find((x) => x.id === id) || LEER);
  if (id) $("#char-auswahl").value = id;
  const f = $("#char-form");
  const feld = (pfad, label, typ = "text") => {
    const wert = pfad.split(".").reduce((o, k) => o?.[k], c);
    return `<label>${label}<input type="${typ}" data-pfad="${pfad}" value="${esc(wert ?? "")}"></label>`;
  };
  const zahl = (p, l) => feld(p, l, "number");
  const zeilenAngriff = (a = {}) => `<tr>
      <td><input data-a="name" value="${esc(a.name)}" placeholder="Waffe"></td>
      <td style="width:56px"><input data-a="bonus" type="number" value="${esc(a.bonus ?? 0)}"></td>
      <td style="width:84px"><input data-a="schaden" value="${esc(a.schaden)}" placeholder="1W8+1"></td>
      <td style="width:76px"><input data-a="krit" value="${esc(a.krit)}" placeholder="19-20/x2"></td>
      <td style="width:28px"><button type="button" class="weg">✕</button></td></tr>`;
  // weitere Angaben (Pool, spontan, Domäne, Ziel …) unsichtbar mitführen, damit Speichern sie nicht verliert
  const zauberExtra = (z) => JSON.stringify(Object.fromEntries(Object.entries(z)
    .filter(([k]) => !["_d", "name", "grad", "proTag", "verbraucht"].includes(k))));
  const zeilenZauber = (z = {}) => `<tr>
      <td><input data-z="name" list="zauber-namen" value="${esc(z.name)}" placeholder="Zauber">
        <input type="hidden" data-z="extra" value="${esc(zauberExtra(z))}"></td>
      <td style="width:48px"><input data-z="grad" type="number" min="0" max="9" value="${esc(z.grad ?? 0)}" title="Grad"></td>
      <td style="width:54px"><input data-z="proTag" type="number" min="0" value="${esc(z.proTag ?? "")}" placeholder="∞" title="pro Tag (leer = beliebig oft)"></td>
      <td style="width:54px"><input data-z="verbraucht" type="number" min="0" value="${esc(z.verbraucht ?? 0)}" title="heute verbraucht"></td>
      <td style="width:28px"><button type="button" class="weg">✕</button></td></tr>`;
  const zeilenFert = (s = {}) => `<tr>
      <td><input data-s="name" value="${esc(s.name)}" placeholder="Fertigkeit"></td>
      <td style="width:64px"><input data-s="bonus" type="number" value="${esc(s.bonus ?? 0)}"></td>
      <td style="width:28px"><button type="button" class="weg">✕</button></td></tr>`;
  f.innerHTML = `
    <fieldset><legend>Grunddaten</legend>
      <div class="raster">
        ${feld("name", "Name")}${feld("klasse", "Klasse & Stufe")}${feld("volk", "Volk")}
        ${feld("gesinnung", "Gesinnung")}${feld("gottheit", "Gottheit")}${feld("farbe", "Farbe", "color")}
        ${zahl("stufe", "Stufe")}${zahl("ep", "Erfahrung (EP)")}
      </div>
    </fieldset>
    <fieldset><legend>Attribute</legend>
      <div class="raster">${["ST", "GE", "KO", "IN", "WE", "CH"].map((k) => zahl("attribute." + k, k)).join("")}</div>
    </fieldset>
    <fieldset><legend>Kampf</legend>
      <div class="raster">
        ${zahl("tp.max", "TP max")}${zahl("tp.aktuell", "TP aktuell")}${zahl("rk.normal", "RK")}
        ${zahl("rk.beruehrung", "RK Berührung")}${zahl("rk.adff", "RK auf d. f. Fuß")}${zahl("ini", "Initiative")}
        ${zahl("gab", "GAB")}${zahl("kmb", "KMB")}${zahl("kmv", "KMV")}
        ${zahl("rw.REF", "Reflex")}${zahl("rw.WIL", "Wille")}${zahl("rw.ZAEH", "Zähigkeit")}
        ${zahl("bewegung", "Bewegung (m)")}
      </div>
    </fieldset>
    <fieldset><legend>Angriffe</legend>
      <table id="t-angriffe">${(c.angriffe || []).map(zeilenAngriff).join("")}</table>
      <button type="button" id="plus-angriff">+ Angriff</button>
    </fieldset>
    <fieldset><legend>Fertigkeiten (Gesamtbonus)</legend>
      <table id="t-fert">${(c.fertigkeiten || []).map(zeilenFert).join("")}</table>
      <button type="button" id="plus-fert">+ Fertigkeit</button>
    </fieldset>
    <fieldset><legend>Zauber</legend>
      <div class="raster">
        ${zahl("zauberstufe", "Zauberstufe")}
        <label>Zauberattribut<select data-pfad="zauberattribut">
          ${["", "IN", "WE", "CH"].map((a) => `<option value="${a}" ${(c.zauberattribut || "") === a ? "selected" : ""}>${a || "automatisch"}</option>`).join("")}
        </select></label>
        <label title="Aus dieser Klassenliste schlägt „Zauber vorbereiten“ die Zauber vor; Grade richten sich danach">Zauberliste<select data-pfad="zauberKlasse">
          <option value="">automatisch${!c.zauberKlasse && c._zauberKlasse ? ` (${esc(c._zauberKlasse)})` : ""}</option>
          ${zauberListen().map((k) => `<option value="${esc(k)}" ${c.zauberKlasse === k ? "selected" : ""}>${esc(k)}</option>`).join("")}
        </select></label>
      </div>
      <table id="t-zauber"><tr><td class="hinweis">Name</td><td class="hinweis">Grad</td><td class="hinweis">pro Tag</td><td class="hinweis">verbr.</td><td></td></tr>
        ${(c.zauberliste || []).map(zeilenZauber).join("")}</table>
      <button type="button" id="plus-zauber">+ Zauber</button>
      <datalist id="zauber-namen">${zauberDb.map(zauberOption).join("")}</datalist>
      <small class="hinweis">Vorschläge: alle Zauber aus dem PRD; Zauber mit hinterlegter Spielmechanik wertet das Tool selbst aus, die übrigen der Spielleiter. Leere Zauberstufe = Klassenstufe.</small>
    </fieldset>
    ${[["zauber", "Zauber-Notizen"],["faehigkeiten", "Besondere Fähigkeiten"], ["talente", "Talente"],
       ["ausruestung", "Ausrüstung"], ["notizen", "Notizen"]].map(([k, l]) =>
      `<fieldset><legend>${l}</legend><textarea data-pfad="${k}">${esc(c[k] || "")}</textarea></fieldset>`).join("")}
    <div class="aktionen">
      <button type="submit" class="primaer">Speichern</button>
      ${id ? `<button type="button" id="char-loeschen" class="gefahr">Löschen</button>` : ""}
    </div>`;
  // Abschnitte einklappbar machen (Zustand wird im Browser gemerkt)
  let sekOffen = {};
  try { sekOffen = JSON.parse(localStorage.getItem("charSektionen") || "{}"); } catch (e) { sekOffen = {}; }
  const sekSpeichern = () => { try { localStorage.setItem("charSektionen", JSON.stringify(sekOffen)); } catch (e) { /* ignorieren */ } };
  $$("fieldset", f).forEach((fs) => {
    const titel = fs.querySelector("legend").textContent;
    const d = document.createElement("details");
    d.className = "fs";
    const sum = document.createElement("summary");
    sum.textContent = titel;
    fs.querySelector("legend").remove();
    d.append(sum, ...fs.childNodes);
    d.open = titel in sekOffen ? sekOffen[titel] : ["Kampf", "Angriffe"].includes(titel);
    d.addEventListener("toggle", () => { sekOffen[titel] = d.open; sekSpeichern(); });
    fs.replaceWith(d);
  });
  f.insertAdjacentHTML("afterbegin", `<div class="zeile"><button type="button" id="sek-zu">Alle einklappen</button><button type="button" id="sek-auf">Alle ausklappen</button></div>`);
  f.onclick = (ev) => {
    if (ev.target.id === "sek-zu" || ev.target.id === "sek-auf") $$("details.fs", f).forEach((d) => (d.open = ev.target.id === "sek-auf"));
    if (ev.target.classList.contains("weg")) ev.target.closest("tr").remove();
    if (ev.target.id === "plus-angriff") $("#t-angriffe").insertAdjacentHTML("beforeend", zeilenAngriff());
    if (ev.target.id === "plus-fert") $("#t-fert").insertAdjacentHTML("beforeend", zeilenFert());
    if (ev.target.id === "plus-zauber") $("#t-zauber").insertAdjacentHTML("beforeend", zeilenZauber());
    if (ev.target.id === "char-loeschen" && confirm(`${c.name} wirklich löschen?`)) {
      api("/api/charakter-loeschen", { id }).then(() => { editorId = null; });
    }
  };
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const neu = structuredClone(c);
    for (const inp of $$("[data-pfad]", f)) {
      const teile = inp.dataset.pfad.split(".");
      let o = neu;
      teile.slice(0, -1).forEach((k) => (o = o[k] ??= {}));
      o[teile.at(-1)] = inp.type === "number" ? (inp.value === "" ? null : Number(inp.value)) : inp.value;
    }
    neu.angriffe = $$("#t-angriffe tr", f).map((tr) => {
      const a = {};
      $$("[data-a]", tr).forEach((i) => (a[i.dataset.a] = i.type === "number" ? Number(i.value) : i.value.trim()));
      return a;
    }).filter((a) => a.name);
    neu.fertigkeiten = $$("#t-fert tr", f).map((tr) => ({
      name: $("[data-s=name]", tr).value.trim(), bonus: Number($("[data-s=bonus]", tr).value),
    })).filter((s) => s.name);
    neu.zauberliste = $$("#t-zauber tr", f).filter((tr) => $("[data-z=name]", tr)).map((tr) => {
      const wert = (k) => $(`[data-z=${k}]`, tr).value.trim();
      const db = zauberDb.find((z) => z.name.toLowerCase() === wert("name").toLowerCase());
      return {
        ...JSON.parse(wert("extra") || "{}"),
        name: db ? db.name : wert("name"),
        grad: wert("grad") === "" ? zauberGradFuer(db, neu.zauberKlasse, c._zauberKlasse, neu.klasse) ?? 0 : Number(wert("grad")),
        proTag: wert("proTag") === "" ? null : Number(wert("proTag")),
        verbraucht: Number(wert("verbraucht") || 0),
      };
    }).filter((z) => z.name);
    if (!neu.name) return meldung("Name fehlt");
    const gespeichert = await api("/api/charakter", neu);
    editorId = gespeichert.id;
    meldung(`${gespeichert.name} gespeichert`, "info");
  };
}
