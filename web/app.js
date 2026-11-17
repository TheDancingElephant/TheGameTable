"use strict";

// ------------------------------------------------------------------ Grundlagen

const SL = new URLSearchParams(location.search).get("sl");
if (SL) document.body.classList.add("sl");
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const schlaf = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(pfad, daten) {
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
const slBefehl = (b) => api("/api/sl/befehl", b);

let toastTimer = null;
function meldung(text, art = "fehler") {
  const t = $("#toast");
  t.textContent = text;
  t.className = art === "info" ? "info" : "";
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4500);
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ------------------------------------------------------------------ Zustand

let stand = null;
let charaktere = [];
let letzteLogId = 0;
let ersteLadung = true;

const ansicht = { zoom: 1, x: 0, y: 0, karteId: null };
let rasterAn = true;
let barrierenAn = false;       // nur SL: erkannte Barrieren einzeichnen
let barrierenCache = { schluessel: "", daten: null, laedt: false };
let werkzeug = "bewegen";
let ausgewaehlt = null;   // Token-ID
let ziehen = null;        // laufende Maus-Aktion
let platzieren = null;    // charId, die auf die Karte gesetzt wird
let pings = [];           // {x, y, t}
let hoverZelle = null;

const bild = new Image();
let bildSchluessel = "";

// ------------------------------------------------------------------ Server-Schleife

async function schleife() {
  let v = 0;
  for (;;) {
    try {
      const r = await fetch(`/api/stand?seit=${v}${SL ? "&sl=" + encodeURIComponent(SL) : ""}`);
      if (!r.ok) throw new Error(r.status);
      const s = await r.json();
      v = s.version;
      charaktere = await (await fetch("/api/charaktere")).json();
      aktualisieren(s);
    } catch (e) {
      statusPill("offline");
      await schlaf(2000);
    }
  }
}

// Kampfzustand
const imKampf = () => !!stand?.initiative?.aktiv;
const kampfLaeuft = () => imKampf() && stand.initiative.phase === "laeuft";
const amZug = (t) => kampfLaeuft() && stand.zug?.tokenId === t?.id;
const meinZug = (t) => amZug(t) && stand.slStatus === "bereit";

function aktualisieren(s) {
  stand = s;
  kopfZeichnen();
  zugleisteZeichnen();
  protokollZeichnen();
  gruppeZeichnen();
  charAuswahlFuellen();
  werSelectFuellen();
  karteLaden();
  zeichnen();
  unterlagenZeichnen();
  ausruestungZeichnen();
  ersteLadung = false;
}

// ------------------------------------------------------------------ Kopf

function statusPill(status) {
  const p = $("#sl-status");
  p.className = "pill " + status;
  p.textContent = {
    bereit: "Der Spielleiter wartet auf euch (Klick: anstupsen)",
    wartet: "Gesendet – der Spielleiter liest gleich",
    denkt: "Der Spielleiter schreibt …",
    offline: "Keine Verbindung zum Spieltisch",
  }[status] || status;
}

$("#sl-status").addEventListener("click", () => {
  if (SL || stand?.slStatus !== "bereit") return;
  api("/api/anstupsen", {}).catch(() => {});
});

function kopfZeichnen() {
  $("#szene-titel").textContent = stand.szene?.titel || "";
  $("#szene-untertitel").textContent = stand.szene?.untertitel || "";
  document.title = (stand.szene?.titel ? stand.szene.titel + " · " : "") + (stand.kampagne || "Spieltisch");
  statusPill(stand.slStatus);
  const ini = stand.initiative;
  $("#initiative").hidden = !ini.aktiv;
  if (ini.aktiv) {
    $("#ini-runde").textContent = `Runde ${ini.runde}`;
    $("#ini-liste").innerHTML = ini.eintraege.map((e, i) => {
      const aktuell = SL ? i === ini.index : e.aktuell;
      return `<li class="${aktuell ? "aktuell" : ""} ${e.verborgen ? "verborgen" : ""}">${esc(e.name)}<b>${esc(e.wert)}</b></li>`;
    }).join("") || `<li>Würfelt Initiative!</li>`;
    // Der Zug-Marker bleibt im scrollbaren Feld sichtbar
    const aktiv = $("#ini-liste li.aktuell");
    if (aktiv) aktiv.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

// ------------------------------------------------------------------ Zugleiste

function zugleisteZeichnen() {
  const leiste = $("#zugleiste");
  const ini = stand.initiative;
  leiste.hidden = !ini.aktiv;
  if (!ini.aktiv) return;
  const z = stand.zug;
  const hinweis = $("#zug-hinweis"), akt = $("#zug-aktionen"), knopf = $("#zug-beenden");
  akt.innerHTML = "";
  knopf.hidden = true;
  leiste.classList.remove("mein-zug");

  if (ini.phase !== "laeuft") {
    const namen = new Set(ini.eintraege.map((e) => e.name));
    const fehlend = stand.tokens.filter((t) => t.art === "sc" && !namen.has(t.name)).map((t) => t.name);
    $("#zug-runde").textContent = "Kampfbeginn";
    $("#zug-name").textContent = "Würfelt Initiative!";
    $("#zug-farbe").style.background = "var(--rot)";
    hinweis.textContent = fehlend.length
      ? `Noch offen: ${fehlend.join(", ")}. Knopf „Initiative“ auf der Charakterkarte (Reiter Gruppe).`
      : "Alle haben gewürfelt – der Spielleiter eröffnet den Kampf.";
    return;
  }

  const t = stand.tokens.find((x) => x.id === z?.tokenId);
  $("#zug-runde").textContent = `Runde ${ini.runde} · am Zug`;
  $("#zug-name").textContent = z?.name || "–";
  $("#zug-farbe").style.background = t?.farbe || FARBE[z?.art] || "#777";
  if (!z || z.art !== "sc") {
    hinweis.textContent = "Der Spielleiter führt die Gegner.";
    return;
  }
  if (stand.slStatus !== "bereit") {
    hinweis.textContent = "Der Spielleiter erzählt gerade – gleich geht es weiter.";
  } else {
    leiste.classList.add("mein-zug");
    knopf.hidden = false;
    hinweis.textContent = "Ziehen = bewegen · Rechtsklick auf Gegner = angreifen oder zaubern · Zauber auch auf der Charakterkarte (Reiter Gruppe).";
  }
  const pip = (key, label, frei) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.className = frei ? "frei" : "verbraucht";
    b.disabled = !frei || stand.slStatus !== "bereit";
    b.title = frei ? "Antippen, um die Aktion für etwas anderes zu nutzen (z. B. einen Zauber)" : "schon verbraucht";
    b.onclick = () => {
      const wofuer = prompt(`Wofür nutzt ${t.name} die ${label}?`, "");
      if (wofuer !== null) api("/api/aktion-verbrauchen", { id: t.id, aktion: key, wofuer });
    };
    akt.append(b);
  };
  pip("standard", "Standard-Aktion", z.standardFrei);
  pip("bewegung", "Bewegungsaktion", z.bewegungFrei);
  pip("schnell", "Schnelle Aktion", z.schnellFrei);
  const s = document.createElement("span");
  s.className = "bewegung";
  const einfach = z.standardFrei && z.bewegungFrei ? Math.max(0, z.tempo - z.bewegt) : z.restFelder;
  s.textContent = `Bewegung: noch ${z.restFelder} Felder (${meter(z.restFelder)} m)` +
    (einfach < z.restFelder ? ` – mehr als ${einfach} kostet die Standard-Aktion` : "");
  akt.append(s);
  knopf.onclick = () => api("/api/zug-beenden", { id: t.id });
}

// ------------------------------------------------------------------ Protokoll

function textFormatieren(t) {
  return esc(t)
    .split(/\n{2,}/)
    .map((absatz) => {
      const zeilen = absatz.split("\n");
      if (zeilen.every((z) => z.startsWith("&gt; "))) {
        return `<blockquote>${zeilen.map((z) => z.slice(5)).join("<br>")}</blockquote>`;
      }
      return `<p>${zeilen.join("<br>")}</p>`;
    })
    .join("")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>");
}

function eintragHtml(e) {
  const meta = (t) => `<div class="meta">${esc(e.zeit)} · ${t}</div>`;
  switch (e.art) {
    case "sl":
      return `<div class="eintrag sl${vorleseId === e.id ? " liest" : ""}" data-id="${e.id}"><button class="vorlesen" title="Vorlesen">${vorleseId === e.id ? "■" : "🔊"}</button>${meta("Spielleiter")}${e.titel ? `<h3>${esc(e.titel)}</h3>` : ""}${textFormatieren(e.text)}</div>`;
    case "sl-notiz":
      return `<div class="eintrag system">SL-Notiz: ${esc(e.text)}</div>`;
    case "spieler":
      return `<div class="eintrag spieler">${meta(esc(e.wer))}${textFormatieren(e.text)}</div>`;
    case "wurf":
      return `<div class="eintrag wurf ${e.besonders || ""}">${meta(esc(e.wer) + (e.verborgen ? " (verdeckt)" : ""))}
        <span class="ergebnis">${esc(e.ergebnis)}</span>${esc(e.text || e.ausdruck)}
        <div class="detail">${esc(e.ausdruck)}: ${esc(e.detail)}${e.besonders === "nat20" ? " – natürliche 20!" : e.besonders === "nat1" ? " – natürliche 1!" : ""}</div></div>`;
    case "angriff": {
      const urteil = e.treffer == null ? `<span class="urteil">– der SL wertet aus</span>`
        : !e.treffer ? `<span class="urteil daneben">Daneben</span>`
        : e.kritisch ? `<span class="urteil krit">Kritischer Treffer!</span>` : `<span class="urteil treffer">Treffer</span>`;
      const schaden = e.schaden ? ` – <b>${esc(e.schaden)} Schaden</b>` : "";
      const details = [e.detail, e.bestaetigung, e.schadenDetail ? "Schaden: " + e.schadenDetail : ""].filter(Boolean);
      return `<div class="eintrag angriff">${meta(esc(e.wer))}<span class="ergebnis">${esc(e.ergebnis)}</span>${esc(e.text)}
        ${urteil}${schaden}<div class="detail">${esc(details.join(" · "))}</div></div>`;
    }
    case "zugende":
      return `<div class="eintrag zugende">${esc(e.text)}</div>`;
    case "ep":
      return `<div class="eintrag ep">✧ ${esc(e.text)}</div>`;
    case "aufstieg":
      return `<div class="eintrag aufstieg">${meta(esc(e.wer))}<div class="titel">⬆ ${esc(e.text)}</div>
        <div class="detail">${esc(e.detail)}</div>${e.wuensche ? `<div class="detail">Wahl: ${esc(e.wuensche)}</div>` : ""}</div>`;
    case "zauber":
      return `<div class="eintrag zauber">${meta(esc(e.wer))}✦ ${esc(e.text)}
        ${e.ergebnisText ? `<span class="urteil">${esc(e.ergebnisText)}</span>` : ""}
        ${e.detail ? `<div class="detail">${esc(e.detail)}</div>` : ""}</div>`;
    default:
      return `<div class="eintrag ${esc(e.art)}">${esc(e.text)}</div>`;
  }
}

function protokollZeichnen() {
  const log = stand.protokoll;
  const neueste = log.length ? log[log.length - 1].id : 0;
  if (neueste === letzteLogId) return;
  const box = $("#protokoll");
  const unten = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  box.innerHTML = log.map(eintragHtml).join("");
  if (unten || ersteLadung) requestAnimationFrame(() => (box.scrollTop = box.scrollHeight));
  if (!ersteLadung) {
    const neueErz = log.filter((e) => e.id > letzteLogId && e.art === "sl");
    if (stimme.auto && neueErz.length) vorlesen(neueErz[neueErz.length - 1]);
    for (const e of log) {
      if (e.id > letzteLogId && e.art === "zeigen" && e.feld) pings.push({ x: e.feld[0], y: e.feld[1], t: performance.now() });
    }
    if (pings.length) animieren();
  }
  letzteLogId = neueste;
}

// ------------------------------------------------------------------ Erzählstimme

const stimme = { name: null, tempo: 0.95, auto: false };
try { Object.assign(stimme, JSON.parse(localStorage.getItem("erzaehlstimme") || "{}")); } catch (e) { /* ohne Speicher */ }
const stimmeMerken = () => { try { localStorage.setItem("erzaehlstimme", JSON.stringify(stimme)); } catch (e) { /* egal */ } };
let vorleseId = null;

function stimmen() {
  const alle = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("de"));
  // natürliche (neuronale) Stimmen zuerst, falls der Browser welche hat
  return alle.sort((a, b) => /natural|online/i.test(b.name) - /natural|online/i.test(a.name));
}
function stimmenFuellen() {
  const liste = stimmen();
  const sel = $("#stimme-wahl");
  sel.innerHTML = liste.length
    ? liste.map((v) => `<option value="${esc(v.name)}">${esc(v.name.replace(/^Microsoft /, "").replace(/ - German \(Germany\)/, ""))}</option>`).join("")
    : `<option value="">(keine deutsche Stimme gefunden)</option>`;
  if (stimme.name && liste.some((v) => v.name === stimme.name)) sel.value = stimme.name;
  $("#stimme-tempo").value = stimme.tempo;
  $("#stimme-auto").checked = stimme.auto;
}
speechSynthesis.addEventListener?.("voiceschanged", stimmenFuellen);
stimmenFuellen();
$("#stimme-wahl").addEventListener("change", (ev) => { stimme.name = ev.target.value; stimmeMerken(); });
$("#stimme-tempo").addEventListener("change", (ev) => { stimme.tempo = +ev.target.value; stimmeMerken(); });
$("#stimme-auto").addEventListener("change", (ev) => { stimme.auto = ev.target.checked; stimmeMerken(); });
$("#stimme-stopp").addEventListener("click", vorlesenStopp);

function vorleseMarke(id) {
  vorleseId = id;
  $$("#protokoll .eintrag.sl").forEach((el) => {
    const an = +el.dataset.id === id;
    el.classList.toggle("liest", an);
    $(".vorlesen", el).textContent = an ? "■" : "🔊";
  });
}
function vorlesenStopp() {
  speechSynthesis.cancel();
  vorleseMarke(null);
}
function vorlesen(e) {
  speechSynthesis.cancel();
  const v = stimmen().find((x) => x.name === stimme.name) || stimmen()[0];
  // Absätze einzeln sprechen: lange Äußerungen bricht Chrome sonst ab; wörtliche Rede (> …) etwas anders betont
  const teile = [];
  if (e.titel) teile.push({ text: e.titel + ".", rede: false });
  for (const absatz of e.text.split(/\n{2,}/)) {
    const zeilen = absatz.split("\n");
    const rede = zeilen.every((z) => z.startsWith("> "));
    const text = zeilen.map((z) => z.replace(/^> /, "")).join(" ").replace(/\*+/g, "").replace(/[„“"]/g, "").trim();
    if (text) teile.push({ text, rede });
  }
  vorleseMarke(e.id);
  teile.forEach((t, i) => {
    const u = new SpeechSynthesisUtterance(t.text);
    u.lang = "de-DE";
    if (v) u.voice = v;
    u.rate = stimme.tempo;
    u.pitch = t.rede ? 1.15 : 0.95;
    if (i === teile.length - 1) u.onend = () => vorleseId === e.id && vorleseMarke(null);
    speechSynthesis.speak(u);
  });
}
$("#protokoll").addEventListener("click", (ev) => {
  const b = ev.target.closest(".vorlesen");
  if (!b) return;
  const id = +b.closest(".eintrag").dataset.id;
  if (vorleseId === id) return vorlesenStopp();
  const e = stand.protokoll.find((x) => x.id === id);
  if (e) vorlesen(e);
});

// ------------------------------------------------------------------ Aktionen & Würfel

function werSelectFuellen() {
  const sel = $("#aktion-wer");
  const namen = ["Gruppe", ...charaktere.map((c) => c.name)];
  if (SL) namen.unshift("SL");
  const sig = namen.join("|");
  if (sel.dataset.sig !== sig) {
    const alt = sel.value;
    sel.innerHTML = namen.map((n) => `<option>${esc(n)}</option>`).join("");
    sel.dataset.sig = sig;
    if (namen.includes(alt)) sel.value = alt;
  }
  // Im Kampf spricht der Charakter, der am Zug ist
  const sprecher = !SL && kampfLaeuft() && stand.zug?.art === "sc" ? stand.zug.name : null;
  if (sprecher && namen.includes(sprecher)) sel.value = sprecher;
  sel.disabled = !!sprecher;
  gruppeniniZeigen();
}

$("#aktion-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#aktion-text").value.trim();
  if (!text) return;
  if (SL) {
    await slBefehl({ op: "erzaehle", text });
  } else {
    await api("/api/aktion", { text, wer: $("#aktion-wer").value });
  }
  $("#aktion-text").value = "";
});
$("#aktion-text").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) $("#aktion-form").requestSubmit();
});

async function wuerfeln(ausdruck, grund, wer, extra = {}) {
  wer = wer || $("#aktion-wer").value;
  if (SL) return slBefehl({ op: "wurf", ausdruck, grund, wer, verborgen: false });
  return api("/api/wurf", { ausdruck, grund, wer, ...extra });
}
$$("#wuerfelleiste button[data-w]").forEach((b) =>
  b.addEventListener("click", () => wuerfeln(b.dataset.w, $("#wurf-grund").value.trim()))
);
$("#wurf-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const a = $("#wurf-ausdruck").value.trim();
  if (a) wuerfeln(a, $("#wurf-grund").value.trim());
});

// Gruppenprobe: jeder Charakter würfelt W20 + Fertigkeitsbonus (gleicher Bonus wie auf der Charakterkarte)
const GRUPPENPROBEN = ["Wahrnehmung", "Motiv erkennen", "Heimlichkeit", "Mechanismus ausschalten", "Wissen (Gewölbekunde)", "Wissen (Religion)", "Wissen (Arkanes)", "Klettern", "Schwimmen", "Akrobatik"];
$("#gruppenprobe-art").innerHTML = GRUPPENPROBEN.map((n) => `<option>${n}</option>`).join("");
$("#gruppenprobe-los").addEventListener("click", async (ev) => {
  const knopf = ev.currentTarget;
  const art = $("#gruppenprobe-art").value;
  knopf.disabled = true;
  try {
    for (const c of charaktere) {
      const f = (c.fertigkeiten || []).find((x) => x.name === art || x.name.startsWith(art + " ("));
      if (!f) continue;
      const bonus = f.bonus || 0;
      await wuerfeln(`1W20${bonus ? (bonus >= 0 ? "+" : "") + bonus : ""}`, art, c.name);
    }
  } finally {
    knopf.disabled = false;
  }
});

// Gruppenprobe Initiative: nur im Kampf (vor Kampfbeginn), würfelt für alle noch fehlenden Charaktere auf der Karte
function offeneIni() {
  if (!imKampf() || stand.initiative.phase === "laeuft") return [];
  const da = new Set(stand.initiative.eintraege.map((e) => e.name));
  return charaktere.filter((c) => !da.has(c.name) && scToken(c.id));
}
function gruppeniniZeigen() {
  const n = SL ? 0 : offeneIni().length;
  $("#gruppenini").hidden = !n;
}
$("#gruppenini-los").addEventListener("click", async (ev) => {
  const knopf = ev.currentTarget;
  knopf.disabled = true;
  try {
    for (const c of offeneIni()) {
      const b = c.ini || 0;
      await wuerfeln(`1W20${b ? (b >= 0 ? "+" : "") + b : ""}`, "Initiative", c.name, { initiative: true, charId: c.id });
    }
  } finally {
    knopf.disabled = false;
  }
});

// ------------------------------------------------------------------ Reiter

$$("#reiter button").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#reiter button").forEach((x) => x.classList.toggle("aktiv", x === b));
    $$(".reiter-inhalt").forEach((x) => x.classList.toggle("aktiv", x.id === "r-" + b.dataset.reiter));
  })
);

// ------------------------------------------------------------------ Ausrüstung

let ausruestungSig = "";
function traegerName(id) {
  return id === "gruppe" ? "Gruppe (Gepäck)" : charaktere.find((c) => c.id === id)?.name || id;
}
function ausruestungZeichnen() {
  const a = stand.ausruestung;
  if (!a) return;
  const sig = JSON.stringify([a, charaktere.map((c) => [c.id, c.name, c.zauberbuch, c.zauberliste])]);
  if (sig === ausruestungSig) return;
  if (document.activeElement && document.activeElement.closest("#ausruestung-liste")) return;
  ausruestungSig = sig;
  const k = a.kasse;
  $("#kasse").innerHTML = `<div class="kasse">${["pp", "gp", "sp", "kp"].map((m) => `<span><b>${k[m]}</b> ${m.toUpperCase()}</span>`).join("")}</div>`;
  const traeger = [...charaktere.map((c) => c.id), "gruppe"];
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
  const buecher = charaktere.filter((c) => c.zauberbuch);
  $("#zauberbuecher").innerHTML = buecher.map((c) => {
    const vorbereitet = new Set((c.zauberliste || []).map((z) => z.name.toLowerCase()));
    const grade = [...new Set(c.zauberbuch.map((z) => z.grad))].sort((x, y) => x - y);
    return `<details open data-char="${esc(c.id)}"><summary>Zauberbuch von ${esc(c.name)} (${c.zauberbuch.length})</summary>` +
      grade.map((g) => `<div class="ort"><b>Grad ${g}</b><div class="buch-zeilen">` + c.zauberbuch.filter((z) => z.grad === g).sort((x, y) => x.name.localeCompare(y.name))
        .map((z) => `<span class="buch-zauber${vorbereitet.has(z.name.toLowerCase()) ? " vorbereitet" : ""}" title="${vorbereitet.has(z.name.toLowerCase()) ? "vorbereitet" : "im Buch"}">${esc(z.name)}<button class="buch-weg" data-name="${esc(z.name)}" title="entfernen">✕</button></span>`).join("") + `</div></div>`).join("") +
      `<form class="buch-form zeile"><input class="buch-name" type="text" placeholder="Zauber eintragen" required><select class="buch-grad">${[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option value="${g}">Grad ${g}</option>`).join("")}</select><button type="submit">Eintragen</button></form></details>`;
  }).join("") || `<div class="hinweis">Keine Zauberbücher.</div>`;
  $$("#zauberbuecher details").forEach((d) => {
    const charId = d.dataset.char;
    d.querySelector(".buch-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await api("/api/zauberbuch", { charId, op: "add", name: d.querySelector(".buch-name").value, grad: Number(d.querySelector(".buch-grad").value) });
      charaktere = await (await fetch("/api/charaktere")).json();
      ausruestungSig = "";
      ausruestungZeichnen();
    });
    d.querySelectorAll(".buch-weg").forEach((b) => b.addEventListener("click", async () => {
      await api("/api/zauberbuch", { charId, op: "weg", name: b.dataset.name });
      charaktere = await (await fetch("/api/charaktere")).json();
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

// ------------------------------------------------------------------ Unterlagen

let unterlagenSig = "";
function unterlagenZeichnen() {
  const u = stand.unterlagen || { karten: [], handouts: [], notizen: "" };
  const sig = JSON.stringify([u.karten, u.handouts]);
  if (sig !== unterlagenSig) {
    unterlagenSig = sig;
    const offen = new Set($$("#unterlagen-handouts details[open]").map((d) => d.dataset.id));
    $("#unterlagen-karten").innerHTML = u.karten.length
      ? u.karten.map((k) => `<button data-karte="${esc(k.id)}"><span>🗺 ${esc(k.name)}</span><small>${k.aktiv ? "aktuelle Szene" : "ansehen"}</small></button>`).join("")
      : `<div class="hinweis">Noch keine Karten.</div>`;
    $("#unterlagen-handouts").innerHTML = u.handouts.length
      ? u.handouts.map((h) => `<details data-id="${esc(h.id)}"${offen.has(h.id) ? " open" : ""}><summary>${esc(h.titel)}</summary><div class="handout-text">${textFormatieren(h.text)}</div></details>`).join("")
      : `<div class="hinweis">Noch keine Handouts.</div>`;
    $$("#unterlagen-karten button").forEach((b) => b.addEventListener("click", () => betrachterOeffnen(b.dataset.karte)));
  }
  const ta = $("#gruppennotizen");
  if (document.activeElement !== ta && !notizenTimer) ta.value = u.notizen || "";
}

let notizenTimer = null;
async function notizenSpeichern() {
  clearTimeout(notizenTimer);
  notizenTimer = null;
  try {
    await api("/api/gruppennotizen", { text: $("#gruppennotizen").value });
    $("#notizen-status").textContent = "gespeichert";
  } catch (e) {
    $("#notizen-status").textContent = "Speichern fehlgeschlagen";
  }
}
$("#gruppennotizen").addEventListener("input", () => {
  $("#notizen-status").textContent = "…";
  clearTimeout(notizenTimer);
  notizenTimer = setTimeout(notizenSpeichern, 800);
});
$("#gruppennotizen").addEventListener("blur", () => notizenTimer && notizenSpeichern());

const betr = { zoom: 1, x: 0, y: 0, ziehen: null };
function betrachterSetzen() {
  $("#betrachter-bild").style.transform = `translate(${betr.x}px, ${betr.y}px) scale(${betr.zoom})`;
}
function betrachterOeffnen(kid) {
  const k = stand.unterlagen.karten.find((x) => x.id === kid);
  if (!k) return;
  $("#betrachter-titel").textContent = k.name;
  const leg = k.legende && stand.unterlagen.handouts.find((h) => h.id === k.legende);
  $("#betrachter-legende").hidden = !leg;
  $("#betrachter-legende").innerHTML = leg ? `<h3>${esc(leg.titel)}</h3>${textFormatieren(leg.text)}` : "";
  const img = $("#betrachter-bild");
  $("#betrachter").showModal();
  img.onload = () => {
    const r = $("#betrachter-flaeche").getBoundingClientRect();
    betr.zoom = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
    betr.x = (r.width - img.naturalWidth * betr.zoom) / 2;
    betr.y = (r.height - img.naturalHeight * betr.zoom) / 2;
    betrachterSetzen();
  };
  img.src = `/api/karte/${kid}.jpg?v=${k.nebelVersion}${SL ? "&sl=" + encodeURIComponent(SL) : ""}`;
}
$("#betrachter-zu").addEventListener("click", () => $("#betrachter").close());
$("#betrachter-flaeche").addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const r = $("#betrachter-flaeche").getBoundingClientRect();
  const sx = ev.clientX - r.left, sy = ev.clientY - r.top;
  const neu = Math.max(0.05, Math.min(4, betr.zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15)));
  betr.x = sx - ((sx - betr.x) * neu) / betr.zoom;
  betr.y = sy - ((sy - betr.y) * neu) / betr.zoom;
  betr.zoom = neu;
  betrachterSetzen();
}, { passive: false });
$("#betrachter-flaeche").addEventListener("pointerdown", (ev) => {
  betr.ziehen = { sx: ev.clientX, sy: ev.clientY, x: betr.x, y: betr.y };
  ev.currentTarget.setPointerCapture(ev.pointerId);
  ev.currentTarget.classList.add("zieht");
});
$("#betrachter-flaeche").addEventListener("pointermove", (ev) => {
  if (!betr.ziehen) return;
  betr.x = betr.ziehen.x + ev.clientX - betr.ziehen.sx;
  betr.y = betr.ziehen.y + ev.clientY - betr.ziehen.sy;
  betrachterSetzen();
});
$("#betrachter-flaeche").addEventListener("pointerup", (ev) => {
  betr.ziehen = null;
  ev.currentTarget.classList.remove("zieht");
});

// ------------------------------------------------------------------ Gruppe

const mod = (w) => (w == null ? 0 : Math.floor((w - 10) / 2));
const vz = (n) => (n >= 0 ? "+" : "") + n;
const scToken = (cid) => stand?.tokens.find((t) => t.art === "sc" && t.charId === cid);

function gruppeZeichnen() {
  const sig = JSON.stringify([charaktere, stand.tokens.filter((t) => t.art === "sc"), stand.zustaende, platzieren,
    !!stand.karte, stand.zug, stand.initiative.eintraege.map((e) => e.name), stand.initiative.aktiv]);
  const liste = $("#gruppe-liste");
  if (liste.dataset.sig === sig) return;
  liste.dataset.sig = sig;
  liste.innerHTML = charaktere.length ? "" : `<p class="hinweis">Noch keine Charaktere. Lege sie im Reiter „Charaktere“ an.</p>`;
  if (charaktere.length > 1) {
    const kopf = document.createElement("div");
    kopf.className = "zeile";
    kopf.innerHTML = `<button type="button" id="gr-zu">Alle einklappen</button><button type="button" id="gr-auf">Alle ausklappen</button>`;
    liste.append(kopf);
    $("#gr-zu", kopf).onclick = () => scKartenEinklappen(true);
    $("#gr-auf", kopf).onclick = () => scKartenEinklappen(false);
  }
  for (const c of charaktere) liste.append(scKarte(c));
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
    knopf.textContent = platzieren === c.id ? "Feld anklicken …" : "Auf Karte setzen";
    knopf.disabled = !stand.karte;
    knopf.onclick = () => {
      platzieren = platzieren === c.id ? null : c.id;
      gruppeZeichnen();
      $("#karte").style.cursor = platzieren ? "crosshair" : "";
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
  if (imKampf() && stand.initiative.eintraege.some((e) => e.name === c.name)) {
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
    zsel.innerHTML += stand.zustaende.filter((z) => !(t.zustaende || []).includes(z)).map((z) => `<option>${esc(z)}</option>`).join("");
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
let zauberDb = [];
fetch("/api/zauber").then((r) => r.json()).then((d) => (zauberDb = d)).catch(() => {});
// Grad eines Katalogzaubers für Klassenangaben wie „Kleriker“ oder „Barde 5“ (die erste passende zählt;
// längste Klassennamen zuerst: Hexenmeister vor Hexe)
function zauberGradFuer(z, ...klassen) {
  for (const klasse of klassen) {
    const k = (klasse || "").toLowerCase();
    const treffer = Object.keys(z?.klassen || {}).sort((a, b) => b.length - a.length).find((n) => k.includes(n.toLowerCase()));
    if (treffer) return z.klassen[treffer];
  }
  return z?.grad;
}
// alle Zauberlisten (Klassen) im Katalog, für die Auswahl im Editor
const zauberListen = () => [...new Set(zauberDb.flatMap((z) => Object.keys(z.klassen || {})))].sort((a, b) => a.localeCompare(b));

// Zauber vorbereiten: je Platz eine Auswahl aus der Zauberliste der Klasse (Magier: aus dem Zauberbuch)
async function zauberVorbereiten(c) {
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
const zauberOption = (z) => `<option value="${esc(z.name)}">${esc(z.klassenText || "Grad " + z.grad)}</option>`;

function charAuswahlFuellen() {
  const sel = $("#char-auswahl");
  const sig = charaktere.map((c) => c.id + ":" + c.name).join("|");
  if (sel.dataset.sig !== sig) {
    sel.innerHTML = charaktere.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("") ||
      `<option value="">(keine)</option>`;
    sel.dataset.sig = sig;
  }
  if (editorId === null && charaktere.length) editorLaden(charaktere[0].id);
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
  const c = structuredClone(charaktere.find((x) => x.id === id) || LEER);
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

// ------------------------------------------------------------------ Karte: Geometrie

const canvas = $("#karte");
const ctx = canvas.getContext("2d");

function karteLaden() {
  const k = stand.karte;
  $("#keine-karte").hidden = !!k;
  if (!k) return;
  const schluessel = `${k.id}:${k.nebelVersion}`;
  if (schluessel !== bildSchluessel) {
    bildSchluessel = schluessel;
    const neu = new Image();
    neu.onload = () => {
      bild.src = neu.src;
    };
    neu.src = `/api/karte/${k.id}.jpg?v=${k.nebelVersion}${SL ? "&sl=" + encodeURIComponent(SL) : ""}`;
  }
  if (ansicht.karteId !== k.id) {
    ansicht.karteId = k.id;
    einpassen();
  }
  if (SL) {
    $("#r-zelle").value = k.zelle; $("#r-ox").value = k.ox; $("#r-oy").value = k.oy;
  }
}
bild.onload = () => zeichnen();

function einpassen() {
  const k = stand?.karte;
  if (!k) return;
  const r = canvas.getBoundingClientRect();
  // Gruppe vorhanden? Dann auf sie zentrieren, sonst auf aufgedeckten Bereich, sonst ganze Karte
  const scs = stand.tokens.filter((t) => t.art === "sc");
  const zellen = scs.length ? scs.map((t) => [t.x, t.y]) : k.aufgedeckt;
  if (zellen && zellen.length) {
    const xs = zellen.map((c) => c[0]), ys = zellen.map((c) => c[1]);
    const x0 = k.ox + (Math.min(...xs) - 6) * k.zelle, x1 = k.ox + (Math.max(...xs) + 7) * k.zelle;
    const y0 = k.oy + (Math.min(...ys) - 6) * k.zelle, y1 = k.oy + (Math.max(...ys) + 7) * k.zelle;
    ansicht.zoom = Math.min(1.5, Math.min(r.width / (x1 - x0), r.height / (y1 - y0)));
    ansicht.x = r.width / 2 - ((x0 + x1) / 2) * ansicht.zoom;
    ansicht.y = r.height / 2 - ((y0 + y1) / 2) * ansicht.zoom;
  } else {
    ansicht.zoom = Math.min(r.width / k.w, r.height / k.h);
    ansicht.x = (r.width - k.w * ansicht.zoom) / 2;
    ansicht.y = (r.height - k.h * ansicht.zoom) / 2;
  }
  zeichnen();
}

const welt = (sx, sy) => [(sx - ansicht.x) / ansicht.zoom, (sy - ansicht.y) / ansicht.zoom];
function zelleBei(sx, sy) {
  const k = stand.karte;
  const [wx, wy] = welt(sx, sy);
  return [Math.floor((wx - k.ox) / k.zelle), Math.floor((wy - k.oy) / k.zelle)];
}
const pfDistanz = (x0, y0, x1, y1) => {
  const dx = Math.abs(x1 - x0), dy = Math.abs(y1 - y0);
  return Math.max(dx, dy) + Math.floor(Math.min(dx, dy) / 2);
};
const meter = (felder) => +(felder * (stand.karte?.meterProFeld || 1.5)).toFixed(1);

function tokenBei(sx, sy) {
  const k = stand.karte;
  const [wx, wy] = welt(sx, sy);
  const liste = [...stand.tokens].reverse();
  return liste.find((t) => {
    const g = t.groesse || 1;
    const x0 = k.ox + t.x * k.zelle, y0 = k.oy + t.y * k.zelle;
    return wx >= x0 && wx < x0 + g * k.zelle && wy >= y0 && wy < y0 + g * k.zelle;
  });
}
const darfZiehen = (t) => SL || t.art === "sc";

// ------------------------------------------------------------------ Karte: Zeichnen

const FARBE = { gegner: "#b3261e", nsc: "#c99a1a", objekt: "#6f6f6f", sc: "#3a7bd5" };

function zeichnen() {
  const dpr = window.devicePixelRatio || 1;
  const r = canvas.getBoundingClientRect();
  if (canvas.width !== Math.round(r.width * dpr) || canvas.height !== Math.round(r.height * dpr)) {
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, r.width, r.height);
  const k = stand?.karte;
  if (!k) return;
  ctx.save();
  ctx.translate(ansicht.x, ansicht.y);
  ctx.scale(ansicht.zoom, ansicht.zoom);
  if (bild.complete && bild.naturalWidth) ctx.drawImage(bild, 0, 0, k.w, k.h);

  // sichtbarer Feldbereich
  const [wx0, wy0] = welt(0, 0), [wx1, wy1] = welt(r.width, r.height);
  const fx0 = Math.max(Math.floor((wx0 - k.ox) / k.zelle), Math.floor(-k.ox / k.zelle));
  const fy0 = Math.max(Math.floor((wy0 - k.oy) / k.zelle), Math.floor(-k.oy / k.zelle));
  const fx1 = Math.min(Math.ceil((wx1 - k.ox) / k.zelle), Math.ceil((k.w - k.ox) / k.zelle));
  const fy1 = Math.min(Math.ceil((wy1 - k.oy) / k.zelle), Math.ceil((k.h - k.oy) / k.zelle));
  const Z = k.zelle;
  const zx = (x) => k.ox + x * Z, zy = (y) => k.oy + y * Z;

  ctx.save();  // Overlays nur innerhalb des Kartenbilds
  ctx.beginPath();
  ctx.rect(0, 0, k.w, k.h);
  ctx.clip();

  if (SL) {  // SL sieht das ganze Bild, Nebel nur angedeutet
    const offen = new Set(k.aufgedeckt.map((c) => c[0] + "," + c[1]));
    ctx.fillStyle = "rgba(10, 8, 20, 0.5)";
    for (let x = fx0; x <= fx1; x++) for (let y = fy0; y <= fy1; y++) {
      if (!offen.has(x + "," + y)) ctx.fillRect(zx(x), zy(y), Z, Z);
    }
  }

  // Bewegungsreichweite: im Kampf die Restbewegung des aktiven Charakters, sonst des ausgewählten
  const aktiv = kampfLaeuft() ? stand.tokens.find((t) => t.id === stand.zug?.tokenId) : null;
  const sel = imKampf() ? (aktiv?.art === "sc" && stand.slStatus === "bereit" ? aktiv : null)
    : stand.tokens.find((t) => t.id === ausgewaehlt);
  if (sel && sel.art === "sc" && !ziehen) {
    const c = charaktere.find((c) => c.id === sel.charId);
    const tempo = Math.floor((c?.bewegung || 9) / (k.meterProFeld || 1.5));
    // grün: ohne die Standard-Aktion erreichbar, gelb: nur mit Doppelbewegung
    let [nah, fern] = [tempo, 2 * tempo];
    if (sel === aktiv) {
      const z = stand.zug;
      fern = z.restFelder;
      nah = z.standardFrei && z.bewegungFrei ? Math.max(0, Math.max(tempo, 1) - z.bewegt) : fern;
    }
    const offen = SL ? null : new Set(k.aufgedeckt.map((c) => c[0] + "," + c[1]));
    for (let x = sel.x - fern; x <= sel.x + fern; x++) {
      for (let y = sel.y - fern; y <= sel.y + fern; y++) {
        const d = pfDistanz(sel.x, sel.y, x, y);
        if (d === 0 || d > fern || (offen && !offen.has(x + "," + y))) continue;
        ctx.fillStyle = d <= nah ? "rgba(95, 174, 107, 0.22)" : "rgba(214, 168, 75, 0.12)";
        ctx.fillRect(zx(x), zy(y), Z, Z);
      }
    }
  }

  if (SL && barrierenAn) {
    const sk = `${k.id}:${stand.version}`;
    if (barrierenCache.schluessel !== sk && !barrierenCache.laedt) {
      barrierenCache.laedt = true;
      fetch(`/api/sl/barrieren?karte=${encodeURIComponent(k.id)}&sl=${encodeURIComponent(SL)}`).then((r) => r.json())
        .then((d) => { barrierenCache = { schluessel: sk, daten: d, laedt: false }; zeichnen(); })
        .catch(() => { barrierenCache.laedt = false; });
    }
    const d = barrierenCache.daten;
    if (d) {
      ctx.lineWidth = 2 / ansicht.zoom;
      ctx.strokeStyle = "rgba(255, 0, 200, 0.85)";
      ctx.beginPath();
      for (const q of d.waende) { ctx.moveTo(q[0], q[1]); ctx.lineTo(q[2], q[3]); }
      ctx.stroke();
      ctx.lineWidth = 5 / ansicht.zoom;
      for (const e of d.extra) {
        ctx.strokeStyle = e.offen ? "rgba(90, 230, 90, 0.9)" : ({ tuer: "rgba(0, 140, 255, 0.95)", geheimtuer: "rgba(160, 0, 220, 0.95)", fenster: "rgba(0, 190, 80, 0.95)" }[e.typ] || "rgba(255, 140, 0, 0.95)");
        ctx.beginPath(); ctx.moveTo(e.p[0], e.p[1]); ctx.lineTo(e.p[2], e.p[3]); ctx.stroke();
      }
      ctx.fillStyle = "#06f";
      ctx.font = `${11 / ansicht.zoom}px sans-serif`;
      for (const e of d.extra) ctx.fillText(e.id, (e.p[0] + e.p[2]) / 2 + 4 / ansicht.zoom, (e.p[1] + e.p[3]) / 2 - 4 / ansicht.zoom);
    }
  }

  if (rasterAn) {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.28)";
    ctx.lineWidth = 1 / ansicht.zoom;
    ctx.beginPath();
    for (let x = fx0; x <= fx1 + 1; x++) { ctx.moveTo(zx(x), zy(fy0)); ctx.lineTo(zx(x), zy(fy1 + 1)); }
    for (let y = fy0; y <= fy1 + 1; y++) { ctx.moveTo(zx(fx0), zy(y)); ctx.lineTo(zx(fx1 + 1), zy(y)); }
    ctx.stroke();
  }
  ctx.restore();

  if (hoverZelle && !ziehen) {
    ctx.strokeStyle = "rgba(240, 201, 106, 0.8)";
    ctx.lineWidth = 2 / ansicht.zoom;
    ctx.strokeRect(zx(hoverZelle[0]), zy(hoverZelle[1]), Z, Z);
  }

  // Rechteck-Auswahl (SL: Nebel)
  if (ziehen?.art === "rechteck") {
    const [a, b] = [ziehen.start, ziehen.ende];
    ctx.fillStyle = ziehen.auf ? "rgba(240, 201, 106, 0.25)" : "rgba(30, 30, 60, 0.45)";
    ctx.fillRect(zx(Math.min(a[0], b[0])), zy(Math.min(a[1], b[1])), (Math.abs(a[0] - b[0]) + 1) * Z, (Math.abs(a[1] - b[1]) + 1) * Z);
  }

  for (const t of stand.tokens) {
    if (ziehen?.art === "token" && ziehen.token.id === t.id) {
      tokenZeichnen(t, t.x, t.y, 0.35);
    } else {
      tokenZeichnen(t, t.x, t.y, t.sichtbar === false ? 0.5 : 1);
    }
  }

  // Ziehen eines Tokens / Messen: Linie und Entfernung
  if (ziehen?.art === "token" || ziehen?.art === "messen") {
    const [a, b] = ziehen.art === "token" ? [[ziehen.token.x, ziehen.token.y], ziehen.ziel] : [ziehen.start, ziehen.ende];
    const g = ziehen.art === "token" ? ziehen.token.groesse || 1 : 1;
    ctx.strokeStyle = "#f0c96a";
    ctx.lineWidth = 3 / ansicht.zoom;
    ctx.setLineDash([8 / ansicht.zoom, 6 / ansicht.zoom]);
    ctx.beginPath();
    ctx.moveTo(zx(a[0] + g / 2), zy(a[1] + g / 2));
    ctx.lineTo(zx(b[0] + g / 2), zy(b[1] + g / 2));
    ctx.stroke();
    ctx.setLineDash([]);
    if (ziehen.art === "token") tokenZeichnen(ziehen.token, b[0], b[1], 0.9);
    const d = pfDistanz(a[0], a[1], b[0], b[1]);
    const text = `${d} Felder · ${meter(d)} m`;
    ctx.font = `600 ${14 / ansicht.zoom}px Segoe UI, sans-serif`;
    const tw = ctx.measureText(text).width;
    const px = zx(b[0] + g) + 6 / ansicht.zoom, py = zy(b[1]) - 6 / ansicht.zoom;
    ctx.fillStyle = "rgba(20, 16, 12, 0.9)";
    ctx.fillRect(px - 4 / ansicht.zoom, py - 16 / ansicht.zoom, tw + 8 / ansicht.zoom, 22 / ansicht.zoom);
    ctx.fillStyle = "#f0c96a";
    ctx.fillText(text, px, py);
  }

  // Zeige-Pings
  const jetzt = performance.now();
  pings = pings.filter((p) => jetzt - p.t < 2500);
  for (const p of pings) {
    const f = (jetzt - p.t) / 2500;
    ctx.strokeStyle = `rgba(240, 201, 106, ${1 - f})`;
    ctx.lineWidth = 4 / ansicht.zoom;
    ctx.beginPath();
    ctx.arc(zx(p.x + 0.5), zy(p.y + 0.5), Z * (0.4 + f * 1.6), 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function tokenZeichnen(t, x, y, alpha) {
  const k = stand.karte;
  const g = t.groesse || 1;
  const Z = k.zelle;
  const cx = k.ox + (x + g / 2) * Z, cy = k.oy + (y + g / 2) * Z;
  const rad = (g * Z) / 2 - Z * 0.07;
  const zs = t.zustaende || [];
  const tot = zs.includes("Tot");
  const schwach = !tot && ["Sterbend", "Kampfunfähig", "Bewusstlos"].some((z) => zs.includes(z));
  ctx.globalAlpha = tot ? alpha * 0.5 : schwach ? alpha * 0.65 : alpha;
  if (amZug(t) && !tot) {  // wer am Zug ist, bekommt einen goldenen Kranz
    ctx.strokeStyle = "#f0c96a";
    ctx.lineWidth = Z * 0.09;
    ctx.beginPath();
    ctx.arc(cx, cy, rad + Z * 0.1, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.fillStyle = tot ? "#5a5a5a" : t.farbe || FARBE[t.art] || "#777";
  ctx.strokeStyle = t.id === ausgewaehlt ? "#f0c96a" : "#fff";
  ctx.lineWidth = (t.id === ausgewaehlt ? 4 : 2.5) * Math.max(1, 1 / ansicht.zoom) * 0.8;
  ctx.shadowColor = "rgba(0,0,0,.6)";
  ctx.shadowBlur = 6;
  ctx.beginPath();
  ctx.arc(cx, cy, rad, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.stroke();
  if (t.sichtbar === false) {  // nur SL: verborgen
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#000";
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.fillStyle = "#fff";
  ctx.font = `700 ${rad * 0.8}px Segoe UI, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const kurz = tot ? "☠" : t.symbol || t.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  ctx.fillText(kurz, cx, cy + 1);
  // TP-Balken (eigene Charaktere, beim SL alle)
  if (t.tpMax && (t.art === "sc" || SL)) {
    const anteil = Math.max(0, Math.min(1, (t.tp ?? 0) / t.tpMax));
    const bw = g * Z * 0.8, bx = cx - bw / 2, by = k.oy + (y + g) * Z - Z * 0.14;
    ctx.fillStyle = "rgba(0,0,0,.7)";
    ctx.fillRect(bx, by, bw, Z * 0.1);
    ctx.fillStyle = anteil > 0.5 ? "#5fae6b" : anteil > 0.25 ? "#d6a84b" : "#c8473a";
    ctx.fillRect(bx, by, bw * anteil, Z * 0.1);
  }
  if ((t.zustaende || []).length) {
    ctx.fillStyle = "#c8473a";
    ctx.beginPath();
    ctx.arc(cx + rad * 0.72, cy - rad * 0.72, Z * 0.13, 0, Math.PI * 2);
    ctx.fill();
  }
  // Name ab mittlerem Zoom
  if (ansicht.zoom * Z > 34) {
    ctx.font = `600 ${11 / ansicht.zoom}px Segoe UI, sans-serif`;
    const w = ctx.measureText(t.name).width;
    ctx.fillStyle = "rgba(15,12,9,.8)";
    ctx.fillRect(cx - w / 2 - 3 / ansicht.zoom, cy + rad + 2 / ansicht.zoom, w + 6 / ansicht.zoom, 14 / ansicht.zoom);
    ctx.fillStyle = "#ece2cf";
    ctx.fillText(t.name, cx, cy + rad + 9 / ansicht.zoom);
    if (tot) {  // durchgestrichen
      ctx.fillRect(cx - w / 2, cy + rad + 9 / ansicht.zoom, w, 1.2 / ansicht.zoom);
    }
  }
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
  ctx.globalAlpha = 1;
}

let animiert = false;
function animieren() {
  if (animiert) return;
  animiert = true;
  const schritt = () => {
    zeichnen();
    if (pings.length) requestAnimationFrame(schritt);
    else animiert = false;
  };
  requestAnimationFrame(schritt);
}

// ------------------------------------------------------------------ Karte: Maus

function punkt(ev) {
  const r = canvas.getBoundingClientRect();
  return [ev.clientX - r.left, ev.clientY - r.top];
}

async function zeigen(feld) {
  const wer = $("#aktion-wer").value;
  pings.push({ x: feld[0], y: feld[1], t: performance.now() });
  animieren();
  const ta = $("#aktion-text");
  ta.value = (ta.value.trimEnd() + ` (${feld[0]},${feld[1]}) `).trimStart();
  if (kampfLaeuft()) meldung("Rechtsklick zeigt nur auf ein Feld. Zum Bewegen den eigenen Charakter mit links ziehen.", "info");
  if (!SL) await api("/api/zeigen", { x: feld[0], y: feld[1], wer });
}

canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());

// ------------------------------------------------------------------ Angriffsmenü (Rechtsklick auf Gegner)

function flankiertC(a, ziel) {
  if ((ziel.groesse || 1) !== 1 || abstandC(a, ziel) > 1) return false;
  const gx = 2 * ziel.x - a.x, gy = 2 * ziel.y - a.y;
  return stand.tokens.some((t) => t !== a && t.art === a.art && tokenFelder(t).some(([x, y]) => x === gx && y === gy)
    && !(t.zustaende || []).some((z) => UNFAEHIG.includes(z)));
}
const UNFAEHIG = ["Bewusstlos", "Sterbend", "Hilflos", "Gelähmt", "Betäubt"];
const tokenFelder = (t) => {
  const g = t.groesse || 1, f = [];
  for (let i = 0; i < g; i++) for (let j = 0; j < g; j++) f.push([t.x + i, t.y + j]);
  return f;
};
const abstandC = (a, b) => Math.min(...tokenFelder(a).flatMap(([x0, y0]) => tokenFelder(b).map(([x1, y1]) => pfDistanz(x0, y0, x1, y1))));

/** Gründe, warum ein Charakter gerade nicht handeln darf (oder null). aktion: standard | schnell | voll */
function kampfSperre(a, aktion = "standard", offensiv = true) {
  if (imKampf()) {
    if (!kampfLaeuft()) return "Erst Initiative würfeln";
    if (stand.slStatus !== "bereit") return "Der Spielleiter ist gerade am Zug";
    if (!amZug(a)) return `${a.name} ist nicht am Zug`;
    const z = stand.zug;
    if (aktion === "schnell" && !z.schnellFrei) return "Schnelle Aktion schon verbraucht";
    if (aktion === "voll" && !(z.standardFrei && z.bewegungFrei)) return "Volle Aktion nicht mehr möglich";
    if (aktion === "standard" && !z.standardFrei) return "Standard-Aktion schon verbraucht";
  } else if (offensiv && stand.angriffAusserhalb) {
    return "Der Kampf beginnt – wartet auf den Spielleiter";
  }
  if ((a.zustaende || []).some((z) => UNFAEHIG.includes(z))) return `${a.name} kann nicht handeln`;
  return null;
}

const RW_NAME = { REF: "Reflex", WIL: "Wille", ZAEH: "Zähigkeit" };

/** Anzeige der freien Plätze: "1/2", "Pool 2/3", "spontan 2" oder "" (beliebig oft) */
function zauberPlaetze(e) {
  const d = e._d;
  if (!d || d.frei == null) return "";
  if (e.spontan) return ` spontan ${d.frei}`;
  if (e.pool) return ` ${d.frei}/${d.poolMax}`;
  return ` ${d.frei}/${e.proTag}`;
}

function zauberBeschreibung(d) {
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
function zauberPrdZeilen(d) {
  const p = d.prd || {};
  const z = [["zeitaufwand", "Zeitaufwand"], ["wirkungsdauer", "Dauer"], ["rettungswurf", "Rettungswurf"], ["zauberresistenz", "ZR"]]
    .filter(([k]) => p[k]).map(([k, t]) => `${t}: ${p[k]}`);
  return z.length ? "\n" + z.join(" · ") : "";
}

function zauberPruefen(a, e, ziel) {
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
let zielModus = null;  // {token, index, e}

async function zauberWirken(t, index, ziel, feld) {
  zielModus = null;
  canvas.style.cursor = "";
  $("#koordinate").textContent = "";
  await api("/api/zaubern", { id: t.id, zauber: index, ziel: ziel?.id, feld });
}

function zauberStarten(c, t, index) {
  const e = c.zauberliste[index];
  const d = e._d;
  if (!t) return meldung(`${c.name} steht nicht auf der Karte`);
  const p = zauberPruefen(t, e, null);
  if (!p.ok) return meldung(`${d?.name || e.name}: ${p.text}`);
  if (!["gegner", "verbuendet", "feld"].includes(d.ziel)) return zauberWirken(t, index, null, null);
  zielModus = { token: t, index, e };
  canvas.style.cursor = "crosshair";
  $("#koordinate").textContent = d.ziel === "feld" ? "Zielfeld anklicken …" : d.ziel === "gegner" ? "Gegner anklicken …" : "Verbündeten anklicken …";
}

const FAEHIGKEIT_AKTION = { standard: "Standard-Aktion", schnell: "Schnelle Aktion", bewegung: "Bewegungsaktion", keine: "keine Aktion" };

function faehigkeitBeschreibung(f) {
  const teile = [FAEHIGKEIT_AKTION[f.aktion || "keine"]];
  if (f.modus === "bereich") teile.push(`${f.radius} m Umkreis`, `${RW_NAME[f.rettungswurf]} SG ${f.sg ?? 10}${f.beiErfolg ? " " + f.beiErfolg : ""}`, `${f.schaden} ${f.art || ""}`.trim());
  if (f.modus === "heilung") teile.push(`heilt ${f.schaden}`);
  if (f.modus === "wurf") teile.push(`würfelt ${f.wurf}`);
  if (f.modus === "sl" || !f.modus) teile.push("der Spielleiter wertet aus");
  if (f.pro) teile.push(f.pro);
  return teile.join(" · ");
}

function faehigkeitPruefen(a, f) {
  const aktion = f.aktion || "keine";
  const sperre = kampfSperre(a, aktion === "schnell" ? "schnell" : aktion === "standard" ? "standard" : "keine",
    f.modus === "bereich" || f.ziel === "gegner");
  if (sperre) return { ok: false, text: sperre };
  if (aktion === "bewegung" && kampfLaeuft() && !stand.zug.bewegungFrei) return { ok: false, text: "Bewegungsaktion schon verbraucht" };
  return { ok: true, text: faehigkeitBeschreibung(f) };
}

async function faehigkeitWirken(t, index, ziel) {
  zielModus = null;
  canvas.style.cursor = "";
  $("#koordinate").textContent = "";
  await api("/api/faehigkeit", { id: t.id, index, ziel: ziel?.id });
}

function faehigkeitStarten(c, t, index) {
  const f = c.faehigkeitenListe[index];
  if (!t) return meldung(`${c.name} steht nicht auf der Karte`);
  const p = faehigkeitPruefen(t, f);
  if (!p.ok) return meldung(`${f.name}: ${p.text}`);
  if (!["gegner", "verbuendet"].includes(f.ziel)) return faehigkeitWirken(t, index, null);
  zielModus = { token: t, faeh: index, e: { name: f.name, _d: { ziel: f.ziel } }, f };
  canvas.style.cursor = "crosshair";
  $("#koordinate").textContent = f.ziel === "gegner" ? "Gegner anklicken …" : "Verbündeten anklicken …";
}

function angriffPruefen(a, ziel, w) {
  const nein = (text) => ({ ok: false, text });
  const sperre = kampfSperre(a, w.serie ? "voll" : "standard");
  if (sperre) return nein(sperre);
  if (w.serie && kampfLaeuft() && stand.zug.bewegt > 1) return nein("Vollangriff: davor höchstens ein 1,5-m-Schritt");
  const pool = (charaktere.find((c) => c.id === a.charId) || {}).betaeubendPool;
  const stunZahl = (w.serie || [w]).filter((x) => (x && typeof x === "object" && "betaeubend" in x ? x.betaeubend : w.betaeubend)).length;
  if (stunZahl && pool && pool.max - pool.verbraucht < stunZahl)
    return nein(`Betäubender Schlag: nur noch ${pool.max - pool.verbraucht} Anwendung(en) heute`);
  const d = abstandC(a, ziel);
  const mods = [];
  if ((ziel.zustaende || []).includes("Liegend")) mods.push(["Ziel liegt", w.fernkampf ? -4 : 4]);
  if (w.fernkampf) {
    const ink = w.inkrement || 9;
    const n = Math.max(1, Math.ceil(meter(d) / ink));
    if (n > 10) return nein(`außer Reichweite (${meter(d)} m, max. ${10 * ink} m)`);
    if (n > 1) mods.push(["Entfernung", -2 * (n - 1)]);
    if (stand.tokens.some((s) => s.art === "sc" && s !== a && abstandC(s, ziel) <= 1)) mods.push(["in den Nahkampf", -4]);
  } else {
    const reich = Math.max(1, a.reichweite || 1);
    if (d > reich) return nein(reich > 1 ? `außerhalb der Reichweite (${meter(d)} m, max. ${meter(reich)} m)` : `steht nicht angrenzend (${meter(d)} m entfernt)`);
    if (flankiertC(a, ziel)) mods.push(["Flankieren", 2]);
  }
  const summe = mods.reduce((s, [, v]) => s + v, 0);
  const art = w.fernkampf ? `Fernkampf · ${meter(d)} m` : "Nahkampf";
  const text = [art, ...mods.map(([t, v]) => `${t} ${vz(v)}`), w.schaden ? `Schaden ${w.schaden}` : ""].filter(Boolean).join(" · ");
  const stunSG = w.betaeubend || (w.serie || []).map((x) => x && x.betaeubend).find(Boolean);
  const rest = stunSG && pool ? `Betäubender Schlag SG ${stunSG} (noch ${pool.max - pool.verbraucht}/${pool.max})` : "";
  return { ok: true, text: [text, rest].filter(Boolean).join(" · "), bonus: (w.bonus || 0) + summe };
}

/** Sturmangriff: nur im Kampf, volle Aktion, Nahkampfwaffe. Liefert null (kein Angebot) oder {ok, text}. */
function sturmangriffPruefen(a, ziel, w) {
  const ch = charaktere.find((c) => c.id === a.charId) || {};
  const anspringen = /anspringen/i.test(`${ch.talente || ""} ${ch.faehigkeiten || ""} ${ch.notizen || ""}`);
  if (!kampfLaeuft() || !amZug(a) || w.fernkampf || w.betaeubend || (w.serie && !anspringen) || (w.beruehrung && !w.schaden)) return null;
  const z = stand.zug;
  const nein = (text) => ({ ok: false, text });
  if (stand.slStatus !== "bereit") return nein("Der Spielleiter ist gerade am Zug");
  if (!z.standardFrei || !z.bewegungFrei || z.bewegt > 0) return nein("Braucht eine volle Aktion, vorher nicht bewegt");
  if ((a.zustaende || []).some((x) => UNFAEHIG.includes(x))) return nein(`${a.name} kann nicht handeln`);
  const d = abstandC(a, ziel);
  if (d < 2) return nein("Das Ziel muss mindestens 3 m entfernt sein");
  const max = 2 * (z.tempo || 6);
  if (d - 1 > max) return nein(`zu weit (max. ${meter(max)} m Anlauf)`);
  return { ok: true, text: `${w.serie ? "Sturmangriff mit Vollangriff (Anspringen)" : "Sturmangriff"} · +2 Angriff · RK −2 bis zum nächsten Zug · bis ${meter(max)} m Anlauf` };
}

function angriffsMenue(ziel, sx, sy) {
  const m = $("#kontextmenue");
  const angreifer = kampfLaeuft()
    ? stand.tokens.filter((t) => t.art === "sc" && amZug(t))
    : stand.tokens.filter((t) => t.art === "sc");
  let html = `<h4>${esc(ziel.name)}${ziel.gesundheit ? ` <small>· ${esc(ziel.gesundheit)}</small>` : ""}</h4>`;
  if (!angreifer.length) html += `<button disabled><b>Kein Angriff möglich</b><small>${imKampf() ? "Gerade ist keiner eurer Charaktere am Zug." : "Keiner eurer Charaktere steht auf der Karte."}</small></button>`;
  for (const a of angreifer) {
    const c = charaktere.find((c) => c.id === a.charId);
    (c?.angriffe || []).forEach((w, i) => {
      if (w.beruehrung && !w.schaden) return;  // nur der Bonus für Berührungszauber, keine eigene Waffe
      const p = angriffPruefen(a, ziel, w);
      const wer = angreifer.length > 1 ? `${a.name}: ` : "";
      html += `<button data-angreifer="${esc(a.id)}" data-i="${i}" ${p.ok ? "" : "disabled"}>
        <b>⚔ ${esc(wer + w.name)}</b><span>${p.ok ? (w.serie ? w.serie.map((x) => vz(x.bonus ?? x)).join("/") : vz(p.bonus)) : ""}</span><small>${esc(p.text)}</small></button>`;
      const sp = sturmangriffPruefen(a, ziel, w);
      if (sp) html += `<button data-sturm="${esc(a.id)}" data-i="${i}" ${sp.ok ? "" : "disabled"}>
        <b>⚡ ${esc(wer + w.name)}: Sturmangriff</b><span>${sp.ok ? (w.serie ? w.serie.map((x) => vz((x.bonus ?? x) + 2)).join("/") : vz((w.bonus || 0) + 2)) : ""}</span><small>${esc(sp.text)}</small></button>`;
    });
    const zauber = (c?.zauberliste || []).map((e, i) => [e, i]).filter(([e]) => e._d?.ziel === "gegner");
    if (zauber.length) html += `<hr>`;
    for (const [e, i] of zauber) {
      const p = zauberPruefen(a, e, ziel);
      const wer = angreifer.length > 1 ? `${a.name}: ` : "";
      const plaetze = zauberPlaetze(e) ? ` (${zauberPlaetze(e).trim()})` : "";
      html += `<button data-zauberer="${esc(a.id)}" data-i="${i}" ${p.ok ? "" : "disabled"}>
        <b>✦ ${esc(wer + e.name)}${plaetze}</b><span></span><small>${esc(p.text)}</small></button>`;
    }
  }
  html += `<hr><button data-zeigen><b>☝ Auf ${esc(ziel.name)} zeigen</b></button>`;
  m.innerHTML = html;
  m.hidden = false;
  const bereich = $("#karte-bereich").getBoundingClientRect();
  m.style.left = Math.min(sx, bereich.width - m.offsetWidth - 8) + "px";
  m.style.top = Math.min(sy, bereich.height - m.offsetHeight - 8) + "px";
  m.onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b || b.disabled) return;
    m.hidden = true;
    if (b.dataset.zeigen !== undefined) return zeigen([ziel.x, ziel.y]);
    if (b.dataset.sturm) return api("/api/sturmangriff", { id: b.dataset.sturm, ziel: ziel.id, angriff: Number(b.dataset.i) });
    if (b.dataset.zauberer) return zauberWirken({ id: b.dataset.zauberer }, Number(b.dataset.i), ziel, null);
    await api("/api/angriff", { id: b.dataset.angreifer, ziel: ziel.id, angriff: Number(b.dataset.i) });
  };
}
document.addEventListener("pointerdown", (ev) => {
  if (ev.target.closest("#kontextmenue")) return;
  if (ev.button === 2 && ev.target === canvas) return;  // der Rechtsklick öffnet es gerade selbst
  $("#kontextmenue").hidden = true;
});

canvas.addEventListener("pointerdown", async (ev) => {
  if (!stand?.karte) return;
  const [sx, sy] = punkt(ev);
  const feld = zelleBei(sx, sy);
  if (zielModus && ev.button === 0) {  // Zauberziel gewählt
    const { token, index, e } = zielModus;
    if (zielModus.faeh != null) {
      const t = tokenBei(sx, sy, zielModus.f.ziel === "gegner");
      if (!t) return meldung("Dort steht niemand – Ziel anklicken oder Esc");
      if (zielModus.f.ziel === "gegner" && t.art === "sc") return meldung("Bitte einen Gegner wählen");
      return faehigkeitWirken(token, zielModus.faeh, t);
    }
    if (e._d.ziel === "feld") return zauberWirken(token, index, null, feld);
    const t = tokenBei(sx, sy, e._d.ziel === "gegner");
    if (!t) return meldung("Dort steht niemand – Ziel anklicken oder Esc");
    if (e._d.ziel === "gegner" && t.art === "sc") return meldung("Bitte einen Gegner wählen");
    const p = zauberPruefen(token, e, t);
    if (!p.ok) return meldung(p.text);
    return zauberWirken(token, index, t, null);
  }
  if (ev.button === 2 && !SL) {
    const t = tokenBei(sx, sy, true);
    if (t && t.art !== "sc") return angriffsMenue(t, sx, sy);
  }
  canvas.setPointerCapture(ev.pointerId);
  if (ev.button === 2 || werkzeug === "zeigen") return zeigen(feld);
  if (platzieren) {
    const cid = platzieren;
    platzieren = null;
    canvas.style.cursor = "";
    await api("/api/sc-platzieren", { charId: cid, x: feld[0], y: feld[1] });
    return;
  }
  if (werkzeug === "messen" || ev.shiftKey) {
    ziehen = { art: "messen", start: feld, ende: feld };
  } else if (werkzeug === "aufdecken" || werkzeug === "verdecken") {
    ziehen = { art: "rechteck", start: feld, ende: feld, auf: werkzeug === "aufdecken" };
  } else {
    let t = tokenBei(sx, sy);
    if (t) ausgewaehlt = t.id;
    if (t && !SL && t.art === "sc" && imKampf() && !meinZug(t)) {  // im Kampf zieht nur, wer am Zug ist
      meldung(!kampfLaeuft() ? "Erst Initiative würfeln" : stand.slStatus !== "bereit"
        ? "Der Spielleiter ist gerade am Zug" : `${t.name} ist nicht am Zug`);
      t = null;
    }
    if (t && darfZiehen(t)) {
      ziehen = { art: "token", token: t, ziel: [t.x, t.y], start: [sx, sy] };
    } else {
      ziehen = { art: "schwenken", start: [sx, sy], ansicht: { ...ansicht }, bewegt: false, token: t };
    }
  }
  zeichnen();
});

canvas.addEventListener("pointermove", (ev) => {
  if (!stand?.karte) return;
  const [sx, sy] = punkt(ev);
  const feld = zelleBei(sx, sy);
  hoverZelle = feld;
  $("#koordinate").textContent = platzieren ? "Feld anklicken …"
    : zielModus ? `✦ ${zielModus.e.name}: Ziel wählen (Esc bricht ab)` : `Feld ${feld[0]}, ${feld[1]}`;
  if (ziehen?.art === "schwenken") {
    const dx = sx - ziehen.start[0], dy = sy - ziehen.start[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) ziehen.bewegt = true;
    ansicht.x = ziehen.ansicht.x + dx;
    ansicht.y = ziehen.ansicht.y + dy;
  } else if (ziehen?.art === "token") {
    ziehen.ziel = feld;
  } else if (ziehen) {
    ziehen.ende = feld;
  }
  tooltip(ev, sx, sy);
  zeichnen();
});

canvas.addEventListener("pointerup", async (ev) => {
  const z = ziehen;
  ziehen = null;
  if (!z) return;
  if (z.art === "token") {
    const [x, y] = z.ziel;
    if (x !== z.token.x || y !== z.token.y) {
      if (SL) await slBefehl({ op: "bewegen", id: z.token.id, x, y });
      else await api("/api/bewegen", { id: z.token.id, x, y });
    }
  } else if (z.art === "schwenken" && !z.bewegt && !z.token) {
    ausgewaehlt = null;
  } else if (z.art === "rechteck") {
    await slBefehl({ op: z.auf ? "aufdecken" : "verdecken", form: "rechteck", felder: [...z.start, ...z.ende] });
  }
  zeichnen();
});

canvas.addEventListener("pointerleave", () => {
  hoverZelle = null;
  $("#tooltip").hidden = true;
  zeichnen();
});

canvas.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const [sx, sy] = punkt(ev);
  zoomen(Math.exp(-ev.deltaY * 0.0015), sx, sy);
}, { passive: false });

function zoomen(faktor, sx, sy) {
  const r = canvas.getBoundingClientRect();
  sx ??= r.width / 2; sy ??= r.height / 2;
  const neu = Math.max(0.1, Math.min(4, ansicht.zoom * faktor));
  ansicht.x = sx - ((sx - ansicht.x) * neu) / ansicht.zoom;
  ansicht.y = sy - ((sy - ansicht.y) * neu) / ansicht.zoom;
  ansicht.zoom = neu;
  zeichnen();
}

function tooltip(ev, sx, sy) {
  const tt = $("#tooltip");
  const t = ziehen ? null : tokenBei(sx, sy);
  if (!t) { tt.hidden = true; return; }
  const zeilen = [`<b>${esc(t.name)}</b>`];
  if (t.tpMax && (t.art === "sc" || SL)) zeilen.push(`TP ${t.tp} / ${t.tpMax}`);
  else if (t.gesundheit) zeilen.push(esc(t.gesundheit));
  if ((t.zustaende || []).length) zeilen.push(esc(t.zustaende.join(", ")));
  if (SL && t.sichtbar === false) zeilen.push("<i>verborgen</i>");
  tt.innerHTML = zeilen.join("<br>");
  tt.hidden = false;
  tt.style.left = sx + 16 + "px";
  tt.style.top = sy + 16 + "px";
}

// ------------------------------------------------------------------ Werkzeugleiste

$$("#werkzeuge [data-werkzeug]").forEach((b) =>
  b.addEventListener("click", () => {
    werkzeug = b.dataset.werkzeug;
    $$("#werkzeuge [data-werkzeug]").forEach((x) => x.classList.toggle("aktiv", x === b));
  })
);
$("#raster-umschalten").addEventListener("click", () => { rasterAn = !rasterAn; zeichnen(); });
$("#barrieren-umschalten").addEventListener("click", () => { barrierenAn = !barrierenAn; zeichnen(); });
$("#zoom-rein").addEventListener("click", () => zoomen(1.25));
$("#zoom-raus").addEventListener("click", () => zoomen(0.8));
$("#zentrieren").addEventListener("click", einpassen);
$("#raster-justieren").classList.add("nur-sl");
$("#raster-justieren").addEventListener("click", () => ($("#raster-panel").hidden = !$("#raster-panel").hidden));
for (const id of ["r-zelle", "r-ox", "r-oy"]) {
  $("#" + id).addEventListener("change", () =>
    slBefehl({ op: "raster", zelle: $("#r-zelle").value, ox: $("#r-ox").value, oy: $("#r-oy").value })
  );
}
window.addEventListener("resize", zeichnen);
window.addEventListener("keydown", (ev) => {
  if (ev.target.matches("input, textarea, select")) return;
  if (ev.key === "Escape") { ausgewaehlt = null; platzieren = null; zielModus = null; canvas.style.cursor = ""; gruppeZeichnen(); zeichnen(); }
});

schleife();
