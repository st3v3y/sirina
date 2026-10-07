## Context

Post-recording processing (`app/processing/job.py`) transcribes the `mic` and `system` tracks one after the other with faster-whisper (CPU, `large-v3`, int8, beam 3, batch 8, all cores), writes the whole transcript, then diarizes, summarizes, and compresses. The packaged app ships without MLX, so faster-whisper is always the engine. Field logs show 0.3x–3.5x real time per second of speech for the same settings.

Benchmark (2026-10-06, M1 Pro 6P+2E, 16 GB, 10-minute clip with 9.4 min of speech, AC power):

| Setup | Time | Peak RAM | Text vs today |
|---|---|---|---|
| Today: faster-whisper large-v3, 8 threads | 193 s | 8.5 GB | — |
| faster-whisper large-v3, 6 threads | 118 s | 8.2 GB | identical |
| WhisperKit large-v3-turbo 626 MB (ANE) | 59 s | 0.4 GB | ~5% raw diff, ~1.6% est. real errors |
| WhisperKit large-v3 (full) | 444 s | 1.2 GB | dropped whole passages |
| Apple SpeechTranscriber (offline) | 9 s | small | ~11% diff (fillers, names) |
| Apple SpeechTranscriber (live) | caption ~0.1 s provisional / ~0.8 s settled, ~2.5% of one core | | |
| faster-whisper at background QoS (E-cores) | >25 min | | not viable during a call |

"Est. real errors" counts only differences where Apple's independent transcript sides with `large-v3`; it is a rough proxy, not a human-checked WER.

Constraints: the packaged app is macOS-only (Apple Silicon); 16 GB Macs are common and often already swapping; the existing Swift sidecar (`native/system-audio-capture`) is a plain `swiftc` build copied into Tauri resources and codesigned by `scripts/build-macos-app.sh`; the UI already polls the recording every 1.5 s while processing (`RecordingDetail.tsx`) and the active recording every 1 s (`useRecorder.ts`).

Related changes: `harden-system-audio-capture` added the recording-time sleep assertion; `production-hardening` 4.x plans an on-demand diarization model download and replacing pyannote/torch.

## Goals / Non-Goals

**Goals:**
- Cut a typical 1h two-track recording from ~25 min (good day) / hours (bad day) to under ~10 min of processing before the final transcript is complete on the reference Mac.
- Show a readable draft immediately at stop, and make it final progressively, both tracks together.
- Optional live captions that cost almost nothing and appear within ~2 s.
- Keep the app bundle small: no bundled model weights, no MLX, a few MB for the new helper.

**Non-Goals:**
- Replacing pyannote diarization (SpeakerKit is an open question for `production-hardening`).
- Running the final pass during the recording.
- Linux/Windows feature parity: there, faster-whisper remains and captions/draft are unavailable.
- Editing draft text.

## Decisions

### D1. One native helper, `speech-engine`, long-running, JSON lines over stdio
WhisperKit is pinned in `Package.resolved` to a tagged release of `argmaxinc/argmax-oss-swift` (1.x); upgrades are a deliberate bump plus a rerun of the validation tasks.
A new Swift package `native/speech-engine/` (SwiftPM, depends on Argmax's open-source WhisperKit; uses Apple's Speech framework) builds one binary with three modes:
- `serve`: long-running. Reads one JSON request per line on stdin, writes one JSON response per line on stdout. Requests: `load {model_dir}`, `transcribe {path, start_s, end_s, language?, prompt?}` → `{segments:[{start,end,text,words:[[s,e,w]...]}], language}`, `draft {path, start_s?, end_s?}` → SpeechTranscriber offline segments, `status` → `{low_power, on_battery, captions_supported}`.
- `captions --sample-rate 48000`: reads raw s16le mono PCM on stdin, writes `{kind:"provisional"|"settled", start, end, text}` lines.
- `--probe`: exits 0 if it can run, prints capabilities.

Times are absolute recording seconds (the helper reads the WAV itself and slices `start_s..end_s`), so Python never ships audio for the final pass.

*Alternatives:* `whisperkit-cli serve` (OpenAI-style HTTP): not ours to bundle, no per-window word timestamps contract, HTTP for a local child is overhead. One process per window: pays model load + ANE specialization each time. Python bindings: none exist.

### D2. Final engine: WhisperKit, `openai_whisper-large-v3-v20240930_626MB`
Default model is OpenAI's large-v3-turbo, compressed for the Neural Engine. It was the only WhisperKit variant that was both fast and did not drop passages in the benchmark. Decoding: WhisperKit defaults (greedy with temperature fallback), word timestamps on, vocabulary prompt from `whisper_initial_prompt`, language from settings or detected on the first window. Inside a window the helper uses WhisperKit's VAD chunking (the turbo run kept all passages); a validation task re-checks this on full recordings.

A new `WhisperKitEngine` in `app/transcribe/whisperkit.py` implements `TranscriptionEngine`, extended with `transcribe_window(path, start_s, end_s, ...)`. It owns the helper subprocess (start on `load()`, restart once on crash).

*Alternatives:* MLX turbo (40 s, 3.1 GB RAM, +480 MB bundle): faster but bigger and memory-hungry; WhisperKit full large-v3: slower and lossy; faster-whisper turbo: 2x faster than today but ~2.9% est. errors (drops phrases) and still ~6.7 GB RAM.

### D3. Engine selection
`transcription_engine`: `auto | whisperkit | faster-whisper` (MLX removed from options; a stored `mlx` value is read as `auto`). `auto` → WhisperKit when the helper probes OK and the configured WhisperKit model is installed; otherwise faster-whisper, with `runtime.engine_note` explaining why. If the model is missing on first run, the job downloads it (stage `preparing_model`) and uses WhisperKit afterwards; on download failure it falls back for that job.

### D4. Windowed, two-track final pass (one module for both callers)
`app/processing/windows.py` holds the pure cut chooser (speech regions in, cut points out; table-tested) and `finalize_range(recording, from_s, to_s, engine)`, which loops windows and commits them. The post-stop job and the during-recording finalizer (D13) both call it; neither has its own loop.
1. Compute speech regions per non-silent track with the Silero VAD already bundled with faster-whisper (`get_speech_timestamps`; ~seconds per hour).
2. Choose cut points near multiples of `transcribe_chunk_seconds` (default 180): the nearest gap ≥ 0.5 s that is silent in all tracks within ±30 s; else the nearest gap silent in any track.
3. For each window in time order: transcribe each track's slice (skip tracks with no speech in it), then commit (D5), then set `final_until_s` = window end.

A 180 s window across both tracks takes ~35 s with WhisperKit on the reference Mac, matching the requested 30–60 s update rhythm. faster-whisper uses the same loop: the batched pipeline already decodes ~30 s VAD chunks independently, so slicing at silences does not change its output (verified by a test comparing windowed vs whole-file text on the benchmark clip).

This replaces the MLX-only "chunked transcription" path; the job, not the engine, owns windows.

### D5. Draft/final storage and resume
- `Segment.is_draft: bool = False` and `Segment.words: str | None` (JSON `[[start,end,word],...]`, final rows only); `Recording.final_until_s: float | None`. All additive columns via the existing `db.py` ALTER path.
- **Why `words`:** diarization (`diarize_lines`) and echo suppression (`_is_echo_cluster`) assign speakers per word and today read the in-memory `TLine.words` of the whole track. With window commits (and windows finalized during recording or before a restart) those lists no longer exist in one process, so the diarization stage rebuilds `TLine`s per track from the stored final segments. `resegment_lines` already keeps each sub-line's words.
- **Window commit** (one transaction): delete this recording's draft rows with `start_ts` in `[win_start, win_end)`, insert the final lines (after `resegment_lines`, with `words`), set `Recording.final_until_s = win_end`. Progress mirrors the stored value.
- **Speaker rows** are created lazily on the first segment of a track ("You" for mic, "Speaker 1" for system) and reused by draft and final rows, so a track with no speech still produces no speaker and a rename made during processing survives window commits. Diarization still rewrites speakers and segments at the end (existing behaviour).
- **Resume and reprocess:** a job whose recording has `final_until_s` set resumes after it (crash, restart, live windows). The reprocess endpoint clears segments, speakers, and `final_until_s` before enqueueing, keeping today's "reprocess rebuilds everything".
- **Stopped processing** (`cancel-processing`): the recording becomes `ready` as today; finalized windows stay final, the rest stays draft. Readers therefore cannot rely on `ready` meaning "no drafts": the summary and exports read final rows only; Q&A reads final rows plus drafts marked as draft in the prompt (decided in review, see Open Questions if changed).

### D6. Draft at stop
Caption drafts are bulk-inserted at stop only for speech after `final_until_s` (live windows may already be final). For any remaining range without drafts, on a supported Mac, the job runs `draft` per non-silent track through the helper before its first final window (~9 s per 10 min). No draft recognizer → skip.

### D7. Live captions
When `live_captions` is on and the helper reports support, the recorder starts one `speech-engine captions` process per track. The mic callback and the system-sidecar pump already hold each PCM block; each `_Track`/`_SidecarTrack` puts a copy into a small bounded queue drained by a writer thread into the helper's stdin. When the queue is full the block is dropped (captions skip, recording is untouched). A reader thread parses result lines into an in-memory caption buffer per track (last provisional + settled list). The active-recording API returns the latest captions; `useRecorder` polls every 1 s (0.5 s when captions are on). At stop, settled captions are bulk-inserted as draft segments; no DB writes happen during recording.

*Alternatives:* WhisperKit streaming: large-v3 fell 3.6x behind real time; turbo competes for ANE/CPU with the video call. Tailing the growing WAV files from the helper: adds file-buffer latency and polling; the frames are already in Python.

### D8. Sleep guard through processing
Replace the recorder-owned `SleepBlocker` with a process-wide reference-counted `PowerGuard` (same IOKit assertion). The recorder holds one reference while recording; the job takes its own reference when a recording is enqueued (before the recorder releases), and releases it when the job ends (`ready`, `failed`, stopped). Assertion is held while the count is > 0.

### D9. Power state and thread default
`app/audio/power.py` gains `power_state()` → `{on_battery, low_power}` from `pmset -g batt` and `pmset -g` (`lowpowermode`), cached 30 s; the job adds `power_note` to progress while either is true. faster-whisper's `cpu_threads` default becomes `hw.perflevel0.physicalcpu` (via `sysctlbyname`), falling back to `os.cpu_count()`.

### D10. Model manager
A small registry (`app/speech_models.py`) of known models: WhisperKit turbo 626 MB (`argmaxinc/whisperkit-coreml`, folder pattern), faster-whisper `large-v3` (fallback), and the Apple caption/draft asset (status and install only; storage is managed by macOS). Downloads use `huggingface_hub.snapshot_download` into the existing `models/hf` cache in a background task with progress; a model counts as installed only when its expected files are all present. API: `GET /api/models`, `POST /api/models/{id}/install`, `DELETE /api/models/{id}` (refused for the in-use model while a job runs). Built so the diarization model planned in `production-hardening` 4.3 can be added as another entry.

### D13. Transcribe during recording (opt-in, per recording)
`Recording` gains `live_transcribe` and `live_captions` booleans, set from Settings defaults by the start dialog and changeable on the recording screen (`PATCH /api/recordings/active`). When `live_transcribe` is on and the engine is WhisperKit, a `LiveFinalizer` task runs beside the recorder:
- Every 15 s it checks how much audio both tracks have on disk (the recorder already counts frames per track). When both are past the next target cut + 30 s look-ahead, it runs VAD on the not-yet-final tail, picks the cut (same chooser as D4), transcribes the window for each track through the helper, and commits it (D5) with recording-relative times.
- The helper reads the growing WAVs: `wave` patches the header after every write, and the finalizer only requests ranges at least 2 s behind the written frame count.
- It shares the helper process and its request lock with the post-stop job, so a backlog simply continues after stop. The job starts from `final_until_s` instead of 0.
- The CPU engine is never used here (D3 fallback does not apply during a recording).
- Stop: `Recorder.stop` cancels the finalizer and awaits it before returning, so no window computed on the untrimmed timeline can commit after a trim. A cancelled in-flight window is simply redone after stop.
- Trim: `apply_trim` shifts all segments (final and draft) and `final_until_s` by `-start_s` and deletes segments starting outside `[start_s, end_s)`, in the same step that rewrites the WAVs.
- It runs outside the job queue: a job for an earlier recording may run at the same time. Both go through the helper's single request lock, so speech work stays sequential; the queue still runs one job at a time.

Work per window is the same as after stop, so total compute is unchanged; it is only moved into the call. At ~0.1x real time and ~17 CPU-s per 10 min (mostly Neural Engine), a 3-minute window costs ~20 s per track, so it stays well ahead of real time.

*Alternative considered (user idea):* bursts, e.g. every 10 min for about a minute. Same total work, but the boundary jumps in 10-minute steps and a burst is a bigger spike during the call. Steady 3-minute windows reuse the after-stop code path unchanged. The interval stays a setting (`transcribe_chunk_seconds`) so bursts can be tried.

*Diarization during recording:* pyannote clusters speakers over the whole file, so it would have to rerun on the growing file (3–13 min of CPU per run on this Mac). Out of scope; it stays after stop.

### D11. First-run Neural Engine preparation
The first load of a WhisperKit model compiles it for the Neural Engine (~3 min measured, cached by macOS afterwards). The job reports stage `preparing_model` with an explanation, and the app warms the model in the background after install so the first recording rarely waits.

### D14. Speaker splitting with SpeakerKit
The helper gains `diarize {path, end_s?}` → turns `[{start,end,speaker}]` plus one embedding per speaker. It replaces `Diarizer` (pyannote) behind the same `DiarizationResult` shape, so `diarize_lines`, cluster pruning and echo suppression stay as they are. Measured on the 2h14 system track: 52 s, 3.6 GB peak, 126 CPU-s vs pyannote 575 s, 7.2 GB; 5.9% disagreement in speech time (collar 0.25 s), 7 vs 6 speakers (the extra one 5 s, removed by the existing negligible-cluster pruning). Its model downloads from Argmax's Hugging Face repo without a token and is listed in the model manager.

`diarization_timing`: `after_stop` (default) | `during_recording`. With `during_recording`, the live finalizer runs `diarize` on the system track's audio so far about every 10 minutes and relabels the final segments; the after-stop run is always performed and wins. Cost estimate for a 2h call: ~13 runs over growing audio, about 11% of one core on average.

Voice fingerprints: `Person.voiceprint` and `Speaker.embedding` gain a `voiceprint_model` tag; the migration clears pyannote-era fingerprints once (People, names, and links stay). Matching only compares fingerprints with the same tag. SpeakerKit v1.1.0 exposes `DiarizationResult.speakerCentroidEmbeddings: [Int: [Float]]` (per-speaker centroids, raw embedder space, filled by its pyannote-based backend), so voice matching keeps working; the match threshold (`voice_match_threshold`) must be recalibrated for these embeddings (task 8.5).

*Alternatives:* keep pyannote (10x slower, ~485 MB of torch, token needed); the ONNX port planned in `production-hardening` (more work, no measured gain over SpeakerKit).

### D12. Privacy
All speech work (captions, draft, final) runs on the Mac; audio and text never leave it. Network use is limited to model downloads (Hugging Face for WhisperKit/faster-whisper weights, Apple for the caption asset). Logs keep today's rule of not logging transcript text; helper errors are logged without audio or text.

## Risks / Trade-offs

- [Turbo quality measured on one 10-minute clip] → validation task on 3 full recordings: compare words per window against faster-whisper `large-v3` and flag any window with >10% fewer words (dropped passage); keep `faster-whisper` selectable in Settings.
- [WhisperKit VAD chunking dropped passages with full large-v3] → same per-window word-count check; fall back to `chunkingStrategy: none` inside the helper if drops show up.
- [Helper crash mid-job] → restart once and retry the window; on second failure finish remaining windows with faster-whisper and record a note.
- [Captions/draft need macOS 26] → feature shown as unavailable; final pass unaffected.
- [Speech framework permission in the packaged app] → probe in the signed app early (task 1.x); add the usage-description key if macOS asks for one.
- [Draft text is worse (~11% diff, fillers, names)] → clearly marked as draft; never used for summary/Q&A.
- [Captions add load during calls] → measured ~2.5% of one core; bounded queue drops caption audio under load; off by default.
- [Finalizer and a queued job compete for the helper] → single request lock; the live boundary may lag during a backlog and catches up after stop.
- [Window cut without a common silence] → falls back to a single-track silence; a word spoken across the cut on the other track can be split → mitigate by choosing the cut in the track with less speech near the target and accepting a rare split.
- [Bundle signing] → new helper signed like `system-audio-capture`; WhisperKit links only Apple frameworks.

## Migration Plan

1. Additive `Segment.is_draft` column (default false); existing transcripts are final.
2. Settings: `mlx` engine value read as `auto`; new settings get defaults (captions off, window 180 s, WhisperKit model id).
3. First launch after update: model manager shows WhisperKit model "not installed"; the first job downloads it (or the user installs it in Settings) and falls back to faster-whisper until then.
4. Rollback: set engine to `faster-whisper` and captions off; drafts are only written when the helper is present.

## Decisions from review (Stefan, 2026-10-06)

- "Transcribe during recording" defaults to **on** when WhisperKit is available; task 7.7 still measures a real call before release.
- Cadence: steady ~3-minute windows (not 10-minute bursts).
- On battery: keep running; pause while Low Power Mode is on, catch up afterwards.
- Speaker splitting: switch to SpeakerKit (tested: 11x faster, ~94% agreement). When: setting, default once after stop; option to also split during recording.
- Voice fingerprints: re-learning after the switch is acceptable.

## Open Questions

- Does the packaged app need a Speech usage description for SpeechTranscriber on macOS 26? Verified in task 2.7.
