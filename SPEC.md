# Library format

Every text the reader shows is a Markdown file in `library/`. Converters write these files
(`library/perseus/` from Perseus, `library/own/` from Wikisource or by hand), and the builder
reads only these files. Converters can change, and the reader can be restyled, without the
library files ever needing to change.

## Header

```markdown
---
id: tlg0006.tlg012.perseus-grc2     # unique; for your own texts anything readable
work: tlg0006.tlg012                # files with the same work are shown side by side
author: Euripides
title: Electra                      # title for the index (usually English)
label: Ἠλέκτρα                      # title in the original, shown beside it
edition: Gilbert Murray             # editor or translator, a name only
language: grc                       # grc or lat = an original (left column); anything else = a translation
layout: verse                       # verse | prose
numbering: explicit                 # explicit | auto | auto-by-section (verse only, see below)
source: PerseusDL/canonical-greekLit/data/tlg0006/tlg012/tlg0006.tlg012.perseus-grc2.xml
---
```

`work` is what pairs an original with its translations. Perseus works use their catalog id
(`tlg0006.tlg012`). For your own texts, pick any id; if your text translates a Perseus work,
use that work's id and it pairs with the Perseus original automatically.

## Body

| Markup | Meaning |
|---|---|
| `## Book 1` | section: large heading, listed in the contents sidebar |
| `### Strophe` | label: a small heading inside a section |
| `**Electra**` (a line on its own) | speaker |
| `*(He goes out.)*` (a line on its own) | stage direction or other aside |
| `{{150}}`, `{{1.150}}`, `{{17a}}` | a citation key; only the last part is displayed |
| `{{+}} text` | verse: a half line that shares the previous line's number |
| `{{gap}}` (a line on its own) | lacuna |
| `> line` | prose: a quoted verse line |
| `¶ text` | verse: a prose paragraph inside a verse text (not numbered) |
| `*word*` | italics |
| `text[^3]` … `[^3]: note` | a note; ids starting with `a` (`[^a12]`) are critical apparatus, hidden until the Apparatus button is on |
| `\#`, `\>`, `\**` at line start | literal characters, not markup |

**Verse** (`layout: verse`): one line per line; a blank line is a stanza break.
- `numbering: explicit`: a line is numbered only if it starts with `{{n}}`.
- `numbering: auto`: lines are counted; a `{{n}}` resets the count (use it where the printed
  numbering jumps or where the edition prints a number).
- `numbering: auto-by-section`: as `auto`, but the count restarts at each `##` and keys become
  `section.line` (`2.150`), as for Homer and Vergil.

**Prose** (`layout: prose`): paragraphs separated by blank lines; keys sit inline where a
section or chapter begins.

## How syncing works

Keys are matched exactly between the original and the translation: `{{1.150}}` on the left
pairs with `{{1.150}}` on the right. The builder keeps the keys both sides share in the same
order, cuts both texts at each one, and lays the pieces out side by side. In **Blocks** mode
pieces are grouped into passages (speeches, paragraphs); in **Lines** mode every shared key
starts a new row.

So keys have to be written the same way on both sides. Perseus texts already agree. For your
own texts, use the citation system of the original (Bekker, Stephanus, Diels–Kranz fragment
numbers, book.line). `site/_sync.md` lists, for every pairing, how many of the translation's
keys found a partner; anything under 90% is flagged when you build.
