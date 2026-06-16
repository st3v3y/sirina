## Why

Transcripts are far more useful when they say *who* spoke. With two-track capture (mic = you, system = others) we get a free first-order split with zero extra dependencies, and a People directory lets names be reused across meetings without retyping. See [docs/V2-LOCAL-REDESIGN.md §4, §6.3, §9](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Add a **baseline speaker split** from the two captured tracks: mic-track segments → "You" (or your name), system-track segments → "Others".
- Add `Speaker` (per-recording label, e.g. `Speaker 1`) and `Person` (reusable identity) models; `Segment` gains `speaker_id`.
- Let the user **rename a speaker within a recording**; renaming links that `Speaker` to a `Person` (creating it if new) and **does not** affect speakers in other recordings.
- Provide **autocomplete from existing People** when renaming, so common names are reused.
- Assign each speaker a stable display color.
- Add a **People page**: every `Person` with total meeting count, last meeting date, and rename/delete actions (delete unlinks speakers back to `Speaker N`, never deletes recordings).

## Capabilities

### New Capabilities
- `speaker-identification`: per-recording speakers, the baseline mic/system split, segment→speaker assignment, and in-recording rename linking to People with autocomplete.
- `people-directory`: the `Person` model and the People page aggregating meetings/last-seen with rename/delete.

### Modified Capabilities
<!-- None archived yet; builds on offline-transcription's transcript-view and segments. -->

## Impact

- **Data model**: new `Person`, `Speaker`; `Segment.speaker_id` populated during/after transcription.
- **Backend**: assignment step in the processing job (mic→You, system→Others); `/api/people` (list/rename/delete), `/api/recordings/{id}/speakers` (list/rename).
- **Frontend**: transcript bubbles grouped by speaker with inline rename + People autocomplete; new `/people` route.
- **Depends on**: `offline-transcription` (needs segments). Enhanced multi-speaker splitting is a separate change (`enhanced-diarization`).
