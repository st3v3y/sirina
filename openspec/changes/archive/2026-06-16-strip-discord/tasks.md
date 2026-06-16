## 1. Frontend — remove Discord affordances

- [x] 1.1 In `frontend/src/pages/Dashboard.tsx`, remove the source toggle, the voice-channel-ID input, and the Discord branch of `startMeeting`; always start a local recording.
- [x] 1.2 In `frontend/src/lib/api.ts`, remove the `discord` source from `StartMeetingRequest` and any Discord-only fields from `Status`.
- [x] 1.3 Simplify or remove `frontend/src/components/ConnectionStatus.tsx` so it no longer references Discord (`bot_connected`/`voice_channel`).
- [x] 1.4 Run `npx tsc --noEmit` and `npm run build`; fix any references to removed symbols.

## 2. Backend API — drop Discord branches

- [x] 2.1 In `app/api/meetings.py`, remove the Discord branch of `start` and any guild/channel handling; keep the local branch as the sole path.
- [x] 2.2 In `app/api/status.py`, remove `bot_connected` and `voice_channel` from the response model and handler.
- [x] 2.3 In `app/runtime.py`, remove `bot`, `bot_connected()`, and `voice_channel_name()`.

## 3. Backend wiring — remove the bot

- [x] 3.1 In `app/main.py`, remove the `TranscriptBot` import, lifespan start/stop of the bot, and the bot task; keep whisper/ollama/pipeline wiring.
- [x] 3.2 Make `Pipeline` no longer accept or reference a `bot` (remove the Discord `start_meeting`; keep `start_local_meeting`, rename to the canonical start if convenient).

## 4. Move shared chunker out of bot/, delete Discord-only files

- [x] 4.1 Move `backend/app/bot/chunker.py` → `backend/app/audio/chunker.py` (it is shared by the surviving local path, not Discord-specific) and update its imports/usages.
- [x] 4.2 Delete the Discord-only files: `backend/app/bot/client.py`, `backend/app/bot/sink.py`, `backend/app/bot/__init__.py` (and the now-empty `app/bot/` dir).
- [x] 4.3 Remove any remaining imports of `app.bot.*` across the backend (e.g. `pipeline.py`).
- [x] 4.4 Keep `silero-vad` for now — it is still used by the moved `chunker.py` on the live local path. It will be removed in `record-to-file` when the live pipeline is replaced by the file recorder.

## 5. Dependencies and config

- [x] 5.1 In `backend/pyproject.toml`, remove `discord.py`/`py-cord`, `discord-ext-voice-recv`, and `audioop-lts`. Keep `silero-vad` (per 4.4).
- [x] 5.2 Remove `[tool.uv] prerelease = "allow"` if no remaining dependency needs it; remove `--prerelease=allow` from `dev.sh`.
- [x] 5.3 Run `uv lock` and `uv sync`; commit the updated lockfile.
- [x] 5.4 In `backend/app/config.py` and `backend/.env.example`, remove `DISCORD_TOKEN` and `DISCORD_GUILD_ID`.

## 6. Docs and verification

- [x] 6.1 Update `README.md` to remove Discord setup (bot token, intents, invite) and describe local-only usage.
- [x] 6.2 Start the backend with no Discord env present; confirm `/api/status` returns 200 with no Discord fields.
- [x] 6.3 Start a local recording end-to-end through the UI and confirm transcription still works (no regression).
- [x] 6.4 Grep the repo for `discord` (case-insensitive) and confirm only historical doc references remain.
