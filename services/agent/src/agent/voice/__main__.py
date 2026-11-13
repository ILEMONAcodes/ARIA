"""Start the local Phase B spoken echo; no actions or cloud calls are enabled."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

import uvicorn

from agent.audio.capture import Microphone
from agent.audio.native import PiperSpeaker, SileroVAD, WhisperSTT, require_file
from agent.audio.wake import HeyAria
from agent.config import load_settings
from agent.voice.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--mic-device", type=int)
    parser.add_argument("--wake", action="store_true", help="Enable supplied custom HeyAria model")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--vocabulary", action="append", default=[], help="Explicit office term")
    args = parser.parse_args()
    try:
        settings = load_settings(args.settings)
        # Validate the entire asset set before any native model is loaded or mic opened.
        files = [
            "silero_vad.onnx",
            "whisper/model.bin",
            "whisper/config.json",
            "whisper/tokenizer.json",
            "piper/voice.onnx",
            "piper/voice.onnx.json",
        ]
        if args.wake:
            files += ["wake/hey_aria.onnx", "wake/melspectrogram.onnx", "wake/embedding_model.onnx"]
        for filename in files:
            require_file(args.models / filename)
        token = os.environ.get("ARIA_SESSION_TOKEN") or secrets.token_urlsafe(32)
        app = create_app(
            token=token,
            audio=Microphone(args.mic_device),
            vad=SileroVAD(args.models / "silero_vad.onnx"),
            stt=WhisperSTT(args.models / "whisper", tuple(args.vocabulary)),
            speaker=PiperSpeaker(args.models / "piper/voice.onnx"),
            wake=HeyAria(args.models / "wake") if args.wake else None,
            silence_ms=settings.vad_silence_ms,
            profile=settings.profile,
            allowed_origins=tuple(args.allow_origin),
        )
    except (ValueError, OSError):
        parser.exit(
            1, "Voice startup failed. Check settings and the installed local speech models.\n"
        )
    print("ARIA voice echo only. Audio stays in memory; commands are echoed, never executed.")
    # Session credential is intentionally shown only to the local development launcher.
    print(f"Local session: ws://127.0.0.1:{args.port}/ws?token={token}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="critical")


if __name__ == "__main__":
    main()
