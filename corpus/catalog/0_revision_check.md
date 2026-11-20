# Format and revision check

Paste this whole file, then the text or text pair to check. It states the file format, the error categories to
look for, and what to output: a short list of the problems and **a runnable revision script that applies the fixes**.

## Your task

You are checking a text file (or an original and its translation) against the format below and against each
other. Find real problems only. Do not rewrite, modernize or improve the text. Never invent content: if something
is missing from the source you were given, say so and leave it out of the script. Keep every `{{key}}` exactly as
it is unless the fix is about the key.

Your output has three parts, in this order:
1. a **summary**: counts by category, and one line saying whether the text is ready or what to fix first;
2. the **issues**, one short entry each (see "Issues");
3. one **revision script** that applies every fix that can be made from the text alone (see "The revision script").

## The format

A text is one Markdown file: a header, then the body.

```markdown
---
id: ws.the-bet.eng-wikisource   unique, ascii
work: ws.the-bet                files with the same work are shown side by side
author: Anton Chekhov
title: The Bet                  English title
label: Пари                     title in the original language
edition: Garnett                editor or translator, a name only
language: eng                   grc | lat | eng | it | fr | ru | ...
original: ru                    only on a translation of a non-Greek, non-Latin original
layout: prose                   prose | verse
numbering: explicit             explicit | auto | auto-by-section   (verse only)
source: https://...
---
```

Body markup, one construct per line unless stated:

| Markup | Meaning |
|---|---|
| `## Book 1` | section heading (listed in the contents) |
| `### Strophe` | small label inside a section |
| `**Electra**` alone on a line | speaker |
| `*(He goes out.)*` alone on a line | stage direction or aside |
| `{{150}}` `{{1.150}}` `{{17a}}` | a pairing key; only the last part is shown |
| `{{+}} text` | verse: half line sharing the previous line's number |
| `{{gap}}` alone on a line | lacuna |
| `> line` | prose: a quoted verse line |
| `¶ text` | verse text only: an unnumbered prose paragraph |
| `*word*` | italics |
| `text[^3]` and `[^3]: note` | a note; ids starting with `a` (`[^a12]`) are critical apparatus |
| `\#`, `\>`, `\**` at line start | a literal character, not markup |

Layout rules:
- **verse:** one line per line; a blank line is a stanza break. `numbering: explicit` numbers only lines
  that start with `{{n}}`; `auto` counts lines and `{{n}}` resets the count; `auto-by-section` restarts the
  count at every `##` and keys become `section.line`.
- **prose:** paragraphs separated by blank lines; keys sit at the start of the paragraph or chapter they number.

Keys pair an original with its translation:
- Keys must be **the same string on both sides** (`{{1.5}}` pairs with `{{1.5}}`, not `{{1.05}}`, `{{I.5}}`, `{{5}}`).
- They must appear **in the same order** on both sides.
- Use the citation system of the original: line numbers for verse; Stephanus or Bekker pages; Diels-Kranz
  or collection numbers for fragments; `book.chapter` for prose; chapter numbers for stories and novels.
- Unkeyed text is fine (it rides with the nearest key). A key on one side only is harmless but lowers the match.

## Error categories

Use these codes. Look for each; report only what you can point to in the text.

**S, Structure.** Text that is not part of the work: licence or copyright lines, "Contents", navigation
words ("Next", "Previous", "↑"), repeated titles, the page's own heading as a paragraph, translator's
notes mixed into the body. A heading that is really a paragraph (`{{2}} I.`) or a paragraph that is really
a heading. Chapters out of order, duplicated, or missing.

**K, Keys.** Keys that do not match the other side (format, number, offset); keys out of order; a key
missing at a chapter or section start; keys in the middle of a sentence; the same key used twice; keys on
headings instead of the first paragraph; hierarchical keys that mix styles (`1.1` and `1`).

**V, Verse and prose.** Verse run together as one paragraph, or prose broken into short lines; stanza breaks
missing or doubled; `layout` or `numbering` that does not match the body; speaker or stage direction
not on its own line; a half line (`{{+}}`) numbered as a full line.

**T, Text.** Encoding damage (`�`, `Ã©`, `â€™`), doubled or missing spaces, hyphenation left over from a
printed line break, words run together, straight quotes mixed with curly, stray digits or page numbers,
bracketed editorial marks that are not part of the text, truncated sentences.

**N, Notes.** A `[^n]` mark without its `[^n]:` definition or the reverse; note text left in the body;
apparatus marked as ordinary notes; notes dropped by a converter (the original has them, this file does not).

**M, Metadata.** Missing or placeholder author (`Various`, `0`); `edition` that is not a name; `language`
wrong for the text; `original:` missing on a translation of a non-Greek/Latin original; `work` that differs
from the other file of the pair; `id` not unique; `label` not in the original language.

**F, Fidelity (only when both original and translation are given).** Compare section by section, key by key.
- **F1 omission:** something in the original is absent from the translation.
- **F2 addition:** something in the translation is not in the original.
- **F3 mistranslation:** the meaning differs (wrong word, reversed sense, wrong person or number, a negative lost).
- **F4 names and numbers:** a name, place, date or figure that differs.
- **F5 order or structure:** passages swapped, merged or split so that they no longer correspond.
- **F6 register:** archaism, calque or padding that the original does not have ("hath", word-for-word
  rendering that reads as non-English). Report only if it hides the meaning or is inconsistent within the text.

## Issues

List them most serious first, one entry each, short:

```
S1  Where: {{2}} / first 8 words   Quote: "…"   Problem: one sentence   Sure: high|medium|low
```

- Quote exactly. Every **F** item quotes both the original and the translation.
- The fix is not written here: it goes into the script, under the same ID.
- Do not flag stylistic preference. Do not list the same pattern more than three times: say "and N similar"
  with the keys, and fix all of them in the script.
- Do not "correct" a faithful but unusual translation of a difficult original. List it as `low` and do not
  put it in the script.
- If a fix needs knowledge you do not have (an author, a missing passage), list it as `need: <what>` and leave
  it out of the script.

## The revision script

Write **one script** that, run on the file(s), produces the revised text. It must never touch the original.

**Choose the method that fits the job:**
- **Python 3 (standard library only)** is the default: it works on Windows, Mac and Linux, reads UTF-8 reliably and
  handles any number of changes. Use it for most outputs, and always when keys change in both files of a pair, or
  when paragraphs are merged, split or reordered.
- **PowerShell** only if the user says they are on Windows and the fixes are plain find-and-replace or line
  deletions.
- Anything simpler (a single `sed` command, a unified diff for `patch`) only if it is clearly the easiest and
  safest way to make one or two changes. Say which method you chose and why in one line.

**The script must:**
1. Take the input path(s) as arguments (a pair: the original's path, then the translation's).
2. Read as UTF-8 without BOM, keep the file's existing line endings, and write the result next to the input as
   `<name>.revised.md`. Never overwrite the input.
3. Make each change by an **exact quote** of the text to find (never by line number), and check that the quote
   occurs exactly once (or the stated number of times). If it does not, skip that change, print its ID as
   `NOT APPLIED`, and carry on.
4. Label every change with its issue ID in a comment, so the script reads as the issue list made executable.
5. Leave all `{{keys}}`, headers and unrelated text untouched; change a key only for a K issue, and in both files
   of a pair together.
6. Print a summary (applied, not applied) and then a unified diff of what changed, so it can be reviewed
   before the revised file replaces the original.
7. Use no network and delete nothing but the text the fixes name.

Put the script in one fenced code block, then give the exact command to run it, for example
`python revise.py "ws.the-bet.ru.md" "ws.the-bet.eng.md"`.

## What to send

- **One file:** the whole file if short; otherwise one `##` section at a time, with the header.
- **A pair:** the header of both files, then one section of each in the same order, with the keys intact. Keep each
  section to what fits comfortably, and repeat for the next section. Ask for one script per section, or for one
  script that you extend.
- Say the language of each text and, if known, the edition. Say whether the user is on Windows.
