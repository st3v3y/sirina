## Why

The Discord voice path is a dead end: Discord enforced the DAVE end-to-end-encryption protocol for all non-stage voice channels (March 2026), and no Python Discord library supports DAVE voice receive. The product direction has shifted to a local, Jamie-style meeting recorder (see [docs/V2-LOCAL-REDESIGN.md](../../../docs/V2-LOCAL-REDESIGN.md)). Carrying the bot, its alpha-pinned dependencies, and its monkey-patches forward adds maintenance cost and confuses the architecture. This change removes Discord entirely so the rest of v2 builds on a clean local-only base.

## What Changes

- **BREAKING**: Remove the Discord bot and its audio-receive pipeline (`app/bot/`).
- Remove Discord dependencies: `discord.py`/`py-cord`, `discord-ext-voice-recv`, the `audioop-lts` shim, and the standalone `silero-vad` dep (offline transcription will use faster-whisper's bundled VAD later).
- Remove Discord configuration: `DISCORD_TOKEN`, `DISCORD_GUILD_ID` from config and `.env.example`.
- Remove the `source` toggle from the start-recording flow; the only source is now local audio.
- Remove `runtime.bot`, the bot lifespan wiring in `main.py`, and Discord fields (`bot_connected`, `voice_channel`) from the status endpoint.
- Remove frontend Discord affordances: the Discord/local source toggle, the voice-channel-ID input, and `ConnectionStatus`'s Discord wording.
- The app continues to function in local-audio mode end-to-end after this change (no regression to the working local path).

## Capabilities

### New Capabilities
- `local-only-runtime`: the application runs as a single local process with no Discord dependency, exposing status and start/stop for local audio recording only.

### Modified Capabilities
<!-- None: there is no pre-existing committed spec in openspec/specs/ yet; this is the first change to define behavior. -->

## Impact

- **Removed code**: `backend/app/bot/` (client.py, sink.py, chunker.py), Discord branches in `app/api/meetings.py`, Discord fields in `app/api/status.py`, bot wiring in `app/main.py` and `app/runtime.py`.
- **Dependencies**: `backend/pyproject.toml` and `uv.lock` lose four packages; smaller install, no prerelease pin needed for voice-recv.
- **Config**: `backend/.env.example` loses two keys.
- **Frontend**: `Dashboard.tsx` source toggle/channel input removed; `ConnectionStatus.tsx` simplified or removed.
- **Docs**: README updated to drop Discord setup.
- **Risk**: low — the local path already works and is exercised; this is deletion, not new behavior.
