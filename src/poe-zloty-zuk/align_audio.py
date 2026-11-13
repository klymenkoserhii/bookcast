#!/usr/bin/env python3
"""
align_audio.py — automatic timestamps for a bilingual (PL -> UA) study reader.

What it does
------------
1. Parses a chapter Markdown file into Polish/Ukrainian units (in file order).
2. Transcribes the Polish MP3 with faster-whisper (word-level timestamps).
3. Normalises the ASR Polish words and every PL sentence (lowercase, no punctuation).
4. Aligns the two word streams with a global LCS alignment (difflib SequenceMatcher)
   at the WORD level, then maps each PL sentence to the ASR words it corresponds to.
5. Derives a start time per unit, applies sanity checks (monotonic, min length 0.8 s),
   flags low-confidence units and prints a ready-to-paste `AUDIO_TIMES` array.
6. Writes `<chapter>.asr.json` with the raw ASR words/segments + the per-unit mapping.

Usage
-----
    python align_audio.py chapter-01.md chapter-01.mp3
    python align_audio.py chapter-01.md chapter-01.mp3 --model large-v3 --min-dur 0.8
    python align_audio.py chapter-01.md chapter-01.mp3 --lead 0.15 --json-out custom.json

Dependencies
------------
    python3 -m venv .venv-asr && ./.venv-asr/bin/pip install faster-whisper
    (PyAV decodes the MP3, so no system ffmpeg binary is required.)

Re-align after editing the PL text:  edit chapter-01.md -> re-run this script ->
paste the printed AUDIO_TIMES array into chapter-01.html.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_MODEL = "large-v3-turbo"
MIN_SECTION_SECONDS = 0.8
LOW_CONFIDENCE = 0.60


# --------------------------------------------------------------------------------------
# 1. Markdown parsing
# --------------------------------------------------------------------------------------

# Matches the bilingual `**PL:**` and `**UA:**` unit lines.
UNIT_LINE_RE = re.compile(r"^\s*\*\*(PL|UA):\*\*\s*(.*)$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def parse_markdown(path: Path) -> Tuple[List[Dict[str, str]], int]:
    """Return ([{pl, ua, para}, ...], paragraph_break_count).

    A new unit starts whenever PL or UA repeats. `---` only bumps the paragraph counter; it never
    creates an empty unit.
    """
    text = path.read_text(encoding="utf-8")
    text = COMMENT_RE.sub("", text)  # drop <!-- ALIGNMENT: ... --> notes

    units: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    para = 0
    last_key: Optional[str] = None
    breaks = 0

    def flush() -> None:
        nonlocal current, last_key
        if current and (current["pl"] or current["ua"]):
            units.append(current)
        current = None
        last_key = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            last_key = None
            continue
        if line.startswith("#"):
            continue
        if re.fullmatch(r"-{3,}", line):
            flush()
            para += 1
            breaks += 1
            continue

        m = UNIT_LINE_RE.match(line)
        if m:
            key = m.group(1).lower()
            value = m.group(2).strip()
            if current is None or current[key]:
                flush()
                current = {"pl": "", "ua": "", "para": str(para)}
            current[key] = (current[key] + " " + value).strip() if current[key] else value
            last_key = key
            continue

        # Wrapped continuation line of the previous field.
        if current is not None and last_key is not None:
            current[last_key] = (current[last_key] + " " + line).strip()

    flush()

    missing = [i for i, u in enumerate(units) if not u["pl"]]
    if missing:
        print(f"warning: {len(missing)} unit(s) without PL text: {missing}", file=sys.stderr)
    return units, breaks


# --------------------------------------------------------------------------------------
# 2. Normalisation
# --------------------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


def normalize_tokens(s: str) -> List[str]:
    """Lowercase, strip punctuation/diacritics-independent junk, return word list.

    Polish diacritics are deliberately KEPT (ą/ć/ę/ł/ń/ó/ś/ź/ż): they are part of the
    spelling and Whisper reproduces them reliably, which improves alignment.
    """
    s = unicodedata.normalize("NFKC", s).lower()
    s = _PUNCT_RE.sub(" ", s)
    return s.split()


# --------------------------------------------------------------------------------------
# 3. Transcription
# --------------------------------------------------------------------------------------


def transcribe(mp3: Path, model_name: str, device: str, compute_type: str,
               language: str = "pl") -> Tuple[List[Dict], List[Dict], float]:
    """Run faster-whisper and return (words, segments, duration)."""
    from faster_whisper import WhisperModel  # imported lazily so --help works without it

    print(f"[asr] loading {model_name} ({device}/{compute_type}) ...", file=sys.stderr)
    model = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=0)

    print(f"[asr] transcribing {mp3.name} ...", file=sys.stderr)
    segments_iter, info = model.transcribe(
        str(mp3),
        language=language,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,                 # skip long silence / music intros
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=False,  # avoids repetition loops on long files
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    )

    words: List[Dict] = []
    segments: List[Dict] = []
    for seg in segments_iter:
        for w in seg.words or []:
            token = w.word.strip()
            if not token:
                continue
            words.append({
                "w": token,
                "norm": " ".join(normalize_tokens(token)),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "prob": round(float(getattr(w, "probability", 0.0)), 3),
            })
        segments.append({
            "start": round(float(seg.start), 3),
            "end": round(float(seg.end), 3),
            "text": seg.text.strip(),
        })
        print(f"  {seg.end:7.1f}s  {seg.text.strip()[:70]}", file=sys.stderr)

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    return words, segments, duration


def fill_gaps(mp3: Path, asr_words: List[Dict], min_gap: float, model_name: str,
              device: str, compute_type: str, language: str = "pl",
              min_prob: float = 0.35) -> List[Dict]:
    """Recover quiet speech that voice-activity detection dropped.

    A whispered line ("— Psst! — szepnął Holmes.") can fall entirely inside a long
    stretch with no ASR words. Re-transcribe just those stretches with VAD off and
    insert the words found there. Opt-in (--fill-gaps), because real silence can
    produce hallucinated words; low-probability words are discarded.
    """
    import av
    import numpy as np
    from faster_whisper import WhisperModel

    gaps = [(asr_words[i]["end"], asr_words[i + 1]["start"])
            for i in range(len(asr_words) - 1)
            if asr_words[i + 1]["start"] - asr_words[i]["end"] >= min_gap]
    if not gaps:
        print(f"[gaps] no stretch >= {min_gap:.1f}s without words", file=sys.stderr)
        return asr_words

    rate = 16000
    resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
    chunks = []
    with av.open(str(mp3)) as container:
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                chunks.append(r.to_ndarray().reshape(-1))
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0

    print(f"[gaps] {len(gaps)} stretch(es) >= {min_gap:.1f}s; re-transcribing without VAD",
          file=sys.stderr)
    model = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=0)
    added: List[Dict] = []
    for g0, g1 in gaps:
        lo, hi = max(0.0, g0 - 0.5), g1 + 0.5
        segs, _ = model.transcribe(audio[int(lo * rate):int(hi * rate)], language=language,
                                   word_timestamps=True, vad_filter=False,
                                   condition_on_previous_text=False)
        found = []
        for seg in segs:
            for w in seg.words or []:
                token = w.word.strip()
                norm = " ".join(normalize_tokens(token))
                ws, we = float(w.start) + lo, float(w.end) + lo
                mid = (ws + we) / 2
                if (norm and g0 - 0.05 <= mid <= g1 + 0.05
                        and float(getattr(w, "probability", 0.0)) >= min_prob):
                    found.append({"w": token, "norm": norm, "start": round(ws, 3),
                                  "end": round(we, 3),
                                  "prob": round(float(getattr(w, "probability", 0.0)), 3),
                                  "filled": True})
        print(f"  gap {g0:7.1f}-{g1:7.1f}s: +{len(found)} word(s) "
              f"{' '.join(f['w'] for f in found)[:70]}", file=sys.stderr)
        added.extend(found)
    return sorted(asr_words + added, key=lambda w: (w["start"], w["end"]))


# --------------------------------------------------------------------------------------
# 4. Word-level alignment
# --------------------------------------------------------------------------------------


@dataclass
class UnitAlignment:
    index: int
    tokens: int
    matched: int
    confidence: float
    first_asr: Optional[int]
    last_asr: Optional[int] = None
    first_pos: int = 0
    tail_matched: bool = True
    start: Optional[float] = None
    end: Optional[float] = None
    note: str = ""
    extra: Dict = field(default_factory=dict)


def _similar(pl_token: str, asr_token: str) -> float:
    """String similarity, with a bonus when one token is a prefix/suffix of the other.

    Catches Whisper's Polish spelling splits/merges at sentence boundaries:
        wpatrywał -> Patrywał      skądinąd -> Skąd inąd
    """
    if not pl_token or not asr_token:
        return 0.0
    ratio = difflib.SequenceMatcher(None, pl_token, asr_token).ratio()
    shorter, longer = sorted((pl_token, asr_token), key=len)
    if len(shorter) >= 4 and (longer.startswith(shorter) or longer.endswith(shorter)):
        ratio = max(ratio, 0.85)
    return ratio


def _phonetic(token: str) -> str:
    """Fold the spelling variants Whisper mixes up in Polish/foreign names.

    "Verloc" -> "Werlok" differs in two letters (v/w, c/k), which scores 0.67
    on raw similarity — below the fuzzy threshold, so the word gets dropped and
    the section starts a sentence later than it should.
    """
    return token.replace("w", "v").replace("k", "c")


def refine_first_word(unit_first_token: str, asr_words: Sequence[Dict], idx: int,
                      floor_idx: int, skipped: int = 0,
                      prev_tail: Sequence[str] = (),
                      prev_tail_unmatched: bool = False) -> int:
    """Pull the start back when the unit's first word(s) were transcribed differently.

    If `skipped` PL tokens preceded the first match ("Heat" heard as "Kit"), the audio
    almost always contains exactly that many ASR words before `idx`, so step back by
    `skipped`. Two guards keep this from stealing the previous sentence's tail:

    * `floor_idx` is the previous unit's last MATCHED word — but when that word was
      itself misrecognised it is unmatched, so the floor sits too far back. Comparing
      the candidate with `prev_tail` (the previous unit's last PL words) catches it:
      "Werlok." at the end of "... pan Werloc." is not this sentence's first word.
    * a PL word split by ASR ("Skądinąd" -> "Skąd inąd", "Gospodyni" ->
      "Gospody nie") needs one extra word back. Accept it only when the two ASR
      words concatenate into the PL token and are adjacent in the audio.
    """
    if skipped <= 0:
        return idx
    # A numeral is spoken as several words ("740" -> "siedemset czterdzieści"), so
    # step back further when the unit opens with digits; the floor still caps it.
    step = skipped * 3 if unit_first_token.isdigit() else skipped
    cand = min(max(floor_idx + 1, idx - step), idx)
    if cand >= idx:
        return idx

    def _is_prev_tail(j: int) -> bool:
        tok = asr_words[j]["norm"]
        return any(_similar(prev, tok) >= 0.8 for prev in prev_tail)

    if _is_prev_tail(cand):
        return idx
    # If the previous sentence's final word never matched (misrecognised), the word
    # immediately after its last match is that missing word, not our first word.
    if prev_tail_unmatched and cand == floor_idx + 1:
        return idx

    # Re-join a word Whisper split in two.
    if cand - 1 > floor_idx and not _is_prev_tail(cand - 1):
        joined = asr_words[cand - 1]["norm"] + asr_words[cand]["norm"]
        if _similar(unit_first_token, joined) >= 0.85:
            gap = asr_words[cand]["start"] - asr_words[cand - 1]["end"]
            if gap <= 0.4:
                cand -= 1
    return cand


def align_units(units: Sequence[Dict[str, str]], asr_words: Sequence[Dict]) -> List[UnitAlignment]:
    """Map every PL sentence onto the ASR word stream.

    Strategy: flatten all PL sentences into one token list while remembering which
    unit each token came from, then run ONE global LCS alignment against the ASR
    words. A global alignment is far more robust than per-sentence local search,
    because a mis-recognised word in one sentence cannot "steal" the position of
    the next sentence's first word.
    """
    asr_norm: List[str] = [w["norm"] for w in asr_words]

    pl_tokens: List[str] = []
    token_unit: List[int] = []
    for i, u in enumerate(units):
        for t in normalize_tokens(u["pl"]):
            pl_tokens.append(t)
            token_unit.append(i)

    sm = difflib.SequenceMatcher(None, asr_norm, pl_tokens, autojunk=False)
    blocks = sm.get_matching_blocks()  # always ends with (len(a), len(b), 0)

    # pl token index -> asr word index
    pl2asr: List[Optional[int]] = [None] * len(pl_tokens)
    for a0, b0, size in blocks:
        for k in range(size):
            pl2asr[b0 + k] = a0 + k

    # Aggregate per unit.
    result: List[UnitAlignment] = []
    ua = UnitAlignment(index=-1, tokens=0, matched=0, confidence=1.0, first_asr=None)
    pos_in_unit = 0
    for pos, unit_idx in enumerate(token_unit):
        if ua.index != unit_idx:
            if ua.index >= 0:
                result.append(ua)
            ua = UnitAlignment(index=unit_idx, tokens=0, matched=0, confidence=1.0, first_asr=None)
            pos_in_unit = 0
        ua.tokens += 1
        a = pl2asr[pos]
        if a is not None:
            ua.matched += 1
            if ua.first_asr is None:
                ua.first_asr = a
                ua.first_pos = pos_in_unit
            ua.last_asr = a if ua.last_asr is None else max(ua.last_asr, a)
        pos_in_unit += 1
    if ua.index >= 0:
        result.append(ua)

    # Units with no PL tokens at all still need a placeholder entry.
    by_index = {u.index: u for u in result}
    result = [by_index.get(i, UnitAlignment(i, 0, 0, 0.0, None)) for i in range(len(units))]

    for u in result:
        u.confidence = round(u.matched / u.tokens, 3) if u.tokens else 0.0
        if u.tokens and u.matched == 0:
            u.note = "no words matched"
        elif u.tokens and u.matched / u.tokens < LOW_CONFIDENCE:
            u.note = "low match ratio"

    # Refine the start: if the sentence's FIRST word was transcribed differently
    # ("wpatrywał" -> "Patrywał"), the LCS match lands a word or two late.
    first_token: Dict[int, str] = {}
    for pos, unit_idx in enumerate(token_unit):
        first_token.setdefault(unit_idx, pl_tokens[pos])

    last_tokens: Dict[int, List[str]] = {
        i: normalize_tokens(u["pl"])[-3:] for i, u in enumerate(units)
    }

    # Did each unit's FINAL PL token match? If not, the next unit's start must not
    # consume the ASR word that belongs to this sentence's unrecognised tail.
    for pos, unit_idx in enumerate(token_unit):
        if pos == len(token_unit) - 1 or token_unit[pos + 1] != unit_idx:
            result[unit_idx].tail_matched = pl2asr[pos] is not None

    # The floor is the previous unit's LAST matched word: stepping further back
    # would steal words from the sentence before (e.g. "... pana obowiązków").
    floor = -1
    for u in result:
        if u.first_asr is not None and u.index in first_token:
            prev = result[u.index - 1] if u.index > 0 else None
            refined = refine_first_word(first_token[u.index], asr_words, u.first_asr,
                                        floor, u.first_pos,
                                        last_tokens.get(u.index - 1, []),
                                        bool(prev and not prev.tail_matched))
            if refined != u.first_asr:
                u.note = (u.note + "; start word fuzzy-corrected").strip("; ")
                u.first_asr = refined
        if u.last_asr is not None:
            floor = u.last_asr
        elif u.first_asr is not None:
            floor = max(floor, u.first_asr)
    return result


def times_from_alignment(units: Sequence[Dict[str, str]],
                         aligns: Sequence[UnitAlignment],
                         asr_words: Sequence[Dict],
                         duration: float,
                         min_dur: float,
                         lead: float) -> None:
    """Turn alignment indices into start/end times, then repair the timeline."""
    n = len(units)

    # Raw start from the first matched ASR word of each unit.
    for a in aligns:
        if a.first_asr is not None:
            a.start = max(0.0, float(asr_words[a.first_asr]["start"]) - lead)

    # Units with nothing matched ("Carterright" heard as "Cartwright", "Nic" as "Nie"):
    # the audio still contains words in the gap between the neighbouring matched units,
    # so anchor on those ASR words before falling back to blind interpolation.
    i = 0
    while i < n:
        if aligns[i].start is not None:
            i += 1
            continue
        j = i
        while j < n and aligns[j].start is None:
            j += 1
        prev = aligns[i - 1] if i > 0 else None
        nxt = aligns[j] if j < n else None
        if (prev and nxt and prev.last_asr is not None and nxt.first_asr is not None):
            window = list(range(prev.last_asr + 1, nxt.first_asr))
            tokens = sum(max(1, aligns[k].tokens) for k in range(i, j))
            # Only trust the gap when it holds a plausible number of words.
            if window and len(window) <= tokens * 3 + 2:
                done = 0
                for k in range(i, j):
                    pos = min(len(window) - 1, int(done / tokens * len(window)))
                    aligns[k].start = max(0.0, float(asr_words[window[pos]]["start"]) - lead)
                    aligns[k].note = (aligns[k].note + "; anchored on unmatched ASR words").strip("; ")
                    done += max(1, aligns[k].tokens)
        i = j

    # Whatever is still untimed: interpolate by token position between known anchors.
    for i, a in enumerate(aligns):
        if a.start is not None:
            continue
        prev = next((aligns[j] for j in range(i - 1, -1, -1) if aligns[j].start is not None), None)
        nxt = next((aligns[j] for j in range(i + 1, n) if aligns[j].start is not None), None)
        if prev and nxt:
            ahead = sum(aligns[k].tokens for k in range(prev.index + 1, i + 1))
            span = ahead + sum(aligns[k].tokens for k in range(i + 1, nxt.index))
            frac = ahead / span if span else 0.5
            a.start = round(prev.start + (nxt.start - prev.start) * frac, 3)
            a.note = (a.note + "; interpolated").strip("; ")
        elif prev:
            a.start = round(min(duration, prev.start + 3.0), 3)
            a.note = (a.note + "; extrapolated").strip("; ")
        elif nxt:
            a.start = max(0.0, round(nxt.start - 3.0, 3))
            a.note = (a.note + "; extrapolated").strip("; ")
        else:
            a.start = 0.0
            a.note = "unaligned"

    # --- sanity check 1: strictly increasing (with a minimum epsilon) -----------------
    for i in range(1, n):
        if aligns[i].start <= aligns[i - 1].start:
            aligns[i].start = round(aligns[i - 1].start + 0.05, 3)
            aligns[i].note = (aligns[i].note + "; start forced monotonic").strip("; ")

    # --- sanity check 2: minimum section length; merge into the previous section ------
    # Setting start -> None makes the reader play this unit's audio as part of the
    # previous one (previous section runs until the next non-null start).
    i = 0
    while i < n - 1:
        nxt = next((aligns[j].start for j in range(i + 1, n) if aligns[j].start is not None), duration)
        if aligns[i].start is not None and nxt - aligns[i].start < min_dur:
            aligns[i + 1].start = None
            aligns[i + 1].note = (aligns[i + 1].note + "; merged into previous (<0.8s)").strip("; ")
            aligns[i].note = (aligns[i].note + "; absorbed short next unit").strip("; ")
            i += 1  # keep comparing the (now longer) merged block
        else:
            i += 1

    # --- end times -------------------------------------------------------------------
    for i, a in enumerate(aligns):
        if a.start is None:
            a.end = None
            continue
        nxt = next((aligns[j].start for j in range(i + 1, n) if aligns[j].start is not None), duration)
        a.end = round(nxt, 3)


# --------------------------------------------------------------------------------------
# 5. Reporting
# --------------------------------------------------------------------------------------


def preview(text: str, limit: int = 42) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_js(times: Sequence[Optional[float]], units: Sequence[Dict[str, str]],
              aligns: Sequence[UnitAlignment]) -> str:
    """Render the paste-ready `const AUDIO_TIMES = [...]` block."""
    out = ["const AUDIO_TIMES = ["]
    width = len(str(len(times) - 1))
    for i, t in enumerate(times):
        value = "null" if t is None else f"{t:.2f}"
        a = aligns[i]
        flags = []
        if t is None:
            flags.append("no timestamp (merged into previous)")
        if a.confidence < LOW_CONFIDENCE:
            flags.append("LOW CONFIDENCE")
        if a.note:
            flags.append(a.note)
        suffix = ("   // " + "; ".join(flags)) if flags else ""
        out.append(
            f"  {value + ',' :<8} // [{i:>{width}}] conf {a.confidence:.2f}  "
            f"\"{preview(units[i]['pl'])}\"{suffix}"
        )
    out.append("];")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# 6. main
# --------------------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Auto-align PL sections to a Polish MP3 recording.")
    ap.add_argument("markdown", type=Path, help="bilingual chapter .md")
    ap.add_argument("mp3", type=Path, help="continuous Polish recording")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"faster-whisper model (default {DEFAULT_MODEL}; 'large-v3' = best quality)")
    ap.add_argument("--device", default="cpu", help="cpu | cuda | auto")
    ap.add_argument("--compute-type", default="int8", help="int8 | int8_float16 | float16 | float32")
    ap.add_argument("--language", default="pl", help="ASR language (default pl)")
    ap.add_argument("--min-dur", type=float, default=MIN_SECTION_SECONDS)
    ap.add_argument("--lead", type=float, default=0.12, help="seconds of pre-roll before the first word")
    ap.add_argument("--json-out", type=Path, default=None, help="default: <chapter>.asr.json")
    ap.add_argument("--js-out", type=Path, default=None, help="also save the AUDIO_TIMES block")
    ap.add_argument("--reuse-asr", type=Path, default=None,
                    help="skip transcription and re-align from an existing <chapter>.asr.json")
    ap.add_argument("--fill-gaps", type=float, default=0.0, metavar="SECONDS",
                    help="re-transcribe stretches with no ASR words longer than this, "
                         "without VAD, to recover whispered speech (0 = off)")
    args = ap.parse_args(argv)

    units, breaks = parse_markdown(args.markdown)
    print(f"[md]  {len(units)} units, {breaks} paragraph breaks", file=sys.stderr)

    if args.reuse_asr and args.reuse_asr.exists():
        data = json.loads(args.reuse_asr.read_text(encoding="utf-8"))
        asr_words = data.get("words", [])
        asr_segments = data.get("segments", [])
        duration = float(data.get("duration", 0.0) or 0.0)
        print(f"[asr] reusing {args.reuse_asr} ({len(asr_words)} words, {duration:.1f}s)",
              file=sys.stderr)
    else:
        asr_words, asr_segments, duration = transcribe(
            args.mp3, args.model, args.device, args.compute_type, args.language)
        # Keep only words whose normalisation survived (pure punctuation -> empty).
        asr_words = [w for w in asr_words if w["norm"]]

    if args.fill_gaps > 0:
        before = len(asr_words)
        asr_words = fill_gaps(args.mp3, asr_words, args.fill_gaps, args.model,
                              args.device, args.compute_type, args.language)
        print(f"[gaps] {len(asr_words) - before} word(s) recovered", file=sys.stderr)

    try:
        import av
        with av.open(str(args.mp3)) as container:
            duration = max(duration, float(container.duration or 0) / 1_000_000)
    except Exception:
        pass
    duration = round(duration or (asr_words[-1]["end"] if asr_words else 0.0), 3)
    print(f"[asr] {len(asr_words)} words, {duration:.1f}s audio", file=sys.stderr)

    aligns = align_units(units, asr_words)
    times_from_alignment(units, aligns, asr_words, duration, args.min_dur, args.lead)

    js = format_js([a.start for a in aligns], units, aligns)

    low = [a for a in aligns if a.confidence < LOW_CONFIDENCE]
    print(f"[align] mean confidence {sum(a.confidence for a in aligns) / max(1, len(aligns)):.2f}; "
          f"{len(low)} low-confidence unit(s): {[a.index for a in low]}", file=sys.stderr)

    print(js)

    json_path = args.json_out or args.markdown.with_suffix(".asr.json")
    payload = {
        "source_markdown": args.markdown.name,
        "source_audio": args.mp3.name,
        "model": args.model,
        "language": args.language,
        "duration": duration,
        "word_count": len(asr_words),
        "words": asr_words,
        "segments": asr_segments,
        "units": [
            {
                "index": a.index,
                "start": a.start,
                "end": a.end,
                "confidence": a.confidence,
                "matched_words": a.matched,
                "total_words": a.tokens,
                "first_asr_word": asr_words[a.first_asr]["w"] if a.first_asr is not None else None,
                "pl": units[a.index]["pl"],
                "note": a.note or None,
            }
            for a in aligns
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[out] wrote {json_path}", file=sys.stderr)

    if args.js_out:
        args.js_out.write_text(js + "\n", encoding="utf-8")
        print(f"[out] wrote {args.js_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
