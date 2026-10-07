# speech-engine

Sirina's on-device speech helper (Swift). One binary covers:

- **Final transcription** — WhisperKit (Argmax OSS, MIT), model `openai_whisper-large-v3-v20240930_626MB` (large-v3-turbo, compressed for the Neural Engine).
- **Speaker splitting** — SpeakerKit (same package), with one centroid embedding per speaker for voice matching.
- **Draft transcript and live captions** — Apple `SpeechTranscriber` (macOS 26+, on-device).

Models are never bundled: the backend downloads them into the app's model cache and passes their folders in. Audio and text never leave the Mac.

## Modes

| Command | Behavior |
| --- | --- |
| `speech-engine --probe` | One JSON line with capabilities (`whisperkit`, `speakerkit`, `apple_speech`, `apple_speech_asset_installed`, `macos`). Exit 0. |
| `speech-engine serve` | Long-running. One JSON request per stdin line, one JSON response per stdout line, handled one at a time. |
| `speech-engine captions [--sample-rate 48000] [--language en] [--prompt "a, b"]` | Reads raw 48 kHz mono s16le PCM on stdin until EOF; writes `{"kind":"provisional"\|"settled","start","end","text"}` lines. Exit 3 if unsupported. |

### `serve` requests

| `cmd` | Fields | Response |
| --- | --- | --- |
| `load_whisper` | `model_dir` | `{}` (first load prepares the model for the Neural Engine: minutes, once) |
| `transcribe` | `path`, `start_s`, `end_s?`, `language?`, `prompt?` | `segments: [{start,end,text,words:[[s,e,w]…]}]`, `language`, `audio_s` — times are absolute (recording time), clamped into the window, sorted |
| `draft` | `path`, `start_s?`, `end_s?`, `language?`, `prompt?` | `segments: [{start,end,text}]` (settled only) |
| `install_speech_asset` | `language?` | `{}` once macOS has the language asset |
| `load_diarizer` | `model_dir` (SpeakerKit snapshot) | `{}` |
| `diarize` | `path`, `end_s?` | `turns: [{start,end,speaker}]`, `embeddings: {speaker: [float]}` |
| `status` | — | capabilities + `low_power` |

Every response carries the request `id` and `ok`; failures are `{"ok":false,"error":…}` and never end the loop. Library output that goes to stdout is redirected to stderr so it can't corrupt the protocol.

## Build

```bash
./build.sh          # -> build/speech-engine, then runs smoke-test.sh (SKIP_SMOKE=1 to skip)
```

Requires Xcode/Swift, macOS 14+ to run (WhisperKit pinned to argmax-oss-swift 1.1.0 in `Package.swift`; bump deliberately and rerun the transcription validation). `smoke-test.sh` synthesizes a fixture with `say`; model checks run only when the models are in the app's cache.

## Known quirk

WhisperKit can place the cut-off last phrase of a single ≤30 s window past the end of the audio. The helper clamps all times into the requested window; the backend's windows are ~3 minutes, where this does not happen.
