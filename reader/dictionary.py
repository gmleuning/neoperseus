"""Build the dictionaries the reader's side panel uses (run: python perseus.py dictionaries).

Sources, downloaded once into corpus/dict/:
- LSJ, A Greek-English Lexicon: PerseusDL/lexica (27 files, about 270 MB), CC BY-SA.
- Lewis & Short, A Latin Dictionary: PerseusDL/lexica (2 files, about 155 MB), CC BY-SA.
- Greek Morpheus forms (inflected form -> headword and parse): gcelano/LemmatizedAncientGreekXML,
  CC BY-NC 4.0 (fine for personal use; do not publish the built site commercially).

Output goes to site/dict/ as small script files grouped by the first two letters, because a
page opened from disk may load scripts but may not read other files.
"""
import html
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

from lxml import etree

from .perseus import download

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "corpus" / "dict"
LEXICA = "https://raw.githubusercontent.com/PerseusDL/lexica/master/CTS_XML_TEI/perseus/pdllex"
MORPHEUS = "https://raw.githubusercontent.com/gcelano/LemmatizedAncientGreekXML/master/Morpheus/MorpheusUnicode.xml.zip"


# ---- text helpers ----------------------------------------------------------------
def fold(s, latin=False):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    if latin:
        s = s.replace("j", "i").replace("v", "u")
    return re.sub(r"[^\w]", "", s)


def bucket(key):
    k = (key + "__")[:2]
    return "-".join(f"{ord(c):x}" for c in k)


BETA = dict(zip("abgdezhqiklmncoprstufxywv", "αβγδεζηθικλμνξοπρστυφχψωϝ"))
DIACRITICS = {")": "\u0313", "(": "\u0314", "/": "\u0301", "\\": "\u0300", "=": "\u0342",
              "+": "\u0308", "|": "\u0345", "?": "\u0323", "^": "\u0306", "_": "\u0304"}


def beta(s):
    """Perseus Beta Code -> polytonic Unicode (a)/nqrwpos -> ἄνθρωπος)."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "*":                                  # capital: diacritics come before the letter
            j, marks = i + 1, ""
            while j < n and s[j] in DIACRITICS:
                marks += DIACRITICS[s[j]]
                j += 1
            if j < n and s[j].lower() in BETA:
                out.append(BETA[s[j].lower()].upper() + "".join(sorted(marks, key=lambda m: m != "\u0308")))
                i = j + 1
                continue
            i += 1
            continue
        lc = c.lower()
        if lc in BETA:
            ch = BETA[lc]
            if lc == "s":
                nxt = s[i + 1] if i + 1 < n else ""
                if nxt == "1":
                    i += 1
                elif nxt == "2":
                    ch = "ς"
                    i += 1
                elif nxt == "3":
                    ch = "ϲ"
                    i += 1
                elif not (nxt.isalpha() or nxt in DIACRITICS):
                    ch = "ς"
            out.append(ch)
        elif c in DIACRITICS:
            out.append(DIACRITICS[c])
        elif c == ":":
            out.append("·")
        elif c == "'":
            out.append("’")
        elif c == "#":
            out.append("ʹ")
        elif c.isdigit() and out and out[-1].isalpha() is False:
            out.append(c)
        else:
            out.append(c)
        i += 1
    return unicodedata.normalize("NFC", "".join(out))


def clean_key(key):
    return re.sub(r"\d+$", "", key)


# ---- downloads ---------------------------------------------------------------------
def fetch_sources():
    files = [(f"{LEXICA}/grc/lsj/grc.lsj.perseus-eng{i}.xml", SRC / f"lsj{i}.xml") for i in range(1, 28)]
    files += [(f"{LEXICA}/lat/ls/lat.ls.perseus-eng{i}.xml", SRC / f"ls{i}.xml") for i in (1, 2)]
    files.append((MORPHEUS, SRC / "MorpheusUnicode.xml.zip"))
    missing = [(u, p) for u, p in files if not p.exists()]
    if missing:
        print(f"downloading {len(missing)} dictionary file(s), about 440 MB in all the first time")
    ok = True
    for url, path in missing:
        print("  " + path.name)
        ok = download(url, path) and ok
    return ok


# ---- entry rendering --------------------------------------------------------------
def render_entry(entry, greek):
    """TEI dictionary entry -> compact HTML. Greek is Beta Code in LSJ, plain in Lewis & Short."""
    def is_greek(el):
        return el.get("lang") in ("greek", "grc")

    def text(t, g):
        if not t:
            return ""
        return html.escape(beta(t) if g else t, quote=False)

    def walk(el, g):
        tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
        g2 = g or is_greek(el)
        inner = text(el.text, g2) + "".join(walk(c, g2) + text(c.tail, g2) for c in el)
        if tag == "orth":
            return f'<b class="hw"{" lang=grc" if g2 else ""}>{inner}</b>'
        if tag == "sense":
            n = el.get("n") or ""
            lvl = el.get("level") or "1"
            sn = f'<span class="sn">{html.escape(n)}</span>' if n else ""
            return f'<div class="sense" data-l="{lvl}">{sn}{inner}</div>'
        if tag == "tr" or (tag == "hi" and "ital" in (el.get("rend") or "")):
            return f'<span class="tr">{inner}</span>'
        if tag == "bibl":
            n = el.get("n") or ""
            m = re.match(r"urn:cts:\w+:([\w]+\.[\w]+)(?:\.[\w-]+)?:(.+)$", n)
            if m:
                return (f'<a class="cit" data-w="{m.group(1)}" data-r="{html.escape(m.group(2).replace(":", "."))}">'
                        f"{inner}</a>")
            return f'<span class="cit">{inner}</span>'
        if tag == "quote":
            return f'<span class="q">“{inner}”</span>'
        if g2 and not g:
            return f'<span class="g" lang="grc">{inner}</span>'
        return inner

    return walk(entry, False)


def headword(entry, greek):
    orth = entry.find("{*}orth") if entry.find("{*}orth") is not None else entry.find(".//orth")
    key = entry.get("key") or ""
    if greek:
        return beta(clean_key(key)), key
    shown = "".join(orth.itertext()).strip().rstrip(",") if orth is not None else clean_key(key)
    return shown, key


def iter_entries(paths):
    for p in paths:
        for _, el in etree.iterparse(str(p), tag="entryFree", recover=True, huge_tree=True,
                                     load_dtd=False, resolve_entities=False):
            yield el
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]


# ---- Latin stems (from Lewis & Short principal parts and genitives) ------------------
def strip_marks(s):
    return fold(s, latin=True)


def attach(lemma, part):
    """Expand an abbreviated principal part or genitive against its headword:
    'lectio' + 'ōnis' -> 'lectionis'; 'flumen' + 'ĭnis' -> 'fluminis'; 'litus' + 'ŏris' -> 'litoris';
    'amo' + 'āvi' -> 'amavi'; 'miles' + 'ĭtis' -> 'militis'."""
    part = strip_marks(part)
    lemma = strip_marks(lemma)
    if not part:
        return ""
    if len(part) > 5 or part[0] not in "aeiou" or lemma.startswith(part[:2]):
        return part                                   # given in full
    i = lemma.rfind(part[0])
    if i > 0 and i >= len(lemma) - 3:                 # the abbreviation starts at that vowel
        return lemma[:i] + part
    if len(part) > 1:
        j = lemma.rfind(part[1])
        if j >= 2 and j >= len(lemma) - 2:            # align on the consonant after the vowel
            return lemma[:j - 1] + part
    return re.sub(r"(eor|ior|eo|io|or|us|is|es|os|o|x|s|e|a)$", "", lemma) + part


NOM_ENDINGS = ("us", "um", "a", "er", "is", "e", "es", "o", "or", "eo", "io", "eor", "ior")


def latin_stems(lemma, itype):
    stems = set()
    base = strip_marks(lemma)
    stems.add(base)
    for e in NOM_ENDINGS:
        if base.endswith(e) and len(base) - len(e) >= 2:
            stems.add(base[: -len(e)])
    parts = [p.strip() for p in re.split(r"[,;]| or ", itype or "") if p.strip()]
    for p in parts:
        w = p.split()[0] if p.split() else ""
        if not re.match(r"^[^\W\d_]+$", strip_marks(w) or "-"):
            continue
        full = attach(lemma, w)
        for e in ("isse", "um", "us", "is", "i", "ae", "ere", "are", "ire", "ri"):
            if full.endswith(e) and len(full) - len(e) >= 2:
                stems.add(full[: -len(e)])
                break
    return {s for s in stems if len(s) >= 2}


# ---- build -------------------------------------------------------------------------
def write_buckets(out_dir, name, table):
    out_dir.mkdir(parents=True, exist_ok=True)
    by_b = defaultdict(dict)
    for k, v in table.items():
        by_b[bucket(k)][k] = v
    for b, part in by_b.items():
        (out_dir / f"{b}.js").write_text(
            f"DictLoaded({json.dumps(name)},{json.dumps(b)},"
            + json.dumps(part, ensure_ascii=False, separators=(",", ":")) + ");\n", encoding="utf-8")
    return len(by_b)


def build_lexicon(paths, greek, out_dir, name):
    table = defaultdict(list)
    stems = defaultdict(set)
    n = 0
    for entry in iter_entries(paths):
        shown, key = headword(entry, greek)
        if not shown:
            continue
        body = re.sub(r"\s+", " ", render_entry(entry, greek)).strip()
        body = re.sub(r"\s+([,.;:)])", r"\1", body)
        k = fold(shown if greek else clean_key(key), latin=not greek)
        if not k:
            continue
        table[k].append([shown, body])
        if not greek:
            it = entry.find("{*}itype")
            itype = "".join(it.itertext()) if it is not None else ""
            for st in latin_stems(clean_key(key), itype):
                stems[st].add(k)
        n += 1
    files = write_buckets(out_dir, name, table)
    if not greek:
        write_buckets(out_dir.parent / "lat-stems", "lat-stems", {k: sorted(v) for k, v in stems.items()})
    print(f"  {name}: {n} entries in {files} files")


def build_morpheus(zip_path, out_dir):
    forms = defaultdict(set)
    lemma_forms = defaultdict(set)
    with zipfile.ZipFile(zip_path) as z, z.open("MorpheusUnicode.xml") as f:
        for _, t in etree.iterparse(f, tag="t", huge_tree=True):
            form = unicodedata.normalize("NFC", t.findtext("f") or "")
            lemma = unicodedata.normalize("NFC", t.findtext("l") or "")
            parse = t.findtext("p") or ""
            t.clear()
            if not form or not lemma:
                continue
            ff = fold(form)
            forms[ff].add((form, lemma, parse))
            lemma_forms[fold(lemma)].add(ff)
    table = {k: sorted([list(x) for x in v]) for k, v in forms.items()}
    files = write_buckets(out_dir / "grc-forms", "grc-forms", table)
    write_buckets(out_dir / "grc-lemmaforms", "grc-lemmaforms", {k: sorted(v) for k, v in lemma_forms.items()})
    print(f"  Greek forms: {len(table)} forms in {files} files")


def build_meta(catalog, out_dir):
    from .perseus import short_author
    works = {w["id"]: [short_author(catalog["authors"].get(w["author"], w["author"])), w["title"]]
             for w in catalog["works"]}
    (out_dir / "meta.js").write_text("window.DICT_WORKS = " + json.dumps(works, ensure_ascii=False,
                                     separators=(",", ":")) + ";\n", encoding="utf-8")


def build_all(site, catalog):
    if not fetch_sources():
        print("some files could not be downloaded; run the command again to retry")
        return False
    out = site / "dict"
    out.mkdir(parents=True, exist_ok=True)
    print("building the Greek forms table")
    build_morpheus(SRC / "MorpheusUnicode.xml.zip", out)
    print("building LSJ")
    build_lexicon([SRC / f"lsj{i}.xml" for i in range(1, 28)], True, out / "lsj", "lsj")
    print("building Lewis & Short")
    build_lexicon([SRC / f"ls{i}.xml" for i in (1, 2)], False, out / "ls", "ls")
    build_meta(catalog, out)
    (out / "READY").write_text("built\n", encoding="utf-8")
    return True
