## Context

After `record-to-file`, stopping a recording finalizes audio files and sets status `processing`, but nothing transcribes them. This change adds the background processor that turns `processing` recordings into `ready` ones with stored transcripts. It reuses the existing `FasterWhisperWorker` (already loaded at startup) and the recording-store schema.

## Goals / Non-Goals

**Goals:**
- A restart-safe, single-flight background queue that transcribes finished recordings.
- High-quality offline transcription (bigger model, beam search, VAD, word timestamps).
- Persist `Segment` rows with accurate start/end/text + the detected language.
- Detail view that shows processing and auto-renders the transcript when ready.

**Non-Goals:**
- Speaker assignment / diarization — segments get a placeholder `speaker_label` here; real speakers come in `speakers-and-people`.
- Summaries on completion — that is `structured-summaries`.
- Changing capture (that is `record-to-file` / `tauri-desktop-app`).

## Decisions

- **Single background worker + asyncio.Queue.** A `TranscriptionProcessor` owns one long-lived task that pulls recording ids and processes them sequentially. Inference itself runs in the whisper worker's thread executor so the event loop stays responsive.
  - *Alternative*: a thread/process pool. Rejected — one Mac, one model in memory; concurrency would just thrash CPU and double memory.
- **Restart-safe via DB scan.** On startup, `requeue_pending()` selects recordings with status `processing` and re-enqueues them. The queue is the only scheduler; stop() enqueues the just-finished recording.
- **Enqueue from the `/stop` endpoint** after `recorder.stop()` returns. Keeps the recorder free of processing concerns.
- **Batched inference for throughput.** Use `faster_whisper.BatchedInferencePipeline` with `vad_filter=True`, `beam_size=5`, `word_timestamps=True`. Batched mode is the big speed win on long files. Trade-off: batched mode does not use `condition_on_previous_text` (segments are processed independently); we accept this for throughput. Fall back to sequential `model.transcribe` if the batched pipeline is unavailable.
  - *Alternative*: sequential with `condition_on_previous_text=True` for marginally more coherent long-range text. Rejected as the default — much slower; batched + VAD gives the better overall result for meeting audio.
- **Default model stays `medium`, configurable.** The redesign's open question (large-v3 vs turbo vs medium) is unresolved and `large-v3` forces a ~3 GB download. Keep `WHISPER_MODEL=medium` as the shipped default (already present, good quality offline) and document bumping to `large-v3-turbo` for best quality. This change does not silently force a large download.
- **Transcribe the mixed/primary track** (`Recording.audio_path`), resampled to 16 kHz inside the worker. faster-whisper accepts a file path or array; we pass the path and let it handle decoding/resampling.
- **Placeholder speaker label.** Segments are written with `speaker_label = "Speaker 1"`. `speakers-and-people` replaces this with the mic/system split and real names.
- **Detail view auto-refresh by polling.** While status is `processing`, the detail view polls `GET /api/recordings/{id}` every few seconds until `ready`/`failed`. Simplest reliable approach; no new WebSocket needed.

## Risks / Trade-offs

- [Batched mode drops `condition_on_previous_text`] → Acceptable; VAD + beam search dominate quality for meeting audio. Documented.
- [Long recordings take minutes to transcribe] → Expected for offline; the UI shows processing and the queue is single-flight so the machine isn't overloaded.
- [A crash mid-job leaves status `processing`] → `requeue_pending()` on startup recovers it; idempotent because re-transcription overwrites the (absent) segments. Clear any partial segments before writing.
- [BatchedInferencePipeline API differences across faster-whisper versions] → Guard import; fall back to sequential transcribe.

## Migration Plan

No schema change beyond what `record-to-file` already created (`Recording.language`, `Segment` exist). No data migration. Deploy = restart backend; pending `processing` recordings auto-resume.

## Open Questions

- Final default model (`medium` vs `large-v3-turbo`) — left to the user; configurable via `WHISPER_MODEL`.
- Whether to also store per-word timestamps now (needed by diarization later) or recompute in `speakers-and-people`. Lean: keep segment-level start/end now; `speakers-and-people` can request word timestamps when it needs them.
