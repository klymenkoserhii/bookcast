---
name: trilingual-vocabulary-builder
description: Build per-chapter Polish vocabulary sheets (chapter-NN.vocab.md plus a self-contained chapter-NN.vocab.html study page) for a trilingual EN/PL/UA book that already has chapter-NN.md and the chapter-NN.html reader. Four columns (PL lemma with grammar tags, Ukrainian, English, a clickable example linked to the unit in the reader). Use when the user says "go" for the next chapter's vocabulary, asks for a vocab sheet, glossary or word list for a chapter, or wants example links into the reader. One chapter per turn. Not for building chapter markdown (trilingual-book-builder) or readers/audio (trilingual-audio-reader).
---

# trilingual-vocabulary-builder

Pipeline position: `trilingual-book-builder` (chapter-NN.md) → `trilingual-audio-reader` (chapter-NN.html reader with `u-N` anchors) → **this skill** → vocabulary pages linked from the reader's index (`vocab_pattern` in `book.json`).

Scripts (standard library only), in `scripts/`:
- `extract_units.py`: numbered PL units, and `--grep` for exact surface forms.
- `vocab_build.py`: TSV items → `chapter-NN.vocab.md` + `.vocab.html`, using `vocab.template.html`.
- `validate_vocab.py`: all checks, plus `--add-anchor` for the reader.

## Output (two files per chapter, nothing else)

`chapter-NN.vocab.md` is the source of truth and stays in `src/<book-slug>/`; `chapter-NN.vocab.html` is generated from the same data into `public/<book-slug>/`. **No CSV** unless the user asks. Do exactly one chapter, report, then ask whether to continue.

Markdown table, four columns in this order:

| PL | UK | EN | Example |

- **PL**: lemma with grammar tags. Nouns `dom (m.)` (also `(f.)`, `(n.)`, `(pl.)`). Verbs: infinitive and aspect, `czytać (impf.)` / `przeczytać (pf.)`. Adjectives: masculine nominative singular. Adverbs, prepositions, conjunctions as-is. Multi-word expressions as one entry. No rows for inflected forms.
- **UK**, **EN**: concise glosses of the sense used in THIS chapter. Join several attested senses with `; `.
- **Example**: `[„fragment”](chapter-NN.html#u-<N>)`. The fragment is a short quoted Polish string (≤ 60 characters, in practice 15–40) copied verbatim from the unit's `PL:` line, showing the attested inflected form. It links to the FIRST unit where the word occurs. Fragments are unique across rows.
- Sorted alphabetically by PL, diacritic-insensitive, in the order a ą b c ć d e ę f g h i j k l ł m n ń o ó p r s ś t u w y z ź ż (the variant letter sorts after its base letter, so `słuszny` precedes `ślad`). `vocab_build.py` does this.
- A "Coverage note" HTML comment at the end of the MD (row count, uncertain senses).

HTML page (from `vocab.template.html`, identical for every chapter): vanilla HTML/CSS/JS, no CDN or external URL, works from `file://`; light theme matching the reader with a dark toggle (`localStorage` key `reader.theme`); mobile friendly; **table header must not be sticky** (an early version was, which was a visual bug); topbar contains `<div class="title">`, which `trilingual-audio-reader`'s `build_index.py` needs to inject its "← Contents" link.

## Selection rules (what goes in)

Include words attested in the chapter that are above A2, or A1–A2 words used idiomatically or non-literally, and non-compositional multi-word expressions. Culturally important proper names are rare exceptions.

Exclude ordinary proper names, the ~1000 most common Polish words (unless the sense here is non-obvious), and `się`/`nie`/`by` (unless the usage is unusual). Drop any entry whose lemma you are unsure of rather than guess. Typical yield: 70–240 rows, roughly 1.5–2.5 per unit. Dense 19th-century prose gives more.

## Workflow per chapter (user says "go")

1. **Extract units** and read ALL of them (do not sample): `python3 <skill>/scripts/extract_units.py N --dir src/<book-slug> > /tmp/chN.txt`. Numbering equals the reader's `u-N` anchors.
2. **Reader anchors.** The reader cards must carry `id="u-N"` (1-based). `validate_vocab.py` checks for `card.id = "u-" + (i + 1);` and `--add-anchor` inserts it after `card.className = "unit";`. If the book was built with the current trilingual-audio-reader template they are already there.
3. **Write `items.tsv`** (outside the book folder, for example the session temp dir): one line per entry, four TAB-separated fields `lemma  UK  EN  fragment`. Blank lines and `#` comment lines are ignored. A TSV is robust: appending chunks with `cat >>` cannot produce a syntax error, unlike the bracketed Python lists used originally.
4. **Look up forms before writing fragments.** `extract_units.py N --grep 'stem\w*'` prints exact surface forms with context and unit numbers.
5. **Build:** `python3 <skill>/scripts/vocab_build.py N items.tsv --dir src/<book-slug> --html-dir public/<book-slug>`. Markdown stays with sources; HTML is published. Every `MISSING lemma 'fragment'` line means the fragment is not in the chapter; grep the exact text and fix it. Exit status 1 while anything is missing.
6. **Validate:** `python3 <skill>/scripts/validate_vocab.py N --dir src/<book-slug> --html-dir public/<book-slug>`. Fix every FAIL. Look at every REVIEW line (see below).
7. If the book index exists, rebuild it from the source metadata into `public/<book-slug>/` so the vocabulary link is live and the page receives its contents back-link. Delete scratch files, check `git status` (the files stay uncommitted unless asked), report, and ask about the next chapter.

## Translation method (UK and EN glosses)

Written by the model from context. There is no MT API and no dictionary lookup.
- Gloss the sense in THIS passage, not every dictionary sense. Add a second sense after `; ` only if it also occurs in the chapter.
- UK is idiomatic Ukrainian, not a calque of EN. Short. Use the Ukrainian apostrophe `'`.
- EN is a short natural gloss. Verbs with `to`. Give the discourse sense for particles ("wszak" → "you know; after all").
- Aspect goes in the lemma tag, not the gloss.
- Archaic or literary Polish (`wszak`, `ilekroć`, `gdym`, `żem`) is common in 19th-century texts. Gloss the modern equivalent and mention uncertainty in the coverage note.
- Re-read the UK column for stray Latin letters inside Cyrillic words and for typos in EN.

## Verification (`validate_vocab.py`)

FAIL (exit 1): fragment not found in its linked unit; fragment also found in an earlier unit (so not the first occurrence); wrong sort; duplicate lemma; duplicate fragment; fragment > 60 chars; a row without 4 columns; HTML entry count ≠ MD rows; an external URL in the HTML; sticky table header; unbalanced `calc()`; theme toggle handler missing; CSV present; reader anchor missing; reader `CHAPTER` not 1:1 with the markdown units.

REVIEW (informational): `possible_earlier` compares the lemma's first-word stem with earlier units. It fires falsely often (`ostatni` vs `ostatnie`, `spod` vs `spodziewał`, the preposition `mimo` vs the phrase `mimo woli`, imperative `bądź`, plain `człowiek` vs `człowiek czynu`, `stanąć` vs `stanąć otworem`). Inspect each one. If the word really occurs earlier, relink to the true first occurrence.

After any fix pass, re-run the validator rather than assuming.

## Pitfalls (all hit in practice)

- **Fragments typed from memory.** Misspelled or inflected differently (`spojarzał`/`spojrzał`, `arcydeła`/`arcydzieła`, `odpokuluje`/`odpokutowuje`, `przecywległej`/`przeciwległej`). Always `--grep` first. Check capitalisation of sentence-initial forms (`Nie jest to miła robota`), typographic apostrophes (`Barrymore’a`) and footnote markers (`<sup>23</sup>`) that can split a word. Fragments are matched against whitespace/NBSP-normalised text.
- **Hidden characters.** A soft hyphen (U+00AD) ended up inside a lemma once. NBSP in the source breaks naive matches (the tools normalise it). Scan an items file for unexpected non-letter characters if a row behaves oddly.
- **Duplicate fragments.** Two rows picking the same quote (`wybuch`/`wdzięczność`, `subtelny`/`woń`, `prowizoryczny`/`buda`) violate uniqueness. Give each row a different substring of the same unit, usually its own word plus one neighbour, and never drop the attested form from the fragment.
- **Wrong first occurrence.** Picking a later, more convenient sentence breaks the "first occurrence only" rule (`nazajutrz` u84 vs the real first use u52, `wszak` u25, `skorzystać` u64). The validator catches it only partially, so read the REVIEW lines.
- **Wrong lemma.** `snąć się` should be `snuć się`; `przypiąć brodę` should be `przyprawić brodę` (the text has `przyprawiwszy`); a contrived `wytyczony ścieżką` should be `wytyczyć`. Derive the lemma from the attested form before writing the row.
- **Typos in glosses.** `abysss`, `constantlv`, a Latin `c` inside a Cyrillic word, `odróżność` for `odrębność`. Re-read the glosses.
- **Large writes:** put long item lists in a few `cat >>` appends; duplicates and junk placeholder rows are dropped by `vocab_build.py` (first lemma wins, empty UK/fragment dropped), but check the final row count.
- **Unit numbers are a public interface.** If `trilingual-book-builder` re-chunks or merges units after the vocabulary exists, every `#u-N` link shifts. Regenerate the vocabulary (the `frag` still identifies the unit; rebuild from the same TSV with `vocab_build.py`) after such a change.
- **Sort key.** Use `vocab_build.py`'s key; do not sort in an editor. `ślad` sorts after `słuszny`. Chapter 1 of the Baskerville book was built with a different key and fails the check.
- **macOS `sed -i`** needs `-i ''`. Prefer small Python edits with an `assert old in s` guard.
- **Browser tool cannot open `file://`.** For a visual check serve the folder with `python3 -m http.server`.
- **Do not commit** vocabulary files unless asked.

## Report template (end of each chapter)

Links to the two files; row and unit counts; reader-anchor status (present, or added); that no CSV was made; validator results with each check; a "Fixes during the build" list; benign `possible_earlier` hits with the reason; then "Shall I continue with chapter N+1?" If no further `chapter-NN.md` exists, say so and offer the book index (trilingual-audio-reader's `build_index.py`).
