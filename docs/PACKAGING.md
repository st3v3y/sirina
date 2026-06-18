# Packaging the macOS desktop app (Tauri)

The desktop app is a **Tauri 2** shell that bundles the built React UI and runs the
FastAPI backend as a **sidecar** (a PyInstaller binary). It's a double-click `.app` —
no terminal, no two dev servers. (Native system-audio capture, removing BlackHole, is a
separate change: `native-system-audio-capture`. This shell only declares the Screen
Recording permission it will consume.)

> **Status:** the pipeline is **verified end-to-end** — `./scripts/build-macos-app.sh`
> freezes the backend (boots + serves `/api/status`), embeds it as the sidecar
> (`Sirina.app/Contents/MacOS/backend`), compiles the Tauri shell, and produces
> `Sirina.app` + a `.dmg`, ad-hoc signed. The only unverified steps are GUI-only:
> launching the app, the first-run permission prompts, and the Gatekeeper bypass.

## Layout

| Path | What |
| --- | --- |
| `frontend/src-tauri/tauri.conf.json` | Tauri config: dist dir, `externalBin` sidecar, dmg/app bundle, macOS min version 13 |
| `frontend/src-tauri/src/lib.rs` | Picks a free port, spawns the backend sidecar with `APP_DATA_DIR`, injects `window.__BACKEND_URL__`, creates the window |
| `frontend/src-tauri/Info.plist` | `NSMicrophoneUsageDescription` (first-run mic prompt) |
| `frontend/src-tauri/capabilities/default.json` | Allows running the `backend` sidecar |
| `backend/packaging/entry.py` | Frozen entry: `uvicorn` with `--host/--port` |
| `backend/packaging/backend.spec` | PyInstaller spec (transcription core; heavy ML extras commented) |
| `scripts/build-macos-app.sh` | End-to-end build + ad-hoc sign |

## How it fits together

- The frontend talks to the backend via `apiUrl()` in `lib/api.ts`. In **dev** there's no
  `window.__BACKEND_URL__`, so requests are relative and go through the Vite proxy to
  `:8000` (unchanged). In the **packaged app**, Rust injects `window.__BACKEND_URL__ =
  http://127.0.0.1:<free-port>` before the UI loads, so every call targets the sidecar.
- The backend honors **`APP_DATA_DIR`**: the SQLite DB, per-recording audio, and the
  HuggingFace/whisper/pyannote model caches all live under it (the app sets it to
  `~/Library/Application Support/com.sirina.app`). In dev, `APP_DATA_DIR`
  is unset → everything stays in `backend/data/`.

## Prerequisites (one-time)

```bash
# Rust + Tauri CLI
curl https://sh.rustup.rs -sSf | sh
cargo install tauri-cli --version '^2'
# PyInstaller (dev dep of the backend)
cd backend && uv add --dev pyinstaller
# Node >= 18 for Vite
nvm use 22
```

## Build

```bash
./scripts/build-macos-app.sh
```

This builds the UI, freezes the backend, copies it to
`frontend/src-tauri/binaries/backend-<target-triple>`, runs `cargo tauri build`, and
ad-hoc signs the app. Outputs land in `frontend/src-tauri/target/release/bundle/`.

## First launch (unsigned)

There's no paid Apple Developer signing, so Gatekeeper blocks the app the first time:

- **Right-click the app → Open** (once), **or**
- `xattr -dr com.apple.quarantine "/path/to/Sirina.app"`

Grant the **Microphone** prompt on first record. The app also expects a local **Ollama**
(`http://localhost:11434`) for summaries/chat.

## Freezing the ML stack — verified, with caveats

The minimal `backend.spec` **builds and boots** (verified: `./dist/backend --port 8000`
→ `/api/status` returns 200). It bundles the transcription core (faster-whisper,
ctranslate2, av, sounddevice) — ~260 MB. Notes from the verified run:

- **Engine falls back to faster-whisper (CPU).** `mlx`/`mlx-whisper` are **not** bundled,
  so the packaged app uses faster-whisper even on Apple Silicon. To get MLX speed, uncomment
  the `mlx`, `mlx_whisper` packages in `backend.spec` and rebuild (larger, may need tuning).
- **Diarization is not bundled.** `torch`/`pyannote` are commented out; if `DIARIZATION_ENABLED=true`
  the frozen app can't import pyannote and gracefully falls back to the baseline speaker split.
  Uncomment `torch`/`pyannote`/`lightning_fabric` to include it (adds hundreds of MB).
- **Cold start is slow** (~tens of seconds first run): a onefile binary extracts to a temp dir
  each launch, and models download to `APP_DATA_DIR/models` on first use. Subsequent runs are
  faster (warm model cache) but the extraction cost remains — acceptable for a desktop app.
- Models are never bundled — they download on first run, exactly as in dev.

Recommended path: ship the minimal (faster-whisper) binary first, then enable `mlx` (speed)
and/or `torch`+`pyannote` (diarization) one at a time, re-testing the frozen binary after each.

## App icon (needed before `cargo tauri build`)

`tauri.conf.json` references `icons/icon.icns`, which doesn't exist yet. Generate icons from
any square PNG before the first Tauri build:

```bash
cd frontend && cargo tauri icon ../path/to/icon.png   # writes src-tauri/icons/*
```

(Or drop the `bundle.icon` line to use Tauri's default icon.)

## Native system-audio capture (no BlackHole)

The build also compiles the Swift **`system-audio-capture`** sidecar (`native/system-audio-capture/`)
and bundles it as an app resource. The Tauri shell passes its path to the backend via
`SYSTEM_AUDIO_SIDECAR`, so in the packaged app the backend can capture the system output mix
(the other call participants) via **ScreenCaptureKit** — no BlackHole / Multi-Output device.

- **Permission:** ScreenCaptureKit needs **Screen Recording** (System Settings → Privacy &
  Security → Screen Recording). There's no Info.plist key for it — macOS prompts at runtime the
  first time capture starts. The backend's `--probe` reports availability; until granted, the
  app falls back to the device path. Unsigned/ad-hoc builds still get the prompt.
- **In the browser/dev** (`./dev.sh`), the sidecar isn't present → `native_system_audio` is
  `false` and the start modal shows the system-audio **device** picker (BlackHole) as before.

## Dev is unchanged

`./dev.sh` still runs the two-server flow (FastAPI `:8000` + Vite `:5173`). The Tauri
files are additive and don't affect it. Native capture is unavailable in dev (no sidecar
path / no Screen Recording grant), so the device/BlackHole path is used.
