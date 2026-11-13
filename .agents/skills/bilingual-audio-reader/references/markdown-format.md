# Bilingual chapter markdown format

`align_audio.py` reads Polish units for narration; the reader displays Polish and Ukrainian.

```markdown
# «Book title» — Chapter 3: Polish chapter title
<!-- bilingual study edition: PL → UA -->

**PL:** Polish sentence(s) for this unit.

**UA:** Ukrainian translation of this unit.

---

**PL:** Next Polish unit in a new paragraph.

**UA:** Ukrainian translation.
```

Parser rules:

- One unit is a PL/UA pair. A new unit starts when a language key repeats.
- `---` marks a paragraph break and does not create an empty unit.
- Headings and HTML comments are ignored; the first Markdown heading is the default page title.
- Keep units short enough for usable audio sections (typically one to three sentences and around 300 Polish characters).
- Numeric footnote markers such as `<sup>23</sup>` render as superscripts; when a sibling `annotations.md` contains that number, the reader adds a PL/UA tooltip. They remain unmatched tokens for audio alignment. Unicode superscripts do not map to annotation-table keys.

## Preflight before transcription

```bash
grep -c '^\*\*PL:' chapter-03.md
grep -c '^\*\*UA:' chapter-03.md
```

The counts must match. Check for stray lines:

```bash
awk 'NF && $0 !~ /^\*\*(PL|UA):/ && $0 !~ /^#/ && $0 !~ /^---$/ && $0 !~ /^<!--/' chapter-03.md | head -3
```

It should print nothing. If the markdown is missing or the UA translation is unfinished, stop; do not generate or repair the user's translation to run the reader pipeline.

## Audio

Use one continuous original Polish MP3 per chapter as the ASR/alignment source. After alignment and triage, convert it to the mono Opus/WebM reader asset with `convert_audio_to_opus.py`; point the reader to that `.webm` path. The recording may include a spoken introduction or outro; consequently the first timestamp need not be zero and the last aligned word need not be at the end of either file.
