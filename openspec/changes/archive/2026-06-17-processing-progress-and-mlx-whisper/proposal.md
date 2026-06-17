## Why

After stopping a recording, the user stares at an indeterminate "Transcribing…" message with no sense of how long it will take — especially painful for long meetings (a 63‑minute recording can take many minutes). And on Apple Silicon the transcription engine (faster‑whisper / CTranslate2) is CPU‑only, leaving the GPU idle; `mlx-whisper` runs on the Apple GPU and is typically 3–5× faster at the same model size.

## What Changes

- **Post-processing progress**: The background job reports staged progress — `transcribing` (with a live percentage derived from segment end-time ÷ audio duration), `diarizing`, `summarizing`, `done` — exposed to the UI so the recording detail view shows a real progress bar instead of an indeterminate spinner.
- **Hardware-aware transcription engine**: On Apple Silicon with `mlx_whisper` available, transcription uses an MLX (Apple‑GPU) engine; otherwise it falls back to faster‑whisper. Selection is automatic at startup, behind the existing transcription interface so nothing downstream changes. The active engine is reported in status.
- **Optional dependency**: `mlx-whisper` is added as a platform-gated optional dependency (Apple Silicon only); the app runs unchanged where it is absent.

## Capabilities

### New Capabilities

- `processing-progress`: The post-recording job tracks and exposes per-recording processing progress (stage + optional fraction) for the UI.

### Modified Capabilities

- `transcription-job`: Transcription engine is selected by hardware/availability (MLX on Apple GPU, faster-whisper otherwise) behind one interface, with graceful fallback. The word-level timestamp guarantee is clarified as engine-independent.
- `transcript-view`: The processing indication becomes a staged progress bar (stage label + percentage when available) rather than an indeterminate spinner.
- `local-only-runtime`: The status endpoint additionally reports which transcription engine is active.

## Impact

- **Backend**:
  - New transcription-engine abstraction: a common `transcribe_file(path, *, word_timestamps) -> (lines, language)` protocol implemented by the existing `FasterWhisperWorker` and a new `MlxWhisperWorker`; a selector at startup based on `platform.machine()`/`mlx_whisper` import (overridable via config).
  - `processing/job.py`: maintain an in-memory `{recording_id: progress}` map; update it at each stage; wrap the whisper segment iteration to report transcription fraction.
  - `api/recordings.py`: include a `progress` field (stage + fraction) on the recording detail (and list) responses, sourced from the processor's in-memory map.
  - `api/status.py`: report the active engine name.
  - `pyproject.toml`: add `mlx-whisper` under an Apple-Silicon platform marker (optional extra).
- **Frontend**:
  - `RecordingDetail.tsx`: replace the indeterminate "Transcribing…" banner with a progress bar driven by `progress` (stage label + %); poll a bit faster (~1.5s) while `processing`.
  - `lib/api.ts`: add `progress` to the recording types; `Status` gains the engine field.
  - Optionally surface a small progress indicator on the dashboard list for in-flight recordings.
- **Caveats**: MLX transcription returns all segments in one call, so the transcription fraction is coarse (stage-level) on the MLX path; the bar still advances by stage. faster-whisper keeps the smooth per-segment percentage.
- **No DB schema changes**: progress is in-memory only; nothing is persisted.
