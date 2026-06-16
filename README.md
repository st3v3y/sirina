# Live Transcript Bot

Self-hosted Discord bot that joins a voice channel, transcribes each participant in near-real-time with [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper), and offers live + on-demand summaries / Q&A via a local [Ollama](https://ollama.com) model. Operated through a local web app.

All inference (Whisper + LLM) runs locally. Nothing is sent to a third-party API.

## What you get

- **Live chat-style transcript** with per-speaker bubbles (Discord gives one PCM stream per user — no diarization needed).
- **Rolling "aspects" panel** — the AI summarises the discussion as short bullets that refresh every ~60s.
- **Full summary on stop**, using a configurable prompt template.
- **Per-meeting Q&A** — ask grounded questions about a past or in-progress meeting.
- **Past recordings list** with detail view, export to `.md`/`.txt`, delete.
- **Editable prompt templates** for aspects, summaries, and Q&A.

## Architecture

```
Discord voice  →  py-cord + voice-recv (per-user PCM)
                ↓
              silero-VAD chunker (~3–8s)
                ↓
              faster-whisper (local)
                ↓
              SQLite + WebSocket → browser
                ↓
              Ollama (aspects, summaries, Q&A)
```

One Python process hosts the bot, the chunker, the whisper worker, the FastAPI HTTP server, and the WebSocket fan-out. A React SPA on Vite talks to it.

## Requirements

- macOS or Linux (tested on Apple Silicon)
- Python **3.12** (uv handles installing it)
- Node **20+**
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Ollama](https://ollama.com) running locally
- A Discord bot token

## Setup

### 1. Discord bot

1. Create an application at [discord.com/developers](https://discord.com/developers/applications).
2. Add a bot, enable **Server Members Intent** and **Voice State** privileged intents.
3. Invite the bot to your server with `bot` + `Connect` + `Speak` voice permissions. (No text channel permissions needed.)
4. Copy the bot token.

### 2. Ollama models

```bash
ollama pull llama3.1:8b-instruct
# or any other instruct-tuned model you prefer
```

### 3. Install dependencies (one time)

```bash
cd backend && uv sync --prerelease=allow && cd ..
cd frontend && npm install && cd ..
cp backend/.env.example backend/.env
# edit backend/.env: set DISCORD_TOKEN, DISCORD_GUILD_ID, OLLAMA_MODEL, WHISPER_MODEL
```

### 4. Run both servers

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

## Using it

1. The status pill in the top-right should go green: **Bot ready**.
2. From the dashboard, optionally enter a **voice channel ID** (right-click a voice channel in Discord with Developer Mode on → Copy ID). Leave blank to auto-pick the busiest voice channel.
3. Click **● Start recording**. The bot joins the channel.
4. Talk. Within ~6–8 seconds each utterance appears as a labelled bubble in the browser.
5. After ~60s a bullet list of "aspects" appears in the side panel and refines over time.
6. Click **■ Stop**. The bot leaves and an auto-generated summary appears on the meeting detail page.
7. Use the prompt bar at the bottom of the detail page to ask questions about the meeting, or download a `.md` / `.txt` export.

## Configuration

All settings live in `backend/.env` (see `.env.example`). The interesting ones:

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_MODEL` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` or `int8_float16` are fastest on Apple Silicon |
| `WHISPER_LANGUAGE` | *(auto)* | Set to e.g. `en` to skip language detection |
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

Recording a voice call in many jurisdictions requires consent from all participants. This project is intended for use with your own meetings where consent has been obtained. The bot does not (yet) send a message in the text channel when recording starts — you should announce it manually until that's wired up.

## Project layout

```
backend/   FastAPI + py-cord + faster-whisper + Ollama (single process)
frontend/  Vite + React + Tailwind SPA
data/      SQLite DB (gitignored)
```
