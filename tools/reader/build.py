"""Build the static site from the library: one page per original/translation pairing,
an index of the shelf, a catalog page, and a sync report."""
import bisect
import hashlib
import html
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path

from . import edits as text_edits
from . import library, paths

ROOT = paths.ROOT
ORIGINAL = {"grc", "lat"}
LANG_NAMES = {"grc": "Greek", "lat": "Latin", "eng": "English", "it": "Italian", "fr": "French", "de": "German",
              "es": "Spanish", "pt": "Portuguese", "ru": "Russian", "zh": "Chinese", "ja": "Japanese", "el": "Greek"}
HTML_LANG = {"grc": "grc", "lat": "la", "eng": "en"}


def html_lang(code):
    return HTML_LANG.get(code, code or "en")


def is_original(meta):
    """Greek and Latin texts are originals. So is any other language that is not English and not marked
    as a translation (`original: it` in the front matter): Wikisource pairs such as Dante and Italian."""
    lang = meta.get("language")
    return lang in ORIGINAL or (lang not in (None, "", "eng") and not meta.get("original"))
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
    """Sections start at ## headings on the left; blocks start at speeches/paragraphs.
    Each chunk is (left, right, ...) with any number of right-hand sides."""
    sections = []
    cur_sec = {"title": None, "groups": []}
    group, glen = [], 0
    for ch in chunks:
        lch, rest = list(ch[0]), [list(r) for r in ch[1:]]
        lead = [e for e in lch[:4] if e[0] == "h2"]
        if lead:
            if group:
                cur_sec["groups"].append(group)
            if cur_sec["groups"] or cur_sec["title"]:
                sections.append(cur_sec)
            lch.remove(lead[0])
            rest = [[e for i, e in enumerate(r) if not (e[0] == "h2" and i < 4)] for r in rest]
            cur_sec = {"title": lead[0][1], "groups": []}
            group, glen = [], 0
        starts_block = bool(lch) and lch[0][0] in ("h3", "spk", "stage", "pb")
        if group and ((starts_block and glen >= GROUP_MIN) or glen >= GROUP_MAX):
            cur_sec["groups"].append(group)
            group, glen = [], 0
        group.append((lch, *rest))
        glen += text_len(lch)
    if group:
        cur_sec["groups"].append(group)
    if cur_sec["groups"] or cur_sec["title"]:
        sections.append(cur_sec)
    return sections


def chunk3(left, a, b):
    """Split the original and two translations at numbers all three share."""
    pa, _ = shared_keys(left, a)
    pb = {k: ri for _, ri, k in shared_keys(left, b)[0]}
    bounds = [(0, 0, 0)]
    for li, ra, k in pa:
        if k not in pb:
            continue
        rb = pb[k]
        if li <= bounds[-1][0] or ra <= bounds[-1][1] or rb <= bounds[-1][2]:
            continue
        lp = back_over_struct(left, li, bounds[-1][0])
        ap = back_over_struct(a, ra, bounds[-1][1])
        bp = back_over_struct(b, rb, bounds[-1][2])
        lp = li if lp <= bounds[-1][0] else lp
        ap = ra if ap <= bounds[-1][1] else ap
        bp = rb if bp <= bounds[-1][2] else bp
        bounds.append((lp, ap, bp))
    bounds.append((len(left), len(a), len(b)))
    return [(left[l0:l1], a[a0:a1], b[b0:b1]) for (l0, a0, b0), (l1, a1, b1) in zip(bounds, bounds[1:])]


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


CAST_TITLES = ("characters", "cast", "dramatis personae", "persons of the drama", "persons of the play")


def front_html(side, meta, cls, lang):
    """A side's ::: blocks: each folded under its title; a cast list is open and compact."""
    parts = []
    for i, (title, paras) in enumerate(meta.get("_front", []), 1):
        cast = re.sub(r"<[^>]+>", "", title).strip().lower() in CAST_TITLES
        body = "".join(f"<p>{side.fill_notes(p)}</p>" for p in paras)
        parts.append(f'<details class="fm{" cast" if cast else ""}" id="{side.prefix}fm{i}"'
                     f'{" open" if cast else ""}><summary>{title}</summary>{body}{side.notes_html(1)}</details>')
    return f'<div class="col {cls}" lang="{lang}">{"".join(parts)}</div>'


def front_section(cols, toc, three=False):
    """The block above the text, and its contents entries; cols: [(side, meta, cls, lang)]."""
    if not any(m.get("_front") for _, m, _, _ in cols):
        return ""
    for side, m, _, _ in cols:
        who = (m.get("edition") or "").split()
        for i, (title, _) in enumerate(m.get("_front", []), 1):
            toc.append(f'<li class="fm"><a href="#{side.prefix}fm{i}"><span class="t">{title}</span>'
                       f'<span class="r">{html.escape(who[-1] if who else "")}</span></a></li>')
    inner = "".join(front_html(s, m, c, l) for s, m, c, l in cols)
    kind = " three" if three else (" single" if len(cols) == 1 else "")
    return f'<section class="front"><div class="grp{kind}">{inner}</div></section>'


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
    cols = [(L, lmeta, f"g {L.layout}", html_lang(lmeta.get("language")))]
    if two:
        cols.append((R, rmeta, f"e {R.layout}", html_lang(rmeta.get("language"))))
    body.append(front_section(cols, toc))
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
        llang = html_lang(lmeta.get("language"))
        rlang = html_lang(rmeta.get("language"))
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


def fold_extra(lch, rch, inner):
    """Material only the translation has (an argument, a preface) is folded away."""
    if text_len(lch) == 0 and text_len(rch) > 600:
        first_text = next((i for i, e in enumerate(rch) if e[0] == "text"), len(rch))
        heads = [e[1] for e in rch[:first_text] if e[0] == "h3"]
        label = heads[-1].rstrip(".") if heads else "Translator’s introduction"
        return f'<details class="aside"><summary>{label}</summary>{inner}</details>'
    return inner


def render_compare(orig, ta, tb):
    """Original in the middle, one translation either side, synced on the numbers all share."""
    lmeta, levents, lnotes = orig
    sides = []
    for meta, events, notes in (ta, tb):
        if own_lineation(levents, events, lmeta, meta):
            events = remap_translation(levents, events)
        sides.append((meta, events, notes))
    sections = sections_and_groups(chunk3(levents, sides[0][1], sides[1][1]))
    L = Side("L", lmeta.get("layout", "prose"), lnotes)
    A = Side("E", sides[0][0].get("layout", "prose"), sides[0][2])
    B = Side("F", sides[1][0].get("layout", "prose"), sides[1][2])

    def lang(m):
        return html_lang(m.get("language"))

    body, toc = [], []
    body.append(front_section([(A, sides[0][0], f"e {A.layout}", lang(sides[0][0])),
                               (L, lmeta, f"g {L.layout}", lang(lmeta)),
                               (B, sides[1][0], f"e f {B.layout}", lang(sides[1][0]))], toc, three=True))
    for si, sec in enumerate(sections, 1):
        all_left = [e for g in sec["groups"] for ch in g for e in ch[0]]
        k0, k1 = first_key(all_left), last_key(all_left)
        rng = f"{last_part(k0)}–{last_part(k1)}" if k0 and k1 and k0 != k1 else (last_part(k0) if k0 else "")
        sid = f"s{si}"
        if sec["title"]:
            toc.append(f'<li><a href="#{sid}"><span class="t">{sec["title"]}</span>'
                       f'<span class="r">{html.escape(rng)}</span></a></li>')
        head = (f'<h2><span class="t">{sec["title"]}</span><span class="r">{html.escape(rng)}</span></h2>'
                if sec["title"] else "")
        groups = []
        for g in sec["groups"]:
            lc, ac, bc = [], [], []
            for r, (lch, ach, bch) in enumerate(g, 1):
                lc.append(f'<div class="ch" style="--r:{r}">{L.render(lch)}</div>')
                ac.append(f'<div class="ch" style="--r:{r}">{fold_extra(lch, ach, A.render(ach))}</div>')
                bc.append(f'<div class="ch" style="--r:{r}">{fold_extra(lch, bch, B.render(bch))}</div>')
            last = len(g) + 1
            groups.append(
                f'<div class="grp three">'
                f'<div class="col e {A.layout}" lang="{lang(sides[0][0])}">{"".join(ac)}{A.notes_html(last)}</div>'
                f'<div class="col g {L.layout}" lang="{lang(lmeta)}">{"".join(lc)}'
                f'{L.notes_html(last).replace(chr(34) + "notes" + chr(34), chr(34) + "notes left" + chr(34))}</div>'
                f'<div class="col e f {B.layout}" lang="{lang(sides[1][0])}">{"".join(bc)}{B.notes_html(last)}</div>'
                f'</div>')
        body.append(f'<section class="sec" id="{sid}">{head}{"".join(groups)}</section>')
    has_app = any(k.startswith("a") for k in lnotes)
    return "".join(body), toc, has_app


# ---- site --------------------------------------------------------------------------
def page_html(title, author, work_title, heads, toc, content, has_two, has_app, page_key, work_id,
              lang, depth=1, extra_tools="", heads_cls=None, sources=()):
    up = "../" * depth
    tools = [extra_tools] if extra_tools else []
    if has_two:
        tools.append('<div class="seg" role="group" aria-label="Alignment">'
                     '<button type="button" data-mode="speech">Blocks</button>'
                     '<button type="button" data-mode="tight">Lines</button></div>')
    if has_app:
        tools.append('<button type="button" class="tog" id="apptog" aria-pressed="false">Apparatus</button>')
    tools.append('<form class="jump"><label for="jump">Go to</label>'
                 '<input id="jump" autocomplete="off" placeholder="1.150"></form>')
    tools.append(f'<a class="icon-btn search" href="{up}search.html?work={html.escape(work_id)}" '
                 f'title="Search this text" aria-label="Search this text"><span class="lbl">Search</span>'
                 f'<svg class="ico" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" '
                 f'stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/>'
                 f'<path d="M15.5 15.5 21 21"/></svg></a>')
    tools.append('<button type="button" class="icon-btn" data-settings aria-expanded="false" '
                 'aria-controls="settings" title="Settings (,)">Settings</button>')
    toc_html = (f'<nav class="toc"><details open><summary>Contents</summary><ol>{"".join(toc)}</ol>'
                f'</details></nav>') if toc else ""
    layout_cls = "layout" if toc else "layout notoc"
    heads_cls = heads_cls or ("heads" if has_two else "heads one")
    # the text ids behind the columns: original, translation, second translation (compare)
    src_attrs = "".join(f' data-src-{k}="{html.escape(v)}"' for k, v in zip("gef", sources) if v)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script src="{up}settings.js"></script>
<link rel="stylesheet" href="{up}style.css">
</head>
<body data-page="{html.escape(page_key)}" data-title="{html.escape(work_title)}" data-author="{html.escape(author)}" data-root="{up}" data-lang="{lang}"{src_attrs}>
<header class="bar"><a class="home brand" href="{up}index.html" lang="grc" title="The Mandate of Fire">Θεσμὸς Πυρός</a><a class="home" href="{up}library.html">Library</a>
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


# ---- groups for authors with many works (corpus/catalog/groups.tsv) ----------------------
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


EDITS = None          # the edit rules used by the last build (for reporting unmatched ones)
STATE_DIR = paths.SITE_CACHE
CODE_FILES = ("style.css", "settings.js", "reader.js", "dict.js", "library.js", "local.js", "search.js")
IMAGE_FILES = ("beacon.jpg", "beacon-tall.jpg")


# ---- what is in the library, read cheaply ------------------------------------------------------
def fingerprint():
    """Changes whenever the code that makes the pages changes: then every page is made again."""
    h = hashlib.sha1()
    for n in ("build.py", "library.py", "edits.py"):
        h.update((Path(__file__).parent / n).read_bytes())
    return h.hexdigest()[:16]


def read_header(path):
    """(front matter as a dict, sha1 of the file) without parsing the text."""
    raw = path.read_bytes()
    head = raw[:20000].decode("utf-8", "replace")
    if head.startswith("---") and head.find("\n---", 3) < 0 and len(raw) > 20000:
        head = raw.decode("utf-8", "replace")
    meta = {}
    if head.startswith("---"):
        end = head.find("\n---", 3)
        for line in unicodedata.normalize("NFC", head[3:end]).strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta, hashlib.sha1(raw).hexdigest()


def scan(lib_dir, include_private=False):
    """works[work id] -> the files that make it up, with their front matter and a digest. library/private/ holds
    texts that may not be published (in copyright): they are only seen by the local pass."""
    works = defaultdict(list)
    for p in sorted(lib_dir.rglob("*.md")):
        if p.name.startswith(("_", ".")) or p.name.upper() == "README.MD":
            continue
        top = p.relative_to(lib_dir).parts[0]
        if top == "private" and not include_private:
            continue
        meta, digest = read_header(p)
        if not meta.get("work"):
            continue
        meta.setdefault("id", p.stem)
        meta["own"] = top == "own"
        works[meta["work"]].append({"path": p, "rel": p.relative_to(lib_dir).as_posix(), "meta": meta,
                                    "sha": digest, "private": top == "private"})
    return works


def split_docs(docs):
    """(originals, translations) of a work's files, as the page builder orders them."""
    originals = sorted([d for d in docs if is_original(d["meta"])], key=lambda d: d["meta"]["id"])
    translations = sorted([d for d in docs if not is_original(d["meta"])], key=lambda d: d["meta"]["id"])
    if not originals:            # a translation alone is shown as the main text
        originals, translations = translations[:1], translations[1:]
    return originals, translations


def plan_works(works, bases=None):
    """[(work id, files, page name, author, title)] in build order; page names are unique per author.
    `bases` pins the page name of works already built elsewhere (the local pass reuses the public names)."""
    plan, used = [], set()
    for wid, docs in sorted(works.items()):
        originals, _ = split_docs(docs)
        m0 = originals[0]["meta"]
        author, title = m0.get("author", ""), m0.get("title", wid)
        base = (bases or {}).get(wid) or slug(title)
        if not (bases or {}).get(wid) and f"{slug(author)}/{base}" in used:
            base = f"{slug(title)}-{slug(wid)}"
        used.add(f"{slug(author)}/{base}")
        plan.append((wid, docs, base, author, title))
    return plan


def work_key(fp, wid, base, docs):
    h = hashlib.sha1()
    for part in (fp, wid, base):
        h.update(part.encode("utf-8"))
    for d in sorted(docs, key=lambda d: d["rel"]):
        h.update(d["rel"].encode("utf-8"))
        h.update(d["sha"].encode("ascii"))
        for r in EDITS.for_id(d["meta"]["id"]):
            h.update(repr(r).encode("utf-8"))
    return h.hexdigest()


# ---- one work -> its pages, search data, index entry -------------------------------------------------------
def render_work(site, wid, docs, base):
    """Write every page of one work under `site`. Returns what the site needs to remember about it."""
    before = set(EDITS.used)
    parsed = []
    for d in docs:
        meta, events, notes = library.parse(d["path"], EDITS.apply)
        meta.setdefault("id", d["path"].stem)
        meta["own"] = d["meta"]["own"]
        parsed.append((meta, events, notes))
    originals = sorted([d for d in parsed if is_original(d[0])], key=lambda d: d[0]["id"])
    translations = sorted([d for d in parsed if not is_original(d[0])], key=lambda d: d[0]["id"])
    if not originals:
        originals, translations = translations[:1], translations[1:]
    m0 = originals[0][0]
    author, title = m0.get("author", ""), m0.get("title", wid)
    files, report = [], []

    def write(rel, text):
        out = site / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        files.append(rel)

    hrefs = {}
    compare = {}            # (a, b) -> the first original between translations a and b
    if len(translations) >= 2:
        for a in range(len(translations)):
            for b in range(len(translations)):
                if a != b:
                    compare[(a, b)] = f"{base}.compare-{a}-{b}.html"
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
            cmp_link = ""
            if compare:
                other = next(i for i in range(len(translations)) if i != ti)
                cmp_link = (f'<a class="icon-btn" href="{compare[(ti, other)]}" '
                            f'title="Two translations either side of the original">Compare</a>')
            page = page_html(f"{title} — {author}", author, title, lhead + rhead, toc, content,
                             t is not None, has_app, f"{slug(author)}/{href}", wid,
                             m0.get("language", ""), extra_tools=cmp_link,
                             sources=(o[0]["id"], t[0]["id"] if t else ""))
            write(f"{slug(author)}/{href}", page)
            if t is not None:
                tk = sum(1 for e in t[1] if key_of(e))
                report.append([wid, o[0]["id"], t[0]["id"], stats["shared"], stats["candidates"], tk,
                               stats["approx"]])
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
    for (a, b), href in compare.items():
        content, toc, has_app = render_compare(originals[0], translations[a], translations[b])
        ahead = edition_head(translations[a][0], [(x[0], compare.get((i, b), href))
                                                  for i, x in enumerate(translations) if i != b],
                             href, "Left translation")
        mhead = edition_head(originals[0][0], [], href, "Original edition")
        bhead = edition_head(translations[b][0], [(x[0], compare.get((a, i), href))
                                                  for i, x in enumerate(translations) if i != a],
                             href, "Right translation")
        back = (f'<a class="icon-btn" href="{hrefs[(0, a)]}" title="Back to one translation">'
                f'One translation</a><a class="icon-btn" href="{compare[(b, a)]}" '
                f'title="Swap the two translations">Swap sides</a>')
        page = page_html(f"{title} — {author} (compare)", author, title, ahead + mhead + bhead, toc,
                         content, True, has_app, f"{slug(author)}/{href}", wid, m0.get("language", ""),
                         extra_tools=back, heads_cls="heads three",
                         sources=(originals[0][0]["id"], translations[a][0]["id"], translations[b][0]["id"]))
        write(f"{slug(author)}/{href}", page)
    payload = {"work": wid, "author": author, "title": title, "parts": search_parts}
    write(f"search/{slug(wid)}.js", "SearchLoaded(" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n")
    entry = {
        "work": wid, "author": author, "title": title,
        "label": m0.get("label", ""), "href": f"{slug(author)}/{hrefs[(0, 0)]}",
        "translations": [d[0].get("edition") or d[0].get("label", "") for d in translations],
        "lang": m0.get("language", ""), "orig": m0.get("original") or m0.get("language", ""),
        "own": bool(m0.get("own")),
        "search": f"search/{slug(wid)}.js",
    }
    return {"files": files, "entry": entry, "base": base, "desc": m0.get("description", ""),
            "shelf": f"{slug(author)}/{hrefs[(0, 0)]}", "report": report,
            "used_rules": [list(r) for r in EDITS.used - before]}


# ---- the persistent site: only works that changed are made again --------------------------------------------
def load_state(name, fp):
    try:
        st = json.loads((STATE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        return st if st.get("fp") == fp else None
    except (OSError, ValueError):
        return None


def save_state(name, st):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / f"{name}.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def remove_files(site, files):
    for rel in files:
        p = site / rel
        try:
            p.unlink()
            if p.parent != site and not any(p.parent.iterdir()):
                p.parent.rmdir()
        except OSError:
            pass


def make_site(site, name, plan, fp, stats, keep=()):
    """Bring `site` up to date for `plan`; returns {work id: remembered result}. A cold start (no record, or the
    builder code changed) clears the folder first, except the names in `keep`."""
    state = load_state(name, fp)
    site.mkdir(parents=True, exist_ok=True)
    if state is None:
        for child in site.iterdir():
            if child.name not in keep:
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        state = {"fp": fp, "works": {}}
    results, wanted = {}, set()
    for wid, docs, base, author, title in plan:
        wanted.add(wid)
        key = work_key(fp, wid, base, docs)
        old = state["works"].get(wid)
        if old and old["key"] == key and all((site / f).exists() for f in old["files"]):
            for r in old["used_rules"]:
                EDITS.used.add(tuple(r))
            results[wid] = old
            stats["cached"] += 1
            continue
        res = render_work(site, wid, docs, base)
        res["key"] = key
        if old:
            remove_files(site, set(old["files"]) - set(res["files"]))
        state["works"][wid] = res
        results[wid] = res
        stats["made"] += 1
    for wid in [w for w in state["works"] if w not in wanted]:
        remove_files(site, state["works"][wid]["files"])
        del state["works"][wid]
        stats["removed"] += 1
    save_state(name, state)
    return results


def assemble(results, rules):
    """The index entries, share map and sync rows for the pages that are on a site."""
    entries, shelf, report = [], {}, []
    for wid in sorted(results):
        r = results[wid]
        e = dict(r["entry"])
        author_id = wid.split(".")[0] if not e["own"] else slug(e["author"])
        e["author_id"] = author_id
        e["group"] = group_of(rules, author_id, e["title"], r["desc"])
        entries.append(e)
        shelf[wid] = r["shelf"]
        report += [tuple(x) for x in r["report"]]
    # your own texts sit under the same author as the Perseus ones when the names agree
    ids = {e["author"]: e["author_id"] for e in entries if not e["own"]}
    for e in entries:
        if e["own"]:
            e["author_id"] = ids.get(e["author"], e["author_id"])
    return entries, shelf, report


def copy_assets(site, extra=()):
    """The site's code (site/code), images and fonts (assets/) into the built site."""
    site.mkdir(parents=True, exist_ok=True)
    for name in CODE_FILES + tuple(extra):
        shutil.copy(paths.SITE_CODE / name, site / name)
    for name in IMAGE_FILES:
        shutil.copy(paths.IMAGES / name, site / name)
    shutil.copytree(paths.FONTS, site / "fonts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("PPEditorialNew*"))      # a licensed font that is not published


def build(lib_dir, site, catalog=None, shelf_ids=(), public=False, local_site=None, stats=None):
    """The public site (`site`, what gets deployed) and, unless public=True, the local overlay (`local_site`):
    the catalog, the private texts, and the library and search pages that list them. The edit server serves the
    overlay first and `site` for everything else. Both are persistent: a page is only made again when the text it
    comes from, its edit rules, or the page code has changed."""
    global EDITS
    stats = stats if stats is not None else {}
    stats.update({"cached": 0, "made": 0, "removed": 0})
    fp = fingerprint()
    rules = load_groups(paths.GROUPS_TSV)
    EDITS = text_edits.Rules(lib_dir / "edits.tsv")

    # 1. the public site: every work, without library/private
    public_works = scan(lib_dir, include_private=False)
    pub = make_site(site, "public", plan_works(public_works), fp, stats, keep=("dict",))
    copy_assets(site)
    for stale in ("_local", "_private", "_sync.md", "catalog.html", "catalog.js"):     # from the older layout
        (site / stale).unlink(missing_ok=True)
    entries, shelf, report = assemble(pub, rules)
    write_landing(site, entries)
    write_local_page(site)
    write_library(site, entries, local=False)
    write_search_page(site, entries, local=False)
    (site / "shelf.js").write_text("window.SHELF = " + json.dumps(shelf, ensure_ascii=False) + ";\n", encoding="utf-8")
    if public or local_site is None:
        return entries, report

    # 2. the local overlay: works that have private files are made again with all their files; the rest is shared
    all_works = scan(lib_dir, include_private=True)
    touched = {w: d for w, d in all_works.items() if any(x["private"] for x in d)}
    bases = {w: r["base"] for w, r in pub.items()}
    plan = [p for p in plan_works(all_works, bases) if p[0] in touched]
    loc = make_site(local_site, "local", plan, fp, stats)
    merged = {w: r for w, r in pub.items() if w not in loc}
    merged.update(loc)
    entries, shelf, report = assemble(merged, rules)
    local_site.mkdir(parents=True, exist_ok=True)
    shutil.copy(paths.SITE_CODE / "catalog.js", local_site / "catalog.js")
    write_library(local_site, entries, local=True)
    write_search_page(local_site, entries, local=True)
    write_catalog(local_site, catalog, {e["work"] for e in entries})
    (local_site / "shelf.js").write_text("window.SHELF = " + json.dumps(shelf, ensure_ascii=False) + ";\n", encoding="utf-8")
    write_report(local_site, report)
    return entries, report


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


LOGO = ('<a class="logo" href="index.html" title="The Mandate of Fire" aria-label="The Mandate of Fire">'
        '<span class="logo-mark" lang="grc">ΘΠ</span></a>')


def top_links(current, local=False):
    links = [("library.html", "Library"), ("search.html", "Search texts")]
    if local:
        links.append(("catalog.html", "Catalog"))
    out = "".join(f'<a href="{h}">{t}</a>' for h, t in links if h != current)
    return (f'<nav class="links">{out}<button type="button" class="icon-btn" data-settings '
            f'aria-expanded="false" aria-controls="settings">Settings</button></nav>')


def write_library(site, entries, local=False):
    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    n = len(entries)
    main = f"""<main class="lib">
<div class="lib-top">{LOGO}<h1>Library</h1>{top_links("library.html", local)}</div>
<p class="count">{n} work{"s" if n != 1 else ""}</p>
<section id="continue-wrap" hidden><h3 class="label">Continue reading</h3><div class="continue" id="continue"></div></section>
<div class="finder"><input type="search" id="find" placeholder="Find a work or author (accents optional)" aria-label="Find a work or author">
<div class="chips" id="langs" role="group" aria-label="Language">
<button type="button" data-l="all" aria-pressed="true">All</button><button type="button" data-l="grc" aria-pressed="false">Greek</button><button type="button" data-l="lat" aria-pressed="false">Latin</button></div></div>
<div class="shelf"><nav class="authors" id="authors" aria-label="Authors"></nav><section class="works" id="works" aria-live="polite"></section></div>
<noscript><p>The library list needs JavaScript.</p></noscript>
</main>"""
    (site / "library.html").write_text(
        html_page("Library", "index", main, ["library.js", "local.js"], f"<script>window.LIBRARY = {data};</script>"),
        encoding="utf-8")


def write_local_page(site):
    """local.html: the reader shell for a text kept on this device; local.js fills it in."""
    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>On this device</title>
<script src="settings.js"></script>
<link rel="stylesheet" href="style.css">
</head>
<body class="local-page" data-root="">
<header class="bar"><a class="home brand" href="index.html" lang="grc" title="The Mandate of Fire">Θεσμὸς Πυρός</a><a class="home" href="library.html">Library</a>
<div class="title"><span class="au"></span> <span class="wk"></span></div>
<div class="tools"></div></header>
<div class="layout notoc"><main><p class="empty">Opening…</p></main></div>
<script src="local.js"></script>
</body>
</html>
"""
    (site / "local.html").write_text(page, encoding="utf-8")


# the Greek title is sized so that it spans exactly the width of "The Mandate of Fire"
LANDING_FIT = """<script>
(function () {
  var sub = document.querySelector(".landing .sub span"), h = document.querySelector(".landing h1");
  var g = h.querySelector("span");
  function fit() {
    h.style.fontSize = "100px";
    var w = g.getBoundingClientRect().width, target = sub.getBoundingClientRect().width;
    if (w) h.style.fontSize = (100 * target / w) + "px";
  }
  fit();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  window.addEventListener("resize", fit);
})();
</script>"""


def write_landing(site, entries):
    main = """<main class="landing">
<div class="art" aria-hidden="true"><picture><source media="(orientation: portrait)" srcset="beacon-tall.jpg"><img src="beacon.jpg" alt=""></picture></div>
<div class="veil" aria-hidden="true"></div>
<p class="land-credit">J. M. W. Turner, <i>The Beacon Light</i></p>
<nav class="land-top"><a href="library.html">Library</a>
<button type="button" class="icon-btn" data-settings aria-expanded="false" aria-controls="settings">Settings</button></nav>
<section class="hero">
<p class="sub"><span>The Mandate of Fire</span></p>
<h1 lang="grc" title="Θεσμὸς Πυρός"><span>ΘΕΣΜΟΣ ΠΥΡΟΣ</span></h1>
</section>
</main>"""
    (site / "index.html").write_text(
        html_page("Θεσμὸς Πυρός — The Mandate of Fire", "landing", main, [], LANDING_FIT), encoding="utf-8")


def write_search_page(site, entries, local=False):
    works = [{"work": e["work"], "author": e["author"], "author_id": e["author_id"], "title": e["title"],
              "lang": e["lang"], "search": e["search"]} for e in entries]
    data = json.dumps(works, ensure_ascii=False, separators=(",", ":"))
    main = f"""<main class="lib">
<div class="lib-top">{LOGO}<h1>Search</h1>{top_links("search.html", local)}</div>
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


def catalog_rows(catalog, on_shelf):
    """One row per work in any public-domain repository we list: Perseus (corpus/catalog/catalog.json) and
    Wikisource pairs (corpus/catalog/wikisource.json, made by tools/wikisource_catalog.py).
    [id, author, title, original title, languages, English editions, on shelf, source]"""
    rows = []
    for w in (catalog or {}).get("works", []):
        langs = sorted({e["lang"] for e in w["editions"]})
        orig = next((e["label"] for e in w["editions"] if e["lang"] in ORIGINAL), "")
        trans = [e["description"] for e in w["editions"] if e["lang"] == "eng"]
        rows.append([w["id"], catalog["authors"].get(w["author"], w["author"]), w["title"], orig,
                     "+".join(langs), len(trans), 1 if w["id"] in on_shelf else 0, "perseus"])
    ws = paths.WIKISOURCE_JSON
    if ws.exists():
        for w in json.loads(ws.read_text(encoding="utf-8"))["works"]:
            work = w["id"].rsplit(".", 1)[0]
            rows.append([w["id"], "", w["en_title"], w["orig_title"], "eng+" + w["lang"], 1,
                         1 if work in on_shelf else 0, "wikisource"])
    return rows


SOURCES = [["perseus", "Perseus Digital Library"], ["wikisource", "Wikisource"]]


def write_catalog(site, catalog, on_shelf):
    rows = catalog_rows(catalog, on_shelf)
    if not rows:
        return
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    main = f"""<main class="lib wide">
<div class="lib-top">{LOGO}<h1 class="long">Works in public domain repositories</h1>{top_links("catalog.html", True)}</div>
<p class="count">Perseus and Wikisource so far; more repositories can be added to this list. Press Add and the work is
downloaded into your library. A Wikisource row adds the original; use <i>translations</i> to find the English page you want, then
<i>+ translation</i> and paste its address. (Add works only when this page is served by <code>python perseus.py edit</code>;
this catalog is not part of the public site.)</p>
<section class="local" id="local" hidden><h3 class="label">On this device</h3>
<div class="local-row"><span id="local-status"></span>
<button type="button" class="icon-btn" id="local-link">Link a folder</button>
<label class="icon-btn">Add .md files<input type="file" id="local-files" accept=".md,.markdown,.txt,text/markdown" multiple hidden></label></div>
<p class="local-note">Your own texts, in the <a href="https://github.com/gmleuning/neoperseus/blob/main/SPEC.md">library format</a>, read in this browser only and never uploaded. You can also drop .md files anywhere on this page.</p></section>
<div class="filters"><input id="q" type="search" placeholder="Search author or title (accents optional)" autofocus>
<label>Repository <select id="src"><option value="">All</option>{"".join(f'<option value="{k}">{html.escape(v)}</option>' for k, v in SOURCES)}</select></label>
<label><input type="checkbox" id="eng"> with English</label>
<label><input type="checkbox" id="shelf"> hide works on my shelf</label></div>
<p class="count" id="n"></p>
<table class="cat"><thead><tr><th>Author</th><th>Title</th><th>Languages</th><th>Repository</th><th></th></tr></thead>
<tbody id="rows"></tbody></table>
</main>"""
    page = html_page("Catalog", "index", main, ["catalog.js", "local.js"], f"<script>window.CATALOG = {data};</script>")
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
