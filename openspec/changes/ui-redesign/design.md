## Context

The frontend is React + React Router + Tailwind 4 (`@import "tailwindcss"` in `frontend/src/index.css`, no config file). Today's theme is dark (`color-scheme: dark`, `#0b0d10` bg, `fuchsia` accent) and navigation is a top header in `App.tsx`. Record start, capture-device selection, and tag filtering all live inside `Dashboard.tsx`; runtime readiness lives in `ConnectionStatus.tsx`. The new design (`design/redesign/Sirina App.dc.html`, 4 screens + interaction notes) specifies a light "paper & ink" theme and a persistent left sidebar that absorbs the record/device/tags/status controls. Every AI/transcription behavior stays exactly as-is — this change is presentational plus the shell relocation.

## Goals / Non-Goals

**Goals:**
- A centralized Tailwind 4 design-token layer so the reskin is consistent and cheap to apply.
- A persistent sidebar shell that owns nav + global Record/device/tags/status, with all routes and behaviors unchanged.
- High-fidelity restyle of the four designed screens; theme-only restyle of the rest.
- Bundled fonts (offline, local-first); light theme only.
- Each phase independently shippable with the app runnable throughout.

**Non-Goals:**
- Any backend/API/route/hook/data-flow change.
- Per-component theme styling — light and dark are delivered by swapping token *values*, not by theming each component twice (see decision 1).
- Redesigning pages that have no comp (Ask, People, Templates) — they get theme-only restyling.
- Removing or restructuring any control not shown in the comps.
- New features implied by the comps' sample data (e.g. transcript search, audio scrubber) beyond what already exists — those are noted as follow-ups, not built here unless the control already exists.

## Decisions

### 1. Tailwind 4 token layer (`@theme` in `index.css`), light + dark
Define the palette, fonts, radii, and shadows as Tailwind 4 theme variables so components use semantic utilities (`bg-paper`, `text-ink`, `text-signal`, `font-serif`, `font-mono`, `rounded-card`, `shadow-card`) rather than hex literals. Components reference the *token*, never a hex — so light and dark are delivered by **swapping the token values**, not by theming each component twice.
- The semantic tokens map to CSS variables in `@theme`; the **light** values live on `:root`, and a `[data-theme="dark"]` (on `<html>`) block **overrides the same variables** with dark values. Because every utility resolves `var(--color-…)`, flipping the attribute re-themes the whole app with no `dark:` duplication.
- **Light** (from `Sirina App.dc.html`): `paper` `#fcfbf8`, `surface` `#ffffff`, sidebar gradient `#f4f0e8 → #efe8dc`, outer `#e7e5df`; `ink` `#24211d`, `ink-2` `#6d675d`, `muted` `#9a9183`, `label` `#aaa090`; borders `#e6dfd1`/`#efe8db`/`#e3dccd`; shadows `rgba(40,33,24,*)`.
- **Dark** (from `Sirina App -Dark-.dc.html`): `paper`/outer `#141210`, `surface` `#221f19` (raised `#2a251e`), sidebar warm near-black gradient (≈ `#1b1814 → #141210`); `ink` `#f1ece1`, `ink-2` `#b4ac9d`, `muted` `#8d8474`, `label` `#7c7466`; borders `#332e26`/`#2a251e`/`#39332a`; shadows deepened (`rgba(0,0,0,*)`). Exact values taken from the dark comp during implementation.
- **Shared across both themes**: the **signal** vermilion (`signal` `#c83f25`, `signal-bright` `#d6492f`, gradient `#e0563b → #c83f25`) is unchanged in dark. `ok` `#4a8c5f` (dark may brighten toward `#74c08d`), `warn` amber tuned per theme. Tag/speaker hues keep their token names (decision 8) with per-theme values (the dark comp warms them, e.g. slate `#93a6c4`, rust `#e3936b`).
- Set `color-scheme: light dark` and the base bg/text from the tokens so native controls/scrollbars follow the active theme.

### 2. Self-hosted fonts
Bundle Newsreader (serif → `font-serif`, titles + summary prose), Hanken Grotesk (sans → default UI), and JetBrains Mono (`font-mono`, time/model-ids/metadata). Prefer `@fontsource/*` packages (Vite-bundled woff2) so PyInstaller/Tauri packaging picks them up and nothing is fetched from Google at runtime. No `<link rel="preconnect">` to Google. `@font-face` is registered via the imported packages; families are mapped in the `@theme` block.

### 3. App-shell component owns the relocated state
Introduce a `Shell` (sidebar + main outlet) rendered once around the routed pages in `App.tsx`. It owns what the comp puts in the sidebar:
- **Nav** (Recordings/Ask/People/Templates/Settings) with active state from the router.
- **Record + device picker**: the start-recording logic and device state currently in `Dashboard.tsx` move up into the shell (or a small `useRecorder` hook shared by the shell). The existing device-selection flow/modal is reused — only its trigger relocates. While recording, the control shows the live state (elapsed timer) per screen 3.
- **Tags**: the tag list + create + filter **and the inline "Manage tags" editor (rename / recolor / delete)** currently live in `Dashboard.tsx`; all of it moves to the sidebar. Filter state must be readable by the Recordings page → lift it to the shell (or a small context) so selecting a sidebar tag filters the list. `TagUI.tsx` chips/AddTag are reused; the manage editor is relocated, not rebuilt.
- **Status footer**: reuse `ConnectionStatus.tsx`'s data (status fetch / `useStatusSocket`) rendered as the "Local · Whisper ready" line.
*Rationale:* the sidebar is the one genuinely structural change; concentrating the lifted state in the shell keeps pages presentational and avoids prop-drilling. A lightweight context (or hook) is preferred over Redux-style machinery for this small surface.

### 4. Shared primitives before page restyles
Build a small styled vocabulary the comps repeat, so page work is assembly, not bespoke CSS each time: `Card`/`Section`, `Button` (vermilion primary / paper-outline secondary / dark-pill), `Pill`/`Badge` (incl. status badges APPLIES INSTANTLY / RESTART REQUIRED / MIXED / READ-ONLY), `ListRow`, `Toggle`, `Stepper`, `Slider`, `SegmentedSelect`, `Avatar`, and a mono-meta text style. These map 1:1 to repeated comp patterns.

### 5. Per-screen mapping (comp → current page) — verified against the code
For each page: inventory current elements → map to a comp counterpart or mark "keep + restyle". The current state below was read from the source, so some mappings are reorganizations, not just restyles:

- **Recordings = `Dashboard.tsx`** — *today:* a flat newest-first list in a `max-w-3xl` column; a top "Start a recording" card (optional title input + button opening a **device-selection modal**); a tag-filter button row; an inline "Manage tags" editor (rename/recolor/delete); per-row status badge / title-rename / tags / duration / Retry / Open / Delete.
  - *New:* a filter header with a **name search** (net-new, client-side filter of the loaded list); **date-grouped** sections (net-new client bucketing — *Recent* = last 7 days, *Earlier this month*, *Last month*, *Older*); each row = status dot + serif title + mono meta (`time · duration · N speakers`; speaker count derived from loaded data) + tag pills + chevron; the in-progress row shows the existing processing % with a bar.
  - *Relocations (preserve, don't remove):* the **Record button + device modal** move to the sidebar, and the optional pre-record **Title** input moves *into* the device modal; **tag list + manage + filter** move to the sidebar; per-row **Delete** moves to the detail header (the comp shows a trash icon there), **Retry** stays on failed rows. Keep empty/failed/loading states (restyled).

- **Recording detail = `RecordingDetail.tsx`** — *today:* a 2-column layout — left = `Transcript | Chat` (**2 tabs**); right 360px sidebar = `AudioPlayer` (native `<audio>` + track switch) **and** Summary (`SummaryControls` template-select + Generate + the rendered sections). Header = ← Back, title-rename, date, status badge, tag chips, Copy .md/.txt. Processing banner has **Skip speakers** (diarization cancel); failed banner has **Retry**.
  - *New (reorg to match comp):* **breadcrumb** (Recordings / title); serif title + rename; mono meta (date · duration · lang — `duration_s`/`language` already loaded); **3 full-width tabs: Summary / Transcript / Ask AI**. Summary **moves out of the right sidebar into the Summary tab** (carrying `SummaryControls` + Copy/Export); "Chat" → "Ask AI" (same `TranscriptChat` + `PromptBar`); the 2-col grid + right sidebar are removed.
  - **Compact audio player** moves to a full-width bar above the tabs — **reuse the existing native `<audio>` + track-switch logic, restyled**; the comp's bespoke play/scrubber transport is an optional follow-up (decision 10), not required for parity.
  - **Speaker-avatar cluster + dropdown** in the header (new element): avatars from speaker initials + `speaker.color`; the dropdown reuses `renameSpeaker` + people-linking and shows You / linked / unnamed states. **Keep** the existing inline rename in `TranscriptChat` as an additional entry point (don't replace it).
  - **Delete** added to the header (the row's delete moves here); **Re-process** = existing reprocess. **Keep:** export-copy (.md/.txt), the processing progress + **Skip speakers**, the failed/Retry banner. **Transcript search** ("Search transcript…") is in the comp → net-new client-side segment filter (in scope, small).

- **Recording live = `RecordingScreen.tsx`** — *today:* centered "Recording" pill, big mono timer, a **single-value** input-level bar (`level` from `activeRecording` polling at 250ms), Stop, helper text. *New:* vermilion live pill, **serif recording title** (net-new — fetch via `getRecording`), big mono timer, restyled level meter. The comp's multi-bar waveform is decorative — we only have one live `level`, so render a styled meter (optionally level-driven bars); a true multi-band waveform needs backend data and is **out of scope**. Renders inside the shell (sidebar shows the live record state).

- **Settings = `Settings.tsx`**: maps directly onto the registry-driven page; section cards (AI / Transcription / Diarization / Advanced / Status) with icon + title + status badge + label/control rows via the primitives. **Keep:** reload-engine, data-folder reveal, Test connection, the cloud/local disclosure, and every registry field.

- **Ask / People / Templates** (no comp): apply tokens + primitives to the existing layouts; no restructure.

### 6. Sequencing (independently shippable)
Phase 0 tokens+fonts → Phase 1 shell → Phase 2 primitives → Phase 3 the four screens (Recordings → Detail → Live → Settings) → Phase 4 the comp-less pages. Verify visually after each via the run/preview. The `.dc.html` + `support.js` are references and never imported by the app.

### 7. Icons — Iconify via `@iconify/react`, bundled offline
The comps are icon-heavy (nav, section headers, row affordances, status), but the app today uses almost none (a few unicode glyphs like `●`, `←`, `×`, `■`). Use the **Iconify** ecosystem with the **`lucide`** set — its stroke weight matches the comp. **Offline is a hard requirement** (`app-shell` spec): icons MUST be bundled, with no runtime calls to the Iconify API (`api.iconify.design`).
- **Approach: `@iconify/react` with offline registration** (no Vite plugin). At startup, register the icons used via `addIcon`/`addCollection` from the bundled `@iconify-json/lucide` data, then render `<Icon icon="lucide:mic" />`. The default `<Icon>` would fetch from the Iconify API on a cache miss — registering up front prevents any network call. Register **only the icons used** (via `addIcon` per glyph) to keep the bundle small; whole-set `addCollection` is acceptable if size is fine.
- Wrap usage in a small `Icon` component / name map so glyph choices are centralized and swappable.
This replaces the earlier hand-copied-SVG plan and adds an Iconify dependency (`@iconify/react` + `@iconify-json/lucide`, approved). `unplugin-icons` was considered but the plugin-free `@iconify/react` offline path is preferred.

### 8. Tag colors — remap styles, keep token names (DB-compatible)
Tag colors are **persisted in the DB** as token names (`sky`, `emerald`, …) via `TAG_COLORS`/`tagChipClass` in `TagUI.tsx`, and the manage-tags UI writes those names. To avoid a data migration, **keep the same token names** but **remap their chip styles** to the warm palette, and update the color `<select>` swatches to match. Existing tags keep working and simply render warm. (The comp's named hues — client/internal/proposal/discovery — can be added as optional extra tokens later.)

### 9. Accessibility
Both themes MUST keep **visible focus states** on every interactive element and **AA contrast** for content text — watch muted on paper in light (`#9a9183` on `#fcfbf8`) and in dark (`#8d8474` on `#141210`): fine for secondary metadata, not for primary content. Preserve keyboard operability of existing controls (native `<select>`, the device dialog, tab switches, the speaker dropdown). Checked per-page and in verification.

### 10. Theme switching (light + dark)
The app supports both themes from decision 1. Mechanism:
- **State:** an `html[data-theme]` attribute toggled at runtime; tokens swap via the CSS-variable override. No per-component `dark:` classes.
- **Default:** follow the OS (`prefers-color-scheme`) on first run; a manual choice overrides and **persists** in `localStorage`. React to OS changes only while no manual override is set.
- **No flash:** apply the resolved theme to `<html>` **before first paint** (a tiny inline script in `index.html`, or set it in `main.tsx` before render).
- **Control:** a small theme toggle (auto / light / dark) in the sidebar footer near the status line — the comps don't show one, so it's an added control (allowed: we add, we don't remove). Tauri window chrome (`color-scheme`) follows the active theme.

## Risks / Trade-offs

- **Lifting Record/device/tags state into the shell** could regress `Dashboard.tsx` behavior. → Mitigation: move logic intact into the shell/hook; verify start-recording, device memory (`lastMicDevice`/`lastSystemDevice`), and tag filtering still work before restyling visuals.
- **Theme flip touches global base styles** (every screen currently assumes the old dark). → Mitigation: tokens land first; restyle page-by-page so unconverted pages still read acceptably against the new base; verify each.
- **Dual-theme upkeep + flash-of-wrong-theme**: two token sets to keep in sync, and a wrong-theme flash on load. → Mitigation: components reference semantic tokens only (no hex, no `dark:` per component), so only the `[data-theme="dark"]` variable block is duplicated; resolve + apply the theme before first paint; spot-check both themes per page.
- **"Don't remove un-shown elements" vs. comp minimalism**: comps omit real controls (export, diarization-cancel, Retry, failed/empty states, per-row Delete). → Mitigation: explicit per-page inventory (done in decision 5); keep + restyle anything not pictured, relocating where the comp implies (e.g. Delete → detail header). The bespoke audio scrubber stays a follow-up (keep native `<audio>`); transcript and name search ARE in the comp and are built (client-side).
- **Detail-page reorg is more than a restyle**: Summary moves from the right sidebar into a Summary tab and the 2-col grid is removed. → Mitigation: re-parent `SummaryControls`/`AudioPlayer`/summary-rendering intact; verify generate/regenerate, copy/export, and audio track-switch still work after the move.
- **Tag-color remap could orphan stored colors**: colors persist in the DB as token names. → Mitigation: keep the names, only remap styles (decision 8); no migration, existing tags render warm.
- **Font bundling + packaging**: bundled woff2 must survive the Vite build and the PyInstaller/Tauri bundle. → Mitigation: use `@fontsource` (import in `main.tsx`/`index.css`), verify the production `vite build` and that no Google request is made.
- **Sidebar on a narrow desktop window**: 252px sidebar + main needs a sensible minimum. → Mitigation: fixed sidebar with a scrollable main; no responsive/mobile work in scope (desktop app).

## Migration Plan

1. Add the light + dark token sets + bundled fonts (`@fontsource`); copy `sirina-mark.svg` into the app; add the pre-paint theme bootstrap (`index.css` + `index.html`/`main.tsx`). App still runs (pages look transitional).
2. Build the `Shell` (+ the offline Iconify `Icon` setup) and move Record/device/tags/status into it; swap the `App.tsx` header for the sidebar; routes unchanged.
3. Add the primitives.
4. Restyle the four designed screens in order; verify each in the running app.
5. Theme-only restyle of Ask/People/Templates and shared components.
6. Rollback: the change is additive-by-phase and frontend-only; reverting the commits restores the previous (pre-redesign) UI with no data impact.

Note: the macOS traffic-light titlebar in the comps is the OS window chrome (Tauri), not app UI — out of scope.

## Open Questions (resolved)

- **Fonts:** use `@fontsource/*` packages (newsreader, hanken-grotesk, jetbrains-mono) — simplest Vite/PyInstaller integration. Resolved.
- **Date buckets:** Recent (≤ 7 days) / Earlier this month / Last month / Older. Resolved (fall back to Today/Earlier if grouping proves fiddly).
- **Transcript & name search:** in scope (client-side filters — both appear in the comp). The bespoke **audio scrubber** is a follow-up; keep the native `<audio>` element.
- **Per-tag counts** (comp shows numbers next to tags): optional — derive client-side if cheap, otherwise omit.
- **Audio player transport:** keep native `<audio controls>` (functional + accessible) restyled; a custom play/scrubber UI is a later nicety, not parity-blocking.
