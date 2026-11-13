#!/usr/bin/env python3
"""
build_reader.py — regenerate <chapter>.html (and its timestamp helper) from
the Markdown + the alignment output.

    python build_reader.py chapter-01.md
    python build_reader.py chapter-01.md --times chapter-01.audio-times.js

The only thing that ever needs editing in the HTML is the AUDIO_TIMES array;
this script just keeps CHAPTER in sync with the Markdown so you never hand-copy
94 units. Everything else is templating:

    reader.template.html          -> chapter-01.html
    timestamphelper.template.html -> timestamp-helper.html
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from align_audio import LOW_CONFIDENCE, parse_markdown, preview


def load_times(chapter: Path, asr_json: Optional[Path], times_js: Optional[Path]):
    """Return (times, meta) where meta[index] = {confidence, note}."""
    asr_path = asr_json or chapter.with_suffix(".asr.json")
    if asr_path.exists():
        data = json.loads(asr_path.read_text(encoding="utf-8"))
        units = data.get("units", [])
        times = [u.get("start") for u in units]
        meta = [{"confidence": u.get("confidence", 0.0), "note": u.get("note")}
                for u in units]
        return times, meta

    if times_js and times_js.exists():
        text = times_js.read_text(encoding="utf-8")
        body = text.split("[", 1)[1].rsplit("]", 1)[0]
        body = re.sub(r"//[^\n]*", "", body)
        values = []
        for chunk in body.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            values.append(None if chunk == "null" else float(chunk))
        return values, [{"confidence": 1.0, "note": None} for _ in values]

    raise SystemExit(f"no timestamps found: expected {asr_path} or --times <file>")


def js_array_with_comments(times: Sequence[Optional[float]], units, meta) -> str:
    lines = ["const AUDIO_TIMES = ["]
    width = len(str(len(times) - 1))
    for i, t in enumerate(times):
        value = "null" if t is None else f"{t:.2f}"
        m = meta[i] if i < len(meta) else {"confidence": 1.0, "note": None}
        flags: List[str] = []
        if t is None:
            flags.append("merged into previous section")
        if m.get("confidence", 1.0) < LOW_CONFIDENCE:
            flags.append("LOW CONFIDENCE")
        if m.get("note"):
            flags.append(m["note"])
        suffix = ("   // " + "; ".join(flags)) if flags else ""
        lines.append(
            f"  {(value + ','):<8} // [{i:>{width}}] conf {m.get('confidence', 1.0):.2f}  "
            f"\"{preview(units[i]['pl'])}\"{suffix}"
        )
    lines.append("];")
    return "\n".join(lines)


def chapter_json(units, times) -> str:
    rows = []
    for i, u in enumerate(units):
        rows.append({
            "en": u["en"],
            "pl": u["pl"],
            "ua": u["ua"],
            "para": int(u.get("para", 0)),
            "start": times[i] if i < len(times) else None,
        })
    text = json.dumps(rows, ensure_ascii=False, indent=1)
    # Never let content terminate the surrounding <script> element.
    return text.replace("</", "<\\/")


def load_annotations(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    """Read the four-column Markdown annotation table into a number lookup."""
    if path is None or not path.exists():
        return {}

    result: Dict[str, Dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        # Split only on unescaped pipes, then restore escaped pipes in cells.
        cells = [re.sub(r"\\([|\\])", r"\1", cell.strip())
                 for cell in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) != 4 or not cells[0].isdigit():
            continue
        number, term, definition, translation = cells
        result[number] = {
            "term": term,
            "definition": definition,
            "translation": translation,
        }
    return result


def chapter_annotations(units, annotations: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Embed only notes referenced by this chapter's study text."""
    superscript_digits = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    referenced = {
        number or unicode_number.translate(superscript_digits)
        for unit in units
        for text in (unit.get("en", ""), unit.get("pl", ""), unit.get("ua", ""))
        for number, unicode_number in re.findall(r"<sup>(\d+)</sup>|([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", text)
    }
    return {number: annotations[number] for number in sorted(referenced, key=int)
            if number in annotations}


def fill(template: str, replacements: Dict[str, str]) -> str:
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown", type=Path)
    ap.add_argument("--times", type=Path, default=None, help="chapter-01.audio-times.js")
    ap.add_argument("--asr", type=Path, default=None, help="chapter-01.asr.json")
    ap.add_argument("--title", default=None,
                    help='header title, e.g. "Pies Baskerville’ów · Rozdział I" '
                         "(default: first # heading of the markdown)")
    ap.add_argument("--subtitle", default="trilingual study edition: EN → PL → UA",
                    help='e.g. "Arthur Conan Doyle · trilingual study edition: EN → PL → UA"')
    ap.add_argument("--chapter-name", default="", help="chapter title shown under the book title")
    ap.add_argument("--audio", default=None, help="relative path to the mp3")
    ap.add_argument("--index", default=None, metavar="HREF",
                    help='add a "← Contents" link to the header, e.g. --index index.html (default: no link)')
    ap.add_argument("--annotations", type=Path, default=None,
                    help="Markdown footnote table (default: annotations.md next to the markdown)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--helper-out", type=Path, default=None,
                    help="default: <chapter>.timestamp-helper.html next to the markdown")
    ap.add_argument("--here", type=Path, default=Path(__file__).parent)
    args = ap.parse_args()

    units, _breaks = parse_markdown(args.markdown)
    times, meta = load_times(args.markdown, args.asr, args.times)
    annotations_path = args.annotations or args.markdown.parent / "annotations.md"
    annotations = load_annotations(annotations_path)
    if len(times) != len(units):
        raise SystemExit(f"unit count mismatch: {len(units)} md units vs {len(times)} timestamps")
    times = [round(t, 2) if isinstance(t, (int, float)) else None for t in times]

    stem = args.markdown.stem
    if args.title is None:
        first = next((l for l in args.markdown.read_text(encoding="utf-8").splitlines()
                      if l.startswith("#")), "")
        args.title = first.lstrip("# ").strip() or stem
    audio_src = args.audio or f"{stem}.mp3"
    out = args.out or args.markdown.with_suffix(".html")

    tpl_path = args.here / "reader.template.html"
    html = fill(tpl_path.read_text(encoding="utf-8"), {
        "__TITLE__": args.title,
        "__CHAPTER_NAME__": args.chapter_name,
        "__INDEX_LINK__": (f'<a class="back" href="{args.index}">← Contents</a>' if args.index else ""),
        "__SUBTITLE__": args.subtitle,
        "__STEM__": stem,
        "__AUDIO_SRC__": audio_src,
        "__CHAPTER_JSON__": chapter_json(units, times),
        "__ANNOTATIONS_JSON__": json.dumps(
            chapter_annotations(units, annotations), ensure_ascii=False
        ).replace("</", "<\\/"),
        "__AUDIO_TIMES_JS__": js_array_with_comments(times, units, meta),
    })
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(units)} units, {sum(t is not None for t in times)} timed)")

    helper_tpl = args.here / "timestamphelper.template.html"
    if helper_tpl.exists():
        sections = [{"i": i, "pl": u["pl"], "start": times[i]} for i, u in enumerate(units)]
        helper = fill(helper_tpl.read_text(encoding="utf-8"), {
            "__SECTIONS_JSON__": json.dumps(sections, ensure_ascii=False, indent=1).replace("</", "<\\/"),
            "__AUDIO_SRC__": audio_src,
            "__TITLE__": args.title,
            "__CHAPTER_NAME__": args.chapter_name,
            "__STEM__": stem,
        })
        helper_out = args.helper_out or args.markdown.with_name(f"{stem}.timestamp-helper.html")
        helper_out.write_text(helper, encoding="utf-8")
        print(f"wrote {helper_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
