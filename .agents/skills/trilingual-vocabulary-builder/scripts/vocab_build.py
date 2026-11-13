#!/usr/bin/env python3
"""Build chapter-NN.vocab.md and chapter-NN.vocab.html from a TSV item list.

    python3 vocab_build.py 15 items.tsv [--dir BOOK_FOLDER] [--html-dir PUBLIC_DIR]

items.tsv: one entry per line, four TAB-separated fields (blank lines and lines starting
with '#' are ignored):

    lemma<TAB>UK<TAB>EN<TAB>fragment

`fragment` is a short quoted Polish string copied VERBATIM from the unit where the word
first occurs. The unit is found automatically (first unit containing the fragment).
Duplicate lemmas keep the first row; rows with an empty UK or fragment are dropped.
A JSON file (list of 4-item lists) is accepted too.

The Markdown stays in the source folder; `--html-dir` can send the HTML to a publish folder.
Exit status is 1 when a fragment is not found in the chapter (files are still written).
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

VARIANT = {"ą": "\ue000", "ć": "\ue001", "ę": "\ue002", "ł": "\ue003", "ń": "\ue004",
           "ó": "\ue005", "ś": "\ue006", "ź": "\ue007", "ż": "\ue008"}
BASE_LETTER = {"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z"}


def sort_key(s: str) -> str:
    """Diacritic-insensitive key: a < ą < b < c < ć ... (variant after its base letter)."""
    return "".join(BASE_LETTER.get(c, c) + VARIANT.get(c, "") for c in s.casefold())


def load_units(book: Path, nn: str) -> list[str]:
    text = (book / f"chapter-{nn}.md").read_text(encoding="utf-8")
    return [re.sub(r"\s+", " ", m.group(1).replace("\u00a0", " ")).strip()
            for m in re.finditer(r"^\*\*PL:\*\*\s*(.*)$", text, re.M)]


def load_items(path: Path) -> list[tuple[str, str, str, str]]:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [tuple(x) for x in raw]
    items = []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            print(f"line {ln}: expected 4 tab-separated fields, got {len(parts)}: {line[:60]!r}", file=sys.stderr)
            continue
        items.append(tuple(p.strip() for p in parts))
    return items


def build(book: Path, nn: str, items, md_dir: Path, html_dir: Path) -> int:
    units = load_units(book, nn)
    seen, rows, dropped = set(), [], 0
    for lemma, uk, en, frag in items:
        if not uk or not frag:
            dropped += 1
            continue
        if lemma in seen:
            continue
        seen.add(lemma)
        rows.append((lemma, uk, en, frag))
    entries, missing = [], 0
    for lemma, uk, en, frag in rows:
        n = next((i for i, u in enumerate(units, 1) if frag in u), None)
        if n is None:
            print("MISSING", lemma, repr(frag))
            missing += 1
            continue
        entries.append({"pl": lemma, "uk": uk, "en": en, "unit": n, "frag": frag})
    entries.sort(key=lambda e: sort_key(e["pl"]))

    ch = str(int(nn))
    table = "\n".join(
        f'| {e["pl"]} | {e["uk"]} | {e["en"]} | [„{e["frag"]}”](chapter-{nn}.html#u-{e["unit"]}) |'
        for e in entries
    )
    md = f"""# Chapter {ch} — Vocabulary

<!-- Generated from chapter-{nn}.md. Each Example links to
     chapter-{nn}.html#u-<N>. Sort: PL, diacritic-insensitive. -->

| PL | UK | EN | Example |
|----|----|----|---------|
{table}

<!-- Coverage note:
  - rows: {len(entries)}
  - uncertain: a few archaic or specialised senses may merit review
  - units without a usable example: none identified; only selected vocabulary is listed
-->
"""
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / f"chapter-{nn}.vocab.md").write_text(md, encoding="utf-8")

    template = (HERE / "vocab.template.html").read_text(encoding="utf-8")
    data = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    page = (template.replace("__CH__", ch).replace("__NN__", nn).replace("__DATA__", data))
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / f"chapter-{nn}.vocab.html").write_text(page, encoding="utf-8")
    print(f"units={len(units)} rows={len(entries)} missing={missing} dropped={dropped}")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chapter", help="chapter number, e.g. 15")
    ap.add_argument("items", type=Path, help="items.tsv (or .json)")
    ap.add_argument("--dir", type=Path, default=Path("."), help="book folder with chapter-NN.md (default: cwd)")
    ap.add_argument("--out-dir", type=Path, default=None, help="legacy: write both outputs here (default: --dir)")
    ap.add_argument("--html-dir", type=Path, default=None, help="where to write HTML (default: --out-dir or --dir)")
    a = ap.parse_args()
    nn = f"{int(a.chapter):02d}"
    book = a.dir.resolve()
    md_dir = (a.out_dir or book).resolve()
    html_dir = (a.html_dir or a.out_dir or book).resolve()
    return build(book, nn, load_items(a.items), md_dir, html_dir)


if __name__ == "__main__":
    raise SystemExit(main())
