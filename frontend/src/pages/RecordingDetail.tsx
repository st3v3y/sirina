import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type RecordingDetail as TR, type Speaker, type Summary, type QAMessage, type Tag, type SummaryTemplate } from "../lib/api";
import TranscriptChat from "../components/TranscriptChat";
import PromptBar from "../components/PromptBar";
import { TagChip, AddTagButton, TAG_COLORS } from "../components/TagUI";

const STATUS_LABEL: Record<string, string> = {
  recording: "Recording",
  processing: "Processing — transcription pending",
  ready: "Ready",
  failed: "Failed",
};

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued…",
  transcribing: "Transcribing…",
  diarizing: "Identifying speakers…",
  summarizing: "Generating summary…",
  done: "Finishing up…",
};

function fmtElapsed(s: number) {
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
}

async function copyToClipboard(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    /* fall through to legacy path */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus();
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
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs uppercase tracking-wide text-neutral-500">Audio</h3>
        {ordered.length > 1 && (
          <div className="flex gap-1">
            {ordered.map((t) => (
              <button
                key={t}
                onClick={() => setTrack(t)}
                className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  track === t
                    ? "bg-neutral-700 text-neutral-100 border-neutral-600"
                    : "border-neutral-800 text-neutral-400 hover:text-neutral-200"
                }`}
              >
                {TRACK_LABEL[t] ?? t}
              </button>
            ))}
          </div>
        )}
      </div>
      <audio key={track} controls className="w-full h-9" src={api.audioUrl(recordingId, track as "mixed" | "mic" | "system")} />
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
    <div className="flex items-center gap-2 mb-3">
      <select
        value={templateId ?? ""}
        onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : null)}
        className="bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-xs flex-1 min-w-0"
      >
        {templates.map((t) => (
          <option key={t.id} value={t.id}>{t.name}</option>
        ))}
      </select>
      <button
        onClick={run}
        disabled={busy || !templateId}
        className="bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 px-2 py-1 rounded text-xs"
      >
        {busy ? "…" : "Generate"}
      </button>
    </div>
  );
}

export default function RecordingDetail() {
  const { id } = useParams();
  const recordingId = Number(id);
  const nav = useNavigate();
  const [rec, setRec] = useState<TR | null>(null);
  const [qa, setQa] = useState<QAMessage[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [peopleNames, setPeopleNames] = useState<string[]>([]);
  const [tab, setTab] = useState<"transcript" | "chat">("transcript");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [copied, setCopied] = useState<"md" | "txt" | null>(null);
  const [pollNonce, setPollNonce] = useState(0);

  async function load() {
    const r = await api.getRecording(recordingId);
    setRec(r);
    setQa(r.qa);
    setSummary(r.summaries[0] ?? null); // API returns summaries newest-first
    return r;
  }

  const [allTags, setAllTags] = useState<Tag[]>([]);

  useEffect(() => {
    api.listPeople().then((p) => setPeopleNames(p.map((x) => x.name))).catch(() => {});
    api.listTags().then(setAllTags).catch(() => {});
  }, [recordingId]);

  async function addTag(tagId: number) {
    await api.addTagToRecording(recordingId, tagId);
    load();
  }
  async function removeTag(tagId: number) {
    await api.removeTagFromRecording(recordingId, tagId);
    load();
  }
  async function createAndAssign(name: string) {
    const t = await api.createTag(name, TAG_COLORS[allTags.length % TAG_COLORS.length]);
    await api.addTagToRecording(recordingId, t.id);
    setAllTags(await api.listTags());
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

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await load();
        if (alive && r.status === "processing") {
          timer = setTimeout(tick, 1500); // poll until transcription finishes
        }
      } catch {
        if (alive) timer = setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [recordingId, pollNonce]);

  async function retry() {
    await api.reprocessRecording(recordingId);
    await load();
    setPollNonce((n) => n + 1); // re-arm the processing poll
  }

  const [cancellingDiar, setCancellingDiar] = useState(false);
  async function cancelDiarization() {
    setCancellingDiar(true);
    try {
      await api.cancelDiarization(recordingId);
    } finally {
      // backend keeps the baseline split and moves on; the poll reflects it
      setTimeout(() => setCancellingDiar(false), 2000);
    }
  }

  const transcriptItems = useMemo(() => {
    if (!rec) return [];
    return rec.segments.map((s) => ({ kind: "segment" as const, segment: s }));
  }, [rec]);

  const chatItems = useMemo(
    () => qa.map((m) => ({ kind: "qa" as const, message: m })),
    [qa]
  );

  async function ask(question: string) {
    const { answer } = await api.ask(recordingId, question);
    setQa((q) => [
      ...q,
      { id: Date.now(), recording_id: recordingId, role: "user", content: question, created_at: new Date().toISOString() },
      { id: Date.now() + 1, recording_id: recordingId, role: "assistant", content: answer, created_at: new Date().toISOString() },
    ]);
  }

  async function summarize(templateId: number) {
    const s = await api.summarize(recordingId, templateId);
    setSummary(s);
  }

  if (!rec) {
    return <div className="p-6 text-sm text-neutral-500">Loading…</div>;
  }

  const isProcessing = rec.status === "processing";
  const hasTranscript = rec.segments.length > 0;

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-neutral-800 px-6 py-3 flex items-center gap-4">
        <button onClick={() => nav("/")} className="text-xs text-neutral-400 hover:text-neutral-100">
          ← Back
        </button>
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
            placeholder={`Recording #${rec.id}`}
            className="text-sm bg-neutral-950 border border-neutral-700 rounded px-2 py-0.5 w-64"
          />
        ) : (
          <button
            onClick={() => {
              setTitleDraft(rec.title ?? "");
              setEditingTitle(true);
            }}
            title="Click to rename"
            className="text-sm font-medium truncate hover:text-neutral-100"
          >
            {rec.title || `Recording #${rec.id}`}
          </button>
        )}
        <span className="text-xs text-neutral-500">
          {new Date(rec.started_at).toLocaleString()}
        </span>
        <span
          className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${
            rec.status === "ready"
              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
              : rec.status === "processing"
              ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
              : rec.status === "failed"
              ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
              : "bg-neutral-700/40 text-neutral-300 border-neutral-600"
          }`}
        >
          {STATUS_LABEL[rec.status] ?? rec.status}
        </span>
        <div className="flex flex-wrap items-center gap-1">
          {rec.tags.map((t) => (
            <TagChip key={t.id} tag={t} onRemove={() => removeTag(t.id)} />
          ))}
          <AddTagButton
            allTags={allTags}
            currentIds={rec.tags.map((t) => t.id)}
            onAdd={addTag}
            onCreate={createAndAssign}
          />
        </div>
        <div className="ml-auto flex gap-2 text-xs">
          <button
            onClick={() => copyExport("md")}
            disabled={!hasTranscript}
            className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 disabled:opacity-40"
          >
            {copied === "md" ? "Copied!" : "Copy .md"}
          </button>
          <button
            onClick={() => copyExport("txt")}
            disabled={!hasTranscript}
            className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 disabled:opacity-40"
          >
            {copied === "txt" ? "Copied!" : "Copy .txt"}
          </button>
        </div>
      </div>

      <div className="border-b border-neutral-800 px-6 flex gap-4 text-sm">
        {(["transcript", "chat"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`py-2 -mb-px border-b-2 ${
              tab === t
                ? "border-fuchsia-500 text-neutral-100"
                : "border-transparent text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {t === "transcript" ? "Transcript" : "Chat"}
          </button>
        ))}
      </div>

      {isProcessing && (() => {
        const p = rec.progress;
        const stage = p?.stage ?? "queued";
        const pct = p?.fraction != null ? Math.round(p.fraction * 100) : null;
        const elapsed = p?.elapsed_s != null ? fmtElapsed(p.elapsed_s) : null;
        return (
          <div className="px-6 py-2 bg-amber-500/5 border-b border-amber-500/20">
            <div className="flex items-center gap-2 text-xs text-amber-300 mb-1">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
              <span>{STAGE_LABEL[stage] ?? "Processing…"}</span>
              <span className="ml-auto flex items-center gap-3 tabular-nums">
                {stage === "diarizing" && (
                  <button
                    onClick={cancelDiarization}
                    disabled={cancellingDiar}
                    className="not-tabular-nums px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-200 hover:bg-amber-500/15 disabled:opacity-50"
                    title="Skip speaker identification and go straight to the summary"
                  >
                    {cancellingDiar ? "Skipping…" : "Skip speakers"}
                  </button>
                )}
                {elapsed != null && <span className="text-amber-300/70">{elapsed}</span>}
                {pct != null && <span>{p?.estimated ? "~" : ""}{pct}%</span>}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-amber-500/15 overflow-hidden">
              {pct != null ? (
                <div
                  className="h-full bg-amber-400 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              ) : (
                <div className="h-full w-1/3 bg-amber-400/70 animate-pulse" />
              )}
            </div>
          </div>
        );
      })()}
      {rec.status === "failed" && (
        <div className="px-6 py-2 text-xs text-rose-300 bg-rose-500/5 border-b border-rose-500/20 flex items-center gap-3">
          <span>
            Transcription failed{rec.segments.length === 0 ? "" : " (partial transcript shown)"}
            {rec.error ? `: ${rec.error}` : "."}
          </span>
          <button
            onClick={retry}
            className="ml-auto shrink-0 px-2 py-0.5 rounded bg-amber-600/80 hover:bg-amber-500 text-amber-50"
          >
            Retry
          </button>
        </div>
      )}

      <div className="flex-1 grid grid-cols-[1fr_360px] min-h-0">
        {tab === "transcript" ? (
          <TranscriptChat
            items={transcriptItems}
            speakers={speakerMap}
            peopleNames={peopleNames}
            onRename={renameSpeaker}
          />
        ) : (
          <div className="flex flex-col min-h-0">
            <TranscriptChat items={chatItems} />
            <PromptBar onAsk={ask} disabled={!hasTranscript} />
          </div>
        )}
        <div className="border-l border-neutral-800 overflow-y-auto p-4 bg-neutral-950/30">
          <AudioPlayer recordingId={rec.id} tracks={rec.tracks ?? []} />
          <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Summary</h3>
          {hasTranscript && <SummaryControls onSummarize={summarize} />}
          {summary && summary.sections.length > 0 ? (
            <div className="space-y-3">
              {summary.sections.map((sec, i) => (
                <div key={i} className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
                  <h4 className="text-xs font-semibold text-neutral-300 mb-1">{sec.title}</h4>
                  <p className="text-sm whitespace-pre-wrap text-neutral-200">{sec.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-neutral-500">
              {hasTranscript ? "No summary yet. Generate one above." : "No transcript to summarise yet."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
