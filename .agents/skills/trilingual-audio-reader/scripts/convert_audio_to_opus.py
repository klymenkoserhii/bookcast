#!/usr/bin/env python3
"""Encode an aligned chapter's original MP3 as a mono Opus/WebM reader asset."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import av


def duration_seconds(container: av.container.InputContainer) -> float | None:
    if container.duration is not None:
        return float(container.duration / av.time_base)
    stream = next((s for s in container.streams if s.type == "audio"), None)
    if stream is None or stream.duration is None or stream.time_base is None:
        return None
    return float(stream.duration * stream.time_base)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original MP3 used for ASR/alignment")
    parser.add_argument("--output", required=True, type=Path,
                        help="WebM output path, e.g. audio/chapter-03.webm")
    parser.add_argument("--bitrate", type=int, default=32000,
                        help="Opus target bitrate in bits/sec (default: 32000)")
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    args = parser.parse_args()

    source = args.source
    target = args.output
    if not source.is_file():
        parser.error(f"source audio does not exist: {source}")
    if target.suffix.lower() != ".webm":
        parser.error("output must use the .webm extension")
    if args.bitrate < 6000 or args.bitrate > 512000:
        parser.error("bitrate must be between 6000 and 512000 bits/sec")
    if target.exists() and not args.force:
        parser.error(f"output already exists (use --force to replace it): {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp.webm",
                                     dir=target.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with av.open(str(source)) as input_container:
            input_stream = next((s for s in input_container.streams if s.type == "audio"), None)
            if input_stream is None:
                parser.error(f"source has no audio stream: {source}")
            source_duration = duration_seconds(input_container)
            with av.open(str(temporary), mode="w", format="webm") as output_container:
                output_stream = output_container.add_stream(
                    "libopus", rate=48000,
                    options={"application": "audio", "vbr": "constrained"},
                )
                output_stream.layout = "mono"
                output_stream.bit_rate = args.bitrate
                resampler = av.AudioResampler(format="fltp", layout="mono", rate=48000)
                for frame in input_container.decode(input_stream):
                    for converted in resampler.resample(frame):
                        for packet in output_stream.encode(converted):
                            output_container.mux(packet)
                for converted in resampler.resample(None):
                    for packet in output_stream.encode(converted):
                        output_container.mux(packet)
                for packet in output_stream.encode(None):
                    output_container.mux(packet)

        with av.open(str(temporary)) as check:
            output_stream = next((s for s in check.streams if s.type == "audio"), None)
            output_duration = duration_seconds(check)
            decoded_frames = sum(1 for _ in check.decode(output_stream)) if output_stream else 0
            if output_stream is None or output_stream.codec_context.name != "opus":
                raise SystemExit("validation failed: output is not an Opus audio stream")
            if output_stream.codec_context.channels != 1 or decoded_frames == 0:
                raise SystemExit("validation failed: expected decodable mono audio")
        if source_duration is not None and output_duration is not None:
            if abs(source_duration - output_duration) > 1.0:
                raise SystemExit(
                    f"validation failed: output duration {output_duration:.2f}s differs "
                    f"from source {source_duration:.2f}s"
                )

        source_size = source.stat().st_size
        output_size = temporary.stat().st_size
        if target.exists() and not args.force:
            raise SystemExit(f"output appeared during encoding; not replacing: {target}")
        os.replace(temporary, target)
        if source_size and output_size <= source_size:
            size_note = f"{(1 - output_size / source_size) * 100:.1f}% smaller"
        elif source_size:
            size_note = f"{(output_size / source_size - 1) * 100:.1f}% larger"
        else:
            size_note = "source size unavailable"
        duration_text = f", {output_duration:.2f}s" if output_duration is not None else ""
        print(f"wrote {target}: {source_size:,} -> {output_size:,} bytes "
              f"({size_note}){duration_text}; Opus mono at {args.bitrate} bps")
        return 0
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
