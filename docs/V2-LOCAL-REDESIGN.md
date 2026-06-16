# V2 — Local Meeting Recorder (Jamie-style) — Redesign

Status: **proposal / roadmap** (no code written yet)
Author: planning doc, 2026-05-18
Supersedes: the live Discord-bot architecture in [README](../README.md) and [the v1 plan](../../.claude/plans/i-would-like-to-snappy-otter.md)

---

## 1. Vision

Turn the current app from a **live Discord transcriber** into a **local, post-hoc meeting recorder** in the spirit of Jamie / Granola / Otter:

1. **Record locally** — capture system audio (the call) + your microphone, to disk. Nothing else runs during the recording.
2. **No live transcription, no live AI** — recording is cheap and silent. CPU stays free so the call is smooth.
3. **Process after stop** — when you end the recording, run high-quality transcription, speaker diarization, and (optionally) an AI summary as a background job.
4. **Speakers & people** — detect distinct speakers, label them `Speaker 1/2/…`, let you rename them per-recording with autocomplete from people you've named before.
5. **Structured summary templates** — multi-section templates (title + prompt per section), stored as JSON, seeded in code, expandable to user-edited later.
6. **Organise** — tag recordings; browse a People directory; manage everything from the dashboard.
7. **Ship as a Mac app** — wrap in Tauri, unsigned (no Apple Developer subscription).

The Discord direction is a **dead end** (DAVE E2EE enforcement) and will be removed entirely.

---

## 2. What changes vs v1

| Area | v1 (now) | v2 (target) |
| --- | --- | --- |
| Audio source | Discord voice-recv **or** local sounddevice | **Local only** (system audio + mic) |
| Transcription | Live, 5–8s chunks, realtime pressure | **Offline, whole-file, high quality** |
| AI | Live "aspects" every 60s | **Post-hoc**, structured multi-section summaries |
| Speakers | Per-Discord-user (free labels) | **Diarization** → `Speaker N` → renamed to People |
| During recording | Whisper + Ollama running hot | **Idle** — just writing audio to disk |
| Summary format | Single freeform block | **Sections** (title + content), template-driven |
| Organisation | Flat list | **Tags + People directory** |
| Packaging | Two dev servers | **Tauri .app** (+ dev mode still works) |
| Discord | Core dependency | **Removed** |

---

## 3. Target architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    Tauri app (macOS .app)                      │
│   React UI  ──localhost──>  Python backend (sidecar)           │
└───────────────────────────────────────────────────────────────┘

RECORDING (cheap, no inference)
  System audio (ScreenCaptureKit / BlackHole) ─┐
                                               ├─> writer ─> recording.wav (+ mic.wav)
  Microphone (CoreAudio) ──────────────────────┘            on disk

STOP ──> enqueue ProcessingJob
                  │
                  ▼
POST-PROCESSING (background, one job at a time)
  1. Transcribe   faster-whisper (large/medium, beam search, VAD, word ts)
  2. Diarize      pyannote.audio  ->  speaker turns
  3. Assign       overlap match: each segment -> Speaker N
  4. Persist      Segments + Speakers
  5. Summarize    per-template: each section -> Ollama -> section content
                  │
                  ▼
            status: ready  ──ws/poll──>  UI updates
```

**Key principle:** recording and processing are fully decoupled. Recording writes raw audio and returns instantly. Processing is a separate, resumable, restart-safe job.

---

## 4. Data model (v2)

SQLModel tables. New or changed tables in **bold**.

```python
# --- core recording ---
class Recording(table):
    id: int
    title: str | None
    created_at: datetime
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    status: str            # recording | processing | ready | failed
    audio_path: str        # path to mixed/primary wav
    mic_path: str | None   # optional separate mic track
    system_path: str | None
    language: str | None   # detected or forced
    error: str | None

# --- people & speakers ---
class Person(table):                         # NEW
    id: int
    name: str                                # unique-ish, used for autocomplete
    created_at: datetime

class Speaker(table):                         # NEW  (per-recording label)
    id: int
    recording_id: int (fk)
    label: str            # "Speaker 1" (default, diarization order)
    person_id: int | None (fk -> Person)     # set when user names them
    color: str | None     # stable UI color

# --- transcript ---
class Segment(table):                          # CHANGED: speaker_id instead of discord user
    id: int
    recording_id: int (fk)
    speaker_id: int | None (fk -> Speaker)
    start_ts: float
    end_ts: float
    text: str

# --- summaries (structured) ---
class SummaryTemplate(table):                  # CHANGED: JSON sections
    id: int
    name: str
    sections: JSON         # [{ "title": "...", "prompt": "..." }, ...]
    is_default: bool
    builtin: bool          # seeded-in-code, not user-deletable

class Summary(table):                           # CHANGED: JSON section outputs
    id: int
    recording_id: int (fk)
    template_id: int | None (fk)
    sections: JSON         # [{ "title": "...", "content": "..." }, ...]
    created_at: datetime

# --- tags ---
class Tag(table):                               # NEW
    id: int
    name: str
    color: str | None

class RecordingTag(table):                      # NEW  (m2m)
    recording_id: int (fk)
    tag_id: int (fk)

# --- Q&A (kept, repointed to recording) ---
class QAMessage(table):
    id: int
    recording_id: int (fk)
    role: str              # user | assistant
    content: str
    created_at: datetime
```

`JSON` columns use SQLAlchemy `JSON`/`sa_column`. **No backwards-compatibility / no migration of v1 data — decided.** v2 starts from a clean `data/` (drop the old SQLite file and recorded audio). This frees us to design the schema cleanly without `ALTER TABLE` gymnastics or carrying Discord-era columns. The `PRAGMA table_info` migration pattern in [db.py](../backend/app/db.py) is still used going forward for *future* v2 schema tweaks.

### Speaker → Person semantics (important)

- Diarization produces anonymous clusters per recording → we create `Speaker` rows `Speaker 1..N`.
- Renaming `Speaker 1` → "Stefan" **within a recording** links that `Speaker.person_id` to a `Person` (creating the Person if new).
- It does **not** retroactively rename speakers in other recordings — each recording diarizes independently, and Speaker 1 in another meeting may be someone else.
- The **autocomplete** when renaming pulls names from the `Person` table, so you reuse "Stefan", "Marta", … without retyping.
- The **People page** aggregates across recordings via `Speaker.person_id`.

---

## 5. Recording pipeline (cheap path)

Goal: near-zero CPU. No model touches audio during a recording.

1. **Capture** two streams at the device's native rate:
   - **System audio** = the call you hear (everyone else).
   - **Microphone** = you.
2. **Write to disk** incrementally (streaming WAV writer; 16-bit PCM). Keep tracks separate:
   - `mic.wav` (you) and `system.wav` (others), **plus** a mixed `recording.wav` for playback/fallback.
   - Separate tracks give us a free first-order diarization: mic = you, system = others.
3. **Stop** → finalize files, compute duration, set status `processing`, enqueue a `ProcessingJob`, return immediately.

The recorder is a small state machine (`idle → recording → finalizing`) replacing the live `Pipeline`/`Chunker`/whisper-queue machinery. Recording uses **no** `faster-whisper`, **no** `silero-vad`, **no** Ollama.

### Capture strategy (the BlackHole problem)

| Phase | Mechanism | UX |
| --- | --- | --- |
| **Now (Python)** | `sounddevice` reads **BlackHole 2ch**; user sets a **Multi-Output Device** so they still hear audio | Works today, but requires manual Audio MIDI Setup |
| **Target (Tauri)** | Native **ScreenCaptureKit** (macOS 13+) taps system audio directly + CoreAudio mic | **No BlackHole, no Multi-Output** — like Jamie. Captures whatever plays, regardless of output device |

ScreenCaptureKit is how Jamie "uses your headphone source and still records both sides": it taps the system audio mix at the OS level, independent of the chosen output device. Implement it in the Tauri Rust layer (e.g. via `cidre`/`screencapturekit` crates) or a tiny Swift sidecar that streams PCM to the backend. Until then, BlackHole + Multi-Output is the documented interim path.

> Requires the **Screen Recording** permission (system audio) and **Microphone** permission. Tauri must declare both; first run prompts the user.

---

## 6. Post-processing pipeline (quality path)

Runs as a background job, one recording at a time (queue), restart-safe (on boot, re-enqueue any `processing` recordings).

### 6.1 Transcription — optimised for quality, not latency

Because we're offline, drop every realtime compromise:

```python
faster_whisper transcribe(
    model      = "large-v3"  (configurable; medium as a faster default)
    beam_size  = 5                       # was 1
    vad_filter = True                    # built-in Silero VAD removes silence
    condition_on_previous_text = True    # was False — full context, better coherence
    word_timestamps = True               # needed to align with diarization
    language   = forced or auto
    initial_prompt = vocabulary hints    # keep WHISPER_INITIAL_PROMPT
)
```

Speed back: use `BatchedInferencePipeline` (faster-whisper) for ~3–4× throughput on long files. On Apple Silicon, CTranslate2 runs on **CPU** (no Metal) — `compute_type=int8` or `int8_float16`. A 30-min meeting on `large-v3` batched ≈ a few minutes on an M-series; acceptable for post-hoc.

### 6.2 Diarization — who spoke when

- **Baseline (no extra model, no token):** two-track capture. `mic.wav` → "You", `system.wav` → "Others". Good enough for 1:1 calls.
- **Enhanced (multi-speaker):** [`pyannote.audio`](https://github.com/pyannote/pyannote-audio) `pyannote/speaker-diarization-3.1`.
  - Outputs `{start, end, speaker}` turns.
  - Runs on **MPS/GPU** on Apple Silicon (unlike whisper) — reasonably fast.
  - Gated model: needs a free **HuggingFace token** + accepting the model terms once. Make it optional/configurable; degrade gracefully to the two-track baseline when absent.
  - For in-room meetings (single mic, multiple people), this is the only way to separate speakers.
  - **Cost: free and unlimited.** The model is MIT-licensed and runs **100% locally** in pure PyTorch. The HF token is only used to authenticate the **one-time model download** (HF gates it behind a terms-acceptance click on `pyannote/segmentation-3.0` **and** `pyannote/speaker-diarization-3.1`). After download, every meeting is processed offline on your Mac — **no API calls, no per-meeting charge, no monthly cap.** Process as many meetings as you like. (Not to be confused with pyannoteAI's separate paid **cloud "Precision" API** — we don't use it.)
  - **One-time setup:** create a free account at huggingface.co → accept the conditions on both model pages → generate a read token at hf.co/settings/tokens → put it in `HF_TOKEN`. That's the entire cost.
- **Alternative considered:** [WhisperX](https://github.com/m-bain/whisperX) bundles faster-whisper + alignment + pyannote in one pass. Cleaner pipeline but heavier deps and version-pinning pain. **Recommendation:** faster-whisper + pyannote, aligned by us; revisit WhisperX if alignment quality is insufficient.

### 6.3 Assignment — segment → speaker

For each whisper segment (word-timestamped), assign the diarization speaker with the **maximum temporal overlap**. Create `Speaker 1..N` rows in first-appearance order, attach `segment.speaker_id`. If diarization is disabled, map mic→Speaker "You", system→Speaker "Others".

### 6.4 Summarization — structured, template-driven

For the recording's chosen (or default) `SummaryTemplate`:
- For each section `{title, prompt}`: call Ollama with `prompt` + the full transcript (speaker-attributed) → section `content`.
- Store `Summary.sections = [{title, content}, …]`.
- Multiple sections = multiple small focused prompts → better quality than one mega-prompt, and each section renders as its own card.
- **Auto-summary on stop (decided):** after transcription completes, **always** generate one summary using the **default template** — no user action needed. The recording becomes `ready` with a summary already present.
- **Regenerate with another template:** the detail view's Summary tab has a template selector + "Generate" button. Picking a different template runs it and stores an additional `Summary` row (keep history; show the latest, allow switching between generated summaries). The default-on-stop summary is just the first one.

---

## 7. Summary templates (multi-section JSON)

Seeded in code, stored in DB, structured so a future "template editor" UI is a thin add-on.

```jsonc
// SummaryTemplate.sections
[
  { "title": "TL;DR",        "prompt": "Summarise the meeting in 2-3 sentences." },
  { "title": "Key decisions","prompt": "List the concrete decisions made. Bullet points." },
  { "title": "Action items", "prompt": "List action items with owner and due date if mentioned." },
  { "title": "Open questions","prompt": "List unresolved questions or topics deferred." }
]
```

Seed a few builtins: **Standard meeting**, **1:1**, **Sales call**, **Standup**. `builtin: true` rows are not deletable (clone-to-edit). Placeholders available to prompts: `{{transcript}}`, `{{speakers}}`, `{{title}}`, `{{date}}`. (Reuse the simple `{{var}}` renderer from [ollama_client.py](../backend/app/llm/ollama_client.py).)

---

## 8. Tags

- Free-form `Tag` (name + optional color), m2m to recordings.
- Dashboard: filter recordings by tag; quick-add/remove on each row; a small tag manager.
- Cheap, high-value organisation. No AI involved.

---

## 9. People page

Route `/people`. Aggregates over `Person` + `Speaker`:

| Column | Source |
| --- | --- |
| Name | `Person.name` |
| Meetings | count of distinct `recording_id` via `Speaker.person_id` |
| Last meeting | max `Recording.started_at` for those |
| Actions | **Rename** (updates Person, cascades to display), **Delete** (unlinks speakers → revert to `Speaker N`) |

Renaming here is global to the Person (intentional — it's the same human). Deleting a Person unlinks; it does not delete recordings or speakers.

---

## 10. UI changes

Remove live-centric pieces, add post-hoc + organisation.

**Remove:** `AspectsPanel`, `PromptBar`'s live mode, `ConnectionStatus` (Discord), `useMeetingSocket` live-segment streaming, Discord channel inputs, source toggle.

**Pages:**
- **Dashboard** — big **Record** button (+ device/source picker), live elapsed timer + level meter while recording (no transcript), recordings list with status badges (`processing…`, `ready`), tag chips + tag filter.
- **Recording detail** —
  - **Transcript tab**: speaker-grouped bubbles; click a speaker name → inline rename with **autocomplete** of existing People; audio player with seek-to-segment.
  - **Summary tab**: section cards; template selector; "Generate / Regenerate"; export.
  - **Ask tab**: Q&A over the finished transcript (kept from v1).
  - Tag editor in the header.
- **People** — directory table (section 9).
- **Templates** — list + (later) section editor; v2 can ship read-only/builtins first.

**Recording states in UI:** `recording` (timer + meter), `processing` (spinner + step label: transcribing → diarizing → summarizing), `ready` (full view), `failed` (error + retry).

Progress updates: a lightweight `/ws/recordings/{id}` status channel (reuse the existing `ConnectionManager` in [ws.py](../backend/app/api/ws.py)) or simple polling. No more per-segment streaming.

---

## 11. Whisper quality & performance

Recording perf is solved structurally (no inference while recording). Transcription quality/perf knobs:

- **Bigger model offline**: default `large-v3` (or `large-v3-turbo` for ~tradeoff); `medium` as the "fast" option. Configurable.
- **Batched inference** (`BatchedInferencePipeline`) for long-file throughput.
- **`vad_filter=True`** skips silence → less audio to decode → faster + fewer hallucinations.
- **`beam_size=5` + `condition_on_previous_text=True`** → markedly better accuracy than the realtime path.
- **`word_timestamps=True`** for diarization alignment.
- **Language**: keep `WHISPER_LANGUAGE` (forcing `es`/`de`/… avoids the per-chunk mis-detection we hit). Auto-detect is now reliable since we detect once over the whole file.
- **Vocabulary**: keep `WHISPER_INITIAL_PROMPT` (e.g. `EcoHubs, Mediakular, Arcos`).
- **Threads**: tune `cpu_threads`/`num_workers` to the Mac's core count.

New/changed config keys for v2 (`.env`): `HF_TOKEN` (free HuggingFace read token for the one-time pyannote model download — see §6.2), `DIARIZATION_ENABLED` (bool; falls back to the two-track baseline when off or token missing), `WHISPER_MODEL` default bumped to a `large` variant. Removed: `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, `ASPECTS_INTERVAL_SECONDS`, `CHUNK_MAX_SECONDS`, `CHUNK_SILENCE_MS` (all live-path only).

Net: dramatically better transcripts than the 5-second-chunk realtime approach, at the cost of a few minutes of post-processing the user doesn't have to watch.

---

## 12. Removing Discord

Delete and clean up:

- `backend/app/bot/` (whole dir: `client.py`, `sink.py`, `chunker.py`)
- Deps: `py-cord` / `discord.py`, `discord-ext-voice-recv` (and the monkey-patches), `silero-vad` (if not reused — note: offline `vad_filter` uses faster-whisper's bundled Silero, so the standalone dep can go)
- Config: `DISCORD_TOKEN`, `DISCORD_GUILD_ID` from [config.py](../backend/app/config.py) and `.env.example`
- API: the Discord branch in `meetings.py` `start`, the `source` toggle, `current_voice_channel_name`, status fields `bot_connected`/`voice_channel`
- `runtime.bot`, bot lifespan wiring in [main.py](../backend/app/main.py)
- Frontend: Discord source option, channel-ID inputs, `ConnectionStatus`

Rename the domain from "meeting/bot" to "recording" throughout (`Meeting` → `Recording`, `/api/meetings` → `/api/recordings`). The project can also be renamed (`live-transcript-bot` → e.g. `meeting-recorder`) — cosmetic, do last.

---

## 13. Tauri packaging (unsigned macOS)

Wrap the existing React frontend; run the Python backend as a **sidecar**.

- **Frontend**: Vite build → Tauri `dist`. Minimal changes (it already talks to `localhost`).
- **Backend sidecar**: bundle the Python app with **PyInstaller** into a single binary; declare it as a Tauri `externalBin`; Tauri spawns it on launch, frontend hits `127.0.0.1:<port>`. Models (whisper/pyannote) download to a user data dir on first run, or are pre-fetched.
- **Permissions / entitlements**: Microphone + Screen Recording (system audio). Add usage descriptions; first launch prompts.
- **Unsigned distribution (no Apple Developer account):**
  - Build `.app`/`.dmg` without notarization.
  - **Ad-hoc sign** locally so it runs without "damaged" errors: `codesign --force --deep --sign - <App>.app`.
  - Users bypass Gatekeeper once: right-click → **Open**, or `xattr -dr com.apple.quarantine <App>.app`.
  - Document this clearly. (Without notarization there's no way around the first-open warning — acceptable for personal/internal use.)
- **Native audio**: the Tauri/Rust layer is also where ScreenCaptureKit lives (section 5), removing BlackHole. This is the main reason Tauri is worth it beyond packaging.

Keep the `./dev.sh` two-server flow for development; Tauri is the distribution wrapper, not a dev-time requirement.

---

## 14. Phased roadmap

Each phase is independently shippable and testable.

1. **Strip Discord** — remove bot, deps, config, UI; collapse to local-only. App still does live local transcription (temporary) so nothing breaks mid-refactor.
2. **Record→file** — replace live pipeline with a recorder that writes `mic.wav` + `system.wav` + mixed; recording status; no inference while recording.
3. **Offline transcription job** — background queue; high-quality faster-whisper; `Recording.status` lifecycle; detail view shows transcript when ready.
4. **Speakers (baseline)** — two-track → "You"/"Others"; `Speaker` rows; rename UI with People autocomplete; `Person` table; People page.
5. **Diarization (enhanced)** — pyannote integration (optional, token-gated); overlap assignment; `Speaker N` for in-room/multi-speaker.
6. **Structured summaries** — JSON section templates; seed builtins; per-section Ollama; section-card UI; auto-summary on completion.
7. **Tags** — model, m2m, dashboard filter + manager.
8. **Polish** — exports (md/txt/json) with speakers + sections; audio player seek-to-segment; settings page (model, language, diarization on/off, HF token).
9. **Tauri** — sidecar packaging, permissions, unsigned `.app`; then ScreenCaptureKit native capture to drop BlackHole.

Phases 1–3 deliver the core "record now, transcribe after" value. 4–6 deliver the Jamie-like speaker + summary experience. 7–9 are organisation + distribution.

---

## 15. Decisions & open questions

### Resolved

1. **Diarization** — **use pyannote** for multi-speaker; it's free and unlimited (local inference, §6.2). Ship the two-track "You/Others" baseline first (works with zero setup), then layer pyannote on top in phase 5. When no `HF_TOKEN` is present, gracefully fall back to the baseline.
2. **Auto-summary on stop** — **yes, always generate a default-template summary** when transcription finishes; allow regenerating with a different template afterward, keeping summary history (§6.4).
3. **Clean DB reset** — **yes, no backwards-compatibility.** v2 starts fresh; drop old data (§4).

### Still open

4. **Default whisper model**: `large-v3` (best, slower) vs `large-v3-turbo`/`medium` (faster) as the out-of-box default? (All configurable; leaning `large-v3-turbo` for the quality/speed balance.)
5. **Project rename**: rename repo/package away from `live-transcript-bot` now, or keep the folder name and just rename internals? (Cosmetic; do last.)
6. **Tauri scope**: package the Python sidecar as-is first (fast), then invest in native ScreenCaptureKit capture (removes BlackHole) — confirm that two-step ordering.

---

## 16. Notes carried over from v1 (still useful)

- Vocabulary hinting via `WHISPER_INITIAL_PROMPT` works well for domain terms (`EcoHubs`, `Arcos`, `Mediakular`).
- Forcing `WHISPER_LANGUAGE` avoids language mis-detection; less critical offline (whole-file detection is reliable) but still useful for known-language meetings.
- Ollama summaries on an 8B model take seconds on CPU/Metal — fine for post-hoc, and no longer competes with whisper for CPU since they run sequentially in the job.
- The `{{var}}` prompt renderer and `ConnectionManager` WS fan-out are reusable as-is.
```
