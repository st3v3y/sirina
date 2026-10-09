# system-audio-capture (Windows, Linux)

Captures the system audio output mix (everything you hear, including remote call
participants) and streams raw PCM to stdout, so recording a call needs no virtual audio
device. It is the Windows/Linux counterpart of the macOS Swift helper in
[`../system-audio-capture/`](../system-audio-capture/README.md), with the same contract.

## Contract

- **Output:** raw PCM on **stdout**: `48000 Hz · mono · signed 16-bit little-endian`.
- **Continuous:** the stream follows wall-clock time. When the source delivers nothing
  (Windows loopback is silent while nothing plays) the gap is filled with silence after
  200 ms, so the backend never sees a stalled track.
- **Exits with its reader:** when stdout closes (the backend died) the helper exits.
- **Self-exclusion status:** one line on stderr after capture starts:
  `self-exclusion: on` or `self-exclusion: off (<why>)`.

| Command | Behavior |
| --- | --- |
| `system-audio-capture [--exclude-pid PID]` | Capture → stdout until terminated. |
| `system-audio-capture --probe` | Exit 0 if capture can run; otherwise non-zero with the reason on stderr. |

Exit codes: `0` ok · `2` capture failed · `3` unavailable · `4` no output device / sound server.

## Platforms

| | Source | Leaves out Sirina's own audio |
| --- | --- | --- |
| Windows 11 | WASAPI process loopback, excluding `--exclude-pid`'s process tree | yes |
| Windows 10 | WASAPI loopback of the default output device (fallback) | no |
| Linux | Monitor of the default sink (`@DEFAULT_MONITOR@`) via the PulseAudio API; works with PulseAudio and PipeWire (pipewire-pulse) | no |

WASAPI and the PulseAudio server convert to 48 kHz mono s16 themselves. When the default
output device changes on Windows the endpoint stream ends and the helper exits with code
2; the backend restarts it on the new default and fills the gap.

## Build

```bash
./build.sh        # Linux: needs libpulse-dev; -> target/release/system-audio-capture
```

```powershell
./build.ps1       # Windows: -> target\release\system-audio-capture.exe
```

`cargo test` runs the pacing tests on any OS (including macOS, where the binary itself
only reports "unsupported platform").

## How the backend uses it

The desktop app passes the bundled path in `SYSTEM_AUDIO_SIDECAR` and its own process id
in `SIRINA_APP_PID`. The backend runs `--probe` to decide availability and then spawns the
helper with `--exclude-pid`, piping stdout into the `system` track. See
`backend/app/audio/system_capture.py` and `_SidecarTrack` in `recording/recorder.py`.
