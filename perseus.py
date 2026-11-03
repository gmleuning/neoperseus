"""Library reader: one command for everything.

    python perseus.py add tlg0006.tlg012      add a work (or an author id: tlg0059 = all of Plato) to the shelf, then update
    python perseus.py remove tlg0006.tlg012   take it off the shelf (its downloaded and converted files are deleted)
    python perseus.py update                  fetch anything missing, convert, and rebuild the site
    python perseus.py build                   rebuild the site only (after editing your own texts)
    python perseus.py find euripides          search the catalog from the command line
    python perseus.py import-wikisource FILE.epub --work ID [--lang grc] [--author A] [--title T]

The site is written to site/; open site/index.html.
"""
import argparse
import shutil
import sys
from pathlib import Path

from reader import build as builder
from reader import perseus

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
LIBRARY = ROOT / "library"


def cmd_update(args, force=False):
    catalog = perseus.load_catalog()
    works, missing = perseus.shelf_works(catalog)
    for m in missing:
        print(f"  not in the catalog: {m}")
    n = perseus.fetch(catalog, works)
    print(f"fetched {n} file(s)")
    done, failed = perseus.convert(catalog, works, force=force or getattr(args, "force", False))
    print(f"converted {done} file(s)" + (f", {len(failed)} failed" if failed else ""))
    cmd_build(args, catalog)


def cmd_build(args, catalog=None):
    catalog = catalog or perseus.load_catalog()
    entries, report = builder.build(LIBRARY, SITE, catalog)
    flagged = [r for r in report if r[5] and r[3] / r[5] < 0.9]
    print(f"built {len(entries)} work(s) into {SITE}")
    for wid, o, t, shared, cand, tk in flagged:
        print(f"  check sync: {o} / {t}: {shared} of {tk} translation numbers matched")
    print(f"open {SITE / 'index.html'}")


def edit_shelf(add=(), remove=()):
    lines = perseus.SHELF.read_text(encoding="utf-8").splitlines() if perseus.SHELF.exists() else []
    present = {l.split("#", 1)[0].strip() for l in lines}
    for a in add:
        if a not in present:
            lines.append(a)
    lines = [l for l in lines if l.split("#", 1)[0].strip() not in set(remove)]
    perseus.SHELF.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_add(args):
    catalog = perseus.load_catalog()
    works, missing = perseus.shelf_works(catalog, args.ids)
    if missing:
        sys.exit("not in the catalog: " + ", ".join(missing) + "  (try: python perseus.py find NAME)")
    edit_shelf(add=args.ids)
    for w in works:
        print(f"  + {w['id']}  {catalog['authors'].get(w['author'], '')}, {w['title']}")
    cmd_update(args)


def cmd_remove(args):
    edit_shelf(remove=args.ids)
    catalog = perseus.load_catalog()
    works, _ = perseus.shelf_works(catalog, args.ids)
    for w in works:
        shutil.rmtree(perseus.LIBRARY / w["id"], ignore_errors=True)
        for ed in w["editions"]:
            p = perseus.local_path(w, ed)
            if p.exists():
                p.unlink()
        print(f"  - {w['id']}")
    if SITE.exists():
        shutil.rmtree(SITE)
    cmd_build(args, catalog)


def cmd_find(args):
    import unicodedata

    def fold(s):
        s = unicodedata.normalize("NFD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    catalog = perseus.load_catalog()
    words = [fold(w) for w in args.words]
    for w in catalog["works"]:
        author = catalog["authors"].get(w["author"], w["author"])
        labels = " ".join(e["label"] for e in w["editions"])
        hay = fold(f"{w['id']} {author} {w['title']} {labels}")
        if all(x in hay for x in words):
            langs = "+".join(sorted({e["lang"] for e in w["editions"]}))
            print(f"{w['id']:<22} {author}, {w['title']}  [{langs}]")


def cmd_import_wikisource(args):
    from reader import wikisource
    out = wikisource.import_epub(Path(args.file), work=args.work, lang=args.lang,
                                 author=args.author, title=args.title, dest=LIBRARY / "own")
    print(f"wrote {out}")
    print("edit it if needed, then run: python perseus.py build")


def main():
    for stream in (sys.stdout, sys.stderr):      # Windows consoles: never fail on Greek
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("remove"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("update"); p.add_argument("--force", action="store_true",
                                                 help="reconvert everything"); p.set_defaults(fn=cmd_update)
    p = sub.add_parser("build"); p.set_defaults(fn=cmd_build)
    p = sub.add_parser("find"); p.add_argument("words", nargs="+"); p.set_defaults(fn=cmd_find)
    p = sub.add_parser("import-wikisource")
    p.add_argument("file"); p.add_argument("--work", required=True)
    p.add_argument("--lang", default="eng"); p.add_argument("--author", default="")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_import_wikisource)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
