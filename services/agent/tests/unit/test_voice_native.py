"""Test native boundary calls with stub engines, never actual models/devices."""

import asyncio
import importlib
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from agent.audio.capture import Microphone
from agent.audio.native import PiperSpeaker, SileroVAD, WhisperSTT
from agent.audio.wake import HeyAria


def install_modules(monkeypatch, **modules):
    original = importlib.import_module

    def load(name, package=None):
        return modules[name] if name in modules else original(name, package)

    monkeypatch.setattr(importlib, "import_module", load)


def test_microphone_is_idle_until_activated_and_discards_stale_callbacks(monkeypatch):
    streams = []

    class Input:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            streams.append(self)

        def start(self):
            pass

        def abort(self):
            pass

        def close(self):
            self.closed = True

    install_modules(monkeypatch, sounddevice=SimpleNamespace(RawInputStream=Input))

    async def scenario():
        mic = Microphone(device=2)
        await mic.start()
        assert streams == []
        await mic.resume()
        assert streams[0].kwargs["samplerate"] == 16000
        assert streams[0].kwargs["blocksize"] == 320
        assert streams[0].kwargs["device"] == 2
        streams[0].kwargs["callback"](bytes(640), 320, None, False)
        await asyncio.sleep(0)
        assert await mic.read() == bytes(640)
        old_callback = streams[0].kwargs["callback"]
        await mic.pause()
        await mic.resume()
        old_callback(bytes([1]) * 640, 320, None, False)
        streams[1].kwargs["callback"](bytes([2]) * 640, 320, None, False)
        await asyncio.sleep(0)
        assert await mic.read() == bytes([2]) * 640
        await mic.close()
        assert all(s.closed for s in streams)

    asyncio.run(scenario())


def test_microphone_overflow_fails_instead_of_transcribing_truncated_audio(monkeypatch):
    callbacks = []

    def stream(**kwargs):
        callbacks.append(kwargs["callback"])
        return SimpleNamespace(start=lambda: None, abort=lambda: None, close=lambda: None)

    install_modules(monkeypatch, sounddevice=SimpleNamespace(RawInputStream=stream))

    async def scenario():
        mic = Microphone()
        await mic.start()
        await mic.resume()
        for _ in range(51):
            callbacks[0](bytes(640), 320, None, False)
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="overrun"):
            await mic.read()
        await mic.close()

    asyncio.run(scenario())


def test_silero_reblocks_frames_and_resets_recurrent_state(tmp_path, monkeypatch):
    path = tmp_path / "vad.onnx"
    path.touch()
    calls = []

    class Session:
        def __init__(self, path, options, *, providers):
            assert providers == ["CPUExecutionProvider"]

        def run(self, outputs, inputs):
            calls.append(inputs)
            return np.array([[0.9]], dtype=np.float32), np.ones((2, 1, 128), dtype=np.float32)

    install_modules(
        monkeypatch,
        onnxruntime=SimpleNamespace(
            SessionOptions=SimpleNamespace,
            InferenceSession=Session,
        ),
    )

    async def scenario():
        vad = SileroVAD(path)
        await vad.start()
        calls.clear()
        assert not vad.is_speech(bytes(640))
        assert vad.is_speech(bytes(640))
        assert calls[0]["input"].shape == (1, 576)
        assert calls[0]["state"].shape == (2, 1, 128)
        assert int(calls[0]["sr"]) == 16000
        vad.reset()
        assert not vad.is_speech(bytes(640))
        await vad.close()

    asyncio.run(scenario())


def test_stt_runs_with_sockets_blocked_and_uses_only_local_assets(tmp_path, monkeypatch):
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).touch()
    configuration, requests, threads = [], [], []

    class Model:
        def __init__(self, path, **kwargs):
            configuration.append(kwargs)

        def transcribe(self, audio, **kwargs):
            requests.append(kwargs)
            threads.append(threading.get_ident())
            assert audio.dtype == np.float32
            return iter([SimpleNamespace(text=" Open"), SimpleNamespace(text=" the folder.")]), None

    install_modules(monkeypatch, faster_whisper=SimpleNamespace(WhisperModel=Model))

    async def scenario():
        recognizer = WhisperSTT(tmp_path, vocabulary=("Bello", "circular"))
        await recognizer.start()
        partials = [text async for text in recognizer.stream(bytes(3200))]
        assert partials == ["Open", "Open the folder."]
        assert await recognizer.transcribe(bytes(3200)) == "Open the folder."
        assert configuration == [
            {"device": "cpu", "compute_type": "int8", "local_files_only": True}
        ]
        assert requests[-1]["hotwords"] == "Bello, circular"
        assert requests[-1]["language"] == "en"
        assert all(t != threading.get_ident() for t in threads)
        await recognizer.close()

    asyncio.run(scenario())


def test_missing_speech_assets_fail_before_importing_any_engine(tmp_path, monkeypatch):
    def forbidden(name, package=None):
        raise AssertionError("Missing assets must be checked before importing an engine")

    monkeypatch.setattr(importlib, "import_module", forbidden)

    async def scenario():
        for component in (
            SileroVAD(tmp_path / "absent"),
            WhisperSTT(tmp_path),
            PiperSpeaker(tmp_path / "absent"),
            HeyAria(tmp_path),
        ):
            try:
                with pytest.raises(ValueError, match="missing"):
                    await component.start()
            finally:
                await component.close()

    asyncio.run(scenario())


def test_piper_speaks_sentence_chunks_and_stops_without_writing_files(tmp_path, monkeypatch):
    model = tmp_path / "voice.onnx"
    model.touch()
    (tmp_path / "voice.onnx.json").write_text(
        '{"phoneme_type":"espeak","espeak":{"voice":"en_US"}}'
    )
    sentences, writes, streams = [], [], []
    waiting, release = threading.Event(), threading.Event()

    class Voice:
        @staticmethod
        def load(path, **kwargs):
            assert kwargs == {"config_path": str(model) + ".json", "use_cuda": False}
            return Voice()

        def synthesize(self, text):
            sentences.append(text)
            if text == "Second sentence.":
                waiting.set()
                assert release.wait(2)
            yield SimpleNamespace(
                sample_rate=22050, sample_channels=1, audio_int16_bytes=bytes(400)
            )

    class Output:
        def __init__(self, **kwargs):
            self.aborted = False
            streams.append(self)

        def start(self):
            pass

        def write(self, pcm):
            writes.append(pcm)

        def stop(self):
            pass

        def abort(self):
            self.aborted = True

        def close(self):
            pass

    install_modules(
        monkeypatch,
        piper=SimpleNamespace(PiperVoice=Voice),
        sounddevice=SimpleNamespace(RawOutputStream=Output),
    )

    async def scenario():
        speaker = PiperSpeaker(model)
        await speaker.start()
        assert writes == []  # Warmup is silent.
        task = asyncio.create_task(speaker.speak("First sentence. Second sentence."))
        assert await asyncio.to_thread(waiting.wait, 2)
        await speaker.stop()
        release.set()
        await task
        assert len(writes) == 1
        assert streams[0].aborted
        assert sentences == ["Ready.", "First sentence.", "Second sentence."]
        await speaker.close()

    asyncio.run(scenario())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["voice.onnx", "voice.onnx.json"]


def test_wake_adapter_requires_custom_models_and_reblocks_80ms(tmp_path, monkeypatch):
    for name in ("hey_aria.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        (tmp_path / name).touch()
    frames = []

    class Model:
        def __init__(self, **kwargs):
            assert kwargs["wakeword_models"] == [str(tmp_path / "hey_aria.onnx")]
            assert kwargs["inference_framework"] == "onnx"
            assert kwargs["melspec_model_path"] == str(tmp_path / "melspectrogram.onnx")

        def predict(self, frame):
            frames.append(frame)
            return {"hey_aria": 0.9}

        def reset(self):
            pass

    install_modules(monkeypatch, **{"openwakeword.model": SimpleNamespace(Model=Model)})

    async def scenario():
        wake = HeyAria(tmp_path)
        await wake.start()
        frames.clear()
        for _ in range(3):
            assert not wake.detected(bytes(640))
        assert wake.detected(bytes(640))
        assert len(frames) == 1
        assert frames[0].shape == (1280,)
        await wake.close()

    asyncio.run(scenario())
