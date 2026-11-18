// Kampf: Zugleiste, Kampfsperren, Angriffsmenü (Angriff, Sturmangriff).
import { vz } from "./charakter.js";
import { $, api, esc } from "./grundlagen.js";
import { FARBE, meter, pfDistanz, zeigen } from "./karte.js";
import { zauberPlaetze, zauberPruefen, zauberWirken } from "./magie.js";
import { amZug, imKampf, kampfLaeuft } from "./tisch.js";
import { nachschlagen } from "./wissen.js";
import { G } from "./zustand.js";

// ------------------------------------------------------------------ Zugleiste

export function zugleisteZeichnen() {
  const leiste = $("#zugleiste");
  const ini = G.stand.initiative;
  leiste.hidden = !ini.aktiv;
  if (!ini.aktiv) return;
  const z = G.stand.zug;
  const hinweis = $("#zug-hinweis"), akt = $("#zug-aktionen"), knopf = $("#zug-beenden");
  akt.innerHTML = "";
  knopf.hidden = true;
  leiste.classList.remove("mein-zug");

  if (ini.phase !== "laeuft") {
    const namen = new Set(ini.eintraege.map((e) => e.name));
    const fehlend = G.stand.tokens.filter((t) => t.art === "sc" && !namen.has(t.name)).map((t) => t.name);
    $("#zug-runde").textContent = "Kampfbeginn";
    $("#zug-name").textContent = "Würfelt Initiative!";
    $("#zug-farbe").style.background = "var(--rot)";
    hinweis.textContent = fehlend.length
      ? `Noch offen: ${fehlend.join(", ")}. Knopf „Initiative“ auf der Charakterkarte (Reiter Gruppe).`
      : "Alle haben gewürfelt – der Spielleiter eröffnet den Kampf.";
    return;
  }

  const t = G.stand.tokens.find((x) => x.id === z?.tokenId);
  $("#zug-runde").textContent = `Runde ${ini.runde} · am Zug`;
  $("#zug-name").textContent = z?.name || "–";
  $("#zug-farbe").style.background = t?.farbe || FARBE[z?.art] || "#777";
  if (!z || z.art !== "sc") {
    hinweis.textContent = "Der Spielleiter führt die Gegner.";
    return;
  }
  if (G.stand.slStatus !== "bereit") {
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
    b.disabled = !frei || G.stand.slStatus !== "bereit";
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

// ------------------------------------------------------------------ Angriffsmenü (Rechtsklick auf Gegner)

function flankiertC(a, ziel) {
  if ((ziel.groesse || 1) !== 1 || abstandC(a, ziel) > 1) return false;
  const gx = 2 * ziel.x - a.x, gy = 2 * ziel.y - a.y;
  return G.stand.tokens.some((t) => t !== a && t.art === a.art && tokenFelder(t).some(([x, y]) => x === gx && y === gy)
    && !(t.zustaende || []).some((z) => UNFAEHIG.includes(z)));
}
const UNFAEHIG = ["Bewusstlos", "Sterbend", "Hilflos", "Gelähmt", "Betäubt"];
const tokenFelder = (t) => {
  const g = t.groesse || 1, f = [];
  for (let i = 0; i < g; i++) for (let j = 0; j < g; j++) f.push([t.x + i, t.y + j]);
  return f;
};
export const abstandC = (a, b) => Math.min(...tokenFelder(a).flatMap(([x0, y0]) => tokenFelder(b).map(([x1, y1]) => pfDistanz(x0, y0, x1, y1))));

/** Gründe, warum ein Charakter gerade nicht handeln darf (oder null). aktion: standard | schnell | voll */
export function kampfSperre(a, aktion = "standard", offensiv = true) {
  if (imKampf()) {
    if (!kampfLaeuft()) return "Erst Initiative würfeln";
    if (G.stand.slStatus !== "bereit") return "Der Spielleiter ist gerade am Zug";
    if (!amZug(a)) return `${a.name} ist nicht am Zug`;
    const z = G.stand.zug;
    if (aktion === "schnell" && !z.schnellFrei) return "Schnelle Aktion schon verbraucht";
    if (aktion === "voll" && !(z.standardFrei && z.bewegungFrei)) return "Volle Aktion nicht mehr möglich";
    if (aktion === "standard" && !z.standardFrei) return "Standard-Aktion schon verbraucht";
  } else if (offensiv && G.stand.angriffAusserhalb) {
    return "Der Kampf beginnt – wartet auf den Spielleiter";
  }
  if ((a.zustaende || []).some((z) => UNFAEHIG.includes(z))) return `${a.name} kann nicht handeln`;
  return null;
}

function angriffPruefen(a, ziel, w) {
  const nein = (text) => ({ ok: false, text });
  const sperre = kampfSperre(a, w.serie ? "voll" : "standard");
  if (sperre) return nein(sperre);
  if (w.serie && kampfLaeuft() && G.stand.zug.bewegt > 1) return nein("Vollangriff: davor höchstens ein 1,5-m-Schritt");
  const pool = (G.charaktere.find((c) => c.id === a.charId) || {}).betaeubendPool;
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
    if (G.stand.tokens.some((s) => s.art === "sc" && s !== a && abstandC(s, ziel) <= 1)) mods.push(["in den Nahkampf", -4]);
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
  const ch = G.charaktere.find((c) => c.id === a.charId) || {};
  const anspringen = /anspringen/i.test(`${ch.talente || ""} ${ch.faehigkeiten || ""} ${ch.notizen || ""}`);
  if (!kampfLaeuft() || !amZug(a) || w.fernkampf || w.betaeubend || (w.serie && !anspringen) || (w.beruehrung && !w.schaden)) return null;
  const z = G.stand.zug;
  const nein = (text) => ({ ok: false, text });
  if (G.stand.slStatus !== "bereit") return nein("Der Spielleiter ist gerade am Zug");
  if (!z.standardFrei || !z.bewegungFrei || z.bewegt > 0) return nein("Braucht eine volle Aktion, vorher nicht bewegt");
  if ((a.zustaende || []).some((x) => UNFAEHIG.includes(x))) return nein(`${a.name} kann nicht handeln`);
  const d = abstandC(a, ziel);
  if (d < 2) return nein("Das Ziel muss mindestens 3 m entfernt sein");
  const max = 2 * (z.tempo || 6);
  if (d - 1 > max) return nein(`zu weit (max. ${meter(max)} m Anlauf)`);
  return { ok: true, text: `${w.serie ? "Sturmangriff mit Vollangriff (Anspringen)" : "Sturmangriff"} · +2 Angriff · RK −2 bis zum nächsten Zug · bis ${meter(max)} m Anlauf` };
}

export function angriffsMenue(ziel, sx, sy) {
  const m = $("#kontextmenue");
  const angreifer = kampfLaeuft()
    ? G.stand.tokens.filter((t) => t.art === "sc" && amZug(t))
    : G.stand.tokens.filter((t) => t.art === "sc");
  let html = `<h4>${esc(ziel.name)}${ziel.gesundheit ? ` <small>· ${esc(ziel.gesundheit)}</small>` : ""}</h4>`;
  if (!angreifer.length) html += `<button disabled><b>Kein Angriff möglich</b><small>${imKampf() ? "Gerade ist keiner eurer Charaktere am Zug." : "Keiner eurer Charaktere steht auf der Karte."}</small></button>`;
  for (const a of angreifer) {
    const c = G.charaktere.find((c) => c.id === a.charId);
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
        <b>✦ ${esc(wer + e.name)}${plaetze}<span class="nachschlagen-zeichen" data-nachschlagen="${esc(e.name)}" title="„${esc(e.name)}“ nachschlagen">?</span></b><span></span><small>${esc(p.text)}</small></button>`;
    }
  }
  html += `<hr><button data-zeigen><b>☝ Auf ${esc(ziel.name)} zeigen</b></button>`;
  m.innerHTML = html;
  m.hidden = false;
  const bereich = $("#karte-bereich").getBoundingClientRect();
  m.style.left = Math.min(sx, bereich.width - m.offsetWidth - 8) + "px";
  m.style.top = Math.min(sy, bereich.height - m.offsetHeight - 8) + "px";
  m.onclick = async (ev) => {
    const ns = ev.target.closest("[data-nachschlagen]");
    if (ns) return nachschlagen("zauber", ns.dataset.nachschlagen);
    const b = ev.target.closest("button");
    if (!b || b.disabled) return;
    m.hidden = true;
    if (b.dataset.zeigen !== undefined) return zeigen([ziel.x, ziel.y]);
    if (b.dataset.sturm) return api("/api/sturmangriff", { id: b.dataset.sturm, ziel: ziel.id, angriff: Number(b.dataset.i) });
    if (b.dataset.zauberer) return zauberWirken({ id: b.dataset.zauberer }, Number(b.dataset.i), ziel, null);
    await api("/api/angriff", { id: b.dataset.angreifer, ziel: ziel.id, angriff: Number(b.dataset.i) });
  };
}
