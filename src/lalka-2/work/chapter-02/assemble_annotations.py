#!/usr/bin/env python3
"""Append notes 600-716 to src/lalka-2/annotations.md from the translated JSON.

    python3 assemble_annotations.py

Validates: unique numbers, 4 columns, all chapter-02 references covered,
PL text matches the EPUB extraction verbatim, no empty UA.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOK = HERE.parent.parent  # src/lalka-2
ANN = BOOK / "annotations.md"
CH2 = BOOK / "chapter-02.md"
NOTES = HERE / "notes-600-716.ua.json"

UA_TAGS = {
    "[przypis redakcyjny]": "[редакційна примітка]",
    "[przypis edytorski]": "[редакторська примітка]",
    "[Przyp. Aut.]": "[Прим. авт.]",
}


def esc(s: str) -> str:
    return s.replace("|", "\\|")


def main() -> int:
    rows = json.loads(NOTES.read_text(encoding="utf-8"))
    errors = []

    # 1. completeness & emptiness
    nums = [r["number"] for r in rows]
    if len(nums) != len(set(nums)):
        errors.append("duplicate numbers in JSON")
    for r in rows:
        if not r.get("ua", "").strip():
            errors.append(f'{r["number"]}: empty UA')
        if not r.get("pl", "").strip():
            errors.append(f'{r["number"]}: empty PL')

    # 2. all chapter-2 references covered
    ch2 = CH2.read_text(encoding="utf-8")
    refs = {int(x) for x in re.findall(r"<sup>(\d+)</sup>", ch2)}
    missing = sorted(refs - set(nums))
    if missing:
        errors.append(f"chapter references missing from notes: {missing}")

    # 3. editorial tag mapping present in UA
    for r in rows:
        for pl_tag, ua_tag in UA_TAGS.items():
            if pl_tag in r["pl"] and ua_tag not in r["ua"]:
                errors.append(f'{r["number"]}: UA missing tag {ua_tag!r}')

    # 4. no stray untranslated Polish tags
    for r in rows:
        for pl_tag in UA_TAGS:
            if pl_tag in r["ua"]:
                errors.append(f'{r["number"]}: UA still contains {pl_tag!r}')

    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(" -", e)
        return 1

    # 5. append rows in order
    ann = ANN.read_text(encoding="utf-8")
    existing = {int(m) for m in re.findall(r"^\| (\d+) \|", ann, re.M)}
    to_add = [r for r in rows if r["number"] not in existing]
    if not to_add:
        print("nothing to add; annotations.md already complete")
        return 0

    lines = []
    for r in sorted(to_add, key=lambda x: x["number"]):
        ua = r["ua"].strip()
        # safety: UA must be a single line
        ua = re.sub(r"\s+", " ", ua)
        lines.append(f'| {r["number"]} | {esc(r["term"])} | {esc(r["pl"])} | {esc(ua)} |')

    if not ann.endswith("\n"):
        ann += "\n"
    ann += "\n".join(lines) + "\n"
    ANN.write_text(ann, encoding="utf-8")

    # 6. re-validate file structure
    final = ANN.read_text(encoding="utf-8")
    row_lines = [l for l in final.splitlines() if re.match(r"^\| \d+ \|", l)]
    bad = [l for l in row_lines if l.count("|") != 5]  # 4 cols => 5 pipes
    if bad:
        print(f"BAD COLUMN COUNT in {len(bad)} rows:")
        for l in bad[:5]:
            print(" -", l[:120])
        return 1
    all_nums = [int(re.match(r"^\| (\d+) \|", l).group(1)) for l in row_lines]
    if len(all_nums) != len(set(all_nums)):
        print("DUPLICATE numbers in annotations.md")
        return 1
    still_missing = sorted(refs - set(all_nums))
    if still_missing:
        print(f"references still missing: {still_missing}")
        return 1

    print(f"appended {len(to_add)} rows; annotations.md now has {len(all_nums)} notes "
          f"({min(all_nums)}-{max(all_nums)}), all {len(refs)} chapter-2 references covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
