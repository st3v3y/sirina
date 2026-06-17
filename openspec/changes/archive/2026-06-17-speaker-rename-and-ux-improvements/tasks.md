## 1. Backend — schema & migrations

- [x] 1.1 Add nullable `general_context: str | None` column to `SummaryTemplate` in `models.py`
- [x] 1.2 Remove `Recording.label` from `models.py`; remove `label` from `StartRecordingRequest`/the `/start` payload and stop reading it in `processing/job.py`
- [x] 1.3 Add `ChatSession` (title, created_at) and `ChatMessage` (session_id FK, role, content, created_at) SQLModel tables
- [x] 1.4 In `db.py` startup, add `general_context` via `ALTER TABLE summarytemplate ADD COLUMN general_context TEXT` guarded by a `PRAGMA table_info` check (idempotent); confirm `create_all` creates the new chat tables and `_assert_schema_current()` still passes

## 2. Backend — speaker / People fixes

- [x] 2.1 In `processing/job.py`, drop the `label or …` fallbacks: mic speaker → "You", single track → "Speaker 1" (no user label)
- [x] 2.2 In `rename_speaker` (`api/recordings.py`), no-op when the submitted name is empty or equals the speaker's own default `label`, so default-label submits never create a `Person`; support clearing a link (set `person_id = None`) on an explicit clear
- [x] 2.3 Keep the existing case-insensitive find-or-create for real renames (already correct — assign-existing works); add a regression check that renaming to an existing name reuses the Person
- [x] 2.4 In the diarization path (`_speaker_groups` / `diarize.py`), discard clusters below a minimum speech-duration/share threshold; always keep ≥1 speaker
- [x] 2.5 Add a `match_speakers_to_people()` no-op hook called post-transcription that returns no matches and creates no People (extension point for future voice matching)

## 3. Backend — recording rename, template prompt building, chat

- [x] 3.1 Add `PATCH /api/recordings/{id}` accepting `{title}` and persisting it
- [x] 3.2 Thread `general_context` through `SummaryTemplateCreate`/`SummaryTemplateUpdate` and the create/update routes in `api/templates.py`
- [x] 3.3 In `pipeline.summarize`, prepend `general_context` (when present) to each section's resolved prompt
- [x] 3.4 In `pipeline.summarize`, auto-append `\n\nTRANSCRIPT:\n<transcript>` to each resolved prompt only when the section prompt source does not contain `{{transcript}}`
- [x] 3.5 Add `api/chat.py`: `POST /api/chat/sessions`, `GET /api/chat/sessions` (with messages), `POST /api/chat/sessions/{id}/ask`, `DELETE /api/chat/sessions/{id}`; register the router
- [x] 3.6 In the chat-ask handler, build bounded context from `ready` recordings (newest-first, char/token budget) and note in the answer when older recordings were omitted; persist the Q&A turn to `ChatMessage`

## 4. Frontend — api.ts

- [x] 4.1 Remove `label` from `StartRecordingRequest`; add `general_context` to `SummaryTemplate`/create/update types
- [x] 4.2 Add `renameRecording(id, title)` (PATCH) and a `getExportText(id, format)` helper that fetches the export endpoint and returns text
- [x] 4.3 Add chat-session API wrappers (create/list/ask/delete) and `ChatSession`/`ChatMessage` types

## 5. Frontend — dashboard: device modal, label removal, list rename

- [x] 5.1 Remove the always-visible mic/system selects and the Label input from `Dashboard.tsx`
- [x] 5.2 Add a device-selection modal shown on "Start recording" click with mic + system-audio selects; require at least one source before starting
- [x] 5.3 Pre-fill the modal from `localStorage` (`lastMicDevice`, `lastSystemDevice`); persist selection on start; feature-safe for the Tauri webview
- [x] 5.4 Add inline title rename in each recordings-list row (click-to-edit, PATCH on blur/Enter, empty falls back to the default "Recording #<id>" label)

## 6. Frontend — recording detail: rename, tabs, clipboard

- [x] 6.1 Make the detail header title click-to-edit, calling `renameRecording` and updating without reload
- [x] 6.2 Add a Transcript | Chat tab bar; render only transcript segments in Transcript and the Q&A history + `PromptBar` in Chat; relocate the Summarize control so it stays reachable (summary panel / Transcript tab)
- [x] 6.3 Stop merging `qa` items into the transcript `items` array
- [x] 6.4 Replace the md/txt download links with "Copy as Markdown" / "Copy as Text" buttons using `getExportText` + `navigator.clipboard.writeText`, with a hidden-textarea fallback and a transient "Copied!" state

## 7. Frontend — speaker rename in transcript

- [x] 7.1 In `TranscriptChat.tsx`, make `commit()` a no-op when the trimmed draft is empty or unchanged from the current display name (fixes junk-People on blur)
- [x] 7.2 Upgrade the rename control from a bare `datalist` to an explicit People picker (list of existing People to select, plus free-text entry); selecting an existing Person links without duplicating
- [x] 7.3 Confirm a confirmed rename updates all lines for that speaker and refreshes the People list

## 8. Frontend — templates page

- [x] 8.1 Add a "General context" textarea to the template editor, bound to `general_context`
- [x] 8.2 Remove the helper line ("Use {{transcript}}, {{title}}, {{date}}.") and the mandatory `TRANSCRIPT: {{transcript}}` boilerplate from new-section/clone defaults
- [x] 8.3 Add native HTML5 drag-and-drop reordering of sections; the existing save path persists the new order

## 9. Frontend — cross-recording AI chat page

- [x] 9.1 Add an `/ask` route and an "Ask" nav link in `App.tsx`
- [x] 9.2 Build `pages/Ask.tsx`: session list/sidebar, create-session, message thread, prompt input
- [x] 9.3 Wire create/list/ask/delete to the chat API; show the omission note when context is truncated

## 10. Verification

- [x] 10.1 Two-person mic+system recording shows "You" + the other speaker — no "Room"; People directory stays empty until a real rename
- [x] 10.2 Clicking a speaker chip and clicking away (no change) creates no Person; a real rename (new name and assign-existing) updates all lines with no duplicate Person
- [ ] 10.3 Rename a recording from both the list and the detail view; verify persistence and empty-title fallback
- [ ] 10.4 Copy as Markdown/Text places the correct content on the clipboard (and the fallback path works)
- [ ] 10.5 Start a recording via the modal with only one source; last devices pre-fill next time
- [x] 10.6 Create a template with general context and a section lacking `{{transcript}}`; summary uses context + transcript with no double transcript; reorder sections by drag and confirm order persists
- [ ] 10.7 Q&A appears only in the Chat tab; the Transcript tab shows no Q&A
- [x] 10.8 Cross-recording chat answers across multiple transcripts; multiple sessions stay independent; truncation note appears when transcripts exceed the budget
