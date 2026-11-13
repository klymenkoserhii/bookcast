---
name: trilingual-book-builder
description: Build per-chapter trilingual study markdown (EN → PL → UA) from source book files (EPUB, PDF or plain text), including the Ukrainian translation, and write book.json. The chapter-NN.md output is the input of trilingual-audio-reader. Use when the user wants to start a new book or chapter, extract chapters from an EPUB/PDF/TXT, align English with Polish, translate Polish into Ukrainian, or verify or rebuild a chapter-NN.md. Not for vocabulary sheets (trilingual-vocabulary-builder) or HTML readers and audio alignment (trilingual-audio-reader).
---

# trilingual-book-builder

Pipeline: source files → **this skill** → `chapter-NN.md` + `book.json` → `trilingual-audio-reader` (HTML reader + audio sections) → `trilingual-vocabulary-builder` (per-chapter vocab sheets).

The tooling is `scripts/trilingual.py` (the CLI, standard library only) and `scripts/book_sources.py` (EPUB/PDF/TXT adapters). It grew out of the Baskerville book's `trilingual.py` and was made book-agnostic: sources, chapter count and header come from `book.config.json`.

## What it produces

`chapter-NN.md` in the book folder, exactly the format `trilingual-audio-reader` parses:

    # «Book» — Chapter 3: English chapter title
    <!-- trilingual study edition: EN → PL → UA -->

    > **EN:** English sentence(s).

    **PL:** Polish sentence(s).

    **UA:** Ukrainian translation of the PL line.

    ---

    > **EN:** next unit …

- One unit = one EN/PL/UA triple. The three counts are equal and there are no stray lines.
- `---` marks each Polish paragraph change.
- PL is chunked at sentence boundaries to at most 300 characters.
- `<!-- ALIGNMENT: ... -->` follows a unit only where EN and PL genuinely diverge (numbers, dates, measures, missing clauses, different order).
- Footnote markers stay inline as `<sup>N</sup>` (bodies omitted), in PL and UA alike.
- UTF-8, no BOM, LF, trailing newline.
- The header line comes from `book.config.json` (`"header": "# «{book}» — Chapter {n}: {title}"`). With an empty title the `: {title}` is dropped.

## Source roles

- **PL is authoritative.** The narrator reads it. Never edit it beyond whitespace normalisation.
- **EN** supplies each unit's EN line and drives the alignment.
- **UA is produced here**, translated from PL. An existing UA edition may be configured as `ua_reference` (names, terms, register only). Never paste its sentences.

## Step 0 — Book folder and config

### Bookcast repository layout

Keep each book's working sources under `src/<book-slug>/` and reserve
`public/<book-slug>/` for files intended to be published. Point `--root` at the
source directory (for example, `src/pies-baskervilleow`); keep `book.config.json`,
source books, `work/`, and built `chapter-NN.md` files there. Do not create or
build study Markdown under `public/`. The audio-reader and vocabulary workflows
publish their HTML outputs separately.

Ask only what is unclear: book folder, which file is PL / EN / UA reference, title, author, header format, chapter numbering (prefaces, appendices).

Create `book.config.json` in the book folder. Start from `references/book.config.example.json` (EPUB sources, the Baskerville setup) or `references/book.config.pdf-txt.example.json` (PDF/TXT source).

- `book`, `header`, `chapters`, `sources.pl`, `sources.en`, optional `sources.ua_reference`.
- EPUB source: `file` is a regex over zip entry names with `{n}` replaced by `chapter + offset`. `container` is an attribute string for a `<div …>`, or a full tag prefix starting with `<` (for example `<section id="chapter-`). `cut` removes a tail such as the Project Gutenberg licence. `title_re` strips the numeral prefix from the heading.
- PDF/TXT source: `heading` is a regex for chapter heading lines (the n-th match is chapter n). Optional `start_after`, `strip_lines` (page numbers, running headers), `char_map`, `para_mode` (`blank` or `line`), `dehyphenate`, `title_re`.
- Inspect the zip first: `unzip -l book.epub`. Do not guess entry names.

Run everything from the skill's scripts. `--root` is a subcommand option and defaults to the current directory:

    python3 <skill>/scripts/trilingual.py list --root src/<book-slug>
    python3 <skill>/scripts/trilingual.py prepare 3 --root src/<book-slug>
    python3 <skill>/scripts/trilingual.py build 3 --root src/<book-slug>
    python3 <skill>/scripts/trilingual.py verify 3 --root src/<book-slug>

Run `list` first. Compare PL and EN paragraph counts per chapter and read the first and last paragraph of a few chapters. If a chapter is missing, or PL and EN counts differ wildly, stop and show the user. Counts that differ moderately are normal (an English paragraph may be split differently).

## Step 1 — Prepare one chapter

`prepare N` writes `work/chapter-NN/`: `raw.json`, `units.json`, `ua.json`, `ua.tsv`, `scaffold.txt`, `report.txt`.

1. PL paragraphs are chunked at sentence boundaries (respecting abbreviations and not splitting inside `<sup>`).
2. **Short one-word replies are merged** (see "Playability rule").
3. EN is split into sentences and aligned to the PL units:
   - `--align llm`: an OpenAI-compatible chat API (`TRILINGUAL_API_BASE`, `TRILINGUAL_API_KEY`/`OPENAI_API_KEY`/`HF_TOKEN`, `TRILINGUAL_MODEL`). The partition is validated and retried; small 7–8B models often fail the strict count.
   - `--align heuristic` (offline; names, digits, measures, dialogue shape, paragraph boundaries, length).
   - `--align proportional` is a last resort and is not semantically reliable.
   - `--align auto` (default) uses LLM if a key is set, else heuristic.
4. `report.txt` lists unit counts, over-limit units, suspicious EN/PL length ratios and every merge. Read it and spot-check the outliers before translating. A wrong partition shifts every later unit.
5. Re-running `prepare` keeps a filled `ua.json` or scaffold (new scaffold goes to `scaffold.new.txt`). `--reset-ua` discards them. If the unit count changed (merge settings, limit), re-check the filled UA still lines up.

## Playability rule: merge units that are too short for audio

`trilingual-audio-reader` gives every unit a ▶ section with a 0.8 s minimum length. A shorter unit is merged into the previous one at alignment time and loses its button. Prevent that here.

- `short_unit()` flags a PL unit with at most `--min-words 2` words and at most `--min-chars 8` characters (after the leading dash or quote): "— Nie.", "— Tak.", "— Po co?", "— Nie ma.". Numbers, dates and roman numerals are headings, not replies, and are never merged.
- Joined to the **previous** unit (the question it answers); to the next unit only if there is no previous one. PL and EN are joined with a space. The merged unit keeps the first piece's paragraph, so the `---` between them disappears. Never merged beyond the 300-character limit. Refusals are reported.
- Calibration (Baskerville and Conrad audio sidecars): the audio aligner merged only a handful of sections (4–5) across 29 chapters. Typical one-word replies last 1.0–1.4 s and are playable; "— Nie." has been seen at 0.81 s. The text side can only approximate narrator pacing, so the defaults are deliberately tight. If a book shows more or fewer merged sections, change `--min-words` / `--min-chars`, or `--no-merge-short`, and say so in the report. Audio-side `--min-dur` remains the safety net.
- Merging changes unit numbers. **Unit numbers are a public interface**: `u-N` anchors in the audio reader and the vocabulary sheets' example links. Apply the rule to chapters before audio and vocabulary work starts. For an already published chapter, ask first and regenerate the reader and vocabulary files afterwards.

## Step 2 — Translate PL → UA (the deliverable)

Fill `work/chapter-NN/scaffold.txt` (`UA:` lines) or `ua.json` / `ua.tsv`, in parts if it is long (a single huge write can hit tool output limits). Do not edit `PL:` or `EN:` lines. Do not run `build` with blank UA unless asked (`--allow-empty` for a scaffold only).

Method:
- Translate from the **PL** line, using EN for meaning and disambiguation (names, pronouns, terms, number formats). If PL and EN disagree, follow PL.
- Natural literary Ukrainian, not a calque. Keep register and period flavour (formal address, narrator voice). Dialogue stays dialogue with the same dashes.
- Same unit content as PL. Do not merge, split, add, summarise or omit; every clause has a counterpart.
- Quotes: UA «…» where PL has „…”. Footnote markers `<sup>N</sup>` in the same positions. Numbers, dates and measures keep their values.
- Names: one transliteration per name across the book, kept in `work/glossary.tsv` (source form, UA form). For an unusual name add the Latin original in parentheses at first occurrence only ("Верлок (Verloc)").
- No Polish diacritics or Latin leftovers in UA, except deliberate parenthetical originals and initials.
- A UA reference edition (if configured in `ua_ref`) guides names and idioms only.
- Record doubtful renderings (archaic words, idioms) for the report.

## Step 3 — Build and verify

`build N` assembles `chapter-NN.md`, verifies, and copies it to the book folder only if verification passes (`--force` to overwrite).

`verify N` re-checks any built file (`--file PATH`). With no prepared work directory it re-extracts from the sources.

Checks:
- Format: no BOM, no CR, trailing newline, exact header, exact edition comment, clean parse.
- No empty EN, PL or UA unit.
- PL reassembly equals the extracted PL paragraphs. A group may span several consecutive paragraphs when short replies were merged; that produces a WARN, any other difference FAILs. Same for EN.
- Separator count equals groups − 1.
- UA has Cyrillic and no Polish diacritics. Footnote markers equal PL's. Quote balance: PL „…” and UA «…».
- Warnings: over-limit units, digit mismatches between EN and PL, units still too short for an audio section, EN quote imbalance (often a Gutenberg artefact).
- Prepared-units consistency (PL/EN text identical to `units.json`).

After the last fix, re-run `verify`. Also check `UA/PL` length ratios by eye in the report; the script does not.

## Step 4 — book.json and hand-off

Maintain `book.json` (title, author, eyebrow, `reader_pattern`, `vocab_pattern`, chapters with `number`, `name` = the spoken PL title, `english`). Its schema is that of trilingual-audio-reader's index builder. Do not commit to git unless asked. Tell the user when the markdown is ready for trilingual-audio-reader; do not start the audio pipeline unasked. Stop after each chapter and ask whether to continue.

## Report per chapter
Unit counts, merges (list them), over-limit units, ALIGNMENT comments, glossary additions, uncertain translations, checks run with results, files written, and anything not verified.

## Pitfalls

- **Wrong extraction pattern.** Never guess EPUB entry names or containers. Use `list` and compare to the source. The Baskerville EN entry for chapter N was `h-{N+2}.htm.html` (the offset matters).
- **Ambiguous EPUB match.** `find_name` fails if two entries match; tighten the regex.
- **Publisher boilerplate** (Gutenberg licence) leaking into the last chapter: set `cut`.
- **Ornament lines and headings** counted as paragraphs shift the alignment; `*` lines are dropped.
- **PDF text is often garbage.** The Wolne Lektury Conrad PDF extracted with 11 000 unexpected glyphs (every "j" came out as a Telugu letter, plus private-use characters). The adapter warns; fix with `char_map`, or better use an EPUB or TXT of the same text. A stray roman-numeral regex matched page marks, so check the chapter count and paragraph counts before trusting a `heading` regex. Scanned PDFs need OCR first.
- **NBSP and whitespace** differences break reassembly checks: all comparisons are whitespace-insensitive.
- **`<sup>` markers** can be split by sentence splitters or dropped in translation; the checks catch both.
- **Abbreviations** (`Mr.`, `r.`, `dr`, initials, `M.R.C.S.`) cause false sentence ends; extend the abbreviation sets in `trilingual.py` if a book needs it.
- **Small LLMs** fail the strict count; proportional alignment looks fine and is wrong.
- **Translation drift:** summarising, dropping clauses, inconsistent names, Russian forms, leftover Polish letters. The checks catch the mechanical ones; read the rest.
- **Over-writing work:** `prepare` keeps filled UA, but a changed unit count (limit, merges) silently misaligns it. Compare counts.
- **CLI detail:** `--root` goes after the subcommand; the default root is the current directory, not the script directory.
- **Scope:** do not generate HTML, vocabulary or audio files here.
