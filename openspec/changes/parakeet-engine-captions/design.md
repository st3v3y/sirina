## Context

The backend sits behind one `TranscriptionEngine` protocol (`transcribe/engine.py`). WhisperKit runs out of process through the Swift speech helper. `FasterWhisperWorker` runs in process on the CPU (`device="cpu"` is hard-coded). `select_engine()` picks WhisperKit only on Apple Silicon with the helper, and faster-whisper otherwise.

Speech features are switched on separately:
- **Captions**: `captions_available()` requires the helper's `apple_speech` probe flag. `CaptionStream` starts `speech-engine captions`: 48 kHz s16le PCM goes in on stdin, and JSON lines `{"kind":"provisional"|"settled","start","end","text"}` come out on stdout.
- **Transcription during recording**: `live_transcription_available()` requires the active engine to be WhisperKit.
- **Instant draft after stop**: `transcribe/draft.py` returns None without `apple_speech`.

Reference numbers from 2026-10-06 (M1 Pro, 10-minute dense clip from rec 13):

| Engine | Time | Memory | Notes |
|---|---|---|---|
| WhisperKit turbo | 59 s | 0.4 GB | ~1.6% estimated real errors |
| faster-whisper turbo, CPU | 52 s | 6.7 GB | ~2.9% estimated real errors; drops phrases |
| Apple captions | 0.1 s provisional / 0.8 s settled latency | – | ~2.5% of one core |

The development machine is an Apple Silicon Mac. sherpa-onnx and Parakeet run on macOS too, so most of this change can be built and measured there. x64 reference measurements come from GitHub-hosted Windows and Linux runners.

## Goals / Non-Goals

**Goals:**
- A fast, CPU-only default engine for Windows and Linux (and an option on macOS), behind the existing interface.
- Near-real-time captions outside macOS 26, or a clear explanation of why they are off.
- Transcription during recording on Parakeet if it is light enough.
- Opt-in CUDA acceleration for faster-whisper with nothing CUDA-related bundled.
- Decisions backed by measured numbers, not assumptions.

**Non-Goals:**
- Speaker splitting on Windows and Linux (sherpa-onnx diarization is a later change).
- GPU acceleration for Parakeet (CUDA or DirectML onnxruntime).
- AMD and Intel GPU support for faster-whisper.
- Replacing WhisperKit or Apple captions on macOS.
- A language detector for Parakeet recordings.

## Decisions

### D1. A spike gates the change, with decision rules fixed in advance

The spike is a script under `scripts/spikes/parakeet/`. It is not shipped, and its results are recorded in `spike-results.md` in this change.

**Workloads:**
- **Final transcription.** The 10-minute rec 13 clip, through Parakeet int8 at 4 and 6 threads. Measure wall time, CPU-seconds, peak RSS and word diff against WhisperKit turbo and faster-whisper turbo. Use the same "estimated real errors" method as 2026-10-06, with Apple's transcript as tiebreaker. Run on a German and an English sample.
- **Windows of 3 minutes.** Transcribe the clip as 3-minute windows with VAD, and separately as VAD chunks capped at 15 s. Compare the two outputs.
- **Captions.** Replay mic and system tracks in real time through the caption worker prototype (D3) as two processes at once. Measure provisional and settled latency (p50 and p90), average CPU and peak RSS.
- **Hotwords.** Feed 10 names from the People directory as hotwords and count recognized occurrences against the run without them.
- **x64 reference.** Run the caption and final workloads in a manual-dispatch CI job on `windows-latest` and `ubuntu-22.04` (4 vCPU).

**Decision rules:**

| Gate | Pass criteria | If it fails |
|---|---|---|
| **G1** Parakeet becomes the default engine | estimated real errors ≤ faster-whisper turbo's on both languages, **and** wall time ≤ 50% of faster-whisper turbo on the same machine, **and** peak RSS ≤ 2 GB | Keep faster-whisper as the default. Parakeet is still offered, and this change is re-scoped |
| **G2** Parakeet captions ship on a platform | on that platform's x64 runner, two streams give provisional p90 ≤ 2 s, settled p90 ≤ 3 s and average CPU ≤ 1 core in total, with no queue overflow over 10 minutes | Captions stay disabled on that platform with the "not available on this platform yet" reason |
| **G3** Parakeet qualifies for transcription during recording | one 3-minute window of both tracks finishes in ≤ 30 s on the x64 runner with ≤ 2 threads, while G2 captions run at the same time | `live-transcription` stays WhisperKit-only |
| **G4** Settled captions become final segments | word diff between 15 s VAD chunks and 3-minute windows ≤ 0.5 percentage points of estimated real errors | Keep both passes: captions become drafts and windows become final, as on macOS |

If G4 passes, the specs are amended before implementation:
- settled Parakeet captions are stored as final segments
- the live finalizer skips spans that captions already settled

**Alternatives considered:**
- Adopt Parakeet without measuring. It was rejected: the 2026-10-06 round showed that engines differ in surprising ways (WhisperKit large-v3 dropped whole passages).
- Benchmark only on the Mac. It was rejected: Apple Silicon flatters CPU inference, while the target hardware is ordinary x64 laptops.

### D2. The Parakeet engine runs in process through sherpa-onnx

- **Class:** `transcribe/parakeet.py` → `ParakeetEngine`. It uses `sherpa_onnx.OfflineRecognizer.from_transducer(...)` with the NeMo transducer model type, int8 weights and `num_threads = default_cpu_threads()`. One worker thread runs it, the same pattern as `FasterWhisperWorker`.
- **`transcribe_window`** reuses existing seams:
  1. Read the slice with `audio/wav.load_wav_16k(path, start_s, end_s)`, which returns mono 16 kHz float32.
  2. Find speech with `processing/windows.speech_regions`, the Silero VAD bundled with faster-whisper. Every engine already uses it, so no extra VAD model is downloaded. Merge and split the regions into segments of at most 15–30 s; the spike picks the cap.
  3. Decode the segments as a batch with `decode_streams`.
  4. Build `TLine`s with the existing `make_word` and `line_from` helpers in `transcribe/whisper.py`: one line per segment, with words assembled from token timestamps, where the SentencePiece `▁` prefix marks the start of a word. The token-to-word fold is a pure function, so it can be table-tested.
  5. Offset all times by the window start.
- **`transcribe_file`:** loops windows (`streams_progress=False`), so the existing chunked-progress requirement applies unchanged.
- **Language:** the engine returns `(lines, configured_language or None)`. The constant `PARAKEET_LANGUAGES` (ISO 639-1 codes) lives next to the engine.
- **Hotwords:** passed through sherpa-onnx's hotwords option with `modified_beam_search` if the spike's hotword measurement shows it works for this model type. Otherwise the engine ignores the hints and the Settings help text says so.

*Alternatives considered:*
- **onnx-asr** or **NeMo**. NeMo pulls in torch, which was removed from the bundle on purpose. onnx-asr is lighter but has no VAD or streaming tooling.
- **A Rust or C++ helper.** Rejected in exploration: it adds a third native codebase, and the protocol gives no benefit when Python can call sherpa-onnx directly.

### D3. The caption worker re-runs the frozen backend as a subprocess

- **Entry point:** `app/recording/caption_worker.py`. `packaging/entry.py` currently only parses `--host` and `--port` with argparse, which would reject other arguments. So it checks for `--worker` before argparse runs and dispatches to the worker. In development the worker runs as `python -m app.recording.caption_worker`.
- **Arguments:** the same as `speech-engine captions`: `--sample-rate`, `--language`, `--prompt`.
- **Loop:**
  1. Read stdin PCM and resample to 16 kHz with `audio/wav.resample_to_16k`.
  2. Feed sherpa-onnx's streaming `VoiceActivityDetector`. It is pointed at the Silero model file that ships with faster-whisper if the spike shows that file is compatible; otherwise the small `silero_vad.onnx` (~2 MB) is downloaded alongside the Parakeet model.
  3. While speech is active, re-decode the open segment every ~0.5 s and emit `provisional`.
  4. When VAD closes the segment, or it reaches 15 s, decode once more and emit `settled`.
  5. On EOF, settle what remains and exit.
- **Process model:** one process per track, as on macOS today.
  - `CaptionStream` currently hard-codes `[helper_path, "captions", …]`. It instead takes a base command (`argv: list[str]`): `[helper, "captions"]` for Apple, and `[sys.executable, "--worker", "captions"]` for the frozen worker. The flags are appended as today.
  - The test fixture passes its own command directly, with no shell wrapper.
- **Why a separate process:** decoding is CPU-bound and would compete for the GIL with the capture threads. A crash must not touch recording; the "Captions stay light" requirement already demands a separate process.
- **Provider:** `captions_provider()` replaces `captions_available()`. It returns either `(argv_builder, None)` or `(None, reason)`, in this order:
  1. the Apple helper if the probe shows `apple_speech`
  2. the Parakeet worker if this build ships it (`PARAKEET_CAPTIONS` in the build config, set per platform from G2) and its models are installed
  3. otherwise, unavailable with a reason
- **Reason fields:** `cross-platform-recording` adds `captions_reason` and `live_transcribe_reason` to the capabilities. This change only changes how they are computed.
- **"Too slow" detection:** `CaptionStream` already counts `dropped_blocks` but doesn't expose them. It gains a rolling drop ratio. If more than 5% of blocks are dropped over 60 s, it stops itself with `failed` and the reason `too_slow`, and `snapshot()` carries the reason. The existing "Captions stopped (the recording continues)" line on the recording screen then shows "this computer is too slow for live captions". A runtime flag remembers it until the app restarts, so the next start dialog explains why the option is off.

*Alternatives considered:*
- **One worker for both tracks.** It halves model memory but needs a multiplexed protocol and a new `CaptionStream`. Revisit if the spike shows two processes over ~2.5 GB RSS.
- **A true streaming model** (Zipformer or Nemotron streaming, English only). Lower CPU, but it only covers English while the user records German. Kept as a fallback candidate in the spike for an English-only caption mode if G2 fails.

### D4. Engine selection order

`select_engine()` with `auto`:
1. WhisperKit, if available (unchanged).
2. Parakeet, if the configured language is empty or in `PARAKEET_LANGUAGES` and `sherpa_onnx` imports.
3. faster-whisper.

`select_engine()` today sends every value except `faster-whisper` down the WhisperKit path, so it is restructured:
- A pure `choose_engine(choice, platform, caps, language, sherpa_ok) -> (name, note)` makes the decision and is table-tested.
- `select_engine()` only instantiates the result.
- An explicit `parakeet` falls back to faster-whisper with a recorded note if sherpa-onnx fails to load.

**Fallback during a job.** `_ready_engine()` and `_transcribe_with_fallback()` currently fall back to the CPU engine only for WhisperKit (`if not is_wk: raise`). Without a change, a failed Parakeet download would fail the job. Both checks become "any engine other than faster-whisper", and the "preparing model" progress stage also shows while Parakeet downloads.

**Model manager.** `speech_models.in_use_ids()` hard-codes model ids by engine name. It also marks `faster-whisper-large-v3` as in use, while the default `whisper_model` is `medium`: the model actually in use is listed as "No longer used" and can be deleted without any check. Since this change adds Parakeet and makes faster-whisper the fallback everywhere, the refactor is in scope:
- Each engine declares `model_ids()`, and `in_use_ids()` reads it.
- The faster-whisper entry is built from the configured `whisper_model` (`Systran/faster-whisper-<model>`).

**Other wiring:**
- Settings gains `parakeet` in the engine options. The Settings UI renders enum options from backend metadata, so only `HELP_HINTS` text changes.
- `live_transcription_available()` returns a reason and accepts Parakeet only when the `PARAKEET_LIVE` build flag (from G3) is on.
- The debug endpoint `/api/_debug/transcribe-wav` calls `runtime.whisper.transcribe()`, which only faster-whisper has. It is already broken on WhisperKit, so it switches to `transcribe_window`.

**Low-power detection.** Transcription during recording pauses in Low Power Mode. Today that is only detected on macOS (through `pmset`), so live work on a Windows or Linux laptop would never pause. `power_state().low_power` gains:
- **Windows:** Battery Saver (`GetSystemPowerStatus().SystemStatusFlag`).
- **Linux:** the power-saver profile of power-profiles-daemon (`powerprofilesctl get`), if it is installed.

### D5. The GPU pack is NVIDIA's own wheels, downloaded into the data directory

The Windows and Linux PyPI wheels of `ctranslate2` that faster-whisper uses are built with CUDA 12. They need cuBLAS 12 and cuDNN 9 at runtime.

- **Install:**
  - The model manager can only download Hugging Face snapshots today, and decides "installed" from the HF cache layout. So `ModelSpec` gains an installer strategy, which keeps it open for extension without touching the HF path:
    - `HfSnapshot` is the existing behaviour.
    - `WheelLibs` is new. Its "installed" check reads a manifest, not the HF cache.
  - `WheelLibs` does this:
    1. It downloads pinned wheels of `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` (`win_amd64` or `manylinux…x86_64`) from `files.pythonhosted.org`. The versions match what the bundled ctranslate2 4.7 expects: CUDA 12 and cuDNN 9.
    2. It verifies each wheel against a **sha256 hard-coded in the app**, not one taken from the index response. The DLLs are loaded into the backend process, so a swapped file must not get in.
    3. It extracts only the `bin/*.dll` or `lib/*.so*` files into `<data>/cuda/` and writes the manifest last, so a partial install never looks complete.
    4. It reuses the existing progress and recoverable-failure handling.
- **Load:** `select_engine()` prepares the libraries before it imports the faster-whisper module. That way it doesn't matter whether ctranslate2 resolves the CUDA libraries at import time or on first use:
  - **Windows:** `os.add_dll_directory(<data>/cuda)` and prepend the folder to `PATH`.
  - **Linux:** preload the libraries in dependency order with `ctypes.CDLL(..., RTLD_GLOBAL)`.
  - **Both:** if `ctranslate2.get_cuda_device_count() > 0`, create `WhisperModel(device="cuda", compute_type=...)`. Otherwise, or on any exception, use CPU and record the reason.
- **Compute type:** a pure `cuda_compute_type(setting)` function. The CPU default `int8` maps to `int8_float16`; any other value the user chose is kept.
- **Device in status:** the status gains `engine_device` (`cpu` | `cuda`) next to `engine_note`, and Settings shows it.
- **Licensing:** the files are NVIDIA's redistributable runtime, fetched from NVIDIA's PyPI packages by the user's own action. The model manager shows a one-line licence notice with a link.

*Alternatives considered:*
- **A separate "CUDA build" of the app.** Doubles CI and distribution for a minority of users.
- **Requiring a system CUDA toolkit install.** Users can't do it reliably, and versions mismatch.

### D6. Packaging

- `backend.spec` collects `sherpa_onnx` with `collect_dynamic_libs` and `collect_data_files`.
- sherpa-onnx ships its own onnxruntime next to the `onnxruntime` package that faster-whisper's VAD uses. The frozen app must load both without symbol clashes; this is verified on all three platforms in CI with a frozen-boot smoke test that loads both engines.
- Bundle growth is measured and recorded in `docs/PACKAGING.md`.

## Risks / Trade-offs

- **Parakeet is weaker on names and jargon, and has no prompt.** → The hotword test in the spike, faster-whisper staying one click away, and Settings explaining that hints are Whisper-only if needed.
- **Parakeet drops filler words and code-switches oddly in mixed German and English.** → Measured in the spike on both languages. A G1 failure keeps faster-whisper as the default.
- **Re-decoding for captions costs CPU on weak laptops.** → G2 with a measured CPU budget, "too slow" detection that stops captions with a message, and captions off by default.
- **Memory with three Parakeet instances** (two caption workers plus the in-process engine during recording). → Measured in the spike. G4 passing removes the in-process live pass. A shared caption worker is the fallback design.
- **Two onnxruntime copies in one process.** → Frozen-boot smoke test per platform. If they clash, run Parakeet final transcription in the worker process too, through the same `--worker` entry.
- **The CUDA libraries are large (~1.5 GB) and need a recent NVIDIA driver.** → Optional download, clear size, CPU fallback with the reason shown.
- **The spike reference runner (4 vCPU cloud VM) isn't a real laptop.** → Treat its numbers as a lower bound and confirm on one real Windows laptop before shipping captions there.

## Migration Plan

- Existing installs keep their `transcription_engine` setting. `auto` on macOS Apple Silicon is unchanged. On Intel Macs and Windows/Linux, `auto` moves from faster-whisper to Parakeet after the upgrade, and the Parakeet model downloads on first use.
- No database changes. Transcripts produced by different engines coexist.
- Rollback: set the engine to `faster-whisper`, or ship builds with `PARAKEET_CAPTIONS` and `PARAKEET_LIVE` off.

## Open Questions

- Which exact Hugging Face repo hosts the sherpa-onnx Parakeet v3 int8 export and the Silero VAD (the model manager downloads from HF)? The spike confirms it, with a GitHub release mirror as fallback.
- Should the macOS `auto` order put Parakeet ahead of faster-whisper for Intel Macs or a missing helper? The current rule in D4 already does. Confirm it is wanted.
- Should Parakeet captions also be offered on macOS older than 26? Technically yes, through the same provider order. Confirm the UX.
