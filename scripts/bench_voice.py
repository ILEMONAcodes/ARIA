"""Measure local STT and corpus WER on explicitly consented 16 kHz WAV clips.

uv run --locked --all-packages --all-extras --group voice python scripts/bench_voice.py \
    --model models/whisper --manifest /path/to/consented/manifest.json
No recordings or transcripts are included in the aggregate JSON output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import wave
from pathlib import Path

from agent.audio.metrics import WordErrors, score_words
from agent.audio.native import WhisperSTT


async def benchmark(model: Path, manifest: Path) -> dict[str, int | float]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("consented") is not True or not data.get("clips"):
        raise ValueError("An explicitly consented, nonempty recording manifest is required")
    scores: list[WordErrors] = []
    elapsed: list[float] = []
    recognizer = WhisperSTT(model)
    try:
        await recognizer.start()
        for clip in data["clips"]:
            path = manifest.parent / clip["audio"]
            with wave.open(str(path), "rb") as audio:
                if (
                    audio.getnchannels(),
                    audio.getsampwidth(),
                    audio.getframerate(),
                    audio.getcomptype(),
                ) != (1, 2, 16000, "NONE"):
                    raise ValueError("Clips must be uncompressed mono 16-bit 16 kHz WAV")
                if audio.getnframes() > 30 * 16000:
                    raise ValueError("Split benchmark clips into at most 30 seconds each")
                pcm = audio.readframes(audio.getnframes())
            started = time.perf_counter()
            text = await recognizer.transcribe(pcm)
            elapsed.append((time.perf_counter() - started) * 1000)
            scores.append(score_words(clip["reference"], text))
        total = WordErrors(sum(s.errors for s in scores), sum(s.words for s in scores))
        ordered = sorted(elapsed)
        return {
            "clips": len(scores),
            "reference_words": total.words,
            "word_errors": total.errors,
            "wer": total.wer,
            "stt_ms_median": statistics.median(elapsed),
            "stt_ms_max": ordered[-1],
        }
    finally:
        await recognizer.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(benchmark(args.model, args.manifest))
    except (ValueError, OSError, KeyError):
        parser.exit(1, "Benchmark failed. Check consent, manifest, WAV format and local models.\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
