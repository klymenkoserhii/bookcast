---
name: bilingual-vocabulary-builder
description: Build a per-chapter Polish vocabulary sheet with Ukrainian glosses and clickable examples linked to the bilingual reader. Use when asked for a Polish glossary, vocabulary list/sheet, or the next chapter's vocabulary in a PL/UA book. Produces chapter-NN.vocab.md and a self-contained chapter-NN.vocab.html with PL, UK, and Example columns only—no English column. Requires the bilingual chapter markdown and reader.
---

# Bilingual Polish vocabulary builder

Pipeline: `bilingual-book-builder` creates `chapter-NN.md` → `bilingual-audio-reader` creates reader cards with `u-N` anchors → **this skill** builds the per-chapter vocabulary sheet.

## Output

Exactly two files per chapter: `chapter-NN.vocab.md` (source of truth, kept in `src/<book-slug>/`) and generated `chapter-NN.vocab.html` (published to `public/<book-slug>/`). No CSV unless requested. Work on one chapter, report, then ask whether to continue.

Markdown table columns, in order:

| PL | UK | Example |

- PL: lemma with grammar tags (noun gender/number; verb aspect), with no rows for inflected forms.
- UK: concise idiomatic Ukrainian gloss for the sense used in this chapter.
- Example: short Polish text copied verbatim from the PL unit, linked to its first occurrence in `chapter-NN.html#u-N`.
- Sort alphabetically by Polish using `vocab_build.py`; include a coverage note in the Markdown.
- HTML must be self-contained, mobile-friendly, usable from `file://`, with a theme toggle and no external URLs. Keep the table header non-sticky and the topbar `.title` element for index injection.

## Selection and workflow

Include attested vocabulary above A2, idiomatic/non-literal A1–A2 use, and non-compositional expressions. Exclude ordinary proper names, common Polish words unless their sense is unusual, and `się`/`nie`/`by` except unusual use. Drop uncertain lemmas rather than guessing.

1. Read every unit: `python3 <skill>/scripts/extract_units.py N --dir src/<book-slug> > scratch.txt`.
2. Confirm the reader has stable `u-N` anchors. The validator can add them with `--add-anchor` if needed.
3. Look up exact forms and contexts with `extract_units.py N --grep 'stem\\w*'` before selecting example fragments.
4. Create `items.tsv` with three TAB-separated fields: `lemma<TAB>UK<TAB>fragment`.
5. Build: `python3 <skill>/scripts/vocab_build.py N items.tsv --dir src/<book-slug> --html-dir public/<book-slug>`. Resolve every `MISSING` example.
6. Validate: `python3 <skill>/scripts/validate_vocab.py N --dir src/<book-slug> --html-dir public/<book-slug>`. Fix every FAIL and inspect every REVIEW hit.
7. If the book index exists, rebuild it from the source metadata into `public/<book-slug>/` so the vocabulary link is live and the page receives its contents back-link. Remove scratch files, check `git status`, report, and ask whether to continue.

## Quality checks and pitfalls

Translate UK from Polish context, not via English. Keep it concise, use Ukrainian apostrophes and Cyrillic, and re-read for typos. Derive lemmas from attested forms; do not invent examples. Every example must occur verbatim in its linked unit and point to its first occurrence. Fragments must be unique and at most 60 characters. Unit numbering is a public interface: if the chapter is re-chunked, regenerate the vocabulary and links.

The validator checks fragment existence/first occurrence, sorting, duplicate lemma/fragment, column count, HTML/Markdown row parity, external URLs, sticky headers, theme toggle, reader anchor and unit parity. Re-run it after any fix.

## Report

Link both files; state row/unit counts, anchor status, that no CSV was made, validator results, fixes, benign `possible_earlier` hits and reasons. Ask whether to continue with the next chapter.
