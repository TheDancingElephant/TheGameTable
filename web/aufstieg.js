"use strict";
// Stufenaufstiegs-Assistent: TP -> Fertigkeiten -> Talent/Attribut -> Zauber -> Zusammenfassung.
// Benötigt app.js (api, esc, $, meldung). Regeln und Prüfungen liegen serverseitig (aufstieg.py).

const AUF_SCHRITTE = ["Trefferpunkte", "Fertigkeiten", "Talent & Attribut", "Zauber", "Zusammenfassung"];
let aufZauberKatalog = null;

async function aufstiegsAssistent(c) {
  const dlg = document.createElement("dialog");
  dlg.id = "aufstieg-assistent";
  document.body.append(dlg);
  dlg.addEventListener("close", () => dlg.remove());
  const S = { c, schritt: 0, klasse: "", antrag: null, plan: null, auf: null };
  const laden = async () => {
    const r = await api("/api/aufstieg-plan", { charId: c.id, ...aufAnfrage(S) });
    S.plan = r.plan;
    S.auf = r.aufstieg;
    return r;
  };
  try {
    await laden();
  } catch (e) {
    dlg.remove();
    return;
  }
  if (!aufZauberKatalog) aufZauberKatalog = await fetch("/api/zauber").then((r) => r.json()).catch(() => []);
  S.klasse = S.plan.klasse || "";
  S.vorlagen = { ...S.plan.vorlagenMap };
  const p = S.plan;
  // Antrag vorbelegen (neu oder vom Spielleiter zurückgegeben)
  S.antrag = S.auf.antrag || {
    bevorzugt: "tp", gab: p.gab, rw: { ...p.rw }, raenge: {}, extraFp: 0, talente: [], attribut: "",
    zauber: { neu: [], proTag: {}, buch: [] }, notiz: "",
  };
  S.antrag.zauber = S.antrag.zauber || { neu: [], proTag: {}, buch: [] };
  S.dlg = dlg;
  aufZeichnen(S);
  dlg.showModal();
}

// Klasse und Regelvorlagen für die Server-Anfragen (leer = Server wählt selbst)
function aufAnfrage(S) {
  if (!S.klasse || !S.vorlagen) return {};
  return { klasse: S.klasse, vorlage: S.klasse in S.vorlagen ? S.vorlagen[S.klasse] : null, vorlagen: S.vorlagen };
}
const aufKlassenText = (p) => `${esc(p.klasse)} ${p.klassenStufeAlt} → ${p.klassenStufe} (Charakterstufe ${p.zielStufe})`;

function aufBudget(S) {
  const p = S.plan, a = S.antrag;
  return Math.max(1, p.fp.klasse + p.fp.intMod) + p.fp.volk + (a.bevorzugt === "fertigkeit" ? 1 : 0) + (+a.extraFp || 0);
}
const aufVerteilt = (S) => Object.values(S.antrag.raenge).reduce((s, v) => s + (+v || 0), 0);

function aufZeichnen(S) {
  const { dlg, plan: p, antrag: a, auf } = S;
  const kopf = `<h2>${esc(S.c.name)} steigt auf Stufe ${p.zielStufe}</h2>
    <p class="auf-klassenzeile">${aufKlassenText(p)}</p>
    <ol class="auf-schritte">${AUF_SCHRITTE.map((n, i) =>
      `<li class="${i === S.schritt ? "aktiv" : i < S.schritt ? "fertig" : ""}">${i + 1}. ${n}</li>`).join("")}</ol>
    ${auf.kommentar ? `<p class="auf-kommentar">Rückfrage des Spielleiters: ${esc(auf.kommentar)}</p>` : ""}`;
  dlg.innerHTML = `<div class="auf-form">${kopf}<div class="auf-körper"></div>
    <div class="zeile auf-knöpfe"><button data-a="abbrechen">Schließen</button><span class="auf-platz"></span>
    <button data-a="zurück" ${S.schritt === 0 ? "disabled" : ""}>‹ Zurück</button>
    <button data-a="weiter" class="primaer">${S.schritt === 4 ? "Abschicken" : "Weiter ›"}</button></div></div>`;
  const koerper = $(".auf-körper", dlg);
  [aufTP, aufFert, aufTalent, aufZauber, aufSumme][S.schritt](S, koerper);
  dlg.onclick = async (ev) => {
    const b = ev.target.closest("button[data-a]");
    if (!b) return;
    const was = b.dataset.a;
    if (was === "abbrechen") return dlg.close();
    if (was === "zurück") { S.schritt--; return aufZeichnen(S); }
    if (was === "weiter") {
      if (S.schritt === 0 && !S.auf.tp) return meldung("Erst Trefferpunkte würfeln oder den Durchschnitt wählen.");
      if (S.schritt === 4) {
        try {
          await api("/api/aufstieg-senden", { charId: S.c.id, ...aufAnfrage(S), antrag: S.antrag });
        } catch (e) { return; }
        meldung(`${S.c.name}: Aufstieg abgeschickt – der Spielleiter prüft und gibt frei.`, "info");
        return dlg.close();
      }
      S.schritt++;
      aufZeichnen(S);
    }
  };
}

// ---- Schritt 1: Trefferpunkte, Klasse, Grundwerte
function aufTP(S, el) {
  const { plan: p, antrag: a, auf } = S;
  const tpTeil = auf.tp
    ? `<p class="auf-erg">Trefferpunkte: <strong>+${auf.tp.plus}</strong> (${esc(auf.tp.text)})${a.bevorzugt === "tp" ? " + 1 bevorzugte Klasse" : ""}</p>`
    : `<div class="zeile"><button data-tp="wurf" class="primaer">🎲 Würfeln: 1W${p.tw} ${p.koMod >= 0 ? "+" : "−"} ${Math.abs(p.koMod)} KO</button>
       <button data-tp="schnitt">Durchschnitt: ${Math.floor(p.tw / 2) + 1} ${p.koMod >= 0 ? "+" : "−"} ${Math.abs(p.koMod)} KO</button></div>
       <small class="hinweis">Das Ergebnis gilt – der Wurf wird auf dem Server festgehalten.</small>`;
  el.innerHTML = `
    <fieldset><legend>Welche Klasse steigt?</legend>
      <label>Klasse
        <select id="auf-klasse">${p.klassen.map((k) => `<option value="${esc(k.name)}" ${k.name === p.klasse ? "selected" : ""}>${esc(k.name)} ${k.stufe}</option>`).join("")}
          ${p.neueKlasse ? `<option value="${esc(p.klasse)}" selected>${esc(p.klasse)} (neu)</option>` : ""}
          <option value="__neu__">Neue Klasse …</option></select></label>
      <p class="auf-erg">${aufKlassenText(p)}</p>
      <table class="auf-tabelle-klein"><tr><th>Klasse</th><th>Regelvorlage (TW, GAB, Rettungswürfe, Zauberplätze)</th></tr>
        ${[...p.klassen.map((k) => k.name), ...(p.neueKlasse ? [p.klasse] : [])].map((n) =>
          `<tr><td>${esc(n)}</td><td><select data-vl="${esc(n)}"><option value="">– keine, selbst eintragen –</option>
          ${p.vorlagen.map((v) => `<option ${v === (S.vorlagen[n] || "") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></td></tr>`).join("")}</table>
      <small class="hinweis">${p.vorlageBekannt ? `TW W${p.tw}, ${p.fp.klasse} Fertigkeitspunkte.` : "Für die steigende Klasse ist keine Vorlage gewählt: Trefferwürfel (W8 angenommen), GAB und Rettungswürfe unten selbst eintragen und mit dem Spielleiter klären."}
      ${p.klassen.length > 1 || p.neueKlasse ? " Mehrere Klassen: GAB und Rettungswürfe werden anteilig addiert und erst am Ende abgerundet (Alternativregel); der Spielleiter prüft die Vorlagen (z. B. „Entfesselter Mönch“)." : ""}
      ${auf.tp ? ` Der TP-Wurf (${esc(auf.tp.text)}) bleibt bestehen, auch wenn der Trefferwürfel der Klasse ein anderer ist.` : ""}</small></fieldset>
    <fieldset><legend>Trefferpunkte</legend>${tpTeil}</fieldset>
    <fieldset><legend>Bonus der bevorzugten Klasse</legend>
      ${[["tp", "+1 Trefferpunkt"], ["fertigkeit", "+1 Fertigkeitsrang"], ["", "keiner"]].map(([v, t]) =>
        `<label class="option"><input type="radio" name="bev" value="${v}" ${a.bevorzugt === v ? "checked" : ""}> ${t}</label>`).join("")}
    </fieldset>
    <fieldset><legend>Grundwerte dieser Stufe (Klassentabelle)</legend>
      <div class="auf-zahlen">
        <label>GAB +<input type="number" id="auf-gab" value="${a.gab}" min="0" max="1"></label>
        <label>Zähigkeit +<input type="number" id="auf-zaeh" value="${a.rw.ZAEH}" min="0" max="2"></label>
        <label>Reflex +<input type="number" id="auf-ref" value="${a.rw.REF}" min="0" max="2"></label>
        <label>Willen +<input type="number" id="auf-wil" value="${a.rw.WIL}" min="0" max="2"></label>
      </div></fieldset>`;
  el.querySelectorAll("[data-tp]").forEach((b) => (b.onclick = async () => {
    await api("/api/aufstieg-tp", { charId: S.c.id, ...aufAnfrage(S), art: b.dataset.tp });
    const r = await api("/api/aufstieg-plan", { charId: S.c.id, ...aufAnfrage(S) });
    S.plan = r.plan; S.auf = r.aufstieg;
    aufZeichnen(S);
  }));
  const neuLaden = async () => {
    const r = await api("/api/aufstieg-plan", { charId: S.c.id, ...aufAnfrage(S) });
    S.plan = r.plan;
    S.vorlagen = { ...S.vorlagen, ...S.plan.vorlagenMap };
    S.antrag.gab = S.plan.gab; S.antrag.rw = { ...S.plan.rw };
    aufZeichnen(S);
  };
  $("#auf-klasse", el).onchange = (ev) => {
    let n = ev.target.value;
    if (n === "__neu__") {
      n = (prompt("Name der neuen Klasse:") || "").trim();
      if (!n) return aufZeichnen(S);
    }
    S.klasse = n;
    neuLaden();
  };
  el.querySelectorAll("select[data-vl]").forEach((sel) => (sel.onchange = () => { S.vorlagen[sel.dataset.vl] = sel.value; neuLaden(); }));
  el.querySelectorAll("input[name=bev]").forEach((r) => (r.onchange = () => { a.bevorzugt = r.value; aufZeichnen(S); }));
  const num = (id, set) => { $(id, el).onchange = (ev) => set(+ev.target.value || 0); };
  num("#auf-gab", (v) => (a.gab = v)); num("#auf-zaeh", (v) => (a.rw.ZAEH = v));
  num("#auf-ref", (v) => (a.rw.REF = v)); num("#auf-wil", (v) => (a.rw.WIL = v));
}

// ---- Schritt 2: Fertigkeitspunkte
function aufFert(S, el) {
  const { plan: p, antrag: a } = S;
  const budget = aufBudget(S);
  const filter = S.filter || "";
  const zeilen = p.fertigkeiten.filter((f) => f.name.toLowerCase().includes(filter.toLowerCase())).map((f) => {
    const neu = +a.raenge[f.name] || 0;
    const ueber = f.raenge + neu > p.zielStufe;
    return `<tr class="${f.klasse ? "klassenfert" : ""} ${neu ? "gewählt" : ""}">
      <td>${f.klasse ? "★ " : ""}${esc(f.name)}</td><td>${f.bonus >= 0 ? "+" : ""}${f.bonus}</td>
      <td class="${ueber ? "zuviel" : ""}">${f.geschaetzt ? "≈" : ""}${f.raenge} / ${p.zielStufe}</td>
      <td class="auf-ct"><button data-f="${esc(f.name)}" data-d="-1" ${neu ? "" : "disabled"}>−</button>
      <b>${neu ? "+" + neu : ""}</b><button data-f="${esc(f.name)}" data-d="1">+</button></td></tr>`;
  }).join("");
  const rest = budget - aufVerteilt(S);
  el.innerHTML = `
    <div class="auf-leiste ${rest < 0 ? "zuviel" : ""}">Fertigkeitspunkte: <strong>${rest}</strong> von ${budget} übrig
      <small>(Klasse ${p.fp.klasse} ${p.fp.intMod >= 0 ? "+" : "−"} ${Math.abs(p.fp.intMod)} IN${p.fp.volk ? " + 1 Mensch" : ""}${a.bevorzugt === "fertigkeit" ? " + 1 bevorzugte Klasse" : ""}${+a.extraFp ? ` + ${a.extraFp} sonstige` : ""})</small>
      <label class="auf-extra">weitere Punkte <input type="number" id="auf-extra" value="${+a.extraFp || 0}" min="0" max="9"></label></div>
    <input type="search" id="auf-such" placeholder="Fertigkeit suchen …" value="${esc(filter)}">
    <div class="auf-tabelle"><table><thead><tr><th>Fertigkeit</th><th>Bonus</th><th>Ränge ≈ / Max</th><th>Neu</th></tr></thead><tbody>${zeilen}</tbody></table></div>
    <small class="hinweis">★ = Klassenfertigkeit (+3 beim ersten Rang). Höchstens ${p.zielStufe} Ränge je Fertigkeit; „≈“ = Ränge aus dem Bonus geschätzt – nach dem Aufstieg werden sie gespeichert.</small>`;
  el.querySelectorAll("button[data-f]").forEach((b) => (b.onclick = () => {
    const n = b.dataset.f;
    const v = Math.max(0, (+a.raenge[n] || 0) + +b.dataset.d);
    if (v) a.raenge[n] = v; else delete a.raenge[n];
    const sc = $(".auf-tabelle", el).scrollTop;
    aufZeichnen(S);
    $(".auf-tabelle", S.dlg).scrollTop = sc;
  }));
  $("#auf-extra", el).onchange = (ev) => { a.extraFp = +ev.target.value || 0; aufZeichnen(S); };
  $("#auf-such", el).oninput = (ev) => {
    S.filter = ev.target.value; const pos = ev.target.selectionStart; aufZeichnen(S);
    const i = $("#auf-such", S.dlg); i.focus(); i.setSelectionRange(pos, pos);
  };
}

// ---- Schritt 3: Talent, Attribut
function aufVorausText(S, name) {
  const k = S.plan.talenteKatalog.find((t) => t.name.toLowerCase() === name.split("(")[0].trim().toLowerCase());
  if (!k) return name ? "Nicht im Katalog – Voraussetzungen prüft der Spielleiter." : "";
  const probleme = [];
  const at = { ...S.plan.attribute };
  if (S.antrag.attribut) at[S.antrag.attribut] = (at[S.antrag.attribut] || 10) + 1;
  for (const [x, mn] of Object.entries(k.pruef.attr || {})) if ((at[x] || 0) < mn) probleme.push(`${x} ${mn} fehlt`);
  const gab = S.plan.gabGesamt + (+S.antrag.gab || 0);
  if (k.pruef.gab && gab < k.pruef.gab) probleme.push(`GAB +${k.pruef.gab} fehlt`);
  if (k.pruef.stufe && S.plan.zielStufe < k.pruef.stufe) probleme.push(`Stufe ${k.pruef.stufe} fehlt`);
  return `${k.voraus ? "Voraussetzung: " + esc(k.voraus) + ". " : "Keine Voraussetzung. "}`
    + (probleme.length ? `<b class="zuviel">✗ ${esc(probleme.join(", "))}</b>` : `<b class="gut">✓ erfüllt (Rest prüft der Spielleiter)</b>`);
}

function aufTalent(S, el) {
  const { plan: p, antrag: a } = S;
  a.talente = a.talente.slice(0, p.talente);
  while (a.talente.length < p.talente) a.talente.push("");
  const talentTeil = p.talente
    ? a.talente.map((t, i) => `<div class="auf-talent"><label>Talent ${i + 1}
        <input list="auf-tal-liste" data-t="${i}" value="${esc(t)}" placeholder="Name wählen oder eintippen"></label>
        <small class="hinweis" id="auf-vor-${i}">${aufVorausText(S, t)}</small></div>`).join("")
    : `<p>Auf Stufe ${p.zielStufe} gibt es kein neues allgemeines Talent (jede ungerade Stufe).</p>`;
  const attrTeil = p.attributPunkt
    ? `<fieldset><legend>Attributspunkt (Stufe ${p.zielStufe})</legend><div class="auf-zahlen">${["ST", "GE", "KO", "IN", "WE", "CH"].map((x) =>
        `<label class="option"><input type="radio" name="attr" value="${x}" ${a.attribut === x ? "checked" : ""}> ${x} ${p.attribute[x]} → ${p.attribute[x] + 1}</label>`).join("")}</div>
        <small class="hinweis">Abgeleitete Werte (Modifikator, Fertigkeiten, TP bei KO …) passt das Tool bei der Freigabe an.</small></fieldset>`
    : `<p class="hinweis">Attributspunkt gibt es auf Stufe 4, 8, 12, 16 und 20.</p>`;
  el.innerHTML = `<fieldset><legend>Talent</legend>${talentTeil}
      <datalist id="auf-tal-liste">${p.talenteKatalog.map((t) => `<option value="${esc(t.name)}">${esc(t.voraus)}</option>`).join("")}</datalist>
      <small class="hinweis">Klassentalente (z. B. Bonustalent des Magiers auf Stufe 5/10/15/20) sind mitgezählt, wenn die Klasse bekannt ist.</small></fieldset>${attrTeil}`;
  el.querySelectorAll("input[data-t]").forEach((i) => (i.oninput = () => {
    a.talente[+i.dataset.t] = i.value;
    $(`#auf-vor-${i.dataset.t}`, el).innerHTML = aufVorausText(S, i.value);
  }));
  el.querySelectorAll("input[name=attr]").forEach((r) => (r.onchange = () => {
    a.attribut = r.value;
    el.querySelectorAll("input[data-t]").forEach((i) => ($(`#auf-vor-${i.dataset.t}`, el).innerHTML = aufVorausText(S, i.value)));
  }));
}

// ---- Schritt 4: Zauber
function aufZauber(S, el) {
  const { plan: p, antrag: a } = S;
  const z = a.zauber;
  const summe = {};
  const proTag = (e) => (e.name in z.proTag ? z.proTag[e.name] : e.proTag);
  p.zauberliste.forEach((e) => { if (e.grad >= 1 && proTag(e) != null && proTag(e) !== "") summe[e.grad] = (summe[e.grad] || 0) + +proTag(e); });
  z.neu.forEach((e) => { if (e.grad >= 1 && e.proTag) summe[e.grad] = (summe[e.grad] || 0) + +e.proTag; });
  const grade = p.plaetzeNeu ? Object.keys(p.plaetzeNeu).map(Number) : [];
  const kopf = p.plaetzeNeu
    ? `<table class="auf-slots"><tr><th>Grad</th>${grade.map((g) => `<th>${g}</th>`).join("")}</tr>
        <tr><td>Plätze (${esc(p.zauberattribut)}-Bonus eingerechnet)</td>${grade.map((g) => {
          const alt = p.plaetzeAlt && p.plaetzeAlt[g] != null ? p.plaetzeAlt[g] : 0;
          const neu = p.plaetzeNeu[g];
          return `<td>${neu}${neu !== alt ? ` <small>(+${neu - alt})</small>` : ""}</td>`; }).join("")}</tr>
        <tr><td>vorbereitet</td>${grade.map((g) => `<td class="${(summe[g] || 0) > p.plaetzeNeu[g] ? "zuviel" : (summe[g] || 0) < p.plaetzeNeu[g] ? "frei" : "gut"}">${summe[g] || 0}</td>`).join("")}</tr></table>
        <small class="hinweis">Alle Plätze sind schon einem Zauber zugeordnet, wenn „vorbereitet“ grün ist. Rot = zu viele, orange = noch frei.</small>`
    : `<p class="hinweis">Für diese Klasse kennt das Tool keine Zauberplatz-Tabelle. Trage Plätze pro Tag selbst ein; der Spielleiter prüft nach der Klassentabelle.</p>`;
  const zeilen = p.zauberliste.filter((e) => e.grad >= 1).map((e) => `<tr><td>Grad ${e.grad}</td><td>${esc(e.name)}</td>
    <td><input type="number" min="0" max="9" data-zn="${esc(e.name)}" value="${proTag(e) ?? ""}" style="width:56px"> ×/Tag</td></tr>`).join("");
  const neu = z.neu.map((e, i) => `<tr><td><input type="number" min="0" max="${p.maxGrad}" data-nn="${i}" data-k="grad" value="${e.grad}" style="width:48px"></td>
    <td><input list="auf-zl" data-nn="${i}" data-k="name" value="${esc(e.name)}" placeholder="Zaubername"></td>
    <td><input type="number" min="0" max="9" data-nn="${i}" data-k="proTag" value="${e.proTag ?? ""}" style="width:56px"> ×/Tag <button data-del="${i}">✕</button></td></tr>`).join("");
  const buch = p.hatBuch ? `<fieldset><legend>Zauberbuch (neu eingetragene Zauber, z. B. 2 gratis pro Magier-Stufe)</legend>
      ${z.buch.map((e, i) => `<div class="zeile"><input type="number" min="0" max="${p.maxGrad}" data-bb="${i}" data-k="grad" value="${e.grad}" style="width:48px">
        <input list="auf-zl" data-bb="${i}" data-k="name" value="${esc(e.name)}" placeholder="Zaubername"><button data-delb="${i}">✕</button></div>`).join("")}
      <button id="auf-buch-neu">+ Zauber ins Zauberbuch</button></fieldset>` : "";
  el.innerHTML = `${kopf}
    <fieldset><legend>Vorbereitete Zauber pro Tag ändern</legend>
      <table class="auf-tabelle-klein">${zeilen || "<tr><td>Keine Zauber mit Tageslimit.</td></tr>"}</table></fieldset>
    <fieldset><legend>Neue Zauber (in die Zauberliste)</legend>
      <table class="auf-tabelle-klein">${neu}</table><button id="auf-zneu">+ Zauber hinzufügen</button></fieldset>
    ${buch}
    <datalist id="auf-zl">${aufZauberKatalog.map(zauberOption).join("")}</datalist>
    <label>Anmerkung an den Spielleiter (Klassenmerkmale, Fragen …)
      <textarea id="auf-notiz" rows="3" placeholder="z. B. neue Klassenfähigkeit, Unklarheiten bei Zaubern …">${esc(a.notiz || "")}</textarea></label>`;
  el.querySelectorAll("[data-zn]").forEach((i) => (i.onchange = () => { z.proTag[i.dataset.zn] = i.value === "" ? null : +i.value; aufZeichnen(S); }));
  el.querySelectorAll("[data-nn]").forEach((i) => (i.onchange = () => {
    const e = z.neu[+i.dataset.nn];
    e[i.dataset.k] = i.dataset.k === "name" ? i.value : +i.value;
    if (i.dataset.k === "name") { const k = aufZauberKatalog.find((x) => x.name.toLowerCase() === i.value.toLowerCase()); if (k) e.grad = zauberGradFuer(k, S.c.zauberKlasse, S.klasse, S.c._zauberKlasse); }
    aufZeichnen(S);
  }));
  el.querySelectorAll("[data-bb]").forEach((i) => (i.onchange = () => {
    const e = z.buch[+i.dataset.bb];
    e[i.dataset.k] = i.dataset.k === "name" ? i.value : +i.value;
    if (i.dataset.k === "name") { const k = aufZauberKatalog.find((x) => x.name.toLowerCase() === i.value.toLowerCase()); if (k) e.grad = zauberGradFuer(k, S.c.zauberKlasse, S.klasse, S.c._zauberKlasse); }
    aufZeichnen(S);
  }));
  el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { z.neu.splice(+b.dataset.del, 1); aufZeichnen(S); }));
  el.querySelectorAll("[data-delb]").forEach((b) => (b.onclick = () => { z.buch.splice(+b.dataset.delb, 1); aufZeichnen(S); }));
  $("#auf-zneu", el).onclick = () => { z.neu.push({ name: "", grad: 1, proTag: 1 }); aufZeichnen(S); };
  const bn = $("#auf-buch-neu", el);
  if (bn) bn.onclick = () => { z.buch.push({ name: "", grad: 1 }); aufZeichnen(S); };
  $("#auf-notiz", el).onchange = (ev) => (a.notiz = ev.target.value);
}

// ---- Schritt 5: Zusammenfassung
function aufSumme(S, el) {
  const { plan: p, antrag: a, auf, c } = S;
  const z = a.zauber;
  const r = Object.entries(a.raenge).filter(([, v]) => +v);
  const zeilen = [
    ["Klasse", aufKlassenText(p)],
    ["Trefferpunkte", auf.tp ? `+${auf.tp.plus + (a.bevorzugt === "tp" ? 1 : 0)} (${esc(auf.tp.text)}${a.bevorzugt === "tp" ? ", +1 bevorzugte Klasse" : ""}) → max. ${(c.tp?.max || 0) + auf.tp.plus + (a.bevorzugt === "tp" ? 1 : 0)}` : "<b class='zuviel'>fehlt</b>"],
    ["GAB / Rettungswürfe", `GAB +${a.gab}, Zäh +${a.rw.ZAEH}, Ref +${a.rw.REF}, Wil +${a.rw.WIL}`],
    ["Fertigkeitsränge", r.length ? r.map(([k, v]) => `${esc(k)} +${v}`).join(", ") : "–"],
    ["Verteilt", `${aufVerteilt(S)} von ${aufBudget(S)} Punkten`],
    ["Talente", a.talente.filter((t) => t.trim()).map(esc).join(", ") || "–"],
    ["Attribut", a.attribut ? `+1 ${a.attribut}` : "–"],
    ["Neue Zauber", z.neu.filter((e) => e.name).map((e) => `${esc(e.name)} (Grad ${e.grad}${e.proTag ? `, ${e.proTag}×` : ""})`).join(", ") || "–"],
    ["Geänderte Plätze", Object.entries(z.proTag).map(([k, v]) => `${esc(k)} → ${v ?? "–"}×`).join(", ") || "–"],
    ["Zauberbuch", z.buch.filter((e) => e.name).map((e) => `${esc(e.name)} (${e.grad})`).join(", ") || "–"],
  ];
  z.neu = z.neu.filter((e) => e.name);
  z.buch = z.buch.filter((e) => e.name);
  a.talente = a.talente.filter((t) => t.trim());
  el.innerHTML = `<table class="auf-summe">${zeilen.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}</table>
    <p class="hinweis">Mit „Abschicken“ geht der Antrag an den Spielleiter. Er prüft und gibt frei – erst dann ändern sich die Werte deines Charakters.
    Offene Punkte (nicht verteilte Fertigkeitspunkte, freie Zauberplätze) meldet das Tool dem Spielleiter als Hinweis.</p>`;
}
