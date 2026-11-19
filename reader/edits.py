"""Text edits kept apart from the texts: library/edits.tsv, applied when a text is read.

Converted Perseus texts are regenerated from the Perseus sources, so an edit made in
library/perseus/ would be lost on the next conversion. Instead each edit is a rule:

    text id <TAB> action <TAB> opening words of the paragraph

The paragraph is found by its opening words (as the reader shows them: no section numbers,
note marks or markup), so a rule keeps working after a re-conversion. Actions:

    delete      remove the paragraph (prose) or stanza (verse)

`python perseus.py edit` writes these rules from the reader; they can also be edited by hand.
"""
import re
import unicodedata
from pathlib import Path

KEY = re.compile(r"\{\{[^}]*\}\}")
NOTE_REF = re.compile(r"\[\^[^\]]+\]")
NOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
ANCHOR_LEN = 80
HEADER = ("# Text edits, applied when the site is built (see reader/edits.py).\n"
          "# text id\taction\topening words of the paragraph\n")


def plain(s):
    """Text as the reader displays it, for matching: no keys, note marks or italics markup."""
    s = KEY.sub("", s)
    s = NOTE_REF.sub("", s)
    s = re.sub(r"\*([^*\n]+)\*", r"\1", s)
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip()


def anchor_of(text):
    return plain(text)[:ANCHOR_LEN]


def front_matter(raw):
    """(meta, index of the first body line)."""
    meta = {}
    if not raw.startswith("---"):
        return meta, 0
    end = raw.find("\n---", 3)
    if end < 0:
        return meta, 0
    for line in raw[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, raw[:end + 1].count("\n") + 1


def segments(raw):
    """Paragraphs as the reader shows them: [(line indices, plain text)], following library.parse."""
    meta, start = front_matter(raw)
    verse = meta.get("layout", "prose") == "verse"
    lines = raw.split("\n")
    out, cur, texts = [], [], []

    def close():
        if cur:
            out.append((list(cur), plain(" ".join(texts))))
        cur.clear()
        texts.clear()

    for i in range(start, len(lines)):
        s = lines[i].strip()
        if NOTE_DEF.match(s):
            continue
        if not s:
            close()
        elif (s.startswith("## ") or s.startswith("### ") or re.fullmatch(r"\*\*[^*]+\*\*", s)
              or re.fullmatch(r"\*\(.*\)\*", s) or s == "{{gap}}"):
            close()
        elif s.startswith("> ") and not verse:
            close()
            out.append(([i], plain(s[2:])))
        elif s.startswith("> "):
            cur.append(i)
            texts.append(s[2:])
        elif verse and s.startswith("¶ "):
            close()
            out.append(([i], plain(s[2:])))
        else:
            if s[:1] == "\\":
                s = s[1:]
            cur.append(i)
            texts.append(s)
    close()
    return out


class Rules:
    def __init__(self, path):
        self.path = Path(path)
        self.rules = []            # (text id, action, anchor)
        self.used = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    self.rules.append((parts[0].strip(), parts[1].strip(), plain(parts[2])))

    def for_id(self, tid):
        return [r for r in self.rules if r[0] == tid]

    def apply(self, raw, path):
        """library.parse hook: the file's text with its rules applied."""
        meta, _ = front_matter(raw)
        rules = self.for_id(meta.get("id") or Path(path).stem)
        if not rules:
            return raw
        drop = set()
        for seg_lines, text in segments(raw):
            for r in rules:
                if r[1] == "delete" and r[2] and text.startswith(r[2]):
                    drop.update(seg_lines)
                    self.used.add(r)
        if not drop:
            return raw
        return "\n".join(l for i, l in enumerate(raw.split("\n")) if i not in drop)

    def unmatched(self):
        return [r for r in self.rules if r not in self.used]

    # ---- writing (the edit server) ----
    def add(self, tid, action, text):
        rule = (tid, action, anchor_of(text))
        if rule[2] and rule not in self.rules:
            self.rules.append(rule)
            self.save()
        return rule

    def remove(self, tid, action, anchor):
        rule = (tid, action, plain(anchor))
        if rule in self.rules:
            self.rules.remove(rule)
            self.save()

    def save(self):
        body = "".join(f"{t}\t{a}\t{x}\n" for t, a, x in self.rules)
        self.path.write_text(HEADER + body, encoding="utf-8")
