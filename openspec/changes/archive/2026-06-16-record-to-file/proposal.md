## Why

The current app transcribes live, in 5–8s chunks, which pins CPU during the meeting (whisper + Ollama competing) and produces lower-quality transcripts. The v2 direction (see [docs/V2-LOCAL-REDESIGN.md](../../../docs/V2-LOCAL-REDESIGN.md)) is "record now, process after": recording should be near-zero CPU and just write audio to disk, so the call stays smooth and the heavy work happens once, afterward, at higher quality. This change establishes the recording half of that split.

## What Changes

- **BREAKING**: Replace the live transcription pipeline with a **recorder** that writes captured audio to disk and runs **no** inference (no whisper, no Ollama, no live chunker) during a recording.
- Capture **two tracks** where available — microphone (you) and system audio (everyone else) — and persist them, plus a mixed track for playback. Separate tracks give a free first-order speaker split downstream.
- **BREAKING**: Replace the `Meeting` data model with a `Recording` model carrying the recording lifecycle (`recording → processing → ready → failed`), file paths, duration, and language. Start v2 from a **clean database** (no migration of v1 data — decided).
- Recording lifecycle API: start → returns immediately; stop → finalizes files, sets status `processing`, and hands off (the processing job itself is a later change).
- UI: a prominent **Record** control with a live elapsed timer and input-level meter while recording — **no transcript shown during recording**. Recordings list shows status badges.
- Audio files live under a gitignored `data/recordings/<id>/` directory.

## Capabilities

### New Capabilities
- `audio-recording`: capture mic + system audio to disk with no inference; start/stop lifecycle; live elapsed time and level metering.
- `recording-store`: the `Recording` data model and on-disk audio layout, including status lifecycle and file references.

### Modified Capabilities
<!-- None archived yet. The start/stop behavior change (persist a Recording with audio files instead of streaming live segments) is captured within the new `audio-recording` capability rather than as a delta against the not-yet-archived `local-only-runtime`. -->


## Impact

- **Data model**: new `Recording` table (replaces `Meeting`); `Segment`/`Summary`/`QAMessage` repoint to `recording_id` (segments populated by the later transcription change). Clean `data/` reset.
- **Backend**: new `app/recording/` (recorder + writer + state machine) replacing the live `Pipeline`/`Chunker`/whisper-queue for the capture path; `app/audio/local.py` extended to expose mic + system streams; new `/api/recordings` start/stop/list/get.
- **Frontend**: Dashboard gains Record button + timer + level meter; recordings list with status badges; live transcript view removed from the recording screen.
- **Disk**: `data/recordings/` (gitignored) holds `mic.wav`, `system.wav`, `mixed.wav` per recording.
- **Depends on**: `strip-discord` (local-only base).
