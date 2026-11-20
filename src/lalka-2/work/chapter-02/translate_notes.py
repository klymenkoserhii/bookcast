#!/usr/bin/env python3
"""Translate notes-600-716.json PL definitions to Ukrainian via local Ollama.

    python3 translate_notes.py [--model qwen3.5:9b] [--limit N]

Resumable: writes notes-600-716.ua.json after every note.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "notes-600-716.json"
OUT = HERE / "notes-600-716.ua.json"
API = "http://localhost:11434/api/generate"

SYSTEM_RULES = """\
Translate the Polish editorial footnote below into Ukrainian. It is from a scholarly edition of an 1890s Polish novel (Boleslaw Prus, "Lalka").

Output ONLY the Ukrainian translation - no labels, no commentary.

Rules:
- Keep names, dates and numbers exactly (translate only the words around them).
- Keep proper names in established Ukrainian transliteration.
- Map editorial tags: [przypis redakcyjny] -> [редакційна примітка]; [przypis edytorski] -> [редакторська примітка]; [Przyp. Aut.] -> [Прим. авт.].
- Do not add, omit, or merge content. Single line output.

Polish footnote:
{pl}

Ukrainian:
"""


def translate(model: str, pl: str, temperature: float = 0.3) -> str:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = json.loads(SRC.read_text(encoding="utf-8"))
    done = {}
    if OUT.exists():
        done = {r["number"]: r.get("ua", "") for r in json.loads(OUT.read_text(encoding="utf-8"))}
    todo = [r for r in rows if not done.get(r["number"])]
    if args.limit:
        todo = todo[: args.limit]
    print(f"rows={len(rows)} to_translate={len(todo)} model={args.model}", flush=True)

    start = time.monotonic()
    times = []
    for i, r in enumerate(todo, 1):
        t0 = time.monotonic()
        ua = ""
        for attempt in range(2):
            try:
                ua = translate(args.model, r["pl"]).replace("\n", " ").strip()
            except Exception as e:  # noqa: BLE001
                print(f"  note {r['number']}: attempt {attempt} error: {e}", flush=True)
                time.sleep(2)
                continue
            if ua:
                break
        r["ua"] = ua
        done[r["number"]] = ua
        times.append(time.monotonic() - t0)
        # progressive write in original order
        out_rows = []
        for orig in rows:
            n = orig["number"]
            out_rows.append({**orig, "ua": done.get(n, "")})
        OUT.write_text(json.dumps(out_rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if i % 10 == 0 or i == len(todo):
            avg = sum(times) / len(times)
            eta = avg * (len(todo) - i)
            print(f"[{i}/{len(todo)}] avg={avg:.1f}s elapsed={(time.monotonic()-start)/60:.1f}m eta={eta/60:.1f}m", flush=True)

    missing = [n for n, v in done.items() if not v]
    print(f"=== done: {len(done)} notes, empty: {missing or 'none'} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
