#!/usr/bin/env python3
"""Fill scaffold.txt UA lines using a local Ollama model, with timing.

    python3 translate_ollama.py [--model qwen3.5:9b] [--limit N] [--temperature 0.3]

- Resumable: units that already have a UA translation are skipped.
- Rewrites scaffold.txt after every unit, so an interrupt loses at most one unit.
- Validates <sup>N</sup> markers match PL; retries once on mismatch/empty output.
- Prints per-unit timing and a final summary.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCAFFOLD = HERE / "scaffold.txt"
API = "http://localhost:11434/api/generate"

SYSTEM_RULES = """\
Translate the Polish text below into Ukrainian. Literary style of an 1890s Polish novel (Boleslaw Prus, "Lalka").
Output ONLY the Ukrainian translation - no labels, no commentary, no explanations.

Rules:
- Keep every <sup>N</sup> marker exactly as it appears in the Polish, unchanged.
- Keep dialogue dashes (—) and the punctuation of the original.
- Keep proper names in established Ukrainian transliteration.
- Do not add, omit, split, or merge any content.
- Single line output.

Polish:
{pl}

Ukrainian:
"""


def parse_scaffold(text: str) -> list[dict]:
    """Same parsing rules as bilingual.py parse_scaffold."""
    units, current, key, para = [], {}, None, 0
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


def fill_scaffold(units: list[dict]) -> None:
    """Rewrite scaffold.txt from parsed units, preserving paragraph breaks."""
    parts, last_para = [], None
    for u in units:
        if last_para is not None and u.get("para") != last_para:
            parts.extend(["---", ""])
        parts.extend([f"**PL:** {u['pl']}", "", f"**UA:** {u['ua']}", ""])
        last_para = u.get("para")
    SCAFFOLD.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def translate(model: str, pl: str, temperature: float) -> str:
    body = json.dumps({
        "model": model,
        "prompt": SYSTEM_RULES.format(pl=pl),
        "stream": False,
        "think": False,
        "options": {"temperature": temperature},
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("response", "").strip()


def markers(text: str) -> list[str]:
    return re.findall(r"<sup>\d+</sup>", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--limit", type=int, default=0, help="stop after N translations (0 = all)")
    ap.add_argument("--temperature", type=float, default=0.3)
    args = ap.parse_args()

    text = SCAFFOLD.read_text(encoding="utf-8")
    units = parse_scaffold(text)
    todo = [i for i, u in enumerate(units) if not u.get("ua")]
    print(f"units={len(units)} to_translate={len(todo)} model={args.model}", flush=True)
    if args.limit:
        todo = todo[: args.limit]

    start = time.monotonic()
    times: list[float] = []
    problems: list[int] = []
    done = 0
    for i in todo:
        pl = units[i]["pl"]
        t0 = time.monotonic()
        ua, ok = "", False
        for attempt in range(2):
            try:
                ua = translate(args.model, pl, args.temperature).replace("\n", " ").strip()
            except Exception as e:  # noqa: BLE001 - report and retry
                print(f"  unit {i}: attempt {attempt} error: {e}", flush=True)
                time.sleep(2)
                continue
            if ua and (attempt == 1 or markers(ua) == markers(pl)):
                ok = True
                break
            if ua and markers(ua) != markers(pl):
                # retry once with an explicit reminder
                try:
                    ua2 = translate(
                        args.model,
                        pl + "\n\nIMPORTANT: the translation must contain exactly these markers: "
                        + ", ".join(markers(pl)) if markers(pl) else pl,
                        args.temperature,
                    ).replace("\n", " ").strip()
                    ua = ua2 or ua
                except Exception:  # noqa: BLE001
                    pass
                ok = bool(ua) and markers(ua) == markers(pl)
                break
        dt = time.monotonic() - t0
        if not ua:
            ua = ""
        units[i]["ua"] = ua
        if not ok:
            problems.append(i)
        times.append(dt)
        done += 1
        fill_scaffold(units)  # progressive, resumable write
        if done % 10 == 0 or done == len(todo):
            avg = sum(times) / len(times)
            remaining = avg * (len(todo) - done)
            print(
                f"[{done}/{len(todo)}] last={dt:.1f}s avg={avg:.1f}s "
                f"elapsed={(time.monotonic()-start)/60:.1f}m eta={remaining/60:.1f}m",
                flush=True,
            )

    total = time.monotonic() - start
    print("=== summary ===", flush=True)
    print(f"translated={done} total_time={total/60:.1f}m avg={sum(times)/len(times):.1f}s "
          f"min={min(times):.1f}s max={max(times):.1f}s", flush=True)
    if problems:
        print(f"marker_mismatch_units={problems} (review these UA lines)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
