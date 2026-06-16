## Context

Today the transcription processor transcribes only the mixed track (`Recording.audio_path`) and writes every `Segment` with `speaker_label = "Speaker 1"`. The recorder already captures `mic.wav` and (optionally) `system.wav` separately — a free first-order speaker split we don't yet use. This change adds real speakers, a People directory, and per-recording rename with autocomplete.

## Goals / Non-Goals

**Goals:**
- A `Speaker` (per-recording) and `Person` (reusable identity) model; segments link to speakers.
- Baseline split: transcribe mic and system tracks separately → "You" / "Others".
- Rename a speaker in a recording → links to a Person (autocompleted from existing People).
- People directory with counts, last-seen, rename (global), delete (unlink).

**Non-Goals:**
- Multi-speaker diarization within a single track (that is `enhanced-diarization`).
- Changing capture or summaries.

## Decisions

- **New tables `Person(id, name, created_at)` and `Speaker(id, recording_id, label, person_id?, color?)`.** Replace `Segment.speaker_label: str` with `Segment.speaker_id` (FK to `Speaker`). Clean reset — no data migration. `Speaker.label` holds the default ("You"/"Others"/"Speaker 1"); display name is the linked Person's name when set, else the label.
  - *Alternative*: keep `speaker_label` string and a parallel link table. Rejected — a `Speaker` row per recording is the natural home for label + person link + color.
- **Per-track transcription in the processor.** Modify `_process()`: if `mic_path` and `system_path` both exist, create two speakers ("You" from mic, "Others" from system), transcribe each track, tag its segments with that speaker. Otherwise create one speaker (from the recording's mic track / label) and transcribe the single track. Merge segments sorted by `start_ts`.
  - This means transcribing up to two files per recording (sequential, single-flight is fine).
- **Recording label.** The recorder currently accepts but ignores `label`. Store it on `Recording` (`label` column) and use it as the single-speaker / "You" default so the user's chosen name flows through.
- **Rename API.** `PUT /api/recordings/{id}/speakers/{speaker_id}` `{name}` → find-or-create Person, set `speaker.person_id`. `GET /api/people` powers autocomplete.
- **People API.** `GET /api/people` (with counts + last-seen), `PUT /api/people/{id}` (rename), `DELETE /api/people/{id}` (null out linked `person_id`).
- **Color.** Assign a stable color per speaker at creation (palette index by speaker order); the frontend already colors by a stable key.

## Risks / Trade-offs

- [Transcribing two tracks doubles processing time for two-track recordings] → Acceptable; offline + single-flight. Mic-only recordings are unaffected.
- [System track contains multiple people but baseline lumps them as "Others"] → Documented; `enhanced-diarization` refines this. Baseline is still useful (you vs everyone).
- [Replacing `speaker_label` with `speaker_id` touches the processor + exporters + detail view] → Coordinated in tasks; clean reset means no data to migrate.

## Migration Plan

Clean reset (consistent with v2). New `person`/`speaker` tables; `segment.speaker_id` replaces `speaker_label`; `recording.label` added. Fresh DB on next boot.

## Open Questions

- Should "You"/"Others" default labels be configurable (e.g. use the recording label for the mic speaker)? Lean: mic speaker defaults to the recording `label` (or "You" if blank); system speaker is "Others".
