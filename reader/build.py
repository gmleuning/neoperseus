"""Build the static site from the library: one page per original/translation pairing,
an index of the shelf, a catalog page, and a sync report."""
import bisect
import html
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path

from . import library

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ORIGINAL = {"grc", "lat"}
LANG_NAMES = {"grc": "Greek", "lat": "Latin", "eng": "English"}
HTML_LANG = {"grc": "grc", "lat": "la", "eng": "en"}
STRUCT = {"h2", "h3", "spk", "stage", "pb"}
GROUP_MIN = 250      # characters before a speech or paragraph start may open a new block
GROUP_MAX = 1600     # a block longer than this is split at the next shared number


# ---- small helpers -----------------------------------------------------------
def slug(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def last_part(key):
    return key.rsplit(".", 1)[-1]


def text_len(events):
    n = 0
    for e in events:
        if e[0] == "text":
            n += len(e[1])
        elif e[0] == "line":
            n += len(e[2])
        elif e[0] == "bq":
            n += len(e[1])
    return n


def key_of(e):
    if e[0] == "key":
        return e[1]
    if e[0] == "line":
        return e[1]
    return None


# ---- alignment -----------------------------------------------------------------
def shared_keys(left, right):
    """Keys present on both sides, in an order both sides agree on (longest increasing run)."""
    rfirst = {}
    for i, e in enumerate(right):
        k = key_of(e)
        if k and k not in rfirst:
            rfirst[k] = i
    pairs, seen = [], set()
    for i, e in enumerate(left):
        k = key_of(e)
        if k and k in rfirst and k not in seen:
            seen.add(k)
            pairs.append((i, rfirst[k], k))
    # longest increasing subsequence on the right positions
    tails, tails_idx, prev = [], [], [None] * len(pairs)
    for j, (_, r, _) in enumerate(pairs):
        p = bisect.bisect_left(tails, r)
        if p == len(tails):
            tails.append(r)
            tails_idx.append(j)
        else:
            tails[p] = r
            tails_idx[p] = j
        prev[j] = tails_idx[p - 1] if p else None
    out, j = [], tails_idx[-1] if tails_idx else None
    while j is not None:
        out.append(pairs[j])
        j = prev[j]
    return list(reversed(out)), len(pairs)


def back_over_struct(events, pos, floor):
    while pos > floor and events[pos - 1][0] in STRUCT:
        pos -= 1
    return pos


def chunk(left, right):
    """Split both sides at shared keys into corresponding chunks."""
    pairs, candidates = shared_keys(left, right) if right is not None else ([], 0)
    bounds = [(0, 0)]
    for li, ri, _ in pairs:
        lp = back_over_struct(left, li, bounds[-1][0])
        rp = back_over_struct(right, ri, bounds[-1][1])
        # if only headings precede the number on one side, split at the number itself, so
        # whatever the other side has first (an argument, a preface) gets a chunk of its own
        if lp <= bounds[-1][0]:
            lp = li
        if rp <= bounds[-1][1]:
            rp = ri
        if lp > bounds[-1][0] and rp > bounds[-1][1]:
            bounds.append((lp, rp))
    bounds.append((len(left), len(right) if right is not None else 0))
    chunks = []
    for (l0, r0), (l1, r1) in zip(bounds, bounds[1:]):
        chunks.append((left[l0:l1], right[r0:r1] if right is not None else []))
    if right is None:   # single column: split at structural starts instead
        chunks = [(c, []) for c in split_single(left)]
    stats = {"shared": len(pairs), "candidates": candidates}
    return chunks, stats


def split_single(events):
    out, cur = [], []
    for e in events:
        if e[0] in ("h2", "h3", "spk") and cur and any(x[0] not in STRUCT for x in cur):
            out.append(cur)
            cur = []
        if e[0] == "pb" and text_len(cur) > GROUP_MAX:
            out.append(cur)
            cur = []
        cur.append(e)
    if cur:
        out.append(cur)
    return out


def sections_and_groups(chunks):
    """Sections start at ## headings on the left; blocks start at speeches/paragraphs."""
    sections = []
    cur_sec = {"title": None, "groups": []}
    group, glen = [], 0
    for lch, rch in chunks:
        lch, rch = list(lch), list(rch)
        lead = [e for e in lch[:4] if e[0] == "h2"]
        if lead:
            if group:
                cur_sec["groups"].append(group)
            if cur_sec["groups"] or cur_sec["title"]:
                sections.append(cur_sec)
            lch.remove(lead[0])
            rch = [e for i, e in enumerate(rch) if not (e[0] == "h2" and i < 4)]
            cur_sec = {"title": lead[0][1], "groups": []}
            group, glen = [], 0
        starts_block = bool(lch) and lch[0][0] in ("h3", "spk", "stage", "pb")
        if group and ((starts_block and glen >= GROUP_MIN) or glen >= GROUP_MAX):
            cur_sec["groups"].append(group)
            group, glen = [], 0
        group.append((lch, rch))
        glen += text_len(lch)
    if group:
        cur_sec["groups"].append(group)
    if cur_sec["groups"] or cur_sec["title"]:
        sections.append(cur_sec)
    return sections


# ---- rendering -------------------------------------------------------------------
class Side:
    def __init__(self, prefix, layout, notes):
        self.prefix, self.layout, self.notes = prefix, layout, notes
        self.ids = set()
        self.pending_notes = []
        self.n = 0
        self.fn = 0

    def anchor(self, key):
        i = self.prefix + key
        if i in self.ids:
            return ""
        self.ids.add(i)
        return f' id="{html.escape(i)}"'

    def fill_notes(self, s):
        def rep(m):
            nid = m.group(1)
            if nid not in self.notes:
                return ""
            self.n += 1
            app = nid.startswith("a")
            ref = f"{self.prefix}n{self.n}"
            if not app:
                self.fn += 1
            mark = "°" if app else str(self.fn)
            self.pending_notes.append((ref, nid, app, mark))
            cls = "fn app" if app else "fn"
            return f'<sup class="{cls}"><a href="#{ref}" id="r{ref}">{mark}</a></sup>'
        return re.sub(r'<sup class="fn" data-note="([^"]+)"></sup>', rep, s)

    def render(self, events):
        out = []
        for e in events:
            t = e[0]
            if t == "line":
                k = e[1]
                if k:
                    lp = last_part(k)
                    num = lp if lp.isdigit() and int(lp) % 5 == 0 else ""
                    out.append(f'<span class="v" data-k="{html.escape(k)}"{self.anchor(k)}>'
                               f'<span class="ln">{num}</span>{self.fill_notes(e[2])}</span>')
                else:
                    out.append(f'<span class="v">{self.fill_notes(e[2])}</span>')
            elif t == "key":
                out.append(f'<span class="mk" data-k="{html.escape(e[1])}"{self.anchor(e[1])}>'
                           f'{html.escape(last_part(e[1]))}</span>')
            elif t == "text":
                out.append(self.fill_notes(e[1]))
            elif t == "pb":
                out.append('<span class="pb"></span>')
            elif t == "spk":
                out.append(f'<span class="spk">{e[1]}</span>')
            elif t == "stage":
                out.append(f'<span class="stage">{e[1]}</span>')
            elif t in ("h3", "h2"):
                out.append(f'<span class="sub">{e[1]}</span>')
            elif t == "bq":
                out.append(f'<span class="bq">{self.fill_notes(e[1])}</span>')
            elif t == "gap":
                out.append('<span class="gap">…</span>')
        return "".join(out)

    def notes_html(self, row):
        if not self.pending_notes:
            return ""
        items = []
        for ref, nid, app, mark in self.pending_notes:
            cls = ' class="app"' if app else ""
            items.append(f'<li{cls} id="{ref}"><a class="back" href="#r{ref}" '
                         f'title="back to the text">{mark}</a>{self.notes[nid]}</li>')
        self.pending_notes = []
        return f'<ol class="notes" style="--r:{row}">{"".join(items)}</ol>'


def first_key(events):
    for e in events:
        k = key_of(e)
        if k:
            return k
    return None


def last_key(events):
    for e in reversed(events):
        k = key_of(e)
        if k:
            return k
    return None


def render_page(orig, trans, page_info):
    lmeta, levents, lnotes = orig
    two = trans is not None
    rmeta, revents, rnotes = trans if two else ({}, None, {})
    chunks, stats = chunk(levents, revents)
    sections = sections_and_groups(chunks)
    L = Side("L", lmeta.get("layout", "prose"), lnotes)
    R = Side("E", rmeta.get("layout", "prose"), rnotes) if two else None

    body, toc = [], []
    for si, sec in enumerate(sections, 1):
        all_left = [e for g in sec["groups"] for lch, _ in g for e in lch]
        k0, k1 = first_key(all_left), last_key(all_left)
        rng = f"{last_part(k0)}–{last_part(k1)}" if k0 and k1 and k0 != k1 else (last_part(k0) if k0 else "")
        sid = f"s{si}"
        if sec["title"]:
            toc.append(f'<li><a href="#{sid}"><span class="t">{sec["title"]}</span>'
                       f'<span class="r">{html.escape(rng)}</span></a></li>')
        head = (f'<h2><span class="t">{sec["title"]}</span><span class="r">{html.escape(rng)}</span></h2>'
                if sec["title"] else "")
        groups = []
        llang = HTML_LANG.get(lmeta.get("language"), "en")
        rlang = HTML_LANG.get(rmeta.get("language"), "en")
        for g in sec["groups"]:
            lcls = f'col g {L.layout}" lang="{llang}'
            lch_html, rch_html = [], []
            for r, (lch, rch) in enumerate(g, 1):
                lch_html.append(f'<div class="ch" style="--r:{r}">{L.render(lch)}</div>')
                if two:
                    inner = R.render(rch)
                    if text_len(lch) == 0 and text_len(rch) > 600:
                        # material only the translation has (an argument, a preface): fold it away
                        first_text = next((i for i, e in enumerate(rch) if e[0] == "text"), len(rch))
                        heads = [e[1] for e in rch[:first_text] if e[0] == "h3"]
                        label = heads[-1].rstrip(".") if heads else "Translator’s introduction"
                        inner = f'<details class="aside"><summary>{label}</summary>{inner}</details>'
                    rch_html.append(f'<div class="ch" style="--r:{r}">{inner}</div>')
            last = len(g) + 1
            lnote = L.notes_html(last).replace('class="notes"', 'class="notes left"')
            if two:
                rnote = R.notes_html(last)
                groups.append(f'<div class="grp"><div class="{lcls}">{"".join(lch_html)}{lnote}</div>'
                              f'<div class="col e {R.layout}" lang="{rlang}">{"".join(rch_html)}{rnote}</div></div>')
            else:
                groups.append(f'<div class="grp single"><div class="{lcls}">{"".join(lch_html)}{lnote}</div></div>')
        body.append(f'<section class="sec" id="{sid}">{head}{"".join(groups)}</section>')

    has_app = any(k.startswith("a") for k in lnotes)
    return "".join(body), toc, stats, has_app


# ---- site --------------------------------------------------------------------------
def page_html(title, author, work_title, heads, toc, content, has_two, has_app, page_key, depth=1):
    up = "../" * depth
    tools = []
    if has_two:
        tools.append('<div class="seg" role="group" aria-label="Alignment">'
                     '<button type="button" data-mode="speech">Blocks</button>'
                     '<button type="button" data-mode="tight">Lines</button></div>')
    if has_app:
        tools.append('<button type="button" class="tog" id="apptog" aria-pressed="false">Apparatus</button>')
    tools.append('<form class="jump"><label for="jump">Go to</label>'
                 '<input id="jump" autocomplete="off" placeholder="1.150"></form>')
    toc_html = (f'<nav class="toc"><details open><summary>Contents</summary><ol>{"".join(toc)}</ol>'
                f'</details></nav>') if toc else ""
    layout_cls = "layout" if toc else "layout notoc"
    heads_cls = "heads" if has_two else "heads one"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{up}style.css">
</head>
<body data-page="{html.escape(page_key)}">
<header class="bar"><a class="home" href="{up}index.html">Library</a>
<div class="title"><span class="au">{html.escape(author)}</span> <span class="wk">{html.escape(work_title)}</span></div>
<div class="tools">{"".join(tools)}</div></header>
<div class="{layout_cls}">{toc_html}
<main><div class="{heads_cls}">{heads}</div>
{content}
</main></div>
<script src="{up}reader.js"></script>
</body>
</html>
"""


def edition_head(meta, others, current, kind):
    lang = LANG_NAMES.get(meta.get("language"), meta.get("language", ""))
    name = meta.get("edition") or meta.get("label") or ""
    if len(others) > 1:
        opts = "".join(
            f'<option value="{html.escape(href)}"{" selected" if href == current else ""}>'
            f'{html.escape(m.get("edition") or m.get("label") or m["id"])}</option>'
            for m, href in others)
        return f'<div><b>{lang}</b> <select class="pick" aria-label="{kind}">{opts}</select></div>'
    return f"<div><b>{lang}</b> {html.escape(name)}</div>"


def collect(lib_dir):
    works = defaultdict(list)
    for p in sorted(lib_dir.rglob("*.md")):
        if p.name.startswith(("_", ".")) or p.name.upper() == "README.MD":
            continue
        meta, events, notes = library.parse(p)
        if not meta.get("work"):
            continue
        meta.setdefault("id", p.stem)
        works[meta["work"]].append((meta, events, notes))
    return works


def build(lib_dir, site, catalog=None, shelf_ids=()):
    if site.exists():                     # start clean so removed works leave no pages behind
        shutil.rmtree(site)
    site.mkdir(parents=True)
    for name in ("style.css", "reader.js", "catalog.js"):
        shutil.copy(ASSETS / name, site / name)
    shutil.copytree(ASSETS / "fonts", site / "fonts", dirs_exist_ok=True)

    works = collect(lib_dir)
    index_entries, report, used = [], [], set()
    for wid, docs in sorted(works.items()):
        originals = sorted([d for d in docs if d[0].get("language") in ORIGINAL], key=lambda d: d[0]["id"])
        translations = sorted([d for d in docs if d[0].get("language") not in ORIGINAL], key=lambda d: d[0]["id"])
        if not originals:            # a translation alone is shown as the main text
            originals, translations = translations[:1], translations[1:]
        m0 = originals[0][0]
        author, title = m0.get("author", ""), m0.get("title", wid)
        base = f"{slug(author)}/{slug(title)}"
        if base in used:
            base = f"{slug(author)}/{slug(title)}-{slug(wid)}"
        used.add(base)

        combos = [(o, t) for o in originals for t in (translations or [None])]
        hrefs = {}
        for oi, o in enumerate(originals):
            for ti, t in enumerate(translations or [None]):
                suffix = "" if oi == 0 and ti == 0 else f".{oi}-{ti}"
                hrefs[(oi, ti)] = f"{slug(title)}{suffix}.html"
        for oi, o in enumerate(originals):
            for ti, t in enumerate(translations or [None]):
                content, toc, stats, has_app = render_page(o, t, None)
                href = hrefs[(oi, ti)]
                lhead = edition_head(o[0], [(x[0], hrefs[(i, ti)]) for i, x in enumerate(originals)],
                                     href, "Original edition")
                rhead = edition_head(t[0], [(x[0], hrefs[(oi, i)]) for i, x in enumerate(translations)],
                                     href, "Translation") if t else ""
                page = page_html(f"{title} — {author}", author, title, lhead + rhead, toc, content,
                                 t is not None, has_app, f"{slug(author)}/{href}")
                out = site / slug(author) / href
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(page, encoding="utf-8")
                if t is not None:
                    tk = sum(1 for e in t[1] if key_of(e))
                    report.append((wid, o[0]["id"], t[0]["id"], stats["shared"], stats["candidates"], tk))
        index_entries.append({
            "work": wid, "author": author, "title": title,
            "label": m0.get("label", ""), "href": f"{slug(author)}/{hrefs[(0, 0)]}",
            "editions": [d[0].get("edition") or d[0].get("label", "") for d in originals],
            "translations": [d[0].get("edition") or d[0].get("label", "") for d in translations],
            "lang": m0.get("language", ""),
        })
    write_index(site, index_entries)
    write_catalog(site, catalog, {e["work"] for e in index_entries})
    write_report(site, report)
    return index_entries, report


def write_index(site, entries):
    by_author = defaultdict(list)
    for e in entries:
        by_author[e["author"]].append(e)
    blocks = []
    for author in sorted(by_author, key=lambda a: slug(a)):
        items = []
        for e in sorted(by_author[author], key=lambda e: e["work"]):
            orig = (f'<span class="orig" lang="{"grc" if e["lang"] == "grc" else "la"}">{html.escape(e["label"])}</span>'
                    if e["label"] and e["label"] != e["title"] else "")
            trans = ", ".join(t for t in e["translations"] if t)
            who = f'<span class="who">{html.escape(trans)}</span>' if trans else ""
            items.append(f'<li data-page="{html.escape(e["href"])}"><a href="{html.escape(e["href"])}">'
                         f'{html.escape(e["title"])}</a>{orig}{who}<span class="where"></span></li>')
        blocks.append(f'<section class="au-block"><h2>{html.escape(author)}</h2><ul>{"".join(items)}</ul></section>')
    n = len(entries)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library</title>
<link rel="stylesheet" href="style.css">
</head>
<body class="index">
<main class="lib"><h1>Library</h1>
<p class="count">{n} work{"s" if n != 1 else ""} on the shelf · <a href="catalog.html">Catalog of all Perseus texts</a></p>
{"".join(blocks)}
</main>
<script src="reader.js"></script>
</body>
</html>
"""
    (site / "index.html").write_text(page, encoding="utf-8")


def write_catalog(site, catalog, on_shelf):
    if not catalog:
        return
    rows = []
    for w in catalog["works"]:
        langs = sorted({e["lang"] for e in w["editions"]})
        orig = next((e["label"] for e in w["editions"] if e["lang"] in ORIGINAL), "")
        trans = [tr for tr in (e["description"] for e in w["editions"] if e["lang"] == "eng")]
        rows.append([w["id"], catalog["authors"].get(w["author"], w["author"]), w["title"], orig,
                     "+".join(langs), len(trans), 1 if w["id"] in on_shelf else 0])
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalog</title>
<link rel="stylesheet" href="style.css">
</head>
<body class="index">
<main class="lib wide"><h1>Catalog</h1>
<p class="count">Every work in the Perseus canonical Greek and Latin repositories. To add one to your shelf, run the
command shown next to it.</p>
<div class="filters"><input id="q" type="search" placeholder="Search author or title (accents optional)" autofocus>
<label><input type="checkbox" id="eng"> with English</label>
<label><input type="checkbox" id="shelf"> on my shelf</label></div>
<p class="count" id="n"></p>
<table class="cat"><thead><tr><th>Author</th><th>Title</th><th>Languages</th><th>To add</th></tr></thead>
<tbody id="rows"></tbody></table>
</main>
<script>window.CATALOG = {data};</script>
<script src="catalog.js"></script>
</body>
</html>
"""
    (site / "catalog.html").write_text(page, encoding="utf-8")


def write_report(site, report):
    lines = ["# Sync report", "",
             "Shared = numbers found on both sides, in an order both sides agree on.",
             "Coverage = shared / numbers in the translation. Below 90% is flagged.", "",
             "| work | original | translation | shared | translation numbers | coverage | |",
             "|---|---|---|---|---|---|---|"]
    for wid, o, t, shared, cand, tk in report:
        cov = shared / tk if tk else 0
        flag = "" if cov >= 0.9 else "CHECK"
        lines.append(f"| {wid} | {o} | {t} | {shared} | {tk} | {cov:.0%} | {flag} |")
    (site / "_sync.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
