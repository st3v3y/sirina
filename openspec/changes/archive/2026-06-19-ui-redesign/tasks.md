## 1. Design tokens + fonts + assets (foundation)

- [x] 1.1 Add the bundled fonts via `@fontsource/*` (newsreader, hanken-grotesk, jetbrains-mono) and import them so no Google CDN is used
- [x] 1.2 Define the Tailwind 4 `@theme` tokens in `index.css`: palette (paper/surface/ink/ink-2/muted/label/signal/signal-bright/ok/warn, tag + speaker colors), font families (serif/sans/mono), radii, shadows — **light values on `:root`, dark overrides under `[data-theme="dark"]`** (vermilion signal shared)
- [x] 1.3 Set the base bg/text from tokens + `color-scheme: light dark`; add the **pre-paint theme bootstrap** (resolve OS preference / saved choice and set `html[data-theme]` before first paint); remove the old dark base styles
- [x] 1.4 Copy `design/redesign/assets/sirina-mark.svg` into the app (e.g. `src/assets`) for the sidebar logo
- [x] 1.5 Verify `npm run build` succeeds and the app renders on the light base with fonts loading from bundled assets (no external font request)

## 2. App shell (sidebar)

- [x] 2.1 Set up offline Iconify icons: install `@iconify/react` + `@iconify-json/lucide`; register the lucide icons used via `addIcon` at startup (NO runtime Iconify API calls); add a small `Icon` wrapper / name map (nav, record, mic, tags, settings, chevrons, status, search, etc.)
- [x] 2.2 Create a `Shell` component (left sidebar 252px + main outlet) with the logo and nav items (Recordings/Ask/People/Templates/Settings) with router-driven active state
- [x] 2.3 Lift Record-start + capture-device state out of `Dashboard.tsx` into the shell (or a shared `useRecorder` hook); the sidebar Record button opens the existing device-selection modal; move the optional pre-record **Title** input into that modal; preserve last-used-device memory (`lastMicDevice`/`lastSystemDevice`)
- [x] 2.4 Show live recording state in the sidebar Record control while recording (active indicator + elapsed timer)
- [x] 2.5 Move the Tags list + create + filter **and the manage editor (rename/recolor/delete)** into the sidebar; lift filter state so the Recordings page reads it (context or hook); reuse `TagUI` chips
- [x] 2.6 Render the runtime status footer ("Local · Whisper ready") reusing `ConnectionStatus.tsx` data
- [x] 2.7 Add a theme toggle (auto / light / dark) in the sidebar footer: set `html[data-theme]`, persist to `localStorage`, and follow OS changes while no manual override is set
- [x] 2.8 Replace the top header in `App.tsx` with the `Shell`; keep all routes unchanged; verify nav + record + device memory + tag filter/manage + status + theme toggle all work

## 3. Shared primitives + tag-color remap

- [x] 3.1 `Card`/`Section`, `Button` (vermilion primary / paper-outline secondary / dark-pill), `Pill`/`Badge` (incl. status badges: APPLIES INSTANTLY / RESTART REQUIRED / MIXED / READ-ONLY)
- [x] 3.2 `ListRow`, `Avatar` (initials + color), tag pill, and a mono-meta text style
- [x] 3.3 Form controls: `Toggle`, `Stepper`, `Slider`, `SegmentedSelect` matching the comp
- [x] 3.4 Remap `TagUI` chip styles + the manage-tags color swatches to the warm palette, **keeping the existing token names** (`sky`/`emerald`/… stay valid so stored tag colors don't break)

## 4. Restyle the designed screens

- [x] 4.1 Recordings (`Dashboard.tsx`): filter header with **name search** (client-side); **date-grouped** sections (Recent ≤ 7d / Earlier this month / Last month / Older); rows = status dot + serif title + mono meta (`time · duration · N speakers`) + tag pills + chevron; in-progress row with a progress bar; relocate per-row **Delete** to the detail header, keep **Retry** on failed rows; keep empty/failed/loading states (restyled)
- [x] 4.2 Recording detail (`RecordingDetail.tsx`) layout reorg: breadcrumb; serif title + rename; mono meta (date · duration · lang); **3 full-width tabs Summary / Transcript / Ask AI** — move Summary (`SummaryControls` + Copy/Export) out of the right sidebar into the Summary tab; remove the 2-col grid
- [x] 4.3 Recording detail components: relocate the existing native `<audio>` + track-switch into a full-width compact player above the tabs (restyled); add the header **speaker-avatar cluster + dropdown** (reuse `renameSpeaker`/people-link; **keep** the inline rename in `TranscriptChat`); add **Delete** to the header; add **transcript search** (client-side segment filter); keep the Skip-speakers (diarization-cancel) and failed/Retry banners
- [x] 4.4 Recording live (`RecordingScreen.tsx`): vermilion live pill, **serif recording title** (fetch via `getRecording`), big mono timer, restyled input-level meter (single `level` value), Stop button
- [x] 4.5 Settings (`Settings.tsx`): section cards with icon + title + status badge + label/control rows using the primitives; keep reload-engine, data-folder reveal, Test connection, cloud/local disclosure, and every registry field
- [ ] 4.6 Verify each restyled screen in the running app against its comp; confirm no pre-existing control/action/route was dropped

## 5. Restyle the comp-less pages (theme only)

- [x] 5.1 Apply tokens/primitives to `Ask.tsx` (no layout change)
- [x] 5.2 Apply tokens/primitives to `People.tsx` (no layout change)
- [x] 5.3 Apply tokens/primitives to `Templates.tsx` (no layout change)
- [x] 5.4 Restyle shared components (`PromptBar.tsx`, `TranscriptChat.tsx`, `ConnectionStatus.tsx`) to the new tokens

## 6. Verification

- [x] 6.1 Sidebar is present and active-marked on every screen; navigating keeps the shell
- [x] 6.2 Record + device selection work from any screen (sidebar → modal); the sidebar reflects live recording; last-used devices remembered; the optional pre-record title is still settable (in the modal)
- [x] 6.3 Selecting a sidebar tag filters the recordings list; tag create + manage (rename/recolor/delete) work; existing stored tag colors render in the warm palette with no migration
- [x] 6.4 Status footer reflects transcription-ready and LLM-reachable states
- [x] 6.5 Detail: all 3 tabs work; Summary generate/regenerate + copy/export; audio track-switch; speaker rename via the header dropdown AND inline; transcript search; Skip-speakers; Retry; Delete
- [x] 6.6 App runs offline with fonts **and icons** from bundled assets; no external font/asset request (incl. no Iconify API call)
- [x] 6.7 Theme defaults to the OS preference; the toggle (auto/light/dark) applies immediately and persists across launch; both themes render correctly with no flash of the wrong theme
- [x] 6.8 Accessibility: visible focus states in **both themes**; AA contrast for content text; keyboard operability of selects, the device dialog, tab switches, and the speaker dropdown
- [x] 6.9 Spot-check each page: every control/action/route that existed before the redesign is still present and functional
- [x] 6.10 `npm run build` (tsc + vite) passes
