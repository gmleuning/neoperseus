# neoperseus

A fast, static, personal reader for Greek, Latin and other classical and world texts, set side by side with
English. It is built from the Perseus Digital Library's own source files and from Wikisource, plus any
texts you add yourself. The result is plain HTML: no server, works offline, hosted free on Cloudflare Pages.

**Read it online: https://neoperseus.pages.dev**

This repository holds the code, the site's source, the catalogs, the format spec, the edit rules and the
texts you add yourself. It does not hold the Perseus texts, the dictionaries or the built site: those come to
over 1.5 GB and are downloaded or generated when you build.

## Where things are

Four top-level folders, one idea each. Every path in the code is defined once, in
[tools/reader/paths.py](tools/reader/paths.py).

```
neoperseus/
  perseus.py             a three-line launcher: python perseus.py edit, build, add ...
  assets/                what the site shows, not code
    fonts/               Gentium, Spectral, Hershey ... (and their licences)
    images/              the landing painting and its crops, design sources
  site/                  the website
    code/                its CSS and JavaScript (the source)
    public/              the built site: what is deployed            (generated)
    local/               the overlay for this computer: catalog, private texts   (generated)
    cache/               what each built site was made from           (generated)
  corpus/                the texts, and everything needed to get more
    library/             finished texts
      perseus/           converted from Perseus                       (generated)
      own/               yours, published
      private/           yours, never published (not committed)
      edits.tsv          edit rules for the Perseus texts
    catalog/             finding and importing
      catalog.json       every Perseus work
      wikisource.json    Wikisource pairs
      groups.tsv         how authors with many works are grouped
      shelf.txt          your Perseus reading list
      SPEC.md            the file format
      TEXTS.md           formatting, pairing and finishing texts by hand
      format_and_revis.md  the format and error categories as an LLM prompt, to check and fix texts
      inbox/             raw files waiting to be imported (not committed)
      unsorted/          files not yet sorted (not committed)
      sources/           downloaded Perseus XML, dictionary sources     (generated)
    reviews/             proofreading logs
  tools/                 all the Python and the scripts
    perseus.py           the command itself
    reader/              the package: build, import, edit server, paths
    deploy.ps1           publish to Cloudflare
    make_catalog.py  wikisource_catalog.py  hershey_greek.py  pdf2md.ps1
    legacy/              the trial fetch scripts the importer grew from
```

Generated folders are in `.gitignore` and safe to delete: the next build or `update` recreates them.
(`.claude/` is the Claude desktop app's own settings for this project. Nothing in it is needed to build.)

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
- **Works on a phone.** The reader's title opens a contents dropdown (with Go to); Blocks/Lines lives in Settings.
- **Your own texts**, from a file you wrote to a PDF you imported; or opened in the browser only, never uploaded.
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

`corpus/catalog/shelf.txt` is the Perseus reading list (one work or author id per line);
`python perseus.py update` makes the library match it. `python perseus.py remove ID` takes a work off.

## Two sites, one build

`python perseus.py build` makes two folders inside `site/`:

| Folder | What it is | Deployed |
|---|---|---|
| `site/public/` | every text except `corpus/library/private/` | yes |
| `site/local/` | an overlay for this computer: the catalog, the private texts (and every page of a work that has one, since a private translation adds an edition and a Compare page), the library and search pages that list them, and the sync report | never |

`python perseus.py edit` serves `site/local/` first and `site/public/` for everything else, so text pages are
never copied or built twice. `python perseus.py build --public` makes only `site/public/`.

Builds are **incremental**: a work's pages are made again only when its Markdown, its edit rules or the page
code changed (the record is in `site/cache/`). Nothing changed: about 2 seconds. One text changed: about 1.
A first build, or one after editing `tools/reader/build.py`, `library.py` or `edits.py`: a few minutes.

## The catalog and edit mode

`python perseus.py edit` opens http://127.0.0.1:8790 with these extras (added by the local server, not in any
built page):

- **Catalog**: *Works in public domain repositories*. Perseus and Wikisource so far, with a repository
  filter, "with English", and "hide works on my shelf". **Add** puts a Perseus work on the shelf, or downloads
  a Wikisource work in both languages. A status bar shows progress.
  `python tools/wikisource_catalog.py` refreshes the Wikisource list.
- **Import…**: raw Markdown, or a PDF or EPUB book, from `corpus/catalog/inbox/`. For a book the panel lists
  the verse parts, with pages and line numbers; choose one, preview, then import to **Private**
  (`corpus/library/private/`, this computer only) or **Library** (`corpus/library/own/`, published).
- **Alt-click a paragraph** to delete it. For Perseus texts this is a rule in `corpus/library/edits.tsv`
  (they are regenerated); for your own texts you can simply edit the file.
- **Rebuild** and **Publish** (build, commit the edit rules and `corpus/library/own/`, push, deploy `site/public/`).

Every import or download is a draft that needs a short revision by hand. **How texts are formatted, how two
texts are paired, and the routine for finishing each one is in [TEXTS.md](corpus/catalog/TEXTS.md).** The markup
itself is in [SPEC.md](corpus/catalog/SPEC.md).

## Your own texts

A Markdown file in `corpus/library/own/` that follows [SPEC.md](corpus/catalog/SPEC.md) is part of the library,
listed under its author beside the Perseus texts. To pair a translation with an original, give both the same
`work:` and the same citation keys; a translation of a Perseus work takes that work's id (`phi1276.phi001` for
Juvenal's Satires) and pairs with the Perseus original automatically. Wikisource EPUBs can also be converted with

```powershell
python perseus.py import-wikisource Dyskolos.epub --work menander.dyskolos --lang grc --author Menander --title Dyskolos
```

Folders carry meaning: `own/` is published, `private/` never is, `perseus/` is generated, `inbox/` is for raw
files. Only `corpus/library/` is built. See TEXTS.md, section 3.

## Publishing (Cloudflare Pages)

The built site is about 700 MB, too big for git, so `site/public/` is uploaded directly to
[Cloudflare Pages](https://pages.cloudflare.com/) (free plan: unlimited bandwidth, 20,000 files, 25 MB per
file). First time only: `npx wrangler login`. Then:

```powershell
.\tools\deploy.ps1            # upload site/public/ as it is
.\tools\deploy.ps1 -Build     # build the public site first, then upload
.\tools\deploy.ps1 -Update    # re-run everything for the shelf, then build and upload
.\tools\deploy.ps1 -Check     # check site/public/ against Cloudflare's limits, upload nothing
```

Only changed files are uploaded after the first deploy. The script refuses a site that carries local markers
(`_local`, `_private`) or has no fonts. The Greek word-form data is **CC BY-NC**, so the published site must
stay non-commercial: no ads, no charging. Keep copyrighted texts out of `corpus/library/own/`; use `private/`.

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
dictionaries and Wiktionary; incremental builds and the public/local split; phone layout; one folder
structure with every path in one file.

Next: a proper Latin form table; non-Perseus alignment modes (paragraph and chapter pairing with a
manual check); an explicit `role: original | translation` and `visibility` in the front matter instead of
reading them from folders and language codes.
