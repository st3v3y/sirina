## Why

In recording #9 the microphone captured the full ~85 minutes while the system-audio (ScreenCaptureKit) track silently froze at 6.6 minutes — most likely when the display slept. Nothing crashed and nothing was logged: the sidecar's `SCStream` was created with `delegate: nil`, so a stream-stop error was never observed; the sidecar kept running but emitted no audio; and the Python reader blocked forever on a read that never returned. The far-end of an entire meeting was lost with no warning to the user, and the mixer silently zero-padded the gap. Capture must fail loud, recover when it can, and never present a partial track as complete.

## What Changes

- **Sidecar observes its own stream**: the `SCStream` gets a delegate that handles `didStopWithError`; on stop/error the sidecar logs the reason and exits non-zero (closing stdout) instead of running on as a silent zombie.
- **Prevent idle/display sleep while recording**: hold a power assertion for the duration of a recording so display/system sleep can't silently kill the capture (covers both the native sidecar and PortAudio streams).
- **Per-track health watchdog (Python)**: the recorder monitors data progress for every track (mic and system). Detection keys on *frames written*, not audio level, so a genuinely silent-but-live source is never falsely flagged. A track that stops producing data while recording is active is marked unhealthy and logged, rather than failing silently. This covers the mic too — a Bluetooth/USB input that disconnects mid-recording (e.g. the "Soundcore A1" used in #9) would otherwise truncate the mic just as silently.
- **Auto-restart the system sidecar on stall/exit**: when the sidecar EOFs or stalls, the recorder re-spawns it and continues appending to the same `system.wav`, bounding the loss to a short gap instead of the rest of the meeting. Restarts are bounded with backoff so a permanently-revoked permission can't cause a respawn loop.
- **Surface track health to the UI**: `active_info` exposes per-track health (healthy / stalled / stopped); the recording screen shows a clear warning when a track stops delivering audio so the user can react live.
- **Record an incompleteness warning**: when a track ends materially shorter than the recording (the mixer would zero-pad a large gap), persist a warning on the recording so the partial far-end is visible after the fact instead of hidden behind silence.

## Capabilities

### New Capabilities
- `recording-health-monitoring`: per-track liveness watchdog during capture, surfacing track health to clients live, and persisting an incompleteness warning when a track ends short.

### Modified Capabilities
- `native-system-audio-capture`: the native helper MUST detect and report stream-stop/permission-loss (via the stream delegate) and exit rather than emit silence; the recorder MAY restart the helper and continue the same system track.
- `audio-recording`: capture MUST keep the surviving track(s) recording when one source fails, MUST prevent idle/display sleep for the duration of a recording, and MUST NOT present a partial track as complete.

## Impact

- **Native helper**: `native/system-audio-capture/Sources/system-audio-capture/main.swift` — add `SCStreamDelegate` (`didStopWithError`), exit non-zero on stop; add a power-assertion / `beginActivity` hold during capture.
- **Backend**: `backend/app/recording/recorder.py` (`_SidecarTrack`/`_Track` watchdog + sidecar restart + gap-aware mix warning), `backend/app/audio/system_capture.py` (respawn helper), `backend/app/api/recordings.py` (`ActiveInfo` track health fields), `backend/app/models.py` (recording warning field).
- **Frontend**: `frontend/src/lib/api.ts`, `frontend/src/pages/RecordingScreen.tsx`, `frontend/src/pages/RecordingDetail.tsx` — live track-health warning and a post-hoc incompleteness badge.
- **Platform**: macOS-only behavior (ScreenCaptureKit + IOKit power assertions); no new third-party dependencies.
