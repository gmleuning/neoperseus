"""Build corpus/catalog/sources/wikisource.json: Wikisource works that exist in English and in another language.

It reads the translation hub pages on English Wikisource (Category:Translations_pages) and
asks the MediaWiki API for their interwiki language links, so each row pairs an English page
with a page on another Wikisource (grc, la, it, fr ...). The catalog page lists these rows next
to the Perseus works; "Add" there downloads both pages as EPUBs and imports them
(tools/reader/wikisource_fetch.py).

    python tools/wikisource_catalog.py                  # the default languages
    python tools/wikisource_catalog.py --langs el la it fr de
    python tools/wikisource_catalog.py --all-langs      # every language (many thousands of rows)

It takes a few minutes (about 35 polite requests) and can be re-run at any time.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from reader import paths

ROOT = paths.ROOT
OUT = paths.WIKISOURCE_JSON
API = "https://en.wikisource.org/w/api.php"
AGENT = "neoperseus-catalog/1.0 (personal reader; one-off catalog build)"
DEFAULT_LANGS = ["grc", "el", "la", "it", "fr", "de", "es", "pt", "ru", "zh", "ja"]


def get(params, tries=6):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
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


def hub_titles(delay):
    titles, cont = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": "Category:Translations_pages",
             "cmnamespace": "0", "cmlimit": "500"}
        if cont:
            p["cmcontinue"] = cont
        d = get(p)
        titles += [m["title"] for m in d["query"]["categorymembers"]]
        cont = d.get("continue", {}).get("cmcontinue")
        if not cont:
            return titles
        time.sleep(delay)


def langlinks(batch, delay):
    rows, cont = [], None
    while True:
        p = {"action": "query", "titles": "|".join(batch), "prop": "langlinks|info", "inprop": "url",
             "llprop": "url", "lllimit": "500"}
        if cont:
            p["llcontinue"] = cont
        d = get(p)
        for page in d.get("query", {}).get("pages", {}).values():
            for ll in page.get("langlinks", []):
                rows.append({"en_title": page["title"], "en_url": page.get("fullurl", ""),
                             "lang": ll.get("lang", ""), "orig_title": ll.get("*", ""), "orig_url": ll.get("url", "")})
        cont = d.get("continue", {}).get("llcontinue")
        if not cont:
            return rows
        time.sleep(delay)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", nargs="*", default=DEFAULT_LANGS)
    ap.add_argument("--all-langs", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N hub pages (testing)")
    ap.add_argument("--delay", type=float, default=0.8)
    args = ap.parse_args()
    keep = None if args.all_langs else set(args.langs)
    titles = hub_titles(args.delay)
    if args.limit:
        titles = titles[:args.limit]
    print(f"{len(titles)} hub pages", file=sys.stderr)
    rows = []
    for i in range(0, len(titles), 50):
        rows += [r for r in langlinks(titles[i:i + 50], args.delay) if keep is None or r["lang"] in keep]
        print(f"  {min(i + 50, len(titles))}/{len(titles)}: {len(rows)} pairs", file=sys.stderr)
        time.sleep(args.delay)
    seen, works = set(), []
    for r in sorted(rows, key=lambda r: (r["lang"], r["en_title"])):
        wid = f"ws.{slug(r['en_title'])}.{r['lang']}"
        if wid in seen:
            continue
        seen.add(wid)
        works.append({"id": wid, **r})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"generated": date.today().isoformat(), "works": works},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(works)} pairs to {OUT}")


if __name__ == "__main__":
    main()
