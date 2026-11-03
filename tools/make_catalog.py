"""Build catalog/catalog.json from local checkouts of the Perseus canonical repos.

The catalog lists every work in PerseusDL/canonical-greekLit and canonical-latinLit:
author, title, and each edition or translation file that actually exists in the repo.
It is committed to this repository, so day-to-day use never needs these checkouts.

Only the small __cts__.xml metadata files have to be checked out. A cheap way to get them:

    git clone --filter=blob:none --no-checkout --depth 1 https://github.com/PerseusDL/canonical-greekLit.git
    cd canonical-greekLit
    git sparse-checkout set --no-cone "data/*/__cts__.xml" "data/*/*/__cts__.xml"
    git checkout

Usage:
    python tools/make_catalog.py path/to/canonical-greekLit path/to/canonical-latinLit
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
CTS = "{http://chs.harvard.edu/xmlns/cts}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
FILE_RE = re.compile(r"^data/([^/]+)/([^/]+)/([^/]+\.([a-z0-9-]+?)\.xml)$")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=True).stdout


def text_of(el, lang=None):
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def pick(parent, tag, prefer=("eng", "lat", "grc")):
    """The child <tag> in the preferred language, else the first one."""
    els = parent.findall(CTS + tag)
    for lang in prefer:
        for el in els:
            if el.get(XML_LANG) == lang:
                return text_of(el)
    return text_of(els[0]) if els else ""


def lang_of(edition_id):
    m = re.search(r"-([a-z]{3})\d*$", edition_id)
    return m.group(1) if m else ""


def read_repo(repo):
    repo = Path(repo)
    name = repo.name.replace("canonical-", "")
    commit = git(repo, "rev-parse", "HEAD").strip()
    files = {}
    for path in git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines():
        m = FILE_RE.match(path)
        if m:
            files.setdefault((m.group(1), m.group(2)), []).append((m.group(4), path))

    authors, works = {}, []
    for tg_file in sorted(repo.glob("data/*/__cts__.xml")):
        tg = tg_file.parent.name
        root = etree.parse(str(tg_file)).getroot()
        authors[tg] = pick(root, "groupname")
    for w_file in sorted(repo.glob("data/*/*/__cts__.xml")):
        tg, wk = w_file.parent.parent.name, w_file.parent.name
        root = etree.parse(str(w_file)).getroot()
        meta = {}
        for kind in ("edition", "translation", "commentary"):
            for el in root.findall(CTS + kind):
                eid = el.get("urn", "").rsplit(".", 1)[-1]
                meta[eid] = {
                    "kind": kind,
                    "label": pick(el, "label", ("grc", "lat", "eng")),
                    "description": pick(el, "description", ("eng", "mul", "lat")),
                }
        editions = []
        for eid, path in sorted(files.get((tg, wk), [])):
            m = meta.get(eid, {})
            lang = lang_of(eid)
            kind = m.get("kind") or ("translation" if lang not in ("grc", "lat") else "edition")
            editions.append({"id": eid, "lang": lang, "kind": kind,
                             "label": m.get("label", ""),
                             "description": m.get("description", ""), "path": path})
        if not editions:
            continue
        works.append({
            "id": f"{tg}.{wk}", "repo": name, "author": tg,
            "title": pick(root, "title"),
            "lang": root.get(XML_LANG, ""),
            "editions": editions,
        })
    return name, commit, authors, works


def main(repos):
    catalog = {"generated": date.today().isoformat(), "sources": {}, "authors": {}, "works": []}
    for repo in repos:
        name, commit, authors, works = read_repo(repo)
        catalog["sources"][name] = {"repo": f"PerseusDL/canonical-{name}", "commit": commit}
        catalog["authors"].update(authors)
        catalog["works"].extend(works)
    out = ROOT / "catalog" / "catalog.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    n_ed = sum(len(w["editions"]) for w in catalog["works"])
    print(f"{len(catalog['works'])} works, {n_ed} files, {len(catalog['authors'])} authors -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
