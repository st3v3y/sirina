## Why

A one-hour call currently takes anywhere from ~25 minutes to 3+ hours to transcribe on the target Mac (M1 Pro, 16 GB). A benchmark on 2026-10-06 (10-minute dense clip, `large-v3`) traced this to three things: the engine uses all 8 cores including the 2 slow efficiency cores (1.6x slower than using the 6 performance cores, with identical text); processing runs on battery in Low Power Mode and the Mac may idle-sleep because the sleep guard is released when recording stops; and the CPU engine peaks at ~8.5 GB of RAM, which pushes a busy 16 GB Mac into heavy swap. The user also gets nothing to read until the whole pipeline finishes. The same benchmark showed better options on this hardware: WhisperKit with the `large-v3-turbo` model (626 MB, compressed) transcribes the clip in 59 s instead of 193 s at 0.4 GB RAM with an estimated ~1.6% real word errors, and macOS's on-device SpeechTranscriber produces live captions within ~1 s using ~2.5% of one CPU core.

## What Changes

- **Quick wins (no quality change):** the CPU engine defaults to one thread per performance core; the idle-sleep guard is held until post-recording processing finishes, not just until recording stops; when processing on battery or in Low Power Mode the app tells the user why it is slower.
- **New default macOS engine:** a native WhisperKit engine (bundled Swift helper, MIT) running `large-v3-turbo` (626 MB) replaces faster-whisper as the default on Apple Silicon. faster-whisper stays as the fallback (non-Apple, or helper unavailable). MLX stays out of the bundle and is no longer part of automatic selection. **BREAKING** (default transcripts come from a different model; existing transcripts are untouched; re-processing an old recording uses the new engine).
- **Speaker splitting moves to SpeakerKit:** the same helper runs Argmax's SpeakerKit instead of pyannote. On a 2h14 recording it took 52 s instead of 575 s, used half the memory, and agreed with pyannote on ~94% of speech time. pyannote/torch leave the app and no Hugging Face token is needed. A setting chooses whether speakers are also split during the recording (default: once after stop). **BREAKING:** stored pyannote voice fingerprints are cleared; known People are re-learned from the next renames.
- **Model manager:** a Settings section lists speech models with size and status, and downloads or deletes them on demand. Models are never bundled in the app.
- **Optional live captions:** while recording, on-device captions for both tracks (You / Others) are shown on the recording screen when enabled (macOS 26+). Off by default. **BREAKING** for the "no inference during recording" and "no live transcript" requirements, which become opt-in exceptions.
- **Transcribe during recording (opt-in, per recording):** with WhisperKit (0.4 GB RAM, mostly Neural Engine) the final windows can be committed while the call is still running, so after stop only the last few minutes, diarization, and the summary remain. Default comes from Settings; it can be changed per recording in the start dialog and on the recording screen. The CPU fallback never runs during a recording.
- **Instant draft, progressive final:** when a recording stops, a draft transcript is available immediately (from live captions, or a fast on-device pass of about a minute per hour of audio). The final engine then works through the recording in short time windows, both tracks per window, and replaces the draft window by window. The UI shows final text normally and the remaining draft greyed with a "draft" marker; the boundary moves down as processing proceeds.

## Capabilities

### New Capabilities
- `speech-models`: listing, downloading, and deleting on-demand speech models (final engine and draft/caption assets), with sizes and status, from Settings.
- `live-captions`: optional on-device captions for both tracks during recording, their latency and resource bounds, and how they are stored as a draft transcript.
- `live-transcription`: opt-in, per-recording finalization of windows during the recording with WhisperKit, including trim reconciliation and what remains after stop.
- `progressive-transcript`: the draft transcript available at stop and its window-by-window replacement by the final transcript, including the draft/final boundary shown to the user.

### Modified Capabilities
- `transcription-job`: engine selection changes (WhisperKit default on Apple Silicon, faster-whisper fallback, MLX dropped from auto selection); the job transcribes in time windows across both tracks and finalizes per window instead of whole file then write; CPU engine thread default; sleep guard held through processing.
- `audio-recording`: "no inference during recording" and "no live transcript" gain opt-in exceptions for live captions and transcription during recording.
- `device-selection-modal`: the start dialog gains per-recording toggles for live captions and transcription during recording.
- `speaker-diarization`: SpeakerKit replaces pyannote (no token), a setting for splitting during the recording, and voice fingerprints re-learned after the switch.
- `transcript-view`: draft vs final rendering, the moving boundary, and editing locked in the draft region.
- `processing-progress`: progress exposes how far the final transcript has reached (`final_until_s`) and a power-state note (battery / Low Power Mode).
- `app-settings`: new settings (live captions toggle, final engine/model choice) and the model manager section on the Settings page.

## Impact

- **New native helper** `native/speech-engine/` (Swift package depending on WhisperKit; uses the Speech framework for captions/draft). Built by a new build step and bundled as a Tauri resource next to `system-audio-capture`. App size grows by a few MB; models download into the existing data dir (`models/`).
- **Backend:** `app/transcribe/` (new WhisperKit engine client, selection in `engine.py`, thread default in `whisper.py`), `app/processing/job.py` (windowed two-track finalization, draft pass, sleep guard), `app/recording/recorder.py` (tee PCM frames to the caption helper; sleep guard handoff), `app/audio/power.py` (battery / Low Power Mode detection), `app/models.py` + `app/db.py` (draft flag on `Segment`, per-recording options on `Recording`, additive migrations), `app/settings_store.py`, new model-manager API.
- **Frontend:** start dialog and `RecordingScreen.tsx` (per-recording toggles, captions), `RecordingDetail.tsx` (draft styling, boundary, editing lock), Settings page (model manager, captions toggle), progress banner (power note).
- **Packaging:** `scripts/build-macos-app.sh` builds and signs the new helper; faster-whisper stays in the bundle as the fallback.
- **Related open work:** `production-hardening` tasks 4.2–4.5 planned an ONNX replacement for pyannote/torch and an on-demand diarization model; this change supersedes them with SpeakerKit (its model goes through the model manager). `harden-system-audio-capture` added the recording-time sleep assertion that this change extends through processing.
- **Out of scope:** transcribing during the recording with the CPU engine (at background priority it was >8x slower in the benchmark).
