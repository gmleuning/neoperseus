"""Read a book (PDF or EPUB) into pages of lines, and find the parts of it that are verse.

A line is a dict:
  t     the text (library inline markup: *italics*)
  it    True if the line is (mostly) italic: a stage direction
  lead  a speaker name printed in bold or capitals at the start, or None
  num   a line number printed in the margin, or None
  head  True for a heading (bold and large in a PDF, a Markdown heading in an EPUB)
  brk   True for an empty line that marks a stanza break

reader/importer.py (convert_lines) turns the lines of a part into the library format.
"""
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

PAGE_JUNK = re.compile(r"^(page \d+ of \d+|pg \d+|\.{8,}|\d+ of \d+)$", re.I)
EN_WORDS = set("the and of to you your is that with his her he she my me for not but this what in it".split())
LA_WORDS = set("et est in non ad quod ac nec ut qui quae quid cum sed iam me te mihi tibi hic per ubi aut uel vel atque".split())
CAPS_LEAD = re.compile(r"^((?:[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’.\-]+\s?)+)(?=\s|$)")


def clean(s):
    """PDF text: U+FFFD stands for dashes and tab-like indents in some Oxford PDFs."""
    s = unicodedata.normalize("NFC", s).replace("\xa0", " ")
    s = s.strip(" �\t")
    s = re.sub(r"\s*�+\s*", "—", s)
    return re.sub(r"\s+", " ", s).strip()


# ---- PDF ----------------------------------------------------------------------------------
def pdf_pages(path):
    import fitz                                   # PyMuPDF
    doc = fitz.open(str(path))
    pages = []
    for pno in range(doc.page_count):
        rows = []
        for b in doc[pno].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                spans = [s for s in l["spans"] if s["text"]]
                if not spans:
                    continue
                raw = "".join(s["text"] for s in spans)
                rows.append((l["bbox"][0], spans, raw))
        pages.append(pdf_lines(rows))
    return pages


def pdf_lines(rows):
    out = []
    xs = sorted(round(x) for x, _, raw in rows if clean(raw))
    body_x = xs[len(xs) // 2] if xs else 0
    for x, spans, raw in rows:
        if not raw.replace("�", "").strip():
            if "�" in raw:
                out.append({"t": "", "brk": True})
            continue
        t = clean(raw)
        if not t or PAGE_JUNK.match(t):
            continue
        if re.fullmatch(r"PG \d+|pg \d+", t):
            continue
        if re.fullmatch(r"\d{1,4}", t) and x < body_x - 25:       # a number in the margin
            out.append({"t": "", "margin": int(t)})
            continue
        bold = [bool(s["flags"] & 16) for s in spans]
        size = max(s["size"] for s in spans)
        # names in small capitals inside a stage direction are set in roman: leave them out
        words = [s for s in spans if re.search(r"[a-z]", s["text"])]
        italic_chars = sum(len(s["text"].strip()) for s in words if s["flags"] & 2)
        letters = sum(len(s["text"].strip()) for s in words)
        line = {"t": t, "it": letters > 0 and italic_chars / letters >= 0.5,
                "head": all(bold) and size >= 13}
        # a speaker: leading bold spans in capitals
        lead = ""
        for s, b in zip(spans, bold):
            if not b:
                break
            lead += s["text"]
        lead = clean(lead)
        if lead and lead.upper() == lead and re.search(r"[A-Z]{2}", lead) and not line["head"]:
            line["lead"] = lead
            line["t"] = clean(t[len(lead):]) if t.startswith(lead) else t
        out.append(line)
    return out


# ---- EPUB (via pandoc) ---------------------------------------------------------------------
PAGEBREAK = re.compile(r"\[\]\{#[^}]*\.pagebreak[^}]*\}")


def pandoc():
    exe = shutil.which("pandoc")
    if not exe:
        raise RuntimeError("pandoc is needed to read EPUB files (https://pandoc.org)")
    return exe


def epub_markdown(path):
    p = subprocess.run([pandoc(), str(path), "-t", "markdown-smart", "--wrap=none"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300] or "pandoc failed")
    return p.stdout


def md_inline(s):
    s = re.sub(r"\[\]\{[^}]*\}", "", s)                      # empty anchors
    s = re.sub(r"\{[#.][^}]*\}", "", s)                      # attributes
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)               # images
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)           # links
    s = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", s)           # spans
    s = re.sub(r"\^\[[^\]]*\]", "", s)                       # inline notes
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|'\"<>$^~])", r"\1", s)
    s = s.replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()


def epub_pages(path):
    text = epub_markdown(path)
    # page breaks of the printed book, when the EPUB keeps them; otherwise each chapter
    chunks = PAGEBREAK.split(text) if PAGEBREAK.search(text) else re.split(r"\n(?=# )", text)
    pages = []
    for chunk in chunks:
        lines = []
        for para in re.split(r"\n\s*\n", chunk):
            para = para.strip()
            if not para or para.startswith(("<", ":::", "```")):
                continue
            head = para.startswith("#")
            for raw in re.split(r"\\\n|\n", para):              # a line break inside a paragraph
                raw = raw.strip()
                if re.fullmatch(r"[+|:=\- ]+", raw):
                    continue                                     # a grid table's rules
                if raw.startswith("|") and raw.endswith("|"):
                    # a grid table row: verse set in a table, the line number in the last cell
                    cells = [c.strip() for c in raw.strip("|").split("|")]
                    if len(cells) > 1 and not re.fullmatch(r"\d{1,4}", cells[-1].replace(" ", "")):
                        cells[-1] = ""                           # no number, or an OCR'd one
                    elif len(cells) > 1:
                        cells[-1] = cells[-1].replace(" ", "")
                    raw = " ".join(c for c in cells if c)
                raw = re.sub(r"^\[Table caption\]", "", raw).strip()
                if not raw:
                    continue
                if head:
                    raw = raw.lstrip("#").strip()
                it = bool(re.fullmatch(r"\*[^*].*[^*]\*|\*[^*]\*", raw))
                t = md_inline(raw.strip("*") if it else raw)
                if not t:
                    continue
                line = {"t": t, "it": it, "head": head}
                m = re.match(r"^\*\*([^*]+)\*\*\s*(.*)$", raw)
                if m and m.group(1).upper() == m.group(1):
                    line["lead"], line["t"] = md_inline(m.group(1)), md_inline(m.group(2))
                lines.append(line)
        pages.append(lines)
    return pages


# ---- any source ----------------------------------------------------------------------------
def read_pages(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return pdf_pages(path)
    if ext == ".epub":
        return epub_pages(path)
    raise ValueError(f"cannot read {ext} files")


def language_of(text):
    words = re.findall(r"[a-zα-ω]+", text.lower())
    greek = sum(1 for w in words if re.match(r"[α-ω]", w))
    if greek > len(words) / 3:
        return "grc"
    en = sum(w in EN_WORDS for w in words)
    la = sum(w in LA_WORDS for w in words)
    return "eng" if en >= la else "lat"


NUMBERED = re.compile(r"^\d{1,4}(?=\D)|\s\d{1,4}$")


def page_kind(lines):
    """('verse' | 'prose' | 'other', language) for one page."""
    text = [l for l in lines if l.get("t")]
    if len(text) < 4:
        return "other", None
    numbered = sum(1 for l in lines if l.get("margin") or NUMBERED.search(l.get("t", "")))
    lengths = sorted(len(l["t"]) for l in text)
    median = lengths[len(lengths) // 2]
    lang = language_of(" ".join(l["t"] for l in text))
    if numbered >= 3 and median < 75:
        return "verse", lang
    return "prose", lang


def numbers_in(lines):
    out = []
    for l in lines:
        if l.get("margin"):
            out.append(l["margin"])
            continue
        m = re.match(r"^(\d{1,4})(?=\D|$)", l.get("t", "")) or re.search(r"\s(\d{1,4})$", l.get("t", ""))
        if m:
            out.append(int(m.group(1)))
    return out


def sequential(nums):
    """Share of steps from one line number to the next that go forward a little: high for a
    numbered text, low for an index or a commentary."""
    if len(nums) < 2:
        return 0
    good = sum(1 for a, b in zip(nums, nums[1:]) if 0 < b - a <= 12)
    return good / (len(nums) - 1)


def lineation(nums):
    """The line numbers that follow on from each other (stray numbers dropped)."""
    run = []
    for n in nums:
        if not run or 0 < n - run[-1] <= 30:
            run.append(n)
        elif len(run) < 3:
            run = [n]
    return run


def parts(pages):
    """Runs of verse pages in one language: [{first, last, language, verse, start}], pages 1-based,
    best first. Prose pages in the same language between verse pages (apparatus-heavy pages,
    a long stage direction) stay in the run."""
    kinds = [page_kind(l) for l in pages]
    runs, cur = [], None
    for i, (kind, lang) in enumerate(kinds, 1):
        if kind != "verse":
            continue
        if cur and cur["language"] == lang and i - cur["last"] <= 4 and all(
                kinds[j - 1][1] in (lang, None) for j in range(cur["last"] + 1, i)):
            cur["last"] = i
        else:
            cur = {"first": i, "last": i, "language": lang}
            runs.append(cur)
    out = []
    for r in runs:
        if r["last"] - r["first"] < 2:
            continue                       # a quotation in an introduction, say
        # the page after: the end of the text, in the same language
        if r["last"] < len(pages) and kinds[r["last"]][1] == r["language"] and kinds[r["last"]][0] == "prose":
            r["last"] += 1
        # the pages before: the cast list and the first heading
        for _ in range(2):
            j = r["first"] - 1
            if j >= 1 and kinds[j - 1][0] != "verse" and any(l.get("head") for l in pages[j - 1]):
                r["first"] = j
        nums = [n for i in range(r["first"], r["last"] + 1) for n in numbers_in(pages[i - 1])]
        run = lineation(nums)
        cover = len(run) / len(nums) if nums else 0
        if cover < 0.5:
            continue                       # an index or a commentary: numbers but no lineation
        r["start"], r["verse"] = (run[0], run[-1]) if run else (0, 0)
        r["score"] = cover * len(run)
        out.append(r)
    out.sort(key=lambda r: -r["score"])
    return out


def page_range(spec, n):
    """'165-200' or '165-200, 210' -> sorted 1-based page numbers."""
    out = set()
    for part in re.split(r"[,\s]+", spec or ""):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        a, b = (int(m.group(1)), int(m.group(2))) if m else (int(part), int(part))
        out.update(range(max(1, a), min(n, b) + 1))
    return sorted(out)
