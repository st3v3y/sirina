## 1. Tauri shell

- [x] 1.1 Add a Tauri project (Rust shell) that loads the built frontend; configure it to use the existing Vite build output.
- [x] 1.2 Configure the app to bind the frontend to the sidecar's localhost port at runtime (pick a free port, pass it to the UI).

## 2. Backend sidecar (PyInstaller)

- [x] 2.1 Freeze the FastAPI backend into a single binary with PyInstaller; verify the frozen binary boots and serves `/api/status`.
- [x] 2.2 Declare the binary as a Tauri `externalBin`; spawn it on app launch (bound to `127.0.0.1:<port>`) and terminate it on quit.
- [x] 2.3 Point whisper/pyannote/HF caches and the SQLite DB at a user data dir (e.g. `~/Library/Application Support/<app>`); make `DB_PATH`/cache dirs configurable.

## 3. Permissions & unsigned distribution

- [x] 3.1 Add `NSMicrophoneUsageDescription` (+ Screen Recording usage) to the app's Info.plist / Tauri config; confirm first-run prompts.
- [x] 3.2 Build `.app`/`.dmg`; ad-hoc codesign (`codesign --force --deep --sign -`); document the Gatekeeper bypass (right-click → Open / `xattr -dr com.apple.quarantine`).
- [x] 3.3 README: install/run the packaged app; note it still needs a local Ollama.

> Native ScreenCaptureKit capture is owned by the `native-system-audio-capture` change. This change only declares the Screen Recording permission that capture consumes.

## 5. Verification

- [ ] 5.1 Launch the packaged app; confirm the backend sidecar starts, the UI loads, and `/api/status` is green — no terminal needed.
- [ ] 5.2 Record end-to-end in the packaged app (device capture); confirm transcription + summary as in dev.
- [ ] 5.3 First-run microphone (and screen-recording) prompts appear and, once granted, recording works.
- [ ] 5.4 Open an unsigned build via the documented Gatekeeper bypass.
- [x] 5.5 Confirm the DB and model caches land in the user data dir, not inside the bundle.
- [x] 5.6 Confirm `./dev.sh` still runs the two-server dev flow unchanged.
