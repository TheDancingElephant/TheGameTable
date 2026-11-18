// Tisch: Server-Schleife, Kopf, Protokoll, Erzählstimme, Aktionen und Würfel, Reiter, Unterlagen.
import { ausruestungZeichnen } from "./besitz.js";
import { charAuswahlFuellen, gruppeZeichnen, scToken } from "./charakter.js";
import { $, $$, SL, api, esc, schlaf, slBefehl } from "./grundlagen.js";
import { zugleisteZeichnen } from "./kampf.js";
import { animieren, karteLaden, zeichnen } from "./karte.js";
import { G } from "./zustand.js";

// ------------------------------------------------------------------ Server-Schleife

export async function schleife() {
  let v = 0;
  for (;;) {
    try {
      const r = await fetch(`/api/stand?seit=${v}${SL ? "&sl=" + encodeURIComponent(SL) : ""}`);
      if (!r.ok) throw new Error(r.status);
      const s = await r.json();
      v = s.version;
      G.charaktere = await (await fetch("/api/charaktere")).json();
      aktualisieren(s);
    } catch (e) {
      statusPill("offline");
      await schlaf(2000);
    }
  }
}

// Kampfzustand
export const imKampf = () => !!G.stand?.initiative?.aktiv;
export const kampfLaeuft = () => imKampf() && G.stand.initiative.phase === "laeuft";
export const amZug = (t) => kampfLaeuft() && G.stand.zug?.tokenId === t?.id;
export const meinZug = (t) => amZug(t) && G.stand.slStatus === "bereit";

function aktualisieren(s) {
  G.stand = s;
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
  G.ersteLadung = false;
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
  if (SL || G.stand?.slStatus !== "bereit") return;
  api("/api/anstupsen", {}).catch(() => {});
});

function kopfZeichnen() {
  $("#szene-titel").textContent = G.stand.szene?.titel || "";
  $("#szene-untertitel").textContent = G.stand.szene?.untertitel || "";
  document.title = (G.stand.szene?.titel ? G.stand.szene.titel + " · " : "") + (G.stand.kampagne || "Spieltisch");
  statusPill(G.stand.slStatus);
  const ini = G.stand.initiative;
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
  const log = G.stand.protokoll;
  const neueste = log.length ? log[log.length - 1].id : 0;
  if (neueste === G.letzteLogId) return;
  const box = $("#protokoll");
  const unten = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  box.innerHTML = log.map(eintragHtml).join("");
  if (unten || G.ersteLadung) requestAnimationFrame(() => (box.scrollTop = box.scrollHeight));
  if (!G.ersteLadung) {
    const neueErz = log.filter((e) => e.id > G.letzteLogId && e.art === "sl");
    if (stimme.auto && neueErz.length) vorlesen(neueErz[neueErz.length - 1]);
    for (const e of log) {
      if (e.id > G.letzteLogId && e.art === "zeigen" && e.feld) G.pings.push({ x: e.feld[0], y: e.feld[1], t: performance.now() });
    }
    if (G.pings.length) animieren();
  }
  G.letzteLogId = neueste;
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
  const e = G.stand.protokoll.find((x) => x.id === id);
  if (e) vorlesen(e);
});

// ------------------------------------------------------------------ Aktionen & Würfel

function werSelectFuellen() {
  const sel = $("#aktion-wer");
  const namen = ["Gruppe", ...G.charaktere.map((c) => c.name)];
  if (SL) namen.unshift("SL");
  const sig = namen.join("|");
  if (sel.dataset.sig !== sig) {
    const alt = sel.value;
    sel.innerHTML = namen.map((n) => `<option>${esc(n)}</option>`).join("");
    sel.dataset.sig = sig;
    if (namen.includes(alt)) sel.value = alt;
  }
  // Im Kampf spricht der Charakter, der am Zug ist
  const sprecher = !SL && kampfLaeuft() && G.stand.zug?.art === "sc" ? G.stand.zug.name : null;
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

export async function wuerfeln(ausdruck, grund, wer, extra = {}) {
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
    for (const c of G.charaktere) {
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
  if (!imKampf() || G.stand.initiative.phase === "laeuft") return [];
  const da = new Set(G.stand.initiative.eintraege.map((e) => e.name));
  return G.charaktere.filter((c) => !da.has(c.name) && scToken(c.id));
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

// ------------------------------------------------------------------ Unterlagen

let unterlagenSig = "";
function unterlagenZeichnen() {
  const u = G.stand.unterlagen || { karten: [], handouts: [], notizen: "" };
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
  const k = G.stand.unterlagen.karten.find((x) => x.id === kid);
  if (!k) return;
  $("#betrachter-titel").textContent = k.name;
  const leg = k.legende && G.stand.unterlagen.handouts.find((h) => h.id === k.legende);
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
