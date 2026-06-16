## 1. Data model

- [ ] 1.1 Add `Person(id, name, created_at)` and `Speaker(id, recording_id, label, person_id?, color?)` to `app/models.py`.
- [ ] 1.2 Replace `Segment.speaker_label: str` with `Segment.speaker_id` (FK to `speaker.id`).
- [ ] 1.3 Add `Recording.label` (the user-entered label captured at start).

## 2. Recorder + capture

- [ ] 2.1 Store `label` on the `Recording` in `recorder.start()` (currently accepted but ignored).

## 3. Processing — speaker attribution

- [ ] 3.1 In `app/processing/job.py` `_process()`: when both `mic_path` and `system_path` exist, create two `Speaker` rows — "You" (from mic, default = recording label or "You") and "Others" (system) — transcribe each track and tag segments with the matching speaker.
- [ ] 3.2 When only one track exists, create a single `Speaker` (label = recording label or "Speaker 1") and transcribe it.
- [ ] 3.3 Assign each speaker a stable `color` (palette index by creation order). Merge segments across tracks ordered by `start_ts`.

## 4. API — speakers & people

- [ ] 4.1 Include speakers in `GET /api/recordings/{id}` (id, label, resolved display name, color) and have segments carry `speaker_id`.
- [ ] 4.2 `PUT /api/recordings/{id}/speakers/{speaker_id}` `{name}`: find-or-create `Person`, set `speaker.person_id`.
- [ ] 4.3 `GET /api/people` (name, recording count, last-seen), `PUT /api/people/{id}` (rename), `DELETE /api/people/{id}` (null linked `person_id`).

## 5. Frontend

- [ ] 5.1 Update `api.ts`: `Speaker` type, `Person` type, segment `speaker_id`, people + rename endpoints.
- [ ] 5.2 `TranscriptChat`: resolve a segment's speaker (display name + color) via the recording's speakers; clicking a speaker name opens an inline rename with autocomplete from `GET /api/people`.
- [ ] 5.3 Add a People page (`/people`) listing People with counts, last-seen, rename, delete; add a nav link.
- [ ] 5.4 Run `tsc --noEmit` and `npm run build`.

## 6. Verification

- [ ] 6.1 Record with mic + a system device; confirm transcript splits into "You" and "Others", time-ordered.
- [ ] 6.2 Rename a speaker; confirm it links to a Person and the name shows; confirm another recording is unaffected.
- [ ] 6.3 Autocomplete suggests an existing Person name.
- [ ] 6.4 People page shows counts/last-seen; rename updates everywhere; delete unlinks (speaker reverts to label) without deleting recordings.
- [ ] 6.5 Mic-only recording yields a single speaker using the recording label.
