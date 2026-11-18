"""HTML einer PRD-Seite (WackoWiki) -> Markdown-Blöcke, ohne Fremdpakete.

`umwandeln(html_inhalt)` liefert eine Liste von Blöcken:
  ("h", stufe, text)      Überschrift (stufe 1–6)
  ("p", text)             Absatz / Liste / Tabelle als fertiger Markdown-Text
Links werden zu reinem Text (spart Tokens), Hervorhebungen bleiben (**fett**, *kursiv*).
"""
import html as _html
import re
from html.parser import HTMLParser

BLOCK = {"p", "div", "ul", "ol", "li", "table", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
         "section", "article", "dl", "dt", "dd", "pre", "hr", "caption", "thead", "tbody", "tfoot"}
SKIP = {"script", "style", "nav", "noscript", "img", "button", "form", "select", "textarea"}


def text_norm(s):
    s = s.replace("\xa0", " ").replace("​", "").replace("­", "")
    return re.sub(r"[ \t\r\f\v]+", " ", s)


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bloecke = []
        self.puffer = []          # Inline-Text des aktuellen Blocks
        self.skip = 0
        self.skip_tags = []
        self.listen = []          # Stapel: "ul"/"ol" mit Zähler
        self.tabellen = []        # Stapel von Tabellen: {"zeilen": [[(text, colspan, th)]], "zelle": None}
        self.ueberschrift = None
        self.inline = []          # offene **/* Marker

    # --- Hilfen ---
    def _text(self):
        t = text_norm("".join(self.puffer))
        self.puffer = []
        self.inline = []
        t = re.sub(r"\*\*(\s+)\*\*", r"\1", t)
        t = re.sub(r"\*\*(\S[^*\n]*?)(\s+)\*\*", r"**\1**\2", t)   # Leerzeichen vor dem Schluss-Marker
        t = re.sub(r" *\n *", "\n", t)
        return t.strip()

    def _fluss(self):
        """Gesammelten Inline-Text als Block abschließen."""
        if self.tabellen and self.tabellen[-1]["zelle"] is not None:
            return
        t = self._text()
        if not t:
            return
        if self.listen:
            art, _ = self.listen[-1]
            tiefe = len(self.listen) - 1
            if art == "ol":
                self.listen[-1][1] += 1
                marke = f"{self.listen[-1][1]}."
            else:
                marke = "-"
            t = "  " * tiefe + marke + " " + t.replace("\n", "\n" + "  " * (tiefe + 1))
            if self.bloecke and self.bloecke[-1][0] == "li":
                self.bloecke[-1] = ("li", self.bloecke[-1][1] + "\n" + t)
                return
            self.bloecke.append(("li", t))
            return
        self.bloecke.append(("p", t))

    # --- Parser ---
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip:
            if tag in SKIP or tag == self.skip_tags[-1]:
                pass
            if tag not in ("br", "img", "hr", "input", "meta", "link"):
                self.skip_tags.append(tag)
                self.skip += 1
            return
        cls = a.get("class") or ""
        if tag in SKIP or (tag == "a" and ("self-link" in cls)) or "layout-box" in cls:
            if tag not in ("img",):
                self.skip_tags.append(tag)
                self.skip += 1
            return
        if tag == "br":
            self.puffer.append("\n")
            return
        if tag in ("strong", "b", "em", "i"):
            self.inline.append((tag, len(self.puffer)))
            self.puffer.append("**" if tag in ("strong", "b") else "*")
        elif tag == "sup":
            self.puffer.append("^")
        elif re.fullmatch(r"h[1-6]", tag):
            self._fluss()
            self.ueberschrift = int(tag[1])
            self.anker = a.get("id")
        elif tag == "table":
            self._fluss()
            self.tabellen.append({"zeilen": [], "zelle": None})
        elif tag == "tr" and self.tabellen:
            self.tabellen[-1]["zeilen"].append([])
        elif tag in ("td", "th") and self.tabellen:
            tb = self.tabellen[-1]
            if not tb["zeilen"]:
                tb["zeilen"].append([])
            tb["zelle"] = [tag == "th", int(a.get("colspan") or 1) if (a.get("colspan") or "1").isdigit() else 1]
            self.puffer = []
        elif tag in ("ul", "ol"):
            self._fluss()
            self.listen.append([tag, 0])
        elif tag == "li":
            self._fluss()
        elif tag in BLOCK:
            self._fluss()

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.puffer.append("\n")

    def handle_endtag(self, tag):
        if self.skip:
            if self.skip_tags and self.skip_tags[-1] == tag:
                self.skip_tags.pop()
                self.skip -= 1
            elif tag in self.skip_tags:
                while self.skip_tags and self.skip_tags[-1] != tag:
                    self.skip_tags.pop(); self.skip -= 1
                if self.skip_tags:
                    self.skip_tags.pop(); self.skip -= 1
            return
        if tag in ("strong", "b", "em", "i"):
            if self.inline and self.inline[-1][0] == tag:
                _, i = self.inline.pop()
                if i < len(self.puffer) and not "".join(self.puffer[i + 1:]).strip():
                    self.puffer[i] = ""           # leere Hervorhebung weglassen
                elif i < len(self.puffer):
                    self.puffer.append("**" if tag in ("strong", "b") else "*")
        elif re.fullmatch(r"h[1-6]", tag) and self.ueberschrift:
            t = self._text().replace("\n", " ").replace("**", "").strip(" *")
            if t:
                self.bloecke.append(("h", self.ueberschrift, t, getattr(self, "anker", None)))
            self.ueberschrift = None
        elif tag in ("td", "th") and self.tabellen and self.tabellen[-1]["zelle"] is not None:
            tb = self.tabellen[-1]
            th, span = tb["zelle"]
            tb["zelle"] = None
            t = self._text().replace("\n", " ").replace("|", "/")
            tb["zeilen"][-1].append((t, span, th))
        elif tag == "table" and self.tabellen:
            tb = self.tabellen.pop()
            md = _tabelle(tb["zeilen"])
            if self.tabellen and self.tabellen[-1]["zelle"] is not None:
                self.puffer.append(" " + md.replace("\n", " ") + " ")
            elif md:
                self.bloecke.append(("p", md))
        elif tag in ("ul", "ol"):
            self._fluss()
            if self.listen:
                self.listen.pop()
        elif tag in BLOCK:
            self._fluss()

    def handle_data(self, data):
        if self.skip:
            return
        self.puffer.append(data.replace("\n", " "))

    def close(self):
        super().close()
        self._fluss()


def _tabelle(zeilen):
    zeilen = [z for z in zeilen if z]
    if not zeilen:
        return ""
    rows = []
    for z in zeilen:
        r = []
        for t, span, _ in z:
            r.append(t)
            r.extend([""] * (max(1, span) - 1))
        rows.append(r)
    breite = max(len(r) for r in rows)
    rows = [r + [""] * (breite - len(r)) for r in rows]
    if all(not any(c for c in r) for r in rows[1:]) and len(rows) <= 2:
        return ""  # leere (per JavaScript gefüllte) Tabelle
    kopf = rows[0]
    aus = ["| " + " | ".join(kopf) + " |", "|" + "---|" * breite]
    aus += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(aus)


def umwandeln(html_inhalt):
    p = _P()
    p.feed(html_inhalt)
    p.close()
    aus = []
    for b in p.bloecke:
        if b[0] == "li":
            aus.append(("p", b[1]))
        else:
            aus.append(b)
    return aus


def als_markdown(bloecke):
    teile = []
    for b in bloecke:
        if b[0] == "h":
            teile.append("#" * b[1] + " " + b[2])
        else:
            teile.append(b[1])
    return "\n\n".join(teile) + "\n"
