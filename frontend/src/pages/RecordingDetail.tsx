import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api, type RecordingDetail as TR, type Speaker, type Summary, type QAMessage, type SummaryTemplate } from "../lib/api";
import TranscriptChat from "../components/TranscriptChat";
import PromptBar from "../components/PromptBar";
import { TagChip, AddTagButton, catColor } from "../components/TagUI";
import { Avatar, Button } from "../components/ui";
import { Icon } from "../components/Icon";
import { confirmDialog } from "../lib/confirm";
import { useShell } from "../components/Shell";

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
function fmtDuration(s: number | null) {
  if (s == null) return "—";
  const total = Math.floor(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const ss = (total % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${ss}` : `${m}:${ss}`;
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

function SpeakerMenu({ speakers, onRename }: { speakers: Speaker[]; onRename: (id: number, name: string) => void }) {
  const [open, setOpen] = useState(false);
  if (speakers.length === 0) return null;
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 pr-1.5 pl-0.5 py-0.5 rounded-full hover:bg-surface-2">
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
        <div className="absolute top-9 left-0 w-64 bg-surface border border-line rounded-card shadow-pop p-2 z-10">
          <div className="text-[10.5px] uppercase tracking-wide text-label px-2 py-1.5">Speakers · rename to link</div>
          {speakers.map((s) => (
            <div key={s.id} className="flex items-center gap-2.5 p-1.5">
              <Avatar name={s.name} color={catColor(s.color)} size={28} />
              <input
                defaultValue={s.name}
                onBlur={(e) => {
                  const v = e.target.value.trim();
                  if (v && v !== s.name) onRename(s.id, v);
                }}
                className="flex-1 min-w-0 bg-paper border border-line rounded-field px-2 py-1 text-[13px]"
              />
            </div>
          ))}
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
  // Share the sidebar's tag list so a tag created here shows up there immediately.
  const { tags: allTags, reloadTags } = useShell();
  const [tab, setTab] = useState<Tab>("summary");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [copied, setCopied] = useState<"md" | "txt" | null>(null);
  const [tq, setTq] = useState("");
  const [pollNonce, setPollNonce] = useState(0);
  const [cancellingDiar, setCancellingDiar] = useState(false);
  const [asking, setAsking] = useState(false);

  async function load() {
    const r = await api.getRecording(recordingId);
    setRec(r);
    setQa(r.qa);
    setSummary(r.summaries[0] ?? null);
    return r;
  }

  useEffect(() => {
    api.listPeople().then((p) => setPeopleNames(p.map((x) => x.name))).catch(() => {});
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
    await api.reprocessRecording(recordingId);
    await load();
    setPollNonce((n) => n + 1);
  }
  async function del() {
    if (!(await confirmDialog("Delete this recording and all its data?"))) return;
    await api.deleteRecording(recordingId);
    nav("/");
  }
  async function cancelDiarization() {
    setCancellingDiar(true);
    try {
      await api.cancelDiarization(recordingId);
    } finally {
      setTimeout(() => setCancellingDiar(false), 2000);
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
        { id: Date.now() + 1, recording_id: recordingId, role: "assistant", content: answer, created_at: new Date().toISOString() },
      ]);
    } finally {
      setAsking(false);
    }
  }
  async function summarize(templateId: number) {
    setSummary(await api.summarize(recordingId, templateId));
  }

  if (!rec) return <div className="p-7 text-sm text-muted">Loading…</div>;

  const isProcessing = rec.status === "processing";
  const hasTranscript = rec.segments.length > 0;
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
              <SpeakerMenu speakers={rec.speakers} onRename={renameSpeaker} />
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              {rec.tags.map((t) => (
                <TagChip key={t.id} tag={t} onRemove={() => removeTag(t.id)} />
              ))}
              <AddTagButton allTags={allTags} currentIds={rec.tags.map((t) => t.id)} onAdd={addTag} onCreate={createAndAssign} />
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={reprocess}>Re-process</Button>
            <Button onClick={del} title="Delete recording" className="!px-2.5">
              <Icon name="trash-2" size={15} />
            </Button>
          </div>
        </div>
      </div>

      {/* audio player */}
      <div className="px-7 mt-4 shrink-0">
        <AudioPlayer recordingId={rec.id} tracks={rec.tracks ?? []} />
      </div>

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
            <div className="h-1.5 rounded-full bg-warn/15 overflow-hidden">
              {pct != null ? (
                <div className="h-full bg-warn transition-all duration-500" style={{ width: `${pct}%` }} />
              ) : (
                <div className="h-full w-1/3 bg-warn/70 animate-pulse" />
              )}
            </div>
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
                    <div className="font-serif text-[16px] leading-relaxed text-ink whitespace-pre-wrap">{sec.content}</div>
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
            <div className="flex-1 min-h-0">
              <TranscriptChat items={transcriptItems} speakers={speakerMap} peopleNames={peopleNames} onRename={renameSpeaker} />
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
