## Why

The app's current look is a dark, utilitarian theme with the navigation in a top header bar. A new hi-fi design (`design/redesign/Sirina App.dc.html`, 4 screens) reframes Sirina as a warm, light **"paper & ink" editorial** product: serif titles, mono for time, and a single vermilion signal reserved for recording/live state. The redesign also moves navigation into a persistent **left sidebar** that carries the always-available Record control, device picker, tag list, and runtime status. This is mostly a presentational reskin, but the shell change is structural and worth doing deliberately so nothing regresses.

## What Changes

- **New visual theme**: replace the old dark/`fuchsia` theme with the paper/ink design, vermilion signal color, and the editorial type system (Newsreader serif for titles/summaries, Hanken Grotesk for UI, JetBrains Mono for time/model-ids). Built with **Tailwind 4** (CSS-first `@theme` tokens in `index.css`) instead of ad-hoc CSS.
- **Light and dark themes** (from `Sirina App.dc.html` and `Sirina App -Dark-.dc.html`): both ship, delivered by swapping token *values* (not per-component styling). Defaults to the OS preference with a manual toggle (auto/light/dark) persisted locally; the vermilion signal is shared across both.
- **Self-hosted fonts**: the three fonts are **bundled** (no Google Fonts CDN), so the app makes no external request for UI assets and works offline — consistent with local-first.
- **Persistent left-sidebar shell** (`app-shell`): navigation moves from the top header into a 252px sidebar that also hosts the **Record button + device picker**, the **Tags** list, and a **"Local · Whisper ready" status** footer. Every screen renders inside this shell; routes are unchanged.
- **Restyle the four designed screens** to match the comps: Recordings (Dashboard), Recording detail, Recording (live), Settings. The **detail page is reorganized** (more than a restyle): its Summary panel moves from the right sidebar into a new Summary tab, giving three full-width tabs (Summary / Transcript / Ask AI); all summary/transcript/Q&A behavior is preserved.
- **Additive controls present in the comps**: a recordings **name filter**, a **transcript search**, date-grouped recording sections, and a header speaker-avatar menu — all client-side/presentational, no backend changes.
- **Theme-only restyle** of the pages with no comp (Ask, People, Templates): colors/fonts/cards updated to the new system, layouts unchanged.
- **Tag colors are preserved**: their styles are remapped to the warm palette while keeping the stored token names, so existing tags need no data migration.
- **Non-goal / hard constraint**: no UI element absent from the comps is removed or restructured. Existing controls, handlers, routes, and behaviors are preserved; relocations (e.g. the device-selection modal's trigger moving to the sidebar) keep the existing component intact. **No API, route, hook, or data-flow changes.**

## Capabilities

### New Capabilities

- `app-shell`: A persistent navigation shell — a left sidebar present on every screen that provides primary navigation, an always-available Record control and device-selection entry point, the tag list (management + filtering entry points), and a persistent local/runtime status indicator — using a bundled, offline visual theme with no external asset fetches.

### Modified Capabilities

_None. The redesign is presentational and preserves existing behavior; `device-selection-modal`, `tagging`, and the per-screen capabilities keep their requirements (the sidebar only relocates their entry points)._

## Impact

- **Frontend only.** No backend, API, route, or data changes.
- `frontend/src/index.css`: Tailwind 4 `@theme` tokens (palette, fonts, radii, shadows) with light values on `:root` and dark overrides under `[data-theme="dark"]`; plus a pre-paint theme bootstrap (`index.html`/`main.tsx`) and a sidebar theme toggle.
- New: bundled font assets (`@fontsource`); a logo asset from `design/redesign/assets/sirina-mark.svg`; an Iconify icon setup (`lucide` set via **`@iconify/react`, registered offline** — no Iconify API at runtime) behind a small `Icon` wrapper; an app-shell/sidebar component; a small set of styled primitives (Card, Button, Pill/Badge, ListRow, Toggle, Stepper, Slider, SegmentedSelect, Avatar).
- New dependencies: `@iconify/react` + `@iconify-json/lucide` — used in offline/bundled mode only.
- `frontend/src/App.tsx`: replace the top header with the sidebar shell (routes unchanged); lift Record + device picker + Tags + status into it (logic moved from `Dashboard.tsx` / `ConnectionStatus.tsx`, behavior preserved).
- Restyle `pages/Dashboard.tsx`, `RecordingDetail.tsx`, `RecordingScreen.tsx`, `Settings.tsx`; theme-only restyle of `Ask.tsx`, `People.tsx`, `Templates.tsx` and shared components (`TagUI.tsx`, `PromptBar.tsx`, `TranscriptChat.tsx`, `ConnectionStatus.tsx`).
- The `design/redesign/*.dc.html` + `support.js` are design references only and stay out of the app bundle.
