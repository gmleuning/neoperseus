"""Read a library Markdown file (see SPEC.md) into metadata and a flat list of events."""
import html
import re
import unicodedata

KEY = re.compile(r"\{\{([^}]+)\}\}")
NOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")


def inline(text):
    """Library inline markup -> HTML (italics and note references)."""
    text = html.escape(text, quote=False)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"\[\^([^\]]+)\]", r'<sup class="fn" data-note="\1"></sup>', text)
    return text


def unescape_start(line):
    return line[1:] if line[:1] == "\\" else line


def parse(path):
    raw = unicodedata.normalize("NFC", path.read_text(encoding="utf-8"))
    meta, body = {}, raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        for line in raw[3:end].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = raw[end + 4:]
    layout = meta.get("layout", "prose")
    numbering = meta.get("numbering", "explicit")

    notes, lines = {}, []
    for line in body.splitlines():
        m = NOTE_DEF.match(line)
        if m:
            notes[m.group(1)] = inline(m.group(2))
        else:
            lines.append(line.rstrip())

    events = []
    para = []
    section_no, line_no = 0, 0

    def flush():
        if not para:
            return
        text = " ".join(p.strip() for p in para)
        para.clear()
        if events and events[-1][0] not in ("pb", "h2", "h3", "spk", "stage"):
            events.append(("pb",))
        pos = 0
        for m in KEY.finditer(text):
            chunk = text[pos:m.start()]
            if chunk.strip():
                events.append(("text", inline(chunk)))
            events.append(("key", m.group(1).strip()))
            pos = m.end()
        if text[pos:].strip():
            events.append(("text", inline(text[pos:])))

    for line in lines:
        s = line.strip()
        if not s:
            flush()
            if layout == "verse" and events and events[-1][0] == "line":
                events.append(("pb",))
            continue
        if s.startswith("## "):
            flush()
            section_no += 1
            line_no = 0
            events.append(("h2", inline(s[3:].strip())))
        elif s.startswith("### "):
            flush()
            events.append(("h3", inline(s[4:].strip())))
        elif re.fullmatch(r"\*\*[^*]+\*\*", s):
            flush()
            events.append(("spk", inline(s[2:-2])))
        elif re.fullmatch(r"\*\(.*\)\*", s):
            flush()
            events.append(("stage", inline(s[2:-2])))
        elif s == "{{gap}}":
            flush()
            events.append(("gap",))
        elif s.startswith("> "):
            if layout == "prose":
                flush()
                events.append(("bq", inline(s[2:])))
            else:
                events.append(("line", None, inline(s[2:])))
        elif layout == "verse" and s.startswith("¶ "):
            flush()
            events.append(("pb",))
            events.append(("text", inline(s[2:].strip())))
            events.append(("pb",))
        elif layout == "verse":
            s = unescape_start(s)
            m = re.match(r"^\{\{([^}]+)\}\}\s*", s)
            key = None
            if m:
                key = m.group(1).strip()
                s = s[m.end():]
                if key == "+":
                    key = None
                elif key.isdigit():
                    line_no = int(key)
            elif numbering.startswith("auto"):
                line_no += 1
                key = str(line_no)
            if key and numbering == "auto-by-section" and "." not in key:
                key = f"{section_no}.{key}"
            events.append(("line", key, inline(s)))
        else:
            para.append(unescape_start(s))
    flush()
    return meta, events, notes
