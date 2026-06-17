## Why

The current app has accumulated several friction points in its day-to-day recording workflow: renaming speakers requires leaving the transcript, "Room" ghost speakers appear in two-person meetings, template authoring is verbose, the Q&A chat clutters the transcript view, and device selection is buried in the dashboard form. Addressing these together makes the app feel polished and production-ready.

## What Changes

- **Speaker rename in transcript**: Inline rename already exists (click a chip → input). Improve it with an explicit pick-list of existing People alongside free-text entry, and fix the junk-People bug below.
- **No junk People from default labels**: Stop creating `Person` rows named "Speaker 1"/"You"/"Others". The actual cause is the rename UI committing the pre-filled default label on blur/Enter even when the user changed nothing — fixed in both the frontend (no-op when unchanged) and the backend (reject creating a Person whose name equals the speaker's own default label).
- **Auto-match to People directory**: Real cross-recording voice recognition needs voice embeddings and is out of scope here; this change provides the assign-from-existing UX plus a `match_speakers_to_people()` extension point that returns no matches for now.
- **Suppress "Room" ghost speaker**: Root cause is the Dashboard `label` field defaulting to the string `"Room"`, which `job.py` applies to the mic/single speaker (`label or "You"`), so your own track is mislabeled "Room". Removing the `label` field end-to-end fixes it. As a secondary safeguard, diarization drops clusters below a minimum speech-duration/share so brief room noise never becomes a separate "Speaker N".
- **Rename recordings**: Inline-edit the recording title in both the detail view header and the dashboard list.
- **Clipboard export**: Replace the md/txt download links with "Copy as Markdown" / "Copy as Text" buttons. The `GET /api/recordings/{id}/export?format=md|txt` endpoint already returns the text, so the buttons fetch it and copy to the clipboard.
- **Device selection modal**: Move microphone/system-audio selection into a modal that appears when the user clicks "● Start recording"; pre-fill from localStorage; only one device is required.
- **Remove Label field**: The "Label" field on the dashboard has no current purpose in the v2 model and should be removed.
- **Template auto-inject transcript**: Each section prompt MUST NOT require the user to type `TRANSCRIPT: {{transcript}}` — the backend injects it automatically.
- **Template general context**: Add a free-text "General context" field to each template that is prepended to every section prompt (describes the meeting type, audience, etc.).
- **Template section drag-drop**: Sections in the template editor can be reordered by dragging.
- **Remove {{title}}/{{date}} placeholders**: Remove these from the section prompt hint; keep them in the backend for now but don't advertise them.
- **AI Chat in a separate tab**: Move Q&A out of the transcript scroll area into a dedicated "Chat" tab on the recording detail view.
- **Cross-recording AI chat page**: New page for multi-recording questions ("recap this week", "what issues affect customers") backed by concatenated transcript context.

## Capabilities

### New Capabilities

- `recording-rename`: Inline rename of a recording's title in both the detail view and the dashboard list.
- `clipboard-export`: "Copy as Markdown" / "Copy as Text" buttons that write the transcript+summary to the clipboard instead of triggering a file download.
- `device-selection-modal`: Modal shown on "Start recording" click that lets the user pick mic/system-audio; selection is persisted to localStorage.
- `template-authoring-ux`: Auto-inject `{{transcript}}` at the prompt layer; general context field on templates; drag-drop section reordering; remove {{title}}/{{date}} hint.
- `cross-recording-qa`: New "Ask everything" page where free-form questions are answered using all (or a filtered subset of) transcripts.

### Modified Capabilities

- `speaker-identification`: Explicit assign-from-People picker; guard against creating People from default/unchanged labels (the junk-People bug); prevent the "Room" mislabel; single-track baseline label becomes "Speaker 1".
- `speaker-diarization`: Discard negligible (sub-threshold) clusters so brief room noise never becomes a phantom "Speaker N".
- `transcript-view`: AI Chat moved into a dedicated tab separate from the transcript scroll (the per-recording Q&A behavior itself is unchanged).
- `summary-templates`: Templates gain an optional general-context field stored as structured data.

## Impact

- **Backend**:
  - `backend/app/api/recordings.py`: add a title-update endpoint (`PATCH /api/recordings/{id}`); remove the `label` param from `/start`; in `rename_speaker`, reject creating a `Person` when the submitted name equals the speaker's default label (and support clearing a link). The existing find-or-create is already case-insensitive — no change needed there.
  - `backend/app/pipeline.py` (`summarize`): prepend `general_context` and auto-append the transcript to each section prompt unless it already contains `{{transcript}}`.
  - `backend/app/processing/job.py`: drop `rec.label` usage (mic → "You", single → "Speaker 1"); add a `match_speakers_to_people()` no-op hook; drop sub-threshold diarization clusters.
  - `backend/app/models.py`: remove `Recording.label`; add `SummaryTemplate.general_context`; add `ChatSession` + `ChatMessage`.
  - `backend/app/api/templates.py`: accept `general_context` in create/update.
  - New `backend/app/api/chat.py`: cross-recording chat sessions (`POST/GET /api/chat/sessions`, `POST /api/chat/sessions/{id}/ask`, `DELETE /api/chat/sessions/{id}`).
- **Frontend**:
  - `Dashboard.tsx`: device-selection modal on Start, remove the Label input, inline title rename in list rows.
  - `RecordingDetail.tsx`: Transcript | Chat tab bar; stop merging Q&A into the transcript; click-to-edit header title; Copy-as-md/txt buttons.
  - `TranscriptChat.tsx`: fix commit-on-blur to no-op when unchanged; explicit People picker.
  - `Templates.tsx`: General Context textarea; drop the `{{transcript}}`/`{{title}}`/`{{date}}` hint and the mandatory `TRANSCRIPT:` boilerplate; drag-drop section reordering (native HTML5 DnD, no new dependency).
  - `lib/api.ts`: `renameRecording`, chat-session calls, `general_context` on template types, a `getExportText` helper.
  - New `pages/Ask.tsx` + `/ask` route + nav link in `App.tsx`.
- **DB**: `SummaryTemplate` gains nullable `general_context TEXT` (added via idempotent `ALTER TABLE` on startup). New `chatsession`/`chatmessage` tables (auto-created). `Recording.label` is dropped from the model; the dangling SQLite column on existing DBs is harmless and unread.
- **No breaking changes** to existing data; all additions are nullable/new tables and backward-compatible.
