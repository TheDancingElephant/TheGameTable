// Karte: Geometrie, Zeichnen, Maus/Werkzeuge, Zoom, Tooltip.
import { gruppeZeichnen } from "./charakter.js";
import { $, $$, SL, api, esc, meldung, slBefehl } from "./grundlagen.js";
import { angriffsMenue } from "./kampf.js";
import { faehigkeitWirken, zauberPruefen, zauberWirken } from "./magie.js";
import { amZug, imKampf, kampfLaeuft, meinZug } from "./tisch.js";
import { G, ansicht, bild } from "./zustand.js";

// ------------------------------------------------------------------ Karte: Geometrie

export const canvas = $("#karte");
const ctx = canvas.getContext("2d");

export function karteLaden() {
  const k = G.stand.karte;
  $("#keine-karte").hidden = !!k;
  if (!k) return;
  const schluessel = `${k.id}:${k.nebelVersion}`;
  if (schluessel !== G.bildSchluessel) {
    G.bildSchluessel = schluessel;
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
  const k = G.stand?.karte;
  if (!k) return;
  const r = canvas.getBoundingClientRect();
  // Gruppe vorhanden? Dann auf sie zentrieren, sonst auf aufgedeckten Bereich, sonst ganze Karte
  const scs = G.stand.tokens.filter((t) => t.art === "sc");
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
  const k = G.stand.karte;
  const [wx, wy] = welt(sx, sy);
  return [Math.floor((wx - k.ox) / k.zelle), Math.floor((wy - k.oy) / k.zelle)];
}
export const pfDistanz = (x0, y0, x1, y1) => {
  const dx = Math.abs(x1 - x0), dy = Math.abs(y1 - y0);
  return Math.max(dx, dy) + Math.floor(Math.min(dx, dy) / 2);
};
export const meter = (felder) => +(felder * (G.stand.karte?.meterProFeld || 1.5)).toFixed(1);

function tokenBei(sx, sy) {
  const k = G.stand.karte;
  const [wx, wy] = welt(sx, sy);
  const liste = [...G.stand.tokens].reverse();
  return liste.find((t) => {
    const g = t.groesse || 1;
    const x0 = k.ox + t.x * k.zelle, y0 = k.oy + t.y * k.zelle;
    return wx >= x0 && wx < x0 + g * k.zelle && wy >= y0 && wy < y0 + g * k.zelle;
  });
}
const darfZiehen = (t) => SL || t.art === "sc";

// ------------------------------------------------------------------ Karte: Zeichnen

export const FARBE = { gegner: "#b3261e", nsc: "#c99a1a", objekt: "#6f6f6f", sc: "#3a7bd5" };

export function zeichnen() {
  const dpr = window.devicePixelRatio || 1;
  const r = canvas.getBoundingClientRect();
  if (canvas.width !== Math.round(r.width * dpr) || canvas.height !== Math.round(r.height * dpr)) {
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, r.width, r.height);
  const k = G.stand?.karte;
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
  const aktiv = kampfLaeuft() ? G.stand.tokens.find((t) => t.id === G.stand.zug?.tokenId) : null;
  const sel = imKampf() ? (aktiv?.art === "sc" && G.stand.slStatus === "bereit" ? aktiv : null)
    : G.stand.tokens.find((t) => t.id === G.ausgewaehlt);
  if (sel && sel.art === "sc" && !G.ziehen) {
    const c = G.charaktere.find((c) => c.id === sel.charId);
    const tempo = Math.floor((c?.bewegung || 9) / (k.meterProFeld || 1.5));
    // grün: ohne die Standard-Aktion erreichbar, gelb: nur mit Doppelbewegung
    let [nah, fern] = [tempo, 2 * tempo];
    if (sel === aktiv) {
      const z = G.stand.zug;
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

  if (SL && G.barrierenAn) {
    const sk = `${k.id}:${G.stand.version}`;
    if (G.barrierenCache.schluessel !== sk && !G.barrierenCache.laedt) {
      G.barrierenCache.laedt = true;
      fetch(`/api/sl/barrieren?karte=${encodeURIComponent(k.id)}&sl=${encodeURIComponent(SL)}`).then((r) => r.json())
        .then((d) => { G.barrierenCache = { schluessel: sk, daten: d, laedt: false }; zeichnen(); })
        .catch(() => { G.barrierenCache.laedt = false; });
    }
    const d = G.barrierenCache.daten;
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

  if (G.rasterAn) {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.28)";
    ctx.lineWidth = 1 / ansicht.zoom;
    ctx.beginPath();
    for (let x = fx0; x <= fx1 + 1; x++) { ctx.moveTo(zx(x), zy(fy0)); ctx.lineTo(zx(x), zy(fy1 + 1)); }
    for (let y = fy0; y <= fy1 + 1; y++) { ctx.moveTo(zx(fx0), zy(y)); ctx.lineTo(zx(fx1 + 1), zy(y)); }
    ctx.stroke();
  }
  ctx.restore();

  if (G.hoverZelle && !G.ziehen) {
    ctx.strokeStyle = "rgba(240, 201, 106, 0.8)";
    ctx.lineWidth = 2 / ansicht.zoom;
    ctx.strokeRect(zx(G.hoverZelle[0]), zy(G.hoverZelle[1]), Z, Z);
  }

  // Rechteck-Auswahl (SL: Nebel)
  if (G.ziehen?.art === "rechteck") {
    const [a, b] = [G.ziehen.start, G.ziehen.ende];
    ctx.fillStyle = G.ziehen.auf ? "rgba(240, 201, 106, 0.25)" : "rgba(30, 30, 60, 0.45)";
    ctx.fillRect(zx(Math.min(a[0], b[0])), zy(Math.min(a[1], b[1])), (Math.abs(a[0] - b[0]) + 1) * Z, (Math.abs(a[1] - b[1]) + 1) * Z);
  }

  for (const t of G.stand.tokens) {
    if (G.ziehen?.art === "token" && G.ziehen.token.id === t.id) {
      tokenZeichnen(t, t.x, t.y, 0.35);
    } else {
      tokenZeichnen(t, t.x, t.y, t.sichtbar === false ? 0.5 : 1);
    }
  }

  // Ziehen eines Tokens / Messen: Linie und Entfernung
  if (G.ziehen?.art === "token" || G.ziehen?.art === "messen") {
    const [a, b] = G.ziehen.art === "token" ? [[G.ziehen.token.x, G.ziehen.token.y], G.ziehen.ziel] : [G.ziehen.start, G.ziehen.ende];
    const g = G.ziehen.art === "token" ? G.ziehen.token.groesse || 1 : 1;
    ctx.strokeStyle = "#f0c96a";
    ctx.lineWidth = 3 / ansicht.zoom;
    ctx.setLineDash([8 / ansicht.zoom, 6 / ansicht.zoom]);
    ctx.beginPath();
    ctx.moveTo(zx(a[0] + g / 2), zy(a[1] + g / 2));
    ctx.lineTo(zx(b[0] + g / 2), zy(b[1] + g / 2));
    ctx.stroke();
    ctx.setLineDash([]);
    if (G.ziehen.art === "token") tokenZeichnen(G.ziehen.token, b[0], b[1], 0.9);
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
  G.pings = G.pings.filter((p) => jetzt - p.t < 2500);
  for (const p of G.pings) {
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
  const k = G.stand.karte;
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
  ctx.strokeStyle = t.id === G.ausgewaehlt ? "#f0c96a" : "#fff";
  ctx.lineWidth = (t.id === G.ausgewaehlt ? 4 : 2.5) * Math.max(1, 1 / ansicht.zoom) * 0.8;
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
export function animieren() {
  if (animiert) return;
  animiert = true;
  const schritt = () => {
    zeichnen();
    if (G.pings.length) requestAnimationFrame(schritt);
    else animiert = false;
  };
  requestAnimationFrame(schritt);
}

// ------------------------------------------------------------------ Karte: Maus

function punkt(ev) {
  const r = canvas.getBoundingClientRect();
  return [ev.clientX - r.left, ev.clientY - r.top];
}

export async function zeigen(feld) {
  const wer = $("#aktion-wer").value;
  G.pings.push({ x: feld[0], y: feld[1], t: performance.now() });
  animieren();
  const ta = $("#aktion-text");
  ta.value = (ta.value.trimEnd() + ` (${feld[0]},${feld[1]}) `).trimStart();
  if (kampfLaeuft()) meldung("Rechtsklick zeigt nur auf ein Feld. Zum Bewegen den eigenen Charakter mit links ziehen.", "info");
  if (!SL) await api("/api/zeigen", { x: feld[0], y: feld[1], wer });
}

canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());

document.addEventListener("pointerdown", (ev) => {
  if (ev.target.closest("#kontextmenue")) return;
  if (ev.button === 2 && ev.target === canvas) return;  // der Rechtsklick öffnet es gerade selbst
  $("#kontextmenue").hidden = true;
});

canvas.addEventListener("pointerdown", async (ev) => {
  if (!G.stand?.karte) return;
  const [sx, sy] = punkt(ev);
  const feld = zelleBei(sx, sy);
  if (G.zielModus && ev.button === 0) {  // Zauberziel gewählt
    const { token, index, e } = G.zielModus;
    if (G.zielModus.faeh != null) {
      const t = tokenBei(sx, sy, G.zielModus.f.ziel === "gegner");
      if (!t) return meldung("Dort steht niemand – Ziel anklicken oder Esc");
      if (G.zielModus.f.ziel === "gegner" && t.art === "sc") return meldung("Bitte einen Gegner wählen");
      return faehigkeitWirken(token, G.zielModus.faeh, t);
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
  if (ev.button === 2 || G.werkzeug === "zeigen") return zeigen(feld);
  if (G.platzieren) {
    const cid = G.platzieren;
    G.platzieren = null;
    canvas.style.cursor = "";
    await api("/api/sc-platzieren", { charId: cid, x: feld[0], y: feld[1] });
    return;
  }
  if (G.werkzeug === "messen" || ev.shiftKey) {
    G.ziehen = { art: "messen", start: feld, ende: feld };
  } else if (G.werkzeug === "aufdecken" || G.werkzeug === "verdecken") {
    G.ziehen = { art: "rechteck", start: feld, ende: feld, auf: G.werkzeug === "aufdecken" };
  } else {
    let t = tokenBei(sx, sy);
    if (t) G.ausgewaehlt = t.id;
    if (t && !SL && t.art === "sc" && imKampf() && !meinZug(t)) {  // im Kampf zieht nur, wer am Zug ist
      meldung(!kampfLaeuft() ? "Erst Initiative würfeln" : G.stand.slStatus !== "bereit"
        ? "Der Spielleiter ist gerade am Zug" : `${t.name} ist nicht am Zug`);
      t = null;
    }
    if (t && darfZiehen(t)) {
      G.ziehen = { art: "token", token: t, ziel: [t.x, t.y], start: [sx, sy] };
    } else {
      G.ziehen = { art: "schwenken", start: [sx, sy], ansicht: { ...ansicht }, bewegt: false, token: t };
    }
  }
  zeichnen();
});

canvas.addEventListener("pointermove", (ev) => {
  if (!G.stand?.karte) return;
  const [sx, sy] = punkt(ev);
  const feld = zelleBei(sx, sy);
  G.hoverZelle = feld;
  $("#koordinate").textContent = G.platzieren ? "Feld anklicken …"
    : G.zielModus ? `✦ ${G.zielModus.e.name}: Ziel wählen (Esc bricht ab)` : `Feld ${feld[0]}, ${feld[1]}`;
  if (G.ziehen?.art === "schwenken") {
    const dx = sx - G.ziehen.start[0], dy = sy - G.ziehen.start[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) G.ziehen.bewegt = true;
    ansicht.x = G.ziehen.ansicht.x + dx;
    ansicht.y = G.ziehen.ansicht.y + dy;
  } else if (G.ziehen?.art === "token") {
    G.ziehen.ziel = feld;
  } else if (G.ziehen) {
    G.ziehen.ende = feld;
  }
  tooltip(ev, sx, sy);
  zeichnen();
});

canvas.addEventListener("pointerup", async (ev) => {
  const z = G.ziehen;
  G.ziehen = null;
  if (!z) return;
  if (z.art === "token") {
    const [x, y] = z.ziel;
    if (x !== z.token.x || y !== z.token.y) {
      if (SL) await slBefehl({ op: "bewegen", id: z.token.id, x, y });
      else await api("/api/bewegen", { id: z.token.id, x, y });
    }
  } else if (z.art === "schwenken" && !z.bewegt && !z.token) {
    G.ausgewaehlt = null;
  } else if (z.art === "rechteck") {
    await slBefehl({ op: z.auf ? "aufdecken" : "verdecken", form: "rechteck", felder: [...z.start, ...z.ende] });
  }
  zeichnen();
});

canvas.addEventListener("pointerleave", () => {
  G.hoverZelle = null;
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
  const t = G.ziehen ? null : tokenBei(sx, sy);
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
    G.werkzeug = b.dataset.werkzeug;
    $$("#werkzeuge [data-werkzeug]").forEach((x) => x.classList.toggle("aktiv", x === b));
  })
);
$("#raster-umschalten").addEventListener("click", () => { G.rasterAn = !G.rasterAn; zeichnen(); });
$("#barrieren-umschalten").addEventListener("click", () => { G.barrierenAn = !G.barrierenAn; zeichnen(); });
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
  if (ev.key === "Escape") { G.ausgewaehlt = null; G.platzieren = null; G.zielModus = null; canvas.style.cursor = ""; gruppeZeichnen(); zeichnen(); }
});
