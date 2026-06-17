## Why

Post-recording processing of a long meeting can take many minutes, during which the user sees only a progress bar (a time-based *estimate* on the MLX engine) and no transcript until the very end. Two improvements make the wait far more bearable: a **real** progress percentage from chunked transcription, and showing the **transcript as soon as it exists** — before diarization and the summary finish. Additionally, when speaker separation isn't needed, the user should be able to **cancel diarization** (the slowest stage) and still get a summary.

## What Changes

- **Chunked transcription (non-streaming engines)**: Transcribe the audio in fixed-size windows (e.g. ~3 min) so progress reflects real work done (`chunks_done / total`) instead of a time estimate. faster-whisper already streams per-segment, so it is unaffected.
- **Early/progressive transcript**: Persist transcript segments as soon as each track's transcription completes (and incrementally per chunk where possible), so the detail view shows the transcript while diarization and the summary are still running — the transcript is no longer gated on the summary.
- **Summary runs last, in the background**: The recording becomes viewable with its transcript before the summary is generated; the summary fills in when ready. Status stays within the existing `processing → ready` lifecycle.
- **Cancel diarization**: While the `diarizing` stage runs, the UI shows a Cancel control. Cancelling abandons diarization, applies the baseline speaker split to the already-transcribed lines, and proceeds to the summary. (Useful when speaker labels aren't needed and diarization is the slow part.)

## Capabilities

### New Capabilities

- `diarization-cancellation`: The user can cancel an in-progress diarization stage; the system falls back to the baseline speaker split and still generates the summary.

### Modified Capabilities

- `transcription-job`: Non-streaming engines transcribe in chunks (real progress); transcript segments are persisted as soon as transcription finishes (before the summary), and the summary is generated as the final background step. (Expressed as added requirements.)
- `transcript-view`: The transcript renders progressively while a recording is still `processing`, not only once `ready`. (Added requirement.)

> Note: chunked transcription naturally produces a real (measured) fraction, which the existing `processing-progress` requirement already handles ("fraction when available"); the `processing-progress` capability needs no requirement change. Diarization cancellation reuses the baseline-split fallback already specified by `speaker-diarization`; the cancel behavior lives in the new `diarization-cancellation` capability.

## Impact

- **Backend**:
  - `transcribe/mlx.py` (and the engine interface): add a chunked transcription path that loads the waveform once, slices it into windows, transcribes each (offsetting timestamps), and calls `progress_cb(done_seconds, total_seconds)` per chunk → real fraction. Configurable chunk length (`TRANSCRIBE_CHUNK_SECONDS`, default ~180).
  - `processing/job.py`: restructure `_process` so segments are written right after transcription (baseline speakers), the recording's transcript becomes visible, then diarization runs (re-labelling speakers), then the summary. Track a per-recording cancel flag for diarization.
  - `api/recordings.py`: add `POST /api/recordings/{id}/cancel-diarization`; progress already exposes the stage so the UI knows when to show Cancel.
  - Diarization stays a single whole-file pass; cancellation makes the job stop *waiting* on it and proceed with the baseline split (the orphaned compute is discarded).
- **Frontend**:
  - `RecordingDetail.tsx`: render the transcript whenever segments exist (already mostly true) while keeping the progress bar for the remaining stages; show a **Cancel** button during the `diarizing` stage.
  - `lib/api.ts`: add `cancelDiarization(id)`.
- **DB**: no schema change — segments are written earlier within the existing tables; status enum unchanged. The transcript "re-flows" once when diarization assigns final speakers.
- **Caveats**: chunk boundaries cost a little cross-window context (minor quality dip); with diarization on, early segments show provisional/baseline speakers until diarization relabels them.
