## 1. Data model

- [ ] 1.1 Add `SummaryTemplate(id, name, sections JSON [{title, prompt}], is_default, builtin)` to `app/models.py`.
- [ ] 1.2 Change `Summary` to store `sections: JSON` `[{title, content}]` (replace `content`); keep `recording_id, template_id, created_at`; drop `kind`.
- [ ] 1.3 Reduce `PromptTemplate` to the `qa` kind only (Q&A prompt).

## 2. Seeds

- [ ] 2.1 Update `app/llm/default_templates.py`: seed builtin `SummaryTemplate`s (Standard meeting, 1:1, Standup) with `builtin=true`, and one builtin qa `PromptTemplate`. Remove the dead `aspects` template.
- [ ] 2.2 Seed in `db.py` for both tables (idempotent).

## 3. Summarization

- [ ] 3.1 In `app/pipeline.py`, implement section-wise `summarize(recording_id, template_id) -> Summary`: render each section prompt with `{{transcript}}/{{title}}/{{date}}`, call Ollama per section, store `sections` JSON.
- [ ] 3.2 Keep `ask()` (Q&A) using the qa `PromptTemplate`.

## 4. Auto-summary on completion

- [ ] 4.1 In `app/processing/job.py`, after a recording becomes `ready` with ≥1 segment, generate a summary from the default `SummaryTemplate` (best-effort; a summarization error must not set the recording `failed`).

## 5. API

- [ ] 5.1 `GET/POST/PUT/DELETE /api/summary-templates` (reject delete of `builtin`).
- [ ] 5.2 Update `POST /api/recordings/{id}/summarize` to take a summary `template_id` and return the new summary's sections.
- [ ] 5.3 `GET /api/recordings/{id}` returns summaries (sections) newest-first.
- [ ] 5.4 Exporters: render summary sections as headings + body in md/txt.

## 6. Frontend

- [ ] 6.1 `api.ts`: `SummaryTemplate`, `Summary` (sections), summary-templates + summarize endpoints.
- [ ] 6.2 Recording detail Summary tab: render section cards from the latest summary; template selector + Generate/Regenerate.
- [ ] 6.3 Templates page: manage `SummaryTemplate`s (builtins read-only, clone to edit); keep the qa prompt editable.
- [ ] 6.4 Run `tsc --noEmit` and `npm run build`.

## 7. Verification

- [ ] 7.1 Transcribe a recording; confirm a default-template summary is auto-generated with multiple sections.
- [ ] 7.2 Regenerate with a different template; confirm a new summary is stored and history is retained.
- [ ] 7.3 Confirm a silent recording (no segments) gets no auto-summary and the recording stays `ready`.
- [ ] 7.4 Confirm a built-in template cannot be deleted; a custom one can be created/edited.
- [ ] 7.5 Q&A still answers from the transcript and retains history; md/txt export includes summary sections.
