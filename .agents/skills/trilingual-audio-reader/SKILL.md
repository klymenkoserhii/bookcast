---
name: trilingual-audio-reader
description: Build offline, per-chapter HTML study readers (EN → PL → UA) from trilingual Markdown and Polish MP3 narration, with section-level audio aligned locally. Use for readers, audiobooks, read-along pages, chapter-NN.md plus MP3 workflows, AUDIO_TIMES, timestamp helpers, realignment, chapter titles, and book indexes. Also use when creating annotations.md or adding hover/focus tooltips for numbered Polish footnotes with Ukrainian translations.
---

# Trilingual reader with automatic audio alignment

Turns `chapter-NN.md` (EN/PL/UA triples) and one MP3 narration of the Polish text into a single self-contained `chapter-NN.html`. The Polish text is always visible with a ▶ button per section that plays only that section. English and Ukrainian sit behind per-card toggles.

The timing comes from running speech recognition locally (faster-whisper, word-level timestamps) and matching the recognised words against the Polish text. No hand stamping or CDN is needed; the reader embeds text/timings and loads its audio asset locally or from the same-site host.

This workflow was developed across 22 real chapters (two books). The scripts already contain the fixes for every alignment bug those chapters exposed. See `references/triage.md` for the list.

## What you produce per chapter

| File | Purpose |
|---|---|
| `chapter-NN.html` | The reader. Embeds `const CHAPTER = [...]` and `const AUDIO_TIMES = [...]`; loads its relative audio URL as a Blob over HTTP, and uses direct media loading from `file://`. |
| `chapter-NN.timestamp-helper.html` | Standalone manual stamping tool (Space = stamp current time). Escape hatch for hand-fixing. |
| `chapter-NN.audio-times.js` | Paste-ready `AUDIO_TIMES` block with per-unit confidence comments. |
| `chapter-NN.asr.json` | Sidecar: every recognised word with start/end, plus the per-unit mapping. This is the source of truth for timings, and re-aligning from it takes seconds. |
| `annotations.md` (optional) | Four-column Polish/Ukrainian footnote table. When present beside the chapter Markdown, the reader embeds only notes referenced by that chapter and renders accessible superscript tooltips. |
| `index.html` + `book.json` | Book-level contents page: title, author, a reader link and a vocabulary link per chapter (links exist even before the files do). See `references/index-page.md`. |

The reader has a controls bar (volume, speed, reveal-all EN/UA, continuous play, dark mode). On HTTP hosts it fetches the whole audio asset as a Blob before playback so seeking works even when the host's range requests do not; `file://` pages use the direct relative media URL because browsers block `fetch()` there. Keys: Space/Enter play/pause, ↑/↓ select, C or → continuous, E toggle EN, U or Esc toggle UA, T or ← theme. The extra keys exist for TV remotes: on Android TV the D-pad OK sends Enter, Back sends Esc, and ◀/▶ send the arrows. Enter is ignored while a button has focus, so D-pad OK presses the focused toolbar button instead of starting playback; Space always plays/pauses. Continuous play starts from the selected card, or the last played one.

## Before you start: confirm the inputs exist

You need, per chapter: the trilingual markdown and its MP3. Check the markdown first (`references/markdown-format.md` has the commands: EN/PL/UA counts must match and there must be no stray lines).

If `chapter-NN.md` is missing, or its UA text is clearly still being written (a work directory with a mostly empty translation file, a file being modified right now), **stop and tell the user**. Do not translate or patch text to make the pipeline run; the text is their deliverable. Resume when they say the markdown is ready.

Ask the user (only if not already clear) for: the book folder, which MP3 belongs to which chapter, the header title format, and the chapter name to show. If the MP3 filenames contain the chapter title (`..._004_iii-zagadka.mp3`), use the spoken title from the narrator's intro rather than the markdown's English title.

## Optional: footnote annotation table and tooltips

Use this workflow when the chapter has numeric references such as `<sup>23</sup>` and the user wants explanatory tooltips, or supplies an `annotations.md`. It is optional; books without footnotes need no extra file and keep ordinary superscripts.

If tooltips are requested but the table is missing, inspect the supplied source book for its footnotes/endnotes section (for EPUB, check the navigation/package and annotation XHTML such as `annotations.xhtml`). If the source contains a section such as **Przypisy:**, create `annotations.md` beside the chapter files with this four-column table:

```markdown
| Number | Term | Definition (PL) | Translation (UA) |
|--------|------|-----------------|------------------|
| 1 | ... | ... | ... |
```

Preserve each source number exactly and include every entry once. Keep the complete Polish explanation verbatim, including punctuation, diacritics, quotation marks, and emphasis; escape `|` as `\|` inside cells. Translate the full Polish definition into Ukrainian. Identify the annotated term from the note's headword or context; for a citation, use the cited name/title. If no term is identifiable, use `—`. Do not add explanatory prose to the Polish definition cell. When a source note itself does not identify a term, explain the limitation outside that cell only if necessary.

Before building, validate the four columns, unique original numbers, and full coverage of the source footnote section. Compare chapter `<sup>N</sup>` references against table keys; unresolved references remain plain superscripts and should be reported. Do not invent notes or translations when the source is unavailable; ask for the source or table.

The builder automatically reads `annotations.md` beside the chapter Markdown when it exists. Use `--annotations path/to/annotations.md` for a different location. It inserts notes as text rather than raw HTML, preserves simple `*italic*` formatting, and embeds only notes referenced by that chapter. Tooltips show the term, `Definicja (PL)`, and `Переклад (UA)` on hover and keyboard focus. Existing books without an annotation table remain unchanged.

## One-time setup per book folder

```bash
bash <skill-dir>/scripts/setup_book.sh /path/to/book-folder
```

This copies the scripts and templates into the book folder (the generated HTML's "How to re-align after edits" comment tells readers to run them from there) and links `.venv-asr` to a shared Python environment with faster-whisper, creating it once. The first transcription downloads the ~1.6 GB `large-v3-turbo` model.

## Per-chapter workflow

Run from the book folder. Each step has a reason, so keep them in this order.

**1. Pre-flight.** Run the markdown checks. A bad file found now costs seconds; found after ASR it costs 15 minutes.

**2. Align (background).** ASR runs at roughly 3–4.5× realtime on CPU: a 20-minute chapter takes about 5 minutes, an hour-long one about 20. Run it in the background and wait with `sleep` calls (a single tool call is capped at 5 minutes).

```bash
nohup ./.venv-asr/bin/python align_audio.py chapter-03.md mp3/chapter-03.mp3 \
      --fill-gaps 3.0 --js-out chapter-03.audio-times.js > /tmp/ch3.out 2> /tmp/ch3.err &
tail -2 /tmp/ch3.err        # progress: seconds of audio transcribed
```

`--fill-gaps 3.0` re-transcribes any stretch of 3 s or more with no recognised words, without the voice-activity filter. Narrators whisper some lines ("— Psst!"), and the filter silently drops them; without this the section gets a guessed timestamp and its neighbour is wrongly merged. It costs nothing when there are no gaps.

**3. Triage.** This step catches real errors, so do not skip it. Run:

```bash
./.venv-asr/bin/python check_chapter.py chapter-03.md
```

Read every flag against the printed ASR context and decide false alarm vs. real bug using `references/triage.md`. Most `LOW CONFIDENCE` flags are the narrator wording a number or abbreviation differently. Merged sections (one-word replies shorter than 0.8 s) are specified behaviour: report them and offer to lower `--min-dur`; do not change the threshold silently.

If the problem is an aligner defect, fix the **aligner** generally, then re-align all earlier chapters with `--reuse-asr` and diff their start times to prove nothing else moved.

**4. Encode the reader audio after alignment.** Keep ASR and forced alignment on the original MP3; only transcode after timing is finalized. In Bookcast, publish the lower-bitrate copy under `public/<book-slug>/audio/`; keep the original MP3 and timing sources under `src/<book-slug>/`.

```bash
./.venv-asr/bin/python convert_audio_to_opus.py mp3/chapter-03.mp3 \
    --output ../../public/<book-slug>/audio/chapter-03.webm  # run from src/<book-slug>
```

The converter validates that the output is decodable Opus and its duration is within one second of the source. It will not overwrite an existing output unless `--force` is supplied. Adjust `--bitrate` if needed.

**5. Build.**

```bash
./.venv-asr/bin/python build_reader.py chapter-03.md \
    --title "Book Title · Rozdział III" --chapter-name "Spoken chapter title" \
    --subtitle "Author · trilingual study edition: EN → PL → UA" \
      --audio "audio/chapter-03.webm" --times chapter-03.audio-times.js \
      --annotations annotations.md \
     --index index.html \
     --out "../../public/<book-slug>/chapter-03.html" \
     --helper-audio "../../public/<book-slug>/audio/chapter-03.webm" # helper stays beside source
```

`--audio` is the URL *relative to the published HTML*, so `audio/chapter-03.webm` resolves within `public/<book-slug>/`. The reader's header shows three lines: title, chapter name (italic; collapses if empty), subtitle. Keep the title, subtitle and audio naming consistent across chapters of a book. `--annotations` is optional; by default, the builder detects `annotations.md` beside the chapter Markdown. Only notes referenced by the chapter are embedded, so text and timing remain self-contained.

**6. Verify in a browser.** Follow `references/browser-verification.md`, serving the Bookcast repository over HTTP. The reader downloads the full audio as a Blob, so playback seeking does not depend on Range support; the timestamp helper remains in `src/<book-slug>/`, uses a direct media URL, and should be tested with the range-enabled server. Drive the reader (playback at a mid section, hard stop at the next boundary, select-then-Continuous) and helper separately. Confirm audio duration and timestamps, and check the console for errors.

When annotations are present, also hover and keyboard-focus at least one footnote reference. Confirm its number resolves to the correct term, complete Polish definition, and Ukrainian translation; check all chapter references, viewport placement, and browser-console errors. Compare a few displayed Polish definitions directly with the source to ensure they were not paraphrased.

**7. Report.** Per chapter: units/timed, source/output audio lengths and sizes, mean and min confidence, first and last timestamp, each flag with a verdict, each merge with its true start, files written, and exactly what was verified or not. If annotations were used, report resolved and unresolved reference counts. Keep the `AUDIO_TIMES` excerpt short (first two and last entries).

## Book index page

In Bookcast, pass the source folder (containing `book.json` and sidecars) and write the index into the matching public folder, for example `build_index.py src/<book-slug> --book src/<book-slug>/book.json --out public/<book-slug>/index.html`. The builder checks reader/vocabulary files and injects "← Contents" into vocabulary pages in the output directory. Build readers with `--index index.html` so they link back. The index always links to each reader and vocabulary page, including not-yet-built pages (dashed "soon" styling); rebuild it whenever published pages are added. Chapter labels use Polish (`pl` when supplied, otherwise `name`); optional `ua` provides the Ukrainian title in an accessible tooltip.

**Card anchors are an interface.** Every reader card has `id="u-N"` (N = 1-based section number) and the page honours `#u-N` on load. Vocabulary pages link to examples this way (`chapter-05.html#u-47`). A template that stops emitting them silently breaks every vocabulary link, so check for `card.id = "u-"` before replacing a book's template, and after rebuilding confirm the links still resolve.

## Decisions worth knowing

- **Why global alignment:** all Polish tokens are matched against all ASR words at once, so one misheard word cannot steal the next sentence's start. Per-sentence search fails exactly where audiobooks are hardest.
- **Timestamps are strictly increasing, minimum section 0.8 s.** A section that would be shorter is merged into the previous one (`null`), because a sub-second button is not usable.
- **Low-confidence is below 0.6** and is emitted as a `// LOW CONFIDENCE` comment in `AUDIO_TIMES` so it is visible when the file is read by a person.
- **The sidecar is the source of truth.** `build_reader.py` regenerates the HTML from it; a hand-edited `AUDIO_TIMES` in the HTML is overwritten on rebuild. Prefer fixing the aligner or the text and re-running.
- **Re-aligning after text edits:** edit the `PL:` lines, then `align_audio.py ... --reuse-asr chapter-NN.asr.json` (seconds, no new transcription), then `build_reader.py`.
- **Audio conversion order:** align the original MP3 first, then make the smaller Opus/WebM playback copy with `convert_audio_to_opus.py`. Point `build_reader.py --audio` to the relative `audio/chapter-NN.webm` path; do not use the re-encoded copy as the ASR source unless the original is unavailable.
- **Reading position is stored per chapter page, preferences are shared.** The selected and last-played section use localStorage keys scoped by `location.pathname`; theme, volume and speed use one key for the whole site. A single shared position key made every new chapter open with the previous chapter's section number selected. Do not make position keys global again.
- **Chapter-agnostic templates:** `reader.template.html` takes `__STEM__`, `__AUDIO_SRC__`, `__TITLE__`, `__CHAPTER_NAME__`, `__SUBTITLE__`, `__CHAPTER_JSON__`, `__ANNOTATIONS_JSON__`, and `__AUDIO_TIMES_JS__`. No chapter or book names are hard-coded.

## Other languages

The markdown keys are fixed as EN / PL / UA, and the narrated language is the `PL:` line (`--language pl`). For a different narrated language, keep the `PL:` key for the narrated text, pass `--language <code>` to `align_audio.py`, and relabel the headings in the template. The accent-aware tokenizer keeps diacritics by design; check `normalize_tokens` if the new language's punctuation differs.

## Maintenance

`setup_book.sh` never overwrites a script in the book folder that differs from the skill's copy (so per-book edits survive). Update `reader.template.html` and `build_reader.py` together: the template's `__INDEX_LINK__` slot is only filled by a current builder. When you improve the aligner, update the skill copy in `scripts/` too, and say which book folders still hold an older copy.
