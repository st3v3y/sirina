# Sirina

**A private meeting recorder for macOS that transcribes, splits speakers and summarises entirely on your Mac.**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue)](LICENSE.md)
![Platform: macOS on Apple Silicon](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Apple%20Silicon-lightgrey)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/sirina.app)

Sirina records your microphone and your call audio as separate tracks, transcribes them on the
Neural Engine with WhisperKit `large-v3-turbo`, and lets you summarise and ask questions with a
local AI model through [Ollama](https://ollama.com). By default, no audio or text leaves your
computer.

> **Status:** early and actively developed.
> [Download the latest release](https://github.com/st3v3y/sirina/releases/latest) for Apple
> Silicon Macs, or build it from source (see [Installation](#installation)).

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Privacy](#privacy)
- [Development](#development)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [Support the project](#support-the-project)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features

- **Two-track recording.** Your mic is "You", call audio is "Others". The packaged app captures
  system audio natively (ScreenCaptureKit), so you don't need a virtual audio device.
- **Fast on-device transcription.** WhisperKit `large-v3-turbo` runs mostly on the Neural
  Engine. In benchmarks on an M1 Pro, 10 minutes of audio took about a minute. On machines
  without WhisperKit, [faster-whisper](https://github.com/SYSTRAN/faster-whisper) runs on the
  CPU instead.
- **Transcription during the recording** (on by default). The transcript is finalised in
  ~3-minute windows while you talk, so only the last few minutes remain after you press stop.
- **Live captions** (optional, macOS 26+). Uses Apple's on-device speech recognition, with
  about one second of delay and very low CPU use.
- **Draft, then final.** A quick draft appears right after stop. Window by window, it's
  replaced by the final text.
- **Speaker splitting** (optional). [SpeakerKit](https://github.com/argmaxinc/argmax-oss-swift)
  splits the call audio into individual speakers in about a minute for a two-hour recording.
- **Voice fingerprints.** Rename a speaker to a person once, and Sirina recognises that voice in
  later recordings.
- **AI summaries and chat.** Use editable summary templates, ask questions about one meeting,
  or ask across all your recordings. Answers stay grounded in the transcripts.
- **People, tags, search and export** to Markdown or plain text.
- **Downloadable models.** The app ships without speech models. They download on first use
  (~630 MB for transcription, ~60 MB for speaker splitting), and you can remove them in
  Settings.

## How it works

```
RECORD                                   PROCESS (during and/or after the recording)
mic + system audio (ScreenCaptureKit)    speech-engine helper (Swift)
  → mic.wav / system.wav                   ├─ WhisperKit large-v3-turbo  → final windows
  → optional live captions ────────────────├─ Apple SpeechAnalyzer      → captions / draft
                                           └─ SpeakerKit                → speakers + voiceprints
              ↓                                            ↓
        SQLite  ←→  FastAPI backend (Python)  ←→  React UI in a Tauri window
                              ↓
                  Ollama (or another AI provider) for summaries and chat
```

- **`frontend/`** is a React + Vite UI. **`frontend/src-tauri/`** is the Tauri 2 shell that
  starts the backend as a sidecar.
- **`backend/`** is a single Python process. It hosts the recorder, the restart-safe
  transcription job and the FastAPI server. After a restart, the job resumes from the last
  final window.
- **`native/speech-engine/`** is a Swift helper that talks to the backend in JSON lines over
  stdio. It wraps WhisperKit, SpeakerKit and Apple's speech framework.
- **`native/system-audio-capture/`** is a Swift helper that captures call audio with
  ScreenCaptureKit.

## Requirements

| | |
| --- | --- |
| **Mac** | Apple Silicon. The release is built for Apple Silicon only. |
| **macOS** | 14 or later. Live captions and the quick draft need macOS 26. |
| **Disk** | ~250 MB for the app, plus ~0.7 GB for models and your recordings |
| **AI (optional)** | [Ollama](https://ollama.com) with an instruct model, for summaries and chat |
| **Build tools** (only to build from source) | Xcode 26+, [Rust](https://rustup.rs) + `cargo install tauri-cli --version '^2'`, Node 20+, [uv](https://docs.astral.sh/uv/) |

Sirina runs on macOS only. There are no Windows or Linux builds.

## Installation

### 1. Download the app

1. Download
   [**Sirina-macOS-arm64.dmg**](https://github.com/st3v3y/sirina/releases/latest/download/Sirina-macOS-arm64.dmg)
   from the [latest release](https://github.com/st3v3y/sirina/releases/latest).
2. Open the DMG and drag **Sirina** into **Applications**.
3. Open Sirina. The app isn't notarized by Apple, so macOS blocks it the first time. Open
   **System Settings → Privacy & Security**, scroll down to the message about Sirina, and click
   **Open Anyway**. You only need to do this once.

If macOS says the app "is damaged" instead, remove the download quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/Sirina.app
```

<details>
<summary><strong>Or build the app from source</strong></summary>

```bash
git clone https://github.com/st3v3y/sirina.git
cd sirina
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
./scripts/build-macos-app.sh
```

The build script makes the UI, freezes the backend with PyInstaller, builds both Swift helpers
and bundles everything. The result is
`frontend/src-tauri/target/release/bundle/macos/Sirina.app`, plus
`bundle/dmg/Sirina-macOS-arm64.dmg`. The app is ad-hoc signed. For details, see
[docs/PACKAGING.md](docs/PACKAGING.md).

</details>

### 2. Set up the AI model (optional)

```bash
ollama pull llama3.1:8b-instruct   # or any instruct model; pick it in Settings → AI
```

Thinking models such as Qwen 3.x work too. Sirina turns their "thinking" off by default because
it makes answers slow without making them better. You can turn it on in Settings.

### 3. First launch

Grant **Microphone** and, to record the other side of calls, **Screen Recording** when macOS
asks. The first transcription downloads the WhisperKit model and prepares it for the Neural
Engine. This happens once and takes a few minutes. To manage models, go to
**Settings → Speech models**.

## Usage

1. Click **Start recording**, then pick your microphone and, optionally, system audio.
2. For this recording, choose whether to **transcribe during the recording** and whether to
   show **live captions**. The defaults are set in Settings.
3. Click **Stop**. The draft appears right away and turns into the final transcript as windows
   finish. A banner shows progress.
4. Rename speakers to people, generate a **summary**, **ask questions**, or **export** the
   transcript.
5. Use **Ask** to chat across all your recordings.

> **Consent:** many jurisdictions require every participant's consent before a conversation is
> recorded. Use Sirina only for meetings where you have that consent, and say that you're
> recording before you start.

## Configuration

Most options can be changed in the app under **Settings**. Environment variables set the
defaults:

- **Dev runs:** put them in `backend/.env` (see [`backend/.env.example`](backend/.env.example)).
- **Packaged app:** put a `.env` in `~/Library/Application Support/com.sirina.app/`.

| Variable | Default | What it does |
| --- | --- | --- |
| `TRANSCRIPTION_ENGINE` | `auto` | `auto` (WhisperKit where available, else CPU), `whisperkit`, or `faster-whisper` |
| `LIVE_TRANSCRIBE_DEFAULT` | `true` | Transcribe during the recording by default (WhisperKit only) |
| `LIVE_CAPTIONS_DEFAULT` | `false` | Show live captions by default (macOS 26+) |
| `TRANSCRIBE_CHUNK_SECONDS` | `180` | Window length for the final transcript (cut at a pause) |
| `WHISPER_LANGUAGE` | *(auto)* | Force a language, e.g. `en` or `de` |
| `WHISPER_INITIAL_PROMPT` | *(empty)* | Comma-separated spelling hints for names and jargon |
| `WHISPER_MODEL` | `medium` | Model for the CPU fallback (faster-whisper) |
| `LLM_PROVIDER` | `ollama` | `ollama`, `lmstudio`, `openai`, `google`, `groq` or `custom` |
| `LLM_MODEL` | `llama3.1:8b-instruct` | Model name for that provider |
| `LLM_THINK` | `false` | Let thinking models reason before answering (Ollama only) |
| `DIARIZATION_ENABLED` | `false` | Split the call audio into individual speakers |
| `DIARIZATION_TIMING` | `after_stop` | `after_stop`, or `during_recording` (also about every 10 min while recording) |
| `VOICE_MATCH_THRESHOLD` | `0.6` | How close a voice must be to auto-link a person (0–1; `0` turns it off) |
| `ECHO_SPEAKER_OVERLAP` | `0.75` | Drops a "speaker" that is just your own voice echoed in the call audio |
| `COMPRESS_AUDIO` | `true` | Compress finished recordings to AAC (`.m4a`, ~10–15× smaller) |

API keys for cloud AI providers are stored in the macOS Keychain.

## Privacy

- **Local by default.** Recording, transcription, speaker splitting and the default AI provider
  (Ollama) all run on your Mac.
- **Network use.** Sirina only goes online to download models from Hugging Face when you first
  need them, and to call a cloud AI provider if you choose one in Settings. That provider then
  receives the transcript text you ask about.
- **Where data lives.** Recordings, transcripts and voice fingerprints are stored under
  `~/Library/Application Support/com.sirina.app/` (`backend/data/` in dev).

## Development

Run the backend and UI with hot reload, without building the app:

```bash
./native/speech-engine/build.sh   # once; needs Xcode
cp backend/.env.example backend/.env
./dev.sh                          # backend on :8000, UI on :5283
```

Then open <http://localhost:5283>. In the browser, call audio can't be captured natively. To
record the other side of a call in dev, route it through
[BlackHole](https://github.com/ExistentialAudio/BlackHole) with a Multi-Output Device, and pick
BlackHole as the system-audio device.

Run the tests and the linter:

```bash
cd backend && uv run pytest
cd frontend && npm run lint
```

Larger changes are planned as [OpenSpec](https://github.com/Fission-AI/OpenSpec) changes in
[`openspec/`](openspec/). Each change has a proposal, a design and a task list, and the current
behaviour is described in `openspec/specs/`.

## Project layout

```
backend/            FastAPI app, recorder, transcription job, AI provider, tests
frontend/           React + Vite + Tailwind UI
frontend/src-tauri/ Tauri 2 desktop shell (Rust)
native/             Swift helpers: speech-engine, system-audio-capture
scripts/            build-macos-app.sh
site/               landing page (Astro, deployed on Vercel)
docs/               packaging and design notes
openspec/           specs and change proposals
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). To report a
security problem, see [SECURITY.md](SECURITY.md).

## Support the project

Sirina is free for noncommercial use. If it saves you time, you can support its development:

<a href="https://buymeacoffee.com/sirina.app"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-sirina.app-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee"></a>

## License

Sirina is **source-available** under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md). You may use, modify and share it for any
noncommercial purpose, such as personal use, research, education, or use by charities and
public institutions. **Commercial use is not permitted** under this license. If you want to use
Sirina commercially, please get in touch via [GitHub](https://github.com/st3v3y).

Because it restricts commercial use, this license is not an
[OSI-approved open-source license](https://opensource.org/licenses).

## Acknowledgements

Sirina builds on these projects (license in brackets):

- [WhisperKit and SpeakerKit](https://github.com/argmaxinc/argmax-oss-swift) by Argmax (MIT)
- [OpenAI Whisper](https://github.com/openai/whisper) models (MIT), via
  [`argmaxinc/whisperkit-coreml`](https://huggingface.co/argmaxinc/whisperkit-coreml) (MIT)
- SpeakerKit models from
  [`argmaxinc/speakerkit-coreml`](https://huggingface.co/argmaxinc/speakerkit-coreml)
  (CC BY 4.0), based on [pyannote](https://github.com/pyannote/pyannote-audio)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) and
  [`Systran/faster-whisper-large-v3`](https://huggingface.co/Systran/faster-whisper-large-v3) (MIT)
- [Tauri](https://tauri.app) (MIT / Apache-2.0), [FastAPI](https://fastapi.tiangolo.com) (MIT),
  [React](https://react.dev) (MIT), [Ollama](https://ollama.com) (MIT)

Models are downloaded at runtime and are not part of this repository. Each one remains under its
own license.
