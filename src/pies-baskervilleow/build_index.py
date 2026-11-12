#!/usr/bin/env python3
"""
build_index.py — build the book's index page (index.html) from book.json.

    python build_index.py --init          # create book.json from what the folder already has
    python build_index.py                 # build index.html and add "← Contents" to vocabulary pages

The index lists every chapter with a link to its reader and a link to its vocabulary
page. BOTH links are always written, even when the target file does not exist yet, so
the index can be built early and the files added later. Missing targets are drawn as
dashed "soon" links. Existence is checked at build time (a page opened from disk cannot
check at open time), so re-run this script after adding a chapter or vocabulary page.

book.json
---------
{
  "title": "Pies Baskerville’ów",
  "author": "Arthur Conan Doyle",
  "eyebrow": "Trilingual study edition · EN → PL → UA",
  "reader_pattern": "chapter-{nn}.html",
  "vocab_pattern":  "chapter-{nn}.vocab.html",
  "chapters": [ {"number": 1, "name": "Pan Sherlock Holmes", "english": "Mr. Sherlock Holmes"}, ... ]
}
`english` is optional (default: the "Chapter N: <title>" in chapter-NN.md's first heading).
`reader` / `vocab` can be set per chapter to override the patterns (e.g. chapter 1 of an
older book that kept a different filename). Section counts and narration time come from
chapter-NN.asr.json when present.

Vocabulary pages are produced by other tools, so this script adds the back-link to the
finished pages itself, idempotently (marker class "idx-link"). Use --no-inject to skip.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(n: int) -> str:
    out = ""
    for value, sym in ROMAN:
        while n >= value:
            out += sym
            n -= value
    return out


def fname(pattern: str, n: int) -> str:
    return pattern.replace("{nn}", f"{n:02d}").replace("{n}", str(n))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- init
def init_book(folder: Path, out: Path) -> int:
    """Create book.json from the chapters/readers already in the folder."""
    mds = sorted(folder.glob("chapter-[0-9][0-9].md"))
    if not mds:
        print("no chapter-NN.md files found; nothing to initialise from", file=sys.stderr)
        return 1
    title = author = ""
    chapters = []
    for md in mds:
        n = int(md.stem.split("-")[1])
        heading = next((l for l in read(md).splitlines() if l.startswith("#")), "")
        m = re.search(r"Chapter\s+\d+:\s*(.*)$", heading)
        english = m.group(1).strip() if m else ""
        name = ""
        page = folder / f"chapter-{n:02d}.html"
        if page.exists():
            h = read(page)
            mn = re.search(r'<p class="chapter-name">(.*?)</p>', h)
            name = html.unescape(mn.group(1)).strip() if mn else ""
            if not title:
                mt = re.search(r"<h1>(.*?)</h1>", h)
                if mt:
                    title = html.unescape(mt.group(1)).split(" · ")[0].strip()
                ms = re.search(r'<p class="chapter-name">.*?</p>\s*<p>(.*?)</p>', h, re.S)
                if ms and " · " in ms.group(1):
                    author = html.unescape(ms.group(1)).split(" · ")[0].strip()
        chapters.append({"number": n, "name": name or english or f"Chapter {n}", "english": english})
    if not title:
        heading = next((l for l in read(mds[0]).splitlines() if l.startswith("#")), "")
        title = re.sub(r"\s*[—-]\s*Chapter.*$", "", heading.lstrip("# ")).strip("«» ") or folder.name
    book = {
        "title": title, "author": author or "",
        "eyebrow": "Trilingual study edition · EN → PL → UA",
        "reader_pattern": "chapter-{nn}.html", "vocab_pattern": "chapter-{nn}.vocab.html",
        "chapters": chapters,
    }
    out.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: \"{title}\" / \"{author}\", {len(chapters)} chapters. Check title, author and names.")
    return 0


# ----------------------------------------------------------------------------- build
def extract_tokens(reader_template: Path) -> tuple[str, str]:
    """Reuse the reader's colour tokens so index, readers and vocabulary pages match."""
    t = read(reader_template)
    light = re.search(r":root \{(.*?)\n  \}", t, re.S)
    dark = re.search(r'html\[data-theme="dark"\] \{(.*?)\n  \}', t, re.S)
    if not (light and dark):
        raise SystemExit(f"could not find the colour tokens in {reader_template}")
    return light.group(1), dark.group(1)


def minutes(seconds: float) -> str:
    return f"{int(round(seconds / 60))} min"


def pill(label: str, href: str, exists: bool, kind: str) -> str:
    if exists:
        return f'<a class="pill {kind}" href="{html.escape(href)}">{label}</a>'
    return (f'<a class="pill {kind} pending" href="{html.escape(href)}" '
            f'title="Not created yet. This link starts working when the file is added.">'
            f'{label}<span class="soon">soon</span></a>')


def build(folder: Path, book_path: Path, out: Path, inject: bool) -> int:
    book = json.loads(read(book_path))
    r_pat = book.get("reader_pattern", "chapter-{nn}.html")
    v_pat = book.get("vocab_pattern", "chapter-{nn}.vocab.html")
    chapters = sorted(book["chapters"], key=lambda c: c["number"])

    rows, total_units, total_sec, n_vocab = [], 0, 0.0, 0
    missing_reader, missing_vocab, injected = [], [], []
    for c in chapters:
        n = c["number"]
        reader = c.get("reader") or fname(r_pat, n)
        vocab = c.get("vocab") or fname(v_pat, n)
        has_reader, has_vocab = (folder / reader).exists(), (folder / vocab).exists()
        n_vocab += has_vocab
        if not has_reader:
            missing_reader.append(reader)
        if not has_vocab:
            missing_vocab.append(vocab)

        english = c.get("english")
        if english is None:
            md = folder / f"chapter-{n:02d}.md"
            m = re.search(r"Chapter\s+\d+:\s*(.*)$", next((l for l in read(md).splitlines() if l.startswith("#")), "")) if md.exists() else None
            english = m.group(1).strip() if m else ""
        meta = [english] if english else []
        side = folder / f"chapter-{n:02d}.asr.json"
        if side.exists():
            data = json.loads(read(side))
            units, dur = len(data.get("units", [])), float(data.get("duration", 0))
            total_units += units
            total_sec += dur
            meta += [f"{units} sections", minutes(dur)]

        rows.append(f'''
      <li class="ch">
        <a class="ch-num" href="{html.escape(reader)}" tabindex="-1" aria-hidden="true">{roman(n)}</a>
        <div class="ch-main">
          <a class="ch-title" href="{html.escape(reader)}">{html.escape(c["name"])}</a>
          <div class="ch-sub">{html.escape(" · ".join(meta))}</div>
        </div>
        <div class="ch-links">
          {pill("▶ Read &amp; listen", reader, has_reader, "primary")}
          {pill("Vocabulary", vocab, has_vocab, "secondary")}
        </div>
      </li>''')

        if inject and has_vocab:
            if inject_back_link(folder / vocab, out.name):
                injected.append(vocab)

    stats = [f"<span><b>{len(chapters)}</b> chapters</span>"]
    if total_units:
        h, m = int(total_sec // 3600), int(round((total_sec % 3600) / 60))
        stats += [f"<span><b>{total_units:,}</b> sections</span>",
                  f"<span><b>{h} h {m:02d} min</b> of narration</span>" if h else f"<span><b>{m} min</b> of narration</span>"]
    if n_vocab:
        stats.append(f"<span><b>{n_vocab} / {len(chapters)}</b> vocabulary lists</span>")

    light, dark = extract_tokens(folder / "reader.template.html" if (folder / "reader.template.html").exists()
                                 else HERE / "reader.template.html")
    page = read(folder / "index.template.html" if (folder / "index.template.html").exists()
                else HERE / "index.template.html")
    for key, value in {
        "__TOKENS_LIGHT__": light, "__TOKENS_DARK__": dark,
        "__TITLE__": html.escape(book["title"]), "__AUTHOR__": html.escape(book.get("author", "")),
        "__EYEBROW__": html.escape(book.get("eyebrow", "Trilingual study edition")),
        "__STATS__": "".join(stats), "__ROWS__": "".join(rows),
    }.items():
        page = page.replace(key, value)
    out.write_text(page, encoding="utf-8")

    print(f"wrote {out}: {len(chapters)} chapters, vocabulary pages {n_vocab}/{len(chapters)}")
    if missing_reader:
        print("  readers not created yet (links kept):", ", ".join(missing_reader))
    if missing_vocab:
        print("  vocabulary not created yet (links kept):", ", ".join(missing_vocab))
    if injected:
        print(f"  added/updated the “← Contents” link in {len(injected)} vocabulary page(s)")
    return 0


VOCAB_CSS = (".idx-wrap{display:flex;flex-direction:column;gap:1px;min-width:0}"
             ".idx-link{font-size:.76rem;color:var(--muted);white-space:nowrap}"
             ".idx-link:hover{color:var(--accent)}")


def inject_back_link(page: Path, index_name: str) -> bool:
    """Add a '← Contents' link above the title of a finished vocabulary page. Idempotent.

    Returns True if the file was changed.
    """
    text = read(page)
    link = f'<a class="idx-link" href="{html.escape(index_name)}">← Contents</a>'
    if 'class="idx-link"' in text:
        new = re.sub(r'<a class="idx-link" href="[^"]*">← Contents</a>', link, text)
    else:
        m = re.search(r'(<div class="title">.*?</div>)', text, re.S)
        if not m:
            print(f"  skipped {page.name}: no <div class=\"title\"> to attach the link to", file=sys.stderr)
            return False
        new = text.replace(m.group(1), f'<div class="idx-wrap">{link}{m.group(1)}</div>', 1)
        new = new.replace("</style>", VOCAB_CSS + "</style>", 1)
    if new != text:
        page.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the book index page.")
    ap.add_argument("folder", nargs="?", type=Path, default=Path("."), help="book folder (default: current)")
    ap.add_argument("--init", action="store_true", help="create book.json from the folder's chapters and exit")
    ap.add_argument("--book", type=Path, default=None, help="book.json (default: <folder>/book.json)")
    ap.add_argument("--out", type=Path, default=None, help="default: <folder>/index.html")
    ap.add_argument("--no-inject", action="store_true",
                    help="do not add the '← Contents' link to existing vocabulary pages")
    args = ap.parse_args()
    folder = args.folder.resolve()
    book_path = args.book or folder / "book.json"
    out = args.out or folder / "index.html"
    if args.init:
        if book_path.exists():
            print(f"{book_path} already exists; edit it or delete it to re-initialise", file=sys.stderr)
            return 1
        return init_book(folder, book_path)
    if not book_path.exists():
        print(f"{book_path} not found. Run with --init first.", file=sys.stderr)
        return 1
    return build(folder, book_path, out, inject=not args.no_inject)


if __name__ == "__main__":
    raise SystemExit(main())
