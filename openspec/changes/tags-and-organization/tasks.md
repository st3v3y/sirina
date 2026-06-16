## 1. Data model

- [ ] 1.1 Add `Tag(id, name, color?)` and `RecordingTag(recording_id, tag_id)` (composite PK) to `app/models.py`.

## 2. API — tag CRUD

- [ ] 2.1 Create `app/api/tags.py`: `GET /api/tags`, `POST /api/tags {name, color?}`, `PUT /api/tags/{id}`, `DELETE /api/tags/{id}` (cascade-delete its `RecordingTag` rows). Wire the router in `main.py`.

## 3. API — assignment & filter

- [ ] 3.1 `POST /api/recordings/{id}/tags {tag_id}` and `DELETE /api/recordings/{id}/tags/{tag_id}`.
- [ ] 3.2 Include each recording's tags (id, name, color) in `GET /api/recordings` list items and `GET /api/recordings/{id}` (batch-load to avoid N+1).
- [ ] 3.3 `GET /api/recordings?tag_id=<id>` filters the list to recordings carrying that tag.

## 4. Frontend

- [ ] 4.1 `api.ts`: `Tag` type, tags on `Recording`/`RecordingDetail`, tag CRUD + assign/remove + `listRecordings(tagId?)`.
- [ ] 4.2 Dashboard: render tag chips on each recording row; a tag-filter pill row; a minimal tag manager (create / rename / recolor / delete).
- [ ] 4.3 Recording detail header: show tags with add/remove.
- [ ] 4.4 Run `tsc --noEmit` and `npm run build`.

## 5. Verification

- [ ] 5.1 Create a tag, assign it to a recording, confirm the chip shows on the row and detail header.
- [ ] 5.2 Filter the dashboard by the tag; confirm only tagged recordings show; clear → all show.
- [ ] 5.3 Rename/recolor a tag; confirm it updates everywhere.
- [ ] 5.4 Remove a tag from a recording (tag still exists); delete a tag (removed from all recordings, recordings intact).
