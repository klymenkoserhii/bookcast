# Chapter markdown format

`align_audio.py` and `build_reader.py` both read this. The aligner only looks at the `PL:` lines (that is what the narrator reads); the reader shows all three.

```markdown
# «Book title» — Chapter 3: The Problem
<!-- trilingual study edition: EN → PL → UA -->

> **EN:** English sentence(s) for this unit.

**PL:** Polish sentence(s) for this unit.

**UA:** Ukrainian sentence(s) for this unit.

---

> **EN:** Next unit, in a new paragraph (the `---` line marks a paragraph break).

**PL:** ...

**UA:** ...
```

Rules the parser relies on:

- A **unit** is one EN/PL/UA triple. A new unit starts whenever a key (EN, PL or UA) repeats, so a unit with no EN line still parses.
- `---` only bumps the paragraph counter. It never creates an empty unit.
- Lines starting with `#` and `<!-- ... -->` comments are ignored. The first `#` heading becomes the default page title.
- A unit usually holds one to three sentences. The Polish text is chunked to roughly 300 characters at sentence boundaries, which gives sections of 5–25 seconds. Much longer units make sections hard to follow; much shorter ones trigger the minimum-length merge (see `triage.md`).
- Numeric footnote markers such as `<sup>23</sup>` are rendered as superscripts; when a sibling `annotations.md` has that number, the reader adds a PL/UA tooltip. They still count as unmatched tokens during audio alignment. Unicode superscripts such as `funtów⁵⁰` remain plain text and do not map to annotation-table keys.

## Pre-flight check (do this before the 15-minute ASR run)

```bash
grep -c '^> \*\*EN:' chapter-03.md   # the three counts must be equal
grep -c '^\*\*PL:\*\*' chapter-03.md
grep -c '^\*\*UA:\*\*' chapter-03.md
awk 'NF && $0 !~ /^> \*\*EN:/ && $0 !~ /^\*\*PL:/ && $0 !~ /^\*\*UA:/ && $0 !~ /^#/ && $0 !~ /^---$/ && $0 !~ /^<!--/' chapter-03.md | head -3   # stray text: should print nothing
```

If the markdown does not exist yet, or its UA text is still being filled in, stop and tell the user. Do not generate or "fix" translations to make the pipeline run: the text is the user's deliverable.

## Audio

One continuous MP3 per chapter. Narrators usually speak an intro first ("Rozdział trzeci. Zagadka.") and sometimes an outro, so the first timestamp is typically 1.5–10 s and the last words of the transcript are usually not the last unit. That is normal.
