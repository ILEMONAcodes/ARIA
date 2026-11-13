"""Optional custom HeyAria detector; every model must already exist locally."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from agent.audio.native import require_file


class HeyAria:
    def __init__(self, directory: Path, threshold: float = 0.5) -> None:
        self.directory = directory
        self.threshold = threshold
        self._model: Any = None
        self._pending = bytearray()

    async def start(self) -> None:
        model = require_file(self.directory / "hey_aria.onnx")
        mel = require_file(self.directory / "melspectrogram.onnx")
        embedding = require_file(self.directory / "embedding_model.onnx")
        module = importlib.import_module("openwakeword.model")
        self._model = module.Model(
            wakeword_models=[model],
            inference_framework="onnx",
            melspec_model_path=mel,
            embedding_model_path=embedding,
        )
        self.detected(bytes(2560))
        self.reset()

    def reset(self) -> None:
        self._pending.clear()
        if self._model is not None:
            self._model.reset()

    def detected(self, audio: bytes) -> bool:
        if self._model is None:
            raise RuntimeError("Wake detector has not started")
        np = importlib.import_module("numpy")
        self._pending.extend(audio)
        match = False
        while len(self._pending) >= 2560:
            frame = bytes(self._pending[:2560])
            del self._pending[:2560]
            scores = self._model.predict(np.frombuffer(frame, dtype="<i2"))
            match = match or float(scores.get("hey_aria", 0)) >= self.threshold
        return match

    async def close(self) -> None:
        self._pending.clear()
        self._model = None
