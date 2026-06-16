## Why

Once recordings are captured to disk (`record-to-file`), they need to be transcribed. Running transcription offline — after the meeting, over the whole file — lets us drop every realtime compromise and use a bigger model with beam search and full context, producing markedly better transcripts than the old 5-second-chunk live path. See [docs/V2-LOCAL-REDESIGN.md §6.1](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Add a **background processing job** that runs when a recording is stopped: it transcribes the recording's audio and stores `Segment` rows, then sets status `ready`.
- Run **one job at a time** (a simple queue) and make it **restart-safe**: on boot, any recording stuck in `processing` is re-enqueued.
- Use **high-quality faster-whisper settings**: larger model (configurable, default a `large` variant), `beam_size=5`, `vad_filter=True`, `condition_on_previous_text=True`, `word_timestamps=True`; batched inference for throughput.
- Detect language once over the whole file (or honor a forced `WHISPER_LANGUAGE`); keep `WHISPER_INITIAL_PROMPT` vocabulary hints.
- UI: the recording detail view shows a **processing state** (step label + spinner), then renders the transcript when `ready`; progress surfaced via the existing WebSocket/status channel.

## Capabilities

### New Capabilities
- `transcription-job`: a restart-safe background queue that transcribes a stopped recording's audio with high-quality offline settings and persists segments with word-level timing.
- `transcript-view`: the detail UI states (`processing` → `ready`) and rendering of the stored transcript.

### Modified Capabilities
<!-- None archived yet; builds on record-to-file's recording-store. -->

## Impact

- **Backend**: new `app/processing/` job runner + queue; `app/transcribe/whisper.py` upgraded for offline quality (batched pipeline, beam, VAD, word timestamps); writes `Segment` rows with `start/end/text` (speaker assignment comes in `speakers-and-people`).
- **Status**: recording transitions `processing → ready` (or `failed` with `error`).
- **Frontend**: detail view processing/ready states; remove any remaining live-transcript assumptions.
- **Config**: default `WHISPER_MODEL` bumped to a `large` variant; transcription threads tunable.
- **Depends on**: `record-to-file` (needs audio files + `Recording` lifecycle).
