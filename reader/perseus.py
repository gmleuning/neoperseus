"""Fetch Perseus texts listed on the shelf and convert them to library Markdown."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from . import tei

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "catalog.json"
CORPUS = ROOT / "corpus"
LIBRARY = ROOT / "library" / "perseus"
SHELF = ROOT / "shelf.txt"
LANGS = {"grc", "lat", "eng"}


def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def read_shelf():
    """Entries are work ids (tlg0006.tlg012) or author ids (tlg0059 = everything by Plato).
    Anything after # is a comment."""
    if not SHELF.exists():
        return []
    out = []
    for line in SHELF.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.split()[0])
    return out


def shelf_works(catalog, entries=None):
    entries = read_shelf() if entries is None else entries
    works, missing = [], []
    for e in entries:
        hits = [w for w in catalog["works"] if w["id"] == e or w["author"] == e]
        if not hits:
            missing.append(e)
        works.extend(h for h in hits if h not in works)
    return works, missing


def short_author(name):
    """'Cicero, Marcus Tullius' -> 'Cicero'; 'Pliny, the Elder' -> 'Pliny the Elder';
    'Titus Livius (Livy)' -> 'Livy'."""
    m = re.search(r"\(([^)]+)\)\s*$", name)
    if m:
        return m.group(1).strip()
    if "," not in name:
        return name
    head, rest = [x.strip() for x in name.split(",", 1)]
    return f"{head} {rest}" if rest.lower().startswith("the ") else head


def local_path(work, ed):
    return CORPUS / work["repo"] / ed["path"]


def download(url, dest, tries=4):
    """Download to a temporary file and rename it into place, so an interrupted download
    never leaves a half file behind. Retries with a growing pause."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    block = r.read(1 << 20)
                    if not block:
                        break
                    f.write(block)
            tmp.replace(dest)
            return True
        except Exception as e:                       # network trouble: wait and retry
            if attempt == tries:
                print(f"  could not download {url}: {e}", file=sys.stderr)
                tmp.unlink(missing_ok=True)
                return False
            time.sleep(2 ** attempt)


def fetch(catalog, works, force=False):
    got, failed = 0, 0
    for w in works:
        src = catalog["sources"][w["repo"]]
        for ed in w["editions"]:
            if ed["lang"] not in LANGS:
                continue
            dest = local_path(w, ed)
            if dest.exists() and not force:
                continue
            url = f"https://raw.githubusercontent.com/{src['repo']}/{src['commit']}/{ed['path']}"
            print(f"  fetch {w['id']} {ed['id']}")
            if download(url, dest):
                got += 1
            else:
                failed += 1
    if failed:
        print(f"  {failed} file(s) could not be downloaded; run the same command again to retry them")
    return got


def frontmatter(meta):
    lines = ["---"]
    for k, v in meta.items():
        if v not in (None, ""):
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def convert(catalog, works, force=False):
    done, failed = 0, []
    for w in works:
        author = short_author(catalog["authors"].get(w["author"], w["author"]))
        for ed in w["editions"]:
            if ed["lang"] not in LANGS:
                continue
            src = local_path(w, ed)
            if not src.exists():
                continue
            dest = LIBRARY / w["id"] / f"{w['id']}.{ed['id']}.md"
            if dest.exists() and not force and dest.stat().st_mtime > src.stat().st_mtime:
                continue
            try:
                layout, body = tei.convert(src, ed["lang"])
            except Exception as e:          # report and carry on with the rest
                failed.append((w["id"], ed["id"], repr(e)))
                continue
            meta = {
                "id": f"{w['id']}.{ed['id']}",
                "work": w["id"],
                "author": author,
                "title": w["title"],
                "label": ed["label"],
                "edition": tei.person_from_description(ed["description"], ed["kind"]),
                "description": ed["description"],
                "language": ed["lang"],
                "layout": layout,
                "source": f"PerseusDL/canonical-{w['repo']}/{ed['path']}",
            }
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(frontmatter(meta) + body, encoding="utf-8")
            done += 1
    for wid, eid, err in failed:
        print(f"  FAILED {wid} {eid}: {err}", file=sys.stderr)
    return done, failed
