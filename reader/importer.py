"""Import a play converted from an EPUB (pandoc Markdown) into the library format (SPEC.md).

Handles the layout of the Chicago "Complete Greek Tragedies" conversions and similar books:
a title block and an introduction, a cast list, speakers in capitals, stage directions in
parentheses, strophe headings, verse either as pandoc tables (a line number every five lines
in the first column) or as a number/blank marker line before each verse line, and textual
notes at the end keyed by line number, referenced in the text by °.

The translation's own line numbers are kept as keys (numbering: auto counts the lines in
between), so it lines up with the Greek or Latin original line by line.
"""
import re
import unicodedata
from pathlib import Path

# a pandoc table rule is indented or has several columns; a bare "---" is a section break
TABLE_RULE = re.compile(r"^(\s+-{3,}(\s+-{3,})*|-{3,}(\s+-{3,})+)\s*$")
TABLE_NUM = re.compile(r"^\s{0,4}(\d+)\s{2,}(\S.*)$")
NUMBER_LINE = re.compile(r"^\s*(\d+)\s*$")
NOTE_LINE = re.compile(r"^(\d+)(?:\s*[–-]\s*(\d+))?\s*:\s*(.+)$", re.S)
SECTION = re.compile(r"^(STROPHE|ANTISTROPHE|EPODE|MESODE|PROLOGUE|PARODOS|EXODOS|EXODUS|EPISODE|"
                     r"STASIMON|KOMMOS|PROLOGOS|CHORAL ODE)\b.*$")
SPEAKER = re.compile(r"^([A-Z][A-Z’'\-. ,]*[A-Z.])(\s*\[([^\]]+)\])?$")
FILENAME = re.compile(r"^(?P<author>[^.]+)\.\s*(?P<title>.+?)\s*(\((?:Tr\.|trans\.?|translated by)\s*(?P<tr>[^)]+)\))?$", re.I)


# English titles that differ from the catalog's
TITLE_ALIASES = {"oedipus the king": "oedipus tyrannus", "oedipus rex": "oedipus tyrannus",
                 "the libation bearers": "libation bearers", "the suppliants": "supplices",
                 "suppliant women": "supplices", "the persians": "persians",
                 "seven against thebes": "seven against thebes", "the eumenides": "eumenides",
                 "women of trachis": "trachiniae", "the trojan women": "troades", "trojan women": "troades",
                 "the bacchae": "bacchae", "the children of heracles": "heracleidae", "heracles": "hercules furens"}


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def slug(s):
    return fold(s).replace(" ", "-") or "x"


def unescape(s):
    return re.sub(r"\\([\[\]()'\"!.#-])", r"\1", s)


def guess(path, catalog=None, shelf=()):
    """Front matter guessed from a file name like 'Aeschylus. Agamemnon (Tr. Richmond Lattimore).md'."""
    stem = Path(path).stem
    m = FILENAME.match(stem)
    author, title, tr = (m.group("author").strip(), m.group("title").strip(), (m.group("tr") or "").strip()) \
        if m else ("", stem, "")
    cands = candidates(author, catalog, shelf)
    want = TITLE_ALIASES.get(fold(title), fold(title))
    work = next((c["id"] for c in cands if fold(c["title"]) == want), "")
    if not work:
        work = next((c["id"] for c in cands if want in fold(c["title"]) or fold(c["title"]) in want), "")
    tid = f"{work or slug(author + ' ' + title)}.{slug(tr.split()[-1]) if tr else 'eng'}"
    return {"author": author, "title": title, "edition": tr, "work": work, "id": tid,
            "language": "eng", "candidates": cands}


def candidates(author, catalog, shelf=()):
    """Works by this author in the catalog, those on the shelf first."""
    if not catalog or not author:
        return []
    names = catalog.get("authors", {})
    out = []
    for w in catalog.get("works", []):
        if fold(author) and fold(author) in fold(names.get(w["author"], w["author"])):
            out.append({"id": w["id"], "title": w["title"], "shelf": w["id"] in shelf})
    out.sort(key=lambda c: (not c["shelf"], c["title"]))
    return out


def convert(text, meta):
    """Raw EPUB Markdown -> (library Markdown, report dict)."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    lines = text.split("\n")
    out, notes, refs = [], [], []          # refs: (placeholder, line number) for each °
    phase = "front"                        # front -> intro -> cast -> play -> notes
    in_table, marker, line_no, verse_n, para = False, None, 0, 0, []
    title_caps = fold(meta.get("title", "")).upper()

    def emit_verse(num, s):
        nonlocal line_no, verse_n
        s = unescape(s.strip())
        if num is not None:
            line_no = num
        else:
            line_no += 1
        verse_n += 1
        while "°" in s:
            k = f"n{len(refs) + 1}"
            refs.append((k, line_no))
            s = re.sub(r"\s*°", f"[^{k}]", s, count=1)
        if re.match(r"^(\*\*|\*\(|##|> |¶ |\\)", s):
            s = "\\" + s
        out.append(f"{{{{{num}}}}} {s}" if num is not None else s)

    def stage(s):
        s = s.strip().strip("()[]").strip()
        out.extend(["", f"*({s})*", ""])

    def prose(s):
        out.extend(["", "¶ " + unescape(s), ""])

    def to_play():
        """Leaving the introduction or cast list: close its ::: block."""
        nonlocal phase
        if phase in ("intro", "cast"):
            out.extend(["", ":::", ""])
        phase = "play"

    def flush():
        nonlocal para, phase
        if not para:
            return
        p = " ".join(x.strip() for x in para).strip()
        para = []
        if p == "---":
            return
        if p.startswith("## "):
            if "textual notes" in p.lower() or p[3:].strip().lower() == "notes":
                phase = "notes"
            return
        if phase == "notes":
            m = NOTE_LINE.match(p)
            if m:
                a = int(m.group(1))
                notes.append((a, int(m.group(2) or a), f"{m.group(0).split(':', 1)[0]}: {unescape(m.group(3)).strip()}"))
            return
        if phase == "front":
            if p.upper().startswith("INTRODUCTION"):
                phase = "intro"
                out.extend(["::: Introduction", ""])
            elif p.lower().startswith("translated by") and not meta.get("edition"):
                meta["edition"] = p[len("translated by"):].strip()
            return
        if phase == "intro":
            if p.lower() == "characters" or fold(p).upper() == title_caps:
                if p.lower() == "characters":
                    phase = "cast"
                    out.extend(["", ":::", "", "::: Characters", ""])
                return
            prose(p)
            return
        if phase == "cast":
            if p.lower() == "characters" or fold(p).upper() == title_caps:
                return
            prose(p)
            if p.lower().startswith("scene"):
                to_play()
            return
        # the play
        if re.fullmatch(r"\(.*\)", p, re.S) or re.fullmatch(r"\[.*\]", p, re.S):
            stage(p)
        elif SECTION.match(p) and len(p) < 40:
            out.extend(["", "### " + p.title(), ""])
        elif SPEAKER.match(p) and len(p) < 60:
            m = SPEAKER.match(p)
            out.extend(["", f"**{m.group(1).strip()}**"])
            if m.group(3):
                out.append(f"*({m.group(3).strip()})*")
        else:
            prose(p)

    for raw in lines:
        if TABLE_RULE.match(raw):
            flush()
            if in_table:
                out.append("")            # end of a table: end of a stanza
            in_table = not in_table
            if phase in ("intro", "cast"):
                to_play()
            continue
        if in_table:
            if not raw.strip():
                continue
            m = TABLE_NUM.match(raw)
            body = m.group(2) if m else raw.strip()
            if re.fullmatch(r"\[.*\]|\(.*\)", body.strip()):
                stage(body)
            else:
                emit_verse(int(m.group(1)) if m else None, body)
            continue
        if raw == "":
            flush()
            continue
        if not raw.strip():                       # a line of spaces: the next line is verse
            flush()
            marker = ("verse", None)
            if phase in ("intro", "cast"):
                to_play()
            continue
        if phase not in ("notes", "front") and NUMBER_LINE.match(raw) and not para:
            flush()
            marker = ("verse", int(NUMBER_LINE.match(raw).group(1)))
            if phase in ("intro", "cast"):
                to_play()
            continue
        if marker:
            flush()
            num = marker[1]
            marker = None
            if re.fullmatch(r"\s*[\[(].*[\])]\s*", raw):
                stage(raw)
            else:
                emit_verse(num, raw)
            continue
        para.append(raw)
    flush()

    # notes: each ° to the textual note for its line (nearest unused), in order
    used, defs = set(), []
    for k, ln in refs:
        best = None
        for i, (a, b, _) in enumerate(notes):
            if i in used:
                continue
            d = 0 if a <= ln <= b else min(abs(a - ln), abs(b - ln))
            if d <= 6 and (best is None or d < best[0]):
                best = (d, i)
        if best is None:
            nxt = [i for i in range(len(notes)) if i not in used]
            best = (None, nxt[0]) if nxt else None
        if best is not None:
            used.add(best[1])
            defs.append(f"[^{k}]: {notes[best[1]][2]}")
        else:
            defs.append(f"[^{k}]: Textual note.")

    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    fm = ["---", f"id: {meta['id']}", f"work: {meta['work']}", f"author: {meta['author']}",
          f"title: {meta['title']}"]
    if meta.get("edition"):
        fm.append(f"edition: {meta['edition']}")
    fm += [f"language: {meta.get('language', 'eng')}", "layout: verse", "numbering: auto"]
    if meta.get("source"):
        fm.append(f"source: {meta['source']}")
    fm.append("---")
    md = "\n".join(fm) + "\n\n" + body + "\n" + ("\n" + "\n".join(defs) + "\n" if defs else "")
    report = {"verse_lines": verse_n, "last_line": line_no, "notes": len(notes), "note_refs": len(refs),
              "notes_matched": len(used)}
    return md, report


# ---- books (PDF, EPUB): pages of lines from reader/sources.py -> library format ------------
ACT_HEAD = re.compile(r"^(ACT|ACTUS|SCENE|SCAENA|SCENA|PROLOGUE|PROLOGUS|EPILOGUE|ODE|"
                      r"EPISODE|PARODOS|STASIMON|EXODOS|STROPHE|ANTISTROPHE|EPODE)\b", re.I)
CAST_HEAD = re.compile(r"^(characters|personae|dramatis personae|cast|persons of the (drama|play))\b:?", re.I)
LEAD_NUM = re.compile(r"^(\d{1,4})(?=[^\d\s.,:;)\]–-]|\s+\S|$)\s*")
TRAIL_NUM = re.compile(r"\s+(\d{1,4})$")
END_HEAD = re.compile(r"^(selective )?(critical apparatus|apparatus|commentary|textual notes|notes|sigla|index|"
                      r"bibliography|appendix)\b", re.I)
ABBREV = re.compile(r"^([A-Za-z]{2,5}\.)\s+(?=[A-ZÀ-Ö(])")


def convert_lines(lines, meta, drop=("||",)):
    """Lines of a book's verse part -> (library Markdown, report). meta: id, work, author, title,
    edition, language, source. drop: lines containing any of these are left out (apparatus)."""
    lines = [dict(l) for l in lines if not any(d and d in l.get("t", "") for d in drop)]
    # running heads: the same short line on many pages (not a speaker)
    seen = {}
    for l in lines:
        t = l.get("t", "")
        if t and len(t) < 50 and not l.get("lead") and t.upper() != t:
            seen[t] = seen.get(t, 0) + 1
    title = fold(meta.get("title", ""))
    junk = {t for t, n in seen.items() if n >= 5 and (fold(t) == title or not re.search(r"[.,;:!?]$", t))}
    lines = [l for l in lines if l.get("t", "") not in junk]

    # where are the line numbers: before the line (margin, own line, glued on) or after it?
    lead_n = sum(1 for l in lines if l.get("margin") or LEAD_NUM.match(l.get("t", "")))
    trail_n = sum(1 for l in lines if TRAIL_NUM.search(l.get("t", "")))
    trailing = trail_n > lead_n

    # speakers given as abbreviations ("lyc. Sceptroque ..."), accepted when they recur
    count = {}
    for l in lines:
        m = ABBREV.match(l.get("t", ""))
        if m and not l.get("it"):
            count[m.group(1)] = count.get(m.group(1), 0) + 1
    abbr = {a for a, n in count.items() if n >= 2}
    names = set()

    # items: ("verse", text, number, number at end) | ("spk", name) | ("stage", text)
    #        | ("head", text) | ("brk",)
    items, front = [], []
    in_front, cast, pending = True, False, None
    for l in lines:
        t = l.get("t", "")
        if l.get("brk"):
            items.append(("brk",))
            continue
        if l.get("margin"):
            pending = l["margin"]
            continue
        if not t or re.fullmatch(r"\[[\w ]{1,6}\]", t):
            continue                                      # nothing, or an OCR'd page number
        if not in_front and items and END_HEAD.match(t) and (l.get("head") or t.upper() == t):
            break                                         # the apparatus or commentary after the play
        if l.get("head") or (len(t) < 40 and ACT_HEAD.match(t) and t.upper() == t):
            if not re.search(r"[A-Za-z]{3}", t) or fold(t) == title:
                continue                                  # OCR'd numbers, the play's title
            if CAST_HEAD.match(t):
                cast = True
                continue
            if ACT_HEAD.match(t) and (t.upper() == t or re.match(r"(?i)act(us)?\b", t)):
                in_front = False
                items.append(("head", t.title() if t.upper() == t else t))
            elif in_front:
                front.append(("label", t.rstrip(":")))
            continue
        if in_front and not l.get("it") and not (LEAD_NUM.match(t) or TRAIL_NUM.search(t) or l.get("lead")
                                                 or re.fullmatch(r"\d{1,4}", t)):
            # before the play: the cast list (it may have begun on an earlier page)
            if re.fullmatch(r"[A-ZÀ-Öa-zà-ÿ .'’\-]+", t) and len(t) < 30:
                names.add(t.rstrip(".").upper())
            if front and front[-1][0] == "p" and (t[:1] in "(" or t[:1].islower()):
                front[-1] = ("p", front[-1][1] + " " + t)
            else:
                front.append(("p", t))
            continue
        in_front = False
        if l.get("it"):
            if items and items[-1][0] == "stage" and (not items[-1][1].endswith((".", "!", "?"))
                                                       or t[:1].islower()):
                items[-1] = ("stage", items[-1][1] + " " + t)
            else:
                items.append(("stage", t))
            continue
        if re.fullmatch(r"\d{1,4}", t):
            pending = int(t)                              # a number on its own line
            continue
        spk = l.get("lead")
        if not spk:
            m = ABBREV.match(t)
            if m and m.group(1) in abbr:
                spk, t = m.group(1), t[m.end():]
            elif len(t) <= 40 and re.fullmatch(r"[A-ZÀ-Ö][A-ZÀ-Ö .'’\-]+\.?", t) and len(t.strip(". ")) > 2:
                spk, t = t, ""
        if spk:
            spk = spk.strip()
            if spk.endswith(".") and len(spk) <= 6 or spk.lower() == spk:
                short = spk.rstrip(".").upper()
                spk = next((n for n in sorted(names) if n.startswith(short)), short)
            spk = spk.rstrip(".")
            items.append(("spk", spk))
            if not t:
                continue
        num, at_end = None, False
        m = None if trailing else LEAD_NUM.match(t)
        if m and m.end() < len(t):
            num, t = int(m.group(1)), t[m.end():]
        elif trailing:
            m = TRAIL_NUM.search(t)
            if m:
                num, at_end, t = int(m.group(1)), True, t[:m.start()]
        if num is None and pending is not None:
            num = pending
        pending = None
        items.append(("verse", t.strip(), num, at_end))

    # a number for every verse line: anchors where the book prints one, estimated between
    # (an OCR'd book may run several lines together: their length tells how many)
    verses = [i for i, it in enumerate(items) if it[0] == "verse"]
    lens = sorted(len(items[i][1]) for i in verses if items[i][2] is not None) or [40]
    med = max(12, lens[len(lens) // 2])
    est = {i: max(1, round(len(items[i][1]) / med)) if len(items[i][1]) > 1.6 * med else 1 for i in verses}
    anchors = []
    for i in verses:
        n = items[i][2]
        if n is None:
            continue
        start = n - est[i] + 1 if items[i][3] else n
        if anchors and not (0 < start - anchors[-1][1] <= 60):
            continue                                      # a stray or misread number
        anchors.append((i, start))
    keys = {}
    if anchors:
        first_i, first_s = anchors[0]
        before = [i for i in verses if i < first_i]
        s = first_s - sum(est[i] for i in before)
        for i in before:
            keys[i] = max(1, s)
            s += est[i]
        for (ai, a), (bi, b) in zip(anchors, anchors[1:] + [(None, None)]):
            span = [i for i in verses if i >= ai and (bi is None or i < bi)]
            total = sum(est[i] for i in span)
            room = (b - a) if b is not None else total
            cum = 0
            for i in span:
                keys[i] = a + (cum * room) // total
                cum += est[i]
    else:
        for n, i in enumerate(verses, 1):
            keys[i] = n

    out, last_key, n_lines, n_half = [], None, 0, 0
    for i, it in enumerate(items):
        kind = it[0]
        if kind == "brk":
            if out and out[-1] != "":
                out.append("")
        elif kind == "head":
            out.extend(["", "### " + it[1], ""])
        elif kind == "spk":
            out.extend(["", f"**{it[1]}**"])
        elif kind == "stage":
            out.extend(["", f"*({it[1].strip('()')})*", ""])
        else:
            text = it[1]
            if re.match(r"^(\*\*|\*\(|##|> |¶ |\\|:::)", text):
                text = "\\" + text
            k = keys.get(i)
            if k is None or (last_key is not None and k <= last_key):
                out.append(f"{{{{+}}}} {text}")
                n_half += 1
            else:
                out.append(f"{{{{{k}}}}} {text}")
                last_key = k
                n_lines += 1

    head = []
    if front:
        texts = [t for k, t in front if k == "p"]
        short = texts and sum(len(t) for t in texts) / len(texts) < 90
        head += ["::: Characters" if cast or short else "::: Introduction", ""]
        label = None
        for kind, t in front:
            if kind == "label":
                label = t
                continue
            head += [f"¶ {label}: {t}" if label else f"¶ {t}", ""]
            label = None
        head += [":::", ""]

    body = re.sub(r"\n{3,}", "\n\n", "\n".join(head + out)).strip()
    fm = ["---", f"id: {meta['id']}", f"work: {meta['work']}", f"author: {meta['author']}",
          f"title: {meta['title']}"]
    if meta.get("edition"):
        fm.append(f"edition: {meta['edition']}")
    fm += [f"language: {meta.get('language', 'eng')}", "layout: verse", "numbering: explicit"]
    if meta.get("source"):
        fm.append(f"source: {meta['source']}")
    fm.append("---")
    report = {"verse_lines": n_lines + n_half, "last_line": last_key or 0, "numbered_in_book": len(anchors),
              "speakers": len({it[1] for it in items if it[0] == "spk"}),
              "stage": sum(1 for it in items if it[0] == "stage"), "half_lines": n_half,
              "numbers_at": "end of line" if trailing else "start of line"}
    return "\n".join(fm) + "\n\n" + body + "\n", report
