#!/usr/bin/env bash
# setup_book.sh — prepare a book folder for the trilingual audio reader pipeline.
#
#   bash setup_book.sh /path/to/book-folder
#
# 1. copies the pipeline scripts and templates into the book folder (the generated
#    HTML tells you to re-run "./.venv-asr/bin/python align_audio.py ..." from there,
#    so the scripts must sit next to the chapters);
# 2. makes <book>/.venv-asr point at one shared Python environment that has
#    faster-whisper installed, creating that environment once if it is missing.
#
# The shared environment lives in ~/.cache/trilingual-asr-venv so a second book
# costs seconds, not a 1 GB re-install. The Whisper model itself (large-v3-turbo,
# ~1.6 GB) downloads on the first transcription and is cached by Hugging Face.
set -euo pipefail

BOOK="${1:?usage: setup_book.sh /path/to/book-folder}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${TRILINGUAL_VENV:-$HOME/.cache/trilingual-asr-venv}"

mkdir -p "$BOOK"
for f in align_audio.py build_reader.py check_chapter.py convert_audio_to_opus.py range_server.py build_index.py \
         reader.template.html timestamphelper.template.html index.template.html; do
  # Never overwrite a customised copy silently.
  if [ -e "$BOOK/$f" ] && ! cmp -s "$HERE/$f" "$BOOK/$f"; then
    echo "keeping existing (differs from skill copy): $BOOK/$f"
  else
    cp "$HERE/$f" "$BOOK/$f"
  fi
done

if [ ! -x "$VENV/bin/python" ]; then
  echo "creating shared environment at $VENV (first time only) ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet faster-whisper
fi
"$VENV/bin/python" -c "import faster_whisper, av; print('faster-whisper', faster_whisper.__version__, 'ok')"

if [ ! -e "$BOOK/.venv-asr" ]; then
  ln -s "$VENV" "$BOOK/.venv-asr"
fi
echo "ready: $BOOK"
echo "next:  cd \"$BOOK\" && ./.venv-asr/bin/python align_audio.py chapter-01.md <audio.mp3> --js-out chapter-01.audio-times.js"
