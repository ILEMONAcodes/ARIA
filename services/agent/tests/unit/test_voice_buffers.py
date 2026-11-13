import pytest

from agent.audio.buffers import BYTES_PER_SECOND, Endpoint, RingBuffer, frame_duration_ms

FRAME = bytes(640)


def test_vad_waits_configured_silence_before_endpoint():
    endpoint = Endpoint(silence_ms=700)
    endpoint.start()
    for _ in range(10):
        assert endpoint.feed(FRAME, True) is None
    for _ in range(34):
        assert endpoint.feed(FRAME, False) is None
    assert endpoint.feed(FRAME, False) == FRAME * 45
    assert not endpoint.active


def test_vad_does_not_cut_off_slow_speaker_with_long_pause():
    endpoint = Endpoint(silence_ms=800)
    endpoint.start()
    for _ in range(10):
        endpoint.feed(FRAME, True)
    for _ in range(35):
        assert endpoint.feed(FRAME, False) is None
    assert endpoint.feed(FRAME, True) is None
    assert endpoint.silent_ms == 0


def test_wake_ring_buffer_keeps_one_second_preroll():
    ring = RingBuffer()
    for value in range(60):
        ring.append(bytes([value]) * 640)
    assert len(ring.snapshot()) == BYTES_PER_SECOND
    assert ring.snapshot()[:640] == bytes([10]) * 640
    ring.clear()
    assert ring.snapshot() == b""


def test_no_audio_stored_or_emitted_before_wake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    endpoint = Endpoint()
    for _ in range(100):
        assert endpoint.feed(FRAME, True) is None
    assert endpoint.finish() == b""
    assert list(tmp_path.iterdir()) == []


def test_endpoint_discards_silence_and_clears_audio_on_cancel():
    endpoint = Endpoint()
    endpoint.start()
    endpoint.feed(FRAME, False)
    assert endpoint.finish() == b""
    endpoint.start()
    for _ in range(10):
        endpoint.feed(FRAME, True)
    endpoint.clear()
    assert endpoint.finish() == b""


def test_endpoint_bounds_utterance_memory_and_does_not_clip_preroll():
    endpoint = Endpoint(max_ms=1000)
    prefix = bytes([1]) * BYTES_PER_SECOND
    endpoint.start(prefix)
    for _ in range(49):
        assert endpoint.feed(FRAME, True) is None
    assert endpoint.feed(FRAME, True) == prefix + FRAME * 50


@pytest.mark.parametrize("size", [0, 1, 320, 1024])
def test_invalid_capture_frame_sizes_are_rejected(size):
    with pytest.raises(ValueError):
        frame_duration_ms(bytes(size))
