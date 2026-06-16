## Context

Recordings are shown as a flat, reverse-chronological list on the dashboard. As they accumulate, finding a meeting is hard. Tags are a cheap, AI-free way to organise and filter. The data model already has `Recording`; this adds tags and a m2m link.

## Goals / Non-Goals

**Goals:**
- `Tag` (name + optional color) and a recording↔tag many-to-many.
- Add/remove tags on a recording (list row + detail header).
- Filter the recordings list by tag; a small tag manager (rename/recolor/delete).

**Non-Goals:**
- Tag hierarchies, auto-tagging, or smart/saved filters. Keep it flat and manual.
- Tagging anything other than recordings.

## Decisions

- **Tables: `Tag(id, name, color?)` and `RecordingTag(recording_id, tag_id)`** (composite-keyed link). Reuse the existing colour-token palette for tag colours so chips match the speaker styling.
- **Tags included in recording payloads.** `GET /api/recordings` list items and `GET /api/recordings/{id}` include their tags (id, name, color). The frontend renders chips from this.
- **Filter on the list endpoint.** `GET /api/recordings?tag_id=<id>` filters server-side via a join; absent → all recordings.
- **Assignment endpoints.** `POST /api/recordings/{id}/tags {tag_id}` and `DELETE /api/recordings/{id}/tags/{tag_id}`. Tag CRUD at `/api/tags` (`GET/POST/PUT/DELETE`). Deleting a tag cascades to `RecordingTag` rows (clean up the m2m).
- **Frontend.** Tag chips on each list row and in the detail header with an add/remove affordance (small dropdown of existing tags + "create"); a filter control (tag pills) on the dashboard; a lightweight tag manager (could live on the dashboard or a small section). Keep it minimal — reuse existing list/inline-edit patterns.

## Risks / Trade-offs

- [Deleting a tag mid-use] → Cascade-delete the `RecordingTag` rows; recordings are untouched. Confirm in the UI.
- [Many tags clutter the dashboard filter] → Acceptable at this scale; a simple horizontal pill row suffices. Revisit if it grows.
- [N+1 when loading tags per list row] → Batch-load tags for the listed recordings in one query and map in memory.

## Migration Plan

Additive: new `tag` + `recordingtag` tables created by `create_all`. No data migration; existing recordings simply have no tags.

## Open Questions

- Where the tag manager lives (dashboard section vs its own page). Lean: a small section/dropdown on the dashboard to avoid another route; can promote to a page later.
