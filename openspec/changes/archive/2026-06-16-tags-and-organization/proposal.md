## Why

As recordings accumulate, a flat list is hard to navigate. Lightweight tags give cheap, high-value organization with no AI involved, and a dashboard filter makes meetings findable. See [docs/V2-LOCAL-REDESIGN.md §8](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Add a `Tag` model (name + optional color) and a many-to-many link to recordings.
- Let the user **add/remove tags** on each recording (from the list row and the detail header).
- Add a **dashboard filter by tag** and a small **tag manager** (rename/delete, recolor).

## Capabilities

### New Capabilities
- `tagging`: tag CRUD, assigning/removing tags on recordings, and filtering the recordings list by tag.

### Modified Capabilities
<!-- None archived yet; builds on record-to-file's recording-store. -->

## Impact

- **Data model**: new `Tag` and `RecordingTag` (m2m) tables.
- **Backend**: `/api/tags` (CRUD), `/api/recordings/{id}/tags` (add/remove), tag filter on the recordings list query.
- **Frontend**: tag chips on list rows + detail header; tag filter control; tag manager.
- **Depends on**: `record-to-file` (needs `Recording`). Independent of transcription/summaries — can proceed in parallel once recordings exist.
