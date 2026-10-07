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
  HuggingFace model caches (WhisperKit, SpeakerKit, faster-whisper) all live under it (the app sets it to
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

## Speech helper & app size

There is one bundle — no optional variants. Speech work runs in the native **`speech-engine`**
helper (`native/speech-engine`, Swift, ~4 MB), bundled as a Tauri resource next to the backend
and signed with the app's bundle identifier:

- **Transcription** — WhisperKit (Argmax OSS, MIT, pinned to 1.1.0) with
  `large-v3-turbo` 626 MB on the Neural Engine. faster-whisper (CPU) stays in the backend
  as the fallback when the helper can't run (Intel, macOS < 14, helper missing).
- **Speaker splitting** — SpeakerKit (same package); no Hugging Face token needed.
- **Draft transcript & live captions** — Apple's on-device `SpeechTranscriber` (macOS 26+).

`./native/speech-engine/build.sh` builds it and runs `smoke-test.sh` (model checks run when
the models are in the app's cache); `scripts/build-macos-app.sh` calls it. The old
`--mlx` / `--diarization` flags are accepted but ignored: MLX, pyannote, torch and scipy are no
longer dependencies (`backend.spec` excludes them as a guard).

Models are never bundled. They download on first use (or from **Settings → Speech models**,
where unused ones can be deleted) into `APP_DATA_DIR/models/hf`. The first load of the
WhisperKit model prepares it for the Neural Engine (a few minutes, once).

Other notes:

- A frozen binary that is **ad-hoc signed** (or signed with a new identity) triggers a
  blocking macOS **Keychain authorization dialog** on startup when reading stored secrets.
  In a GUI session the user just clicks Allow; in headless testing bypass it with
  `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`. Diagnose any startup wedge with
  `kill -USR1 <pid>` — the entrypoint registers a faulthandler stack dump.
- `GET /api/_debug/diarization-check` reports whether this build can split speakers (helper +
  SpeakerKit available).
- **Cold start**: onedir (not onefile), so there is no per-launch extraction.
- Further size candidates in the backend bundle (verify the frozen app still boots after
  excluding): `onnxruntime` (~62 MB, needed by faster-whisper's VAD and the window cutter — keep),
  `grpc` (~19 MB), `sklearn` (~18 MB), `pandas` (~18 MB), `PIL` (~12 MB).

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

## Stable signing (so permissions persist)

macOS ties a permission grant (Screen Recording, Microphone) to the app's **code signature**.
With **ad-hoc** signing (`-`, the default here) every rebuild — and often every launch — looks
like a different app, so macOS re-prompts each time. Signing with a **stable identity** makes the
grant stick.

**Prefer a self-signed cert over an Apple Development cert for apps you share.** An Apple-issued
cert embeds your team's organization in the signature (e.g. `codesign -dvvv` shows
`O=<Your Company>`), which you may not want associated with the app. A **self-signed "Code Signing"
certificate** has only the name you choose and no org/team — and you don't need a paid account:

1. **Keychain Access → Certificate Assistant → Create a Certificate…**
   - Name: e.g. `Sirina Dev`
   - Identity Type: **Self-Signed Root**
   - Certificate Type: **Code Signing**  ← required; this sets the code-signing key usage
   - Verify it registered: `security find-identity -p codesigning` should list it (note: it won't
     appear under `find-identity -v`, the *valid/trusted*-only list — that's expected for a
     self-signed cert, and the build script accounts for it).
2. Build with it:
   ```bash
   CODESIGN_IDENTITY="Sirina Dev" ./scripts/build-macos-app.sh
   ```
   (If exactly one self-signed code-signing identity exists, the script auto-selects it and prints
   which one — Apple Development/Distribution/Developer ID certs are skipped so a work cert isn't
   used by accident. Override anytime with `CODESIGN_IDENTITY`.)
3. Grant Screen Recording once on first launch; subsequent launches/rebuilds with the **same**
   identity keep the grant. Ad-hoc builds print a warning that permissions will re-prompt.

This is still not Gatekeeper/notarization (that needs the paid program) — first launch may still
require right-click → Open or clearing the quarantine attribute (see "First launch" above).

## Dev is unchanged

`./dev.sh` still runs the two-server flow (FastAPI `:8000` + Vite `:5173`). The Tauri
files are additive and don't affect it. Native capture is unavailable in dev (no sidecar
path / no Screen Recording grant), so the device/BlackHole path is used.
