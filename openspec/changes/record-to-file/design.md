## Context

After `strip-discord`, the app captures local audio but still transcribes live (whisper + Ollama during the call). v2 splits recording from processing. This change builds the recording half: a lightweight capture-to-disk path and the `Recording` data model. The processing half (transcription job) is a separate change that consumes the files this one writes.

## Goals / Non-Goals

**Goals:**
- Capture mic + system audio to disk with effectively no inference cost.
- Persist a `Recording` with a clear status lifecycle and file references.
- Give the user clear "is it recording?" feedback (timer + level meter) without a transcript.
- Two-track capture (mic vs system) to enable a free "You vs Others" split later.

**Non-Goals:**
- Transcription, diarization, or summaries (later changes).
- Native ScreenCaptureKit capture (that's `tauri-desktop-app`); here system audio comes from the existing virtual-device path (BlackHole / Multi-Output) via `sounddevice`.
- Renaming the project package.

## Decisions

- **Replace the live `Pipeline`/`Chunker`/whisper-queue capture path with a `Recorder`.** The recorder owns a small state machine (`idle → recording → finalizing`) and a streaming WAV writer per track. No `asyncio.Queue` of audio to whisper; no VAD chunking.
  - *Alternative*: keep the pipeline and disable inference. Rejected — the chunker/queue machinery is pure overhead for a file writer and complicates the model.
- **Persist three tracks**: `mic.wav`, `system.wav`, `mixed.wav` (16-bit PCM, capture at device rate; resampling to 16 kHz is the transcription job's concern, not the recorder's). Separate tracks are the cheapest reliable speaker prior ("mic = you").
  - *Alternative*: a single stereo file (mic L / system R). Workable, but separate files are simpler to feed to per-track diarization later. Keep mixed too for the player.
- **`Recording` replaces `Meeting`.** Fields: `id, title, created_at, started_at, ended_at, duration_s, status, language, mic_path, system_path, audio_path(mixed), error`. `Segment/Summary/QAMessage` get `recording_id`. **Clean DB reset** — drop old data; no migration code.
- **System audio source selection** reuses `app/audio/local.py` device discovery. When no system-capable device (e.g. BlackHole) is selected/available, record mic-only and set `system_path = null`; `mixed = mic`.
- **Files under `data/recordings/<id>/`**, already covered by the `/data/` gitignore rule.
- **API**: `POST /api/recordings` (start), `POST /api/recordings/{id}/stop`, `GET /api/recordings`, `GET /api/recordings/{id}`. Start returns `{id}` immediately.

## Risks / Trade-offs

- [System audio still needs BlackHole/Multi-Output until native capture exists] → Acceptable interim; documented. `tauri-desktop-app` removes it.
- [Disk growth from raw WAV] → Acceptable for local single-user; note a future `store_audio`/format (FLAC) option. Keep WAV for simplicity now.
- [Clock drift between mic and system streams over long recordings] → Capture each stream with its own timestamps; the mixed track is best-effort for playback, while transcription uses the per-track files with their own timing. Note as a known limitation for very long sessions.
- [Removing the live transcript UI is user-visible] → Intended; the value proposition shifts to higher-quality post-hoc transcripts.

## Migration Plan

Clean reset: on first v2 boot, create fresh tables. Provide a one-line note/command to delete the old `data/transcripts.db`. No rollback of data needed (greenfield local app).

## Open Questions

- Mixed-track generation: mix in real time during capture, or synthesize from mic+system at stop? (Lean: simplest correct option — write mic and system live, produce mixed at finalize if real-time mixing adds latency/complexity.)
- WAV vs FLAC on disk now? (Lean: WAV now, FLAC as a later optimization.)
