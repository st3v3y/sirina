# Sirina

Self-hosted **local meeting recorder**: records audio from an input device on your Mac, then — after you stop — transcribes the whole recording with [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) and offers summaries / Q&A via a local [Ollama](https://ollama.com) model. Operated through a local web app.

All inference (Whisper + LLM) runs locally. Nothing is sent to a third-party API.

> **Evolving toward v2** (Jamie-style): record now, transcribe after. Speaker detection, structured multi-section summaries, tags, and a packaged macOS app are on the roadmap — see [docs/V2-LOCAL-REDESIGN.md](docs/V2-LOCAL-REDESIGN.md) and [docs/V2-PRIORITIES.md](docs/V2-PRIORITIES.md). The Discord integration has been removed (Discord's DAVE voice encryption made it unworkable).

## What you get

- **Record to disk** — recording runs no inference, so it stays light on CPU. Capture your mic and (optionally) system audio as separate tracks.
- **High-quality transcription after stop** — whole-file faster-whisper with beam search + VAD, processed in the background. The recording goes `processing → ready`.
- **Full summary** using a configurable prompt template, and **Q&A** grounded in the transcript.
- **Recordings list** with detail view, export to `.md`/`.txt`, delete.
- **Editable prompt templates** for summaries and Q&A.

## Architecture

```
RECORD                              PROCESS (after stop)
Local audio (mic + optional system) Recording (processing)
  → sounddevice capture                → faster-whisper (whole file,
  → mic.wav / system.wav / mixed.wav     beam + VAD + word timestamps)
  → Recording (status: recording)      → Segments + language → status: ready
                                       → Ollama (summaries, Q&A) on demand
            ↓                                       ↓
                       SQLite  ←→  FastAPI  ←→  React SPA (Vite)
```

One Python process hosts the recorder, the background transcription processor (single-flight, restart-safe), the whisper worker, and the FastAPI server. A React SPA on Vite talks to it.

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

The first run will download the chosen Whisper model (small ≈ 480 MB, medium ≈ 1.5 GB, large-v3 ≈ 3 GB).

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
3. Click **● Start recording**. A timer and input-level meter show it's capturing — no transcript yet (transcription happens after you stop).
4. Click **■ Stop**. The recording moves to **processing**; the detail view shows a "transcribing…" banner and auto-updates to **ready** when the transcript is in (a few seconds to a few minutes depending on length and model).
5. On the detail page, generate a summary, ask questions grounded in the transcript, or download a `.md` / `.txt` export.

## Configuration

All settings live in `backend/.env` (see `.env.example`). The interesting ones:

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_MODEL` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v3-turbo` / `large-v3`. Since transcription is offline, **`large-v3-turbo`** is a good quality/speed pick (first use downloads it). |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` or `int8_float16` are fastest on Apple Silicon |
| `WHISPER_LANGUAGE` | *(auto)* | Set to e.g. `en` / `es` / `de` to skip language detection |
| `WHISPER_INITIAL_PROMPT` | *(empty)* | Comma-separated vocabulary hints (e.g. `EcoHubs, Mediakular`) |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct` | any local Ollama model |
| `DIARIZATION_ENABLED` | `false` | Split a track into multiple speakers (see below) |
| `HF_TOKEN` | *(empty)* | HuggingFace read token, required when diarization is on |
| `VOICE_MATCH_THRESHOLD` | `0.5` | Auto-recognise recurring people by voice fingerprint (cosine similarity 0..1); `0` disables |
| `COMPRESS_AUDIO` | `true` | Compress finished recordings from WAV to AAC (`.m4a`, ~10-15× smaller) via macOS `afconvert` |

## Speaker diarization (optional)

By default speakers are split by track: your mic is **"You"**, system audio is **"Others"** (and a single mic is one speaker). To break a track into individual people — e.g. several people on a call, or an in-room meeting through one mic — enable **diarization**, which uses [`pyannote.audio`](https://github.com/pyannote/pyannote-audio) locally.

It's **free and runs entirely on your machine** — the model is MIT-licensed; the HuggingFace token only gates the one-time model download. No per-meeting cost, no cap.

One-time setup:

1. Create a free account at [huggingface.co](https://huggingface.co).
2. Accept the terms on the model page: [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1) (the model used by pyannote.audio 4.x).
3. Create a **read** token at [hf.co/settings/tokens](https://hf.co/settings/tokens).
4. In `backend/.env` set `DIARIZATION_ENABLED=true` and `HF_TOKEN=<your token>`, then restart.

(The model is configurable via `DIARIZATION_MODEL` if you prefer a different pyannote pipeline.)

When enabled, the mic track stays "You" and the other track is split into `Speaker 1`, `Speaker 2`, … which you can rename into People in the transcript. If the token is missing or diarization fails, it silently falls back to the track-based split — recordings always complete.

### Voice fingerprints (recognising recurring people)

Renaming a diarized speaker to a person enrolls that speaker's voice embedding as the person's **voice fingerprint** (People with one show a "Voice" badge). In later recordings, diarized speakers are automatically linked to the closest enrolled person when their voice similarity is at least `VOICE_MATCH_THRESHOLD`. Only manual renames update a fingerprint — an automatic match never feeds back, so a wrong match is fixed by simply renaming the speaker. The "You" speaker needs no fingerprint: your mic track is always you, and renaming "You" once (e.g. to your name) applies to every recording.

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
backend/   FastAPI + faster-whisper + Ollama (single local process)
frontend/  Vite + React + Tailwind SPA
docs/      v2 redesign + priorities
data/      SQLite DB (gitignored)
```
