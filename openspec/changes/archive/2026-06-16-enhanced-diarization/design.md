## Context

The processor currently does a baseline speaker split: mic → "You", system → "Others" (or one speaker for a single track). That separates you from everyone else but cannot tell apart multiple people on the system track, nor multiple people in an in-room single-mic recording. `pyannote.audio` provides local speaker diarization that clusters a track into distinct speakers. It is free (MIT-licensed, runs on-device); the HuggingFace token only gates the one-time model download.

## Goals / Non-Goals

**Goals:**
- Optional diarization that splits a track into `Speaker 1..N`.
- Assign each transcript segment to the maximally overlapping diarization cluster.
- Strictly gated (`DIARIZATION_ENABLED` + `HF_TOKEN`) with graceful fallback to the baseline split on disabled/missing-token/error.

**Non-Goals:**
- Naming speakers automatically — diarization gives anonymous clusters; the user renames them via the existing speakers-and-people flow.
- Diarizing the microphone track of a two-track recording — it's just you, kept as "You".
- A heavyweight settings UI; configuration is env-driven, with on/off surfaced in status.

## Decisions

- **Diarize the non-mic audio only.** Two-track: keep mic → "You"; diarize the system track into `Speaker 1..N`. Single-track: diarize the one track. This preserves the high-confidence "you vs them" signal and only spends diarization on the ambiguous audio.
- **`Diarizer` in `app/processing/diarize.py`.** Lazily loads `pyannote/speaker-diarization-3.1` via `Pipeline.from_pretrained(..., use_auth_token=HF_TOKEN)` on first use; runs inference in a thread executor (it's blocking). Uses MPS when available (independent of whisper's CPU path).
- **Overlap assignment utility.** Given whisper segments `[(start,end,text)]` and diarization turns `[(start,end,cluster)]`, assign each segment the cluster with max overlap; segments with no overlap fall to the nearest/most-common cluster. Clusters map to `Speaker` rows in first-appearance order, labelled `Speaker 1..N`, each with a stable colour (reuse the existing palette).
- **Gating + fallback.** `DIARIZATION_ENABLED` (default off) and `HF_TOKEN`. In `_process()`: if enabled and token present, try diarization for the relevant track; wrap in try/except so any failure logs and reverts to the current baseline path. A diarization failure never fails the recording.
- **Config + status.** Add `diarization_enabled` and `hf_token` to settings; surface `diarization` (on/off/available) in `/api/status` so the UI can show it. No token-entry UI in this change (env-configured); documented one-time HF setup in README.
- **Dependency.** Add `pyannote.audio` to `pyproject.toml` (torch already present). Heavy, but only loaded when diarization runs.

## Risks / Trade-offs

- [pyannote model download is gated + large] → One-time; documented HF setup. Off by default so users who don't want it pay nothing.
- [Diarization is slow on CPU] → Runs on MPS where available; it's offline/background; single-flight queue already serializes work.
- [Diarization API/version drift] → Pin a known-good `pyannote.audio`; guard import and load so absence/failure falls back cleanly.
- [Diarization and whisper-VAD segment boundaries don't align perfectly] → Resolved during verification: segment-level overlap is NOT sufficient — faster-whisper can emit one segment spanning a speaker change, collapsing it to a single speaker. Diarized assignment therefore operates at WORD level (word timestamps are already captured): each word is assigned to its max-overlap cluster and consecutive same-speaker words are regrouped into segments.
- [pyannote 4.x uses the gated `speaker-diarization-community-1` model and a `DiarizeOutput` return type] → Verified against pyannote.audio 4.0.4: model id is configurable (`DIARIZATION_MODEL`, default community-1), `from_pretrained(token=...)` with a 3.x `use_auth_token` fallback, and the `DiarizeOutput.exclusive_speaker_diarization` annotation is used for clean alignment.

## Migration Plan

No schema change (Speaker/Segment already exist). Add config keys + an optional dependency. Off by default; enabling requires `DIARIZATION_ENABLED=true` + `HF_TOKEN` and accepting the model terms on HuggingFace once.

## Open Questions

- Whether to diarize the mic track too when a two-track recording's "You" mic actually has multiple people near it. Lean: no — mic is treated as you; revisit if needed.
- Word-level vs segment-level overlap assignment. Lean: segment-level now (simpler); word timestamps already captured if we want to refine later.
