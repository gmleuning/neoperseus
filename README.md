# perseusrebuild

A fast, static, personal reader for Greek and Latin texts side by side with English, built
from the Perseus Digital Library's own source files, plus any texts you add yourself.
Plain HTML, no server, works offline.

## Setup

Python 3.9 or later and lxml:

```powershell
pip install lxml
```

## Use

```powershell
python perseus.py find euripides electra       # look up a work's id
python perseus.py add tlg0006.tlg012           # add it: downloads, converts, rebuilds
python perseus.py add tlg0059                  # an author id adds every work by that author
python perseus.py remove tlg0006.tlg012
python perseus.py update                       # re-run everything for the shelf
python perseus.py build                        # rebuild only (after editing your own texts)
```

Then open `site/index.html`. The index lists your shelf and remembers where you stopped in each
work. `site/catalog.html` searches every Perseus work and shows the command to add it.

In a text: **Blocks / Lines** switches between passage-level and line-level alignment (key
`t`), **Apparatus** shows the critical notes where an edition has them (key `a`), and **Go to**
jumps to a line or section (`150`, `2.150`, `17a`; key `/`).

## Your own texts

Any Markdown file in `library/own/` that follows [SPEC.md](SPEC.md) is part of the library.
To start from a Wikisource text, export it from Wikisource as EPUB, then:

```powershell
python perseus.py import-wikisource Dyskolos.epub --work menander.dyskolos --lang grc --author Menander --title Dyskolos
```

The importer writes a draft to `library/own/`. Check its front matter (title pages, an
introduction you may not want), then `python perseus.py build`. For verse it reports any
place where its line count disagrees with the line numbers printed in the edition.

To pair a translation with an original, give both files the same `work:` id and the same
citation keys. A translation of a Perseus work takes that work's id (for example
`phi1276.phi001` for Juvenal's Satires) and pairs with the Perseus Latin automatically.

## Layout

```
perseus.py            the command
reader/               tei.py (Perseus XML -> library), wikisource.py (EPUB -> library),
                      library.py (reads library files), build.py (library -> site),
                      perseus.py (catalog, shelf, download)
assets/               style.css, reader.js, catalog.js, fonts/
catalog/catalog.json  every Perseus work and file (regenerate with tools/make_catalog.py)
shelf.txt             your reading list
library/own/          your texts (committed)
library/perseus/      converted Perseus texts (generated, not committed)
corpus/               downloaded Perseus XML (generated, not committed)
site/                 the built reader (generated, not committed)
```

## Sources and licences

- Texts: [PerseusDL/canonical-greekLit](https://github.com/PerseusDL/canonical-greekLit) and
  [canonical-latinLit](https://github.com/PerseusDL/canonical-latinLit), CC BY-SA 4.0. Files are
  downloaded at the commit recorded in the catalog, so a build is reproducible.
- Wikisource texts: CC BY-SA, source URL in each file's header.
- Fonts: Gentium Book Plus and Spectral, SIL Open Font License (`assets/fonts/OFL-*.txt`).

## Status

Done: catalog, shelf, download, Perseus converter (tested on drama, Stephanus prose, epic and a
Latin speech), side-by-side builder with sync report, Wikisource importer (tested on verse
drama, a fragment collection and a verse translation with introduction and endnotes).

Next: LSJ lookup for Greek words, search inside texts, and checking the converter against more
of the shelf.
