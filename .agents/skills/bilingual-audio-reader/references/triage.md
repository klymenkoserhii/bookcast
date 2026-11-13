# Triage: deciding whether an alignment is trustworthy

Run `check_chapter.py chapter-NN.md` after every alignment. Every real chapter produced a few flags. Almost all were false alarms, but a handful were genuine bugs, and the difference is only visible by reading the ASR words around the start. This file is the decision guide.

## How the aligner works (so the verdicts make sense)

1. faster-whisper transcribes the whole MP3 to word-level timestamps.
2. All Polish tokens of the chapter are concatenated and matched against the ASR words with one global sequence alignment (`difflib`). One global pass is far more robust than per-sentence search: a misheard word in one sentence cannot steal the next sentence's start.
3. Per unit: `confidence = matched tokens / total tokens`. The start is the first matched ASR word minus a 0.12 s lead.
4. Start-word repair (details below), then timeline repair: strictly increasing, with a 0.8 s minimum section length.

## Flags and what they usually mean

### `LOW CONFIDENCE` (confidence below 0.6)

Usually a **false alarm**: the narrator's wording differs from the text, so few tokens match, but the start is on the right word. Check by reading the `ASR:` context line `check_chapter.py` prints. The start should sit on the first spoken word of the unit.

Common benign causes seen in practice:

| Text | Heard | Why |
|---|---|---|
| `— Dobrze, sir.` | "Dobrze, ser" | English loanword respelled |
| `Dr. Watson` | "Doktor Watson" | abbreviation expanded |
| `740 000 funtów` | "Siedemset czterdzieści tysięcy funtów" | numerals spoken in full |
| `mimo woli` | "mimowoli" | one word vs two |
| `Carterright.` | "Cartwright" | proper-name spelling |

Two-to-four-word units are the most prone to this: one misheard word is 25–50 % of the sentence.

**Genuine problem** (fix needed): the start is on the wrong word, for example a whole sentence early or late. See "Real bugs" below.

### Merged section (`null` timestamp, "merged into previous (<0.8s)")

A unit whose start would be less than 0.8 s after the previous unit's start is merged, which is the specified behaviour, because a button that plays under a second is useless. In practice this only happens with one-word replies in fast dialogue (`— Nie.`, `— Tak.`, `— Poznam.`). The previous section then plays through into the merged one, and the merged card's ▶ button is disabled.

Do not "fix" this silently. Report each merge with the true start the audio shows (the merged unit's first ASR word minus the lead) and offer the user a choice: keep, or lower the threshold with `--min-dur 0.5` for that book and rebuild. `--reuse-asr` makes a rebuild take seconds.

### First word heard differs from the text

Almost always harmless. Categories:

- **Spelling variants**: `sir`/"Ser", `Stapleton`/"Stapelton", `były`/"Był". The start lands on the right word.
- **Split or joined words**: `Nazajutrz` → "Na zajutrz", `Skądinąd` → "Skąd inąd". The aligner re-joins these, so the start is on the first piece.
- **Dropped lead word**: the translation says "Tak, moje ciało..." but the narrator starts "Moje ciało...", or an interjection like `Hm!`/`Ach` is not read. The start is correctly on the next spoken word.

## Real bugs seen, and what fixed them

These are already handled in the bundled `align_audio.py`. They are listed so you recognise the symptoms if a new book shows something similar.

| Symptom | Cause | Handled by |
|---|---|---|
| A section starts 1–3 s **early**, inside the previous sentence | Start-word repair stepped back past the previous sentence's last word | repair floor = previous unit's last *matched* word, plus guards on the previous tail |
| A section starts 0.3–1 s **late**: first word misheard ("Heat" → "Kit") | LCS match begins at the second word | step back by the number of skipped tokens (structural, not similarity-based) |
| Section starts 2–3 s late; name misspelled ("Verloc" → "Werlok") | similarity 0.67 under the 0.72 threshold | phonetic fold (v↔w, c↔k) |
| A zero-match unit placed far from the audio; neighbours get wrongly merged | blind interpolation between neighbours | anchor on the ASR words that sit between the neighbours |
| `740 000` starts after "Siedemset" | numerals are several spoken words | digit-leading units step back further |
| A whispered line ("— Psst! — szepnął Holmes.") is missing; a 5–6 s hole in the transcript | VAD discarded quiet speech | `--fill-gaps 3.0` re-transcribes word-less stretches with VAD off |

If you see a **new** kind of error, inspect the words around it:

```bash
./.venv-asr/bin/python - <<'PY'
import json
d = json.load(open('chapter-03.asr.json')); w = d['words']
print(" ".join(f"{x['w']}[{x['start']:.2f}-{x['end']:.2f}]" for x in w if 59 <= x['start'] <= 66))
PY
```

Then fix the **aligner** (generalise the rule) and re-run every previously built chapter with `--reuse-asr` to prove nothing else moved:

```bash
./.venv-asr/bin/python align_audio.py chapter-NN.md <audio> --reuse-asr chapter-NN.asr.json --js-out chapter-NN.audio-times.js
```

Compare each chapter's `start` values before and after. Changes should be limited to the units you meant to fix. This is how a fix made on chapter 6 was shown safe for chapters 1–5.

## Hand-editing a single timestamp

Last resort for one-off cases: use the chapter's `*.timestamp-helper.html` (Space stamps the current playback time per section), paste the resulting `AUDIO_TIMES` block into the reader's section 2. The reader has no other state. Note that rebuilding with `build_reader.py` regenerates from the sidecar and overwrites a hand-edited array, so prefer fixing the aligner.

## Reporting

For each chapter report: units/timed, mean and min confidence, every flag with a one-line verdict, merged sections with their true start, and what was verified. State plainly what was *not* verified (for example a screenshot that could not be taken).
