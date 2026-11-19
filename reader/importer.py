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
                out.extend(["### Introduction", ""])
            elif p.lower().startswith("translated by") and not meta.get("edition"):
                meta["edition"] = p[len("translated by"):].strip()
            return
        if phase == "intro":
            if p.lower() == "characters" or fold(p).upper() == title_caps:
                if p.lower() == "characters":
                    phase = "cast"
                    out.extend(["", "### Characters", ""])
                return
            prose(p)
            return
        if phase == "cast":
            if p.lower() == "characters" or fold(p).upper() == title_caps:
                return
            prose(p)
            if p.lower().startswith("scene"):
                phase = "play"
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
                phase = "play"
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
                phase = "play"
            continue
        if phase not in ("notes", "front") and NUMBER_LINE.match(raw) and not para:
            flush()
            marker = ("verse", int(NUMBER_LINE.match(raw).group(1)))
            if phase in ("intro", "cast"):
                phase = "play"
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
