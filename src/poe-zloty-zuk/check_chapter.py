#!/usr/bin/env python3
"""
check_chapter.py — triage report for one aligned chapter.

    python check_chapter.py chapter-03.md

Reads <chapter>.md and <chapter>.asr.json (written by align_audio.py) and prints
everything needed to decide whether the alignment is trustworthy, with the ASR
words around each suspicious start so the verdict takes seconds:

  * unit counts, monotonicity, section-length spread, mean/min confidence
  * FLAG lines: units below the low-confidence threshold, and merged (null) units
  * first-word differences between the Polish text and the first word heard
  * words recovered by --fill-gaps, units anchored on unmatched ASR words
  * the first/last ASR words (the audio usually has a spoken intro and outro)

Exit code is 0 even when flags exist: flags are prompts for a human look, and
most of them are false alarms (see references/triage.md).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_audio import LOW_CONFIDENCE, normalize_tokens, parse_markdown  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    md_path = Path(sys.argv[1])
    asr_path = md_path.with_suffix(".asr.json")
    data = json.loads(asr_path.read_text(encoding="utf-8"))
    units, words = data["units"], data["words"]
    md, _ = parse_markdown(md_path)

    def ctx(t: float, k: int = 3) -> str:
        j = min(range(len(words)), key=lambda z: abs(words[z]["start"] - t))
        return " | ".join(f"{w['w']}@{w['start']:.2f}" for w in words[max(0, j - k): j + k + 1])

    starts = [u["start"] for u in units if u["start"] is not None]
    durs = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    print(f"{md_path.name}: {len(units)} units, {len(starts)} timed, {len(words)} ASR words, "
          f"{data['duration']:.1f}s ({int(data['duration'] // 60)}:{int(data['duration'] % 60):02d})")
    print("monotonic:", all(starts[i] < starts[i + 1] for i in range(len(starts) - 1)))
    if durs:
        print("section length min/median/max: %.2f / %.2f / %.2f s" %
              (min(durs), statistics.median(durs), max(durs)))
    confs = [u["confidence"] for u in units]
    low = min(units, key=lambda u: u["confidence"])
    print("confidence mean %.3f, min %.2f (#%d)" % (statistics.mean(confs), low["confidence"], low["index"]))
    if len(units) != len(md):
        print(f"!! markdown has {len(md)} units but the sidecar has {len(units)}: re-run align_audio.py")

    print("\n-- flags (confidence < %.2f or no timestamp) --" % LOW_CONFIDENCE)
    flagged = [u for u in units if u["confidence"] < LOW_CONFIDENCE or u["start"] is None]
    if not flagged:
        print("none")
    for u in flagged:
        i = u["index"]
        kind = "MERGED" if u["start"] is None else "LOW"
        print(f"{kind} #{i} conf={u['confidence']} matched={u['matched_words']}/{u['total_words']} "
              f"start={u['start']} | {md[i]['pl'][:60]} | {u['note']}")
        if u["start"] is not None:
            print("      ASR:", ctx(u["start"], 4))
        else:
            prev = next((units[j] for j in range(i - 1, -1, -1) if units[j]["start"] is not None), None)
            if prev:
                lo = prev["start"]
                span = " ".join(f"{w['w']}[{w['start']:.2f}-{w['end']:.2f}]"
                                for w in words if lo <= w["start"] <= lo + 8)
                print("      audio after previous start:", span[:200])

    print("\n-- first word heard differs from first word of the text --")
    shown = 0
    for i, u in enumerate(units):
        if u["start"] is None:
            continue
        pl = normalize_tokens(md[i]["pl"])
        heard = normalize_tokens((u["first_asr_word"] or "").strip(".,;:!?…„”\"—-–«»"))
        if pl and heard and heard[0] != pl[0]:
            shown += 1
            print(f"#{i} @{u['start']:.2f} heard '{heard[0]}' vs text '{pl[0]}' conf {u['confidence']} | {ctx(u['start'])}")
    if not shown:
        print("none")

    anchored = [u["index"] for u in units if "anchored" in (u.get("note") or "")]
    filled = [(w["w"], w["start"]) for w in words if w.get("filled")]
    print("\nanchored on unmatched ASR words:", anchored or "none")
    print("recovered by --fill-gaps:", filled or "none")
    print("first words:", [(w["w"], round(w["start"], 2)) for w in words[:6]])
    print("last words: ", [(w["w"], round(w["start"], 2)) for w in words[-3:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
