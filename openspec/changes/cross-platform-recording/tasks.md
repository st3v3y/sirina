## 1. Rust system-audio helper (Windows and Linux)

- [x] 1.1 Create the `native/system-audio-capture-rs/` crate with the binary `system-audio-capture`, `--probe` and `--exclude-pid <pid>` arguments, and the exit codes from the existing README contract (0/2/3/4)
- [x] 1.2 Add a clock-driven output stage (`pacer`):
  - write captured samples in 20 ms blocks; once the source has delivered nothing for 200 ms, pad with zeros up to real time
  - the platform delivers 48 kHz mono s16 (WASAPI autoconvert, PulseAudio server), so there is no resampler
  - exit on a failed stdout write; SIGTERM/TerminateProcess end it as before
  - unit tests (`cargo test`) for pass-through, jitter, silence padding and the buffer bound
- [x] 1.3 Windows backend (`wasapi` crate):
  - process loopback in exclude mode for `--exclude-pid`
  - endpoint loopback on the default render device as fallback; exit non-zero when the device is invalidated so the backend restarts it
  - a `self-exclusion: on|off (…)` status line on stderr
  - `--probe` that opens and closes a stream and exits 4 when there is no render device
- [x] 1.4 Linux backend (`libpulse-simple-binding`):
  - record `@DEFAULT_MONITOR@` as s16le, 48 kHz, mono
  - `--probe` exit 4 with "no PulseAudio/PipeWire server" when the server is unreachable
  - `self-exclusion: off` on stderr
- [x] 1.5 Write `build.sh` and `build.ps1` for the crate and a README with the contract (including the continuous-stream and exit-on-broken-pipe rules) and the platform notes; link both READMEs to each other

## 2. Backend: platform-neutral utilities

- [x] 2.1 Make `psutil` and `av` direct dependencies (pyproject and uv.lock; keep `av` at the locked 17.x); check that PyInstaller collects psutil
- [x] 2.2 `audio/system_capture.py`:
  - resolve the helper name with `.exe` on Windows and the dev-build path for the Rust crate
  - pass `--exclude-pid` from `SIRINA_APP_PID`, falling back to the backend's own PID
  - start the probe and capture subprocesses with `CREATE_NO_WINDOW` on Windows
- [x] 2.3 Add a pure `probe_reason(platform, exit_code, stderr)` that maps the probe result to user-facing text; `native_available()` returns `(ok, reason)`; table-test it per platform
- [x] 2.4 Use the reason in both callers: `native_system_audio_reason` in `/api/audio/capabilities`, and the native-unavailable 400 in `api/recordings.py` (instead of the Screen Recording/BlackHole text); add an API test for the 400 text
- [x] 2.5 Replace the `pkill` in `kill_stale()` with `psutil`, matching on the exact resolved `exe()` path; add a test that an unrelated process with the same name survives
- [x] 2.6 `audio/power.py`: a `make_sleep_blocker()` factory; tests inject fakes into `PowerGuard` and check the factory's choice per platform
  - macOS: IOKit, unchanged
  - Windows: `SetThreadExecutionState` from a dedicated thread
  - Linux: a `systemd-inhibit` subprocess
  - no-op with a warning when the mechanism is missing
- [x] 2.7 `power_state()`: read AC versus battery from `psutil.sensors_battery()` on Windows and Linux; macOS keeps its tested `pmset` reader (it also knows Low Power Mode); extend `test_power_state.py`
- [x] 2.8 `processing/compress.py`:
  - encode and decode AAC `.m4a` with PyAV at 64 kbps, retrying at the encoder's default bitrate when 64 kbps is rejected
  - `available()` means "PyAV importable"
  - remove the `afconvert` calls
  - remove the afconvert skip markers in `test_compress.py` and `test_review_fixes.py`
  - add a round-trip test (length and level) and a decode test of an `afconvert`-made `.m4a` fixture
- [x] 2.9 Add `captions_reason`, `live_transcribe_reason` and `diarization_reason` to `/api/audio/capabilities` (current conditions, worded per platform); add `platform` to the status payload; update the types in `frontend/src/lib/api.ts`
- [x] 2.10 `speech_models.list_models`: hide WhisperKit, SpeakerKit and the Apple asset when not on macOS; extend `test_speech_models.py`

## 3. Desktop shell and packaging

- [x] 3.1 `lib.rs`:
  - resolve resources with `EXE_SUFFIX`
  - pass an empty env var for helpers that are absent
  - pass `SIRINA_APP_PID`
  - start the backend with `CREATE_NO_WINDOW` on Windows
  - on Linux, `chmod +x` the bundled backend and helper if they lost the bit
- [x] 3.2 Split the Tauri config into the base config plus `tauri.macos.conf.json`, `tauri.windows.conf.json` (NSIS target, `icons/icon.ico`) and `tauri.linux.conf.json` (deb target; AppImage dropped because linuxdeploy fails on the PyInstaller backend's libraries, the existing PNG icons, `Depends: libwebkit2gtk-4.1-0, libpulse0`, `Recommends: pipewire-pulse | pulseaudio`); each lists that platform's resources
- [x] 3.3 Remove the stale `binaries/backend` entry from `capabilities/default.json` (the `.ico` and PNG icons already exist)
- [x] 3.4 `backend.spec`: read the target architecture from `SIRINA_TARGET_ARCH` (default: arm64 on macOS, the host elsewhere); PortAudio comes from the sounddevice wheel on macOS/Windows and is bundled from the build machine on Linux (`entry.py` points sounddevice at it); `multiprocessing.freeze_support()` in `entry.py`
- [x] 3.5 Add `scripts/build-windows.ps1` and `scripts/build-linux.sh`, mirroring `build-macos-app.sh` without signing (frontend → PyInstaller → copy resources → helper → `tauri build`)

## 4. CI

- [x] 4.1 Make the tests portable: `test_whisperkit_engine.py` and `test_captions_stream.py` run their Python fixtures through a shared `exec_wrapper` (a shell script on POSIX, a `.cmd` file on Windows) that runs `sys.executable`
- [x] 4.2 Add `.github/workflows/build.yml`:
  - a matrix of a macOS arm64 runner with an Xcode that has the macOS 26 SDK, windows-latest and ubuntu-22.04, triggered on PRs and main
  - set up Node, Python with uv, Rust and Swift (macOS only), plus the Linux system packages
- [x] 4.3 On each platform run `npm run lint`, pytest, and `cargo test` (Windows and Linux)
- [ ] 4.4 Build the bundles and upload them as artifacts; no signing secrets and no releases

## 5. UI wording

- [x] 5.1 Replace the macOS wording with backend reasons or `platform`-aware text:
  - `Shell.tsx` 448-460: live-transcription and captions hints from `live_transcribe_reason` and `captions_reason`
  - `SpeechModels.tsx` 74-75 (left as is: the Apple asset it describes is hidden off macOS)
  - `RecordingDetail.tsx` 816, from `diarization_reason`
  - `Settings.tsx` 26, 37, 47, 53 and 298; the 329 "Open in Finder" button becomes Show in Explorer on Windows and Open folder on Linux
  - `useRecorder.ts` 126
  - help text in `settings_store.py` 67, 76 and 127
- [x] 5.2 Show `native_system_audio_reason` in the start dialog when native capture is unavailable, keeping the existing device fallback
- [x] 5.3 Start dialog: when no input matches the mic auto-pick, default to the host's default input device
- [x] 5.4 Run `npm run lint` and `npm run build` (build passes; lint has the same 15 pre-existing react-hooks errors as main, so the CI lint step is non-blocking until they are fixed)

## 6. Docs and verification

- [x] 6.1 Docs:
  - README: platform badges, a support matrix (what each feature does on each OS), Windows and Linux requirements
  - `docs/PACKAGING.md`:
    - Windows and Linux builds, plus the SmartScreen and `.deb` steps
    - the `WEBKIT_DISABLE_DMABUF_RENDERER` note and the Windows microphone privacy switch
    - self-exclusion on each platform, dev on Windows (two terminals)
    - fix the stale `externalBin`/dmg notes
  - `CONTRIBUTING.md`: ask for the OS and version instead of "your Mac model"
- [ ] 6.2 Manual checklist on Windows 11 x64:
  - install, then record a call (browser or Teams audio plus mic)
  - a quiet stretch of a minute or more with nothing playing, with no restarts in the log
  - play back a recording during capture to confirm Sirina's own audio is excluded
  - unplug or plug in a headset mid-recording (restart and gap-fill)
  - kill the backend mid-recording and confirm the helper exits
  - sleep is blocked
  - compression and re-processing work
  - the microphone privacy switch off shows a flat level
- [ ] 6.3 Manual checklist on Ubuntu 24.04 (PipeWire) and one PulseAudio distribution: the same flow, the mic default selection, and the probe failing cleanly with no audio server
- [ ] 6.4 macOS regression: native capture, compression with PyAV, re-processing an old `afconvert` recording, the model manager unchanged
