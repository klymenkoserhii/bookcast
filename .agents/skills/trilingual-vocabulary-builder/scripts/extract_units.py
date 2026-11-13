#!/usr/bin/env python3
"""Print the numbered Polish units of a chapter, or grep them.

    python3 extract_units.py 15 [--dir BOOK] [--out units.txt]
    python3 extract_units.py 15 --grep 'zgładz\\w*'       # exact surface forms with unit numbers

Numbering is 1-based and equals the reader's `u-<N>` anchors. Text is whitespace and
NBSP normalised, which is the form fragments must match. Use --grep before writing a
fragment: typing forms from memory is the most common source of MISSING rows.
"""
import argparse
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("chapter")
ap.add_argument("--dir", type=Path, default=Path("."))
ap.add_argument("--out", type=Path, default=None)
ap.add_argument("--grep", default=None, help="regex; print matching surface forms with context")
a = ap.parse_args()
nn = f"{int(a.chapter):02d}"
text = (a.dir / f"chapter-{nn}.md").read_text(encoding="utf-8")
units = [re.sub(r"\s+", " ", m.group(1).replace("\u00a0", " ")).strip()
         for m in re.finditer(r"^\*\*PL:\*\*\s*(.*)$", text, re.M)]
if a.grep:
    rx = re.compile(a.grep, re.I)
    for i, u in enumerate(units, 1):
        for m in rx.finditer(u):
            lo, hi = max(0, m.start() - 25), min(len(u), m.end() + 25)
            print(f"[{i}] …{u[lo:hi]}…   <{m.group(0)}>")
else:
    out = "\n\n".join(f"[{i}] {u}" for i, u in enumerate(units, 1))
    if a.out:
        a.out.write_text(out, encoding="utf-8")
    else:
        print(out)
    print(f"{len(units)} units", file=__import__("sys").stderr)
