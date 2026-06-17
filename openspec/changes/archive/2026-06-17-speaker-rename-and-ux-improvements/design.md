## Context

The v2 local recorder is functional but has rough edges surfaced through real use. Most items here are UX refinements that touch the React frontend (Dashboard, RecordingDetail, Templates), with a handful of small backend changes (a title PATCH endpoint, a template `general_context` column, prompt-building that auto-injects the transcript, and stopping auto-creation of People from default speaker labels). One genuinely new surface is a cross-recording AI chat page.

The app is local-only (FastAPI + SQLite + React/Vite), is being packaged toward a Tauri desktop app, and uses Ollama for all LLM calls. There is no migration framework — the schema is created fresh via `create_all`, guarded by `_assert_schema_current()`. Adding a nullable column is the only safe additive change without a reset.

## Goals / Non-Goals

**Goals:**
- Inline speaker rename from the transcript, with assign-from-existing-People.
- Stop polluting the People directory with "Speaker 1/2" auto-created rows.
- Eliminate the spurious "Room" third speaker in 2-person meetings.
- Inline recording-title rename in both the list and the detail view.
- Clipboard copy (md/txt) replacing file-download export.
- Device-selection modal on Start, persisted to localStorage; one device suffices.
- Remove the unused Label field.
- Template authoring: auto-inject `{{transcript}}`, add General Context, drag-drop section reorder, drop `{{title}}`/`{{date}}` from the UI hint.
- Move per-recording Q&A into its own tab.
- New cross-recording AI chat page with multiple sessions.

**Non-Goals:**
- Real voice-fingerprint speaker recognition across recordings (true biometric matching). We do the cheap heuristic now and leave a hook for later.
- A vector DB / embeddings retrieval for cross-recording chat — v1 stuffs concatenated transcripts into the context window (with a size guard).
- Persisting chat sessions to a rich threaded model beyond what's needed; cross-recording sessions are stored simply.

## Decisions

### 1. The "Room" ghost speaker — verified root cause and fix
Confirmed in code: `Dashboard.tsx` initializes `label` state to `"Room"` and passes it to `startRecording`; `Recording.label` stores it; `processing/job.py` then uses `label or "You"` for the mic speaker and `label or "Speaker 1"` for a single track. So the user's *own* mic track is displayed as "Room" — it is a mislabel, not literally an extra speaker, but in a mic+system 2-person call it reads as an unexpected third name ("Room" + "Others"/"Speaker 1"). **Decision:** remove `label` end-to-end — the Dashboard input, the `StartRecordingRequest.label` field, the `/start` param, the `Recording.label` model column, and the `job.py` usage (mic → "You", single → "Speaker 1"). As a secondary safeguard for the in-person single-mic case (where diarization can over-segment room noise into a spurious "Speaker 3"), drop diarization clusters whose total speech duration is below a threshold (e.g. < 2s or < 5% of the track). *Alternative considered:* keep label but hide it — rejected, it's dead weight and the source of the bug.

### 2. No junk People from default labels — verified root cause and fix
Confirmed in code: the **only** place a `Person` is created is `rename_speaker` in `api/recordings.py` (find-or-create, already case-insensitive). The transcription job creates `Speaker` rows only — it never creates People. The real bug is in `TranscriptChat.tsx`: clicking a speaker chip sets the edit draft to the current display name (`setDraft(name)`, which for an un-renamed speaker is the default label like "Speaker 1"), and the input's `onBlur` calls `commit()`, which submits the unchanged draft → `renameSpeaker(id, "Speaker 1")` → a `Person` named "Speaker 1" is created. So merely clicking a chip and clicking away spawns junk People. **Decision (defense in depth):**
- *Frontend:* `commit()` becomes a no-op when the trimmed draft is empty **or** unchanged from the speaker's current display name. Renaming only fires when the value actually changed.
- *Backend:* `rename_speaker` rejects (no-op, returns current state) when the submitted name equals the speaker's own default `label`, so a stray default-label submit can never create a `Person`. Also support clearing a link (empty/explicit clear sets `person_id = None`).

This keeps the People directory empty until the user makes a real, distinct rename. The existing case-insensitive find-or-create (reuse an existing Person when the name matches) already satisfies "assign an existing one" — no backend change there.

### 3. Auto-match to existing People (deferred; hook only)
Confirmed there is no voice-embedding data captured, so cross-recording recognition is not feasible without new infrastructure. **Decision (v1):** keep the existing rename autocomplete (datalist of People names) and upgrade it to an explicit picker; add a `match_speakers_to_people()` hook in the job that returns no matches for now and never auto-creates People. Real biometric matching (pyannote embeddings + cosine similarity, stored per speaker) is deferred to its own change.

### 4. Recording title rename
Add `PATCH /api/recordings/{id}` accepting `{title}`. Frontend: click-to-edit the `<h1>` in the detail header and an inline edit affordance in the dashboard list row. *Alternative:* a separate modal — rejected, inline is lighter.

### 5. Clipboard copy instead of download
Confirmed `GET /api/recordings/{id}/export?format=md|txt` already exists and returns the rendered text via `export_markdown`/`export_text`. **Decision:** replace the two `<a href=exportUrl>` links with buttons that `fetch` that endpoint, read `.text()`, and `navigator.clipboard.writeText()` it — single source of truth for formatting, no client-side re-rendering. Show a transient "Copied!" state. Feature-detect `navigator.clipboard`; fall back to a hidden-textarea + `document.execCommand('copy')`. Tauri's webview supports the async Clipboard API.

### 6. Device selection modal + localStorage
Move the mic/system-audio selects out of the always-visible form into a modal triggered by "● Start recording". Pre-select from `localStorage` keys (`lastMicDevice`, `lastSystemDevice`), falling back to the current auto-detect. Only one of the two is required to start (validate: at least one non-empty). Persist the chosen values on start. localStorage works in the Tauri webview. *Alternative:* Tauri store plugin — unnecessary, localStorage is simpler and portable.

### 7. Template authoring changes
The prompt builder is `pipeline.summarize`, which calls `render(section["prompt"], meta)` where `render` is pure `{{key}}` string substitution and `meta` already includes `transcript`, `title`, `date`. So:
- **Auto-inject transcript:** in `summarize`, after `render`, if the *section prompt source* does not contain `{{transcript}}`, append `\n\nTRANSCRIPT:\n<transcript>` to the resolved prompt. Users stop typing it. Backward-compatible: the built-in templates already embed `TRANSCRIPT:\n{{transcript}}`, and the contains-check prevents a second copy.
- **General Context:** new nullable `general_context` column on `SummaryTemplate`, threaded through `SummaryTemplateCreate`/`Update` and the API. At summarize time it is prepended once to each section's resolved prompt (before the section instruction, before the transcript). Rationale for "before": it frames the task/persona; the transcript stays last so the model reads instructions first, then data.
- **Drag-drop reorder:** `sections` is already an ordered JSON array persisted as-is. Use native HTML5 drag-and-drop (no new dependency) to reorder the array in the editor; the existing save path persists the new order.
- **Remove {{title}}/{{date}} hint:** drop the helper line ("Each section is a separate prompt. Use {{transcript}}, {{title}}, {{date}}.") and the mandatory `TRANSCRIPT:` boilerplate from the editor. Keep `render` resolving `{{title}}`/`{{date}}` if present (cheap, avoids breaking any existing template) but don't surface them in the UI.

### 8. Q&A moved to a tab
RecordingDetail gains a simple tab bar: **Transcript** | **Chat**. The transcript view stops merging `qa` items into its scroll. The Chat tab renders the Q&A history + PromptBar. Summarize stays accessible (keep it in the right-hand summary panel / a control on the relevant tab). *Alternative:* a slide-over panel — tabs are clearer and match the request.

### 9. Cross-recording AI chat page
New route `/ask`. A session asks a question answered over **all** transcripts (optionally filtered by tag or date range later). **Storage:** add a lightweight model for cross-recording chat sessions and messages, OR reuse `QAMessage` with `recording_id = NULL` and a `session_id`. **Decision:** introduce `ChatSession` + `ChatMessage` tables (clean separation from per-recording Q&A; avoids overloading nullable FKs). Context building: concatenate ready recordings' transcripts newest-first up to a token/char budget; note truncation in the answer. Endpoint `POST /api/chat/sessions`, `GET /api/chat/sessions`, `POST /api/chat/sessions/{id}/ask`. *Alternative:* reuse meeting-qa with null recording — rejected for schema clarity; this is additive (new tables), still no reset needed since `create_all` adds new tables.

## Risks / Trade-offs

- **New tables via `create_all`** → adding `ChatSession`/`ChatMessage` is safe (create_all creates missing tables) but the `_assert_schema_current()` guard and `general_context` column on an existing table need care: a column added to `SummaryTemplate` will NOT be added to an existing table by `create_all`. → **Mitigation:** treat `general_context` like other v2 columns — document that an existing DB needs the clean reset, OR add a tiny `ALTER TABLE ... ADD COLUMN` on startup if the column is missing (additive, safe for SQLite). Prefer the in-place `ADD COLUMN` to avoid forcing a reset.
- **Cross-recording context overflow** → many/long transcripts exceed the model context. → **Mitigation:** char/token budget with newest-first truncation and an explicit "(older recordings omitted)" note.
- **Auto-inject transcript double-counting** → a template already containing `{{transcript}}` must not get a second copy. → **Mitigation:** contains-check before appending.
- **Removing Label** → any stored recording that relied on it for display. → **Mitigation:** the v2 transcript renders by speaker, not label; Label is unused in display, safe to remove.
- **Clipboard API in Tauri** → permission/availability. → **Mitigation:** feature-detect `navigator.clipboard`; fall back to a hidden textarea + `execCommand('copy')` if absent.
- **Heuristic People matching disappoints** → users expect real recognition. → **Mitigation:** scope it as autocomplete-only now; document the biometric matching as a future change.

## Migration Plan

1. Add nullable `general_context` to `SummaryTemplate`; on startup, if the column is missing from an existing table, run `ALTER TABLE summarytemplate ADD COLUMN general_context TEXT` (idempotent — guarded by a `PRAGMA table_info` check, consistent with the existing `_assert_schema_current` approach).
2. `create_all` creates the new `chatsession` / `chatmessage` tables automatically.
3. Remove `Recording.label` from the model. On an existing SQLite DB the physical column remains but is never selected (SQLModel maps only model fields) or written (it was nullable) — harmless. No `_assert_schema_current` rule references it, so no reset is forced.
4. No data migration for People — the junk-People bug is fixed at the source (rename guard). Pre-existing junk "Speaker N" People can be deleted by the user from the directory (deletion already unlinks speakers safely).
5. Rollback: revert code; the extra column and tables are inert if unused.

## Open Questions

- Should cross-recording chat be filterable by tag/date in v1, or all-transcripts only? (Leaning: all-transcripts with a simple optional tag filter if cheap.)
- Should the "General Context" be prepended once per summarize run or once per section? (Decided: once per section prompt, since each section is an independent LLM call.)
