---
name: bilingual-book-builder
description: Build per-chapter Polish → Ukrainian study markdown from EPUB, PDF, or plain-text sources. Polish is the source text and Ukrainian is translated from Polish; English is neither required nor emitted. Use when starting a bilingual PL/UA book, extracting a chapter, preparing or verifying chapter-NN.md, or translating Polish units into Ukrainian. Not for HTML/audio readers or vocabulary sheets; use bilingual-audio-reader or bilingual-vocabulary-builder for those.
---

# Bilingual book builder (PL → UA)

Pipeline: source book → **this skill** → `chapter-NN.md` + `book.json` → `bilingual-audio-reader` → `bilingual-vocabulary-builder`.

## Output format

```markdown
# «Book» — Chapter 3: Polish chapter title
<!-- bilingual study edition: PL → UA -->

**PL:** Polish sentence(s).

**UA:** Ukrainian translation of the PL line.

---
```

Each unit contains exactly one PL and one UA line. `---` separates source paragraphs. Chunk PL at sentence boundaries to at most 300 characters. Keep footnote markers inline as `<sup>N</sup>` in both languages. Use UTF-8, no BOM, LF, and a trailing newline.

## Source roles and setup

### Bookcast repository layout

Keep each book's working sources under `src/<book-slug>/` and reserve
`public/<book-slug>/` for files intended to be published. Point `--root` at the
source directory (for example, `src/pies-baskervilleow`); keep `book.config.json`,
source books, `work/`, and built `chapter-NN.md` files there. Do not create or
build study Markdown under `public/`. The audio-reader and vocabulary workflows
publish their HTML outputs separately.

- **PL is authoritative** and must not be rewritten beyond whitespace normalization.
- **UA is translated from PL.** An optional Ukrainian reference edition may guide names, terms, and register, but do not copy its sentences.
- No English file, text, or alignment is used by this workflow.
- Ask only for unclear details: book folder, Polish source, title/author, chapter numbering, and header format.
- Create `book.config.json` with `book`, `author`, `header`, `chapters`, and `sources.pl`; optional `sources.ua_reference` is for terminology guidance only. Use the examples in `references/` as a starting point, replacing the former English source with the Polish source.
- EPUB: inspect entries first (`unzip -l`). `file` is a regex over entry names with `{n}` replaced by chapter number plus offset; configure `container`, `cut`, and `title_re` as needed.
- PDF/TXT: configure `heading`, optional `start_after`, `strip_lines`, `char_map`, `para_mode`, `dehyphenate`, and `title_re`. Scanned PDFs need OCR first.

The source adapters are in `scripts/book_sources.py`; the PL/UA CLI is `scripts/bilingual.py`. Before processing, run `python3 <skill>/scripts/bilingual.py list --root src/<book-slug>` and spot-check the first and last paragraphs. Stop and show the user if the chapter count or extraction looks wrong.

## Per-chapter workflow

1. Prepare a chapter with `python3 <skill>/scripts/bilingual.py prepare N --root src/<book-slug>`. Polish paragraphs are split into sentence-sized chunks; report any chunking limitations. Unit numbers are used as reader anchors.
2. Fill `work/chapter-NN/scaffold.txt`, translating each PL unit into UA. The CLI preserves completed scaffolds on reruns; do not silently reuse them if the unit count has changed.
3. Translate every PL unit into natural literary Ukrainian. Preserve meaning, register, dialogue dashes, clause coverage, names consistently, footnote positions, and number/date/measure values. Do not merge, split, summarize, add, or omit content in UA.
4. Assemble and verify with `python3 <skill>/scripts/bilingual.py build N --root src/<book-slug>` (or `verify N` after edits). The CLI checks unit parity and exact PL reassembly. Review markers, punctuation, UA/PL length ratios, and translation quality; mechanical checks cannot establish semantic fidelity.
5. Maintain `book.json` with title, author, chapter number, Ukrainian spoken chapter name, and optional reader/vocab filename patterns. Do not commit generated book files unless asked. Stop after one chapter and ask whether to continue.

## Translation checks

- Use Ukrainian «…» quotes where appropriate; retain Polish `„…”` in PL.
- Keep name transliterations consistent in `work/glossary.tsv`; add a Latin original in parentheses only on first mention when useful.
- Avoid Polish diacritics or Latin leftovers in Ukrainian except deliberate originals and initials.
- Record uncertain archaic words or idioms for the report.
- Never run the audio/vocabulary pipeline unless requested.

## Report per chapter

Report extracted paragraphs, unit count, merges, over-limit units, glossary additions, uncertain translations, verification results, files written, and anything not checked.
