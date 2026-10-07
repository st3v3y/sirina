# Sirina

Self-hosted **local meeting recorder**: records audio from an input device on your Mac and transcribes it on-device — [WhisperKit](https://github.com/argmaxinc/argmax-oss-swift) `large-v3-turbo` on the Neural Engine (optionally while you record), with [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) as the CPU fallback — then offers summaries / Q&A via a local [Ollama](https://ollama.com) model. Operated through a local web app.

All inference (speech + LLM) runs locally. Nothing is sent to a third-party API; models download once.

> **Evolving toward v2** (Jamie-style): record now, transcribe after. Speaker detection, structured multi-section summaries, tags, and a packaged macOS app are on the roadmap — see [docs/V2-LOCAL-REDESIGN.md](docs/V2-LOCAL-REDESIGN.md) and [docs/V2-PRIORITIES.md](docs/V2-PRIORITIES.md). The Discord integration has been removed (Discord's DAVE voice encryption made it unworkable).

## What you get

- **Record to disk** — capture your mic and (optionally) system audio as separate tracks. Optional, per recording: **live captions** (Apple on-device speech, macOS 26+) and **transcription during the recording** (WhisperKit, mostly on the Neural Engine), both off the capture path.
- **Fast transcription** — WhisperKit `large-v3-turbo` in ~3-minute windows cut at pauses; a quick on-device **draft** appears right after stop and is replaced window by window by the final text. Falls back to faster-whisper (CPU) where WhisperKit can't run. The recording goes `processing → ready`.
- **Full summary** using a configurable prompt template, and **Q&A** grounded in the transcript.
- **Recordings list** with detail view, export to `.md`/`.txt`, delete.
- **Editable prompt templates** for summaries and Q&A.

## Architecture

```
RECORD                              PROCESS (windows; during and/or after the recording)
Local audio (mic + optional system) draft (Apple on-device) → final windows
  → sounddevice / ScreenCaptureKit     → speech-engine helper: WhisperKit (Neural Engine),
  → mic.wav / system.wav / mixed.wav     SpeakerKit speakers, Apple captions/draft
  → optional live captions             → Segments (draft → final) → status: ready
                                       → Ollama (summaries, Q&A) on demand
            ↓                                       ↓
                       SQLite  ←→  FastAPI  ←→  React SPA (Vite)
```

One Python process hosts the recorder, the background transcription processor (single-flight, restart-safe — it resumes after the last final window), and the FastAPI server. Speech runs in the native `speech-engine` Swift helper (`native/speech-engine`, build with its `build.sh`); faster-whisper stays in-process as the fallback. A React SPA on Vite talks to it.

## Requirements

- macOS or Linux (tested on Apple Silicon)
- Python **3.12** (uv handles installing it)
- Node **20+**
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Ollama](https://ollama.com) running locally
- (Optional) [BlackHole](https://github.com/ExistentialAudio/BlackHole) to capture system/call audio rather than just the mic

## Setup

### 1. Ollama models

```bash
ollama pull llama3.1:8b-instruct
# or any other instruct-tuned model you prefer
```

### 2. Install dependencies (one time)

```bash
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
cp backend/.env.example backend/.env
# edit backend/.env: set OLLAMA_MODEL, WHISPER_MODEL, WHISPER_LANGUAGE as desired
```

### 3. Run both servers

```bash
./dev.sh
```

This starts the backend on `:8000` and the frontend on `:5173` with prefixed, colour-coded output. Ctrl-C stops both. Override ports with `BACKEND_PORT=8001 FRONTEND_PORT=5174 ./dev.sh`.

Build the speech helper once with `./native/speech-engine/build.sh` (needs Xcode). The first transcription downloads the WhisperKit model (~630 MB) and prepares it for the Neural Engine (a few minutes, once); manage models under **Settings → Speech models**.

Then open [http://localhost:5173](http://localhost:5173).

### Capturing the other participants

To record a call's far-end (everyone else), the system audio has to be captured too:

- **Packaged desktop app** → captures system audio **natively** (ScreenCaptureKit). Just grant
  **Screen Recording** when prompted; pick only your microphone. No extra setup.
- **Browser / dev** → install **BlackHole** and route your call's output through a Multi-Output
  device, then pick **BlackHole** as the "System audio" device in the start modal. Without it,
  only your microphone is recorded.

### Packaged macOS app (optional)

To build a double-click `.app` (Tauri shell + bundled backend + native capture, no terminal),
see [docs/PACKAGING.md](docs/PACKAGING.md). The dev flow above is unaffected.

#### Or run them separately

```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev
```

## Capturing system / call audio (optional)

By default you can pick any input device (e.g. your microphone). To transcribe a call (Zoom, Meet, etc.) you need to route the call's audio into an input device:

1. Install [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole).
2. In **Audio MIDI Setup**, create a **Multi-Output Device** combining your speakers/headphones **and** BlackHole 2ch, and set it as the system output (so you still hear the call while it's also routed to BlackHole).
3. In the dashboard, pick **BlackHole 2ch** as the input device.

To capture your own mic *and* the call together, create an **Aggregate Device** combining BlackHole 2ch + your mic and select that instead.

## Using it

1. The status pill in the top-right should go green: **Ready**.
2. On the dashboard, pick a **microphone** (and optionally a **system audio** device like BlackHole), a **label**, and an optional title.
3. Click **● Start recording** and choose, for this recording, whether to transcribe during the recording and show live captions (defaults are in Settings).
4. Click **■ Stop**. The recording moves to **processing**; the detail view shows a "transcribing…" banner and auto-updates to **ready** when the transcript is in (a few seconds to a few minutes depending on length and model).
5. On the detail page, generate a summary, ask questions grounded in the transcript, or download a `.md` / `.txt` export.

## Configuration

All settings live in `backend/.env` (see `.env.example`). The interesting ones:

| Variable | Default | Notes |
| --- | --- | --- |
| `TRANSCRIPTION_ENGINE` | `auto` | `auto` (WhisperKit on Apple Silicon, else faster-whisper) / `whisperkit` / `faster-whisper` |
| `LIVE_TRANSCRIBE_DEFAULT` | `true` | Default for new recordings: finalize the transcript during the call (WhisperKit only) |
| `LIVE_CAPTIONS_DEFAULT` | `false` | Default for new recordings: live captions (macOS 26+) |
| `TRANSCRIBE_CHUNK_SECONDS` | `180` | Window length for the final transcript (cut at a pause) |
| `WHISPER_MODEL` | `medium` | CPU fallback (faster-whisper) model only |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` or `int8_float16` are fastest on Apple Silicon |
| `WHISPER_LANGUAGE` | *(auto)* | Set to e.g. `en` / `es` / `de` to skip language detection |
| `WHISPER_INITIAL_PROMPT` | *(empty)* | Comma-separated vocabulary hints (e.g. `EcoHubs, Mediakular`) |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct` | any local Ollama model |
| `DIARIZATION_ENABLED` | `false` | Split a track into multiple speakers (see below) |
| `DIARIZATION_TIMING` | `after_stop` | `after_stop` or `during_recording` (also about every 10 min while recording) |
| `VOICE_MATCH_THRESHOLD` | `0.6` | Auto-recognise recurring people by voice fingerprint (cosine similarity 0..1); `0` disables |
| `ECHO_SPEAKER_OVERLAP` | `0.75` | Drop a diarized speaker whose speech overlaps your mic speech by at least this fraction (your own echo in the call audio); `0` disables |
| `COMPRESS_AUDIO` | `true` | Compress finished recordings from WAV to AAC (`.m4a`, ~10-15× smaller) via macOS `afconvert` |

## Speaker diarization (optional)

By default speakers are split by track: your mic is **"You"**, system audio is **"Others"** (and a single mic is one speaker). To break a track into individual people — e.g. several people on a call, or an in-room meeting through one mic — enable **diarization** (Settings → Speaker splitting). It uses [SpeakerKit](https://github.com/argmaxinc/argmax-oss-swift) in the speech helper, entirely on your Mac: no account or token, a ~60 MB model that downloads on first use, and about a minute for a 2-hour recording.

When enabled, the mic track stays "You" and the other track is split into `Speaker 1`, `Speaker 2`, … which you can rename into People in the transcript. If speaker splitting fails, it falls back to the track-based split and notes why — recordings always complete.

### Voice fingerprints (recognising recurring people)

Renaming a diarized speaker to a person enrolls that speaker's voice embedding as the person's **voice fingerprint** (People with one show a "Voice" badge). In later recordings, diarized speakers are automatically linked to the closest enrolled person when their voice similarity is at least `VOICE_MATCH_THRESHOLD`. Fingerprints are tagged with the model that made them; the switch from pyannote to SpeakerKit cleared the old ones, so people are re-learned from your next renames. Only manual renames update a fingerprint — an automatic match never feeds back, so a wrong match is fixed by simply renaming the speaker. The "You" speaker needs no fingerprint: your mic track is always you, and renaming "You" once (e.g. to your name) applies to every recording.

## Audio storage

Recordings are captured as 48 kHz WAV; once processing finishes they're compressed to AAC (`.m4a`, ~10-15× smaller) using macOS's built-in `afconvert` (`COMPRESS_AUDIO=false` keeps the WAVs). **Re-process** transparently decodes compressed audio back to WAV first. On a recording's detail page you can also **delete just the audio** (the small trash button next to the player) to free disk space — the transcript, summary and chat are kept, but playback and re-processing become unavailable.

## Prompt templates

The **Templates** page in the UI lets you edit the summary and Q&A prompts and add your own. Available placeholders:

- `{{transcript}}` — full recording transcript (summary / qa)
- `{{qa_history}}` — previous Q&A turns for this recording (qa)
- `{{question}}` — the user's current question (qa)

## Consent

Recording a meeting in many jurisdictions requires consent from all participants. This project is intended for use with your own meetings where consent has been obtained. Announce that you are recording before you start.

## Project layout

```
backend/   FastAPI + job/recorder + faster-whisper fallback + Ollama (single local process)
native/    speech-engine (WhisperKit, SpeakerKit, Apple speech) and system-audio-capture helpers
frontend/  Vite + React + Tailwind SPA
docs/      v2 redesign + priorities
data/      SQLite DB (gitignored)
```
