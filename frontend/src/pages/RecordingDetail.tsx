import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type RecordingDetail as TR, type Segment, type Summary, type QAMessage } from "../lib/api";
import TranscriptChat from "../components/TranscriptChat";
import PromptBar from "../components/PromptBar";

const STATUS_LABEL: Record<string, string> = {
  recording: "Recording",
  processing: "Processing — transcription pending",
  ready: "Ready",
  failed: "Failed",
};

export default function RecordingDetail() {
  const { id } = useParams();
  const recordingId = Number(id);
  const nav = useNavigate();
  const [rec, setRec] = useState<TR | null>(null);
  const [qa, setQa] = useState<QAMessage[]>([]);
  const [fullSummary, setFullSummary] = useState<Summary | null>(null);

  async function load() {
    const r = await api.getRecording(recordingId);
    setRec(r);
    setQa(r.qa);
    setFullSummary(r.summaries.filter((s) => s.kind === "full").slice(-1)[0] ?? null);
  }

  useEffect(() => {
    load();
  }, [recordingId]);

  const items = useMemo(() => {
    if (!rec) return [];
    const merged: ({ kind: "segment"; segment: Segment } | { kind: "qa"; message: QAMessage })[] = [];
    for (const s of rec.segments) merged.push({ kind: "segment", segment: s });
    for (const m of qa) merged.push({ kind: "qa", message: m });
    return merged;
  }, [rec, qa]);

  async function ask(question: string, templateId?: number) {
    const { answer } = await api.ask(recordingId, question, templateId);
    setQa((q) => [
      ...q,
      { id: Date.now(), recording_id: recordingId, role: "user", content: question, created_at: new Date().toISOString() },
      { id: Date.now() + 1, recording_id: recordingId, role: "assistant", content: answer, created_at: new Date().toISOString() },
    ]);
  }

  async function summarize(templateId: number) {
    const { content } = await api.summarize(recordingId, templateId);
    setFullSummary({
      id: Date.now(),
      recording_id: recordingId,
      kind: "full",
      template_id: templateId,
      content,
      created_at: new Date().toISOString(),
    });
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
        <h1 className="text-sm font-medium truncate">
          {rec.title || `Recording #${rec.id}`}
        </h1>
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
        <div className="ml-auto flex gap-2 text-xs">
          <a href={api.exportUrl(rec.id, "md")} className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">
            Export .md
          </a>
          <a href={api.exportUrl(rec.id, "txt")} className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">
            Export .txt
          </a>
        </div>
      </div>

      {isProcessing && !hasTranscript && (
        <div className="px-6 py-2 text-xs text-amber-300 bg-amber-500/5 border-b border-amber-500/20">
          This recording is captured and awaiting transcription. The transcript and summary will appear once processing runs.
        </div>
      )}

      <div className="flex-1 grid grid-cols-[1fr_360px] min-h-0">
        <TranscriptChat items={items} />
        <div className="border-l border-neutral-800 overflow-y-auto p-4 bg-neutral-950/30">
          <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Summary</h3>
          {fullSummary ? (
            <pre className="text-sm whitespace-pre-wrap font-sans">{fullSummary.content}</pre>
          ) : (
            <p className="text-sm text-neutral-500">
              {hasTranscript ? "No summary yet. Generate one below." : "No transcript to summarise yet."}
            </p>
          )}
        </div>
      </div>
      <PromptBar onAsk={ask} onSummarize={summarize} disabled={!hasTranscript} />
    </div>
  );
}
