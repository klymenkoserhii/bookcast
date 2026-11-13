#!/usr/bin/env python3
"""Validate chapter-NN.vocab.md / .vocab.html against chapter-NN.md and the reader.

    python3 validate_vocab.py 15 [--dir SOURCE] [--html-dir PUBLIC] [--add-anchor]

FAIL (exit 1): fragment not in its linked unit; fragment also in an earlier unit; wrong
sort; duplicate lemma or fragment; fragment > 60 chars; row without 3 columns; HTML
entry count != MD rows; external URL in HTML; sticky table header; unbalanced calc();
CSV present; reader card id missing; reader CHAPTER not 1:1 with the markdown units.
REVIEW (printed, exit unaffected): `possible_earlier`, a stem heuristic that often fires
falsely (e.g. 'ostatni' vs 'ostatnie', preposition 'mimo' vs the phrase 'mimo woli');
look at each one, relink if the word really occurs earlier.
--add-anchor inserts `card.id = "u-" + (i + 1);` into the reader if absent.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocab_build import sort_key, BASE_LETTER, load_units  # noqa: E402

ANCHOR = 'card.id = "u-" + (i + 1);'
ap = argparse.ArgumentParser()
ap.add_argument("chapter")
ap.add_argument("--dir", type=Path, default=Path("."), help="source directory with chapter Markdown and vocab Markdown")
ap.add_argument("--html-dir", type=Path, default=None, help="published directory with reader/vocab HTML (default: --dir)")
ap.add_argument("--add-anchor", action="store_true")
a = ap.parse_args()
nn = f"{int(a.chapter):02d}"
d = a.dir.resolve()
h = (a.html_dir or d).resolve()
fails: list[str] = []
review: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


units = load_units(d, nn)
md = (d / f"chapter-{nn}.vocab.md").read_text(encoding="utf-8")
rows = [l for l in md.splitlines() if l.startswith("| ")][1:]
check(all(len(r.split(" | ")) == 3 for r in rows), "a row does not have exactly 3 columns")
links = [(int(n), f) for f, n in re.findall(rf"\[„([^”]+)”\]\(chapter-{nn}\.html#u-(\d+)\)", md)]
check(len(links) == len(rows), f"links {len(links)} != rows {len(rows)}")
frags = [f for _, f in links]
lemmas = [r.split("|")[1].strip() for r in rows]

bad = [(l, n, f) for (n, f), l in zip(links, lemmas) if not (1 <= n <= len(units)) or f not in units[n - 1]]
check(not bad, f"fragment not in its unit: {bad[:5]}")
earlier = [(l, n) for (n, f), l in zip(links, lemmas)
           if 1 <= n <= len(units) and any(f in units[i] for i in range(n - 1))]
check(not earlier, f"fragment also occurs in an earlier unit (not first occurrence): {earlier[:8]}")
keys = [sort_key(l) for l in lemmas]
check(keys == sorted(keys), "rows are not in spec sort order")
check(not [l for l in set(lemmas) if lemmas.count(l) > 1], f"duplicate lemmas: {[l for l in set(lemmas) if lemmas.count(l) > 1]}")
check(not [f for f in set(frags) if frags.count(f) > 1], f"duplicate fragments: {[f for f in set(frags) if frags.count(f) > 1]}")
check(all(len(f) <= 60 for f in frags), f"fragment over 60 chars: {[f for f in frags if len(f) > 60]}")


def fold(w):
    return "".join(BASE_LETTER.get(c, c) for c in w.casefold())


for lem, (n, _) in zip(lemmas, links):
    st = fold(re.sub(r"\s*\([^)]*\)", "", lem).split()[0]) if lem else ""
    if len(st) < 4:
        continue
    for i, u in enumerate(units, 1):
        if any(fold(w).startswith(st) for w in re.findall(r"\w+", u)):
            if i < n:
                review.append(f"possible_earlier: {lem} linked u{n}, stem first seen u{i}")
            break

page = (h / f"chapter-{nn}.vocab.html").read_text(encoding="utf-8")
check(page.count('"pl":') == len(rows), f"HTML entries {page.count(chr(34) + 'pl' + chr(34) + ':')} != MD rows {len(rows)}")
check("http://" not in page and "https://" not in page, "HTML contains an external URL")
check("position:sticky;top:57px" not in page, "table header is sticky (must not be)")
check("calc((100% - 1100px)/2))" in page, "topbar padding calc() missing or unbalanced")
check("'click'" in page, "theme toggle handler missing")
check(not (d / f"chapter-{nn}.vocab.csv").exists(), "a CSV exists (not requested)")

reader_path = h / f"chapter-{nn}.html"
reader = reader_path.read_text(encoding="utf-8")
if ANCHOR not in reader:
    if a.add_anchor:
        new, n = re.subn(r'^(\s*)card\.className = "unit";\n', lambda m: f'{m.group(0)}{m.group(1)}{ANCHOR}   // stable anchor: vocabulary pages link to chapter-NN.html#u-N\n', reader, count=1, flags=re.M)
        if n:
            reader_path.write_text(new, encoding="utf-8")
            reader = new
            print("added reader anchor")
    check(ANCHOR in reader, "reader has no card.id = \"u-\" + (i + 1) anchor (use --add-anchor)")
m = re.search(r"const CHAPTER = (\[.*?\n\]);", reader, re.S)
if m:
    arr = json.loads(m.group(1))
    check(len(arr) == len(units), f"reader CHAPTER {len(arr)} != markdown units {len(units)}")
    mism = [i + 1 for i, (x, y) in enumerate(zip(arr, units))
            if re.sub(r"\s+", " ", str(x.get("pl", "")).replace("\u00a0", " ")).strip() != y]
    check(not mism, f"reader PL text differs from markdown at units {mism[:5]}")
else:
    review.append("could not parse const CHAPTER in the reader")

print(f"chapter {nn}: units={len(units)} rows={len(rows)} max_frag={max(map(len, frags)) if frags else 0}")
for r in review:
    print("REVIEW:", r)
for f in fails:
    print("FAIL:", f)
print("PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
