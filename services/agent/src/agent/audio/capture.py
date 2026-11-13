"""PortAudio capture. Idle preparation never opens the microphone."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any


class Microphone:
    def __init__(self, device: int | None = None) -> None:
        self.device = device
        self._stream: Any = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=50)
        self._generation = 0
        self._overflow = False

    async def start(self) -> None:
        # Import is explicit; missing optional dependencies never select a fake.
        importlib.import_module("sounddevice")

    async def resume(self) -> None:
        if self._stream is not None:
            return
        self._generation += 1
        generation = self._generation
        while not self._queue.empty():
            self._queue.get_nowait()
        loop = asyncio.get_running_loop()
        self._overflow = False

        def enqueue(frame: bytes, failed: bool) -> None:
            if generation != self._generation:
                return
            if failed or self._queue.full():
                self._overflow = True
                return
            self._queue.put_nowait(frame)

        def callback(data: Any, frames: int, timing: Any, status: Any) -> None:
            loop.call_soon_threadsafe(enqueue, bytes(data), bool(status))

        sd = importlib.import_module("sounddevice")
        self._stream = sd.RawInputStream(
            samplerate=16000,
            blocksize=320,
            channels=1,
            dtype="int16",
            device=self.device,
            callback=callback,
        )
        try:
            self._stream.start()
        except BaseException:
            await self.pause()
            raise

    async def read(self) -> bytes | None:
        frame = await self._queue.get()
        if self._overflow:
            raise RuntimeError("Microphone overrun; retry the utterance")
        return frame

    async def pause(self) -> None:
        self._generation += 1
        stream, self._stream = self._stream, None
        try:
            if stream is not None:
                stream.abort()
                stream.close()
        finally:
            while not self._queue.empty():
                self._queue.get_nowait()
            self._queue.put_nowait(None)

    async def close(self) -> None:
        await self.pause()
