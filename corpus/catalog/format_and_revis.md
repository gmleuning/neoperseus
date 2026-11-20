# Format and revision check (for an LLM)

Paste this whole file, then the text or text pair to check. It states the file format, the error
categories to look for, and how to report fixes. It is written to be used as-is as instructions.

---

## Your task

You are checking a text file (or an original and its translation) against the format below and against
each other. Report real problems only, each with a minimal fix. Do not rewrite, modernize or improve the
text. Never invent content: if something is missing from the source you were given, say so and stop.
Keep every `{{key}}` exactly as it is unless the fix is about the key.

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

## How to report

List issues, most serious first. For each:

```
ID      S1, K3, F2 ...  (category code + number)
Where   the key, or the first 8 words of the paragraph
Quote   the exact text that is wrong (short)
Problem one sentence
Fix     the exact replacement text, or "delete the line", or "add before <where>: <text>"
Sure    high | medium | low
```

Rules for reporting:
- Quote exactly; give the fix as text I can paste, not a description.
- If an original is given, every **F** item must quote both the original and the translation.
- Do not flag stylistic preference. Do not report the same pattern more than three times: say "and N
  similar" with the keys.
- Do not "correct" a faithful but unusual translation of a difficult original. Mark it `low` and explain.
- If a fix needs knowledge you do not have (an author, a missing passage), write `need: <what>` as the fix.
- End with a count by category and one line: whether the pair is ready, or what to fix first.

## What to send

- **Format check (one file):** the whole file if short; otherwise one `##` section at a time, with the header.
- **Fidelity check (a pair):** the header of both files, then one section of each, in the same order, with
  the keys intact. Keep each section to what fits comfortably; repeat for the next section.
- Say the language of each text and, if known, the edition.
