## Why

The baseline mic/system split only separates "you" from "everyone else". For in-room meetings (one mic, several people) or to break the "Others" track into individuals, we need real speaker diarization. `pyannote.audio` does this locally for free — the model is MIT-licensed and runs entirely on-device; the HuggingFace token is only for the one-time gated download, with no per-meeting cost or cap. See [docs/V2-LOCAL-REDESIGN.md §6.2](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Add **optional** `pyannote.audio` diarization (`pyannote/speaker-diarization-3.1`) as a step in the processing job.
- Produce per-recording speaker clusters and **assign each transcript segment to the speaker with maximum temporal overlap** (using word timestamps from transcription).
- **Configurable + token-gated**: controlled by `DIARIZATION_ENABLED` and `HF_TOKEN`. When disabled or the token is missing, **gracefully fall back** to the baseline mic/system split — no failure.
- Run diarization on MPS/GPU where available (it is not bound to whisper's CPU path).
- First-run UX: document the one-time HuggingFace setup (accept model terms, create read token).

## Capabilities

### New Capabilities
- `speaker-diarization`: optional local pyannote diarization with overlap-based segment assignment and graceful fallback to the baseline split.

### Modified Capabilities
- `speaker-identification`: speakers may now be produced by diarization clusters (`Speaker 1..N`) rather than only the mic/system split; assignment uses overlap matching.

## Impact

- **Dependencies**: add `pyannote.audio` (+ its torch usage; torch already present for whisper).
- **Backend**: diarization stage in `app/processing/`; overlap-assignment utility; config keys `DIARIZATION_ENABLED`, `HF_TOKEN`.
- **Models**: one-time download of gated pyannote models to a local cache.
- **Settings UI** (light): toggle diarization, store HF token.
- **Depends on**: `speakers-and-people` (Speaker/Person model + assignment plumbing + rename UI).
