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
python perseus.py dictionaries                 # once: LSJ and Lewis & Short (downloads about 440 MB)
```

Several ids can go in one `add` (`python perseus.py add tlg0011 tlg0059 phi0690`), or edit
`shelf.txt` (one id per line) and run `update`.

Then open `site/index.html`:

- **Library**: what you were last reading, then authors on the left and the chosen author's
  works on the right. Authors with many works are grouped (Cicero: speeches, rhetoric,
  philosophy, letters); the rules are in `catalog/groups.tsv` and can be edited. The box at the
  top finds works and authors across the shelf.
- **Search texts**: words or phrases across the shelf, one author or one work, in the original,
  the translation or both. Accents, breathings, case, final sigma, u/v and i/j are ignored.
  "All forms of a Greek word" finds every inflected form (λόγος finds λόγου, λόγῳ, λόγοις…).
- **Catalog**: every Perseus work, with the command to add it.

In a text:
- **Click a Greek or Latin word** for the dictionary panel: the possible dictionary words (with
  the parse, for Greek) and the full LSJ or Lewis & Short entry. Citations become links when
  the cited work is on your shelf.
- **Blocks / Lines** (key `t`) switches between passage-level and line-level alignment;
  **Apparatus** (key `a`) shows an edition's critical notes; **Go to** (key `/`) jumps to `150`,
  `2.150` or `17a`; **Search** searches this work.
- **Settings** (key `,`): colour scheme (light, sepia, dark, black or automatic), Greek, Latin and
  English fonts, text size, size of the original language, line spacing, page width, justified
  prose, which columns to show, line numbers, section numbers, notes, the contents sidebar,
  and dictionary options. Settings are kept in the browser.

Greek look-up uses the Morpheus analyses, so it knows almost every inflected form. Latin look-up
has no such table yet: it strips endings and matches the stems Lewis & Short gives, so it finds
the right word for most regular forms but can rank a lookalike first (`venit` offers *vēneo*
before *venio*) and misses some irregular forms. The panel always lists the other candidates
and has a box for typing a dictionary form.

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
                      perseus.py (catalog, shelf, download), dictionary.py (LSJ, Lewis & Short)
assets/               style.css, settings.js, reader.js, dict.js, index.js, search.js,
                      catalog.js, fonts/
catalog/catalog.json  every Perseus work and file (regenerate with tools/make_catalog.py)
catalog/groups.tsv    how authors with many works are grouped on the library page
shelf.txt             your reading list
library/own/          your texts (committed)
library/perseus/      converted Perseus texts (generated, not committed)
corpus/               downloaded Perseus XML (generated, not committed)
site/                 the built reader (generated, not committed); site/dict/ holds the
                      dictionaries and survives rebuilds
```

## Sources and licences

- Texts: [PerseusDL/canonical-greekLit](https://github.com/PerseusDL/canonical-greekLit) and
  [canonical-latinLit](https://github.com/PerseusDL/canonical-latinLit), CC BY-SA 4.0. Files are
  downloaded at the commit recorded in the catalog, so a build is reproducible.
- Wikisource texts: CC BY-SA, source URL in each file's header.
- Dictionaries: LSJ and Lewis & Short from [PerseusDL/lexica](https://github.com/PerseusDL/lexica),
  CC BY-SA. Greek inflected forms from Morpheus via
  [gcelano/LemmatizedAncientGreekXML](https://github.com/gcelano/LemmatizedAncientGreekXML),
  **CC BY-NC 4.0**: fine for personal use, but a site built with it must not be published commercially.
- Fonts: Gentium Book Plus, Spectral, EB Garamond, Cardo, GFS Didot and GFS Neohellenic, SIL Open
  Font License (`assets/fonts/OFL-*.txt`).

## Status

Done: catalog, shelf, download; Perseus converter; side-by-side pages with sync report (verse
translations with their own line numbers are placed approximately and marked so); Wikisource
importer; library page with grouping and continue-reading; text search with all-forms search for
Greek; dictionary panel (LSJ, Lewis & Short); settings panel.

Next: a proper Latin form table, and checking the converter against more of the shelf.
