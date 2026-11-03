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


# ---- verse translations with their own line numbers ---------------------------------
def split_key(k):
    p, _, n = k.rpartition(".")
    return p, n


def verse_lines_by_section(events):
    """prefix -> sorted line numbers, and the line numbers where a new speaker begins."""
    nums, turns, after_spk = defaultdict(list), defaultdict(list), False
    for e in events:
        if e[0] == "spk":
            after_spk = True
        elif e[0] == "line" and e[1]:
            p, n = split_key(e[1])
            if n.isdigit():
                nums[p].append(int(n))
                if after_spk:
                    turns[p].append(int(n))
            after_spk = False
    return {p: sorted(set(v)) for p, v in nums.items()}, turns


def own_lineation(left, right, lmeta, rmeta):
    """True when a verse translation numbers its own lines (Eclogue 1: 83 Latin lines,
    101 English), so equal numbers on the two sides do not mean the same line."""
    if lmeta.get("layout") != "verse" or rmeta.get("layout") != "verse":
        return False
    lnums, _ = verse_lines_by_section(left)
    rnums, _ = verse_lines_by_section(right)
    common = [p for p in lnums if p in rnums and lnums[p] and rnums[p]]
    if not common:
        return False
    off = sum(1 for p in common if abs(rnums[p][-1] - lnums[p][-1]) > max(3, 0.03 * lnums[p][-1]))
    return off > len(common) / 3


def remap_translation(left, right):
    """Give each translation line the original's line it most likely renders: anchored at
    section starts and ends and, when both sides have the same number of speeches, at each
    change of speaker; proportional in between. The translation keeps showing its own numbers."""
    lnums, lturns = verse_lines_by_section(left)
    rnums, rturns = verse_lines_by_section(right)
    maps = {}
    for p, rn in rnums.items():
        ln = lnums.get(p)
        if not ln:
            continue
        anchors = [(rn[0], ln[0])]
        if len(lturns.get(p, [])) == len(rturns.get(p, [])):
            anchors += list(zip(rturns[p], lturns[p]))
        anchors.append((rn[-1], ln[-1]))
        anchors = sorted(set(anchors))
        clean = [anchors[0]]
        for a in anchors[1:]:
            if a[0] > clean[-1][0] and a[1] >= clean[-1][1]:
                clean.append(a)
        maps[p] = (clean, ln)

    def mapped(p, n):
        anchors, ln = maps[p]
        xs = [a[0] for a in anchors]
        i = max(0, min(bisect.bisect_right(xs, n) - 1, len(anchors) - 2)) if len(anchors) > 1 else 0
        if len(anchors) == 1:
            target = anchors[0][1]
        else:
            (x0, y0), (x1, y1) = anchors[i], anchors[i + 1]
            target = y0 + (n - x0) * (y1 - y0) / (x1 - x0) if x1 != x0 else y0
        j = min(bisect.bisect_left(ln, round(target)), len(ln) - 1)
        return ln[j]

    out = []
    for e in right:
        if e[0] == "line" and e[1]:
            p, n = split_key(e[1])
            if p in maps and n.isdigit():
                m = mapped(p, int(n))
                out.append(("line", f"{p}.{m}" if p else str(m), e[2], e[1]))
                continue
        out.append(e)
    return out


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
                    lp = last_part(e[3] if len(e) > 3 else k)     # a translation's own number
                    cls = "ln n5" if lp.isdigit() and int(lp) % 5 == 0 else "ln"
                    out.append(f'<span class="v" data-k="{html.escape(k)}"{self.anchor(k)}>'
                               f'<span class="{cls}">{html.escape(lp)}</span>{self.fill_notes(e[2])}</span>')
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
    approx = two and own_lineation(levents, revents, lmeta, rmeta)
    if approx:
        revents = remap_translation(levents, revents)
    chunks, stats = chunk(levents, revents)
    stats["approx"] = approx
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
    return "".join(body), toc, stats, has_app, (levents, revents or [])


# ---- site --------------------------------------------------------------------------
def page_html(title, author, work_title, heads, toc, content, has_two, has_app, page_key, work_id,
              lang, depth=1):
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
    tools.append(f'<a class="icon-btn" href="{up}search.html?work={html.escape(work_id)}" '
                 f'title="Search this text">Search</a>')
    tools.append('<button type="button" class="icon-btn" data-settings aria-expanded="false" '
                 'aria-controls="settings" title="Settings (,)">Settings</button>')
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
<script src="{up}settings.js"></script>
<link rel="stylesheet" href="{up}style.css">
</head>
<body data-page="{html.escape(page_key)}" data-title="{html.escape(work_title)}" data-author="{html.escape(author)}" data-root="{up}" data-lang="{lang}">
<header class="bar"><a class="home" href="{up}index.html">Library</a>
<div class="title"><span class="au">{html.escape(author)}</span> <span class="wk">{html.escape(work_title)}</span></div>
<div class="tools">{"".join(tools)}</div></header>
<div class="{layout_cls}">{toc_html}
<main><div class="{heads_cls}">{heads}</div>
{content}
</main></div>
<script src="{up}reader.js"></script>
<script src="{up}shelf.js"></script>
<script src="{up}dict.js"></script>
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
        meta["own"] = "own" in p.relative_to(lib_dir).parts[:1]
        works[meta["work"]].append((meta, events, notes))
    return works


# ---- groups for authors with many works (catalog/groups.tsv) ----------------------
def load_groups(path):
    rules = defaultdict(list)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                rules[parts[0].strip()].append((parts[1].strip(), re.compile(parts[2].strip(), re.I)))
    return rules


def group_of(rules, author_id, title, description):
    for name, rx in rules.get(author_id, []):
        target = description if rx.pattern.startswith("desc:") else title
        pat = rx.pattern[5:] if rx.pattern.startswith("desc:") else None
        if pat is not None:
            if re.search(pat, description or "", re.I):
                return name
        elif rx.search(title or ""):
            return name
    return ""


# ---- search data -------------------------------------------------------------------
TAG = re.compile(r"<sup[^>]*>.*?</sup>|<[^>]+>")


def plain(s):
    return html.unescape(TAG.sub("", s))


def segments(events):
    """[key, text] for each stretch of text after a key; text before any key gets key ''."""
    out, key, buf = [], "", []
    for e in events:
        k = key_of(e)
        if k:
            if buf:
                out.append([key, " ".join(buf)])
                buf = []
            key = k
        if e[0] == "line":
            buf.append(plain(e[2]))
        elif e[0] in ("text", "bq"):
            buf.append(plain(e[1]))
    if buf:
        out.append([key, " ".join(buf)])
    return out


def write_search_data(site, wid, author, title, parts):
    d = site / "search"
    d.mkdir(exist_ok=True)
    payload = {"work": wid, "author": author, "title": title, "parts": parts}
    js = "SearchLoaded(" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n"
    (d / f"{slug(wid)}.js").write_text(js, encoding="utf-8")


def build(lib_dir, site, catalog=None, shelf_ids=()):
    # start clean so removed works leave no pages behind; the dictionary is kept (slow to rebuild)
    site.mkdir(parents=True, exist_ok=True)
    for child in site.iterdir():
        if child.name == "dict":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for name in ("style.css", "settings.js", "reader.js", "dict.js", "index.js", "catalog.js", "search.js"):
        if (ASSETS / name).exists():
            shutil.copy(ASSETS / name, site / name)
    shutil.copytree(ASSETS / "fonts", site / "fonts", dirs_exist_ok=True)

    rules = load_groups(ROOT / "catalog" / "groups.tsv")
    works = collect(lib_dir)
    index_entries, report, used = [], [], set()
    shelf_map = {}
    for wid, docs in sorted(works.items()):
        originals = sorted([d for d in docs if d[0].get("language") in ORIGINAL], key=lambda d: d[0]["id"])
        translations = sorted([d for d in docs if d[0].get("language") not in ORIGINAL], key=lambda d: d[0]["id"])
        if not originals:            # a translation alone is shown as the main text
            originals, translations = translations[:1], translations[1:]
        m0 = originals[0][0]
        author, title = m0.get("author", ""), m0.get("title", wid)
        base = slug(title)
        if f"{slug(author)}/{base}" in used:
            base = f"{slug(title)}-{slug(wid)}"
        used.add(f"{slug(author)}/{base}")

        hrefs = {}
        for oi, o in enumerate(originals):
            for ti, t in enumerate(translations or [None]):
                suffix = "" if oi == 0 and ti == 0 else f".{oi}-{ti}"
                hrefs[(oi, ti)] = f"{base}{suffix}.html"
        search_parts = []
        for oi, o in enumerate(originals):
            for ti, t in enumerate(translations or [None]):
                content, toc, stats, has_app, final = render_page(o, t, None)
                href = hrefs[(oi, ti)]
                lhead = edition_head(o[0], [(x[0], hrefs[(i, ti)]) for i, x in enumerate(originals)],
                                     href, "Original edition")
                rhead = edition_head(t[0], [(x[0], hrefs[(oi, i)]) for i, x in enumerate(translations)],
                                     href, "Translation") if t else ""
                page = page_html(f"{title} — {author}", author, title, lhead + rhead, toc, content,
                                 t is not None, has_app, f"{slug(author)}/{href}", wid,
                                 m0.get("language", ""))
                out = site / slug(author) / href
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(page, encoding="utf-8")
                if t is not None:
                    tk = sum(1 for e in t[1] if key_of(e))
                    report.append((wid, o[0]["id"], t[0]["id"], stats["shared"], stats["candidates"], tk,
                                   stats["approx"]))
                # search: the first original once, and each translation on its own page
                page_href = f"{slug(author)}/{href}"
                if ti == 0:
                    search_parts.append({"href": page_href, "side": "L", "lang": o[0].get("language", ""),
                                         "ed": o[0].get("edition") or o[0].get("label", ""),
                                         "segs": segments(final[0])})
                if oi == 0 and t is not None:
                    search_parts.append({"href": page_href, "side": "E", "lang": t[0].get("language", ""),
                                         "ed": t[0].get("edition") or t[0].get("label", ""),
                                         "segs": segments(final[1])})
        write_search_data(site, wid, author, title, search_parts)
        author_id = wid.split(".")[0] if not m0.get("own") else "own-" + slug(author)
        desc = m0.get("description", "")
        index_entries.append({
            "work": wid, "author": author, "author_id": author_id, "title": title,
            "label": m0.get("label", ""), "href": f"{slug(author)}/{hrefs[(0, 0)]}",
            "translations": [d[0].get("edition") or d[0].get("label", "") for d in translations],
            "lang": m0.get("language", ""), "own": bool(m0.get("own")),
            "group": group_of(rules, author_id, title, desc),
            "search": f"search/{slug(wid)}.js",
        })
        shelf_map[wid] = f"{slug(author)}/{hrefs[(0, 0)]}"
    write_index(site, index_entries)
    write_catalog(site, catalog, {e["work"] for e in index_entries})
    write_search_page(site, index_entries)
    (site / "shelf.js").write_text("window.SHELF = " + json.dumps(shelf_map, ensure_ascii=False) + ";\n",
                                   encoding="utf-8")
    write_report(site, report)
    return index_entries, report


def html_page(title, body_cls, main, scripts, data_js=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script src="settings.js"></script>
<link rel="stylesheet" href="style.css">
</head>
<body class="{body_cls}">
{main}
{data_js}
{"".join(f'<script src="{s}"></script>' for s in scripts)}
</body>
</html>
"""


def top_links(current):
    links = [("index.html", "Library"), ("search.html", "Search texts"), ("catalog.html", "Catalog")]
    out = "".join(f'<a href="{h}">{t}</a>' for h, t in links if h != current)
    return (f'<nav class="links">{out}<button type="button" class="icon-btn" data-settings '
            f'aria-expanded="false" aria-controls="settings">Settings</button></nav>')


def write_index(site, entries):
    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    n = len(entries)
    main = f"""<main class="lib">
<div class="lib-top"><h1>Library</h1>{top_links("index.html")}</div>
<p class="count">{n} work{"s" if n != 1 else ""} on the shelf</p>
<section id="continue-wrap" hidden><h3 class="label">Continue reading</h3><div class="continue" id="continue"></div></section>
<div class="finder"><input type="search" id="find" placeholder="Find a work or author (accents optional)" aria-label="Find a work or author">
<div class="chips" id="langs" role="group" aria-label="Language">
<button type="button" data-l="all" aria-pressed="true">All</button><button type="button" data-l="grc" aria-pressed="false">Greek</button><button type="button" data-l="lat" aria-pressed="false">Latin</button><button type="button" data-l="own" aria-pressed="false">My texts</button></div></div>
<div class="shelf"><nav class="authors" id="authors" aria-label="Authors"></nav><section class="works" id="works" aria-live="polite"></section></div>
<noscript><p>The library list needs JavaScript.</p></noscript>
</main>"""
    (site / "index.html").write_text(
        html_page("Library", "index", main, ["index.js"], f"<script>window.LIBRARY = {data};</script>"),
        encoding="utf-8")


def write_search_page(site, entries):
    works = [{"work": e["work"], "author": e["author"], "author_id": e["author_id"], "title": e["title"],
              "lang": e["lang"], "search": e["search"]} for e in entries]
    data = json.dumps(works, ensure_ascii=False, separators=(",", ":"))
    main = f"""<main class="lib">
<div class="lib-top"><h1>Search</h1>{top_links("search.html")}</div>
<form class="search-form" id="sf">
<input class="q" id="q" type="search" placeholder="Words or a phrase — accents optional (λογος, arma virumque)" aria-label="Search" autofocus>
<div class="opts">
<label>In <select id="scope"></select></label>
<label>Language <select id="side"><option value="all">Original and translation</option><option value="L">Original only</option><option value="E">Translation only</option></select></label>
<label><input type="checkbox" id="whole" checked> Whole words</label>
<label><input type="checkbox" id="forms"> All forms of a Greek word (needs the dictionary)</label>
</div></form>
<div class="progress" id="prog" hidden><i></i></div>
<p class="search-note" id="status">Type a word or phrase and press Enter.</p>
<div id="results"></div>
</main>"""
    (site / "search.html").write_text(
        html_page("Search", "index search", main, ["search.js", "dict.js"],
                  f"<script>window.WORKS = {data};</script>"),
        encoding="utf-8")


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
    main = f"""<main class="lib wide">
<div class="lib-top"><h1>Catalog</h1>{top_links("catalog.html")}</div>
<p class="count">Every work in the Perseus canonical Greek and Latin repositories. To add one to your shelf, run the
command shown next to it.</p>
<div class="filters"><input id="q" type="search" placeholder="Search author or title (accents optional)" autofocus>
<label><input type="checkbox" id="eng"> with English</label>
<label><input type="checkbox" id="shelf"> on my shelf</label></div>
<p class="count" id="n"></p>
<table class="cat"><thead><tr><th>Author</th><th>Title</th><th>Languages</th><th>To add</th></tr></thead>
<tbody id="rows"></tbody></table>
</main>"""
    page = html_page("Catalog", "index", main, ["catalog.js"], f"<script>window.CATALOG = {data};</script>")
    (site / "catalog.html").write_text(page, encoding="utf-8")


def write_report(site, report):
    lines = ["# Sync report", "",
             "Shared = numbers found on both sides, in an order both sides agree on.",
             "Coverage = shared / numbers in the translation. Below 90% is flagged.", "",
             "Approximate = a verse translation with its own line numbers, placed against the original",
             "proportionally between section starts and changes of speaker.", "",
             "| work | original | translation | shared | translation numbers | coverage | |",
             "|---|---|---|---|---|---|---|"]
    for wid, o, t, shared, cand, tk, approx in report:
        cov = shared / tk if tk else 0
        flag = "approximate" if approx else ("" if cov >= 0.9 else "CHECK")
        lines.append(f"| {wid} | {o} | {t} | {shared} | {tk} | {cov:.0%} | {flag} |")
    (site / "_sync.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
