#!/usr/bin/env python3
"""Prepare, assemble and verify Polish → Ukrainian chapter markdown."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import book_sources as bs


def load(root: Path) -> dict:
    cfg = json.loads((root / "book.config.json").read_text(encoding="utf-8"))
    if "pl" not in cfg.get("sources", {}):
        raise SystemExit("book.config.json must define sources.pl; no English source is used")
    return cfg


def extract(root: Path, cfg: dict, n: int) -> dict:
    return bs.chapter_from(root, cfg["sources"]["pl"], n)


def chunks(text: str, limit: int = 300) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+(?=[\"„«—–A-ZĄĆĘŁŃÓŚŹŻ])", text.strip())
    out: list[str] = []
    cur = ""
    for sentence in filter(None, (s.strip() for s in sentences)):
        parts = [sentence]
        if len(sentence) > limit:
            parts = re.split(r"(?<=;|,)\s+", sentence)
        for part in parts:
            if cur and len(cur) + len(part) + 1 > limit:
                out.append(cur)
                cur = part
            else:
                cur = f"{cur} {part}".strip()
    if cur:
        out.append(cur)
    return out


def work(root: Path, n: int) -> Path:
    return root / "work" / f"chapter-{n:02d}"


def make_book_json(root: Path, cfg: dict) -> None:
    chapters = []
    for n in range(1, int(cfg["chapters"]) + 1):
        data = extract(root, cfg, n)
        chapters.append({"number": n, "name": data.get("title") or f"Chapter {n}"})
    data = {"title": cfg["book"], "author": cfg.get("author", ""),
            "eyebrow": "Bilingual study edition · PL → UA",
            "reader_pattern": "chapter-{nn}.html", "vocab_pattern": "chapter-{nn}.vocab.html",
            "chapters": chapters}
    (root / "book.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_list(root: Path, cfg: dict) -> int:
    print(f"{'#':>3}  {'title':<45}  PL paragraphs")
    for n in range(1, int(cfg["chapters"]) + 1):
        data = extract(root, cfg, n)
        print(f"{n:>3}  {data.get('title', '')[:45]:<45}  {len(data['paras'])}")
    return 0


def cmd_prepare(root: Path, cfg: dict, n: int) -> int:
    raw = extract(root, cfg, n)
    units = [(pno, unit) for pno, para in enumerate(raw["paras"]) for unit in chunks(para)]
    wd = work(root, n)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "units.json").write_text(json.dumps([{"para": p, "pl": t} for p, t in units], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scaffold_parts = []
    last_para = None
    for para, unit in units:
        if last_para is not None and para != last_para:
            scaffold_parts.extend(["---", ""])
        scaffold_parts.extend([f"**PL:** {unit}", "", "**UA:**", ""])
        last_para = para
    scaffold = "\n".join(scaffold_parts).rstrip() + "\n"
    path = wd / "scaffold.txt"
    if path.exists():
        print(f"preserved existing {path}; compare it with the updated {len(units)} units before continuing")
    else:
        path.write_text(scaffold, encoding="utf-8")
    (wd / "report.txt").write_text(f"chapter={n}\nsource={raw['file']}\nparagraphs={len(raw['paras'])}\nunits={len(units)}\n", encoding="utf-8")
    print(f"prepared {len(units)} PL units: {path}")
    return 0


def parse_scaffold(text: str) -> list[dict[str, str]]:
    units: list[dict[str, str]] = []
    current: dict[str, str] = {}
    key = None
    para = 0
    for raw in text.splitlines():
        line = raw.strip()
        if line == "---":
            if current:
                current["para"] = para
                units.append(current)
                current = {}
            para += 1
            key = None
            continue
        m = re.match(r"^\*\*(PL|UA):\*\*\s*(.*)$", line)
        if m:
            k, val = m.group(1).lower(), m.group(2).strip()
            if k == "pl" and current.get("pl"):
                current["para"] = para
                units.append(current)
                current = {}
            current[k] = val
            key = k
        elif line and key:
            current[key] = (current.get(key, "") + " " + line).strip()
    if current:
        current["para"] = para
        units.append(current)
    return units


def assemble(root: Path, cfg: dict, n: int) -> str:
    wd = work(root, n)
    units = parse_scaffold((wd / "scaffold.txt").read_text(encoding="utf-8"))
    if not units or any(not u.get("pl") or not u.get("ua") for u in units):
        raise SystemExit("scaffold has missing PL/UA text; fill every UA line before building")
    raw = extract(root, cfg, n)
    title = raw.get("title", "")
    header = cfg.get("header", "# «{book}» — Chapter {n}: {title}").format(book=cfg["book"], n=n, title=title)
    lines = [header, "<!-- bilingual study edition: PL → UA -->", ""]
    last_para = None
    for i, u in enumerate(units):
        if i and u.get("para") != last_para and u.get("para") is not None:
            lines.extend(["---", ""])
        lines.extend([f"**PL:** {u['pl']}", "", f"**UA:** {u['ua']}", ""])
        last_para = u.get("para")
    return "\n".join(lines).rstrip() + "\n"


def verify(root: Path, cfg: dict, n: int, text: str) -> list[str]:
    errors = []
    units = parse_scaffold(text)
    if not units:
        errors.append("no PL/UA units parsed")
    if any(not u.get("pl") or not u.get("ua") for u in units):
        errors.append("one or more units have an empty PL or UA line")
    raw = extract(root, cfg, n)
    got = re.sub(r"\s+", " ", " ".join(u.get("pl", "") for u in units)).strip()
    expected = re.sub(r"\s+", " ", " ".join(raw["paras"])).strip()
    if got != expected:
        errors.append("PL reassembly differs from extracted source")
    if "<!-- bilingual study edition: PL → UA -->" not in text:
        errors.append("missing bilingual edition comment")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("list", "prepare", "build", "verify"))
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    args = ap.parse_args()
    root, cfg = args.root.resolve(), load(args.root.resolve())
    if args.command == "list":
        return cmd_list(root, cfg)
    if args.chapter is None:
        ap.error("chapter number is required for prepare/build/verify")
    n = args.chapter
    if args.command == "prepare":
        return cmd_prepare(root, cfg, n)
    path = root / f"chapter-{n:02d}.md"
    if args.command == "build":
        text = assemble(root, cfg, n)
        errors = verify(root, cfg, n, text)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        path.write_text(text, encoding="utf-8")
        make_book_json(root, cfg)
        print(f"wrote {path}; verified {len(parse_scaffold(text))} PL/UA units")
        return 0
    text = path.read_text(encoding="utf-8")
    errors = verify(root, cfg, n, text)
    print("PASS" if not errors else "FAIL: " + "; ".join(errors))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
