import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type MeetingDetail as TM, type Segment, type Summary, type QAMessage } from "../lib/api";
import TranscriptChat from "../components/TranscriptChat";
import PromptBar from "../components/PromptBar";

export default function MeetingDetail() {
  const { id } = useParams();
  const meetingId = Number(id);
  const nav = useNavigate();
  const [meeting, setMeeting] = useState<TM | null>(null);
  const [qa, setQa] = useState<QAMessage[]>([]);
  const [fullSummary, setFullSummary] = useState<Summary | null>(null);

  async function load() {
    const m = await api.getMeeting(meetingId);
    setMeeting(m);
    setQa(m.qa);
    const full = m.summaries.filter((s) => s.kind === "full").slice(-1)[0] ?? null;
    setFullSummary(full);
  }

  useEffect(() => {
    load();
  }, [meetingId]);

  const items = useMemo(() => {
    if (!meeting) return [];
    const merged: ({ kind: "segment"; segment: Segment } | { kind: "qa"; message: QAMessage })[] = [];
    for (const s of meeting.segments) merged.push({ kind: "segment", segment: s });
    for (const m of qa) merged.push({ kind: "qa", message: m });
    return merged;
  }, [meeting, qa]);

  async function ask(question: string, templateId?: number) {
    const { answer } = await api.ask(meetingId, question, templateId);
    setQa((q) => [
      ...q,
      { id: Date.now(), meeting_id: meetingId, role: "user", content: question, created_at: new Date().toISOString() },
      { id: Date.now() + 1, meeting_id: meetingId, role: "assistant", content: answer, created_at: new Date().toISOString() },
    ]);
  }

  async function summarize(templateId: number) {
    const { content } = await api.summarize(meetingId, templateId);
    setFullSummary({
      id: Date.now(),
      meeting_id: meetingId,
      kind: "full",
      template_id: templateId,
      content,
      created_at: new Date().toISOString(),
    });
  }

  if (!meeting) {
    return <div className="p-6 text-sm text-neutral-500">Loading…</div>;
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-neutral-800 px-6 py-3 flex items-center gap-4">
        <button onClick={() => nav("/")} className="text-xs text-neutral-400 hover:text-neutral-100">
          ← Back
        </button>
        <h1 className="text-sm font-medium truncate">
          {meeting.title || `Meeting #${meeting.id}`}
        </h1>
        <span className="text-xs text-neutral-500">
          {new Date(meeting.started_at).toLocaleString()}
        </span>
        <div className="ml-auto flex gap-2 text-xs">
          <a
            href={api.exportUrl(meeting.id, "md")}
            className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
          >
            Export .md
          </a>
          <a
            href={api.exportUrl(meeting.id, "txt")}
            className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
          >
            Export .txt
          </a>
        </div>
      </div>
      <div className="flex-1 grid grid-cols-[1fr_360px] min-h-0">
        <TranscriptChat items={items} />
        <div className="border-l border-neutral-800 overflow-y-auto p-4 bg-neutral-950/30">
          <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Summary</h3>
          {fullSummary ? (
            <pre className="text-sm whitespace-pre-wrap font-sans">{fullSummary.content}</pre>
          ) : (
            <p className="text-sm text-neutral-500">No full summary yet. Generate one below.</p>
          )}
        </div>
      </div>
      <PromptBar onAsk={ask} onSummarize={summarize} />
    </div>
  );
}
