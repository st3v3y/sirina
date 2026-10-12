# Packaging the desktop app (Tauri)

macOS is covered first; Windows and Linux are in [Windows and Linux](#windows-and-linux).

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
| `frontend/src-tauri/tauri.conf.json` | Shared Tauri config (dist dir, icons) |
| `frontend/src-tauri/tauri.{macos,windows,linux}.conf.json` | Per-platform bundle targets and resources (macOS `.app` + min version 13; Windows NSIS; Linux deb + AppImage) |
| `frontend/src-tauri/tauri.appimage.conf.json` | Linux resources for the AppImage pass: the helper only (the backend is added afterwards, see [AppImage](#appimage)) |
| `frontend/src-tauri/src/lib.rs` | Picks a free port, spawns the bundled backend with `APP_DATA_DIR`, the helper paths and `SIRINA_APP_PID`, injects `window.__BACKEND_URL__`, creates the window |
| `frontend/src-tauri/Info.plist` | `NSMicrophoneUsageDescription` (first-run mic prompt) |
| `frontend/src-tauri/capabilities/default.json` | Default window permissions (the backend is started with `std::process`, not the shell plugin) |
| `backend/packaging/entry.py` | Frozen entry: `uvicorn` with `--host/--port` |
| `backend/packaging/backend.spec` | PyInstaller spec (transcription core; heavy ML extras commented) |
| `scripts/build-macos-app.sh` | End-to-end macOS build + ad-hoc sign |
| `scripts/build-windows.ps1`, `scripts/build-linux.sh` | End-to-end Windows / Linux builds (unsigned) |
| `scripts/appimage-add-backend.sh`, `scripts/smoke-linux-appimage.sh` | Add the frozen backend to the AppImage; smoke-test the AppImage (CI) |
| `.github/workflows/build.yml` | CI: tests and bundles for all three platforms, uploaded as run artifacts |

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

- **System Settings → Privacy & Security → Open Anyway** (once; since macOS 15, right-click →
  Open no longer bypasses Gatekeeper), **or**
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

This is still not Gatekeeper/notarization (that needs the paid program) — first launch still
needs **Open Anyway** or clearing the quarantine attribute (see "First launch" above).

## Releases

`.github/workflows/release.yml` builds the app on a `macos-26` runner (the speech helper needs
the macOS 26 SDK) and publishes `Sirina-macOS-arm64.dmg` to a GitHub release. The DMG name has
no version, so `releases/latest/download/Sirina-macOS-arm64.dmg` always points at the newest
one.

To release:

1. Bump `version` in `frontend/src-tauri/tauri.conf.json` (and `Cargo.toml`), and merge.
2. Tag `main` and push the tag. The workflow fails if the tag and the version differ.
   ```bash
   git tag v0.2.0 && git push origin v0.2.0
   ```
   A tag with a `-` (e.g. `v0.2.0-rc.1`) is published as a pre-release.

Pull requests that touch packaging also run the build (without publishing), and the DMG is
kept as a workflow artifact for 7 days.

**Signing in CI.** Without secrets, CI builds are ad-hoc signed. To sign with your stable
self-signed certificate (so permission grants survive updates), export it once and add two
repository secrets:

```bash
# Keychain Access → My Certificates → right-click "Sirina Dev" → Export… → sirina-dev.p12
base64 -i sirina-dev.p12 | gh secret set MACOS_SIGNING_CERT_P12
gh secret set MACOS_SIGNING_CERT_PASSWORD   # the export password
```

Every release signed with the same certificate keeps the user's grants.

## Dev is unchanged

`./dev.sh` still runs the two-server flow (FastAPI `:8000` + Vite `:5173`). The Tauri
files are additive and don't affect it. Native capture is unavailable in dev (no sidecar
path / no Screen Recording grant), so the device/BlackHole path is used.

## Windows and Linux

Preview builds. They record the microphone and the call audio as separate tracks, then
transcribe with faster-whisper on the CPU after the recording stops. Transcription during
recording, live captions and speaker splitting are macOS-only for now; the app shows why
the options are off.

### Build

```bash
./scripts/build-linux.sh          # Linux → bundle/deb/*.deb, bundle/appimage/*.AppImage
```

```powershell
./scripts/build-windows.ps1       # Windows → bundle\nsis\Sirina_*_x64-setup.exe
```

Prerequisites: Rust, uv, Node ≥ 18. On Linux also Tauri's WebKitGTK deps
(`libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev patchelf`), `libpulse-dev` for the capture
helper, `libportaudio2`, which is bundled into the backend (a fresh desktop may not have
it), and `squashfs-tools` for the AppImage. The scripts use `cargo tauri` when installed, else the frontend's pinned `@tauri-apps/cli` (`npm run tauri`). CI builds both
(plus macOS) on every pull request; download the bundles from the run's artifacts.

#### AppImage

Tauri's AppImage step runs linuxdeploy over every ELF file in the AppDir. On the PyInstaller
backend that fails (it can't resolve ctranslate2's vendored `libgomp-<hash>.so.1.0.0`), and
if it succeeded it would rewrite the rpaths of the backend's libraries. So the backend never
goes through linuxdeploy:

1. `tauri build --bundles deb` builds the app and the `.deb` with every resource.
2. `tauri bundle --bundles appimage --config tauri.appimage.conf.json` bundles the same
   binary as an AppImage whose resources are only the capture helper. linuxdeploy bundles
   WebKitGTK, GTK and libpulse as usual.
3. `scripts/appimage-add-backend.sh` unpacks the AppImage's squashfs, copies the frozen
   backend to `usr/lib/Sirina/resources/backend/` unchanged, and repacks it behind the
   same runtime with the same compression.

The shell finds the backend at run time as it does in the `.deb`
(`<resource dir>/resources/backend/backend`), and it runs straight from the AppImage's
read-only mount. Don't run a bare `tauri build` on Linux: with both targets it fails at the
AppImage step; use the script, or `--bundles deb`.

CI then runs `scripts/smoke-linux-appimage.sh`: it unpacks the AppImage, checks the bundled
backend is byte-identical to the build's, starts it and waits for `/api/status`, and
finally launches the AppImage under Xvfb and checks the shell started the backend from the
AppImage's mount and that it answers.

### First launch (unsigned)

- **Windows:** SmartScreen says the app is unrecognized: choose **More info → Run anyway**.
  Some antivirus tools flag PyInstaller binaries; that is a false positive of unsigned builds.
- **Linux:** `chmod +x Sirina_*.AppImage && ./Sirina_*.AppImage`, or `sudo apt install
  ./Sirina_*.deb`. The AppImage needs FUSE to mount itself; without it, run it with
  `--appimage-extract-and-run`. The `.deb` depends on `libpulse0` and recommends
  `pipewire-pulse` or `pulseaudio`. If the window stays blank or flickers (seen with some NVIDIA drivers), start
  it with `WEBKIT_DISABLE_DMABUF_RENDERER=1`.

There are no permission prompts. On Windows, the microphone is silent (a flat level meter)
if *Settings → Privacy & security → Microphone → Let desktop apps access your microphone* is
off.

### Call audio

`native/system-audio-capture-rs/` (Rust) follows the same contract as the Swift helper:
48 kHz mono s16le on stdout, `--probe` exit codes, a continuous stream (silence is filled in
while nothing plays), and it exits when the backend goes away.

| | Source | Sirina's own audio left out |
| --- | --- | --- |
| Windows 11 | WASAPI process loopback, excluding the app's process tree (`SIRINA_APP_PID`) | yes |
| Windows 10 | WASAPI loopback of the default output device | no |
| Linux | Monitor of the default PulseAudio/PipeWire sink | no |

Sirina plays nothing while recording, so "no" only matters if you play back an old
recording during a call. When the default output device changes (a headset is plugged in),
the helper exits and the backend restarts it on the new device and fills the gap with
silence. If no sound server or output device is found, the start dialog says so and
offers the loopback-device fallback.

### Development on Windows

`dev.sh` needs bash. Run the two servers in separate terminals instead:

```powershell
cd backend; uv run uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev -- --port 5283
```

Build the capture helper once (`native/system-audio-capture-rs/build.ps1`); the backend
finds the dev build and captures natively.

