## Why

On Windows and Linux, and on Macs without the speech helper, Sirina falls back to CPU faster-whisper. On the M1 Pro reference machine, faster-whisper took 52 s for 10 minutes of audio, peaked at 6.7 GB and dropped phrases. It is slower on typical Windows laptops, and there are no live captions or transcription during recording. NVIDIA's Parakeet TDT 0.6B v3 covers 25 European languages, including German and English. It runs through sherpa-onnx, a cross-platform ONNX runtime with Python wheels, at what should be a fraction of Whisper's CPU cost on any hardware. That makes it the candidate for a fast default engine and near-real-time captions outside macOS. faster-whisper stays as the user-selectable engine for other languages, and NVIDIA users can download GPU acceleration for it.

## What Changes

- **Spike first.** It gates the rest of the change and runs on the development Mac against the reference recording (rec 13). It measures:
  - Parakeet's speed, memory and accuracy against WhisperKit turbo and faster-whisper turbo
  - word-timestamp quality
  - hotword (vocabulary) support
  - near-real-time caption feasibility: latency and CPU for two simultaneous tracks
  - short caption chunks against 3-minute windows

  The spike settles whether settled captions can serve as final segments, and whether captions ship on Windows and Linux at all.
- **New `parakeet` transcription engine**, in-process in the Python backend through `sherpa-onnx`:
  - it implements the existing `TranscriptionEngine` interface (`transcribe_file`, `transcribe_window`) with word timestamps built from token timestamps
  - it runs on CPU on any hardware
  - its model (Parakeet int8) is downloaded on demand through the existing model manager; final transcription reuses the Silero VAD bundled with faster-whisper
- **Engine selection**:
  - The `auto` setting resolves to WhisperKit on Apple Silicon with the speech helper as today.
  - Otherwise it resolves to Parakeet, unless the configured language is outside Parakeet's 25, in which case it uses faster-whisper.
  - Users can pick `parakeet` or `faster-whisper` explicitly; the Settings engine options gain `parakeet`.
  - Parakeet is also selectable on macOS.
- **Near-real-time live captions on Windows and Linux** (and on macOS without Apple's speech recognizer):
  - A Python caption worker (the frozen backend re-run as a worker) speaks the same stdin-PCM / stdout-JSON contract as `speech-engine captions`, so `CaptionStream` is unchanged apart from the command it runs.
  - Captions must meet the existing latency targets: provisional text within 2 s and settled text within 3 s.
  - If no model meets the targets within the CPU budget, captions stay **disabled on Windows and Linux with an explanation**.
  - A machine that can't keep up during a recording stops captions with a message; the recording continues.
- **Transcription during recording** also runs on Parakeet, not only WhisperKit, when the spike confirms it is light enough for a live call.
- **Optional GPU acceleration pack for faster-whisper** (Windows and Linux with NVIDIA):
  - a download in the model manager that installs NVIDIA's cuBLAS and cuDNN runtime libraries into the data directory
  - with it, faster-whisper runs on CUDA (float16) when an NVIDIA GPU is detected, and falls back to CPU otherwise
  - nothing CUDA-related is bundled in the app
- **Language and vocabulary**:
  - Parakeet doesn't report a language, so the recording's language is the configured one when set, otherwise left empty (the badge is hidden).
  - Vocabulary hints (`whisper_initial_prompt`) are passed as hotwords if the spike shows sherpa-onnx supports them for Parakeet. Otherwise Settings states that hints apply to Whisper engines only.

## Capabilities

### New Capabilities
- `parakeet-engine`:
  - the Parakeet engine's behaviour, its language coverage, word timings and models
  - vocabulary hints
  - the caption worker that runs on it
- `gpu-acceleration-pack`: the optional downloadable CUDA runtime for faster-whisper, GPU detection, CPU fallback and removal

### Modified Capabilities
- `transcription-job`: engine selection gains Parakeet and the language-aware `auto` rule.
- `live-captions`:
  - availability is per platform recognizer: Apple speech on macOS 26+, the Parakeet caption worker elsewhere, when shipped
  - the CPU budget is defined per platform
  - captions are disabled with a reason when no recognizer meets the targets
- `live-transcription`: transcription during recording may run on Parakeet as well as WhisperKit; the low-power pause works on Windows and Linux.
- `speech-models`: "in use" follows the active engine's real configuration. Today the default faster-whisper `medium` model is listed as unused and can be deleted.

## Impact

- **Backend**:
  - new `transcribe/parakeet.py` (engine)
  - new `recording/caption_worker.py`, the worker entry point and an argv switch in the frozen entry
  - `transcribe/engine.py`: selection
  - `recording/recorder.py`: `captions_available()` and `live_transcription_available()` return reasons
  - `recording/captions.py`: the command comes from a provider
  - `speech_models.py`: Parakeet, VAD and GPU pack entries
  - `transcribe/whisper.py`: CUDA device when the pack is present
  - `settings_store.py`: engine options
  - `api/audio.py` and `api/settings.py`: reasons and pack status
- **Dependencies**: `sherpa-onnx`, a Python wheel for macOS, Windows and Linux that brings its own onnxruntime. PyInstaller must collect its native libraries. The bundle grows by roughly 30–60 MB, to be measured.
- **Frontend**: the Settings engine picker, the model manager entries (Parakeet, GPU pack), and caption and live-option hints driven by backend reasons.
- **Data**: no schema change. Models and CUDA libraries live in the data directory.
- **Depends on**:
  - `cross-platform-recording`, which adds the capability reason fields, the `platform` status field and the psutil-based `power_state()`; this change only changes how those are computed. Its Windows and Linux bundles are needed for end-to-end use there. The spike and the engine can be built and tested on macOS first.
  - `faster-transcription-live-captions` is already archived (2026-10-09), so its requirements are in the main specs.
- **Out of scope**:
  - speaker splitting on Windows and Linux, a later change with sherpa-onnx diarization
  - GPU acceleration for Parakeet itself
  - AMD and Intel GPU acceleration for faster-whisper
