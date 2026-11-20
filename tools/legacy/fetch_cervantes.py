#!/usr/bin/env python3
"""
Download and format Miguel de Cervantes Saavedra's works in Castilian and
public-domain English translations according to SPEC.md (without relying on
www.gutenberg.org):

  1. Don Quijote de la Mancha
     - Castilian: es.wikisource.org (Don Quijote de la Mancha)
     - English:   en.wikisource.org (Don Quixote, John Ormsby 1885)
  2. Los trabajos de Persiles y Sigismunda
     - Castilian: es.wikisource.org (1920 Editorial Calpe edition)
     - English:   Louisa Dorothea Stanley (1854, via mirrorservice / archive.org)

Usage:
    python3 fetch_cervantes.py --out-dir library/own
    python3 fetch_cervantes.py --delay 1.5 --out-dir library/own
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

USER_AGENT = "CervantesLibraryFetcher/2.0 (https://en.wikisource.org; educational script)"


def http_get_text(url: str, max_retries: int = 6, delay: float = 1.0) -> str:
    """Fetch UTF-8 text from URL with HTTP 429/5xx retry and backoff."""
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                try:
                    return raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    return raw.decode("latin-1")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait_s = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 5.0 * (2**attempt))
                print(f"HTTP {exc.code} on {url}; waiting {wait_s:.1f}s...", file=sys.stderr)
                time.sleep(wait_s)
                continue
            raise
    raise RuntimeError(f"Failed to fetch {url}")


def fetch_wikisource_parse(lang: str, page: str, prop: str = "text", delay: float = 1.0) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": page,
            "prop": prop,
            "format": "json",
            "redirects": "1",
        }
    )
    url = f"https://{lang}.wikisource.org/w/api.php?{params}"
    data: dict[str, Any] = json.loads(http_get_text(url, delay=delay))
    if "error" in data:
        raise RuntimeError(f"Wikisource API error for {lang}:{page}: {data['error']}")
    time.sleep(delay)
    return data["parse"]


def fetch_wikisource_html(lang: str, page: str, delay: float = 1.0) -> str:
    return fetch_wikisource_parse(lang, page, prop="text", delay=delay)["text"]["*"]


def fetch_wikisource_links(lang: str, page: str, delay: float = 1.0) -> list[str]:
    parsed = fetch_wikisource_parse(lang, page, prop="links", delay=delay)
    return [link["*"] for link in parsed.get("links", []) if link.get("ns", 0) == 0 and "exists" in link]


def roman_to_int(token: str) -> int | None:
    token = token.strip().upper().rstrip(".")
    special = {"PRIMERO": 1, "I": 1, "SEGUNDO": 2, "TERCERO": 3, "CUARTO": 4}
    if token in special:
        return special[token]
    if token.isdigit():
        return int(token)
    if not re.fullmatch(r"[IVXLCDM]+", token):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(token):
        val = values[ch]
        total = total - val if val < prev else total + val
        prev = val
    return total


def strip_html_tags(fragment: str) -> str:
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", "", fragment, flags=re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.replace("\u200b", "").replace("\xa0", " ")


def extract_wikisource_paragraphs(raw_html: str) -> list[str]:
    """Extract clean body paragraphs from a Wikisource chapter HTML fragment."""
    cleaned = re.sub(r"<table\b[^>]*>.*?</table>", "", raw_html, flags=re.DOTALL)
    cleaned = re.sub(r'<div[^>]*class="[^"]*(?:ws-noexport|headertemplate|footertemplate|mw-editsection)[^"]*"[^>]*>.*?</div>', "", cleaned, flags=re.DOTALL)
    paras: list[str] = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", cleaned, flags=re.DOTALL):
        txt = re.sub(r"\s+", " ", strip_html_tags(p)).strip()
        if not txt or txt.startswith("↑"):
            continue
        if txt.startswith("This work is a translation") or txt.startswith("Original:") or txt.startswith("Translation:"):
            break
        paras.append(txt)
    return paras


def format_frontmatter(meta: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def write_pair(
    out_dir: Path,
    slug: str,
    orig_meta: dict[str, str],
    orig_body: str,
    trans_meta: dict[str, str],
    trans_body: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    orig_path = out_dir / f"{slug}.{orig_meta['language']}.md"
    trans_path = out_dir / f"{slug}.{trans_meta['language']}.md"
    orig_path.write_text(f"{format_frontmatter(orig_meta)}\n\n{orig_body.strip()}\n", encoding="utf-8")
    trans_path.write_text(f"{format_frontmatter(trans_meta)}\n\n{trans_body.strip()}\n", encoding="utf-8")
    return orig_path, trans_path


# ---------------------------------------------------------------------------
# 1. Don Quijote de la Mancha (Wikisource: es + en Ormsby)
# ---------------------------------------------------------------------------
def discover_es_quixote_chapters(delay: float) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Discover transcribed Spanish Don Quijote chapter pages from es.wikisource.org."""
    hub_links = fetch_wikisource_links("es", "Don Quijote de la Mancha", delay=delay)
    # Prefer the 1859 Barcelona (Tomás Gorchs) edition, then 1905 / 1842
    candidates = [
        t for t in hub_links
        if "Don Quijote de la Mancha" in t and ("1859" in t or "1905" in t or "1842" in t)
    ]
    part1: dict[int, str] = {}
    part2: dict[int, str] = {}

    chap_num_re = re.compile(r"/(?:Cap[íi]tulo\s+)?([IVXLCDM]+|\d+)$", re.IGNORECASE)
    for vol_title in candidates:
        sublinks = fetch_wikisource_links("es", vol_title, delay=delay)
        is_part2 = "Tomo II" in vol_title or "Segunda" in vol_title
        target = part2 if is_part2 else part1
        for link in sublinks:
            m = chap_num_re.search(link)
            if not m:
                continue
            num = roman_to_int(m.group(1))
            if num is not None and num not in target:
                target[num] = link
        if len(part1) >= 52 and len(part2) >= 74:
            break

    return sorted(part1.items()), sorted(part2.items())


def discover_en_quixote_chapters(delay: float) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Discover Ormsby's English Don Quixote chapter pages from en.wikisource.org."""
    links = fetch_wikisource_links("en", "Don Quixote", delay=delay)
    part1: dict[int, str] = {}
    part2: dict[int, str] = {}

    pat = re.compile(r"Volume\s+(1|2)/Chapter\s+(\d+)$", re.IGNORECASE)
    for link in links:
        m = pat.search(link)
        if not m:
            continue
        vol = int(m.group(1))
        chap = int(m.group(2))
        if vol == 1:
            part1[chap] = link
        else:
            part2[chap] = link
    return sorted(part1.items()), sorted(part2.items())


def build_quixote_wikisource_body(
    parts: list[tuple[int, str, str, list[tuple[int, str]]]],
    lang: str,
    delay: float,
) -> str:
    out_lines: list[str] = []
    for part_num, part_title, chap_prefix, chapters in parts:
        out_lines.append(f"## {part_title}")
        out_lines.append("")
        for chap_num, page_title in chapters:
            print(f"Fetching [{lang}] {page_title}...", file=sys.stderr)
            raw_html = fetch_wikisource_html(lang, page_title, delay=delay)
            paras = extract_wikisource_paragraphs(raw_html)
            if not paras:
                continue
            out_lines.append(f"### {chap_prefix} {chap_num}")
            out_lines.append("")
            paras[0] = f"{{{{{part_num}.{chap_num}}}}} {paras[0]}"
            for p in paras:
                out_lines.append(p)
                out_lines.append("")
    return "\n".join(out_lines)


def build_don_quixote(out_dir: Path, delay: float) -> tuple[Path, Path]:
    print("Discovering Spanish Don Quijote chapters on es.wikisource.org...", file=sys.stderr)
    es_p1, es_p2 = discover_es_quixote_chapters(delay=delay)
    print(f"Found {len(es_p1)} Part I and {len(es_p2)} Part II Spanish chapters.", file=sys.stderr)

    print("Discovering English Don Quixote chapters on en.wikisource.org...", file=sys.stderr)
    en_p1, en_p2 = discover_en_quixote_chapters(delay=delay)
    print(f"Found {len(en_p1)} Volume 1 and {len(en_p2)} Volume 2 English chapters.", file=sys.stderr)

    es_body = build_quixote_wikisource_body(
        [(1, "Primera parte", "Capítulo", es_p1), (2, "Segunda parte", "Capítulo", es_p2)],
        lang="es",
        delay=delay,
    )
    en_body = build_quixote_wikisource_body(
        [(1, "Part I", "Chapter", en_p1), (2, "Part II", "Chapter", en_p2)],
        lang="en",
        delay=delay,
    )

    orig_meta = {
        "id": "cervantes.quijote.es",
        "work": "cervantes.quijote",
        "author": "Miguel de Cervantes Saavedra",
        "title": "Don Quixote",
        "label": "El ingenioso hidalgo Don Quijote de la Mancha",
        "edition": "Wikisource",
        "language": "es",
        "layout": "prose",
        "source": "https://es.wikisource.org/wiki/Don_Quijote_de_la_Mancha",
    }
    trans_meta = {
        "id": "cervantes.quijote.ormsby",
        "work": "cervantes.quijote",
        "author": "Miguel de Cervantes Saavedra",
        "title": "Don Quixote",
        "label": "El ingenioso hidalgo Don Quijote de la Mancha",
        "edition": "John Ormsby",
        "language": "en",
        "original": "es",
        "layout": "prose",
        "source": "https://en.wikisource.org/wiki/Don_Quixote",
    }
    return write_pair(out_dir, "cervantes-don-quixote", orig_meta, es_body, trans_meta, en_body)


# ---------------------------------------------------------------------------
# 2. Los trabajos de Persiles y Sigismunda (1617)
# ---------------------------------------------------------------------------
def parse_persiles_es_book(raw_html: str, book_num: int) -> list[str]:
    """Extract chapters from a Spanish Wikisource Book page of Persiles (1920)."""
    cleaned = re.sub(r"<table\b[^>]*>.*?</table>", "", raw_html, flags=re.DOTALL)
    chap_pat = re.compile(
        r"(?:<h[2-4][^>]*>|<p[^>]*>\s*(?:<[^>]+>)*)\s*CAP[ÍI]TULO\s+([A-Z]+)\b.*?(?:</h[2-4]>|</p>)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    matches = list(chap_pat.finditer(cleaned))
    lines: list[str] = []
    for idx, m in enumerate(matches):
        chap_num = roman_to_int(m.group(1))
        if chap_num is None:
            continue
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        paras = extract_wikisource_paragraphs(cleaned[start:end])
        if not paras:
            continue
        lines.append(f"### Capítulo {chap_num}")
        lines.append("")
        paras[0] = f"{{{{{book_num}.{chap_num}}}}} {paras[0]}"
        for p in paras:
            lines.append(p)
            lines.append("")
    return lines


def parse_persiles_en_html(raw_html: str) -> str:
    """Parse Stanley's 1854 translation from mirrored PG HTML."""
    # Extract body text between <body> tags
    m_body = re.search(r"<body[^>]*>(.*)</body>", raw_html, flags=re.DOTALL | re.IGNORECASE)
    body = m_body.group(1) if m_body else raw_html
    book_re = re.compile(r"<h[1-3][^>]*>\s*BOOK\s+([IVX]+)\b.*?</h[1-3]>", re.IGNORECASE | re.DOTALL)
    chap_re = re.compile(r"<h[2-4][^>]*>\s*CHAPTER\s+([IVXLCDM]+)\b.*?</h[2-4]>", re.IGNORECASE | re.DOTALL)

    book_matches = list(book_re.finditer(body))
    out_lines: list[str] = []
    for b_idx, bm in enumerate(book_matches):
        book_num = roman_to_int(bm.group(1))
        if book_num is None:
            continue
        b_start = bm.end()
        b_end = book_matches[b_idx + 1].start() if b_idx + 1 < len(book_matches) else len(body)
        book_html = body[b_start:b_end]

        out_lines.append(f"## Book {book_num}")
        out_lines.append("")
        chap_matches = list(chap_re.finditer(book_html))
        for c_idx, cm in enumerate(chap_matches):
            chap_num = roman_to_int(cm.group(1))
            if chap_num is None:
                continue
            c_start = cm.end()
            c_end = chap_matches[c_idx + 1].start() if c_idx + 1 < len(chap_matches) else len(book_html)
            paras = extract_wikisource_paragraphs(book_html[c_start:c_end])
            if not paras:
                continue
            out_lines.append(f"### Chapter {chap_num}")
            out_lines.append("")
            paras[0] = f"{{{{{book_num}.{chap_num}}}}} {paras[0]}"
            for p in paras:
                out_lines.append(p)
                out_lines.append("")
    return "\n".join(out_lines)


def build_persiles(out_dir: Path, delay: float) -> tuple[Path, Path]:
    es_books = [
        (1, "Libro primero", "Los trabajos de Persiles y Sigismunda (1920)/Tomo I/Libro primero"),
        (2, "Libro segundo", "Los trabajos de Persiles y Sigismunda (1920)/Tomo I/Libro segundo"),
        (3, "Libro tercero", "Los trabajos de Persiles y Sigismunda (1920)/Tomo II/Libro tercero"),
        (4, "Libro cuarto", "Los trabajos de Persiles y Sigismunda (1920)/Tomo II/Libro cuarto"),
    ]
    es_lines: list[str] = []
    for book_num, book_title, page in es_books:
        print(f"Fetching Persiles (Spanish, {book_title})...", file=sys.stderr)
        raw_html = fetch_wikisource_html("es", page, delay=delay)
        es_lines.append(f"## {book_title}")
        es_lines.append("")
        es_lines.extend(parse_persiles_es_book(raw_html, book_num))

    en_mirrors = [
        "https://www.mirrorservice.org/sites/ftp.ibiblio.org/pub/docs/books/gutenberg/6/1/5/6/61561/61561-h/61561-h.htm",
        "https://readingroo.ms/6/1/5/6/61561/61561-h/61561-h.htm",
    ]
    en_html = ""
    for url in en_mirrors:
        try:
            print(f"Downloading Persiles (Stanley, 1854) from {url}...", file=sys.stderr)
            en_html = http_get_text(url, delay=delay)
            break
        except Exception as exc:
            print(f"Mirror failed ({exc}), trying next...", file=sys.stderr)
    if not en_html:
        raise RuntimeError("Could not download Persiles English translation from any mirror.")

    en_body = parse_persiles_en_html(en_html)

    orig_meta = {
        "id": "cervantes.persiles.es",
        "work": "cervantes.persiles",
        "author": "Miguel de Cervantes Saavedra",
        "title": "The Wanderings of Persiles and Sigismunda",
        "label": "Los trabajos de Persiles y Sigismunda",
        "edition": "Editorial Calpe (1920)",
        "language": "es",
        "layout": "prose",
        "source": "https://es.wikisource.org/wiki/Los_trabajos_de_Persiles_y_Sigismunda",
    }
    trans_meta = {
        "id": "cervantes.persiles.stanley",
        "work": "cervantes.persiles",
        "author": "Miguel de Cervantes Saavedra",
        "title": "The Wanderings of Persiles and Sigismunda",
        "label": "Los trabajos de Persiles y Sigismunda",
        "edition": "Louisa Dorothea Stanley",
        "language": "en",
        "original": "es",
        "layout": "prose",
        "source": "https://www.mirrorservice.org/sites/ftp.ibiblio.org/pub/docs/books/gutenberg/6/1/5/6/61561/61561-h/61561-h.htm",
    }
    return write_pair(out_dir, "cervantes-persiles", orig_meta, "\n".join(es_lines), trans_meta, en_body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and format Cervantes works in Castilian and English.")
    parser.add_argument("--out-dir", type=Path, default=Path("library/own"), help="Output directory")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between HTTP requests (default: 1.0)")
    args = parser.parse_args()

    for fn in (build_don_quixote, build_persiles):
        orig_path, trans_path = fn(args.out_dir, delay=args.delay)
        print(f"Wrote: {orig_path}")
        print(f"Wrote: {trans_path}")


if __name__ == "__main__":
    main()