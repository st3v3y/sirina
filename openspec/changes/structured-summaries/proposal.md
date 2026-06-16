## Why

A single freeform summary blob is hard to scan and hard to tailor. Multi-section templates (each section a title + focused prompt) produce better, structured output — and storing templates as data sets up user-editable templates later. A default summary should appear automatically when a recording finishes, with the option to regenerate using a different template. See [docs/V2-LOCAL-REDESIGN.md §6.4, §7](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Replace freeform summaries with **multi-section templates**: `SummaryTemplate.sections` is JSON `[{title, prompt}, …]`; `Summary.sections` stores the produced `[{title, content}, …]`.
- **Seed builtin templates in code** (e.g. Standard meeting, 1:1, Sales call, Standup), marked non-deletable; designed so a future template-editor UI is a thin add-on.
- **Auto-generate a default-template summary on stop** (after transcription completes) — no user action required.
- Allow **regenerating with a different template**; keep summary history and let the user switch between generated summaries.
- Run each section as its own focused Ollama call (`{{transcript}}`, `{{speakers}}`, `{{title}}`, `{{date}}` placeholders) and render each as a card.
- Keep **Q&A** over the finished transcript, repointed to `recording_id`.

## Capabilities

### New Capabilities
- `summary-templates`: the JSON multi-section template model, seeded builtins, and (read-first) management.
- `meeting-summaries`: per-section summary generation, auto-summary on stop, regenerate-with-template, and summary history.
- `meeting-qa`: grounded question answering over a finished recording's transcript.

### Modified Capabilities
<!-- None archived yet; builds on offline-transcription's transcript. -->

## Impact

- **Data model**: `SummaryTemplate.sections` (JSON), `Summary.sections` (JSON), `QAMessage` on `recording_id`.
- **Backend**: section-wise summarizer reusing the `{{var}}` renderer + Ollama client; auto-run default on processing completion; `/api/recordings/{id}/summarize` (template_id), `/api/templates`, `/api/recordings/{id}/ask`.
- **Frontend**: Summary tab with section cards + template selector + regenerate; Ask tab; Templates page (builtins read-only first).
- **Soft dependency**: `speakers-and-people` improves prompts (speaker-attributed transcript) but is not required.
- **Depends on**: `offline-transcription` (needs a transcript).
