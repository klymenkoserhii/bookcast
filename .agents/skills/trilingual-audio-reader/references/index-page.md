# Book index page

`build_index.py` reads book metadata and sidecars from a source folder and writes an `index.html` plus optional vocabulary back-links in the published output folder. In Bookcast, pass `src/<book-slug>` as the source folder and `public/<book-slug>/index.html` as `--out`.

## Design (approved by the user)

- Hero: small caps eyebrow, large serif title, author, then stats (chapters, sections, narration time, vocabulary lists done). Stats come from the `chapter-NN.asr.json` sidecars, so they are always true.
- Contents: one card per chapter. Roman numeral badge, the chapter name (the main link, in the book's own language), a muted line with the English title, section count and length, and two pills: green **▶ Read & listen** and outlined **Vocabulary**.
- Same colour tokens, fonts and dark mode as the readers. The tokens are read from `reader.template.html` at build time, and the theme preference is shared through the same `reader.theme` storage key.
- Chapter labels use Polish (`pl` when supplied, otherwise the existing `name`). An optional `ua` chapter field adds the Ukrainian title in a custom annotation-style tooltip on hover and keyboard focus. The tooltip is viewport-positioned, theme-aware, and linked accessibly with `aria-describedby`; do not rely on the browser-native `title` popup.
- One self-contained index file: it uses relative links and works from `file://`.

## Links to files that do not exist yet

Both links are **always** written, so the index can be built at the start of a book and the chapters and vocabulary pages added later. A target that is missing at build time is drawn dashed and grey with a small "soon" label and a tooltip, and the link still points at the future filename.

A page opened from disk cannot check whether a file exists when it is opened, so this check happens at build time. **Re-run `build_index.py` after adding a chapter or vocabulary page.** Say so in the report, so the user is not surprised by a stale "soon".

## Keys (same mapping as the readers, including the TV remote)

| Action | Keyboard | TV remote (D-pad) |
|---|---|---|
| Choose chapter | ↑ ↓ or J K, Home / End | ▲ ▼ |
| Open the reader | Enter or Space | OK |
| Open the vocabulary | → or V | ▶ |
| Theme | ← or T | ◀ |

The chosen row is remembered (`index.selected`) and also set by any click on a row, so Back returns to the same row. Enter is ignored while a button or link has focus, so D-pad OK still presses a focused control. Back on a TV remote is left alone: it returns to the previous page.

## Workflow

```bash
./.venv-asr/bin/python build_index.py src/<book-slug> --init  # writes book.json beside source chapters
# edit src/<book-slug>/book.json if anything is wrong
./.venv-asr/bin/python build_index.py src/<book-slug> \
  --book src/<book-slug>/book.json \
  --out public/<book-slug>/index.html  # checks/injects pages in public/<book-slug>/
```

Then build every reader with `--index index.html` so each header gets the "← Contents" link (the option is off by default, so books without an index are unaffected).

`book.json` fields: `title`, `author`, `eyebrow`, `reader_pattern` (default `chapter-{nn}.html`), `vocab_pattern` (default `chapter-{nn}.vocab.html`), and `chapters: [{number, name, english, pl?, ua?}]`. `english` is optional (it falls back to the "Chapter N: ..." heading in `chapter-NN.md`). `pl` optionally supplies the visible Polish title; `ua` optionally supplies the Ukrainian tooltip title. A chapter can set `reader` or `vocab` to override the patterns. `--init` takes the title and author from the first built reader's header ("Title · Rozdział I", "Author · trilingual study edition ..."), so build at least one reader first, then check the result. Escape chapter text as HTML when generating the page; keep tooltip text in a `role="tooltip"` element associated with its chapter link via `aria-describedby`, and position it within the viewport on both hover and keyboard focus.

## Vocabulary pages

Vocabulary pages are produced by other tools under `public/<book-slug>/`, so `build_index.py` adds the back-link to those published pages itself, as a small `idx-wrap` block above the title plus one CSS rule. It is idempotent: a marker class (`idx-link`) means a second run changes nothing, and it updates the href if the index filename changes. Use `--no-inject` to skip it. If the vocabulary generator regenerates those files, re-run `build_index.py` afterwards, or add the link at its source.

Vocabulary example links use the reader's `#u-N` anchors (N is the 1-based section number). The reader template emits those ids and honours `#u-N` on load; do not remove them.

## Keep template and builder in step

`reader.template.html` contains an `__INDEX_LINK__` slot that only a current `build_reader.py` fills. If a book folder has an older `build_reader.py` (without `--index`) together with the new template, the page would show the literal placeholder. `setup_book.sh` never overwrites a differing script, so after updating the skill, copy `reader.template.html`, `build_reader.py`, `build_index.py` and `index.template.html` into the book folder together and rebuild.
