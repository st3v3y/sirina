# V2 — Change Priorities

Dependency-ordered priority list for the OpenSpec changes that implement [V2-LOCAL-REDESIGN.md](V2-LOCAL-REDESIGN.md). Start at the top; items in the same tier can be worked in parallel.

## Dependency graph

```
strip-discord                     (no deps)
  └─ record-to-file
       ├─ offline-transcription
       │    ├─ speakers-and-people
       │    │    └─ enhanced-diarization
       │    └─ structured-summaries        (soft dep on speakers-and-people)
       ├─ tags-and-organization            (independent; parallelizable)
       └─ tauri-desktop-app                (needs a stable core: record + transcription)
```

## Priority tiers

| Tier | Change | Status | Blocked by | Notes |
| --- | --- | --- | --- | --- |
| **P0 — start now** | `strip-discord` | ✅ apply-ready (4/4) | — | Pure subtraction; unblocks everything. Run `/opsx:apply` on it first. |
| **P1** | `record-to-file` | ✅ apply-ready (4/4) | strip-discord | Recorder + `Recording` model (clean reset) + record UI. The foundation of the new architecture. |
| **P2a** | `offline-transcription` | 📝 proposal only | record-to-file | **Critical path.** High-quality post-hoc whisper + `Segment`s + transcript view. |
| **P2b** | `tags-and-organization` | 📝 proposal only | record-to-file | Independent + low-effort; can run in parallel with P2a/P3. |
| **P3a** | `speakers-and-people` | 📝 proposal only | offline-transcription | Baseline mic/system speakers + People directory + rename/autocomplete. |
| **P3b** | `structured-summaries` | 📝 proposal only | offline-transcription | Multi-section templates + auto-summary on stop + regenerate + Q&A. Soft dep on speakers. |
| **P4** | `enhanced-diarization` | 📝 proposal only | speakers-and-people | Optional pyannote multi-speaker (free/local). Layers onto the speaker model. |
| **P5** | `tauri-desktop-app` | 📝 proposal only | stable core (record + transcription) | Package as unsigned macOS app; then native ScreenCaptureKit to drop BlackHole. |

Legend: ✅ apply-ready (proposal + specs + design + tasks) · 📝 proposal only (specs/design/tasks to be generated when picked up, via `/opsx:propose <name>`).

## Recommended path to a usable MVP

The shortest line to a working "record → transcript → summary" Jamie-like tool:

```
strip-discord → record-to-file → offline-transcription → structured-summaries
```

That delivers the core loop. Then layer on, in roughly this order:

1. `speakers-and-people` — who said what (big perceived-quality jump).
2. `tags-and-organization` — findability (cheap; slot in anytime after record-to-file).
3. `enhanced-diarization` — multi-speaker for in-room meetings.
4. `tauri-desktop-app` — turn it into a real Mac app and drop the BlackHole setup.

## Parallelization notes

- After `record-to-file` lands, **`tags-and-organization` can proceed independently** of the transcription/summary track — good for parallel work or a quick win.
- After `offline-transcription` lands, **`speakers-and-people` and `structured-summaries` can proceed in parallel** (summaries have only a soft dependency on speakers — they improve with speaker-attributed transcripts but don't require them).
- `enhanced-diarization` must wait for `speakers-and-people` (it reuses the Speaker/Person model and assignment plumbing).
- `tauri-desktop-app` is best done once the core is stable; its step 1 (package the sidecar) only needs record + transcription, while step 2 (native ScreenCaptureKit) can come later.

## How to proceed in OpenSpec

- **Implement an apply-ready change:** `/opsx:apply` (start with `strip-discord`).
- **Flesh out a proposal-only change** (generate its specs/design/tasks) when you reach it: `/opsx:propose <change-name>` — it will continue the existing change rather than create a new one.
- **Dashboard:** `openspec view` for an interactive status board; `openspec list` for the change list.
