## Context

Sirina has three layers: a Tauri shell (`frontend/src-tauri`, about 135 lines of Rust and no Tauri commands), a FastAPI backend frozen with PyInstaller, and two Swift helpers.
- The **shell** starts the backend as a subprocess. It passes three paths as environment variables (`APP_DATA_DIR`, `SYSTEM_AUDIO_SIDECAR`, `SPEECH_ENGINE_HELPER`) and points the webview at `http://127.0.0.1:<port>/`.
- The **backend** records each source to its own 48 kHz mono s16le WAV. The microphone uses `sounddevice` (PortAudio). System audio comes either from `_SidecarTrack`, which reads raw PCM from the ScreenCaptureKit helper's stdout, or from a loopback input device. Every speech feature is switched on by flags in the helper's `--probe` output, so on another OS the backend already degrades to CPU faster-whisper with no captions and no speaker splitting.

What blocks Windows and Linux today:
- the ScreenCaptureKit helper
- `pkill` in `kill_stale()`
- `afconvert` in `processing/compress.py`
- IOKit and `pmset` in `audio/power.py`
- the macOS-only build: `target_arch="arm64"`, `bundle.targets: ["app"]`, an `.icns`-only icon, and no CI
- macOS wording in the UI

The development machine is an Apple Silicon Mac. Windows and Linux can only be built and run in CI, in VMs, or on borrowed hardware.

## Goals / Non-Goals

**Goals:**
- Record mic plus system audio as separate tracks on Windows 10/11 x64 and Linux x64, with no virtual audio device.
- Keep the backend's recorder, watchdog, restart and mixing logic unchanged by reusing the helper contract.
- Make sleep prevention, power state, compression and helper cleanup work on all three platforms.
- Produce installable bundles for all three platforms from CI.
- Report unavailable features with a reason instead of macOS wording.

**Non-Goals:**
- Fast transcription, captions and transcription during recording on Windows and Linux. That is `parakeet-engine-captions`; until it lands, those platforms use CPU faster-whisper after stop.
- Speaker splitting on Windows and Linux. Later, with sherpa-onnx; the existing mic/system split applies meanwhile.
- Code signing, auto-update, store distribution, and ARM64 Windows or Linux builds.
- Selecting a specific output device or application for native capture. It always captures the default output.

## Decisions

### D1. One Rust helper for Windows and Linux, with the same contract as the Swift helper

`native/system-audio-capture-rs/` is a single crate with `#[cfg(windows)]` and `#[cfg(target_os = "linux")]` backends. It builds to `system-audio-capture[.exe]`. The contract is the one in `native/system-audio-capture/README.md`:

| | |
|---|---|
| `--probe` | exit 0 = available · 2 = capture failed · 3 = permission denied or unavailable · 4 = no device or audio server; reason on stderr |
| capture mode | 48 kHz mono s16le on stdout until terminated |
| self-exclusion | a status line on stderr at start, e.g. `self-exclusion: on` or `self-exclusion: off (endpoint loopback)` |

`_SidecarTrack` already drains stderr into the log, so self-exclusion becomes visible without a protocol change.

The platform converts to the contract format itself: WASAPI with `AUTOCONVERTPCM` and the PulseAudio server both deliver 48 kHz mono s16. The helper therefore has no resampler of its own, and `system.wav` is identical across platforms.

**The helper must produce a continuous stream.** WASAPI loopback delivers no packets while nothing is playing. `_SidecarTrack`'s watchdog would read that silence as a stall and terminate and restart the helper, up to five times, and the track would end up marked incomplete. So the output stage runs on its own clock: every 20 ms it writes either the captured samples or zeros. The written sample count follows wall-clock time, not packet arrival. The Linux monitor source is continuous already, but it goes through the same output stage.

**The helper exits when the backend dies.** The shell's `child.kill()` only kills the backend, not its children. When the backend dies, the helper's stdout pipe breaks. The helper treats a failed write as the signal to exit, so it doesn't live on as an orphan. `kill_stale()` (D4) remains the safety net.

*Alternatives considered:*
- **Capture inside Python, with PyAudioWPatch or `soundcard`.** That adds a second capture path to the recorder and loses process isolation; a hung WASAPI call would wedge the backend thread.
- **Extend the Tauri shell itself.** The shell is not involved in recording today and the backend owns capture. Moving capture there would couple recording to the webview's lifetime.
- **Use only the existing "device" path**, with Stereo Mix or a `.monitor` source through PortAudio. Stereo Mix is disabled or missing on most Windows machines, and PortAudio's handling of monitor sources varies across distributions. The path stays as a manual fallback.

### D2. Windows: process loopback that excludes the app, with endpoint loopback as fallback

We use the `wasapi` crate (HEnquist/wasapi-rs). The primary mode is application loopback in **exclude** mode, targeting the Tauri app's process ID. The app's process tree includes the WebView2 processes that play recordings back, the backend and the helper.

The shell already passes paths through the environment. It also passes `SIRINA_APP_PID`, and the backend forwards it to the helper as `--exclude-pid`. Without the variable, for example in dev mode where the UI is a browser tab, the backend passes its own PID, which excludes nothing that plays audio.

Process loopback is documented from build 20348. So in practice it covers Windows 11, while Windows 10 22H2 (build 19045) uses the fallback.

Process loopback is activated through `ActivateAudioInterfaceAsync`. If that activation fails, the helper falls back to a standard loopback stream on the default render endpoint and reports `self-exclusion: off`. The recorder plays nothing during capture, so the practical impact is small.

The default render device can change mid-recording, for example when a headset is plugged in. The endpoint loopback stream then ends, the helper exits non-zero, and the existing bounded restart in `_SidecarTrack` reopens it on the new default. The track's gap-filling keeps the timing aligned. Whether process loopback follows a new default device by itself is unverified; the manual checklist covers device switching in both modes.

All helper subprocesses started by the backend get `CREATE_NO_WINDOW` on Windows: the probe, the capture helper and `systemd-inhibit`'s counterpart. That way no console window ever appears, even when the backend runs with a visible console.

### D3. Linux: PulseAudio simple API on `@DEFAULT_MONITOR@`

We use `libpulse-simple-binding` to record from `@DEFAULT_MONITOR@` at the requested format (s16le, 48000, 1 channel). The server does format conversion. This works on PulseAudio and on PipeWire through pipewire-pulse, the default on current Ubuntu and Fedora.

Self-exclusion is not attempted. It would need a PipeWire graph that links every stream except ours, which costs a lot for little benefit; it is reported as `off`.

`--probe` connects to the server, opens the monitor briefly and exits 0, or 4 with "no PulseAudio/PipeWire server".

*Alternative considered:* native PipeWire (`pipewire-rs`). It is more correct for self-exclusion but adds a C dependency that is harder to build statically. Keep it as a later option.

### D4. Backend utilities become platform-neutral

- **Helper cleanup:**
  - `kill_stale()` uses `psutil` instead of `pkill`.
  - It only kills processes whose `exe()` resolves to the configured helper path.
  - Matching by exact path rather than by name is safer than the current `pkill -f` on every OS.
- **Sleep:** a `make_sleep_blocker()` factory in `audio/power.py` returns the `SleepBlocker` for the platform. `PowerGuard` already takes its blocker as a constructor argument, so the tests inject fakes.
  - **macOS:** IOKit, unchanged.
  - **Windows:** `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)` through ctypes, from a dedicated thread. The state is per thread, so that thread lives until release.
  - **Linux:** a `systemd-inhibit --what=idle:sleep --why=… sleep infinity` subprocess, killed on release. That is simpler than D-Bus and needs no new dependency.
  - If any blocker is missing, it logs and does nothing.
  - `power_state()` uses `psutil.sensors_battery()` for AC versus battery on Windows and Linux. macOS keeps its `pmset` reader, which also reports Low Power Mode.
- **Compression:** `processing/compress.py` uses **PyAV** for AAC encode and decode on every platform, including macOS.
  - PyAV is bundled today only as a transitive dependency of faster-whisper. Because we now import it directly, it becomes a direct dependency, pinned to the locked 17.x.
  - It writes a `.m4a` at the same 64 kbps as today. Like the current `afconvert` path, it retries with the encoder's default bitrate if 64 kbps is rejected (as happens for 16 kHz mono tracks).
  - `available()` becomes "PyAV importable". The `afconvert` skip markers in `test_compress.py` and `test_review_fixes.py` are removed, so those tests run on every platform.
  - One code path replaces two, and old `afconvert` files decode with PyAV since they are standard AAC-in-MP4.
  - *Alternative:* keep `afconvert` on macOS and use PyAV elsewhere. That means two encoders to test for no benefit.
- **Capabilities:**
  - `system_capture.native_available()` returns `(ok, reason)`. The reason comes from a pure function that maps the probe's exit code and stderr to user-facing text for each platform.
  - Both callers use it:
    - `/api/audio/capabilities` adds `native_system_audio_reason`.
    - The 400 that `api/recordings.py` returns when native is requested but unavailable carries that reason. Today it always says "Grant Screen Recording permission… or pick BlackHole".
  - `/api/audio/capabilities` also gains `captions_reason`, `live_transcribe_reason` and `diarization_reason`. For now they hold the current conditions, worded per platform (e.g. "Needs macOS 26 or newer", "Not available on Windows yet"). `parakeet-engine-captions` later changes how they are computed, not the fields.
  - The status payload adds `platform` (`macos` | `windows` | `linux`) so the UI can pick wording.
  - Existing fields stay, so this is additive.

### D5. Shell resolves resources per platform

- `lib.rs` builds each resource name with `std::env::consts::EXE_SUFFIX`. If a resource doesn't exist, it passes an empty variable instead of a broken path.
- The macOS `speech-engine` resource is listed only in the macOS config. Tauri merges `tauri.macos.conf.json`, `tauri.windows.conf.json` and `tauri.linux.conf.json` over the base config, so per-platform `bundle.resources`, `targets` and icons go there.
- The base config keeps the shared settings.
- The stale `binaries/backend` shell-sidecar allow-list entry is removed.

The PyInstaller backend is built with `console=True`. On Windows, `CREATE_NO_WINDOW` is set when starting it, so no console window appears. The `main.rs` `windows_subsystem` attribute already covers the shell itself.

Tauri resources may lose their executable bit in the `.deb` or AppImage. On Linux, the shell checks the bundled backend and helper and runs `chmod +x` if needed before spawning them.

### D6. PyInstaller and builds

- `backend.spec` reads the target architecture from the environment, defaulting to the host architecture instead of hard-coding `arm64`.
- PyInstaller's `sounddevice` hook bundles PortAudio on Windows. On Linux, the build machine's `libportaudio2` is collected.
- New scripts mirror `build-macos-app.sh` without the signing steps:
  - `scripts/build-windows.ps1`
  - `scripts/build-linux.sh`
- `.github/workflows/build.yml` runs a matrix of a macOS arm64 runner, `windows-latest` and `ubuntu-22.04`. The macOS runner's Xcode must have the macOS 26 SDK, because `speech-engine` uses `SpeechTranscriber`.
  1. Set up Node, then run `npm run lint` and the frontend build.
  2. Set up Python and uv sync, then run pytest.
  3. Run `cargo test` for the Rust helper (Windows and Linux).
  4. Build the PyInstaller backend.
  5. Build the native helper: Swift on macOS, cargo elsewhere.
  6. Run `tauri build`.
  7. Upload the bundles as artifacts.
- Linux builds on 22.04 so the AppImage's glibc floor stays low. They need the `libwebkit2gtk-4.1-dev`, `libpulse-dev` and `libportaudio2` packages.
- Two tests fake helpers with `#!/bin/sh` wrapper scripts, which can't run on Windows: `test_whisperkit_engine.py` and `test_captions_stream.py`. They switch to running the existing Python fixtures via `sys.executable`, which works on every platform.
- The `.deb` declares `Depends: libwebkit2gtk-4.1-0, libpulse0` and `Recommends: pipewire-pulse | pulseaudio`. `libpulse0` is the client library and talks to pipewire-pulse too.
- Development on Windows: `dev.sh` is bash-only. The docs give the two commands to run in separate terminals instead of adding a second script.

### D7. UI wording

Strings that name macOS are replaced by capability reasons from the backend, or chosen by `platform`.
- **Frontend:**
  - `Shell.tsx`: the captions and live-transcription hints at 448-460.
  - `SpeechModels.tsx:74-75`: "managed by macOS".
  - `RecordingDetail.tsx:816`.
  - `Settings.tsx`:
    - 26, 37, 47, 53 and 298: "on your Mac", Neural Engine, keeping "the Mac" responsive.
    - 329: the button becomes "Show in Explorer" on Windows and "Open folder" on Linux.
  - `useRecorder.ts:126`.
- **Backend:**
  - The help text in `settings_store.py` (67, 76, 127).
  - The name of the Apple speech model in `speech_models.py`.
  - The native-unavailable error in `api/recordings.py`.

Because the backend owns the reasons, `parakeet-engine-captions` can change what is available without touching these strings again.

## Risks / Trade-offs

- **No Windows or Linux machine on hand.** Capture and sleep behaviour can't be verified from macOS. → CI proves the bundles build and the backend tests pass. Manual checks run in UTM VMs (Ubuntu ARM can validate the Linux code path, built natively for arm64 in the VM) and on at least one real x64 Windows machine before release. Tasks include a manual test checklist.
- **Behaviour of WASAPI process loopback differs between Windows builds.** → Endpoint loopback as fallback, the self-exclusion status in the log, and the probe reporting the mode.
- **The default device changes mid-call (headset plugged in).** → Helper exit, bounded restart and gap-fill already exist in `_SidecarTrack` (from `harden-system-audio-capture`). The manual tests cover it.
- **Linux audio stacks vary** (pure ALSA, or PipeWire without pipewire-pulse). → Unsupported: the probe reports "no PulseAudio/PipeWire server" and the device path remains available.
- **AppImage and WebKitGTK quirks** (e.g. GPU or DMA-BUF rendering bugs on NVIDIA). → Document `WEBKIT_DISABLE_DMABUF_RENDERER=1`. The shell may set it by default if testing shows it's needed.
- **Unsigned Windows installer.** SmartScreen warns, and some antivirus tools flag PyInstaller binaries. → Document it; signing is a later change.
- **PyAV replacing `afconvert` on macOS** could change file size or quality slightly. → Same AAC bitrate. A round-trip test (WAV → m4a → WAV) checks length and level.
- **Windows microphone privacy switch.** "Let desktop apps access your microphone" can be off. WASAPI then delivers silence and no error, and the level meter stays flat. → `docs/PACKAGING.md` documents it, and the manual checklist covers it. Detecting it automatically is left for later.
- **Linux microphone choice.** PortAudio lists ALSA devices plus `pulse`/`default`, and the UI's auto-pick regex (`/microphone|mic/i`) may match nothing, or a busy `hw:` device. → The start dialog defaults to the host's default input when nothing matches. The manual checklist covers it.
- **The Linux sink suspends when idle**, which could stall the monitor source. → Recording from the monitor keeps the sink active on PulseAudio and PipeWire. The helper's own clock (D1) keeps the track continuous regardless, and the manual checklist covers a quiet stretch of a minute or more.

## Migration Plan

- No data migration. Existing `.m4a` files stay valid (PyAV decodes them).
- Settings and DB are unchanged; the capability fields are additive.
- macOS behaviour is unchanged except for the compression encoder. Ship macOS first from CI to confirm parity, then publish Windows and Linux builds as "preview".
- Rollback: macOS can go back to the previous build. Windows and Linux are new, so they have nothing to roll back.

## Open Questions

- Whether a Linux AppImage built on Ubuntu 22.04 runs on the distributions users actually have. Decide after the first preview feedback.
- The `site/` landing page and download links are updated when Windows and Linux builds are first published, not in this change.
