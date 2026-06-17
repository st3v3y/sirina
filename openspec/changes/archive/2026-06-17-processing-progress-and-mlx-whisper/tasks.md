## 1. Backend — transcription engine abstraction

- [x] 1.1 Define a common engine interface/protocol: `async load()`, `is_loaded()`, `async transcribe_file(path, *, word_timestamps, progress_cb=None) -> (list[TLine], language)`, and a `name` property
- [x] 1.2 Make `FasterWhisperWorker` satisfy it: add optional `progress_cb(done_seconds, total_seconds)` called while iterating segments (use `seg.end` and `info.duration`); add `name = "faster-whisper"`
- [x] 1.3 Add `MlxWhisperWorker` in `transcribe/` wrapping `mlx_whisper.transcribe(path, path_or_hf_repo=<repo>, word_timestamps=...)`, converting its segments/words to `TLine`s; `name = "mlx"`; fraction reporting is stage-only (no streaming callback)
- [x] 1.4 Add config: `transcription_engine` (`auto` default | `faster-whisper` | `mlx`) and `mlx_whisper_repo` override; map `whisper_model` size → `mlx-community/whisper-<size>` repo with a logged default for unknown sizes
- [x] 1.5 Add a selector used at startup: `auto` → MLX when `platform.system()=="Darwin"` and `platform.machine()=="arm64"` and `import mlx_whisper` succeeds, else faster-whisper; honor explicit config; log the chosen engine
- [x] 1.6 Wire the selector into the lifespan/runtime so `runtime.whisper` is the chosen engine; keep `whisper_loaded()` working

## 2. Backend — progress tracking

- [x] 2.1 In `TranscriptionProcessor`, add an in-memory `self._progress: dict[int, dict]` and `progress_for(id) -> dict | None` (stage + optional fraction)
- [x] 2.2 Set stage `queued` on enqueue; `transcribing` / `diarizing` / `summarizing` / `done` at the corresponding points in `_process`
- [x] 2.3 Pass a `progress_cb` into `transcribe_file` that updates the transcribing fraction; for two-track recordings weight the mic then system passes into a single 0–1 range
- [x] 2.4 Clear/finalize the progress entry in a `finally` so a failed/finished job doesn't leak; absent for non-processing recordings

## 3. Backend — expose progress + engine

- [x] 3.1 Add a `progress` field (stage + fraction|null) to the recording detail response and the list item, sourced from `runtime.processor.progress_for(id)`
- [x] 3.2 Add the active engine name to the status endpoint (`api/status.py`) and its response model
- [x] 3.3 Add `mlx-whisper` to `pyproject.toml` under a `sys_platform == 'darwin' and platform_machine == 'arm64'` marker (optional/extra); confirm non-Apple installs are unaffected

## 4. Frontend — progress bar

- [x] 4.1 Add `progress` to the `Recording`/`RecordingDetail` types and `engine` to `Status` in `lib/api.ts`
- [x] 4.2 In `RecordingDetail.tsx`, replace the indeterminate "Transcribing…" banner with a progress bar: stage label always, a filled % when `fraction` is present, indeterminate shimmer otherwise
- [x] 4.3 Poll the detail endpoint faster (~1.5s) while `processing`
- [x] 4.4 (Optional polish) Show a small inline progress indicator on the dashboard list for in-flight recordings

## 6. Refinements (elapsed time, estimate, MLX warm-up, DEV logging)

- [x] 6.1 Warm the MLX model in `load()` (download + resident `ModelHolder` cache at startup) so the ~GB download isn't a silent mid-job hang; log it
- [x] 6.2 Add `streams_progress` to both engines + the protocol; faster-whisper streams, MLX does not
- [x] 6.3 Track per-recording start time; expose `elapsed_s` in progress
- [x] 6.4 Derive a time-based estimated fraction (capped <1.0, flagged `estimated`) for non-streaming engines from `duration_s × transcribe_rt_factor` (×2 for two-track)
- [x] 6.5 Frontend: show elapsed time (mm:ss) and percentage (real, or `~` estimated) in the progress bar
- [x] 6.6 Add `DEV` config flag → DEBUG logging, with noisy third-party loggers kept at INFO; add debug logs in the processing path

## 5. Verification

- [x] 5.1 On Apple Silicon with `mlx-whisper` installed, startup logs and `/api/status` report the MLX engine; transcription succeeds and is faster than faster-whisper on the same file
- [x] 5.2 Forcing `TRANSCRIPTION_ENGINE=faster-whisper` uses faster-whisper and shows a smooth transcription percentage that advances with audio time
- [ ] 5.3 A processing recording shows stage transitions (transcribing → diarizing → summarizing → done) in the detail view, with a bar that fills during transcription
- [x] 5.4 On a non-Apple environment (or with MLX absent), the app starts and transcribes via faster-whisper unchanged
- [x] 5.5 Progress is absent for `ready`/`failed` recordings and does not error after a restart
