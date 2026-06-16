## Context

Today summaries are a single freeform block: `PromptTemplate(name, kind, body, is_default)` holds one prompt, `Summary(recording_id, kind, template_id, content, created_at)` holds one text blob, and `Pipeline.summarize/ask` render a single `{{var}}` prompt via Ollama. The default templates seeded include an `aspects` kind that is now dead (live aspects were removed). This change moves summaries to titled multi-section templates, auto-generates a default summary when transcription finishes, and keeps Q&A.

## Goals / Non-Goals

**Goals:**
- Multi-section summary templates (title + prompt per section), stored as JSON.
- Per-section generation; summaries stored as JSON `[{title, content}]`.
- Auto-generate the default summary when a recording becomes `ready`.
- Regenerate with a different template, keeping history.
- Keep grounded Q&A.

**Non-Goals:**
- Live aspects (removed).
- Speaker-aware prompt enrichment beyond using the (speaker-attributed) transcript text — works with or without `speakers-and-people`.

## Decisions

- **New `SummaryTemplate(id, name, sections JSON, is_default, builtin)`** where `sections = [{title, prompt}]`. Replaces the `summary`/`aspects` kinds of `PromptTemplate`. Seed builtins (Standard meeting, 1:1, Standup) with `builtin=true` (not deletable; clone to customize).
- **Q&A keeps a single prompt.** Reuse `PromptTemplate` but only the `qa` kind (drop `summary`/`aspects`); seed one builtin qa prompt. Q&A is inherently single-prompt, so multi-section doesn't apply.
- **`Summary` stores sections.** Replace `content: str` with `sections: JSON` `[{title, content}]`; keep `recording_id, template_id, created_at`; drop `kind` (all rows are full summaries now). Multiple `Summary` rows per recording = history; the latest is shown, with the option to view earlier ones.
- **Per-section generation** reuses the `{{var}}` renderer + `OllamaClient`. Placeholders: `{{transcript}}`, `{{title}}`, `{{date}}`. Each section is an independent Ollama call (better focus than one mega-prompt).
- **Auto-summary on completion** hooks into the transcription processor: after a recording is set `ready` and has ≥1 segment, generate a summary from the default `SummaryTemplate`. Runs in the same background context (sequential after transcription). No transcript → skip.
- **API.** `GET/POST/PUT/DELETE /api/summary-templates`; `POST /api/recordings/{id}/summarize {template_id}` → new `Summary`; `GET /api/recordings/{id}` returns summaries (sections) newest-first. Q&A endpoint unchanged (`/ask`).
- **Frontend.** Summary tab renders section cards from the latest summary, with a template selector + "Generate" (regenerate). A Templates page manages `SummaryTemplate`s (builtins read-only; clone to edit). Q&A unchanged.

## Risks / Trade-offs

- [N Ollama calls per summary (one per section) is slower than one call] → Acceptable; sections are short and focused, quality is better. Auto-summary runs in the background.
- [Replacing `PromptTemplate.kind`/`Summary.content` touches seeds, pipeline, API, exporters, frontend] → Coordinated in tasks; clean reset (no data migration).
- [Auto-summary couples the processor to summarization] → Keep it a best-effort step after `ready`; a summarization failure must not flip the recording back to `failed` (transcript still valid).

## Migration Plan

Clean reset. New `summarytemplate` table + `Summary.sections`; `PromptTemplate` retains only `qa`. Fresh seeds on boot.

## Open Questions

- Should auto-summary be skippable via config for users who want manual-only? Lean: always on (decided in redesign), no toggle for now.
- Exporters: include all sections in md/txt — yes; render each section as a heading + body.
