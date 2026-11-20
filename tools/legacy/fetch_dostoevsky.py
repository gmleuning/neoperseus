#!/usr/bin/env python3
"""
Discover all works by Fyodor Dostoevsky on en.wikisource.org and ru.wikisource.org
that have both an English translation and a Russian original, download them, and
format them as paired Markdown files according to SPEC.md.

Usage:
    python3 fetch_dostoevsky.py --out-dir library/own
    python3 fetch_dostoevsky.py --delay 1.5 --limit 5 --out-dir library/own
    python3 fetch_dostoevsky.py --list-only
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "DostoevskyLibraryFetcher/1.0 (https://en.wikisource.org; educational script)"
EN_AUTHOR_PAGE = "Author:Fyodor Mikhailovich Dostoevsky"
RU_AUTHOR_PAGE = "Автор:Фёдор Михайлович Достоевский"


def http_get_json(url: str, params: dict[str, str], max_retries: int = 6) -> Any:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait_s = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 5.0 * (2**attempt))
                print(f"HTTP {exc.code}; waiting {wait_s:.1f}s before retry ({attempt + 1}/{max_retries})...", file=sys.stderr)
                time.sleep(wait_s)
                continue
            raise
    raise RuntimeError(f"Failed request: {full_url}")


def api_url(lang: str) -> str:
    return f"https://{lang}.wikisource.org/w/api.php"


def fetch_author_links(lang: str, page: str, delay: float) -> list[str]:
    data = http_get_json(
        api_url(lang),
        {"action": "parse", "page": page, "prop": "links", "format": "json", "redirects": "1"},
    )
    time.sleep(delay)
    links = data.get("parse", {}).get("links", [])
    return [lk["*"] for lk in links if lk.get("ns", 0) == 0 and "exists" in lk]


def resolve_en_to_ru_pairs(en_titles: list[str], delay: float) -> list[dict[str, str]]:
    """Batch-resolve en.wikisource titles that have a ru.wikisource langlink."""
    pairs: list[dict[str, str]] = []
    batch_size = 50
    for i in range(0, len(en_titles), batch_size):
        batch = en_titles[i : i + batch_size]
        data = http_get_json(
            api_url("en"),
            {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "langlinks|info|categories",
                "inprop": "url",
                "lllang": "ru",
                "llprop": "url",
                "cllimit": "500",
                "format": "json",
                "redirects": "1",
            },
        )
        for page in data.get("query", {}).get("pages", {}).values():
            if "missing" in page:
                continue
            lls = page.get("langlinks", [])
            if not lls:
                continue
            cats = {c["title"] for c in page.get("categories", [])}
            if any("Incomplete" in c or "Works to be transcribed" in c for c in cats):
                continue
            ru_ll = lls[0]
            pairs.append(
                {
                    "en_title": page["title"],
                    "en_url": page.get("fullurl", ""),
                    "ru_title": ru_ll.get("*", ""),
                    "ru_url": ru_ll.get("url", ""),
                    "is_hub": "Category:Translations pages" in cats,
                }
            )
        time.sleep(delay)
    return pairs


def resolve_hub_edition(en_hub_title: str, delay: float) -> tuple[str, str]:
    """If an en.wikisource page is a Translations hub, pick the first listed translation subpage/edition."""
    data = http_get_json(
        api_url("en"),
        {"action": "parse", "page": en_hub_title, "prop": "text|links", "format": "json", "redirects": "1"},
    )
    time.sleep(delay)
    links = [
        lk["*"]
        for lk in data.get("parse", {}).get("links", [])
        if lk.get("ns", 0) == 0 and "exists" in lk and not lk["*"].startswith("Author:")
    ]
    # Prefer Garnett / Hogarth / Martin / named editions
    for candidate in links:
        if any(name in candidate for name in ("Garnett", "Hogarth", "Martin", "Whishaw", "Translation:")):
            return candidate, f"https://en.wikisource.org/wiki/{urllib.parse.quote(candidate.replace(' ', '_'))}"
    if links:
        return links[0], f"https://en.wikisource.org/wiki/{urllib.parse.quote(links[0].replace(' ', '_'))}"
    return en_hub_title, f"https://en.wikisource.org/wiki/{urllib.parse.quote(en_hub_title.replace(' ', '_'))}"


def list_subpages(lang: str, root_title: str, delay: float) -> list[str]:
    """List existing subpages under `<root_title>/` in namespace 0."""
    prefix = f"{root_title}/"
    subpages: list[str] = []
    apcontinue: str | None = None
    while True:
        params: dict[str, str] = {
            "action": "query",
            "list": "allpages",
            "apprefix": prefix,
            "apnamespace": "0",
            "aplimit": "500",
            "format": "json",
        }
        if apcontinue:
            params["apcontinue"] = apcontinue
        data = http_get_json(api_url(lang), params)
        for p in data.get("query", {}).get("allpages", []):
            title = p["title"]
            # Skip notes, illustrations, or frontmatter-only subpages
            tail = title[len(prefix) :].lower()
            if any(skip in tail for skip in ("notes", "illustrations", "cover", "title page", "contents")):
                continue
            subpages.append(title)
        apcontinue = data.get("continue", {}).get("apcontinue")
        if not apcontinue:
            break
        time.sleep(delay)
    return natural_sort_titles(subpages)


def natural_sort_titles(titles: list[str]) -> list[str]:
    def key_fn(s: str) -> list[Any]:
        return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", s)]

    return sorted(titles, key=key_fn)


def strip_html_tags(fragment: str) -> str:
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", "", fragment, flags=re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.replace("\u200b", "").replace("\xa0", " ")


def fetch_page_paragraphs(lang: str, title: str, delay: float) -> list[str]:
    data = http_get_json(
        api_url(lang),
        {"action": "parse", "page": title, "prop": "text", "format": "json", "redirects": "1"},
    )
    time.sleep(delay)
    raw_html = data.get("parse", {}).get("text", {}).get("*", "")
    cleaned = re.sub(r"<table\b[^>]*>.*?</table>", "", raw_html, flags=re.DOTALL)
    cleaned = re.sub(
        r'<div[^>]*class="[^"]*(?:ws-noexport|headertemplate|footertemplate|mw-editsection|license)[^"]*"[^>]*>.*?</div>',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    paras: list[str] = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", cleaned, flags=re.DOTALL):
        txt = re.sub(r"\s+", " ", strip_html_tags(p)).strip()
        if not txt or txt.startswith("↑"):
            continue
        if txt.startswith(("This work is a translation", "Original:", "Translation:", "Это произведение")):
            break
        paras.append(txt)
    return paras


def build_body_from_pages(lang: str, root_title: str, subpages: list[str], delay: float) -> tuple[str, int]:
    """Build SPEC.md prose body. Uses chapter/section keys when subpages exist, else paragraph keys."""
    if subpages:
        lines: list[str] = []
        key_idx = 0
        for sp in subpages:
            paras = fetch_page_paragraphs(lang, sp, delay=delay)
            if not paras:
                continue
            key_idx += 1
            heading = sp.split("/", 1)[1].replace("/", " — ")
            lines.append(f"## {heading}")
            lines.append("")
            paras[0] = f"{{{{{key_idx}}}}} {paras[0]}"
            for p in paras:
                lines.append(p)
                lines.append("")
        return "\n".join(lines), key_idx

    paras = fetch_page_paragraphs(lang, root_title, delay=delay)
    lines = [f"## {root_title}", ""]
    for idx, p in enumerate(paras, start=1):
        lines.append(f"{{{{{idx}}}}} {p}")
        lines.append("")
    return "\n".join(lines), len(paras)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "work"


def format_frontmatter(meta: dict[str, str]) -> str:
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gather and format matching Dostoevsky works from Wikisource.")
    parser.add_argument("--out-dir", type=Path, default=Path("library/own"), help="Output directory")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between API calls (default: 1.0)")
    parser.add_argument("--limit", type=int, default=None, help="Max number of works to download")
    parser.add_argument("--list-only", action="store_true", help="Only print discovered matching works")
    args = parser.parse_args()

    print("Fetching Dostoevsky work links from en.wikisource.org...", file=sys.stderr)
    en_links = fetch_author_links("en", EN_AUTHOR_PAGE, delay=args.delay)
    # Also verify ru author page is reachable for reference
    _ = fetch_author_links("ru", RU_AUTHOR_PAGE, delay=args.delay)

    pairs = resolve_en_to_ru_pairs(en_links, delay=args.delay)
    # Deduplicate by Russian title
    seen_ru: set[str] = set()
    unique_pairs: list[dict[str, Any]] = []
    for p in pairs:
        if p["ru_title"] not in seen_ru:
            seen_ru.add(p["ru_title"])
            unique_pairs.append(p)

    print(f"Discovered {len(unique_pairs)} matching Dostoevsky works with EN + RU pages.", file=sys.stderr)
    if args.limit:
        unique_pairs = unique_pairs[: args.limit]

    if args.list_only:
        for p in unique_pairs:
            print(f"{p['en_title']}  <->  {p['ru_title']}")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for item in unique_pairs:
        en_title = item["en_title"]
        en_url = item["en_url"]
        if item["is_hub"]:
            en_title, en_url = resolve_hub_edition(en_title, delay=args.delay)

        ru_title = item["ru_title"]
        ru_url = item["ru_url"]
        slug = f"dostoevsky-{slugify(item['en_title'])}"
        work_id = f"dostoevsky.{slugify(item['en_title']).replace('-', '_')}"

        print(f"Processing: {en_title} <-> {ru_title}", file=sys.stderr)
        en_subs = list_subpages("en", en_title, delay=args.delay)
        ru_subs = list_subpages("ru", ru_title, delay=args.delay)

        ru_body, ru_keys = build_body_from_pages("ru", ru_title, ru_subs, delay=args.delay)
        en_body, en_keys = build_body_from_pages("en", en_title, en_subs, delay=args.delay)

        if ru_keys == 0 or en_keys == 0:
            print(f"  Skipping {item['en_title']} (empty body: ru={ru_keys}, en={en_keys})", file=sys.stderr)
            continue

        ru_meta = {
            "id": f"{work_id}.ru",
            "work": work_id,
            "author": "Fyodor Mikhailovich Dostoevsky",
            "title": item["en_title"],
            "label": ru_title,
            "edition": "Wikisource",
            "language": "ru",
            "layout": "prose",
            "source": ru_url,
        }
        en_meta = {
            "id": f"{work_id}.en",
            "work": work_id,
            "author": "Fyodor Mikhailovich Dostoevsky",
            "title": item["en_title"],
            "label": ru_title,
            "edition": "Wikisource",
            "language": "en",
            "original": "ru",
            "layout": "prose",
            "source": en_url,
        }

        ru_path = args.out_dir / f"{slug}.ru.md"
        en_path = args.out_dir / f"{slug}.en.md"
        ru_path.write_text(f"{format_frontmatter(ru_meta)}\n\n{ru_body.strip()}\n", encoding="utf-8")
        en_path.write_text(f"{format_frontmatter(en_meta)}\n\n{en_body.strip()}\n", encoding="utf-8")
        print(f"  Wrote {ru_path} ({ru_keys} keys) & {en_path} ({en_keys} keys)")


if __name__ == "__main__":
    main()