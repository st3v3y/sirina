## Context

The post-recording pipeline (`processing/job.py`) runs one recording at a time: it loads whisper, transcribes the mic and/or system track via `FasterWhisperWorker.transcribe_file`, optionally diarizes, writes `Segment`/`Speaker` rows, generates the auto-summary, then flips the recording to `ready`. The frontend (`RecordingDetail.tsx`) polls `getRecording` every 3s and shows an indeterminate "Transcribing…" banner while `status == "processing"`.

Two gaps: (1) no progress signal, and (2) the engine is hard-coded to faster-whisper/CTranslate2, which is CPU-only on Apple Silicon. `mlx_whisper` uses the Apple GPU and is materially faster. The app is local-only and being packaged toward Tauri; it must keep running where MLX is unavailable.

## Goals / Non-Goals

**Goals:**
- A real, staged progress signal for the post-recording job, with a live transcription percentage where the engine supports it.
- Automatic, hardware-aware engine selection (MLX on Apple GPU, faster-whisper otherwise) behind one interface, with safe fallback.
- Zero schema changes; progress is ephemeral.

**Non-Goals:**
- Live transcription/diarization during the recording phase (explicitly rejected earlier — keeps capture isolated and reliable).
- Streaming/online diarization. Diarization stays a single whole-file pass.
- A precise percentage for the diarization and summary stages (they don't expose clean fractions).
- WebSocket push for progress — polling the existing detail endpoint is sufficient.

## Decisions

### 1. Engine abstraction + selection
Define a minimal protocol both engines satisfy:
`async load()`, `is_loaded()`, `async transcribe_file(path, *, word_timestamps, progress_cb=None) -> (list[TLine], language)`.
`FasterWhisperWorker` already matches this (add the optional `progress_cb`). A new `MlxWhisperWorker` wraps `mlx_whisper.transcribe(path, path_or_hf_repo=<mapped repo>, word_timestamps=...)` and converts its `segments` (with `words`) into `TLine`s.

**Selection** at startup (in the lifespan/runtime wiring):
- If `settings.transcription_engine` is set (`faster-whisper` | `mlx` | `auto`), honor it.
- `auto` (default): use MLX when `platform.system() == "Darwin"` **and** `platform.machine() == "arm64"` **and** `import mlx_whisper` succeeds; else faster-whisper.
- Any MLX load/transcribe failure logs and the recording falls back per the existing failure path. (We do not silently swap engines mid-recording; the selected engine is fixed at startup.)

*Alternative considered:* a hard dependency on mlx — rejected; it only installs on Apple Silicon. Platform-marker optional dependency keeps other environments working.

### 2. Model-name mapping
faster-whisper uses bare sizes (`"medium"`). MLX uses HF repos (`mlx-community/whisper-medium`, `…-large-v3`, etc.). The MLX worker maps `settings.whisper_model` → a `mlx-community/whisper-<size>` repo, with an override `settings.mlx_whisper_repo` for exact control. Unknown sizes fall back to a sensible default and log.

### 3. Progress model (in-memory)
The processor holds `self._progress: dict[int, Progress]` where `Progress = {stage: str, fraction: float | None}` with stages `queued | transcribing | diarizing | summarizing | done`. A method `progress_for(id) -> Progress | None`.
- **Transcription fraction**: `transcribe_file` accepts `progress_cb(done_seconds, total_seconds)`. faster-whisper calls it as it iterates segments (`seg.end` vs `info.duration`) → smooth %. For a two-track recording, the two passes are weighted (mic then system) into one 0–1 range. MLX has no streaming callback → it reports stage-only (fraction `None`).
- **Other stages**: set the stage label; fraction `None` (indeterminate within the stage).
- Cleared (or set to `done`) when the recording finishes; absent for non-processing recordings.

Why in-memory: progress updates many times/second; persisting would thrash SQLite for data that is meaningless after completion. A process restart re-enqueues the job (existing behavior), and progress simply restarts.

### 4. Exposure to the UI
Enrich the existing `GET /api/recordings/{id}` (and the list endpoint) response with an optional `progress` object read from `runtime.processor.progress_for(id)`. No new endpoint. The detail view polls slightly faster (~1.5s) while `processing` and renders a bar: stage label always, a filled percentage when `fraction` is present, indeterminate shimmer otherwise. Status endpoint adds the active engine name for visibility.

### 5. word_timestamps stays conditional
Both engines accept `word_timestamps`; the job already requests them only when diarization is in effect for that track. The spec text for transcription-job is clarified so the word-timestamp guarantee is about *speaker alignment when diarizing*, engine-independent.

## Risks / Trade-offs

- **MLX output shape differs from faster-whisper** → segment/word fields may not map 1:1. → Mitigation: a small adapter with defensive `.get()`s; treat missing word timing as "no words" (diarization already falls back to line-level units).
- **MLX model download on first run** (HF repo) → first MLX transcription is slow/needs network. → Mitigation: log clearly; same one-time cost faster-whisper already has.
- **Coarse progress on MLX** → users on Apple GPU see stage-only progress, not a smooth %. → Mitigation: documented; the speed gain offsets it, and stages still advance.
- **Progress map leak** if a job dies without cleanup → small unbounded dict. → Mitigation: clear the entry in a `finally` around processing; it's keyed by recording id so re-runs overwrite.
- **Engine mismatch confusion** (which engine ran) → Mitigation: status reports the active engine; log it at startup.

## Migration Plan

1. Add the engine protocol + `MlxWhisperWorker`; wire selection in startup. Default `auto`.
2. Add the progress map + `progress_cb` plumbing; enrich API responses.
3. Frontend progress bar + faster poll.
4. `pyproject`: `mlx-whisper` under `sys_platform == 'darwin' and platform_machine == 'arm64'` (optional). No DB migration.
5. Rollback: set `TRANSCRIPTION_ENGINE=faster-whisper` to force the old path; progress is additive and inert if ignored.

## Open Questions

- Exact `mlx-community` repo names per model size — confirm at implementation against the live HF org (e.g. `whisper-medium` vs `whisper-medium-mlx`); the `mlx_whisper_repo` override exists as an escape hatch.
- Whether to also show the dashboard-list mini progress — included as optional polish, not required.
