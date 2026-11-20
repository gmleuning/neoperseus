"""Convert one Perseus canonical TEI (EpiDoc) file to the library Markdown format (SPEC.md).

Every citable number in the source becomes an explicit key, written in full
(`{{1.150}}` for Iliad 1.150, `{{17a}}` for a Stephanus section, `{{1.5}}` for
Catiline 1.5). Originals and translations in the canonical repos use the same
citation scheme, so the builder can sync the two columns on shared keys.
"""
import re
import unicodedata

from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Division types that start a large section (## in the library file).
SECTION_TYPES = {
    "book", "speech", "oration", "episode", "choral", "act", "scene", "poem", "hymn",
    "letter", "life", "dialogue", "part", "prologue", "parodos", "exodos", "satire",
    "ode", "elegy", "epigram", "fable", "idyll", "treatise", "volume", "chapter-group",
}
# Smaller divisions shown as a label (###).
SUBSECTION_TYPES = {
    "strophe", "antistrophe", "epode", "mesode", "lyric", "anapests", "proode",
    "commentary", "argument", "preface", "epilogue",
}
# Divisions that only carry a number.
NUMBER_ONLY = {"section", "chapter", "card", "page", "paragraph", "verse", "line", "entry"}
LABELS = {"choral": "Choral ode", "anapests": "Anapests", "lyric": "Lyric"}
KEY_MILESTONES = {"line", "section", "verse"}
SKIP = {"pb", "figure", "graphic", "fw", "index", "interp", "link", "anchor", "ref_skip"}


def norm(s):
    s = unicodedata.normalize("NFC", s)
    s = s.replace("ʼ", "’")      # Perseus elision mark -> apostrophe
    return re.sub(r"\s+", " ", s)


def esc(s):
    """Protect text that would otherwise read as library markup at line start."""
    return re.sub(r"^(#|>|\*\*|\*\(|\[\^)", r"\\\1", s)


def latin_u(word):
    """Lower-case an inscriptional Latin capital word, turning V into u where it is a vowel."""
    out, w = [], word
    for i, ch in enumerate(w):
        if ch == "V":
            prev = w[i - 1] if i else ""
            nxt = w[i + 1] if i + 1 < len(w) else ""
            vowel = prev == "Q" or not nxt or not nxt.isalpha() or nxt not in "AEIOUY"
            out.append("u" if vowel else "v")
        else:
            out.append(ch.lower())
    return "".join(out)


SMALL_WORDS = {"a", "an", "and", "the", "of", "in", "on", "to", "at", "by", "for", "with", "from",
               "or", "et", "ad", "de", "cum", "ex", "ab", "e", "ac", "atque", "qua", "qui", "quae"}


def tidy_heading(text, lang):
    """All-capital headings become title case; short function words stay lower-case."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) < 0.8 * len(letters):
        return text
    words, start = [], True
    for w in text.split():
        if re.fullmatch(r"[A-Z]\.", w):
            words.append(w)
        else:
            low = latin_u(w) if lang == "lat" else w.lower()
            core = low.strip(".,;:")
            if core in SMALL_WORDS and not start:
                words.append(low)
            else:
                words.append(low[:1].upper() + low[1:])
        start = w.endswith(".") and not re.fullmatch(r"[A-Z]\.", w)
    return " ".join(words)


def local(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def person_from_description(desc, kind):
    """'Euripides. ... Coleridge, Edward P., translator. London ...' -> 'Edward P. Coleridge'.
    Accepts dates after the name (Burnet, John, 1863-1928, editor) and qualified roles
    (prose translator). Prefers the role that fits the file; falls back to the other."""
    pat = re.compile(r"([A-Z][\w'’\-]+(?: [A-Z][\w'’\-]+)*), ([A-Z][^,;]*?)(?:, [\d?][\d\-–?]*)?,"
                     r" (?:[a-z]+ )?(editor|translator)s?\b")
    desc = re.sub(r", ([A-Z])\b,", r" \1.,", desc)   # 'Williams, Theodore, C, translator'
    desc = re.sub(r"([A-Z][\w'’\-]+), ([^,;]+), (Sir|Lord|Rev\.|Mrs\.|Dr\.), ", r"\1, \3 \2, ", desc)  # 'Jebb, Richard, Sir,'
    found = pat.findall(desc)
    want = "translator" if kind == "translation" else "editor"
    names = [(last, first) for last, first, role in found if role == want] or \
            [(last, first) for last, first, role in found]
    clean = lambda s: re.sub(r"\s*\([^)]*\)", "", s).strip()
    return " and ".join(f"{clean(first)} {last}" for last, first in names)


class Converter:
    def __init__(self, root, lang):
        self.lang = lang
        self.is_trans = lang not in ("grc", "lat")
        self.out = []            # finished library lines
        self.para = []           # open prose paragraph (list of strings)
        self.notes = []          # (id, text)
        self.note_n = 0
        self.stanza_break = False
        self.counters = {}
        self.last_key = None
        self.pending_key = None
        self.body = root.find(f".//{TEI}text/{TEI}body")
        self.layout = self.detect_layout(self.body)

    # ---- layout --------------------------------------------------------------
    @staticmethod
    def detect_layout(body):
        lines = [l for l in body.iter(TEI + "l") if l.get("n") != "0"]
        if not lines:
            return "prose"
        in_p = sum(1 for l in lines if any(local(a) in ("p", "quote", "q") for a in l.iterancestors()))
        if in_p > len(lines) / 2:
            return "prose"
        avg = sum(len("".join(l.itertext()).strip()) for l in lines) / len(lines)
        return "verse" if avg < 90 else "prose"

    # ---- output helpers ------------------------------------------------------
    def has_text(self):
        return bool(re.sub(r"\{\{[^}]*\}\}", "", norm("".join(self.para))).strip())

    def flush(self):
        text = norm("".join(self.para)).strip()
        if text:
            if self.out and self.out[-1] != "":
                self.out.append("")
            self.out.append(esc(text))
            self.out.append("")
        self.para = []

    def break_paragraph(self):
        """End the open paragraph; keys written just before the break move to the next one."""
        if not self.has_text():
            return
        joined = "".join(self.para)
        m = re.search(r"(\s*\{\{[^}]*\}\}\s*)+$", joined)
        carry = m.group(0) if m else ""
        self.para = [joined[: len(joined) - len(carry)]]
        self.flush()
        if carry:
            self.para = [carry]

    def block(self, line):
        carry = []
        if not self.has_text():          # keys waiting for text go after the heading
            carry, self.para = self.para, []
        self.flush()
        if self.layout == "prose" and self.out and self.out[-1] != "":
            self.out.append("")
        self.out.append(line)
        self.para = carry

    def add_key(self, key):
        """Append a key marker to the open paragraph. An immediate repeat is skipped, and a
        coarser key directly followed by a finer one (page 17, then 17a) gives way to it."""
        if key == self.last_key:
            return
        joined = "".join(self.para)
        m = re.search(r"\{\{([^}]*)\}\}\s*$", joined)
        if m and key.startswith(m.group(1)):
            self.para = [joined[:m.start()]]
        self.last_key = key
        self.para.append(f" {{{{{key}}}}} ")

    def blank(self):
        if self.layout == "verse":
            self.stanza_break = True
        else:
            self.flush()

    def verse_line(self, key, text):
        if self.stanza_break and self.out and self.out[-1] != "" and not self.out[-1].startswith(("##", "**", "*(")):
            self.out.append("")
        self.stanza_break = False
        text = norm(text).strip()
        self.out.append((f"{{{{{key}}}}} " if key else "") + esc(text))

    def add_note(self, el):
        text = norm("".join(el.itertext())).strip()
        if not text or re.fullmatch(r"[\d\s.*†]+", text):
            return ""
        self.note_n += 1
        nid = (f"a{self.note_n}" if not self.is_trans else str(self.note_n))
        self.notes.append((nid, text))
        return f"[^{nid}]"

    # ---- keys ----------------------------------------------------------------
    def prefix(self, el):
        parts = []
        for a in el.iterancestors(TEI + "div"):
            if a.get("type") == "textpart" and a.get("n") and a.get("subtype", "").lower() != "card":
                parts.append(a.get("n"))
        return list(reversed(parts))

    def key_for(self, el, n):
        pre = self.prefix(el)
        parent_n = pre[-1] if pre else None
        # Stephanus-style labels (17a inside page 17) are already complete
        if parent_n and n != parent_n and n.startswith(parent_n) and re.match(r"^\d+[a-z]$", n):
            return n
        return ".".join(pre + [n])

    # ---- walk ----------------------------------------------------------------
    def run(self):
        for child in self.body:
            self.walk(child)
        self.flush()
        while self.out and self.out[-1] == "":
            self.out.pop()
        if self.notes:
            self.out.append("")
            for nid, text in self.notes:
                self.out.append(f"[^{nid}]: {text}")
        return self.layout, "\n".join(self.out) + "\n"

    def heading_label(self, div, sub):
        n = div.get("n")
        head = div.find(TEI + "head")
        head_text = norm("".join(head.itertext())).strip() if head is not None else ""
        name = LABELS.get(sub, sub.capitalize())
        if n and not n.startswith("urn:"):
            label = f"{name} {n}"
        else:
            self.counters[sub] = self.counters.get(sub, 0) + 1
            label = f"{name} {self.counters[sub]}"
        if head_text and re.fullmatch(r"(book|scroll|liber|βιβλίον)\s+\S+", head_text, re.I):
            head_text = ""
        return label, head_text

    def walk(self, el):
        tag = local(el)
        if not tag or tag in SKIP:
            return
        handler = getattr(self, "on_" + tag, None)
        if handler:
            handler(el)
        else:
            self.walk_children(el)

    def walk_children(self, el):
        if el.text and el.text.strip():
            self.para.append(el.text)
        for c in el:
            self.walk(c)
            if c.tail and c.tail.strip():
                self.para.append(c.tail)
            elif c.tail and self.para:
                self.para.append(" ")

    # structure
    def on_div(self, el):
        typ, sub = el.get("type"), (el.get("subtype") or "").lower()
        if typ == "textpart":
            if sub in SECTION_TYPES:
                label, head = self.heading_label(el, sub)
                self.block(f"## {label}")
                if head:
                    self.block(f"### {tidy_heading(head, self.lang)}")
            elif sub in SUBSECTION_TYPES:
                head = el.find(TEI + "head")
                head = norm("".join(head.itertext())).strip() if head is not None else ""
                default = "Introduction" if sub == "commentary" else LABELS.get(sub, sub.capitalize())
                self.block(f"### {tidy_heading(head, self.lang) if head else default}")
            n = el.get("n")
            if n and not n.startswith("urn:") and (sub in NUMBER_ONLY or not sub):
                key = self.key_for(el, n)
                if self.layout == "prose":
                    self.add_key(key)
                else:
                    self.pending_key = key
        for c in el:
            if local(c) == "head":
                continue
            self.walk(c)
            if c.tail and c.tail.strip():
                self.para.append(c.tail)
        if typ == "textpart" and sub in SUBSECTION_TYPES | SECTION_TYPES:
            self.blank()

    def on_head(self, el):
        pass

    def on_p(self, el):
        if self.layout == "verse":
            # prose inside a verse text (rare): a separate block
            self.flush()
            self.walk_children(el)
            text = norm("".join(self.para)).strip()
            self.para = []
            if text:
                self.out.append("¶ " + text)
            return
        self.break_paragraph()
        self.walk_children(el)
        self.flush()

    def on_milestone(self, el):
        unit, n = (el.get("unit") or "").lower(), el.get("n")
        if unit == "para":
            if self.layout == "prose":
                self.break_paragraph()
            else:
                self.stanza_break = True
        elif unit == "speech" and n:
            self.block(f"## Speech {n}")
        elif unit in KEY_MILESTONES and n:
            key = self.key_for(el, n)
            if self.layout == "prose":
                self.add_key(key)
            else:
                self.pending_key = key

    def on_l(self, el):
        n = el.get("n")
        if n == "0" and not "".join(el.itertext()).strip():
            return
        key = self.key_for(el, n) if n else None
        if self.layout == "prose":
            if key:
                self.add_key(key)
            self.walk_children(el)
            self.para.append(" ")
            return
        saved, self.para = self.para, []
        self.walk_children(el)
        text = "".join(self.para)
        self.para = saved
        if not key and self.pending_key:
            key = self.pending_key
        self.pending_key = None
        self.verse_line(key, text)

    def on_lg(self, el):
        self.blank()
        for c in el:
            self.walk(c)
        self.blank()

    def on_sp(self, el):
        self.flush()
        for c in el:
            self.walk(c)
            if c.tail and c.tail.strip():
                self.para.append(c.tail)
        self.flush()

    def on_speaker(self, el):
        name = norm("".join(el.itertext())).strip().rstrip(".:")
        if name:
            self.block(f"**{name}**")

    def on_stage(self, el):
        text = norm("".join(el.itertext())).strip().strip("()[]").strip()
        if text:
            self.block(f"*({text})*")

    def on_note(self, el):
        if el.get("place") == "inline" or el.get("type") == "dramatis":
            parts = [norm("".join(p.itertext())).strip() for p in el.iter(TEI + "p")]
            parts = [p for p in parts if p]
            if parts:
                self.block("*(" + " · ".join(parts) + ")*")
                self.blank()
            return
        ref = self.add_note(el)
        if ref:
            self.para.append(ref)

    def on_gap(self, el):
        if self.layout == "verse" and not self.para:
            self.out.append("{{gap}}")
        else:
            self.para.append(" … ")

    # inline
    def wrap(self, el, left, right):
        self.para.append(left)
        self.walk_children(el)
        joined = "".join(self.para)
        stripped = joined.rstrip()
        self.para = [stripped, right, joined[len(stripped):]]

    def on_del(self, el):
        self.wrap(el, "[", "]")

    def on_add(self, el):
        self.wrap(el, "⟨", "⟩")

    def on_supplied(self, el):
        self.wrap(el, "⟨", "⟩")

    def on_surplus(self, el):
        self.wrap(el, "{", "}")

    def on_q(self, el):
        if el.find(f".//{TEI}l") is not None or el.find(f".//{TEI}p") is not None:
            return self.on_quote_block(el)
        if self.is_trans and not "".join(el.itertext()).lstrip().startswith(("“", '"', "‘")):
            self.wrap(el, "“", "”")
        else:
            self.walk_children(el)

    on_quote = on_q
    on_said = on_q

    def on_quote_block(self, el):
        lines = list(el.iter(TEI + "l"))
        if lines and self.layout == "prose":
            for l in lines:
                saved, self.para = self.para, []
                self.walk_children(l)
                text = norm("".join(self.para)).strip()
                self.para = saved
                self.para.append(f"\n> {text}\n")
            return
        for c in el:
            self.walk(c)

    def on_bibl(self, el):
        text = norm("".join(el.itertext())).strip()
        if text:
            self.para.append(f" ({text})")

    def on_choice(self, el):
        for pref in ("corr", "reg", "abbr", "orig", "sic", "expan"):
            c = el.find(TEI + pref)
            if c is not None:
                self.walk_children(c)
                return
        self.walk_children(el)

    def on_app(self, el):
        lem = el.find(TEI + "lem")
        if lem is not None:
            self.walk_children(lem)

    def on_hi(self, el):
        if self.is_trans and "italic" in (el.get("rend") or ""):
            self.wrap(el, "*", "*")
        else:
            self.walk_children(el)

    def on_title(self, el):
        if self.is_trans:
            self.wrap(el, "*", "*")
        else:
            self.walk_children(el)

    def on_reg(self, el):
        # Latin editions mark sentence-initial words with <reg>: capitalise them
        start = len(self.para)
        self.walk_children(el)
        if self.lang == "lat" and len(self.para) > start:
            first = self.para[start]
            i = len(first) - len(first.lstrip())
            self.para[start] = first[:i] + first[i:i + 1].upper() + first[i + 1:]

    def on_lb(self, el):
        self.para.append(" ")


def convert(path, lang):
    root = etree.parse(str(path)).getroot()
    conv = Converter(root, lang)
    return conv.run()
