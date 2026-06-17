## 1. Backend — chunked transcription

- [x] 1.1 Add `transcribe_chunk_seconds` config (default 180; 0 disables chunking)
- [x] 1.2 In `MlxWhisperWorker.transcribe_file`, load the waveform once (`mlx_whisper.audio.load_audio`), slice into `transcribe_chunk_seconds` windows, transcribe each, offset segment/word times by the window start, and call `progress_cb(done_seconds, total_seconds)` after each chunk
- [x] 1.3 When chunking is disabled (0) or duration unknown, fall back to the single-pass call (existing behavior)
- [x] 1.4 Confirm faster-whisper is unchanged (already streams a real fraction)

## 2. Backend — early transcript + summary-last ordering

- [x] 2.1 Restructure `processing/job.py::_process`: after transcription, write baseline segments/speakers immediately (mic→"You", system/single→"Others"/"Speaker 1") in a first transaction so the transcript is visible
- [x] 2.2 If diarization is in effect and not cancelled, run it and replace that track's segments/speakers with the diarized word-level result in a second transaction (reuse `_speaker_groups`/`diarize_lines`)
- [x] 2.3 Generate the summary as the final step (stage `summarizing`), then flip to `ready`; keep "ready ⇒ transcript + summary present" for non-empty transcripts
- [x] 2.4 Ensure segment/speaker replacement is idempotent (clear-then-write) so baseline→diarized swap is clean and re-runnable

## 3. Backend — cancel diarization

- [x] 3.1 Add a per-recording cancel set on the processor (`self._cancel_diar: set[int]`) and a `cancel_diarization(id)` method
- [x] 3.2 In `_process`, check the flag before running diarization for a track; if set, skip diarization and keep the baseline segments, then proceed to summary
- [x] 3.3 Make the diarization await cancellable: run it so the job can stop waiting on a cancel signal and proceed with the baseline split (orphaned pyannote pass finishes in the background, result discarded)
- [x] 3.4 Clear the cancel flag in the job's `finally`
- [x] 3.5 Add `POST /api/recordings/{id}/cancel-diarization` (no-op when not diarizing)

## 4. Frontend

- [x] 4.1 Add `cancelDiarization(id)` to `lib/api.ts`
- [x] 4.2 In `RecordingDetail.tsx`, render the transcript whenever segments exist (even while `processing`), keeping the progress bar for remaining stages
- [x] 4.3 Show a **Cancel** button next to the progress bar only while the stage is `diarizing`; on click call `cancelDiarization` and reflect the change
- [x] 4.4 Verify the transcript re-flows (speakers update) once diarization assigns speakers, without a manual reload

## 6. Silence gate (no hallucinated speech on empty tracks)

- [x] 6.1 Add `silence_peak_threshold` config and a `_is_silent(path)` helper (blocked peak read, bounded memory)
- [x] 6.2 In `_process`, skip transcribing any silent track (and skip diarizing a silent system/single track); a silent system track produces no "Others" speaker
- [x] 6.3 Regression test: silent system track yields only the "You" speaker (mic), no hallucinated "Others"

## 5. Verification

- [x] 5.1 On the MLX engine, a multi-chunk recording shows a real, advancing percentage (not the `~` estimate) that tracks completed audio
- [ ] 5.2 The transcript appears while the recording is still `processing` (during diarizing/summarizing), before it becomes `ready`
- [ ] 5.3 With diarization on, clicking Cancel during `diarizing` yields baseline speakers, still generates a summary, and reaches `ready`
- [x] 5.4 Cancel is shown only during `diarizing`; a cancel sent otherwise is a no-op
- [x] 5.5 Chunk timestamps are absolute (transcript ordering is correct across chunk boundaries); `TRANSCRIBE_CHUNK_SECONDS=0` falls back to single-pass
- [x] 5.6 faster-whisper path still streams a real percentage and is otherwise unchanged
