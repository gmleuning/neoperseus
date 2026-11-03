"""Import a Wikisource EPUB export into the library format.

Wikisource exports every text with the same MediaWiki markup, so one converter handles them
all. The result is a draft: look it over (front matter, an introduction you may want to
keep or drop) and edit the Markdown file directly.

What it does:
- Takes the chapter files in reading order; skips the export's title and about pages.
- Drops scan page markers, edit links, header templates, images and styles.
- Turns footnotes into [^n] notes.
- Verse (poem blocks, or paragraphs made of line breaks) becomes one line per line. Line
  numbers printed in the text ("[10]") become explicit keys; other lines are counted.
  A line indented with spaces continues the previous line's number (a line shared
  between speakers).
- A bold name opening a verse line becomes a speaker.
- Headings become sections (##) or labels (###). A heading that is only a number or
  "Fragment 12" becomes a key instead, so fragment collections sync by fragment number.
"""
import re
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from lxml import etree, html as lhtml

DROP_CLASSES = ("pagenum", "ws-pagenum", "mw-editsection", "noprint", "mw-cite-backlink",
                "headertemplate", "ws-noexport", "wst-header", "licenseContainer", "reflist-hidden")
FRAGMENT = re.compile(r"^(?:fragment|fr\.?|frag\.?)\s*([0-9]+[a-z]?(?:[-–][0-9]+[a-z]?)?)\.?$"
                      r"|^([0-9]+[a-z]?(?:[-–][0-9]+[a-z]?)?|[IVXLC]+)\.?$", re.I)
HEAD = "\ue000H"        # a centred line inside a poem: a label, not a numbered line
LINE_NO = re.compile(r"^\[?\s*(\d+[a-z]?)\s*\]?$")
OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
LANG = {"el": "grc", "grc": "grc", "la": "lat", "en": "eng"}
TOKEN_KEY = "⟦{}⟧"        # ⟦n⟧ marks a printed line number until lines are cut


def norm(s):
    s = unicodedata.normalize("NFC", s.replace("\xa0", " "))
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def classes(el):
    return (el.get("class") or "").split()


def read_epub(path):
    z = zipfile.ZipFile(path)
    container = etree.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").get("full-path")
    opf = etree.fromstring(z.read(opf_path))
    base = PurePosixPath(opf_path).parent
    meta = {
        "title": " ".join(opf.xpath("//dc:title/text()", namespaces=OPF_NS)).strip(),
        "author": " ".join(opf.xpath("//dc:creator/text()", namespaces=OPF_NS)).strip(),
        "language": " ".join(opf.xpath("//dc:language/text()", namespaces=OPF_NS)).strip(),
        "source": " ".join(opf.xpath("//dc:source/text()", namespaces=OPF_NS)).strip(),
    }
    items = {i.get("id"): i.get("href") for i in opf.iterfind(".//opf:manifest/opf:item", OPF_NS)}
    docs = []
    for ref in opf.iterfind(".//opf:spine/opf:itemref", OPF_NS):
        href = items.get(ref.get("idref"), "")
        name = PurePosixPath(href).name
        if name in ("title.xhtml", "about.xhtml", "nav.xhtml") or not href.endswith("html"):
            continue
        docs.append(z.read(str(base / href)).decode("utf-8"))
    return meta, docs


class Writer:
    def __init__(self):
        self.out = []
        self.notes = {}
        self.note_order = []
        self.pending_key = None

    def blank(self):
        if self.out and self.out[-1] != "":
            self.out.append("")


def clean(root, notes, order):
    """Remove apparatus of the web page; turn footnote references into [^n] tokens."""
    for el in root.xpath("//style|//link|//script|//img|//figure|//meta"):
        el.drop_tree()
    # footnote texts, keyed by their anchor id
    for li in root.xpath("//ol[contains(@class,'references')]/li"):
        text = norm("".join(t for t in li.xpath(".//*[contains(@class,'reference-text')]//text()")))
        if li.get("id"):
            notes[li.get("id")] = text.strip()
    for ol in root.xpath("//ol[contains(@class,'references')]|//div[contains(@class,'reflist')]"):
        ol.drop_tree()
    # endnotes (a numbered NOTES section at the end, as in transcribed books)
    for cite in root.xpath("//cite[contains(@class,'wst-endnote')]"):
        p = cite.getparent()
        if cite.get("id") and p is not None:
            cite_text = "".join(cite.itertext())
            notes[cite.get("id")] = norm("".join(p.itertext())).replace(cite_text, "", 1).strip()
            p.drop_tree()
    for sup in root.xpath("//sup[contains(@class,'reference') or contains(@class,'wst-ref')]"):
        a = sup.find(".//a")
        target = (a.get("href") or "").split("#")[-1] if a is not None else ""
        if target in notes:
            order.append(target)
            tok = f"[^{len(order)}]"
        else:
            tok = ""
        sup.drop_tree() if not tok else replace_with_text(sup, tok)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if any(c in DROP_CLASSES for c in classes(el)):
            el.drop_tree()
    for table in root.xpath("//table"):      # header boxes and license notices
        if len("".join(table.itertext())) < 400:
            table.drop_tree()
    # printed line numbers: small bracketed numbers, usually anchors with an id
    for el in root.xpath("//span|//a"):
        t = "".join(el.itertext()).strip()
        if LINE_NO.match(t) and (el.get("id") or "linenum" in (el.get("class") or "")
                                 or "font-size" in (el.get("style") or "")):
            replace_with_text(el, TOKEN_KEY.format(LINE_NO.match(t).group(1)))


def replace_with_text(el, text):
    parent = el.getparent()
    if parent is None:
        return
    prev = el.getprevious()
    tail = el.tail or ""
    if prev is not None:
        prev.tail = (prev.tail or "") + text + tail
    else:
        parent.text = (parent.text or "") + text + tail
    parent.remove(el)


def inline_text(el):
    """Text of an element with <br> as newlines and <i> as *...*."""
    parts = []

    def flat(t):            # source newlines are layout only; <br> makes the line break
        return t.replace("\n", " ") if t else t

    def walk(e):
        if e.tag == "br":
            parts.append("\n")
        elif e.tag in ("i", "em") and e.text and len(e) == 0:
            parts.append(f"*{e.text}*")
        elif e.tag == "b" and len(e) == 0 and e.text:
            parts.append(f"⁣B{e.text}⁣")      # mark bold for speaker detection
        else:
            if e.text:
                parts.append(flat(e.text))
            for c in e:
                if isinstance(c.tag, str):
                    walk(c)
                if c.tail:
                    parts.append(flat(c.tail))
    if el.text:
        parts.append(flat(el.text))
    for c in el:
        if isinstance(c.tag, str):
            walk(c)
        if c.tail:
            parts.append(flat(c.tail))
    return "".join(parts)


def verse_lines(text, w):
    carry_indent = 0
    for raw in text.split("\n"):
        lead = raw[: len(raw) - len(raw.lstrip(" \xa0\t"))]
        indent = carry_indent + len(lead) + 3 * lead.count("\t")
        carry_indent = 0
        line = norm(raw).strip()
        if line.startswith(HEAD):
            label = line[len(HEAD):].strip()
            if label:
                w.blank()
                w.out.append("### " + label.replace("\u2063B", "").replace("\u2063", ""))
            continue
        if not line:
            if "\xa0" in raw:          # an indent cut off by a stray line break
                carry_indent = indent
            elif w.out and w.out[-1] != "":
                w.out.append("")
            continue
        m = re.match(r"^⁣B([^⁣]+)⁣\s*(.*)$", line)
        if m:
            w.out.append(f"**{m.group(1).strip()}**")
            line = m.group(2).strip()
            indent = 0
            if not line:
                continue
        line = line.replace("⁣B", "").replace("⁣", "")
        key = None
        km = re.search(r"\s*⟦([^⟧]+)⟧\s*", line)
        if km:
            key = km.group(1)
            line = (line[:km.start()] + " " + line[km.end():]).strip()
        if not line:
            continue
        if key:
            w.out.append(f"{{{{{key}}}}} {line}")
        elif indent >= 6 and any(l and not l.startswith(("**", "##", "*(")) for l in w.out):
            w.out.append(f"{{{{+}}}} {line}")
        else:
            w.out.append(line)


def to_markdown(docs, w):
    verse_n = prose_n = 0
    for doc in docs:
        root = lhtml.fromstring(doc.encode("utf-8"))
        clean(root, w.notes, w.note_order)
        body = root.find(".//body")
        blocks = body.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//p|.//div[contains(@class,'poem')]"
                            "|.//div[contains(@class,'ws-poem')]|.//blockquote|.//dl|.//li")
        seen = set()
        for b in blocks:
            if any(a in seen for a in b.iterancestors()):
                continue
            seen.add(b)
            tag = b.tag
            if tag in ("h1", "h2", "h3", "h4", "h5"):
                t = norm("".join(b.itertext())).strip()
                if not t or t.lower() in ("contents", "notes", "footnotes", "references"):
                    continue
                fm = FRAGMENT.match(t)
                w.blank()
                if fm:              # the number opens the next paragraph
                    w.pending_key = fm.group(1) or fm.group(2)
                else:
                    w.out.append(("## " if tag in ("h1", "h2") else "### ") + t)
                w.blank()
                continue
            poem = "poem" in " ".join(classes(b)) or b.xpath(".//*[contains(@class,'ws-poem-line')]")
            text = inline_text(b)
            if poem or text.count("\n") >= 3:
                if b.xpath(".//*[contains(@class,'ws-poem-line')]"):
                    # one element per line; stanza elements (when present) mark the breaks
                    stanzas = b.xpath(".//*[contains(@class,'ws-poem-stanza')]") or [b]
                    text = "\n\n".join(
                        "\n".join((HEAD if "ws-poem-center" in classes(l) else "")
                                  + inline_text(l).replace("\n", " ")
                                  for l in st.xpath(".//*[contains(@class,'ws-poem-line')]"))
                        for st in stanzas)
                w.blank()
                start = len(w.out)
                verse_lines(text, w)
                w.out[start:] = [VERSE + l if l and not l.startswith("**") else l for l in w.out[start:]]
                verse_n += text.count("\n") + 1
                w.blank()
            else:
                t = norm(text.replace("\n", " ")).replace("⁣B", "").replace("⁣", "").strip()
                if not t:
                    continue
                t = re.sub(r"⟦([^⟧]+)⟧", r" {{\1}} ", t).strip()
                if JUNK.match(t) or is_number_run(t):
                    continue
                w.blank()
                if w.pending_key:
                    t = f"{{{{{w.pending_key}}}}} {t}"
                    w.pending_key = None
                w.out.append(PROSE + ("> " if tag == "blockquote" else "") + t)
                w.blank()
                prose_n += 1
    return "verse" if verse_n > prose_n * 3 else "prose"


VERSE, PROSE = "\u2029V", "\u2029P"
JUNK = re.compile(r"^(layout \d+|contents|\[?edit\]?)$", re.I)


def is_number_run(t):
    """A table of contents made only of fragment or chapter numbers."""
    toks = t.split()
    return len(toks) >= 10 and all(re.fullmatch(r"[0-9]+[a-z]?(?:-[0-9]+)?|[IVXLC]+\.?", x) for x in toks)


def finish(lines, layout):
    """Verse inside a prose text becomes quoted verse (> line); prose inside a verse text
    becomes a ¶ paragraph, which is not given a line number."""
    out = []
    for l in lines:
        if l.startswith(VERSE):
            l = l[len(VERSE):]
            out.append(l if layout == "verse" else "> " + re.sub(r"^\{\{[^}]*\}\}\s*", "", l))
        elif l.startswith(PROSE):
            l = l[len(PROSE):]
            out.append("¶ " + l if layout == "verse" else l)
        else:
            out.append(l)
    return out


def import_epub(path, work, lang="eng", author="", title="", dest=Path("library/own")):
    meta, docs = read_epub(path)
    w = Writer()
    layout = to_markdown(docs, w)
    w.out = finish(w.out, layout)
    while w.out and w.out[-1] == "":
        w.out.pop()
    lines = w.out
    if w.note_order:
        lines += [""] + [f"[^{i}]: {w.notes[t]}" for i, t in enumerate(w.note_order, 1)]
    lang = lang or LANG.get(meta["language"], meta["language"])
    front = {
        "id": f"{work}.{lang}-wikisource",
        "work": work,
        "author": author or meta["author"],
        "title": title or meta["title"],
        "label": meta["title"],
        "edition": "Wikisource",
        "language": lang,
        "layout": layout,
        "numbering": "auto" if layout == "verse" else "explicit",
        "source": meta["source"],
    }
    text = "---\n" + "\n".join(f"{k}: {v}" for k, v in front.items() if v) + "\n---\n\n" + \
        "\n".join(lines) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{work}.{lang}-wikisource.md"
    out.write_text(text, encoding="utf-8")
    if layout == "verse":
        for printed, counted in numbering_report(lines):
            print(f"  check: line printed as {printed}, but it is line {counted} by count")
    return out


def numbering_report(lines):
    """Places where a printed line number disagrees with the running count."""
    n, bad = 0, []
    for line in lines:
        s = line.strip()
        if not s or s.startswith(("**", "##", "*(", "[^")):
            continue
        m = re.match(r"\{\{([^}]+)\}\}", s)
        if m and m.group(1) == "+":
            continue
        n += 1
        if m and m.group(1).isdigit():
            if int(m.group(1)) != n:
                bad.append((m.group(1), n))
            n = int(m.group(1))
    return bad
