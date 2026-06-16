## 1. Data model (clean reset)

- [x] 1.1 Add a `Recording` SQLModel (`id, title, created_at, started_at, ended_at, duration_s, status, language, mic_path, system_path, audio_path, error`) and remove the `Meeting` model.
- [x] 1.2 Repoint `Segment`, `Summary`, `QAMessage` foreign keys to `recording_id`.
- [x] 1.3 Update `app/db.py` to create the v2 schema fresh; remove `Meeting`-era seed/migration assumptions. Document deleting `data/transcripts.db` for the reset.

## 2. Audio capture — two tracks

- [x] 2.1 Extend `app/audio/local.py` to open a microphone stream and (when a system-capable device is selected) a system-audio stream concurrently.
- [x] 2.2 Implement streaming 16-bit PCM WAV writers for `mic.wav` and `system.wav` under `data/recordings/<id>/`.
- [x] 2.3 Produce a `mixed.wav` (real-time or synthesized at finalize per design open question).
- [x] 2.4 Handle the mic-only case: `system_path = null`, `mixed = mic`.

## 3. Recorder state machine

- [x] 3.1 Create `app/recording/recorder.py` with an `idle → recording → finalizing` state machine that owns the streams and writers.
- [x] 3.2 `start()` creates the `Recording` row (status `recording`), opens devices/writers, returns the id immediately (no model load).
- [x] 3.3 `stop()` closes writers, computes `duration_s`, sets status `processing`, stores paths and ended timestamp.
- [x] 3.4 Remove the live capture path (`app/pipeline.py` capture portions; `app/bot/chunker.py` is already gone after strip-discord). Keep Ollama/whisper modules for later changes but do not invoke them during recording.

## 4. API

- [x] 4.1 Replace `/api/meetings*` with `/api/recordings`: `POST /` (start, body: device, system_device?, label?, title?), `POST /{id}/stop`, `GET /`, `GET /{id}`.
- [x] 4.2 Return `{ id }` from start without blocking; ensure stop is idempotent.
- [x] 4.3 Update `GET /` and `GET /{id}` response models to include status and file references.

## 5. Frontend — record UI

- [x] 5.1 Replace the live-meeting screen with a recording screen: large Record/Stop control, elapsed timer, and an input-level meter; no transcript.
- [x] 5.2 Drive the level meter from the input stream (e.g. periodic RMS over a `/ws` or polled endpoint, or client-side if capture is server-side — choose simplest; document).
- [x] 5.3 Update the dashboard recordings list to show status badges (`recording`, `processing`, `ready`, `failed`).
- [x] 5.4 Update `api.ts` to the `/api/recordings` shape; run `tsc --noEmit` and `npm run build`.

## 6. Verification

- [x] 6.1 Start a recording; confirm `Recording` row is `recording` and audio files appear under `data/recordings/<id>/`.
- [x] 6.2 Speak for ~20s; confirm no whisper/Ollama activity in logs and low CPU.
- [x] 6.3 Stop; confirm files are closed/readable, `duration_s` set, status `processing`.
- [x] 6.4 Confirm the recording screen showed a timer + level meter and no transcript.
- [x] 6.5 Confirm a fresh `data/` initializes cleanly with the new schema.
