## 1. Sidecar: detect and report stream stop

- [x] 1.1 Add an `SCStreamDelegate` to the sidecar that implements `stream(_:didStopWithError:)`; pass it as the `delegate` in `SCStream(...)` instead of `nil` (main.swift)
- [x] 1.2 On `didStopWithError`, write the error reason to stderr and `exit(non-zero)` so stdout closes and the consumer sees EOF
- [x] 1.3 Keep `stream`/`output` retained for the capture lifetime (preserve the existing weak-ref fix) and verify the delegate fires on display sleep / lock
- [x] 1.4 Rebuild the sidecar (`native/system-audio-capture/build.sh`) and confirm `--probe` still works

## 2. Sidecar: prevent idle sleep

- [x] 2.1 Wrap capture in `ProcessInfo.processInfo.beginActivity(options: [.idleSystemSleepDisabled, .idleDisplaySleepDisabled], reason:)` and end it on teardown (main.swift)
- [ ] 2.2 Manually verify the display does not sleep while the sidecar is capturing

## 3. Backend: power assertion for the whole recording

- [x] 3.1 Add an IOKit power-assertion helper (best-effort, macOS-only, no-op elsewhere) to create/release `PreventUserIdleSystemSleep`
- [x] 3.2 Acquire the assertion in `Recorder.start` and release it in `Recorder.stop` and in the error/`finally` path so it can't leak

## 4. Backend: per-track liveness watchdog

- [x] 4.1 Track a monotonic "last progress" timestamp on `_Track` and `_SidecarTrack`, updated whenever frames are written
- [x] 4.2 Add per-track health state (healthy / stalled / stopped) and a `STALL_SECONDS` threshold
- [x] 4.3 Add a single recorder-owned watchdog (asyncio task or daemon thread) that flags a track unhealthy + logs a WARNING when its frame count hasn't advanced for `STALL_SECONDS` while recording is active
- [x] 4.4 Ensure the watchdog covers the mic track too (device-disconnect case) and stops cleanly on `Recorder.stop`

## 5. Backend: sidecar auto-restart continuing the same track

- [x] 5.1 In `_SidecarTrack._pump`, on EOF (or watchdog stall) re-spawn via `system_capture.spawn()` and resume appending to the already-open `system.wav`
- [x] 5.2 Add bounded retries with backoff (cap restarts; exponential up to a max) and log each restart; after the cap, mark the track `stopped` and stop respawning
- [x] 5.3 Guard restart against `stop()` (honor the existing `_stop` event) so teardown never races a respawn
- [x] 5.4 Surface restart count in track health

## 6. Backend: surface health + incompleteness

- [x] 6.1 Extend `Recorder.active_info()` with per-track health (e.g. `mic_healthy`, `system_healthy`, `system_restarts`, last-data age)
- [x] 6.2 Extend the `ActiveInfo` API model in `api/recordings.py` with the new fields
- [x] 6.3 Add a nullable `warning: str | None` column to the `Recording` model and confirm the schema-creation/migration path
- [x] 6.4 In `Recorder.stop`, compare each source track's duration to the recording duration; if materially short (>2 s or >1%), set `Recording.warning` describing the shortfall
- [x] 6.5 Expose `warning` in the `RecordingDetail` response

## 7. Frontend: live and post-hoc indication

- [x] 7.1 Add the new health fields to `ActiveInfo` and a `warning` field to the recording detail type in `lib/api.ts`
- [x] 7.2 In `RecordingScreen.tsx`, show a clear inline warning when a track is unhealthy (e.g. "System audio stopped — trying to reconnect")
- [x] 7.3 In `RecordingDetail.tsx`, show an incompleteness badge when the recording has a `warning`

## 8. Verification

- [ ] 8.1 Reproduce the failure mode (force the sidecar to stop, e.g. revoke permission / sleep display) and confirm: EOF is observed promptly, the watchdog flags it, restart fires, and the UI shows the warning
- [ ] 8.2 Confirm a full two-track recording with no interruption produces equal-length tracks and no warning
- [ ] 8.3 Confirm idle sleep is prevented during a recording and restored after stop
- [x] 8.4 Run backend tests / linters and frontend type-check; update the relevant openspec specs on archive
