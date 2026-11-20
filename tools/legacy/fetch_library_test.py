#!/usr/bin/env python3
"""
Download public-domain world literature (200 AD - 1900 AD) and public-domain
English translations from Wikisource, and format them as paired Markdown files
according to SPEC.md.

Usage:
    python3 fetch_library.py [--out-dir library/own]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "WorldLitLibraryFetcher/1.0 (public-domain educational script)"


def fetch_wikisource_html(lang: str, page: str) -> str:
    """Fetch parsed HTML content from a Wikisource MediaWiki API."""
    params = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": page,
            "prop": "text",
            "format": "json",
            "redirects": "1",
        }
    )
    url = f"https://{lang}.wikisource.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"Wikisource API error for {lang}:{page}: {data['error']}")
    return data["parse"]["text"]["*"]


def strip_tags(fragment: str) -> str:
    """Remove HTML tags, decode entities, and normalize whitespace."""
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", "", fragment, flags=re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    return text


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
# 1. Dante Alighieri — Inferno, Canto I (1308-1321 AD)
# ---------------------------------------------------------------------------
def build_dante_inferno_1(out_dir: Path) -> tuple[Path, Path]:
    it_html = fetch_wikisource_html("it", "Divina Commedia/Inferno/Canto I")
    en_html = fetch_wikisource_html("en", "Divine Comedy (Longfellow 1867)/Volume 1/Canto 1")

    def extract_lines(raw_html: str, is_italian: bool) -> list[str]:
        # Wikisource poem blocks live inside <div class="poem">...</div>
        poems = re.findall(r'<div class="poem"[^>]*>(.*?)</div>', raw_html, flags=re.DOTALL)
        block = "\n".join(poems) if poems else raw_html
        # Remove inline line-number spans/links
        block = re.sub(r'<span[^>]*class="[^"]*linenum[^"]*"[^>]*>.*?</span>', "", block, flags=re.DOTALL)
        text = strip_tags(block)
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+\d+$", "", raw_line).strip()
            if not line:
                continue
            if is_italian and line.startswith("Incomincia la Comedia"):
                continue
            lines.append(line)
        return lines

    it_lines = extract_lines(it_html, is_italian=True)
    en_lines = extract_lines(en_html, is_italian=False)

    # Group Italian lines into tercets + final closing line (136 lines total)
    it_formatted: list[str] = ["## Canto I", ""]
    for idx, line in enumerate(it_lines, start=1):
        it_formatted.append(line)
        if idx % 3 == 0 and idx < len(it_lines):
            it_formatted.append("")

    en_formatted: list[str] = ["## Canto I", ""] + en_lines

    orig_meta = {
        "id": "dante.inferno.1.it",
        "work": "dante.inferno.1",
        "author": "Dante Alighieri",
        "title": "Inferno, Canto I",
        "label": "Divina Commedia — Inferno, Canto I",
        "edition": "Wikisource",
        "language": "it",
        "layout": "verse",
        "numbering": "auto-by-section",
        "source": "https://it.wikisource.org/wiki/Divina_Commedia/Inferno/Canto_I",
    }
    trans_meta = {
        "id": "dante.inferno.1.longfellow",
        "work": "dante.inferno.1",
        "author": "Dante Alighieri",
        "title": "Inferno, Canto I",
        "label": "Divina Commedia — Inferno, Canto I",
        "edition": "Henry Wadsworth Longfellow",
        "language": "en",
        "original": "it",
        "layout": "verse",
        "numbering": "auto-by-section",
        "source": "https://en.wikisource.org/wiki/Divine_Comedy_(Longfellow_1867)/Volume_1/Canto_1",
    }
    return write_pair(
        out_dir,
        "dante-inferno-1",
        orig_meta,
        "\n".join(it_formatted),
        trans_meta,
        "\n".join(en_formatted),
    )


# ---------------------------------------------------------------------------
# 2. Charles Baudelaire — Hymne à la Beauté (1861 AD)
# ---------------------------------------------------------------------------
def build_baudelaire_hymne(out_dir: Path) -> tuple[Path, Path]:
    fr_html = fetch_wikisource_html("fr", "Les Fleurs du mal (1861)/Hymne à la beauté")
    en_html = fetch_wikisource_html("en", "Hymn to Beauty (Martin)")

    def extract_stanzas(raw_html: str) -> list[list[str]]:
        poems = re.findall(r'<div class="poem"[^>]*>(.*?)</div>', raw_html, flags=re.DOTALL)
        block = poems[0] if poems else raw_html
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", block, flags=re.DOTALL)
        stanzas: list[list[str]] = []
        for p in paragraphs:
            lines = [ln.strip() for ln in strip_tags(p).splitlines() if ln.strip()]
            if lines:
                stanzas.append(lines)
        return stanzas

    fr_stanzas = extract_stanzas(fr_html)
    en_stanzas = extract_stanzas(en_html)

    fr_body = ["## Hymne à la Beauté", ""]
    for stanza in fr_stanzas:
        fr_body.extend(stanza)
        fr_body.append("")

    en_body = ["## Hymn to Beauty", ""]
    for stanza in en_stanzas:
        en_body.extend(stanza)
        en_body.append("")

    orig_meta = {
        "id": "baudelaire.hymne_beaute.fr",
        "work": "baudelaire.hymne_beaute",
        "author": "Charles Baudelaire",
        "title": "Hymn to Beauty",
        "label": "Hymne à la Beauté",
        "edition": "Poulet-Malassis et de Broise (1861)",
        "language": "fr",
        "layout": "verse",
        "numbering": "auto",
        "source": "https://fr.wikisource.org/wiki/Les_Fleurs_du_mal_(1861)/Hymne_%C3%A0_la_beaut%C3%A9",
    }
    trans_meta = {
        "id": "baudelaire.hymne_beaute.martin",
        "work": "baudelaire.hymne_beaute",
        "author": "Charles Baudelaire",
        "title": "Hymn to Beauty",
        "label": "Hymne à la Beauté",
        "edition": "Dorothy Martin",
        "language": "en",
        "original": "fr",
        "layout": "verse",
        "numbering": "auto",
        "source": "https://en.wikisource.org/wiki/Hymn_to_Beauty_(Martin)",
    }
    return write_pair(
        out_dir,
        "baudelaire-hymn-to-beauty",
        orig_meta,
        "\n".join(fr_body),
        trans_meta,
        "\n".join(en_body),
    )


# ---------------------------------------------------------------------------
# 3. Tao Yuanming — 桃花源記 / The Peach-Blossom Fountain (421 AD)
# ---------------------------------------------------------------------------
def build_tao_peach_blossom(out_dir: Path) -> tuple[Path, Path]:
    zh_html = fetch_wikisource_html("zh", "桃花源記")
    en_html = fetch_wikisource_html("en", "Gems of Chinese Literature/T‘ao Yüan-ming-The Peach-blossom Fountain")

    # Extract main Chinese prose paragraph (starts with 晉太元)
    zh_paras = re.findall(r"<p[^>]*>(.*?)</p>", zh_html, flags=re.DOTALL)
    zh_prose = ""
    for p in zh_paras:
        cleaned = strip_tags(p).strip()
        if "武陵人捕魚" in cleaned:
            # Remove inline variant-reading annotations like 一作「...」
            cleaned = re.sub(r"一作「[^」]+」", "", cleaned)
            cleaned = re.sub(r"\s+", "", cleaned)
            zh_prose = cleaned
            break

    # Split Chinese prose at the 4 narrative transitions matching Giles's 4 paragraphs
    markers = ["見漁人", "既出，得其船", "南陽劉子驥"]
    zh_sections: list[str] = []
    remaining = zh_prose
    for marker in markers:
        if marker in remaining:
            head, tail = remaining.split(marker, 1)
            zh_sections.append(head.strip())
            remaining = marker + tail
    if remaining.strip():
        zh_sections.append(remaining.strip())

    # Extract English paragraphs from Giles's translation
    en_paras_raw = re.findall(r"<p[^>]*>(.*?)</p>", en_html, flags=re.DOTALL)
    en_sections: list[str] = []
    for p in en_paras_raw:
        txt = re.sub(r"\s+", " ", strip_tags(p)).strip()
        if txt.startswith("Towards the close of the fourth century") or en_sections:
            if txt.startswith("↑"):
                break
            if txt:
                en_sections.append(txt)

    zh_body = ["## 桃花源記", ""]
    for idx, para in enumerate(zh_sections, start=1):
        zh_body.append(f"{{{{{idx}}}}} {para}")
        zh_body.append("")

    en_body = ["## The Peach-Blossom Fountain", ""]
    for idx, para in enumerate(en_sections, start=1):
        en_body.append(f"{{{{{idx}}}}} {para}")
        en_body.append("")

    orig_meta = {
        "id": "tao_yuanming.peach_blossom.zh",
        "work": "tao_yuanming.peach_blossom",
        "author": "Tao Yuanming",
        "title": "The Peach-Blossom Fountain",
        "label": "桃花源記",
        "edition": "Wikisource",
        "language": "zh",
        "layout": "prose",
        "source": "https://zh.wikisource.org/wiki/%E6%A1%83%E8%8A%B1%E6%BA%90%E8%A8%98",
    }
    trans_meta = {
        "id": "tao_yuanming.peach_blossom.giles",
        "work": "tao_yuanming.peach_blossom",
        "author": "Tao Yuanming",
        "title": "The Peach-Blossom Fountain",
        "label": "桃花源記",
        "edition": "Herbert Allen Giles",
        "language": "en",
        "original": "zh",
        "layout": "prose",
        "source": "https://en.wikisource.org/wiki/Gems_of_Chinese_Literature/T%E2%80%98ao_Y%C3%BCan-ming-The_Peach-blossom_Fountain",
    }
    return write_pair(
        out_dir,
        "tao-peach-blossom-spring",
        orig_meta,
        "\n".join(zh_body),
        trans_meta,
        "\n".join(en_body),
    )


# ---------------------------------------------------------------------------
# 4. Anton Chekhov — Пари / The Bet (1889 AD)
# ---------------------------------------------------------------------------
def build_chekhov_the_bet(out_dir: Path) -> tuple[Path, Path]:
    ru_html = fetch_wikisource_html("ru", "Пари (Чехов)")
    en_html = fetch_wikisource_html("en", "Best Russian Short Stories/The Bet")

    def extract_two_parts(raw_html: str, is_russian: bool) -> tuple[list[str], list[str]]:
        # Split on section II heading
        parts = re.split(r"<h[23][^>]*>.*?\bII\b.*?</h[23]>|<p[^>]*>\s*(?:<[^>]+>)*\s*II\s*(?:</[^>]+>)*\s*</p>", raw_html, maxsplit=1, flags=re.DOTALL)
        part1_html = parts[0]
        part2_html = parts[1] if len(parts) > 1 else ""

        def clean_paras(chunk: str, start_marker: str) -> list[str]:
            paras = []
            started = False
            for p in re.findall(r"<p[^>]*>(.*?)</p>", chunk, flags=re.DOTALL):
                txt = re.sub(r"\s+", " ", strip_tags(p)).strip()
                if not txt:
                    continue
                if not started:
                    if start_marker in txt:
                        started = True
                    else:
                        continue
                if is_russian and txt.startswith("↑"):
                    break
                if not is_russian and (txt.startswith("This work is a translation") or txt.startswith("Original:")):
                    break
                paras.append(txt)
            return paras

        p1 = clean_paras(part1_html, "Была темная" if is_russian else "IT was a dark")
        p2 = clean_paras(part2_html, "Старик-банкир" if is_russian else "The banker recalled")
        return p1, p2

    ru_p1, ru_p2 = extract_two_parts(ru_html, is_russian=True)
    en_p1, en_p2 = extract_two_parts(en_html, is_russian=False)

    def format_prose(p1: list[str], p2: list[str]) -> str:
        lines = ["## I", ""]
        for i, p in enumerate(p1, start=1):
            lines.append(f"{{{{1.{i}}}}} {p}")
            lines.append("")
        lines.extend(["## II", ""])
        for i, p in enumerate(p2, start=1):
            lines.append(f"{{{{2.{i}}}}} {p}")
            lines.append("")
        return "\n".join(lines)

    orig_meta = {
        "id": "chekhov.the_bet.ru",
        "work": "chekhov.the_bet",
        "author": "Anton Chekhov",
        "title": "The Bet",
        "label": "Пари",
        "edition": "Полное собрание сочинений (1977)",
        "language": "ru",
        "layout": "prose",
        "source": "https://ru.wikisource.org/wiki/%D0%9F%D0%B0%D1%80%D0%B8_(%D0%A7%D0%B5%D1%85%D0%BE%D0%B2)",
    }
    trans_meta = {
        "id": "chekhov.the_bet.murry",
        "work": "chekhov.the_bet",
        "author": "Anton Chekhov",
        "title": "The Bet",
        "label": "Пари",
        "edition": "John Middleton Murry",
        "language": "en",
        "original": "ru",
        "layout": "prose",
        "source": "https://en.wikisource.org/wiki/Best_Russian_Short_Stories/The_Bet",
    }
    return write_pair(
        out_dir,
        "chekhov-the-bet",
        orig_meta,
        format_prose(ru_p1, ru_p2),
        trans_meta,
        format_prose(en_p1, en_p2),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and format public-domain world literature pairs.")
    parser.add_argument("--out-dir", type=Path, default=Path("library/own"), help="Output directory")
    args = parser.parse_args()

    builders = [
        ("Dante Alighieri — Inferno, Canto I", build_dante_inferno_1),
        ("Charles Baudelaire — Hymne à la Beauté", build_baudelaire_hymne),
        ("Tao Yuanming — Peach Blossom Spring", build_tao_peach_blossom),
        ("Anton Chekhov — The Bet", build_chekhov_the_bet),
    ]
    for label, fn in builders:
        print(f"Fetching {label}...")
        orig_path, trans_path = fn(args.out_dir)
        print(f"  -> {orig_path}")
        print(f"  -> {trans_path}")


if __name__ == "__main__":
    main()