# neoperseus

A fast, static, personal reader for Greek, Latin and other classical and world texts, set side by side with
English. It is built from the Perseus Digital Library's own source files and from Wikisource, plus any
texts you add yourself. The result is plain HTML: no server, works offline, hosted free on Cloudflare Pages.

**Read it online: https://neoperseus.pages.dev**

This repository holds the code that builds the reader, the reading list (`shelf.txt`), the catalog of
available works, the edit rules, and the documentation. It does not hold the texts: Perseus texts, the
dictionaries and the built site come to over 1.5 GB, so they are downloaded or generated when you build.

## What it does

- **Side-by-side texts.** An original on the left, a translation on the right, paired on shared
  citation keys (line numbers, Stephanus pages, chapters) so passages face each other. Works with two
  English translations get a Compare view. Pairs that do not match perfectly still read: unmatched text
  rides along in the nearest block, and each build reports how well every pair matched.
- **Click any word.** Greek and Latin words open LSJ or Lewis & Short, with the parse for Greek. English
  words open Wiktionary: senses, IPA, recordings and the etymology as a timeline.
- **Library, search, settings.** Authors and works with continue-reading; full-text search (accents,
  breathings and final sigma ignored; all inflected forms of a Greek word); colour schemes, fonts, sizes,
  columns, line numbers, notes. Settings stay in the browser.
- **Works on a phone.** The reader's title opens a contents dropdown (with Go to), so you never scroll
  back to the top to move around; Blocks/Lines lives in Settings.
- **Your own texts.** Anything in the library format (see below), from a file you wrote to a PDF you
  imported. Texts may also be opened in the browser only, never uploaded.
- **A local catalog of public-domain works** (Perseus and Wikisource) with an Add button, and an edit mode
  for deleting and importing. These exist only on your own computer, not on the public site.

## Setup

Python 3.9 or later and lxml:

```powershell
pip install lxml
```

Optional: `pip install pymupdf` (import PDFs), [pandoc](https://pandoc.org) (import EPUBs),
[Node.js](https://nodejs.org) (to publish).

## First use

```powershell
python perseus.py find euripides electra       # look up a Perseus work's id
python perseus.py add tlg0006.tlg012           # add it: downloads, converts, builds
python perseus.py add tlg0059                  # an author id adds every work by that author
python perseus.py dictionaries                 # once: LSJ, Lewis & Short, Greek forms (about 440 MB)
python perseus.py edit                         # open the reader with the catalog and editing on
```

`shelf.txt` is the reading list (one work or author id per line); `python perseus.py update` makes the
library match it. `python perseus.py remove ID` takes a work off.

## Two sites, one build

`python perseus.py build` makes two folders:

| Folder | What it is | Deployed |
|---|---|---|
| `site/` | the public site: every text except `library/private/` | yes |
| `site-local/` | an overlay for this computer: the catalog, the private texts (and every page of a work that has one, since a private translation adds an edition and a Compare page), the library and search pages that list them, and the sync report | never |

`python perseus.py edit` serves `site-local/` first and `site/` for everything else, so text pages are
never copied or built twice. `python perseus.py build --public` makes only `site/`.

Builds are **incremental**. A work's pages are made again only when its Markdown, its edit rules or the page
code changed (the record is in `.buildcache/`). Nothing changed: about 2 seconds. One text changed: about
1. A first build, or one after editing `reader/build.py`, `library.py` or `edits.py`: about 100.

## The catalog and edit mode

`python perseus.py edit` opens http://127.0.0.1:8790 with these extras (they are added by the local server
and are not in any built page):

- **Catalog**: *Works in public domain repositories*. Perseus and Wikisource so far, with a repository
  filter, "with English", and "hide works on my shelf" (to see what you do not have). **Add** puts a Perseus
  work on the shelf, or downloads a Wikisource work in both languages. A status bar shows progress.
  `python tools/wikisource_catalog.py` refreshes the Wikisource list.
- **Import…**: raw Markdown, or a PDF or EPUB book, from `library/additions/`. For a book the panel lists the
  verse parts, with pages and line numbers; choose one, preview, then import to **Private**
  (`library/private/`, this computer only) or **Library** (`library/own/`, published).
- **Alt-click a paragraph** to delete it. For Perseus texts this is a rule in `library/edits.tsv`
  (they are regenerated); for your own texts you can simply edit the file.
- **Rebuild** and **Publish** (build, commit `library/edits.tsv` and `library/own/`, push, deploy `site/`).

Every import or download is a draft that needs a short revision by hand. **How texts are formatted, how two
texts are paired, and the routine for finishing each one is in [docs/TEXTS.md](docs/TEXTS.md).** The
markup itself is in [SPEC.md](SPEC.md).

## Your own texts

A Markdown file in `library/own/` that follows [SPEC.md](SPEC.md) is part of the library, listed under its
author beside the Perseus texts. To pair a translation with an original, give both the same `work:` and the
same citation keys; a translation of a Perseus work takes that work's id (`phi1276.phi001` for Juvenal's
Satires) and pairs with the Perseus original automatically. Wikisource EPUBs can also be converted with

```powershell
python perseus.py import-wikisource Dyskolos.epub --work menander.dyskolos --lang grc --author Menander --title Dyskolos
```

Folders carry meaning: `own/` is published, `private/` never is, `perseus/` is generated, `additions/` is an
inbox. A file with a `work:` header is built wherever it sits under `library/`. See docs/TEXTS.md, section 3.

## Publishing (Cloudflare Pages)

The built site is about 700 MB, too big for git, so it is uploaded directly to
[Cloudflare Pages](https://pages.cloudflare.com/) (free plan: unlimited bandwidth, 20,000 files, 25 MB per
file). First time only: `npx wrangler login`. Then:

```powershell
.\deploy.ps1            # upload site/ as it is
.\deploy.ps1 -Build     # build the public site first, then upload
.\deploy.ps1 -Update    # re-run everything for the shelf, then build and upload
.\deploy.ps1 -Check     # check site/ against Cloudflare's limits, upload nothing
```

Only changed files are uploaded after the first deploy. The script refuses a site that carries the old
local markers (`_local`, `_private`). The Greek word-form data is **CC BY-NC**, so the published site must
stay non-commercial: no ads, no charging. Keep copyrighted texts out of `library/own/`; use `private/`.

## Layout

```
perseus.py            the command
reader/               tei.py (Perseus XML -> library), library.py (reads library files),
                      build.py (library -> site: pages, cache, the two sites), edits.py (edit rules),
                      editserver.py (python perseus.py edit), importer.py + sources.py (books and
                      raw Markdown), wikisource.py (EPUB), wikisource_fetch.py (Wikisource API),
                      perseus.py (catalog, shelf, download), dictionary.py (LSJ, Lewis & Short)
assets/               style.css, settings.js, reader.js, dict.js, library.js, local.js, search.js,
                      catalog.js, edit.js (edit mode only), fonts/
catalog/              catalog.json (every Perseus work; tools/make_catalog.py), wikisource.json
                      (tools/wikisource_catalog.py), groups.tsv (author groups on the library page)
tools/                make_catalog.py, wikisource_catalog.py, hershey_greek.py
docs/TEXTS.md         formatting, pairing and last-mile revision of texts
SPEC.md               the library file format
reviews/              proofreading logs for individual texts
shelf.txt             your reading list
deploy.ps1            publishes site/ to Cloudflare Pages
library/edits.tsv     edit rules (committed)
library/own/          your published texts (committed)
library/private/      texts for this computer only (not committed, never deployed)
library/additions/    inbox: raw files, books, scripts (not committed)
library/perseus/      converted Perseus texts (generated, not committed)
corpus/               downloaded Perseus XML (generated, not committed)
site/  site-local/    the built sites (generated, not committed); site/dict/ holds the dictionaries
.buildcache/          what each site was last built from (generated, not committed)
```

## Sources and licences

- Perseus texts: [PerseusDL/canonical-greekLit](https://github.com/PerseusDL/canonical-greekLit) and
  [canonical-latinLit](https://github.com/PerseusDL/canonical-latinLit), CC BY-SA 4.0, downloaded at the
  commit recorded in the catalog so a build is reproducible.
- Wikisource texts: CC BY-SA, with the source address in each file's header. Translations there can still be
  in copyright where you are: check before publishing.
- English word look-ups: Wiktionary, CC BY-SA, fetched live and not stored.
- Dictionaries: LSJ and Lewis & Short from [PerseusDL/lexica](https://github.com/PerseusDL/lexica), CC BY-SA.
  Greek inflected forms from Morpheus via
  [gcelano/LemmatizedAncientGreekXML](https://github.com/gcelano/LemmatizedAncientGreekXML),
  **CC BY-NC 4.0**: fine for personal use, but a site built with it must not be published commercially.
- Fonts: Gentium Book Plus, Spectral, EB Garamond, Cardo, GFS Didot and GFS Neohellenic, SIL Open Font
  License (`assets/fonts/OFL-*.txt`). The landing page title uses Hershey Greek Simplex and Roman Triplex
  (the Hershey vector fonts, free to redistribute).
- Landing image: J. M. W. Turner, *The Beacon Light* (detail).

## Status

Done: catalog, shelf, download; Perseus converter; side-by-side pages with sync report; Compare;
Wikisource import (EPUB and API) and the Add button; book import (PDF, EPUB); library, search, settings;
dictionaries and Wiktionary; incremental builds and the public/local split; phone layout.

Next: a proper Latin form table; non-Perseus alignment modes (paragraph and chapter pairing with a
manual check); an explicit `role: original | translation` and `visibility` in the front matter instead of
reading them from folders and language codes.
