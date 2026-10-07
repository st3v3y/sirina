## 0. Decision gate (before implementation)

- [x] 0.1 Compare WhisperKit SpeakerKit with pyannote on the benchmark clip and one full recording (speaker count, agreement, time, CPU, memory); decide whether speaker splitting moves to SpeakerKit and/or runs during recording; update this change accordingly
- [x] 0.2 Check that SpeakerKit's Swift API returns per-speaker embeddings usable for voice matching; record the answer in design D14

## 1. Quick wins (no quality change)

- [x] 1.1 Default faster-whisper `cpu_threads` to the performance-core count (`sysctlbyname("hw.perflevel0.physicalcpu")`, fallback `os.cpu_count()`); keep an explicit setting as override; unit-test the resolver
- [x] 1.2 Replace the recorder-owned `SleepBlocker` with a reference-counted `PowerGuard` in `app/audio/power.py`; recorder holds a reference while recording, the job takes one at enqueue and releases it when the job ends (ready / failed / stopped); tests for refcount and no gap at the stop→job handoff
- [x] 1.3 Add `power_state()` (`pmset -g batt` + `pmset -g` lowpowermode, cached 30 s) and a `power_note` in progress while on battery or Low Power Mode; show it in the processing banner in `RecordingDetail.tsx`
- [x] 1.4 Verify on the benchmark clip that 6 threads gives identical text to 8 threads in the app path (verified in the 2026-10-06 benchmark: 1225/1225 words identical; no automated test, since it needs the 3 GB model)

## 2. Native speech helper (`native/speech-engine`)

- [x] 2.1 Create the SwiftPM package depending on Argmax's open-source WhisperKit pinned to a tagged 1.x release; `--probe` prints capabilities (WhisperKit OK, SpeechTranscriber supported, macOS version)
- [x] 2.2 Implement `serve` mode: JSON-lines loop with `load {model_dir}`, `transcribe {path,start_s,end_s,language?,prompt?}` (reads the WAV slice itself, word timestamps, absolute times), `status`; errors returned as `{error}` lines, never crash the loop
- [x] 2.3 Implement `draft {path,start_s?,end_s?}` with SpeechTranscriber offline (absolute times; settled results only)
- [x] 2.4 Implement `captions --sample-rate 48000`: s16le PCM on stdin → resample to the analyzer format → provisional/settled JSON lines on stdout; exit cleanly on EOF
- [x] 2.5 `build.sh` for the package; extend `scripts/build-macos-app.sh` to build, copy to `resources/speech-engine`, and codesign it like `system-audio-capture`; add it to `tauri.conf.json` resources
- [x] 2.6 Smoke-test script for the helper (probe, `transcribe` on a 30 s fixture with word times, `draft`, `captions` on a PCM fixture, malformed request returns `{error}`), run by the build script
- [ ] 2.7 Probe the signed packaged app on macOS 26: WhisperKit loads, SpeechTranscriber runs without a permission failure (add a usage-description key if required)

## 3. Speech model manager

- [x] 3.1 `app/speech_models.py`: registry (WhisperKit `openai_whisper-large-v3-v20240930_626MB`, faster-whisper `large-v3`, Apple caption/draft asset), install status from expected files, size on disk, in-use flag
- [x] 3.2 Background install via `huggingface_hub.snapshot_download` (allow patterns per model) into `models/hf` with progress; partial downloads never count as installed; Apple asset install via the helper
- [x] 3.3 API: `GET /api/models`, `POST /api/models/{id}/install`, `DELETE /api/models/{id}` (refused for the in-use model while a job runs); tests
- [x] 3.4 Settings UI section: list with size/status/in-use, install with progress, delete with confirmation, retry on failure

## 4. WhisperKit engine and selection

- [x] 4.1 `app/transcribe/whisperkit.py`: `WhisperKitEngine` owning the helper subprocess (start on `load`, restart once on crash), implementing `TranscriptionEngine` plus `transcribe_window(path,start_s,end_s,...)`
- [x] 4.2 Add `transcribe_window` to `FasterWhisperWorker` (slice audio, batched pipeline, offset times) and to the `TranscriptionEngine` protocol
- [x] 4.3 Update `select_engine()`: `auto | whisperkit | faster-whisper`; map stored `mlx` to `auto`; record the fallback reason in `runtime.engine_note`; update `settings_store` options; reuse `transcribe_chunk_seconds` (180) as the window length (no separate WhisperKit model setting: one model)
- [x] 4.4 First-run: if the WhisperKit model is missing, download it in the job (stage `preparing_model`), report the one-time Neural Engine preparation, fall back to faster-whisper on failure; warm the model in the background after install
- [x] 4.5 Engine tests with a fake helper (JSON-lines stub): window offsets, crash + restart, fallback after second failure

## 5. Draft/final data model and windowed job

- [x] 5.1 Additive columns: `Segment.is_draft` (default false), `Segment.words` (JSON, final rows), `Recording.final_until_s`; migration in `db.py`; expose `is_draft` and `final_until_s` in the recording API
- [x] 5.2 `app/processing/windows.py`: VAD speech regions per track (faster-whisper's Silero VAD) and the pure cut-point chooser (common silence ≥0.5 s within ±30 s of each target, else single-track silence); table tests with synthetic regions
- [x] 5.3 `finalize_range(recording, from_s, to_s, engine)` in `windows.py`: per window transcribe each track, then one transaction deleting draft rows starting in the window, inserting resegmented final rows with `words`, and storing `final_until_s`; speaker rows created lazily per track and reused
- [x] 5.4 Rewrite the transcription stage of `_process` to call `finalize_range` from the stored `final_until_s` (or 0) to the end (language detected on the first window with speech, reused after); keep silent-track skipping and cancellation between windows
- [x] 5.4a Diarization stage rebuilds each track's `TLine`s with words from stored final segments (system track for `diarize_lines`, mic track as echo reference) instead of in-memory lists
- [x] 5.4b Reprocess endpoint clears segments, speakers, and `final_until_s` before enqueueing
- [x] 5.5 Draft at stop: insert caption drafts only after `final_until_s`; for ranges still without drafts run helper `draft` per non-silent track (stage `drafting`) before the first window; skip when unsupported
- [x] 5.6 Remove the MLX-only chunking path from the job (engine no longer owns windows); `mlx.py` and its settings deleted (packaging flag removed with 8.3)
- [x] 5.7 Segment readers: summary (`pipeline.py`) and exports (`exporters.py`) use final rows only; Q&A includes drafts labelled as draft in the prompt; speaker sampling may use both
- [x] 5.8 Tests: windowed faster-whisper output equals whole-file output on a short fixture; commit leaves no draft/final overlap; stop-midway → `ready` with finals + drafts and no summary from drafts; restart resumes from `final_until_s`; diarization after restart uses stored words; reprocess rebuilds from 0

## 6. Live captions

- [x] 6.1 Settings: `live_captions` (default off), shown disabled with a reason when the helper reports no support
- [x] 6.2 Recorder: per-track bounded queue + writer thread teeing PCM blocks to a `speech-engine captions` process; drop on full; reader thread fills an in-memory caption buffer; helper exit stops captions without affecting capture
- [x] 6.3 Active-recording API returns latest provisional + recent settled captions per track; at stop, bulk-insert settled captions as draft segments
- [x] 6.4 Recording screen: caption panel with "You" / "Others" lines, provisional text styled lighter; `useRecorder` polls at 0.5 s when captions are on; "captions stopped" notice
- [ ] 6.5 Measure on the reference Mac: caption latency (<2 s provisional, <3 s settled incl. polling) and CPU of the helper (<10% of one core); recorded files identical in length with captions on/off

## 7. Transcribe during recording

- [x] 7.1 `Recording.live_transcribe` / `Recording.live_captions` columns (additive migration); Settings defaults `live_transcribe_default` (on when WhisperKit is available) and `live_captions_default` (off)
- [x] 7.2 Start dialog: two per-recording toggles pre-set from Settings, disabled with a reason when unavailable; pass them to `POST /api/recordings/start`
- [x] 7.3 Recording screen toggles + `PATCH /api/recordings/active` to change them mid-recording (on → catch up from last final point; off → stop after the current window)
- [x] 7.4 `LiveFinalizer`: frame-count check every 15 s; calls `finalize_range` for the next window once both tracks are ≥30 s past the target cut and ≥2 s behind the written frames; WhisperKit only; shares the helper request lock with jobs; never blocks capture; helper failure leaves the rest for after stop
- [x] 7.4b Pause the finalizer while Low Power Mode is on (power state from 1.3), show "paused" on the recording screen, resume and catch up afterwards; test with a stubbed power state
- [x] 7.4a `Recorder.stop` cancels and awaits the finalizer before returning (in-flight window committed or redone after stop); test with a slow fake helper
- [x] 7.5 Job starts from `final_until_s` when live windows exist; tail + diarization + summary only
- [x] 7.6 `apply_trim`: shift all segments and `final_until_s` by `-start_s`, delete segments starting outside the kept range; test
- [ ] 7.7 Measure during a real call: CPU/ANE load of the helper, no audio glitches, final boundary stays within ~4 min of the live edge

## 8. Speaker splitting with SpeakerKit

- [x] 8.1 Helper `diarize {path,end_s?}` → turns + per-speaker embeddings; smoke test on a fixture
- [x] 8.2 Replace `Diarizer` (pyannote) with a SpeakerKit client returning the same `DiarizationResult`; keep pruning and echo suppression; fall back to the baseline split with a note when unavailable
- [x] 8.3 Remove pyannote/torch/torchaudio from dependencies, `backend.spec`, and the `--diarization` build variant; drop the HF-token requirement and its Settings text; mark `production-hardening` 4.2–4.5 as superseded there
- [x] 8.4 Add the SpeakerKit model to the model manager registry
- [x] 8.5 Voiceprint migration: add `voiceprint_model` tags, clear pyannote-era `Person.voiceprint`/`voiceprint_n` and `Speaker.embedding`/`enrolled` once, compare only same-tag fingerprints; recalibrate `voice_match_threshold` for SpeakerKit centroids; tests
- [x] 8.6 Setting `diarization_timing` (`after_stop` default, `during_recording`); with `during_recording` the live finalizer re-splits about every 10 min and relabels final segments; after-stop run always happens; test with a fake helper
- [ ] 8.7 Measure on 2 full recordings: time, memory, speaker counts vs the old pyannote results stored in the app

## 9. Transcript view

- [x] 9.1 Render draft lines muted with a "draft" marker; boundary moves as polling returns new finals
- [x] 9.2 Speaker rename during processing shows on draft and final lines and survives later window commits (test)
- [x] 9.3 Show `preparing_model`, `drafting`, and `power_note` in the processing banner

## 10. Validation

- [ ] 10.1 Run the new pipeline on 3 full recordings (incl. the 2h+ ones); compare words per window with faster-whisper `large-v3`; investigate any window with >10% fewer words; tune helper chunking if passages drop
- [ ] 10.2 Time a 1h two-track recording end to end on AC (target: final transcript under ~10 min) and on battery with Low Power Mode (note shown, guard holds)
- [ ] 10.3 Packaged-app check: bundle size delta (target: a few MB), fresh install downloads the model once, offline first run falls back with a retry, captions off by default, no pyannote/torch in the bundle
- [x] 10.4 Update docs (`docs/PACKAGING.md`, README) for the new helper, model manager, captions, SpeakerKit, and removal of the `--diarization` variant
