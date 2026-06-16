## 1. Whisper worker — offline file transcription

- [x] 1.1 Add `transcribe_file(path) -> (segments, language)` to `app/transcribe/whisper.py`, returning a list of `(start, end, text)` plus the detected/forced language.
- [x] 1.2 Use `BatchedInferencePipeline` with `vad_filter=True`, `beam_size=5`, `word_timestamps=True`, honoring `WHISPER_LANGUAGE` and `WHISPER_INITIAL_PROMPT`; fall back to sequential `model.transcribe` if the batched pipeline is unavailable.
- [x] 1.3 Run inference inside the existing thread executor + lock so the event loop isn't blocked.

## 2. Processing job

- [x] 2.1 Create `app/processing/job.py` with a `TranscriptionProcessor` (asyncio.Queue + one worker task).
- [x] 2.2 `enqueue(recording_id)` and a `_run()` loop that processes one recording at a time.
- [x] 2.3 `_process(recording_id)`: load the recording, clear any existing segments, transcribe `audio_path`, write `Segment` rows (placeholder `speaker_label="Speaker 1"`), store `language`, set status `ready`. On error set status `failed` + `error`.
- [x] 2.4 `requeue_pending()`: on startup, enqueue all recordings whose status is `processing`.

## 3. Wiring

- [x] 3.1 In `app/runtime.py`, add a `processor` handle.
- [x] 3.2 In `app/main.py` lifespan, create the `TranscriptionProcessor`, start its worker task, and call `requeue_pending()` after `init_db()`/whisper load is kicked off; cancel the task on shutdown.
- [x] 3.3 In the `/api/recordings/{id}/stop` endpoint, enqueue the recording for processing after `recorder.stop()`.

## 4. Config

- [x] 4.1 Keep `WHISPER_MODEL=medium` as the default; document bumping to `large-v3-turbo` for best offline quality in `.env.example` / README.

## 5. Frontend — processing → ready

- [x] 5.1 In `RecordingDetail`, poll `GET /api/recordings/{id}` while status is `processing`; stop polling and render the transcript once `ready` (or show a failure note on `failed`).
- [x] 5.2 Run `tsc --noEmit` and `npm run build`.

## 6. Verification

- [x] 6.1 Record a short clip with speech, stop, and confirm the recording transitions `processing → ready` and segments are stored.
- [x] 6.2 Confirm the detail view shows processing then auto-renders the transcript without a manual reload.
- [x] 6.3 Restart the backend with a recording left in `processing`; confirm it is re-enqueued and completes.
- [x] 6.4 Confirm a transcription error sets status `failed` with an error message (e.g. point at a missing/corrupt file).
