---
name: bilingual-audio-reader
description: Build offline per-chapter Polish–Ukrainian HTML readers from PL/UA chapter-NN.md plus a Polish MP3, with section-level playback timed by local speech recognition and forced alignment. Use for bilingual readers, audiobook/read-along pages, AUDIO_TIMES, timestamp alignment, timestamp helpers, re-alignment after text edits, book indexes, or creating annotations.md and hover/focus tooltips for numbered Polish footnotes with Ukrainian translations. The reader has no English text, controls, or source requirement.
---

# Bilingual reader with automatic audio alignment

Turns a PL/UA `chapter-NN.md` and its Polish MP3 into a study reader. Polish is visible with one ▶ button per unit; Ukrainian is revealed per card or all at once. Local faster-whisper alignment creates timestamps. On HTTP hosts the reader fetches its relative audio asset as a Blob for reliable seeking; from `file://` it uses the direct media URL because browsers block `fetch()` there.

## Inputs and preflight

Each chapter needs complete PL/UA markdown and its Polish MP3. Consult `references/markdown-format.md`: PL and UA unit counts must match, and no stray lines are allowed. If the UA translation is missing or still being written, stop; do not translate or patch the user's text.

Ask only for unclear details: book folder, chapter-to-MP3 mapping, header title format, and spoken chapter name. If the audio filename includes a chapter name, prefer the narrator's spoken title over a Polish source heading.

## Build workflow

1. Set up the book once with `bash <skill-dir>/scripts/setup_book.sh /path/to/book-folder`. The first ASR run downloads the configured Whisper model.
2. Run `align_audio.py chapter-03.md mp3/chapter-03.mp3 --fill-gaps 3.0 --js-out chapter-03.audio-times.js` using the book's ASR environment. For long audio, run it in the background and monitor its log.
3. Triage every flag with `check_chapter.py` and `references/triage.md`. Treat low confidence as a review cue, not an automatic error. Report sub-0.8-second units merged into the previous section; do not change the threshold silently.
4. After alignment and triage, encode the original MP3 as an Opus/WebM reader asset. In Bookcast, write it to `../../public/<book-slug>/audio/chapter-03.webm` from `src/<book-slug>/`. The converter defaults to 32 kbps mono Opus, validates codec and duration, and refuses to overwrite an existing output unless `--force` is supplied. Keep ASR/alignment on the original MP3; transcode only after timing is finalized.
5. From `src/<book-slug>/`, build with `build_reader.py chapter-03.md --title "Book · Rozdział III" --chapter-name "Spoken title" --subtitle "Author · bilingual study edition: PL → UA" --audio audio/chapter-03.webm --times chapter-03.audio-times.js --index index.html --out ../../public/<book-slug>/chapter-03.html --helper-audio ../../public/<book-slug>/audio/chapter-03.webm`. The reader is published under `public/`; the timestamp helper stays beside the source Markdown. Add `--annotations annotations.md` when using footnotes. The audio URL is relative to the generated page; by default, sibling `annotations.md` is detected beside the Markdown.
6. Build the book index from source metadata into public with `build_index.py src/<book-slug> --book src/<book-slug>/book.json --out public/<book-slug>/index.html`. The index checks and updates pages in the output directory.
7. Verify in a browser using `references/browser-verification.md`. Check playback, stopping at section boundaries, continuous play, and the manual helper. Confirm the Blob-loaded WebM duration agrees with the source MP3, section timestamps still match, and there are no console errors. If annotations are present, test a note on hover and keyboard focus, check term/PL definition/UA translation and viewport placement, and compare definitions against the source.
8. Report unit/timestamp counts, source/output audio lengths and sizes, mean/min confidence, first/last timestamp, triage verdicts, merges, files written, and exactly what was verified.

## Optional: footnote annotations and tooltips

Use this only when chapters contain numeric references such as `<sup>23</sup>` and the user wants explanatory notes or supplies an `annotations.md`. No annotation file is needed for books without footnotes; unannotated references remain ordinary superscripts.

When requested and the table is missing, inspect the supplied book source's footnotes/endnotes. If present, create `annotations.md` beside the chapter Markdown using this table:

```markdown
| Number | Term | Definition (PL) | Translation (UA) |
|--------|------|-----------------|------------------|
| 1 | ... | ... | ... |
```

Preserve original numbering and the complete Polish definition verbatim, including punctuation, diacritics, and emphasis; escape pipes as `\\|`. Translate that definition fully into Ukrainian. Use the annotated headword or the cited name/title for `Term`, or `—` if none can be identified. Do not add explanatory prose to the Polish definition. Validate unique numbers, four columns, complete source coverage, and references used by the chapter. Never invent missing definitions or translations; ask for the source/table if unavailable.

The builder reads a sibling `annotations.md` by default, or accepts `--annotations path/to/annotations.md`. It embeds only referenced notes and renders text safely (not as raw HTML), with hover/focus tooltips showing the term, Polish definition, and Ukrainian translation. Simple `*italic*` emphasis is preserved.

## Index and vocabulary integration

Use `build_index.py` for a book contents page; follow `references/index-page.md`. The bilingual `book.json` has title, author, an eyebrow such as `Bilingual study edition · PL → UA`, reader/vocabulary patterns, and chapters with number and Ukrainian `name`. Optionally add `pl` for the Polish chapter title: it becomes the visible linked label, while `name` appears in an accessible, annotation-style tooltip on hover and keyboard focus. Without `pl`, the existing `name` remains the visible label. Rebuild the index when chapters/readers/vocabulary pages change.

Reader cards keep stable `id="u-N"` anchors because vocabulary examples link to them. Preserve these anchors when changing templates.

## Alignment and maintenance notes

- The aligner matches Polish tokens to Polish ASR globally; local alignment per sentence can shift boundaries.
- Timestamps are increasing; sections shorter than 0.8 seconds merge into the previous unit. `chapter-NN.asr.json` is the timing source of truth.
- After Polish text edits, reuse the ASR sidecar with `align_audio.py ... --reuse-asr chapter-NN.asr.json`, then rebuild.
- Align against the original MP3 before converting it; a lower-bitrate Opus re-encode may slightly degrade ASR input. Keep the original as the timing source and use `audio/chapter-NN.webm` for the reader.
- Templates must contain no English card, reveal control, or keyboard shortcut. Polish remains the narrated language (`--language pl`).
- `setup_book.sh` preserves differing per-book scripts. Update bundled reader template and builder together when changing the page contract.
