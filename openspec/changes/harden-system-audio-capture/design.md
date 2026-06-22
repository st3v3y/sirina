## Context

The recorder captures up to two independent sources into separate WAVs and mixes them only at stop:

- **mic** — a PortAudio (`sounddevice`) `InputStream` whose callback writes mono s16le to `mic.wav`.
- **system** — on macOS, a native Swift sidecar (`native/system-audio-capture`) using ScreenCaptureKit. It emits 48 kHz mono s16le PCM on stdout; the Python `_SidecarTrack._pump` thread does a **blocking** `proc.stdout.read()` and writes bytes straight to `system.wav`. (A loopback-device path via PortAudio also exists as a fallback.)

In recording #9 the system track froze at 6.6 min while mic ran 85 min. Root cause: the sidecar builds its stream as `SCStream(filter:configuration:delegate: nil)` ([main.swift:86](../../../native/system-audio-capture/Sources/system-audio-capture/main.swift)). ScreenCaptureKit reports a stalled/stopped capture via the delegate's `stream(_:didStopWithError:)`. With no delegate, the sidecar never learns the stream died (likely on display sleep, since capture is bound to a `display` via `SCContentFilter`). It stays parked on `Task.sleep(.max)` emitting nothing, so the Python `read()` blocks forever; `system.wav` stops growing while mic continues. At stop, `_mix_wavs` zero-pads the shorter track, hiding the loss.

Constraints: macOS 13+ only for native capture; no Apple Developer signing (power assertions must not require entitlements); the recorder must remain inference-free during capture; changes should not regress the dev/loopback path.

## Goals / Non-Goals

**Goals:**
- A stopped/stalled system capture is detected within seconds, logged with a reason, and surfaced live to the UI.
- The system sidecar exits (closes stdout) on stream stop instead of becoming a silent zombie.
- Display/system idle sleep cannot silently kill capture during a recording.
- A stalled sidecar is automatically restarted, continuing the same `system.wav`, bounding loss to a short gap.
- A track that ends materially short leaves a persisted, user-visible warning; a partial track is never presented as complete.
- The same liveness monitoring covers the mic track (e.g. Bluetooth disconnect).

**Non-Goals:**
- Recovering audio that was never captured (the #9 gap is unrecoverable).
- Reworking the post-stop mix/processing pipeline beyond the incompleteness warning.
- Non-macOS system-audio capture.
- Changing the loopback-device fallback's capture mechanism (it inherits the watchdog only).

## Decisions

### 1. SCStreamDelegate + non-zero exit on stop
Attach a delegate implementing `stream(_:didStopWithError:)`. On callback: write the error to stderr (drained into the app log) and `exit(non-zero)`. This closes stdout, so the Python `read()` returns empty (`b""`) promptly instead of blocking — turning a silent hang into an observable EOF. Keep `withExtendedLifetime` so the stream/output aren't deallocated early (the existing weak-ref hazard).
*Alternative considered:* poll `SCStream` state from Python — rejected; the delegate is the supported signal and needs no IPC.

### 2. Prevent idle sleep with a scoped power assertion
Hold an assertion only while a recording is active. Two viable layers:
- **Sidecar (chosen for system capture):** wrap capture in `ProcessInfo.processInfo.beginActivity(options: [.idleSystemSleepDisabled, .idleDisplaySleepDisabled], reason:)` / `endActivity`. No entitlement required, scoped to the process lifetime.
- **Backend host:** an IOKit `IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep)` held by the recorder for the whole recording, covering the mic-only and loopback paths too.

Decision: hold the assertion in the **backend recorder** for the full recording (covers every source) **and** keep the sidecar's `beginActivity` as defense-in-depth. Release on stop and on process exit.
*Alternative considered:* shelling out to `caffeinate` — rejected as a fragile extra child process.

### 3. Per-track liveness watchdog in the recorder
Each track already tracks `frames`. Add a monotonic "last progress" timestamp updated whenever bytes are written. A single recorder-owned watchdog task (asyncio or a daemon thread) checks every ~2 s: if a track's `frames` hasn't advanced for `STALL_SECONDS` (e.g. 5 s) while recording is active, mark it `stalled` and log a WARNING. This is source-agnostic — it catches sidecar hangs, PortAudio stalls, and Bluetooth mic drops alike.
*Alternative considered:* per-track timers inside each callback — rejected; one central monitor is simpler and gives a single place to drive UI/restart.

### 4. Sidecar auto-restart, continuing the same WAV
When `_pump` sees EOF or the watchdog flags the system track stalled, `_SidecarTrack` re-spawns the sidecar (via `system_capture.spawn()`) and resumes appending to the already-open `system.wav` (the WAV stays open; we keep writing frames — the gap is simply missing samples, not a new file). Bounded retries with backoff (e.g. up to N restarts, exponential up to a cap) prevent spin when permission is permanently lost. Each restart is logged and reflected in track health.
*Trade-off:* the gap between stall detection and restarted audio is lost, but it is now seconds, not the rest of the meeting. Appending (not zero-filling) the gap keeps `system.wav` shorter than wall-clock; the mix step already pads to the mic length, and decision #6 records the shortfall.

### 5. Expose track health in `active_info`
Extend the recorder's `active_info()` and the `ActiveInfo` API model with per-track health: `{name, level, healthy, last_data_age_s}` (or a compact `mic_healthy`/`system_healthy` + `system_restarts`). The recording screen, which already polls `/active`, shows a clear inline warning ("System audio stopped — trying to reconnect") when a track is unhealthy.
*Alternative considered:* push via WebSocket — rejected; the screen already polls, keep it simple.

### 6. Persist an incompleteness warning at stop
At stop, compare each source track's duration to the recording duration. If a track is shorter than the mic by more than a tolerance (e.g. >2 s or >1%), set a `warning` field on the `Recording` (new nullable column, e.g. `warning: str | None`) describing the shortfall ("system audio captured 6.6 min of 85.2 min"). `RecordingDetail` surfaces it as a badge so the zero-padded silence is explained rather than hidden.
*Alternative considered:* a separate `track_events` table — deferred as over-engineered for current needs; a single warning string covers the user-facing need.

## Risks / Trade-offs

- **Restart loop on permanently-denied permission** → bounded retries + backoff; after the cap, stop restarting, mark the track `stopped`, and rely on the surfaced warning.
- **Power assertion leak if the app crashes mid-recording** → assertions are released by the OS on process exit; the recorder also releases in a `finally`/`stop` path, and `kill_stale()` already cleans orphaned sidecars at startup.
- **Watchdog false positive on genuine silence** → the watchdog keys on *frames written* (data flowing), not audio level; a silent-but-live stream still advances frames, so true silence isn't flagged as a stall.
- **Restart races with stop()** → guard restart on the same `_stop` event the pump already honors; `stop()` sets it before terminating, so no respawn races a teardown.
- **DB migration for the new `warning` column** → nullable with default `None`; confirm the project's schema-creation/migration approach (SQLModel `create_all` vs. an explicit migration) during apply.
- **`beginActivity`/IOKit unavailable in dev/browser runtime** → guarded behind the macOS/native path; the backend assertion is best-effort and no-ops elsewhere.
