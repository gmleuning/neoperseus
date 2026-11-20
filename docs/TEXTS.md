# Texts: how they are formatted, how two texts are paired, and how to finish each one by hand

This explains the whole path from "a text arrives from somewhere" to "it reads correctly beside its
original or translation on the site". It assumes what is true in practice: **every download or import
arrives with irregularities, and each one needs a short, individual last-mile revision.** The system is
built around that. Nothing is expected to be perfect automatically, and nothing is hidden when it is not.

[SPEC.md](../SPEC.md) is the format reference (the markup, one line each). This is the practice: why the
format is what it is, what each source tends to get wrong, and the routine for fixing it.

---

## 1. The idea in one page

1. **One Markdown file per text** is the only thing the site is built from. The builder reads Markdown
   and nothing else. An import, a download, a PDF conversion and a hand-typed file all end up as the
   same kind of file, so they are all revised the same way.
2. **A draft is a file you will edit.** Importers make their best guess and then stop. You open the
   file, fix it, rebuild (seconds), and look at the page. There is no "re-import and lose my fixes"
   step for your own texts (see section 8 for the one exception, Perseus).
3. **Two texts are paired by shared keys, not by position or by language.** A key such as `{{1.150}}`
   written in both files is a hinge: the page is cut at every key both files share, and the two pieces
   are laid side by side. Where keys are missing or do not match, nothing is lost. The text simply pairs
   in bigger blocks.
4. **Every build reports how well each pair matched** (`site-local/_sync.md`, and a `check sync:` line
   printed when a pair is under 90%). That number is your to-do list.
5. **Public, private and generated are decided by folder** (section 3), so a revised text is also a
   decision about who may see it.

---

## 2. Anatomy of a text file

```markdown
---
id: ws.the-bet.eng-wikisource      # unique; for your own texts anything readable
work: ws.the-bet                   # files with the same work are shown side by side
author: Anton Čechov
title: The Bet                     # the title in the index (English)
label: The Bet                     # the title in the original language, shown beside it
edition: Garnett                   # a name only: editor, translator or "Wikisource"
language: eng                      # grc, lat, eng, it, fr, ru ...
original: ru                       # only on a translation of a non-Greek, non-Latin original
layout: prose                      # prose | verse
numbering: explicit                # explicit | auto | auto-by-section (verse only)
source: https://en.wikisource.org/wiki/The_Bet_(Chekhov/Garnett)
---

## Chapter I

{{1}} It was a dark autumn night. The old banker was walking up and down his study …

A paragraph without a key is just a paragraph.
```

The fields that matter for pairing:

| Field | What it decides | Common mistake |
|---|---|---|
| `work` | which files share a page. Same `work`, same page. | Two files with different `work` ids never meet, however alike they look. |
| `language` / `original` | which file is the left column (the original) and which the right (the translation). Greek and Latin are always originals. Any other non-English language is an original unless the file says `original:`. | An English translation of Italian that lacks `original: it` is still correct (English is a translation by default), but a French translation of an Italian poem needs `original: it`. |
| `layout` | `verse`: one line per line, blank line between stanzas. `prose`: paragraphs separated by blank lines. | A poem imported as prose collapses its lines into one paragraph. |
| `numbering` | verse only. `explicit`: a line is numbered only if it begins with `{{n}}`. `auto`: lines are counted and a `{{n}}` resets the count. `auto-by-section`: the count restarts at every `##`, keys become `section.line`. | `explicit` on a long poem with no keys: nothing to pair. Use `auto` or `auto-by-section`. |
| `id` | the identity used by edit rules (section 8) and by the sources of each page. Must be unique. | Copying a file and forgetting to change it. |

Body markup (full list in SPEC.md): `## Heading` is a section in the contents list; `### Label` is a small
heading; `**Speaker**` alone on a line; `*(stage direction)*` alone on a line; `*italics*`; `{{key}}`
a pairing key; `[^n]` / `[^n]: note` notes; `¶` a prose paragraph inside verse; `{{gap}}` a lacuna.

---

## 3. Where a file lives decides what it is

| Folder | Meaning | Published? | Committed? |
|---|---|---|---|
| `library/perseus/` | converted Perseus texts. **Generated**, replaced on the next conversion. | yes | no |
| `library/own/` | texts you add and revise. **Yours**, edit freely. | **yes** | yes |
| `library/private/` | texts you may read but may not publish (in copyright). | never; local only | no |
| `library/additions/` | the inbox: raw files, PDFs, EPUBs, old scripts. | not unless a file has a `work:` header | no |
| `library/preowned/` | files that came from elsewhere and are not sorted yet. | same rule as `additions/` | no |

Two consequences you should keep in mind:

- **Everything the catalog Add button imports goes to `library/own/`, which is published.** Wikisource is
  mostly public domain, but a translation on Wikisource can still be in copyright in your country, and an
  import may carry text you did not mean to publish. If in doubt, **move the file to `library/private/`**
  before you do anything else. (Publish commits `library/own/`.)
- A file with a `work:` header is built wherever it sits under `library/`, even in `additions/`. If you do
  not want it on the site, take the header off or move it.

The public site (`site/`) is built without `library/private/`. The local overlay (`site-local/`, served
by `python perseus.py edit`) adds it. See README, "Two sites, one build".

---

## 4. How two texts become one page (the reconciliation, in plain words)

Given an original (left) and a translation (right) with the same `work`:

1. The builder lists the keys in each file (`{{…}}` markers, and the numbered lines of verse).
2. It keeps the keys **present in both**, and among those it keeps the longest run that appears **in the
   same order in both files**. (If the translation has a section moved, or a key out of order, that
   key drops out; the others still pair.)
3. It **cuts both files at each kept key** and lays the pieces side by side. The page is a row of such
   pieces: this is what Blocks mode groups into passages and Lines mode shows one per row.
4. Everything between two kept keys, in each file, stays together in that row: unkeyed paragraphs,
   headings, notes. **Text is never dropped for lack of a partner**; it just rides along in the nearest
   row.
5. Only the last part of a key is shown. `{{2.150}}` appears as 150, and the `2.` is only there so that
   book 2's line 150 does not pair with book 1's.

What this means in practice:

- **Matching is exact text.** `{{1.5}}` pairs with `{{1.5}}`, not with `{{1.05}}`, `{{I.5}}` or `{{5}}`.
- **Order matters, spelling of the rest does not.** The words around a key can be anything.
- **A key belongs at the start** of the paragraph (prose) or line (verse) it numbers.
- **Few shared keys is not an error, it is a coarse page.** Two texts with no shared keys at all sit in
  one big block each, still side by side. For a short work that can be the right answer.
- **Coverage** (the percentage in `_sync.md`) is *keys shared ÷ keys in the translation*. Extra keys in the
  original do not lower it; keys in the translation that the original lacks do.
- **Verse translations with their own line numbers** (a translation whose line 150 is not the original's
  line 150) are placed *approximately*: proportionally between the keys they do share, and at each
  change of speaker. The report marks these `approximate`; they are expected to be imperfect.

### Choosing the key system for a pair

Use the **citation system of the original**, so a reader can cite it:

| Kind of text | Keys |
|---|---|
| Drama, epic, any verse | line numbers (`auto` or `auto-by-section`). For epic, `book.line`. |
| Dialogue, philosophy | Stephanus or Bekker pages (`{{17a}}`, `{{1094a}}`). |
| Fragments | Diels–Kranz or the standard collection number (`{{B12}}`, `{{12}}`). |
| History, speeches, treatises | `book.chapter` or `chapter.section` as the editions print them. |
| A novel, a story, a Bible book | chapter numbers (`{{1.14}}`), or paragraph numbers if the two have the same paragraphs. |
| Nothing better exists | key only the first paragraph of each chapter, or leave unkeyed. |

---

## 5. What each source gets right and wrong

Each source fails in its own, predictable ways. Check those first.

### Perseus (the shelf; `python perseus.py add …`)

- **Reliable:** keys. The original and its translations come out of the same citation scheme.
- **Typical defects:** a translation with its own line numbering (placed approximately); front matter
  and prefaces to remove; notes that are fine in one edition and absent in another.
- **Revision:** edit rules, not the file (section 8), because the file is regenerated.

### Wikisource through the catalog (Add, `reader/wikisource_fetch.py`)

- **What it does.** The original is the catalog row's page on its own Wikisource (a chapter list if it
  has subpages, otherwise the one page). The English side is found by reading the hub page on English
  Wikisource and taking the first listed page that really is a translation of that work (a page named
  `Hub (Translator)`, `Hub/…` or `Collection/Hub`), never an anthology that merely links to it. Each page
  is read through the MediaWiki API. Poems (`div.poem`) become verse, everything else prose. Chapters are
  keyed from the numbers in their titles (Roman, Arabic or spelled out: `Chapter XIV`, `Capítulo 3`,
  `Libro primero`), as `{{n}}` or `{{part.n}}`. The log says which translation it chose.
- **Typical defects:**
  - *The wrong translation:* the first valid one wins. Check `edition:` and `source:`. To use another,
    run **+ translation** with its address.
  - *Author:* often `Various`. Set it by hand.
  - *Title lines inside the text:* `UNA SCOMMESSA`, `I.` and similar arrive as ordinary paragraphs.
  - *Footnotes are dropped.* The fetcher removes Wikisource's reference markers and notes.
  - *Verse numbers inside Bible-like pages* stay inside the paragraph; they are not turned into keys.
  - *Unequal paragraph counts.* If original and translation are each a single prose page and the
    paragraph counts differ, the builder pairs them as one block (key `{{1}}` only) rather than
    mispair them. The log line reads "different numbers of paragraphs".
  - *Chapter splits that differ* between editions (a Spanish edition with 52 chapters beside an English
    one with 53): the keys shared are fewer; coverage tells you.
  - *Mojibake and oddities* (`�`, doubled spaces, stray `↑`).
- **Revision:** section 7.

### Wikisource EPUB export (`python perseus.py import-wikisource FILE.epub --work ID`)

The older route, kept for texts the API route cannot reach. It keeps footnotes as notes, turns "Fragment
12" headings into keys, and counts verse lines, with printed numbers as keys. Review the headings and the
`check: line printed as …` messages it prints.

### Books (PDF, EPUB) through Import… in edit mode

- Built for plays and verse with margin numbers: speakers in capitals, stage directions in parentheses,
  strophe headings, a line number every five lines, textual notes keyed by line number.
- **Typical defects:** the guess of author, title, translator and original; the verse parts it picks
  (the Import panel shows them best first, so check); page headers and footers that survive; a
  speaker that is really a heading. A PDF with `U+FFFD` stands for dashes and indents; the importer maps
  those to dashes, but look.
- **Revision:** the panel's *Leave out lines containing* field (comma-separated; it starts as `||`, which drops a critical apparatus) removes unwanted lines before you save; after that,
  edit the file.

### Your own Markdown, pasted or dropped

Files with no front matter open as an English text named after the file (on this device) or import with a
guessed header (edit mode). You write the keys. This is the most controllable route and the least
automatic.

---

## 6. The kinds of irregularity, and what each one looks like

| Kind | How it shows | Where to fix |
|---|---|---|
| **Structure:** front matter, licence blocks, tables of contents, duplicated headings, a heading that is really a paragraph | the contents list is wrong; odd first rows; a stray `{{2}} I.` | the file |
| **Alignment:** keys that do not match, appear in a different order, or exist on one side only | coverage under 90%; passages that do not face each other | the keys in either file |
| **Text:** mojibake, quotation marks, hyphenation, run-together words, a missing book | something looks wrong while reading | the file |
| **Metadata:** author, edition, language, `original`, `layout` | wrong column; wrong index entry; poem as a paragraph | the front matter |
| **Notes and apparatus** | missing or misplaced footnote marks | the `[^n]` marks and definitions |
| **Publication status** | the text appears where it should not | the folder (section 3) |

---

## 7. The last-mile routine, one text at a time

Do this per text. It takes minutes once you know where to look, and each step is cheap to repeat because
builds are incremental (only the work you changed is rebuilt).

1. **Put the file where it belongs.** Decide `own` (publish) or `private` (never). Move it before
   anything else if it came from Add.
2. **Build.** `python perseus.py build`. The last lines list every pair under 90% and any edit rules that
   no longer match.
3. **Read the sync report.** Open `site-local/_sync.md`: one row per pair with `shared`, `translation
   numbers`, `coverage`.

   | Coverage | Usually means | First thing to do |
   |---|---|---|
   | 90 to 100% | fine | read it once for structure |
   | 50 to 90% | one section is out of step: a missing chapter, a different division | compare the keys around the first gap (below) |
   | under 50% | the two use different key styles, or one side has none | list the keys of both files (below) |
   | 0 | the files are not paired (`work` differs) or the keys are written differently (`1.1` against `1`) | check `work`, then the key style |
   | one row, 1 of 1 | paired as a single block (no usable keys) | decide if that is acceptable (below) |

4. **Look at the keys.** In PowerShell, from the repository folder:

   ```powershell
   Select-String -Path "library\own\ws.the-bet.*.md" -Pattern '\{\{[^}]*\}\}' -AllMatches |
     ForEach-Object { "$($_.Filename): " + (($_.Matches | ForEach-Object Value) -join ' ') }
   ```

   That prints each file's keys in order. The first place the two lists disagree is where the pairing
   breaks.
5. **Open the page** (`python perseus.py edit`, the work's page). Read the first screen and the end, switch
   Blocks and Lines, scan the contents list. Things to catch: a first row that is only a title, a heading
   in the middle of a paragraph, a poem that has run together, a passage with no partner opposite.
6. **Fix the file.** Edit `library/own/….md` (or `private/`) in any editor. Common repairs:
   - **Delete what is not text.** Licence lines, "Contents", repeated titles, the page's own heading.
     In edit mode you can Alt-click a paragraph to delete it as a rule (section 8). In your own file,
     just delete the lines.
   - **Fix a heading that became a paragraph** (`{{2}} I.`): make it `## I` and remove the key.
   - **Make the keys agree.** Pick the coarsest system both texts share (section 4) and write it in
     both files. If the originals and translation divide differently, use the one the *translation*
     can follow, and drop keys the other side does not have.
   - **Pair paragraph by paragraph when the counts are equal; otherwise by chapter.** If a pair came as
     one block because the paragraph counts differed, merge or split paragraphs in one file until the
     counts match, then key each paragraph `{{1}}`, `{{2}}` … on both sides. If you will not do that,
     key only the chapter starts.
   - **Set the metadata:** real `author`, correct `edition`, `language`, `original`, `layout`,
     `numbering`.
   - **Re-add notes** the fetcher dropped, as `[^n]` in the text and `[^n]: …` at the end.
7. **Rebuild and look again.** Only this work is rebuilt, in about a second. Repeat steps 3 to 7 until the
   coverage and the page are acceptable. "Acceptable" is your call: a one-block pair of a short story is
   fine; a drama with 40% coverage is not.
8. **Keep a record if you reviewed the translation itself.** For a text you have proofread against its
   original, write a short log in `reviews/<work>-<part>.md`: each change, its category (mechanical,
   style, fidelity to the original), and what you left alone and why. The Book IV review of Martianus
   Capella (`reviews/martianus-book4.md`) is the model.
9. **Publish** when satisfied (Publish in edit mode, or `.\deploy.ps1 -Build`). Publish builds `site/`
   without private texts, commits `library/edits.tsv` and `library/own/`, pushes, and deploys `site/`.

### A worked example: "The Bet"

The catalog row *The Bet* (Russian) was added. The log said:

```
[ru] reading Пари (Чехов)
[en] looking for a translation of The Bet
[en] trying translation: The Bet (Chekhov/Garnett)
the two texts have different numbers of paragraphs, so they are paired as one block
```

`_sync.md` reported 1 of 1 (100%), which really means "one block each". Two things to improve, in
`library/own/ws.the-bet.ru-wikisource.md` and `ws.the-bet.eng-wikisource.md`:

- The English begins with title lines that became paragraphs (`{{1}} THE BET`, then `THE BET`, then `I`).
  Delete the repeated title and turn `I` into a heading `## I`. Check the Russian for the same.
- The two have different numbers of paragraphs: somewhere one text has a paragraph break the other does
  not. Find it by reading both side by side, merge the two paragraphs in one file (or split the other),
  until the counts are equal. Then key every paragraph `{{1}}`, `{{2}}` … on both sides.

After saving, `python perseus.py build` rebuilds only this work and the coverage becomes the true
paragraph-level figure, which you can now trust.

---

## 8. Edits: in the file, or as rules

| Where the text lives | How to change it |
|---|---|
| `library/own/`, `library/private/` | **edit the file.** It is yours and is never regenerated. |
| `library/perseus/` | **an edit rule** in `library/edits.tsv`, because the file is replaced the next time the work is converted. Alt-click a paragraph in edit mode, or write the rule by hand. |

An edit rule is `text id<TAB>delete<TAB>opening words of the paragraph`. It finds the paragraph by its
opening words as the reader shows them (without keys, note marks or markup), so it survives a
re-conversion. If upstream changes the text, the build prints `edit not applied (text changed?)` and
lists the rule; fix or remove it.

If you want to make *substantial* changes to a Perseus text, copy the converted file to `library/own/`,
give it a new `id`, change its `work`, and edit it there; it is then yours.

---

## 9. What the system does not do

- It does not translate or align by meaning. Pairing is only by keys you or the source provide.
- It does not merge two editions of the same language into one text, or decide which translation is
  better. Several translations of one work each get a page (a Compare view puts two beside the original).
- It does not check the *content* of a translation against the original. Section 7, step 8, is how you
  do that, and it is manual.
- It does not keep Wikisource's footnotes through the API route, or verse numbers inside Bible-style pages.
- It does not decide copyright. The folder you put a file in is your decision, recorded by where it sits.

## 10. Quick reference

```powershell
python perseus.py build                  # public site and local overlay; only changed works rebuilt
python perseus.py build --public         # only site/ (what is deployed)
python perseus.py edit                   # http://127.0.0.1:8790: Catalog, Import…, Alt-click delete, Rebuild, Publish
python perseus.py find euripides         # find a Perseus work id
python tools/wikisource_catalog.py       # refresh the Wikisource list in the catalog
.\deploy.ps1 -Build                      # build site/ and upload it
.\deploy.ps1 -Check                      # check site/ against Cloudflare's limits, upload nothing
```

Files: `site-local/_sync.md` the pairing report; `library/edits.tsv` the edit rules; `reviews/` your
proofreading logs; `.buildcache/` what was built from what (safe to delete; the next build is just slower).
