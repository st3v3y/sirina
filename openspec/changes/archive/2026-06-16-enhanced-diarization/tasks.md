## 1. Dependency & config

- [x] 1.1 Add `pyannote.audio` to `backend/pyproject.toml`; `uv lock` + `uv sync`.
- [x] 1.2 Add `diarization_enabled: bool = False` and `hf_token: str = ""` to `app/config.py`; document `DIARIZATION_ENABLED` / `HF_TOKEN` in `.env.example`.

## 2. Diarizer

- [x] 2.1 Create `app/processing/diarize.py` with a `Diarizer` that lazily loads `pyannote/speaker-diarization-3.1` via `Pipeline.from_pretrained(use_auth_token=HF_TOKEN)` (MPS if available) and runs inference in a thread executor.
- [x] 2.2 `diarize(path) -> list[(start, end, cluster)]`; `is_available()` returns whether it's enabled + a token is present.
- [x] 2.3 Add an overlap-assignment helper: given whisper lines + diarization turns, return a cluster label per line (max temporal overlap; nearest cluster as fallback).

## 3. Processor integration

- [x] 3.1 In `app/processing/job.py` `_process()`: when diarization is available, diarize the system track (two-track) or the single track; create `Speaker 1..N` from clusters (stable colours); assign segments by overlap. Keep mic → "You" for two-track.
- [x] 3.2 Wrap diarization in try/except: on disabled/missing-token/error, fall back to the current baseline split; never fail the recording.

## 4. Status & docs

- [x] 4.1 Surface diarization state (on/off/available) in `GET /api/status`.
- [x] 4.2 README: document the one-time HuggingFace setup (accept `pyannote/segmentation-3.0` + `pyannote/speaker-diarization-3.1` terms, create a read token, set `HF_TOKEN` + `DIARIZATION_ENABLED=true`); note it's free/local/unlimited.

## 5. Verification

- [x] 5.1 With diarization disabled (default): confirm the baseline mic/system split still works and no diarization model loads.
- [x] 5.2 With diarization enabled + token: a multi-speaker single-track clip yields multiple `Speaker N`; segments assigned by overlap.
- [x] 5.3 Two-track + diarization: mic stays "You"; system track splits into `Speaker N`.
- [x] 5.4 Enabled but no token / forced error: recording still completes via the baseline split (no failure).
- [x] 5.5 Renaming diarized `Speaker N` into People works (existing flow) end-to-end.
