## Context

`processing/job.py::_process` currently: loads the engine → transcribes each track (diarization happens *inside* `_speaker_groups` for the system/single track) → writes all `Segment`/`Speaker` rows in one transaction → generates the summary → flips to `ready`. So the transcript is invisible until the very end, and on the MLX engine there is no real progress (a time-based estimate fills the bar). The frontend already renders `transcriptItems` whenever segments exist and shows the progress bar while `status == "processing"`.

## Goals / Non-Goals

**Goals:**
- Real progress fraction on non-streaming engines via chunked transcription.
- Persist + display the transcript before diarization/summary finish.
- Let the user cancel diarization and still get a summary.
- No DB schema change; status lifecycle unchanged (`processing → ready`).

**Non-Goals:**
- Killing the pyannote computation mid-flight (not cleanly interruptible) — cancellation means "stop waiting and use the baseline split"; the orphaned thread finishes and its result is discarded.
- Streaming/online diarization or live speaker labels.
- Changing faster-whisper's path (it already streams a real fraction).
- A new `transcript-ready` status value (avoids touching the recording-store enum).

## Decisions

### 1. Chunked transcription for non-streaming engines
Add `transcribe_file` chunking in the MLX worker: load the waveform once (`mlx_whisper.audio.load_audio`), slice into `TRANSCRIBE_CHUNK_SECONDS` (~180s) windows, transcribe each window, offset each segment/word time by the window start, and call `progress_cb(done_seconds, total_seconds)` after each chunk. The processor's existing `progress_cb` → real fraction (no estimate needed when chunking reports). faster-whisper keeps its per-segment streaming.
- *Quality:* boundaries lose cross-window conditioning; ~3 min windows keep this rare. Configurable.
- *Engine flag:* chunked MLX now effectively streams progress, so set/treat it as reporting a real fraction; the time-estimate path remains a fallback when duration is unknown or chunking is disabled (`TRANSCRIBE_CHUNK_SECONDS=0`).

### 2. Early/progressive transcript persistence
Restructure `_process`:
1. Transcribe each track (chunked where applicable). After transcription, **write baseline segments immediately** (mic→"You", system/single→"Others"/"Speaker 1") and set stage so the UI shows the transcript. (Optionally write per-chunk for true progressive appearance — same mechanism, more writes.)
2. If diarization is in effect and not cancelled, run it, then **replace** that track's segments/speakers with the diarized, word-level result (the existing `_speaker_groups` + `diarize_lines` logic) in a second transaction.
3. Generate the summary (stage `summarizing`).
4. Flip to `ready`.

The transcript is visible from step 1; it "re-flows" once at step 2 when speakers are assigned. The frontend already polls and re-renders, so no protocol change — just earlier writes. `ready` still means transcript + summary both present.

### 3. Cancel diarization
A per-recording cancel flag on the processor (`self._cancel_diar: set[int]`). `POST /api/recordings/{id}/cancel-diarization` adds the id to the set (and is a no-op if not diarizing). In `_process`, before running diarization for a track, check the flag; if set, skip diarization and keep the baseline segments already written. Because pyannote runs as one blocking executor call, a cancel *during* the call can't preempt it — so we run diarization in a task we can stop *awaiting*: the job `await`s the diarization with a cancellation race (e.g. an `asyncio.Event`), and on cancel proceeds with the baseline split while the executor thread is left to finish and its result discarded. Simplest robust form: check the flag right before starting diarization and also offer cancel to take effect at the next track boundary; document that an already-running pyannote pass may run to completion in the background but its output is ignored.
- *Result on cancel:* baseline speaker split (already persisted) stands; summary proceeds. Status → `ready`.

### 4. Progress stages
Stages become: `queued → transcribing (real %) → [diarizing (cancellable)] → summarizing → done`. Progress already carries `stage`, `fraction`, `elapsed_s`. The UI shows Cancel only during `diarizing`.

## Risks / Trade-offs

- **Chunk-boundary quality dip** → use ~3 min windows; configurable; document it. Mitigation: overlap could be added later, not in v1.
- **pyannote not preemptible** → cancellation discards the result rather than killing the thread; one wasted pass at worst. Acceptable; documented.
- **Transcript re-flow on diarization** → segments change speaker/segmentation once mid-view. Mitigation: it only happens once; the bar still shows `diarizing`, so it's expected.
- **More DB writes** (baseline then diarized) → two transactions per diarized track. Negligible at these volumes.
- **Cancel race** (cancel arrives just as diarization finishes) → harmless: whichever path completes, segments are consistent (baseline or diarized); idempotent segment/speaker replacement guards it.

## Migration Plan

1. Add chunked transcription to the MLX worker + `TRANSCRIBE_CHUNK_SECONDS` config (default 180; 0 disables).
2. Restructure `_process` for early segment writes + post-summary ordering; add the diarization cancel flag + endpoint.
3. Frontend: show transcript during processing (already mostly there) + Cancel button during `diarizing`; add `cancelDiarization`.
4. No DB migration. Rollback: set `TRANSCRIBE_CHUNK_SECONDS=0` to disable chunking; the cancel endpoint is additive.

## Open Questions

- Per-chunk segment writes (true progressive transcript) vs. one write after each track finishes — start with per-track writes; add per-chunk if the incremental feel is wanted.
- Whether `transcribe_rt_factor` estimate is still needed once chunking lands — keep it as the fallback when duration is unknown or chunking disabled.
