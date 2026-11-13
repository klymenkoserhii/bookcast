#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone builder for the trilingual (EN -> PL -> UA) study edition.

The script is deliberately dependency-free (Python 3 standard library only).

Workflow for a chapter:

    python3 trilingual.py prepare 3              # extract + chunk + align
    # fill work/chapter-03/ua.json (or edit work/chapter-03/scaffold.txt)
    python3 trilingual.py build 3                # assemble + verify
    python3 trilingual.py verify 3               # re-check a built file

Alignment can be done by an OpenAI-compatible chat API, or offline by a
translation-invariant heuristic (names, digits, measures, punctuation,
dialogue shape, paragraph boundaries, cumulative length) -- the heuristic
needs no key and was tuned against the hand-built chapters 1 and 2. A dumb
proportional split remains available for comparison.  Translation is intentionally
NOT automated: ``prepare`` writes an empty UA table and a readable scaffold,
and ``build`` refuses to run until every unit has a Ukrainian translation.
Re-running ``prepare`` keeps a UA file or scaffold you have already filled
(use ``--reset-ua`` to start over).

Examples:

    python3 trilingual.py list
    python3 trilingual.py prepare 3 --align heuristic   # offline, no key
    python3 trilingual.py prepare 3 --align llm --model gpt-4o-mini
    python3 trilingual.py build 3 --ua work/chapter-03/scaffold.txt
    python3 trilingual.py verify 3

Environment for LLM alignment:

    TRILINGUAL_API_BASE   default https://api.openai.com/v1
    TRILINGUAL_API_KEY    falls back to OPENAI_API_KEY, then HF_TOKEN
    TRILINGUAL_MODEL      default gpt-4o-mini

Sources (EPUB, PDF or plain text) are described in <root>/book.config.json; see
references/book.config.example.json. Short one-word replies are joined to a
neighbouring unit during ``prepare`` so every unit is long enough to be a playable
audio section (see ``merge_short_units``).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_sources as bs  # noqa: E402
from book_sources import norm, strip_tags, read_epub, find_name, paras_from_html  # noqa: E402,F401

DEFAULT_LIMIT = 300
MIN_WORDS = 2
MIN_CHARS = 8
DEFAULT_HEADER = "# «{book}» — Chapter {n}: {title}"

CONFIG: dict = {}

PL_ABBREV = {
    "r.", "np.", "itd.", "itp.", "tzn.", "tzw.", "dr", "dr.", "prof.",
    "prof.", "św.", "p.", "pp.", "nr", "nr.", "m.in.", "mgr", "inż.",
    "hab.", "godz.", "tys.", "mln", "mld", "w.", "z.", "o.", "mjr",
    "płk", "gen.", "ks.", "bp.", "kard.", "kpt.", "por.", "sierż.",
}

EN_ABBREV = {
    "mr.", "mrs.", "ms.", "dr.", "st.", "jr.", "sr.", "capt.", "col.",
    "gen.", "lt.", "sgt.", "rev.", "hon.", "prof.", "maj.", "gov.",
    "sen.", "rep.", "vs.", "etc.", "e.g.", "i.e.", "no.", "vol.",
    "p.", "pp.", "m.r.c.s.", "c.c.h.",
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def ws(t: str) -> str:
    """Whitespace-insensitive comparison form (NBSP included)."""
    return re.sub(r"[\s\u00a0]+", " ", t).strip()


# --------------------------------------------------------------------------
# configuration, chapter metadata and extraction
# --------------------------------------------------------------------------

def load_config(root: Path) -> dict:
    path = root / "book.config.json"
    if not path.exists():
        raise SystemExit(
            f"missing {path}. Create it from references/book.config.example.json "
            "(EPUB) or references/book.config.pdf-txt.example.json (PDF/TXT)."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("book", "chapters", "sources"):
        if key not in cfg:
            raise SystemExit(f"{path}: missing key {key!r}")
    for lang in ("pl", "en"):
        if lang not in cfg["sources"]:
            raise SystemExit(f"{path}: sources.{lang} is required")
    return cfg


def header_line(chapter: int, title: str) -> str:
    fmt = CONFIG.get("header", DEFAULT_HEADER)
    line = fmt.format(book=CONFIG["book"], n=chapter, title=title)
    if not title:
        line = re.sub(r":\s*$", "", line.rstrip())
    return line


def load_chapter(root: Path, chapter: int) -> dict:
    total = int(CONFIG["chapters"])
    if not (1 <= chapter <= total):
        raise SystemExit(f"chapter must be between 1 and {total}")
    srcs = CONFIG["sources"]
    pl = bs.chapter_from(root, srcs["pl"], chapter)
    en = bs.chapter_from(root, srcs["en"], chapter)
    ua = bs.ua_reference(root, srcs.get("ua_reference"), chapter)
    return {
        "chapter": chapter,
        "title": en["title"] or pl["title"],
        "pl_title": pl["title"],
        "pl": pl["paras"],
        "en": en["paras"],
        "ua_ref": ua,
        "pl_file": pl["file"],
        "en_file": en["file"],
    }


# --------------------------------------------------------------------------
# sentence splitting and PL chunking
# --------------------------------------------------------------------------

def _is_initial(seg: str) -> bool:
    tail = seg.rstrip().split()
    if not tail:
        return False
    return bool(re.fullmatch(r"(?:[A-Z]\.){1,3}", tail[-1]))


def split_sentences(text: str, abbrev: set[str]) -> list[str]:
    """Split on sentence punctuation, then merge false boundaries.

    The merge rules are deliberately conservative: a boundary is rejected when
    the next fragment starts with a lowercase letter, or when the previous
    fragment ends with a known abbreviation or initials.
    """
    tmp = re.sub(
        r'([.!?\u2026][\u201d\u00bb"\u2019]?)\s+',
        lambda m: m.group(1) + "\x00",
        text,
    )
    raw = [s for s in tmp.split("\x00") if s.strip()]
    out: list[str] = []
    for seg in raw:
        seg = seg.strip()
        if not seg:
            continue
        if out:
            prev = out[-1]
            next_lower = bool(re.match(r"[a-ząćęłńóśźż]", seg))
            prev_tail = prev.rstrip().split()[-1].lower() if prev.rstrip().split() else ""
            if next_lower or prev_tail in abbrev or _is_initial(prev):
                out[-1] = prev + " " + seg
                continue
        out.append(seg)
    return out


def inside_sup(t: str, idx: int) -> bool:
    return t.rfind("<sup>", 0, idx) > t.rfind("</sup>", 0, idx)


def split_overlong(t: str, limit: int) -> list[str]:
    if len(t) <= limit:
        return [t]
    for sep in ("; ", " \u2014 ", ", ", " "):
        # keep the separator's punctuation (e.g. the ";" of "; ") with the left
        # fragment, otherwise the split silently drops it from the text
        keep = len(sep.rstrip(" "))
        start = 0
        while True:
            idx = t.rfind(sep, start, limit + 1)
            if idx <= 0:
                break
            if not inside_sup(t, idx):
                left = t[:idx + keep].rstrip()
                right = t[idx + keep:].lstrip()
                if left and right:
                    return [left] + split_overlong(right, limit)
            start = idx + 1
    return [t]


def chunk_pl(text: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for sent in split_sentences(text, PL_ABBREV):
        if not cur:
            cur = sent
        elif len(cur) + 1 + len(sent) <= limit:
            cur += " " + sent
        else:
            chunks.append(cur)
            cur = sent
    if cur:
        chunks.append(cur)

    out: list[str] = []
    for c in chunks:
        out.extend(split_overlong(c, limit) if len(c) > limit else [c])
    return [c.strip() for c in out if c.strip()]


def short_unit(pl: str, min_words: int = MIN_WORDS, min_chars: int = MIN_CHARS) -> bool:
    """True if a PL unit is too short to be a playable audio section (< ~0.8 s).

    Calibrated on the Baskerville/Conrad audio sidecars: units of <= 2 words and <= 8
    characters ("— Nie.", "— Tak.", "— Po co?") are the ones that can fall under the
    0.8 s minimum section length; longer one-word replies usually last 1.0-1.4 s and
    are playable. Numbers, dates and roman numerals are headings, not replies.
    """
    body = re.sub(r"^[\s\u2014\u2013\-\u201e\"\u00ab\u201c]+", "", pl).strip()
    words = re.findall(r"\w+", body)
    if not words or re.fullmatch(r"[\dIVXLC.,:\s]+", body):
        return False
    return len(words) <= min_words and len(body) <= min_chars


def merge_short_units(units: list[dict], limit: int, min_words: int, min_chars: int):
    """Join too-short units to a neighbour (previous preferred, next for the first unit).

    PL and EN are joined with a space; the merged unit keeps the paragraph position of
    the FIRST piece, so the '---' between the pieces disappears. Never exceeds ``limit``.
    Returns (units, log) where log lists every merge and every refusal.
    """
    out: list[dict] = []
    log: list[str] = []
    i = 0
    while i < len(units):
        u = units[i]
        if short_unit(u["pl"], min_words, min_chars):
            if out and len(out[-1]["pl"]) + 1 + len(u["pl"]) <= limit:
                prev = out[-1]
                prev["pl"] += " " + u["pl"]
                prev["en"] = (prev["en"] + " " + u["en"]).strip()
                if u.get("comment"):
                    prev["comment"] = ((prev.get("comment") or "") + " " + u["comment"]).strip()
                log.append(f"merged into previous: {u['pl']!r}")
                i += 1
                continue
            if not out and i + 1 < len(units) and len(u["pl"]) + 1 + len(units[i + 1]["pl"]) <= limit:
                nxt = units[i + 1]
                nxt["pl"] = u["pl"] + " " + nxt["pl"]
                nxt["en"] = (u["en"] + " " + nxt["en"]).strip()
                nxt["plp"] = u["plp"]
                log.append(f"merged into next: {u['pl']!r}")
                i += 1
                continue
            log.append(f"NOT merged (limit or no neighbour): {u['pl']!r}")
        out.append(u)
        i += 1
    return out, log


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------

def proportional_counts(pls: list[str], m: int) -> list[int]:
    """Split m EN segments across len(pls) units, every unit >= 1."""
    n = len(pls)
    if m < n:
        raise ValueError(f"not enough EN segments ({m}) for {n} PL units")
    weights = [max(1, len(p)) for p in pls]
    total = sum(weights)
    counts = [max(1, int(round(m * w / total))) for w in weights]
    while sum(counts) > m:
        i = max((i for i in range(n) if counts[i] > 1), key=lambda i: counts[i])
        counts[i] -= 1
    while sum(counts) < m:
        i = max(range(n), key=lambda i: weights[i] / counts[i])
        counts[i] += 1
    return counts


def align_proportional(pls: list[str], en_segments: list[str]) -> list[str]:
    if len(en_segments) < len(pls):
        raise ValueError(
            f"not enough EN segments ({len(en_segments)}) for {len(pls)} PL units"
        )
    counts = proportional_counts(pls, len(en_segments))
    out = []
    pos = 0
    for c in counts:
        out.append(" ".join(en_segments[pos:pos + c]))
        pos += c
    return out


# --------------------------------------------------------------------------
# offline heuristic alignment
#
# Scores a monotonic PL->EN mapping on cues that survive translation: names,
# digits, number words, measures, question/exclamation marks, dialogue shape,
# sentence counts, length ratio, paragraph boundaries and cumulative progress.
# Tuned against the hand-built chapters 1 and 2 (mean paragraph similarity
# 0.95 and 0.92 respectively). Needs no network access and no model.
# --------------------------------------------------------------------------

HE_NUM_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80",
    "ninety": "90", "hundred": "100", "thousand": "1000",
    "jeden": "1", "jedna": "1", "jedno": "1", "dwa": "2", "dwie": "2",
    "trzy": "3", "cztery": "4", "pięć": "5", "sześć": "6", "siedem": "7",
    "osiem": "8", "dziewięć": "9", "dziesięć": "10", "jedenaście": "11",
    "dwanaście": "12", "trzynaście": "13", "czternaście": "14",
    "piętnaście": "15", "szesnaście": "16", "siedemnaście": "17",
    "osiemnaście": "18", "dziewiętnaście": "19", "dwadzieścia": "20",
    "trzydzieści": "30", "czterdzieści": "40", "sto": "100",
    "tysiąc": "1000",
}

HE_MEASURE = {
    "mile": "MILE", "miles": "MILE", "mila": "MILE", "mile": "MILE",
    "mil": "MILE", "mili": "MILE",
    "yard": "YARD", "yards": "YARD", "jard": "YARD", "jardy": "YARD",
    "jardów": "YARD",
    "foot": "FOOT", "feet": "FOOT", "stopa": "FOOT", "stopy": "FOOT",
    "stóp": "FOOT",
    "inch": "INCH", "inches": "INCH", "cal": "INCH", "cala": "INCH",
    "cale": "INCH", "cali": "INCH",
    "hour": "HOUR", "hours": "HOUR", "godzina": "HOUR", "godziny": "HOUR",
    "godzin": "HOUR",
    "day": "DAY", "days": "DAY", "dzień": "DAY", "dni": "DAY", "dnia": "DAY",
    "night": "NIGHT", "nights": "NIGHT", "noc": "NIGHT", "nocy": "NIGHT",
    "week": "WEEK", "weeks": "WEEK", "tydzień": "WEEK", "tygodnie": "WEEK",
    "tygodni": "WEEK",
    "month": "MONTH", "months": "MONTH", "miesiąc": "MONTH",
    "miesiące": "MONTH", "miesięcy": "MONTH",
    "year": "YEAR", "years": "YEAR", "rok": "YEAR", "roku": "YEAR",
    "lata": "YEAR", "lat": "YEAR",
    "pound": "POUND", "pounds": "POUND", "funt": "POUND", "funty": "POUND",
    "funtów": "POUND",
    "shilling": "SHILLING", "shillings": "SHILLING", "szyling": "SHILLING",
    "szylingi": "SHILLING", "szylingów": "SHILLING",
}

HE_STOP = {
    "the", "a", "an", "and", "but", "or", "if", "so", "then", "there",
    "here", "he", "she", "it", "they", "we", "you", "i", "his", "her",
    "its", "their", "my", "our", "your", "this", "that", "when", "where",
    "who", "why", "how", "not", "no", "yes", "oh", "come", "let", "may",
    "must", "can", "pan", "pani", "panna", "w", "we", "na", "do", "z",
    "ze", "i", "a", "ale", "gdy", "kiedy", "tak", "nie", "to", "ten",
    "ta", "te", "ci", "on", "ona", "moje", "jego", "jej", "ich", "się",
    "że", "bo", "lecz", "więc", "już", "tylko", "żeby", "aby", "przez",
    "dla", "od", "po", "pod", "za", "bez", "który", "która", "które",
    "mr", "mrs", "miss", "sir", "lady", "lord", "dr",
}


def he_anchors(text: str) -> set[str]:
    out: set[str] = set()
    for tok in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż’'\-]+|\d+", text):
        low = tok.lower()
        if tok.isdigit():
            out.add("#" + tok)
        elif low in HE_NUM_WORDS:
            out.add("#" + HE_NUM_WORDS[low])
        if low in HE_MEASURE:
            out.add("@" + HE_MEASURE[low])
        if tok[:1].isupper() and len(tok) > 2 and low not in HE_STOP:
            out.add("N:" + low)
    return out


def he_is_dialogue(text: str) -> bool:
    s = text.lstrip()
    return s[:1] in ("—", "–", "“", '"')


def he_cost(
    pl: str,
    ens: list[str],
    ratio: float,
    pl_start: bool,
    pl_end: bool,
    en_start: bool,
    en_end: bool,
    cum_pl: int,
    cum_en: int,
    total_pl: int,
    total_en: int,
) -> float:
    en = " ".join(ens)
    ap, ae = he_anchors(pl), he_anchors(en)
    union, inter = ap | ae, ap & ae
    anchor_sim = len(inter) / len(union) if union else 0.35

    punct_pen = (
        abs(pl.count("?") - en.count("?"))
        + abs(pl.count("!") - en.count("!"))
        + abs(pl.count("…") - en.count("…"))
    )
    dial_pen = 0 if he_is_dialogue(pl) == he_is_dialogue(en) else 1

    sent_pen = abs(
        len(split_sentences(pl, PL_ABBREV)) - len(ens)
    )

    len_pen = abs(math.log((len(en) + 1.0) / ((len(pl) + 1.0) * ratio)))

    # paragraph boundaries: a PL paragraph change should land on an EN one
    bound = 0.0
    if pl_start:
        bound += -0.55 if en_start else 0.30
    if pl_end:
        bound += -0.55 if en_end else 0.30
    if not pl_start and en_start:
        bound += 0.20
    if not pl_end and en_end:
        bound += 0.20

    cum_pen = abs(cum_en / max(1, total_en) - cum_pl / max(1, total_pl))

    return (
        2.5 * (1.0 - anchor_sim)
        + 0.45 * punct_pen
        + 0.55 * dial_pen
        + 0.35 * sent_pen
        + 0.55 * len_pen
        + bound
        + 1.2 * cum_pen
    )


def heuristic_counts(
    pls: list[str],
    segs: list[str],
    pl_para: list[int],
    en_para: list[int],
    maxspan: int = 10,
) -> list[int]:
    """Monotonic alignment of PL units to EN segments. Returns counts."""
    n, m = len(pls), len(segs)
    if m < n:
        raise ValueError(f"not enough EN segments ({m}) for {n} PL units")
    ratio = (sum(len(s) for s in segs) + 1.0) / (sum(len(p) for p in pls) + 1.0)
    cum_pl = [0]
    for p in pls:
        cum_pl.append(cum_pl[-1] + len(p))
    cum_en = [0]
    for s in segs:
        cum_en.append(cum_en[-1] + len(s))
    total_pl, total_en = max(1, cum_pl[-1]), max(1, cum_en[-1])

    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        pl = pls[i - 1]
        pl_start = i == 1 or pl_para[i - 1] != pl_para[i - 2]
        pl_end = i == n or pl_para[i - 1] != pl_para[i]
        for j in range(i, m - (n - i) + 1):
            best, best_k = INF, -1
            lo = max(i - 1, j - maxspan)
            for k in range(lo, j):
                if dp[i - 1][k] == INF:
                    continue
                en_start = k == 0 or en_para[k] != en_para[k - 1]
                en_end = j == m or en_para[j - 1] != en_para[j]
                c = dp[i - 1][k] + he_cost(
                    pl, segs[k:j], ratio, pl_start, pl_end, en_start, en_end,
                    cum_pl[i], cum_en[j], total_pl, total_en,
                )
                if c < best:
                    best, best_k = c, k
            dp[i][j] = best
            back[i][j] = best_k
    if dp[n][m] == INF:
        raise RuntimeError("no heuristic alignment path")

    counts: list[int] = []
    j = m
    for i in range(n, 0, -1):
        k = back[i][j]
        counts.append(j - k)
        j = k
    counts.reverse()
    return counts


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def llm_chat(cfg: dict, messages: list[dict], json_mode: bool = True) -> str:
    if not cfg.get("key"):
        raise RuntimeError(
            "no API key: set TRILINGUAL_API_KEY, OPENAI_API_KEY or HF_TOKEN, "
            "or pass --api-key"
        )
    url = cfg["base"].rstrip("/") + "/chat/completions"
    body = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["key"],
    }

    def call(payload):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]

    try:
        return call(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        if json_mode and e.code in (400, 404, 422):
            body.pop("response_format", None)
            try:
                return call(body)
            except urllib.error.HTTPError as e2:
                detail = e2.read().decode("utf-8", "replace")[:500]
                raise RuntimeError(f"API HTTP {e2.code}: {detail}") from e2
        raise RuntimeError(f"API HTTP {e.code}: {detail}") from e


def llm_counts(
    cfg: dict,
    pls: list[str],
    segs: list[str],
    pl_para_of: list[int] | None = None,
    en_para_of: list[int] | None = None,
) -> list[int]:
    n, m = len(pls), len(segs)
    if m < n:
        raise ValueError(f"not enough EN segments ({m}) for {n} PL units")

    if pl_para_of is not None:
        pl_block = "\n".join(
            f"{i}. (PL para {pl_para_of[i]}) {p}" for i, p in enumerate(pls)
        )
    else:
        pl_block = "\n".join(f"{i}. {p}" for i, p in enumerate(pls))
    if en_para_of is not None:
        en_block = "\n".join(
            f"{i}. (EN para {en_para_of[i]}) {s}" for i, s in enumerate(segs)
        )
    else:
        en_block = "\n".join(f"{i}. {s}" for i, s in enumerate(segs))
    base = [
        {
            "role": "system",
            "content": (
                "You are a careful bilingual alignment assistant for a Polish "
                "translation of an English novel. You output JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Align the Polish units below with the English segments. Both are "
                "the same chapter in narrative order.\n\n"
                f"Return JSON: {{\"counts\": [c0, c1, ...]}}\n"
                f"- There are {n} Polish units and {m} English segments.\n"
                "- counts[i] is the number of consecutive English segments assigned "
                "to Polish unit i.\n"
                "- Every count must be an integer >= 1.\n"
                f"- The counts must sum to exactly {m}.\n"
                "- Keep sentences, quoted speech, names and titles intact. A unit may "
                "take several segments when the English passage is longer.\n"
                "- Paragraph markers (PL para / EN para) are hints only. Paragraph "
                "counts differ between the two editions, so do not require them to "
                "match.\n"
                "- Do not skip or reorder anything.\n\n"
                f"POLISH UNITS:\n{pl_block}\n\nENGLISH SEGMENTS:\n{en_block}"
            ),
        },
    ]
    messages = base
    last_error = ""
    for _ in range(3):
        text = llm_chat(cfg, messages)
        try:
            data = _parse_json(text)
            counts = [int(x) for x in data["counts"]]
            if len(counts) != n:
                raise ValueError(f"expected {n} counts, got {len(counts)}")
            if any(c < 1 for c in counts):
                raise ValueError("every count must be >= 1")
            if sum(counts) != m:
                raise ValueError(f"counts sum to {sum(counts)}, expected {m}")
            return counts
        except Exception as e:  # noqa: BLE001 - report the model's error back
            last_error = str(e)
            messages = base + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"Your previous answer was invalid: {last_error}. "
                        "Return only corrected JSON."
                    ),
                },
            ]
    raise RuntimeError(f"LLM alignment failed after 3 attempts: {last_error}")


def llm_comments(cfg: dict, pairs: list[tuple[str, str]]) -> dict[int, str]:
    block = []
    for i, (pl, en) in enumerate(pairs):
        block.append(f"{i}.\nPL: {pl}\nEN: {en}")
    prompt = (
        "For each numbered unit, compare the Polish (PL) and English (EN) text. "
        "Return JSON: {\"comments\": {\"<unit index>\": \"<short comment>\"}}.\n"
        "Include a unit ONLY when there is a substantive divergence:\n"
        "- a number, date, time or measure that differs;\n"
        "- a sentence or clause present in one language but absent in the other;\n"
        "- a factual difference (for example, the position of a body, or who did "
        "what).\n"
        "Do NOT comment on paragraph breaks, punctuation, or small wording "
        "differences. EN chunks are an automatic partition and may end mid-"
        "sentence; ignore that. Keep every comment under 180 characters. Omit "
        "units with no such divergence.\n\n"
        + "\n\n".join(block)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You compare a Polish literary translation with its English source "
                "and report only substantive divergences. Output JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    text = ""
    data = None
    last_error = ""
    for _ in range(2):
        text = llm_chat(cfg, messages)
        try:
            data = _parse_json(text)
            if not isinstance(data.get("comments", {}), dict):
                raise ValueError("'comments' must be an object")
            break
        except Exception as e:  # noqa: BLE001 - report the model's error back
            last_error = str(e)
            messages = messages + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"Your previous answer was invalid: {last_error}. "
                        'Return only corrected JSON of the form '
                        '{"comments": {"<unit index>": "<comment>"}}.'
                    ),
                },
            ]
    if data is None:
        raise RuntimeError(f"LLM comment generation failed: {last_error}")
    raw = data.get("comments", {})
    out: dict[int, str] = {}
    for k, v in raw.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(pairs) and isinstance(v, str) and v.strip():
            out[idx] = re.sub(r"\s+", " ", v.strip())[:220]
    return out


# --------------------------------------------------------------------------
# assembly and verification
# --------------------------------------------------------------------------

def assemble(chapter: int, title: str, units: list[dict], ua: dict[int, str]) -> str:
    lines = [
        header_line(chapter, title),
        "<!-- trilingual study edition: EN → PL → UA -->",
        "",
    ]
    prev_para = None
    for n, u in enumerate(units):
        if prev_para is not None and u["plp"] != prev_para:
            lines.extend(["---", ""])
        lines.extend(
            [
                "> **EN:** " + u["en"],
                "",
                "**PL:** " + u["pl"],
                "",
                "**UA:** " + ua.get(n, ""),
                "",
            ]
        )
        if u.get("comment"):
            lines.extend(["<!-- ALIGNMENT: " + u["comment"] + " -->", ""])
        prev_para = u["plp"]
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_built(text: str) -> tuple[list[dict], list[int]]:
    lines = text.split("\n")
    units: list[dict] = []
    seps: list[int] = []
    cur = None
    pending_sep = False
    for line in lines[2:]:
        if line == "---":
            seps.append(len(units))
            pending_sep = True
            continue
        if line.startswith("> **EN:** "):
            if cur is not None:
                raise ValueError("EN line before previous unit closed")
            cur = {"en": line[len("> **EN:** "):], "sep_before": pending_sep}
            pending_sep = False
        elif line.startswith("**PL:** "):
            if cur is None or "pl" in cur:
                raise ValueError("unexpected PL line")
            cur["pl"] = line[len("**PL:** "):]
        elif line.startswith("**UA:** "):
            if cur is None or "ua" in cur:
                raise ValueError("unexpected UA line")
            cur["ua"] = line[len("**UA:** "):]
            units.append(cur)
            cur = None
        elif line.startswith("<!-- ALIGNMENT: "):
            if not units or units[-1].get("comment"):
                raise ValueError("unexpected ALIGNMENT comment")
            units[-1]["comment"] = line[len("<!-- ALIGNMENT: "):-len(" -->")]
        elif line == "":
            pass
        else:
            raise ValueError("unexpected line: " + repr(line))
    if cur is not None:
        raise ValueError("unclosed unit")
    if pending_sep:
        raise ValueError("trailing separator")
    return units, seps


def quote_balance(t: str, o: str, c: str) -> tuple[int, int]:
    d = 0
    mn = 0
    for ch in t:
        if ch == o:
            d += 1
        elif ch == c:
            d -= 1
        mn = min(mn, d)
    return d, mn


def has_digits(t: str) -> bool:
    t = re.sub(r"<sup>\d+</sup>", "", t)
    t = re.sub(r"\[\d+\]", "", t)
    return bool(re.search(r"\d", t))


def verify_text(
    text: str,
    chapter: int,
    title: str,
    raw: dict,
    units_meta: list[dict] | None,
    allow_empty: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    if text.startswith("\ufeff"):
        problems.append("BOM found")
    if "\r" in text:
        problems.append("CR found")
    if not text.endswith("\n"):
        problems.append("no trailing newline")

    lines = text.split("\n")
    expected = header_line(chapter, title)
    if lines[0] != expected:
        problems.append(f"bad header: {lines[0]!r}")
    if lines[1] != "<!-- trilingual study edition: EN → PL → UA -->":
        problems.append(f"bad edition comment: {lines[1]!r}")

    try:
        units, seps = parse_built(text)
    except ValueError as e:
        return False, [f"parse error: {e}"]

    pl_paras = raw["pl"]
    en_paras = raw["en"]

    groups: list[list[dict]] = []
    g: list[dict] = []
    for u in units:
        if u["sep_before"] and g:
            groups.append(g)
            g = []
        g.append(u)
    if g:
        groups.append(g)
    for gi, grp in enumerate(groups):
        for u in grp:
            u['plp'] = gi

    # A group normally equals one PL paragraph; a group may also cover several
    # consecutive paragraphs when short replies were merged (merge_short_units).
    pi = 0
    merged_groups: list[tuple[int, int]] = []
    for gi, grp in enumerate(groups):
        joined = ws(" ".join(u["pl"] for u in grp))
        acc: list[str] = []
        matched = False
        while pi + len(acc) < len(pl_paras):
            acc.append(pl_paras[pi + len(acc)])
            if ws(" ".join(acc)) == joined:
                matched = True
                break
        if not matched:
            problems.append(f"PL reassembly mismatch in paragraph group {gi + 1}")
            break
        if len(acc) > 1:
            merged_groups.append((gi + 1, len(acc)))
        pi += len(acc)
    else:
        if pi != len(pl_paras):
            problems.append(f"PL paragraphs left over: used {pi} of {len(pl_paras)}")
    for gi, k in merged_groups:
        warnings.append(f"group {gi} spans {k} PL paragraphs (short replies merged)")

    if ws(" ".join(u["en"] for u in units)) != ws(" ".join(en_paras)):
        problems.append("EN reassembly mismatch")

    if len(seps) != max(0, len(groups) - 1):
        problems.append(f"separators {len(seps)} != {len(groups) - 1}")
    for s in seps:
        if s <= 0 or units[s - 1].get("plp") is None or units[s].get("plp") is None:
            continue
        if units[s - 1]["plp"] == units[s]["plp"]:
            problems.append(f"separator inside paragraph at unit {s}")

    for i, u in enumerate(units):
        for k in ("en", "pl", "ua"):
            if not u[k].strip() and not (k == "ua" and allow_empty):
                problems.append(f"unit {i + 1}: empty {k.upper()}")
        if not allow_empty and u["ua"].strip():
            if not re.search(r"[А-Яа-яІіЇїЄєҐґ]", u["ua"]):
                problems.append(f"unit {i + 1}: UA has no Cyrillic")
            if re.search(r"[ąęłńśźż]", u["ua"]):
                problems.append(f"unit {i + 1}: Polish diacritic in UA")

    pl_sup = re.findall(r"<sup>(\d+)</sup>", " ".join(u["pl"] for u in units))
    ua_sup = re.findall(r"<sup>(\d+)</sup>", " ".join(u["ua"] for u in units))
    if not allow_empty and sorted(pl_sup) != sorted(ua_sup):
        problems.append(f"footnote markers PL {sorted(pl_sup)} != UA {sorted(ua_sup)}")

    over = [(i + 1, len(u["pl"])) for i, u in enumerate(units) if len(u["pl"]) > limit]
    for idx, ln in over:
        warnings.append(f"unit {idx} is {ln} PL chars")
    too_short = [i + 1 for i, u in enumerate(units) if short_unit(u["pl"])]
    if too_short:
        warnings.append(
            "units too short for an audio section (<~0.8 s): " + ", ".join(map(str, too_short))
        )

    digit_xor = []
    for i, u in enumerate(units):
        if has_digits(u["en"]) != has_digits(u["pl"]):
            digit_xor.append(i + 1)
    if digit_xor:
        warnings.append("digit XOR in units: " + ", ".join(map(str, digit_xor)))

    plq = quote_balance(" ".join(u["pl"] for u in units), "„", "”")
    uaq = quote_balance(" ".join(u["ua"] for u in units), "«", "»")
    enq = quote_balance(" ".join(u["en"] for u in units), "“", "”")
    if not allow_empty and plq != (0, 0):
        problems.append(f"PL quote imbalance {plq}")
    if not allow_empty and uaq != (0, 0):
        problems.append(f"UA quote imbalance {uaq}")
    if enq != (0, 0):
        warnings.append(f"EN quote balance {enq} (may be a source artifact)")

    if units_meta is not None:
        if len(units) != len(units_meta):
            problems.append(f"unit count {len(units)} != prepared {len(units_meta)}")
        else:
            for i, (u, m) in enumerate(zip(units, units_meta)):
                if u["pl"] != m["pl"]:
                    problems.append(f"unit {i + 1}: PL text differs from prepared units")
                    break
                if u["en"] != m["en"]:
                    problems.append(f"unit {i + 1}: EN text differs from prepared units")
                    break

    print(f"units {len(units)}  groups {len(groups)}  separators {len(seps)}  "
          f"comments {sum(1 for u in units if u.get('comment'))}")
    print(f"max PL {max(len(u['pl']) for u in units)}  "
          f"max EN {max(len(u['en']) for u in units)}  "
          f"max UA {max(len(u['ua']) for u in units)}")
    for w in warnings:
        print("WARN:", w)
    for p in problems:
        print("FAIL:", p)
    return not problems, problems


# --------------------------------------------------------------------------
# UA file loading
# --------------------------------------------------------------------------

def load_ua(path: Path, n: int) -> dict[int, str]:
    if not path.exists():
        raise SystemExit(f"UA file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {int(k): str(v) for k, v in data.items()}
    if path.name.endswith(".tsv"):
        out = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            if "\t" not in line:
                continue
            k, v = line.split("\t", 1)
            try:
                out[int(k)] = v
            except ValueError:
                continue
        return out
    # scaffold: ### N blocks with a UA: line
    out = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+(\d+)\s*$", line)
        if m:
            cur = int(m.group(1))
            continue
        if cur is not None and line.startswith("UA:"):
            out[cur] = line[3:].strip()
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def work_dir(args, chapter: int) -> Path:
    return (args.work or (args.root / "work")) / f"chapter-{chapter:02d}"


def out_file(args, chapter: int) -> Path:
    return (args.out or args.root) / f"chapter-{chapter:02d}.md"


def cmd_list(args):
    print(f"{'#':>2}  {'title':<52}  PL paras  EN paras")
    for ch in range(1, int(CONFIG["chapters"]) + 1):
        try:
            raw = load_chapter(args.root, ch)
        except Exception as e:  # noqa: BLE001
            print(f"{ch:>2}  ERROR: {e}")
            continue
        print(f"{ch:>2}  {raw['title'][:52]:<52}  {len(raw['pl']):>7}  {len(raw['en']):>7}")


def cmd_prepare(args):
    chapter = args.chapter
    root = args.root
    wd = work_dir(args, chapter)
    wd.mkdir(parents=True, exist_ok=True)

    raw = load_chapter(root, chapter)
    pls: list[str] = []
    pl_para_of: list[int] = []
    for pi, para in enumerate(raw["pl"]):
        for part, chunk in enumerate(chunk_pl(para, args.limit)):
            pls.append(chunk)
            pl_para_of.append(pi)
    if not pls:
        raise SystemExit("no Polish text found")

    en_segs: list[str] = []
    en_para_of: list[int] = []
    for pi, para in enumerate(raw["en"]):
        for sent in split_sentences(para, EN_ABBREV):
            en_segs.append(sent)
            en_para_of.append(pi)

    cfg = {
        "base": args.api_base
        or os.environ.get("TRILINGUAL_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1",
        "key": args.api_key
        or os.environ.get("TRILINGUAL_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("HF_TOKEN"),
        "model": args.model
        or os.environ.get("TRILINGUAL_MODEL")
        or "gpt-4o-mini",
    }

    mode = args.align
    if mode == "auto":
        mode = "llm" if cfg["key"] else "heuristic"

    used = mode
    counts: list[int] | None = None
    en_units: list[str]
    if mode == "llm":
        if len(en_segs) < len(pls):
            used = "heuristic"
        else:
            try:
                counts = llm_counts(cfg, pls, en_segs, pl_para_of, en_para_of)
            except Exception as e:  # noqa: BLE001
                print(f"LLM alignment failed: {e}", file=sys.stderr)
                print("Falling back to heuristic alignment.", file=sys.stderr)
                used = "heuristic"

    if used == "heuristic" and counts is None:
        if len(en_segs) < len(pls):
            used = "proportional"
        else:
            try:
                counts = heuristic_counts(pls, en_segs, pl_para_of, en_para_of)
            except Exception as e:  # noqa: BLE001
                print(f"Heuristic alignment failed: {e}", file=sys.stderr)
                print("Falling back to proportional alignment.", file=sys.stderr)
                used = "proportional"

    if counts is None:
        if len(en_segs) < len(pls):
            # word-level fallback: split EN words proportionally
            words = " ".join(raw["en"]).split()
            wcounts = proportional_counts(pls, len(words))
            en_units = []
            pos = 0
            for c in wcounts:
                en_units.append(" ".join(words[pos:pos + c]))
                pos += c
            used = "proportional-words"
        else:
            en_units = align_proportional(pls, en_segs)
    else:
        en_units = []
        pos = 0
        for c in counts:
            en_units.append(" ".join(en_segs[pos:pos + c]))
            pos += c

    # attach paragraph positions
    units = []
    idx = 0
    for pi, para in enumerate(raw["pl"]):
        parts = chunk_pl(para, args.limit)
        for part, chunk in enumerate(parts):
            if idx >= len(pls):
                break
            if pls[idx] != chunk:
                # should not happen, but keep the audit honest
                raise RuntimeError(f"chunk bookkeeping mismatch at unit {idx}")
            units.append(
                {
                    "plp": pi,
                    "plpart": part,
                    "pl": chunk,
                    "en": en_units[idx],
                    "comment": None,
                }
            )
            idx += 1

    merge_log: list[str] = []
    if not args.no_merge_short:
        units, merge_log = merge_short_units(units, args.limit, args.min_words, args.min_chars)

    # comments
    cmode = args.comments
    if cmode == "auto":
        cmode = "llm" if used == "llm" else "none"
    comment_note = ""
    if cmode == "llm":
        try:
            pairs = [(u["pl"], u["en"]) for u in units]
            comments = llm_comments(cfg, pairs)
            for i, c in comments.items():
                units[i]["comment"] = c
            comment_note = f"llm ({len(comments)})"
        except Exception as e:  # noqa: BLE001
            print(f"LLM comment generation failed: {e}", file=sys.stderr)
            comment_note = "none (LLM error)"
    else:
        comment_note = "none"

    meta = {
        "chapter": chapter,
        "title": raw["title"],
        "pl_title": raw["pl_title"],
        "alignment": used,
        "model": cfg["model"] if used == "llm" else None,
        "comment_source": comment_note,
        "limit": args.limit,
        "merges": merge_log,
        "pl_file": raw["pl_file"],
        "en_file": raw["en_file"],
        "units": units,
    }
    (wd / "raw.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (wd / "units.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    ua_path = wd / "ua.json"
    if args.reset_ua or not ua_path.exists():
        ua_path.write_text(
            json.dumps({str(i): "" for i in range(len(units))}, ensure_ascii=False, indent=1)
            + "\n",
            encoding="utf-8",
        )
    else:
        try:
            old = json.loads(ua_path.read_text(encoding="utf-8"))
            if len(old) != len(units):
                print(
                    f"warning: kept {ua_path} has {len(old)} entries but the new "
                    f"unit count is {len(units)}; use --reset-ua to start over",
                    file=sys.stderr,
                )
        except Exception:  # noqa: BLE001 - leave a malformed file for build to report
            pass
    tsv_path = wd / "ua.tsv"
    if args.reset_ua or not tsv_path.exists():
        tsv_path.write_text(
            "".join(f"{i}\t\n" for i in range(len(units))), encoding="utf-8"
        )

    # readable scaffold; never clobber a scaffold the user has already filled
    scaf = [
        f"# Chapter {chapter}: {raw['title']}",
        f"# PL source: {raw['pl_file']}",
        f"# EN source: {raw['en_file']}",
        f"# Alignment: {used}",
        "# Fill the UA: line for every unit, then run:",
        f"#   python3 trilingual.py build {chapter} --ua {wd / 'scaffold.txt'}",
        "# Do not edit the PL: or EN: lines.",
        "",
    ]
    for i, u in enumerate(units):
        scaf.extend(
            [
                f"### {i}",
                "PL: " + u["pl"],
                "EN: " + u["en"],
                "UA:",
                "",
            ]
        )
    scaffold_path = wd / "scaffold.txt"
    filled = False
    if scaffold_path.exists() and not args.reset_ua:
        for line in scaffold_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("UA:") and line[3:].strip():
                filled = True
                break
    if filled:
        alt = wd / "scaffold.new.txt"
        alt.write_text("\n".join(scaf), encoding="utf-8")
        print(
            f"kept filled {scaffold_path}; new scaffold written to {alt}",
            file=sys.stderr,
        )
    else:
        scaffold_path.write_text("\n".join(scaf), encoding="utf-8")

    # diagnostics
    over = [(i + 1, len(u["pl"])) for i, u in enumerate(units) if len(u["pl"]) > args.limit]
    ratios = []
    for i, u in enumerate(units):
        ratio = len(u["en"]) / max(1, len(u["pl"]))
        if ratio > 3.0 or ratio < 0.25:
            ratios.append((i + 1, round(ratio, 2)))
    lines = [
        f"chapter {chapter}: {raw['title']}",
        f"PL paragraphs: {len(raw['pl'])}",
        f"PL units: {len(units)}",
        f"EN segments: {len(en_segs)}",
        f"alignment: {used}",
        f"comments: {comment_note}",
        f"over {args.limit} PL chars: {over if over else 'none'}",
        f"short-unit merges ({len(merge_log)}): " + ("; ".join(merge_log) if merge_log else "none"),
        f"suspicious EN/PL length ratios: {ratios if ratios else 'none'}",
        f"UA scaffold: {wd / 'scaffold.txt'}",
        f"UA JSON: {ua_path}",
        f"next: fill UA, then python3 trilingual.py build {chapter}",
    ]
    (wd / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def cmd_build(args):
    chapter = args.chapter
    wd = work_dir(args, chapter)
    units_path = wd / "units.json"
    raw_path = wd / "raw.json"
    if not units_path.exists() or not raw_path.exists():
        raise SystemExit(f"no prepared data in {wd}; run: prepare {chapter}")
    meta = json.loads(units_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    units = meta["units"]
    n = len(units)

    if args.ua is not None:
        ua_path = Path(args.ua)
    else:
        # Pick whichever prepared UA source actually holds the most text, so a
        # filled scaffold.txt is not ignored just because ua.json exists empty.
        candidates = [wd / "ua.json", wd / "ua.tsv", wd / "scaffold.txt"]
        best, best_count = wd / "ua.json", -1
        for cand in candidates:
            if not cand.exists():
                continue
            try:
                count = sum(1 for v in load_ua(cand, n).values() if v.strip())
            except Exception:  # noqa: BLE001 - a broken source is not a candidate
                continue
            if count > best_count:
                best, best_count = cand, count
        ua_path = best
    ua = load_ua(Path(ua_path), n)
    stray = sorted(k for k in ua if not 0 <= k < n)
    if stray:
        print(f"warning: ignoring {len(stray)} UA key(s) outside 0..{n - 1}: {stray[:10]}",
              file=sys.stderr)

    missing = [i for i in range(n) if not ua.get(i, "").strip()]
    if missing and not args.allow_empty:
        print(f"missing UA for {len(missing)} of {n} units: {missing[:15]}", file=sys.stderr)
        print(f"source: {ua_path}", file=sys.stderr)
        print(f"fill {wd / 'ua.json'} or {wd / 'scaffold.txt'}", file=sys.stderr)
        return 1

    text = assemble(chapter, meta["title"], units, ua)
    built = wd / f"chapter-{chapter:02d}.md"
    with open(built, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    ok, problems = verify_text(
        text, chapter, meta["title"], raw, units, args.allow_empty, args.limit
    )
    if not ok:
        print(f"verification failed; file left at {built}", file=sys.stderr)
        return 1

    dest = out_file(args, chapter)
    if dest.exists() and not args.force:
        print(f"refusing to overwrite {dest} (use --force)", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {dest}")
    return 0


def cmd_verify(args):
    chapter = args.chapter
    wd = work_dir(args, chapter)
    path = args.file or out_file(args, chapter)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    raw_path = wd / "raw.json"
    if raw_path.exists():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        # No prepared data: rebuild the reference paragraphs from the EPUBs so
        # hand-built chapters can still be checked for structure and reassembly.
        try:
            raw = load_chapter(args.root, chapter)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"no raw.json in {wd} and EPUB extraction failed: {e}")
        print(f"note: no prepared data in {wd}; verifying against the EPUBs", file=sys.stderr)
    units_meta = None
    units_path = wd / "units.json"
    if units_path.exists():
        units_meta = json.loads(units_path.read_text(encoding="utf-8"))["units"]
    title = raw.get("title", "")
    ok, _ = verify_text(
        text, chapter, title, raw, units_meta, args.allow_empty, args.limit
    )
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Standalone trilingual chapter builder (EN -> PL -> UA)."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="book folder holding book.config.json and the source files (default: current directory)",
    )
    common.add_argument(
        "--work",
        type=Path,
        default=None,
        help="work directory (default: <root>/work)",
    )
    common.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory for chapter-NN.md (default: <root>)",
    )
    common.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="max PL unit length"
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", parents=[common], help="list chapters")
    p_list.set_defaults(func=cmd_list)

    p_prep = sub.add_parser("prepare", parents=[common], help="extract, chunk, align")
    p_prep.add_argument("chapter", type=int)
    p_prep.add_argument(
        "--align",
        choices=("auto", "llm", "heuristic", "proportional"),
        default="auto"
    )
    p_prep.add_argument("--comments", choices=("auto", "llm", "none"), default="auto")
    p_prep.add_argument("--api-base", default=None)
    p_prep.add_argument("--api-key", default=None)
    p_prep.add_argument("--model", default=None)
    p_prep.add_argument("--reset-ua", action="store_true")
    p_prep.add_argument(
        "--no-merge-short", action="store_true",
        help="keep one-word replies as separate units (they may be merged by the audio aligner)",
    )
    p_prep.add_argument("--min-words", type=int, default=MIN_WORDS)
    p_prep.add_argument("--min-chars", type=int, default=MIN_CHARS)
    p_prep.set_defaults(func=cmd_prepare)

    p_build = sub.add_parser("build", parents=[common], help="assemble and verify")
    p_build.add_argument("chapter", type=int)
    p_build.add_argument("--ua", type=Path, default=None, help="UA JSON/TSV/scaffold")
    p_build.add_argument("--allow-empty", action="store_true")
    p_build.add_argument("--force", action="store_true")
    p_build.set_defaults(func=cmd_build)

    p_ver = sub.add_parser("verify", parents=[common], help="verify a built file")
    p_ver.add_argument("chapter", type=int)
    p_ver.add_argument("--file", type=Path, default=None)
    p_ver.add_argument("--allow-empty", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    global CONFIG
    args.root = args.root.resolve()
    CONFIG = load_config(args.root)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
