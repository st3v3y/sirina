import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api, type RecordingDetail as TR, type Segment, type Speaker, type Summary, type QAMessage, type SummaryTemplate } from "../lib/api";
import TranscriptChat from "../components/TranscriptChat";
import Markdown from "../components/Markdown";
import PromptBar from "../components/PromptBar";
import { TagChip, AddTagButton } from "../components/TagUI";
import { catColor } from "../lib/tagColors";
import { Avatar, Button } from "../components/ui";
import { Icon } from "../components/Icon";
import { confirmDialog } from "../lib/confirm";
import { useShell } from "../lib/shell";

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued…",
  preparing_model: "Preparing the speech model (first time only, a few minutes)…",
  drafting: "Writing a quick draft…",
  transcribing: "Transcribing…",
  diarizing: "Identifying speakers…",
  summarizing: "Generating summary…",
  compressing: "Compressing audio…",
  done: "Finishing up…",
};

function fmtElapsed(s: number) {
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
}
function fmtDuration(s: number | null) {
  if (s == null) return "—";
  const total = Math.floor(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const ss = (total % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}
// Human phrase for a silence gap, e.g. "2 h 5 min", "3 min", "45 sec".
function fmtGap(s: number) {
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.round((total % 3600) / 60);
  if (h > 0) return m > 0 ? `${h} h ${m} min` : `${h} h`;
  if (m > 0) return `${m} min`;
  return `${total} sec`;
}

async function copyToClipboard(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(ta);
  }
}

const TRACK_LABEL: Record<string, string> = { mixed: "Mixed", mic: "Mic (you)", system: "System (others)" };

function AudioPlayer({ recordingId, tracks }: { recordingId: number; tracks: string[] }) {
  const ordered = ["mixed", "mic", "system"].filter((t) => tracks.includes(t));
  const [track, setTrack] = useState<string>(ordered[0] ?? "mixed");
  if (ordered.length === 0) return null;
  return (
    <div className="flex items-center gap-3 border border-line-2 rounded-card bg-surface shadow-card px-3.5 py-2.5">
      <audio
        key={track}
        controls
        className="h-9 flex-1 min-w-0"
        src={api.audioUrl(recordingId, track as "mixed" | "mic" | "system")}
      />
      {ordered.length > 1 && (
        <div className="flex gap-1 shrink-0">
          {ordered.map((t) => (
            <button
              key={t}
              onClick={() => setTrack(t)}
              className={`text-[11px] px-2 py-1 rounded-field border ${
                track === t ? "bg-ink text-paper border-ink" : "border-line text-ink-2 hover:bg-surface-2"
              }`}
            >
              {TRACK_LABEL[t] ?? t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SummaryControls({ onSummarize }: { onSummarize: (templateId: number) => Promise<void> }) {
  const [templates, setTemplates] = useState<SummaryTemplate[]>([]);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listSummaryTemplates().then((t) => {
      setTemplates(t);
      setTemplateId((t.find((x) => x.is_default) ?? t[0])?.id ?? null);
    });
  }, []);

  async function run() {
    if (!templateId) return;
    setBusy(true);
    try {
      await onSummarize(templateId);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted">Template</span>
      <select
        value={templateId ?? ""}
        onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : null)}
        className="h-8 px-2.5 border border-line rounded-field bg-surface text-[12.5px] text-ink-2 focus:outline-none"
      >
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <button
        onClick={run}
        disabled={busy || !templateId}
        className="h-8 px-3 rounded-field border border-line text-[12.5px] text-ink-2 hover:bg-surface-2 disabled:opacity-50 inline-flex items-center gap-1.5"
      >
        <Icon name="refresh-cw" size={12} /> {busy ? "…" : "Regenerate"}
      </button>
    </div>
  );
}

// Up to this many distinct clips per speaker; each press of the play button plays the
// next one, so a short ambiguous "yeah" doesn't decide whether you recognise a voice.
const MAX_SAMPLE_CLIPS = 5;
const SAMPLE_CLIP_S = 8;

/** Voice-sample windows for a speaker: their longest lines, preferring ones where nobody
 *  else is talking at the same time (crosstalk makes a voice hard to recognise). */
function sampleClips(segments: Segment[], speakerId: number): [number, number][] {
  const mine = segments.filter((s) => s.speaker_id === speakerId && s.end_ts - s.start_ts >= 1.5);
  const others = segments.filter((s) => s.speaker_id !== speakerId);
  const clean = mine.filter((m) => !others.some((o) => o.start_ts < m.end_ts && o.end_ts > m.start_ts));
  const pool = clean.length ? clean : mine.length ? mine : segments.filter((s) => s.speaker_id === speakerId);
  return [...pool]
    .sort((a, b) => b.end_ts - b.start_ts - (a.end_ts - a.start_ts))
    .slice(0, MAX_SAMPLE_CLIPS)
    .map((s) => [s.start_ts, Math.min(s.end_ts, s.start_ts + SAMPLE_CLIP_S)]);
}

function SpeakerMenu({
  recordingId,
  speakers,
  segments,
  tracks,
  onRename,
}: {
  recordingId: number;
  speakers: Speaker[];
  segments: Segment[];
  tracks: string[];
  onRename: (id: number, name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clipIdx = useRef<Record<number, number>>({});
  const [playing, setPlaying] = useState<{ id: number; loading: boolean } | null>(null);

  function stopSample() {
    const a = audioRef.current;
    audioRef.current = null;
    if (a) {
      a.pause();
      a.removeAttribute("src");
      a.load();
    }
    setPlaying(null);
  }

  // Close on outside click / Escape. On outside click, blur a focused rename field first
  // so its onBlur still commits the edit (an unmounted input wouldn't fire it).
  useEffect(() => {
    if (!open) return;
    const close = (cancelEdit: boolean) => {
      const el = document.activeElement;
      if (el instanceof HTMLElement && rootRef.current?.contains(el)) {
        // Escape abandons a half-typed rename: restore it so onBlur sees no change.
        if (cancelEdit && el instanceof HTMLInputElement) el.value = el.defaultValue;
        el.blur();
      }
      stopSample();
      setOpen(false);
    };
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) close(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(true);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Stop any sample when the page goes away (closing the menu stops it too).
  useEffect(() => () => audioRef.current?.pause(), []);

  if (speakers.length === 0) return null;

  // "You" is on the mic track, everyone else on the system track; a single-track
  // recording only has the mixed file.
  function trackFor(sp: Speaker): "mixed" | "mic" | "system" | null {
    const want = sp.is_self ? "mic" : "system";
    if (tracks.includes(want)) return want;
    return tracks.includes("mixed") ? "mixed" : null;
  }

  function toggleSample(sp: Speaker) {
    if (playing?.id === sp.id) {
      stopSample();
      return;
    }
    stopSample();
    const track = trackFor(sp);
    const clips = sampleClips(segments, sp.id);
    if (!track || clips.length === 0) return;
    const i = clipIdx.current[sp.id] ?? 0;
    clipIdx.current[sp.id] = (i + 1) % clips.length;
    const [start, end] = clips[i % clips.length];

    const a = new Audio(api.audioUrl(recordingId, track));
    a.preload = "auto";
    audioRef.current = a;
    setPlaying({ id: sp.id, loading: true });
    const done = () => {
      if (audioRef.current === a) stopSample();
    };
    a.addEventListener(
      "loadedmetadata",
      () => {
        a.currentTime = start;
        a.play()
          .then(() => audioRef.current === a && setPlaying({ id: sp.id, loading: false }))
          .catch(done);
      },
      { once: true }
    );
    a.addEventListener("timeupdate", () => {
      if (a.currentTime >= end) done();
    });
    a.addEventListener("ended", done);
    a.addEventListener("error", done);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => {
          if (open) stopSample();
          setOpen(!open);
        }}
        className="flex items-center gap-2 pr-1.5 pl-0.5 py-0.5 rounded-full hover:bg-surface-2"
      >
        <span className="flex">
          {speakers.slice(0, 4).map((s, i) => (
            <span key={s.id} style={{ marginLeft: i ? -8 : 0 }} className="ring-2 ring-paper rounded-full">
              <Avatar name={s.name} color={catColor(s.color)} size={25} />
            </span>
          ))}
        </span>
        <span className="text-[12.5px] text-ink-2">{speakers.length} speaker{speakers.length > 1 ? "s" : ""}</span>
        <Icon name="chevron-down" size={11} className="text-muted" />
      </button>
      {open && (
        <div className="absolute top-9 left-0 w-72 bg-surface border border-line rounded-card shadow-pop p-2 z-10">
          <div className="text-[10.5px] uppercase tracking-wide text-label px-2 py-1.5">Speakers · rename to link</div>
          {speakers.map((s) => {
            const canSample = trackFor(s) !== null && segments.some((x) => x.speaker_id === s.id);
            const isPlaying = playing?.id === s.id;
            return (
              <div key={s.id} className="flex items-center gap-2.5 p-1.5">
                <Avatar name={s.name} color={catColor(s.color)} size={28} />
                <input
                  defaultValue={s.name}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v && v !== s.name) onRename(s.id, v);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  className="flex-1 min-w-0 bg-paper border border-line rounded-field px-2 py-1 text-[13px]"
                />
                {canSample && (
                  <button
                    type="button"
                    onClick={() => toggleSample(s)}
                    title={isPlaying ? "Stop" : "Play a voice sample (press again for another)"}
                    aria-label={isPlaying ? `Stop ${s.name}'s voice sample` : `Play ${s.name}'s voice sample`}
                    className={`shrink-0 w-7 h-7 rounded-full border inline-flex items-center justify-center ${
                      isPlaying ? "bg-ink text-paper border-ink" : "border-line text-ink-2 hover:bg-surface-2"
                    }`}
                  >
                    <Icon
                      name={isPlaying ? (playing?.loading ? "loader" : "square") : "play"}
                      size={12}
                      className={playing?.loading && isPlaying ? "animate-spin" : undefined}
                    />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

type Tab = "summary" | "transcript" | "chat";

export default function RecordingDetail() {
  const { id } = useParams();
  const recordingId = Number(id);
  const nav = useNavigate();
  const [rec, setRec] = useState<TR | null>(null);
  const [qa, setQa] = useState<QAMessage[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [peopleNames, setPeopleNames] = useState<string[]>([]);
  const [diarOn, setDiarOn] = useState<boolean | null>(null);
  const [diarSupported, setDiarSupported] = useState<boolean>(true);
  const [diarReason, setDiarReason] = useState<string | null>(null);
  // Share the sidebar's tag list so a tag created here shows up there immediately.
  const { tags: allTags, reloadTags } = useShell();
  const [tab, setTab] = useState<Tab>("summary");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [copied, setCopied] = useState<"md" | "txt" | null>(null);
  const [tq, setTq] = useState("");
  const [pollNonce, setPollNonce] = useState(0);
  const [cancellingDiar, setCancellingDiar] = useState(false);
  const [stoppingProc, setStoppingProc] = useState(false);
  const [trimming, setTrimming] = useState<null | "trim" | "keep">(null);
  const [asking, setAsking] = useState(false);

  // Guards against a stale response landing after navigation: a slow fetch for
  // recording A must not overwrite the view once the route points at B.
  const currentIdRef = useRef(recordingId);
  useLayoutEffect(() => {
    currentIdRef.current = recordingId;
  }, [recordingId]);

  async function load() {
    const r = await api.getRecording(recordingId);
    if (recordingId !== currentIdRef.current) return r;
    setRec(r);
    setQa(r.qa);
    setSummary(r.summaries[0] ?? null);
    return r;
  }

  useEffect(() => {
    api.listPeople().then((p) => setPeopleNames(p.map((x) => x.name))).catch(() => {});
    api.status().then((s) => {
      setDiarOn(s.diarization);
      setDiarSupported(s.diarization_supported ?? true);
      setDiarReason(s.diarization_reason ?? null);
    }).catch(() => {});
  }, [recordingId]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await load();
        if (alive && r.status === "processing") timer = setTimeout(tick, 1500);
      } catch {
        if (alive) timer = setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingId, pollNonce]);

  async function addTag(tagId: number) {
    await api.addTagToRecording(recordingId, tagId);
    load();
  }
  async function removeTag(tagId: number) {
    await api.removeTagFromRecording(recordingId, tagId);
    load();
  }
  async function createAndAssign(name: string) {
    const t = await api.createTag(name);
    await api.addTagToRecording(recordingId, t.id);
    await reloadTags();
    load();
  }

  const speakerMap = useMemo(() => {
    const m: Record<number, Speaker> = {};
    for (const sp of rec?.speakers ?? []) m[sp.id] = sp;
    return m;
  }, [rec]);

  async function renameSpeaker(speakerId: number, name: string) {
    await api.renameSpeaker(recordingId, speakerId, name);
    await load();
    api.listPeople().then((p) => setPeopleNames(p.map((x) => x.name))).catch(() => {});
  }

  async function commitTitle() {
    setEditingTitle(false);
    const v = titleDraft.trim();
    if (rec && v !== (rec.title ?? "")) {
      await api.renameRecording(recordingId, v);
      await load();
    }
  }

  async function copyExport(format: "md" | "txt") {
    const text = await api.getExportText(recordingId, format);
    await copyToClipboard(text);
    setCopied(format);
    setTimeout(() => setCopied((c) => (c === format ? null : c)), 1500);
  }

  async function reprocess() {
    try {
      await api.reprocessRecording(recordingId);
    } catch {
      // Most likely already queued/processing (409) — the poll below shows the truth.
    }
    await load();
    setPollNonce((n) => n + 1);
  }
  async function del() {
    if (!(await confirmDialog("Delete this recording and all its data?"))) return;
    await api.deleteRecording(recordingId);
    nav("/");
  }
  async function delAudio() {
    const ok = await confirmDialog(
      "Delete the audio files for this recording? This frees disk space but is permanent — " +
        "playback and re-processing will no longer be possible. The transcript, summary and chat are kept."
    );
    if (!ok) return;
    await api.deleteRecordingAudio(recordingId);
    await load();
  }
  async function cancelDiarization() {
    setCancellingDiar(true);
    try {
      await api.cancelDiarization(recordingId);
    } finally {
      setTimeout(() => setCancellingDiar(false), 2000);
    }
  }
  async function stopProcessing() {
    setStoppingProc(true);
    try {
      await api.cancelProcessing(recordingId);
    } catch {
      setStoppingProc(false);
    }
  }
  async function decideTrim(trim: boolean) {
    setTrimming(trim ? "trim" : "keep");
    try {
      await api.trimDecision(recordingId, trim);
      await load();
      setPollNonce((n) => n + 1);
    } finally {
      setTrimming(null);
    }
  }

  const transcriptItems = useMemo(() => {
    if (!rec) return [];
    const q = tq.trim().toLowerCase();
    return rec.segments
      .filter((s) => !q || s.text.toLowerCase().includes(q))
      .map((s) => ({ kind: "segment" as const, segment: s }));
  }, [rec, tq]);

  const chatItems = useMemo(() => qa.map((m) => ({ kind: "qa" as const, message: m })), [qa]);

  async function ask(question: string) {
    // Show the question immediately; a loading bubble runs until the answer arrives.
    setQa((q) => [
      ...q,
      { id: Date.now(), recording_id: recordingId, role: "user", content: question, created_at: new Date().toISOString() },
    ]);
    setAsking(true);
    try {
      const { answer } = await api.ask(recordingId, question);
      setQa((q) => [
        ...q,
        { id: Date.now() + 1, recording_id: recordingId, role: "assistant", content: answer || "_(The AI returned an empty answer.)_", created_at: new Date().toISOString() },
      ]);
    } catch (e) {
      // Surface the failure in the chat instead of leaving a dangling question bubble.
      const detail = e instanceof Error ? e.message : String(e);
      setQa((q) => [
        ...q,
        { id: Date.now() + 1, recording_id: recordingId, role: "assistant", content: `⚠️ Couldn't get an answer: ${detail}`, created_at: new Date().toISOString() },
      ]);
    } finally {
      setAsking(false);
    }
  }
  async function summarize(templateId: number) {
    setSummary(await api.summarize(recordingId, templateId));
  }

  if (!rec) return <div className="p-7 text-sm text-muted">Loading…</div>;

  const awaitingTrim = rec.pending_trim != null;
  const isProcessing = rec.status === "processing" && !awaitingTrim;
  const hasTranscript = rec.segments.length > 0;
  const hasAudio = (rec.tracks ?? []).length > 0;
  const p = rec.progress;
  const pct = p?.fraction != null ? Math.round(p.fraction * 100) : null;

  const tabBtn = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      className={`h-[38px] px-4 text-[14.5px] border-b-2 -mb-px ${
        tab === t ? "border-signal text-ink font-bold" : "border-transparent text-muted hover:text-ink-2"
      }`}
    >
      {label}
    </button>
  );
  const toolBtn = "h-8 px-3 rounded-field border border-line text-[12.5px] text-ink-2 hover:bg-surface-2 inline-flex items-center gap-1.5";

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <div className="px-7 pt-5 shrink-0">
        <div className="flex items-center gap-2 text-[12.5px] text-muted mb-3">
          <Icon name="chevron-left" size={14} />
          <Link to="/" className="hover:text-ink-2">Recordings</Link>
          <span className="text-line-3">/</span>
          <span className="text-ink-2 truncate">{rec.title || `Recording #${rec.id}`}</span>
        </div>
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5">
              {editingTitle ? (
                <input
                  autoFocus
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onBlur={commitTitle}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitTitle();
                    if (e.key === "Escape") setEditingTitle(false);
                  }}
                  className="font-serif text-[27px] font-semibold bg-paper border border-line rounded px-2 w-full max-w-lg"
                />
              ) : (
                <>
                  <h1 className="font-serif text-[27px] font-semibold tracking-tight truncate">
                    {rec.title || `Recording #${rec.id}`}
                  </h1>
                  <button
                    onClick={() => {
                      setTitleDraft(rec.title ?? "");
                      setEditingTitle(true);
                    }}
                    className="text-muted hover:text-ink-2"
                    title="Rename"
                  >
                    <Icon name="pencil" size={15} />
                  </button>
                </>
              )}
            </div>
            <div className="flex items-center gap-3.5 mt-2.5 flex-wrap">
              <div className="flex items-center gap-2.5 text-[12.5px] text-muted font-mono">
                <span>{new Date(rec.started_at).toLocaleString()}</span>
                <span className="text-line-3">|</span>
                <span>{fmtDuration(rec.duration_s)}</span>
                {rec.language && (
                  <>
                    <span className="text-line-3">|</span>
                    <span className="uppercase">{rec.language}</span>
                  </>
                )}
              </div>
              <SpeakerMenu
                recordingId={rec.id}
                speakers={rec.speakers}
                segments={rec.segments}
                tracks={rec.tracks ?? []}
                onRename={renameSpeaker}
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              {rec.tags.map((t) => (
                <TagChip key={t.id} tag={t} onRemove={() => removeTag(t.id)} />
              ))}
              <AddTagButton allTags={allTags} currentIds={rec.tags.map((t) => t.id)} onAdd={addTag} onCreate={createAndAssign} />
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            {isProcessing ? (
              <Button onClick={stopProcessing} disabled={stoppingProc} title="Stop processing (keeps any transcript so far)">
                <Icon name="square" size={14} /> {stoppingProc ? "Stopping…" : "Stop"}
              </Button>
            ) : awaitingTrim || !hasAudio ? null : (
              <Button onClick={reprocess}>Re-process</Button>
            )}
            <Button
              onClick={del}
              disabled={isProcessing}
              title={isProcessing ? "Stop processing first, then delete" : "Delete recording"}
              className="!px-2.5 disabled:opacity-50"
            >
              <Icon name="trash-2" size={15} />
            </Button>
          </div>
        </div>
      </div>

      {/* audio player */}
      {hasAudio && (
        <div className="px-7 mt-4 shrink-0 flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <AudioPlayer recordingId={rec.id} tracks={rec.tracks ?? []} />
          </div>
          {(rec.status === "ready" || rec.status === "failed") && (
            <button
              onClick={delAudio}
              title="Delete audio files — frees disk space; transcript & summary are kept"
              className="h-9 px-2.5 rounded-field border border-line text-muted hover:text-signal hover:bg-surface-2 inline-flex items-center gap-1.5 text-[12px] shrink-0"
            >
              <Icon name="trash-2" size={13} /> Audio
            </button>
          )}
        </div>
      )}

      {/* trim-silence prompt (recording held before transcription) */}
      {awaitingTrim && rec.pending_trim && (
        <div className="px-7 mt-3 shrink-0">
          <div className="rounded-field bg-signal/[0.06] border border-signal/25 px-4 py-3">
            <div className="flex items-start gap-2.5">
              <Icon name="clock" size={16} className="text-signal shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="text-[13.5px] font-semibold text-ink">
                  Trim {fmtGap(rec.pending_trim.leading_s + rec.pending_trim.trailing_s)} of silence?
                </div>
                <div className="text-[12.5px] text-muted mt-0.5">
                  {[
                    rec.pending_trim.leading_s >= 1 && `${fmtGap(rec.pending_trim.leading_s)} at the start`,
                    rec.pending_trim.trailing_s >= 1 && `${fmtGap(rec.pending_trim.trailing_s)} at the end`,
                  ]
                    .filter(Boolean)
                    .join(" and ")}
                  {" "}was detected — likely dead air. Trimming skips transcribing it and shortens the recording.
                </div>
                <div className="flex flex-wrap gap-2 mt-2.5">
                  <Button onClick={() => decideTrim(true)} disabled={trimming != null}>
                    <Icon name="check" size={14} /> {trimming === "trim" ? "Trimming…" : "Trim & transcribe"}
                  </Button>
                  <button
                    onClick={() => decideTrim(false)}
                    disabled={trimming != null}
                    className="h-9 px-3.5 rounded-field border border-line text-[13px] text-ink-2 hover:bg-surface-2 disabled:opacity-50"
                  >
                    {trimming === "keep" ? "Keeping…" : "Keep full recording"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* processing / failed banners */}
      {isProcessing && (
        <div className="px-7 mt-3 shrink-0">
          <div className="rounded-field bg-warn/5 border border-warn/20 px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-warn-deep mb-1">
              <span className="w-2 h-2 rounded-full bg-warn animate-recpulse shrink-0" />
              <span>{STAGE_LABEL[p?.stage ?? "queued"] ?? "Processing…"}</span>
              <span className="ml-auto flex items-center gap-3 tabular-nums">
                {p?.stage === "diarizing" && (
                  <button onClick={cancelDiarization} disabled={cancellingDiar} className="px-1.5 py-0.5 rounded border border-warn/40 hover:bg-warn/15 disabled:opacity-50">
                    {cancellingDiar ? "Skipping…" : "Skip speakers"}
                  </button>
                )}
                {p?.elapsed_s != null && <span className="opacity-70">{fmtElapsed(p.elapsed_s)}</span>}
                {pct != null && <span>{p?.estimated ? "~" : ""}{pct}%</span>}
              </span>
            </div>
            <div className="relative h-1.5 rounded-full bg-warn/15 overflow-hidden">
              {pct != null ? (
                <div className="h-full bg-warn transition-all duration-500" style={{ width: `${pct}%` }} />
              ) : (
                <div className="progress-indeterminate bg-warn/70" />
              )}
            </div>
            {p?.power_note && <div className="mt-1.5 text-[11.5px] text-warn-deep/80">{p.power_note}</div>}
          </div>
        </div>
      )}
      {rec.status === "failed" && (
        <div className="px-7 mt-3 shrink-0">
          <div className="rounded-field bg-signal/5 border border-signal/20 px-3 py-2 text-xs text-signal flex items-center gap-3">
            <span>Transcription failed{rec.segments.length ? " (partial transcript shown)" : ""}{rec.error ? `: ${rec.error}` : "."}</span>
            <button onClick={reprocess} className="ml-auto shrink-0 px-2 py-0.5 rounded-field bg-warn/15 text-warn-deep hover:bg-warn/25">Retry</button>
          </div>
        </div>
      )}
      {rec.warning && (
        <div className="px-7 mt-3 shrink-0">
          <div className="rounded-field bg-warn/5 border border-warn/20 px-3 py-2 text-xs text-warn-deep flex items-center gap-2">
            <Icon name="triangle-alert" size={14} className="shrink-0" />
            <span>{rec.warning}</span>
          </div>
        </div>
      )}

      {/* tabs */}
      <div className="px-7 mt-4 flex items-center gap-1.5 border-b border-line-2 shrink-0">
        {tabBtn("summary", "Summary")}
        {tabBtn("transcript", "Transcript")}
        {tabBtn("chat", "Ask AI")}
      </div>

      {/* tab body */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "summary" && (
          <div className="h-full overflow-y-auto px-7 py-5">
            <div className="flex items-center gap-2.5 mb-5 flex-wrap">
              {hasTranscript && <SummaryControls onSummarize={summarize} />}
              <div className="flex-1" />
              <button onClick={() => copyExport("md")} disabled={!hasTranscript} className={toolBtn}>
                <Icon name="copy" size={12} /> {copied === "md" ? "Copied!" : "Copy"}
              </button>
              <a href={api.exportUrl(recordingId, "md")} className={toolBtn} download>
                <Icon name="download" size={12} /> Export
              </a>
            </div>
            {summary && summary.sections.length > 0 ? (
              <div className="max-w-[680px] space-y-6">
                {summary.sections.map((sec, i) => (
                  <div key={i}>
                    <div className="text-[11.5px] font-bold uppercase tracking-wide text-signal mb-2">{sec.title}</div>
                    <Markdown content={sec.content} className="font-serif text-[16px] leading-relaxed text-ink" />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">
                {hasTranscript ? "No summary yet — generate one above." : "No transcript to summarise yet."}
              </p>
            )}
          </div>
        )}

        {tab === "transcript" && (
          <div className="h-full flex flex-col">
            <div className="px-7 py-3 flex items-center gap-2.5 shrink-0">
              <div className="flex items-center gap-2 w-[250px] h-8 px-3 border border-line rounded-field bg-surface text-muted">
                <Icon name="search" size={13} />
                <input value={tq} onChange={(e) => setTq(e.target.value)} placeholder="Search transcript…" className="flex-1 min-w-0 bg-transparent text-[12.5px] text-ink focus:outline-none" />
              </div>
              <div className="flex-1" />
              <button onClick={() => copyExport("txt")} disabled={!hasTranscript} className={toolBtn}>
                <Icon name="copy" size={12} /> {copied === "txt" ? "Copied!" : "Copy"}
              </button>
              <a href={api.exportUrl(recordingId, "txt")} className={toolBtn} download>
                <Icon name="download" size={12} /> Export
              </a>
            </div>
            {diarOn === false && (rec.tracks ?? []).includes("system") && (
              <div className="px-7 pb-1 shrink-0">
                <div className="flex items-center gap-2 text-[12px] text-muted bg-surface-2 border border-line-2 rounded-field px-3 py-1.5">
                  <Icon name="users" size={13} className="shrink-0" />
                  {diarSupported ? (
                    <span>
                      Everyone but you is grouped as one speaker. Turn on{" "}
                      <Link to="/settings" className="text-ink-2 underline underline-offset-2 hover:text-ink">
                        Speaker diarization
                      </Link>{" "}
                      (Settings) to split them into Speaker 1, 2, 3… then Re-process.
                    </span>
                  ) : (
                    <span>
                      Everyone but you is grouped as one speaker.{" "}
                      {diarReason ?? "Speaker separation isn't available here."}
                    </span>
                  )}
                </div>
              </div>
            )}
            <div className="flex-1 min-h-0">
              <TranscriptChat items={transcriptItems} speakers={speakerMap} peopleNames={peopleNames} onRename={renameSpeaker} mode="transcript" />
            </div>
          </div>
        )}

        {tab === "chat" && (
          <div className="h-full flex flex-col">
            <TranscriptChat items={chatItems} pending={asking} />
            <PromptBar onAsk={ask} disabled={!hasTranscript} />
          </div>
        )}
      </div>
    </div>
  );
}
