# Live Transcript Bot

Self-hosted **local meeting transcriber**: captures audio from an input device on your Mac, transcribes it near-real-time with [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper), and offers live + on-demand summaries / Q&A via a local [Ollama](https://ollama.com) model. Operated through a local web app.

All inference (Whisper + LLM) runs locally. Nothing is sent to a third-party API.

> **Heading toward v2.** This is evolving into a Jamie-style "record now, transcribe after" recorder with speaker detection, structured summaries, tags, and a packaged macOS app. See [docs/V2-LOCAL-REDESIGN.md](docs/V2-LOCAL-REDESIGN.md) and [docs/V2-PRIORITIES.md](docs/V2-PRIORITIES.md). The Discord integration has been removed (Discord's DAVE voice encryption made it unworkable).

## What you get

- **Live chat-style transcript** of the captured audio.
- **Rolling "aspects" panel** — the AI summarises the discussion as short bullets that refresh every ~60s.
- **Full summary on stop**, using a configurable prompt template.
- **Per-meeting Q&A** — ask grounded questions about a past or in-progress meeting.
- **Past recordings list** with detail view, export to `.md`/`.txt`, delete.
- **Editable prompt templates** for aspects, summaries, and Q&A.

## Architecture

```
Local audio input (mic / BlackHole)  →  sounddevice capture (16 kHz mono)
                ↓
              silero-VAD chunker (~3–8s)
                ↓
              faster-whisper (local)
                ↓
              SQLite + WebSocket → browser
                ↓
              Ollama (aspects, summaries, Q&A)
```

One Python process hosts the audio capture, the chunker, the whisper worker, the FastAPI HTTP server, and the WebSocket fan-out. A React SPA on Vite talks to it.

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
2. On the dashboard, pick an **input device** and a **label** (shown next to each transcript line, e.g. "Room"), optionally a title.
3. Click **● Start recording**.
4. Talk. Within ~6–8 seconds each utterance appears as a labelled bubble in the browser.
5. After ~60s a bullet list of "aspects" appears in the side panel and refines over time.
6. Click **■ Stop**. An auto-generated summary appears on the meeting detail page.
7. Use the prompt bar at the bottom of the detail page to ask questions about the meeting, or download a `.md` / `.txt` export.

## Configuration

All settings live in `backend/.env` (see `.env.example`). The interesting ones:

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_MODEL` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` or `int8_float16` are fastest on Apple Silicon |
| `WHISPER_LANGUAGE` | *(auto)* | Set to e.g. `en` / `es` / `de` to skip language detection (more reliable on short chunks) |
| `WHISPER_INITIAL_PROMPT` | *(empty)* | Comma-separated vocabulary hints (e.g. `EcoHubs, Mediakular`) |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct` | any local Ollama model |
| `ASPECTS_INTERVAL_SECONDS` | `60` | how often to regenerate the live bullet list |
| `CHUNK_MAX_SECONDS` | `8` | hard cap per transcription chunk |
| `CHUNK_SILENCE_MS` | `600` | trailing silence that ends a chunk |

## Prompt templates

The **Templates** page in the UI lets you edit the three default prompts (aspects, summary, Q&A) and add your own. Available placeholders:

- `{{transcript}}` — full meeting transcript (summary / qa)
- `{{new_transcript}}` — only newly transcribed lines since the last aspect (aspects)
- `{{previous_aspects}}` — the most recent aspect bullets (aspects)
- `{{qa_history}}` — previous Q&A turns for this meeting (qa)
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
