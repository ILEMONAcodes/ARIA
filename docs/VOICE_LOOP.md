# Phase B offline voice pipeline

Backend implementation for VOX-1–4 and SYSX-1. It repeats the recognized words
out loud. Saying “Open the policy folder” produces a caption and spoken echo;
it does not open anything. There is no planner, gateway, speaker identification,
database access or action execution in this mode.

## Files and flow

The implementation is in `services/agent/src/agent/audio`:

- `capture.py`: sounddevice capture, 16 kHz mono int16, 20 ms frames, device selection.
- `buffers.py`: one-second volatile wake pre-roll, 500–800 ms silence setting,
  100 ms minimum speech, 30-second utterance limit.
- `native.py`: Silero ONNX VAD, CPU int8 faster-whisper, English espeak Piper.
- `wake.py`: optional custom openWakeWord HeyAria ONNX adapter.
- `pipeline.py`: push-to-talk/wake activation, partial/final captions, spoken
  echo, stop/cancel and cleanup. No audio file writes.
- `metrics.py`: corpus word error rate (WER), normalized for case/punctuation.

`services/agent/src/agent/voice/server.py` serves authenticated health and
WebSocket endpoints. Its lifespan loads and warms the models once before
accepting requests; one authenticated connection owns the microphone at a
time. Disconnect stops capture and speech. Native inference runs in serial
workers; cancellation suppresses stale output but cannot forcibly terminate
an in-progress native inference call. Shutdown waits for that work to finish.

The foundation `python -m agent` CLI remains separate. Echo mode deliberately
does not create profile/history records before identity/profile work exists.
It emits a content-free `activity.entry` after successful playback; this is
session activity, not durable per-user history.

## Run on Windows

From the repository root, with Python 3.11 and uv 0.13.7:

```sh
uv sync --locked --all-packages --all-extras --group voice
uv run --locked --all-packages --all-extras --group voice python -m agent.voice --models models
```

The `voice` dependency group installs native packages on Windows only. Default
backend checks on macOS/Linux use stub engines, not a supported native voice
installation. The extra Windows CI job checks native imports without opening
a device or downloading models.

Supply these already-installed assets (not included in this repository):

```text
models/
  silero_vad.onnx          Silero 16 kHz recurrent ONNX model
  whisper/
    model.bin             faster-whisper tiny.en or base.en CTranslate2 model
    config.json
    tokenizer.json
    ...                   remaining files from the same model distribution
  piper/
    voice.onnx            English Piper voice
    voice.onnx.json       matching config: phoneme_type espeak, English voice
```

Use the matching assets from each upstream model distribution. The installer
and checksum manifest are Phase I work; keep local models outside git. Missing
assets fail before microphone access. No model is downloaded at runtime and
failure never selects a fake engine. The current Piper runtime is GPL; record
runtime and individual voice licenses with the eventual installer assets.

`--mic-device 2` selects a PortAudio input index. `--settings config/agent.toml`
uses the existing `vad_silence_ms` and active profile. Repeat
`--vocabulary Bello --vocabulary circular` for explicitly supplied office terms;
this biases recognition and does not guarantee correct names.

Set `ARIA_SESSION_TOKEN` in the launching shell or use the development session
credential printed by the CLI. Requests and access URLs are not logged. Bind
is always `127.0.0.1`; use `--port` if needed. For a browser/Tauri frontend,
pass its exact Origin with `--allow-origin`; no browser origins are allowed by
default. The launcher-to-sidecar credential handoff remains packaging work.

## UI handoff (v1 unchanged)

Connect to the printed `/ws?token=...` URL; health uses
`GET /api/health` with `Authorization: Bearer ...`.

1. Send `{"v":1,"type":"ptt.start"}` when the hotkey/mic button is pressed.
2. Send `{"v":1,"type":"ptt.stop"}` when released; silence also endpoints speech.
3. Render `status`, cumulative `transcript.partial`, `transcript.final`,
   `reply.text`, `activity.entry` and `error` events using the generated types.
4. Send `{"v":1,"type":"tts.stop"}` for the global Stop/Cancel control, including
   during capture or transcription. `task.cancel` also accepts the current
   reply's `task_id`; unrelated IDs do not cancel it.

Capture is off while idle in default PTT mode. During spoken playback the mic
is active for stop/cancel recognition and status is `listening`. Other speech
during playback is ignored. A headset is recommended for the hardware test;
acoustic echo cancellation is not implemented. Partials arrive as Whisper
segments after endpointing, not as continuous transcription while holding PTT.
All status events report `online:false` because this mode uses no network
provider; it does not probe internet connectivity.

The frontend owns the actual hotkey, mic indicator, mute/Stop button and caption
UI. `voice_echo.json` provides the same event flow through the mock:

```sh
uv run --locked --all-packages --all-extras python -m agent.mock --scenario voice_echo
```

## Optional wake word

Default is PTT only. Enable `--wake` only with the trained custom assets:
`wake/hey_aria.onnx`, `wake/melspectrogram.onnx`, `wake/embedding_model.onnx`.
These must be compatible openWakeWord ONNX models. No generic wake phrase is
substituted. Enabling wake keeps the microphone active and status `listening`;
pre-wake PCM is limited to a one-second RAM ring and never transcribed or saved.
The user has no trained model yet, so actual HeyAria behavior is unverified.

## Accuracy and release gate

With written consent, collect 100–200 Nigerian-English sentences as mono 16-bit
16 kHz WAV files outside the repo. Put a manifest next to them:

```json
{
  "consented": true,
  "clips": [{"audio": "sentence-001.wav", "reference": "Open the policy folder."}]
}
```

```sh
uv run --locked --all-packages --all-extras --group voice python scripts/bench_voice.py --model models/whisper --manifest /path/to/manifest.json
```

The report contains clip/word/error counts, corpus WER and post-warmup STT
median/max milliseconds, without audio or transcript text. This measures STT
inference only; measure endpoint-to-final latency separately on the real UI.
No recordings were supplied, so no accuracy or latency result is claimed.

Phase B stays open until a Windows PC completes a spoken echo with its network
disabled, endpoint-to-transcript is under 1.5 s, TTS starts under 500 ms, WER is
under 15%, HeyAria has fewer than one false accept/hour, and the real/mock UI
controls and non-technical user smoke test pass. Model packaging, checksums
and the 90-second cold-start gate remain Phase I work.

Adapter references: [sounddevice raw streams](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html),
[Silero ONNX wrapper](https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md),
[openWakeWord](https://github.com/dscripka/openWakeWord).
