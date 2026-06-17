# system-audio-capture

A tiny Swift sidecar that captures the macOS **system audio output mix** (everything you
hear, including remote call participants) via **ScreenCaptureKit** and streams raw PCM to
stdout — so recording a call needs **no BlackHole / virtual device**, like Jamie.

## Contract

- **Output:** raw PCM on **stdout** — `48000 Hz · mono · signed 16-bit little-endian`.
  This matches the backend recorder's WAV writer exactly, so frames are written straight
  to `system.wav`.
- **Excludes our own audio** (`excludesCurrentProcessAudio`) so we never capture the app's
  own playback (no feedback loop).

## Modes

| Command | Behavior |
| --- | --- |
| `system-audio-capture` | Capture system audio → stdout until terminated (SIGTERM). |
| `system-audio-capture --probe` | Verify it can run with Screen Recording permission. **Exit 0** = available; **non-zero** + stderr message = unavailable (used by the backend's `native_available()`). |

Exit codes: `0` ok · `2` capture failed · `3` permission denied/unavailable · `4` no display.

## Build

```bash
./build.sh        # -> build/system-audio-capture  (requires Xcode/Swift, macOS 13+)
```

## Permission

ScreenCaptureKit requires the **Screen Recording** permission (System Settings → Privacy &
Security → Screen Recording). It's granted to the *host app* (the Tauri desktop app), which
is why native capture is only available there — in the plain browser/dev setup the backend
falls back to the BlackHole device path. Running `--probe` without permission exits `3`
(verified: `Code=-3801 "user declined TCCs"`).

## How the backend uses it

The backend locates this binary via the `SYSTEM_AUDIO_SIDECAR` env var (set by the Tauri
app to the bundled path), runs `--probe` to decide availability, and—when the user picks
native capture—spawns it and pipes its stdout into the `system` track. See
`backend/app/audio/system_capture.py` and `_SidecarTrack` in `recording/recorder.py`.
