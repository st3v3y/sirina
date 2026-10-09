## 1. Spike (gates everything below)

- [ ] 1.1 Find the Hugging Face repo (or a GitHub release mirror) for the sherpa-onnx Parakeet TDT 0.6B v3 int8 export; note its size; check whether sherpa-onnx's `VoiceActivityDetector` accepts faster-whisper's bundled `silero_vad_v6.onnx`
- [ ] 1.2 Under `scripts/spikes/parakeet/`, run final transcription of the 10-minute rec 13 clip at 4 and 6 threads, with VAD from `speech_regions`; record wall time, CPU-seconds, peak RSS and word diff against WhisperKit turbo and faster-whisper turbo; add one German and one English sample
- [ ] 1.3 Compare 3-minute windows with 15 s VAD chunks on the same clip (G4 input); check that word timestamps assembled from tokens line up with the audio
- [ ] 1.4 Run the hotword test with 10 People names, with and without hotwords (`modified_beam_search`)
- [ ] 1.5 Prototype the caption worker (re-decode the open VAD segment every ~0.5 s, settle at the VAD end or 15 s); replay mic and system in real time as two processes; record provisional and settled latency (p50 and p90), CPU and RSS on the Mac
- [ ] 1.6 Add a manual-dispatch CI job that runs 1.2 and 1.5 on `windows-latest` and `ubuntu-22.04` (x64 reference)
- [ ] 1.7 Write `spike-results.md` in this change with the numbers and the G1–G4 verdicts; set the `PARAKEET_CAPTIONS` and `PARAKEET_LIVE` build defaults per platform; amend the specs if G4 passes or G1 fails, and re-run `openspec validate`

## 2. Parakeet engine

- [ ] 2.1 Add the `sherpa-onnx` dependency (pyproject and uv.lock); add the `collect_dynamic_libs` and `collect_data_files` hooks to `backend.spec`
- [ ] 2.2 Add `transcribe/parakeet.py` with `ParakeetEngine` (`load`, `is_loaded`, `transcribe_window`, `transcribe_file`, `model_ids`):
  - a single worker thread and lock, like `FasterWhisperWorker`
  - `load_wav_16k` for the slice, `speech_regions` for VAD
  - segments capped per the spike, decoded as a batch
- [ ] 2.3 Write the pure token-to-word fold (`▁` marks a word start) using `make_word` and `line_from`, with absolute times; table-test it with token and timestamp fixtures, including an empty window and a single token
- [ ] 2.4 Add the `PARAKEET_LANGUAGES` constant; return the configured language or None
- [ ] 2.5 Pass hotwords from `whisper_initial_prompt` when supported (per the spike), otherwise ignore them
- [ ] 2.6 Register the Parakeet `ModelSpec` (engine `parakeet`), plus the Silero `ModelSpec` only if 1.1 found the bundled file incompatible

## 3. Engine selection, fallback and model manager

- [ ] 3.1 Extract a pure `choose_engine(choice, platform, caps, language, sherpa_ok) -> (name, note)`; `select_engine()` only instantiates; table tests in `test_whisperkit_engine.py` (or a new `test_engine_select.py`) for every branch, including an unsupported language, Parakeet failing to load, and `mlx` → `auto`
- [ ] 3.2 `processing/job.py`: in `_ready_engine()` and `_transcribe_with_fallback()`, fall back to CPU for any engine other than faster-whisper, and show "preparing model" for Parakeet too; extend `test_progress_job.py` with a Parakeet load failure that falls back
- [ ] 3.3 `speech_models.in_use_ids()` comes from the active engine's `model_ids()`; the faster-whisper entry follows `whisper_model` (`Systran/faster-whisper-<model>`); extend `test_speech_models.py`: `medium` is in use, not listed as unused, and deletion is refused while busy
- [ ] 3.4 Add `parakeet` to the engine setting options; update the Settings `HELP_HINTS` text; vocabulary-hint help says "Whisper engines only" when Parakeet is active and hotwords aren't supported
- [ ] 3.5 `/api/_debug/transcribe-wav`: use `transcribe_window` instead of the faster-whisper-only `transcribe()`
- [ ] 3.6 Frontend: Parakeet appears in the model manager; the model text no longer depends on the engine

## 4. Captions on Parakeet

- [ ] 4.1 Add `recording/caption_worker.py` implementing the `speech-engine captions` stdin/stdout protocol (provisional and settled JSON lines, settle at 15 s, settle on EOF); unit-test the segmenter logic with synthetic VAD events
- [ ] 4.2 `packaging/entry.py`: dispatch `--worker captions` before argparse; dev command `python -m app.recording.caption_worker`; verify in the frozen build
- [ ] 4.3 `CaptionStream` takes a base `argv` instead of `helper_path`; update `test_captions_stream.py` to pass the fixture command directly
- [ ] 4.4 Add `captions_provider()` (Apple → Parakeet worker when the `PARAKEET_CAPTIONS` flag is on and the models are installed → unavailable with a reason); it feeds the existing `captions_available` and `captions_reason` fields; table-test the provider order
- [ ] 4.5 "Too slow": a rolling drop ratio in `CaptionStream` (more than 5% over 60 s) → `failed` with the reason `too_slow` in `snapshot()`, plus a runtime flag for later start dialogs; tests for the threshold and for capture never blocking
- [ ] 4.6 Frontend: the start dialog and the recording screen show `captions_reason`, and the "Captions stopped" line shows the stop reason

## 5. Transcription during recording on Parakeet

- [ ] 5.1 `live_transcription_available()` returns `(ok, reason)`, accepts Parakeet only when the `PARAKEET_LIVE` flag is on, and never faster-whisper; it feeds the `live_transcribe_reason` field
- [ ] 5.2 `power_state().low_power`: Windows Battery Saver (`GetSystemPowerStatus`), Linux `powerprofilesctl get` = power-saver, off when unreadable; table tests with mocked readers; the "Paused while Low Power Mode is on" text in `RecordingScreen.tsx` is worded per platform
- [ ] 5.3 Extend `test_live_finalizer.py` with a fake Parakeet engine (windows committed, engine shared with a queued job through its lock)
- [ ] 5.4 If G4 passed (per the amended specs): store settled Parakeet captions as final segments, and have the finalizer skip spans the captions already settled

## 6. GPU acceleration pack

- [ ] 6.1 Add an installer strategy to `ModelSpec`: `HfSnapshot` (existing) and `WheelLibs`, each with its own installed check; existing tests stay green unchanged
- [ ] 6.2 `WheelLibs` for the `gpu-pack` (Windows and Linux only):
  - pinned `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` wheel URLs with sha256 values hard-coded in the app
  - verify before extracting; extract only the DLLs or `.so` files into `<data>/cuda/`; write the manifest last
  - reuse the progress and retry handling
  - tests: checksum mismatch, truncated download, interrupted extract
- [ ] 6.3 Load: `select_engine()` prepares the libraries before importing faster-whisper (Windows `add_dll_directory` and PATH; Linux `ctypes` RTLD_GLOBAL preload); if `get_cuda_device_count() > 0`, load on `cuda` with the pure `cuda_compute_type()`; otherwise fall back to CPU and record the reason
- [ ] 6.4 Add `engine_device` to the status and show it in Settings; refuse to delete the pack during a job; show the licence notice in the model manager
- [ ] 6.5 Tests: `cuda_compute_type` table, the CPU fallback when no device is found or loading fails (ctranslate2 mocked), the pack hidden on macOS

## 7. Packaging, docs and verification

- [ ] 7.1 Frozen-boot smoke test in CI on all three platforms: load Parakeet and faster-whisper in one process (two onnxruntime copies) and start the caption worker once
- [ ] 7.2 Measure the bundle-size growth and record it in `docs/PACKAGING.md`; update the README support matrix (engines, captions and GPU pack per platform)
- [ ] 7.3 Manual check on a real Windows laptop: Parakeet final transcript, captions (if shipped) on a live call, Battery Saver pausing live work, the GPU pack on an NVIDIA machine if one is available
- [ ] 7.4 macOS regression: the `auto` engine still picks WhisperKit, Apple captions are unchanged, the Parakeet engine is selectable and works, the model manager shows the right model in use
- [ ] 7.5 Run `uv run pytest`, `npm run lint` and `npm run build`
