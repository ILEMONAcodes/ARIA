"""Local-only CPU adapters. All native packages are optional until voice startup.

The installer supplies model files. These adapters never fetch models, record
audio, or pass audio/text to a network provider.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import threading
from collections.abc import AsyncIterator, Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


def require_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError("A required local speech model file is missing")
    return str(path.resolve())


class SileroVAD:
    def __init__(self, model: Path, threshold: float = 0.5) -> None:
        self.model = model
        self.threshold = threshold
        self._session: Any = None
        self._pending = bytearray()
        self._speech = False

    async def start(self) -> None:
        path = require_file(self.model)
        ort = importlib.import_module("onnxruntime")
        options = ort.SessionOptions()
        options.inter_op_num_threads = options.intra_op_num_threads = 1
        self._session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
        self.reset()
        self.is_speech(bytes(1024))  # Warm the recurrent session without microphone audio.
        self.reset()

    def reset(self) -> None:
        np = importlib.import_module("numpy")
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)
        self._pending.clear()
        self._speech = False

    def is_speech(self, audio: bytes) -> bool:
        if self._session is None:
            raise RuntimeError("VAD has not started")
        np = importlib.import_module("numpy")
        self._pending.extend(audio)
        while len(self._pending) >= 1024:
            samples = np.frombuffer(bytes(self._pending[:1024]), dtype="<i2")
            del self._pending[:1024]
            signal = samples.astype(np.float32).reshape(1, -1) / 32768.0
            output, self._state = self._session.run(
                None,
                {
                    "input": np.concatenate((self._context, signal), axis=1),
                    "state": self._state,
                    "sr": np.array(16000, dtype=np.int64),
                },
            )
            self._context = signal[:, -64:]
            self._speech = float(output[0][0]) >= self.threshold
        return self._speech

    async def close(self) -> None:
        self._pending.clear()
        self._session = None


class WhisperSTT:
    def __init__(self, directory: Path, vocabulary: tuple[str, ...] = ()) -> None:
        self.directory = directory
        self.vocabulary = vocabulary
        self._model: Any = None
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aria-stt")
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        for filename in ("model.bin", "config.json", "tokenizer.json"):
            require_file(self.directory / filename)
        whisper = importlib.import_module("faster_whisper")
        self._model = await asyncio.get_running_loop().run_in_executor(
            self._worker,
            lambda: whisper.WhisperModel(
                str(self.directory.resolve()),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            ),
        )
        await self.transcribe(bytes(16000 * 2))

    def _segments(self, audio: bytes) -> Generator[str, None, None]:
        if self._model is None:
            raise RuntimeError("STT has not started")
        if len(audio) % 2 or len(audio) > 32 * 32000:
            raise ValueError("Invalid or oversized PCM utterance")
        np = importlib.import_module("numpy")
        signal = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            signal,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            hotwords=", ".join(self.vocabulary) or None,
        )
        for segment in segments:
            yield str(segment.text)

    async def stream(self, audio: bytes) -> AsyncIterator[str]:
        # Serializing native jobs prevents cancelled requests accumulating inference.
        async with self._lock:
            iterator = self._segments(audio)
            loop = asyncio.get_running_loop()
            text = ""
            try:
                while True:
                    chunk = await loop.run_in_executor(self._worker, lambda: next(iterator, None))
                    if chunk is None:
                        break
                    text += chunk
                    yield text.strip()
            finally:
                # Serialized behind any uncancellable native inference still in progress.
                await loop.run_in_executor(self._worker, iterator.close)

    async def transcribe(self, audio: bytes) -> str:
        result = ""
        async for result in self.stream(audio):
            pass
        return result

    async def close(self) -> None:
        await asyncio.to_thread(self._worker.shutdown, wait=True, cancel_futures=True)
        self._model = None


class PiperSpeaker:
    def __init__(self, model: Path) -> None:
        self.model = model
        self._voice: Any = None
        self._output: Any = None
        self._stop = threading.Event()
        self._output_lock = threading.Lock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aria-tts")

    async def start(self) -> None:
        path = require_file(self.model)
        config = require_file(Path(str(self.model) + ".json"))
        metadata = json.loads(Path(config).read_text(encoding="utf-8"))
        if metadata.get("phoneme_type") != "espeak" or not str(
            metadata.get("espeak", {}).get("voice", "")
        ).startswith("en"):
            raise ValueError("An English espeak Piper voice is required")
        piper = importlib.import_module("piper")
        self._voice = await asyncio.get_running_loop().run_in_executor(
            self._worker, lambda: piper.PiperVoice.load(path, config_path=config, use_cuda=False)
        )
        # Warm synthesis, discard PCM in RAM; never play startup speech.
        await asyncio.get_running_loop().run_in_executor(
            self._worker, lambda: list(self._voice.synthesize("Ready."))
        )

    def _speak(self, text: str, stop: threading.Event) -> None:
        sd = importlib.import_module("sounddevice")
        output: Any = None
        try:
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                if stop.is_set():
                    break
                for chunk in self._voice.synthesize(sentence):
                    if stop.is_set():
                        return
                    if output is None:
                        output = sd.RawOutputStream(
                            samplerate=chunk.sample_rate,
                            channels=chunk.sample_channels,
                            dtype="int16",
                        )
                        with self._output_lock:
                            self._output = output
                            output.start()
                    if stop.is_set():
                        return
                    output.write(chunk.audio_int16_bytes)
            if output is not None and not stop.is_set():
                output.stop()  # Drain the last sentence before declaring idle.
        finally:
            with self._output_lock:
                if self._output is output:
                    self._output = None
                if output is not None:
                    output.close()

    async def speak(self, text: str) -> None:
        if self._voice is None:
            raise RuntimeError("Speaker has not started")
        stop = threading.Event()
        self._stop = stop
        await asyncio.get_running_loop().run_in_executor(self._worker, self._speak, text, stop)

    async def stop(self) -> None:
        self._stop.set()
        with self._output_lock:
            if self._output is not None:
                self._output.abort()

    async def close(self) -> None:
        await self.stop()
        await asyncio.to_thread(self._worker.shutdown, wait=True, cancel_futures=True)
        self._voice = None
