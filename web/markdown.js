// Markdown der Regeldatenbank (bereiche/wissen/regeln_md.py) als HTML: Absätze, Überschriften, Listen,
// Tabellen, Zitate, **fett**, *kursiv*, Hochzahl^1. Alles wird zuerst mit esc() entschärft.
import { esc } from "./grundlagen.js";

// verweis(text) -> Eintrag („zauber:Hast“) oder null: kursive Begriffe (meist Zauber, Zustände) werden Links
function zeile(t, verweis) {
  let h = esc(t);
  h = h.replace(/(^|\s)\*([^*\s][^*\n]*?)\*\*(?!\*)/g, "$1**$2**");  // „*Immunitäten**“ aus dem PRD: gemeint ist fett
  h = h.replace(/\*\*([^*\n]+?)\*\*/g, "<b>$1</b>");
  h = h.replace(/(^|[^*\w])\*([^*\n]+?)\*(?!\*)/g, (_, vor, inner) => {
    const e = verweis?.(inner.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&"));
    return vor + (e ? `<a class="verweis" data-e="${esc(e)}" href="#"><i>${inner}</i></a>` : `<i>${inner}</i>`);
  });
  h = h.replace(/\*\*/g, "");  // verwaiste Marker (z. B. „*Immunitäten**“)
  h = h.replace(/(\S)\^(\d+|[a-z])\b/g, "$1<sup>$2</sup>");
  return h;
}

function tabelle(zeilen, verweis) {
  const zellen = (z) => z.trim().replace(/^\||\|$/g, "").split("|").map((x) => x.trim());
  const trenner = (z) => /^\|?\s*:?-{3,}/.test(z.trim());
  let kopf = null;
  let rumpf = zeilen;
  if (zeilen.length > 1 && trenner(zeilen[1])) {
    kopf = zellen(zeilen[0]);
    rumpf = zeilen.slice(2);
  }
  rumpf = rumpf.filter((z) => !trenner(z));
  return `<div class="tabelle"><table>${kopf ? `<thead><tr>${kopf.map((c) => `<th>${zeile(c, verweis)}</th>`).join("")}</tr></thead>` : ""}` +
    `<tbody>${rumpf.map((z) => `<tr>${zellen(z).map((c) => `<td>${zeile(c, verweis)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

export function mdHtml(text, verweis = null, ebene = 2) {
  const zeilen = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
  const aus = [];
  let i = 0;
  const sammeln = (pruef) => {
    const block = [];
    while (i < zeilen.length && pruef(zeilen[i])) block.push(zeilen[i++]);
    return block;
  };
  while (i < zeilen.length) {
    const z = zeilen[i];
    if (!z.trim()) { i++; continue; }
    let m;
    if (/^\s*\|/.test(z)) {
      aus.push(tabelle(sammeln((x) => /^\s*\|/.test(x)), verweis));
    } else if ((m = z.match(/^(#{1,6})\s+(.*)$/))) {
      const h = Math.min(6, m[1].length + ebene - 1);
      aus.push(`<h${h}>${zeile(m[2].replace(/\s*\[\d+\]\s*$/, ""), verweis)}</h${h}>`);
      i++;
    } else if (/^\s*([-*+]|\d+[.)])\s+/.test(z) && !/^\s*\*\*/.test(z)) {
      const geordnet = /^\s*\d/.test(z);
      const punkte = sammeln((x) => /^\s*([-*+]|\d+[.)])\s+/.test(x) && !/^\s*\*\*/.test(x));
      const tag = geordnet ? "ol" : "ul";
      aus.push(`<${tag}>${punkte.map((p) => `<li>${zeile(p.replace(/^\s*([-*+]|\d+[.)])\s+/, ""), verweis)}</li>`).join("")}</${tag}>`);
    } else if (/^\s*>/.test(z)) {
      const q = sammeln((x) => /^\s*>/.test(x)).map((x) => x.replace(/^\s*>\s?/, ""));
      aus.push(`<blockquote>${q.map((x) => zeile(x, verweis)).join("<br>")}</blockquote>`);
    } else if (/^\s*(-{3,}|\*{3,})\s*$/.test(z)) {
      aus.push("<hr>");
      i++;
    } else {
      const absatz = sammeln((x) => x.trim() && !/^\s*\|/.test(x) && !/^#{1,6}\s/.test(x) && !/^\s*>/.test(x)
        && !(/^\s*([-*+]|\d+[.)])\s+/.test(x) && !/^\s*\*\*/.test(x)));
      if (!absatz.length) absatz.push(zeilen[i++]);
      aus.push(`<p>${absatz.map((x) => zeile(x, verweis)).join("<br>")}</p>`);
    }
  }
  return aus.join("\n");
}

// Suchwörter im Ausschnitt hervorheben (Wortanfänge, ohne Groß-/Kleinschreibung)
export function hervorheben(text, frage) {
  let h = esc(text);
  const woerter = [...new Set(String(frage || "").toLowerCase().match(/[0-9a-zäöüß]{3,}/g) || [])];
  if (!woerter.length) return h;
  const muster = new RegExp(`(^|[^0-9a-zäöüß])(${woerter.map((w) => w.slice(0, Math.max(3, w.length - 2))
    .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})([0-9a-zäöüß]*)`, "gi");
  return h.replace(muster, "$1<mark>$2$3</mark>");
}
