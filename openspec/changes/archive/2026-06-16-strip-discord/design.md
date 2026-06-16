## Context

The codebase currently supports two audio sources: Discord voice-recv and local `sounddevice` capture. The Discord path is non-functional in practice (DAVE enforcement) and was retained only experimentally. The local path works. This change is a pure subtraction that leaves the working local path intact.

## Goals / Non-Goals

**Goals:**
- Remove all Discord code, dependencies, configuration, and UI.
- Keep the local-audio record path working with no regression.
- Shrink the dependency surface (drop alpha-pinned `discord-ext-voice-recv` and the prerelease resolver flag if no longer needed).

**Non-Goals:**
- Changing the recording/transcription model (that is `record-to-file` and `offline-transcription`).
- Renaming the project or the `Meeting` model (cosmetic; deferred).
- Removing live transcription behavior — that is replaced later by `record-to-file`; here the app keeps doing what it does, minus Discord.

## Decisions

- **Delete `app/bot/` wholesale** rather than guarding it behind a flag. The code is unused and its monkey-patches (`sink=None` shim, `OpusError` swallow) only exist to work around the dead path. Keeping dead code "just in case" contradicts the committed direction.
  - *Alternative considered*: keep behind `if settings.discord_token`. Rejected — leaves dead deps and confuses the architecture.
- **Drop the standalone `silero-vad` dependency.** The live `Chunker` used it; once `record-to-file` replaces the live pipeline, VAD comes from faster-whisper's bundled Silero (`vad_filter=True`). Remove it here since the only consumer (`chunker.py`) is going away. If `record-to-file` lands after this and still needs the live chunker temporarily, keep `silero-vad` until then — sequence so the app never breaks.
- **Keep `sounddevice` and `app/audio/local.py`.** That is the surviving source.
- **Status endpoint** keeps `ollama_ok`, `whisper_loaded`, `model`; drops `bot_connected`, `voice_channel`.
- **Remove the prerelease flag** (`[tool.uv] prerelease = "allow"` and `--prerelease=allow` in `dev.sh`) only if no remaining dependency requires it. `discord-ext-voice-recv==0.5.2a179` was the reason; once gone, revert to stable resolution.

## Risks / Trade-offs

- [Removing `silero-vad` while the live chunker still exists would break recording] → Sequence the removal: only drop `silero-vad` in the same step that removes `chunker.py`, or land `record-to-file` first. The tasks order this explicitly.
- [Frontend references to removed endpoints/fields cause runtime errors] → Update `api.ts`, `Dashboard.tsx`, `ConnectionStatus.tsx` in the same change; type-check the frontend.
- [Lockfile churn] → Re-run `uv lock` and `npm install` to keep lockfiles truthful; commit them.

## Migration Plan

This is internal-only; no user data migration. Steps:
1. Remove frontend Discord affordances and rebuild/type-check.
2. Remove Discord API branches and status fields.
3. Remove bot wiring from `main.py`/`runtime.py`.
4. Delete `app/bot/`.
5. Remove Discord deps + `silero-vad` (coordinated with chunker removal) and re-lock.
6. Remove Discord config keys and update README/.env.example.

Rollback: `git revert` the change; no external state involved.

## Open Questions

- Should the prerelease resolver flag be removed now, or left until we confirm no other alpha deps are added in `record-to-file`? (Lean: remove now; re-add only if a later change needs it.)
