#!/usr/bin/env python3
"""
Build a catalog of works on Wikisource that have both an English page
and at least one non-English (original/other-language) Wikisource page.

Supports two discovery modes:
  1. wikisource (default): Walks `Category:Translations_pages` on en.wikisource.org
     via the MediaWiki API and resolves interwiki `langlinks`, with polite rate
     limiting and automatic HTTP 429 retry/backoff.
  2. sparql: Queries Wikidata's SPARQL endpoint for works with both an
     en.wikisource.org sitelink and another *.wikisource.org sitelink,
     optionally filtered by publication/inception year (e.g. 200..1900).

Usage:
    python3 list_wikisource_pairs.py --out wikisource_pairs.csv
    python3 list_wikisource_pairs.py --delay 1.5 --out wikisource_pairs.csv
    python3 list_wikisource_pairs.py --mode sparql --min-year 200 --max-year 1900 --out sparql_pairs.csv
    python3 list_wikisource_pairs.py --langs it fr ru zh la grc --format json --out pairs.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "WorldLitPairCataloger/1.1 (https://en.wikisource.org; educational script)"
EN_API = "https://en.wikisource.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def http_get_json(
    url: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 6,
) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait_s = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 5.0 * (2**attempt))
                print(
                    f"HTTP {exc.code} received; waiting {wait_s:.1f}s before retry ({attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(wait_s)
                continue
            raise


def fetch_translation_hub_titles(delay: float, limit: int | None = None) -> list[str]:
    """List page titles in Category:Translations_pages on en.wikisource.org."""
    titles: list[str] = []
    cmcontinue: str | None = None

    while True:
        params: dict[str, str] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Translations_pages",
            "cmnamespace": "0",
            "cmlimit": "500",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = http_get_json(EN_API, params)
        members = data.get("query", {}).get("categorymembers", [])
        for item in members:
            titles.append(item["title"])
            if limit and len(titles) >= limit:
                return titles

        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
        time.sleep(delay)

    return titles


def fetch_langlinks_batch(titles: list[str], delay: float) -> list[dict[str, Any]]:
    """Fetch interwiki langlinks and URLs for up to 50 en.wikisource.org titles."""
    rows: list[dict[str, Any]] = []
    llcontinue: str | None = None

    while True:
        params: dict[str, str] = {
            "action": "query",
            "titles": "|".join(titles),
            "prop": "langlinks|info",
            "inprop": "url",
            "llprop": "url",
            "lllimit": "500",
            "format": "json",
        }
        if llcontinue:
            params["llcontinue"] = llcontinue

        data = http_get_json(EN_API, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" in page:
                continue
            langlinks = page.get("langlinks", [])
            if not langlinks:
                continue
            en_url = page.get("fullurl", "")
            en_title = page.get("title", "")
            for ll in langlinks:
                rows.append(
                    {
                        "title": en_title,
                        "en_url": en_url,
                        "orig_lang": ll.get("lang", ""),
                        "orig_title": ll.get("*", ""),
                        "orig_url": ll.get("url", ""),
                        "year": "",
                        "wikidata_id": "",
                    }
                )

        llcontinue = data.get("continue", {}).get("llcontinue")
        if not llcontinue:
            break
        time.sleep(delay)

    return rows


def collect_via_wikisource(
    lang_filter: set[str] | None,
    limit: int | None,
    delay: float,
) -> list[dict[str, Any]]:
    titles = fetch_translation_hub_titles(delay=delay, limit=limit)
    batch_size = 50
    total_batches = (len(titles) + batch_size - 1) // batch_size
    print(
        f"Found {len(titles)} pages in Category:Translations_pages ({total_batches} batches). Resolving langlinks...",
        file=sys.stderr,
    )

    all_rows: list[dict[str, Any]] = []
    for idx, start in enumerate(range(0, len(titles), batch_size), start=1):
        batch = titles[start : start + batch_size]
        rows = fetch_langlinks_batch(batch, delay=delay)
        if lang_filter:
            rows = [r for r in rows if r["orig_lang"] in lang_filter]
        all_rows.extend(rows)
        if idx % 5 == 0 or idx == total_batches:
            print(f"  Processed batch {idx}/{total_batches} ({len(all_rows)} pairs so far)", file=sys.stderr)
        if idx < total_batches:
            time.sleep(delay)

    return all_rows


def collect_via_sparql(
    min_year: int | None,
    max_year: int | None,
    lang_filter: set[str] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    if min_year is not None or max_year is not None:
        filters = []
        if min_year is not None:
            filters.append(f"YEAR(?date) >= {min_year}")
        if max_year is not None:
            filters.append(f"YEAR(?date) <= {max_year}")
        year_clause = f"?work wdt:P577 ?date . FILTER({' && '.join(filters)})"
    else:
        year_clause = "OPTIONAL { ?work wdt:P577 ?date . }"

    lang_clause = ""
    if lang_filter:
        quoted = ", ".join(f'"{code}"' for code in sorted(lang_filter))
        lang_clause = f"FILTER(?origLang IN ({quoted}))"

    limit_clause = f"LIMIT {limit}" if limit else "LIMIT 2000"

    query = f"""
    SELECT ?work ?workLabel ?enUrl ?origUrl ?origLang (YEAR(?date) AS ?year) WHERE {{
      ?enUrl schema:about ?work ;
             schema:isPartOf <https://en.wikisource.org/> .
      ?origUrl schema:about ?work ;
               schema:isPartOf ?wiki ;
               schema:inLanguage ?origLang .
      FILTER(CONTAINS(STR(?wiki), ".wikisource.org/"))
      FILTER(?origLang != "en")
      {lang_clause}
      {year_clause}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    {limit_clause}
    """

    data = http_get_json(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
    )
    rows: list[dict[str, Any]] = []
    for binding in data.get("results", {}).get("bindings", []):
        rows.append(
            {
                "title": binding.get("workLabel", {}).get("value", ""),
                "en_url": binding.get("enUrl", {}).get("value", ""),
                "orig_lang": binding.get("origLang", {}).get("value", ""),
                "orig_title": "",
                "orig_url": binding.get("origUrl", {}).get("value", ""),
                "year": binding.get("year", {}).get("value", ""),
                "wikidata_id": binding.get("work", {}).get("value", "").rsplit("/", 1)[-1],
            }
        )
    return rows


def write_output(rows: list[dict[str, Any]], out_path: Path, fmt: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    fieldnames = ["title", "en_url", "orig_lang", "orig_title", "orig_url", "year", "wikidata_id"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalog matching English/original works on Wikisource.")
    parser.add_argument("--mode", choices=["wikisource", "sparql"], default="wikisource", help="Discovery source")
    parser.add_argument("--langs", nargs="*", default=None, help="Filter by original language codes (e.g. it fr ru zh)")
    parser.add_argument("--min-year", type=int, default=200, help="Minimum publication year (sparql mode)")
    parser.add_argument("--max-year", type=int, default=1900, help="Maximum publication year (sparql mode)")
    parser.add_argument("--limit", type=int, default=None, help="Max hub pages (wikisource) or rows (sparql)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between API requests (default: 1.0)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format")
    parser.add_argument("--out", type=Path, default=Path("wikisource_pairs.csv"), help="Output file path")
    args = parser.parse_args()

    lang_filter = set(args.langs) if args.langs else None
    if args.mode == "wikisource":
        rows = collect_via_wikisource(lang_filter=lang_filter, limit=args.limit, delay=args.delay)
    else:
        rows = collect_via_sparql(
            min_year=args.min_year,
            max_year=args.max_year,
            lang_filter=lang_filter,
            limit=args.limit,
        )

    rows.sort(key=lambda r: (r["orig_lang"], r["title"]))
    write_output(rows, args.out, args.format)
    print(f"Wrote {len(rows)} matching pairs to {args.out}")


if __name__ == "__main__":
    main()