"""Add a Wikisource work from the catalog (corpus/catalog/wikisource.json) to corpus/library/own, both sides.

It follows what worked in the trial scripts (tools/legacy/fetch_*.py), made generic:

  1. The original: the catalog row's page on its own Wikisource. If it has subpages (a chapter
     list) they are fetched in order; otherwise the page itself.
  2. The English: the English page of the row is a hub that lists translations. The first listed
     translation that actually has text is used (or the address you give, see add_translation).
  3. Each page is fetched through the MediaWiki API (action=parse), not an EPUB export: poems
     (div.poem) become verse, everything else prose paragraphs.
  4. Chapters are keyed {{n}} or {{part.n}} from the numbers in their titles, Roman or Arabic or
     spelled out (Chapter XIV, Capítulo 14, Libro primero), so the two sides pair on the same
     key. A site build reports how many keys matched (site/local/_sync.md).

The result is a draft to look over.
"""
import html as htmlmod
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lxml import html as lhtml

from . import paths

ROOT = paths.ROOT
CATALOG = paths.WIKISOURCE_JSON
AGENT = "neoperseus/1.0 (personal reader; polite, one page at a time)"
CODE = {"el": "grc", "la": "lat", "en": "eng"}      # Wikisource language code -> library code
DELAY = 0.7
SKIP_TAIL = ("notes", "illustrations", "cover", "title page", "contents", "index", "footnotes", "errata")
SKIP_LINK = re.compile(r"^(Author|Portal|Category|Index|Wikisource|Help|Special|Talk|File|Template):", re.I)
STOP_PARA = re.compile(r"^(↑|This work is a translation|Original:|Translation:|Это произведение|Cette œuvre|"
                       r"Dieses Werk|Questo testo|Esta obra)")
ORDINALS = {w: i for i, ws in enumerate((
    "first primero primera primo prima premier première erste erster ersten primus".split(),
    "second segundo segunda secondo seconda deuxième zweite zweiter secundus secunda".split(),
    "third tercero tercera terzo terza troisième dritte dritter tertius tertia".split(),
    "fourth cuarto cuarta quarto quarta quatrième vierte vierter quartus".split(),
    "fifth quinto quinta cinquième fünfte quintus".split(),
    "sixth sexto sexta sesto sixième sechste sextus".split(),
    "seventh séptimo septimo séptima settimo septième siebte septimus".split(),
    "eighth octavo octava ottavo huitième achte octavus".split(),
    "ninth noveno novena nono neuvième neunte nonus".split(),
    "tenth décimo decimo dixième zehnte decimus".split()), 1) for w in ws}


def log_default(msg):
    print(msg)


# ---- the API --------------------------------------------------------------------------------
def api(lang, tries=6, **params):
    url = f"https://{lang}.wikisource.org/w/api.php?" + urllib.parse.urlencode(
        {**params, "format": "json", "redirects": "1"})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(DELAY)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < tries - 1:
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def find(wid):
    for w in json.loads(CATALOG.read_text(encoding="utf-8"))["works"]:
        if w["id"] == wid:
            return w
    raise KeyError(f"not in corpus/catalog/wikisource.json: {wid}")


def page_of(url):
    """https://en.wikisource.org/wiki/Hymn_to_Beauty_(Martin) -> ('en', 'Hymn to Beauty (Martin)')"""
    u = urllib.parse.urlsplit(url)
    return u.hostname.split(".")[0], urllib.parse.unquote(u.path.split("/wiki/", 1)[1]).replace("_", " ")


# ---- numbers in titles ------------------------------------------------------------------------
def roman(s):
    if not re.fullmatch(r"[IVXLCDM]+", s):
        return None
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = prev = 0
    for ch in reversed(s):
        v = vals[ch]
        total = total - v if v < prev else total + v
        prev = v
    return total


def num_of(part):
    """'Chapter XIV' -> 14, 'Capítulo 3' -> 3, 'Libro primero' -> 1, 'Volume 2' -> 2, else None."""
    toks = re.findall(r"[\wÀ-ÿ]+", part.strip(), re.U)
    for t in reversed(toks[-2:]):
        if t.isdigit():
            return int(t)
        if t.isupper() and roman(t):
            return roman(t)
        if t.lower() in ORDINALS:
            return ORDINALS[t.lower()]
    return None


def sort_key(title, root):
    tail = title[len(root):].lstrip("/")
    return [(0, num_of(p), p) if num_of(p) is not None else (1, 0, p.lower()) for p in tail.split("/")]


def subpages(lang, root):
    """Existing subpages root/..., in reading order (numbers in the titles, not alphabetical)."""
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "allpages", "apprefix": root + "/", "apnamespace": "0", "aplimit": "500"}
        if cont:
            p["apcontinue"] = cont
        d = api(lang, **p)
        for pg in d.get("query", {}).get("allpages", []):
            tail = pg["title"][len(root) + 1:].lower()
            if not any(s in tail for s in SKIP_TAIL):
                out.append(pg["title"])
        cont = d.get("continue", {}).get("apcontinue")
        if not cont:
            break
    # a container ("Volume 1" with "Volume 1/Chapter I" under it) holds no text of its own
    have = set(out)
    leaves = [t for t in out if not any(o.startswith(t + "/") for o in have)]
    return sorted(leaves or out, key=lambda t: sort_key(t, root))


def hub_links(lang, title):
    d = api(lang, action="parse", page=title, prop="links")
    if "error" in d:
        return []
    return [l["*"] for l in d["parse"].get("links", [])
            if l.get("ns", 0) == 0 and "exists" in l and not SKIP_LINK.match(l["*"]) and l["*"] != title]


# ---- reading a page ----------------------------------------------------------------------------
DROP_TAGS = ("table", "style", "script")
DROP_CLASSES = ("ws-noexport", "headertemplate", "footertemplate", "mw-editsection", "pagenum", "ws-pagenum",
                "reference", "reflist", "noprint", "licenseContainer", "mw-empty-elt", "toc")


def has_class(c):
    return f'contains(concat(" ", normalize-space(@class), " "), " {c} ")'


DROP_XPATH = " | ".join([f"//{t}" for t in DROP_TAGS] + [f"//*[{has_class(c)}]" for c in DROP_CLASSES] + ['//*[@id="toc"]'])


def drop_junk(root):
    for el in root.xpath(DROP_XPATH):
        if el.getparent() is not None:
            el.drop_tree()


def italics(el):
    for i in el.xpath(".//i|.//em"):
        t = i.text_content().strip()
        if t:
            i.text = "*" + t + "*"
            for c in list(i):
                i.remove(c)


def tidy(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ").replace("​", "")).strip()


def read_page(lang, title):
    """A page as {'verse': [stanza, ...]} (lists of lines) or {'prose': [paragraph, ...]}; None if it has no text."""
    d = api(lang, action="parse", page=title, prop="text")
    if "error" in d:
        return None
    root = lhtml.fragment_fromstring(d["parse"]["text"]["*"], create_parent="div")
    drop_junk(root)
    stanzas = []
    for poem in root.xpath(f"//div[{has_class('poem')}]"):
        for p in poem.xpath(".//p") or [poem]:
            for br in p.xpath(".//br"):
                br.tail = "\n" + (br.tail or "")
            italics(p)
            lines = [tidy(l) for l in p.text_content().split("\n")]
            lines = [re.sub(r"\s+\d+$", "", l) for l in lines if l]
            if lines:
                stanzas.append(lines)
    if stanzas:
        return {"verse": stanzas}
    paras = []
    for p in root.xpath(".//p"):
        for br in p.xpath(".//br"):
            br.tail = " " + (br.tail or "")
        italics(p)
        t = tidy(p.text_content())
        if not t or t == "↑":
            continue
        if STOP_PARA.match(t):
            break
        paras.append(t)
    return {"prose": paras} if paras else None


def author_of(lang, title):
    d = api(lang, action="parse", page=title, prop="text")
    if "error" in d:
        return ""
    m = re.search(r'href="/wiki/(?:Author|Autor|Auteur|Autore|Автор|作者|著者):[^"]*"[^>]*>([^<]+)<',
                  d["parse"]["text"]["*"])
    return htmlmod.unescape(m.group(1)).strip() if m else ""


# ---- building the Markdown ------------------------------------------------------------------------
def short(title):
    """'The Bet (Chekhov/Garnett)' -> 'The Bet'; 'Collection/The Bet' -> 'The Bet'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).split("/")[-1].strip() or title


def heading_of(title, root):
    tail = title[len(root):].lstrip("/")
    return (tail or short(root)).replace("/", " — ")


def fetch_work(lang, root, log):
    """The pages of a work, in order, as (title, page): the subpages of root, else root itself."""
    subs = subpages(lang, root)
    pages = []
    if subs:
        log(f"[{lang}] {root}: {len(subs)} subpages")
        for n, t in enumerate(subs, 1):
            if n % 8 == 1 or n == len(subs):
                log(f"[{lang}] reading {n}/{len(subs)}: {t}")
            pg = read_page(lang, t)
            if pg:
                pages.append((t, pg))
    else:
        log(f"[{lang}] reading {root}")
        pg = read_page(lang, root)
        if pg:
            pages.append((root, pg))
    return pages


def keys_for(pages, root):
    """{{n}} or {{part.n}} per page from the numbers in the titles; ordinals where there are none."""
    out, seen = [], set()
    for i, (t, _) in enumerate(pages, 1):
        parts = t[len(root):].lstrip("/").split("/") if t != root else [""]
        nums = [num_of(p) for p in parts]
        if len(parts) >= 2 and nums[-1] is not None and nums[-2] is not None:
            k = f"{nums[-2]}.{nums[-1]}"
        elif len(parts) == 1 and nums[-1] is not None:
            k = str(nums[-1])
        else:
            k = str(i)
        while k in seen:
            k += "b"
        seen.add(k)
        out.append(k)
    return out


def to_markdown(pages, root, para_keys=True):
    verse = sum("verse" in p for _, p in pages) > len(pages) / 2
    single = len(pages) == 1
    lines, keys = [], keys_for(pages, root)
    for (t, pg), k in zip(pages, keys):
        lines += [f"## {heading_of(t, root)}", ""]
        if verse:
            for st in pg.get("verse") or [[x] for x in pg.get("prose", [])]:
                lines += st + [""]
        else:
            paras = pg.get("prose") or [" ".join(s) for s in pg["verse"]]
            if single and para_keys:                    # one page: paragraph numbers are the keys
                for n, p in enumerate(paras, 1):
                    lines += [f"{{{{{n}}}}} {p}", ""]
            else:                                       # chapters: the chapter number keys its first paragraph
                lines += [f"{{{{{1 if single else k}}}}} {paras[0]}", ""]
                for p in paras[1:]:
                    lines += [p, ""]
    return "\n".join(lines).strip() + "\n", ("verse" if verse else "prose")


def front(meta):
    return "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items() if v) + "\n---\n\n"


def is_translation_of(cand, hub):
    """A page that is the hub's work: "Hub (Translator)", "Hub/...", or "Collection/Hub". Anthologies that merely
    link to the hub are not (importing one would bring in every story in it)."""
    h = hub.lower()
    c = cand.lower()
    last = re.sub(r"\s*\(.*\)\s*$", "", c.split("/")[-1])
    return c.startswith(h + " (") or c.startswith(h + "/") or last == h


def pick_translation(hub, log):
    """The English text for a hub page: the hub itself if it has chapters, else the first listed page that is a
    translation of it and has text. Returns (title or None, reason)."""
    log(f"[en] looking for a translation of {hub}")
    if subpages("en", hub):
        return hub, ""
    cands = [c for c in hub_links("en", hub) if is_translation_of(c, hub)]
    for cand in cands[:6]:
        log(f"[en] trying translation: {cand}")
        if subpages("en", cand) or read_page("en", cand):
            return cand, ""
    return None, f"no English translation of {hub} with text was found"


def work_of(wid):
    return re.sub(r"\.[a-z]+$", "", wid)


def write_side(dest, work, title, author, lang_ws, root, pages, edition, orig_ws, log, para_keys=True):
    body, layout = to_markdown(pages, root, para_keys)
    code = CODE.get(lang_ws, lang_ws)
    meta = {"id": f"{work}.{code}-wikisource", "work": work, "author": author or "Various", "title": title,
            "label": short(root), "edition": edition, "language": code}
    if lang_ws == "en" and orig_ws not in ("el", "la"):
        meta["original"] = CODE.get(orig_ws, orig_ws)
    meta["layout"] = layout
    meta["numbering"] = ("auto-by-section" if len(pages) > 1 else "auto") if layout == "verse" else "explicit"
    meta["source"] = f"https://{lang_ws}.wikisource.org/wiki/" + urllib.parse.quote(root.replace(" ", "_"))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{work}.{code}-wikisource.md"
    out.write_text(front(meta) + body, encoding="utf-8")
    log(f"wrote {out.name}: {len(pages)} section(s), {layout}")
    return out


def edition_of(title):
    m = re.search(r"\(([^)]+)\)\s*$", title)
    return m.group(1).split("/")[-1] if m else "Wikisource"


def add(wid, dest=None, log=log_default, translation=""):
    """Original and English both. `translation` is an English Wikisource address to use instead of the hub's first."""
    w = find(wid)
    dest = Path(dest or paths.LIBRARY_OWN)
    work = work_of(wid)
    olang, otitle = page_of(w["orig_url"])
    opages = fetch_work(olang, otitle, log)
    if not opages:
        raise RuntimeError(f"no text found on {w['orig_url']}")
    author = author_of(olang, otitle)
    if translation:
        if not re.match(r"^https://en\.wikisource\.org/wiki/.+", translation):
            raise ValueError("paste the address of an English Wikisource page (https://en.wikisource.org/wiki/...)")
        etitle, why = page_of(translation)[1], ""
    else:
        etitle, why = pick_translation(w["en_title"], log)
    if not etitle:
        log(why + ". Only the original was added; use '+ translation' with the address of one.")
        return [write_side(dest, work, w["en_title"], author, olang, otitle, opages, "Wikisource", olang, log)]
    epages = fetch_work("en", etitle, log)
    if not epages:
        log(f"no text on {etitle}; only the original was added")
        return [write_side(dest, work, w["en_title"], author, olang, otitle, opages, "Wikisource", olang, log)]
    # two single pages of prose pair paragraph by paragraph only if they have the same number of paragraphs
    pk = not (len(opages) == 1 and len(epages) == 1 and "prose" in opages[0][1] and "prose" in epages[0][1]
              and len(opages[0][1]["prose"]) != len(epages[0][1]["prose"]))
    if not pk:
        log("the two texts have different numbers of paragraphs, so they are paired as one block")
    return [write_side(dest, work, w["en_title"], author, olang, otitle, opages, "Wikisource", olang, log, pk),
            write_side(dest, work, w["en_title"], author, "en", etitle, epages, edition_of(etitle), olang, log, pk)]


def add_translation(wid, url, dest=None, log=log_default):
    """Only the English side, from the address given, for a work whose original is already added."""
    w = find(wid)
    if not re.match(r"^https://en\.wikisource\.org/wiki/.+", url):
        raise ValueError("paste the address of an English Wikisource page (https://en.wikisource.org/wiki/...)")
    olang, otitle = page_of(w["orig_url"])
    etitle = page_of(url)[1]
    epages = fetch_work("en", etitle, log)
    if not epages:
        raise RuntimeError(f"no text found on {url}")
    return [write_side(dest or paths.LIBRARY_OWN, work_of(wid), w["en_title"], author_of(olang, otitle),
                       "en", etitle, epages, edition_of(etitle), olang, log)]
