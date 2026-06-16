import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type MeetingDetail, type Segment, type Summary, type QAMessage } from "../lib/api";
import { useMeetingSocket } from "../lib/useMeetingSocket";
import TranscriptChat from "../components/TranscriptChat";
import AspectsPanel from "../components/AspectsPanel";
import PromptBar from "../components/PromptBar";

export default function LiveMeeting() {
  const { id } = useParams();
  const meetingId = Number(id);
  const nav = useNavigate();
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [aspect, setAspect] = useState<Summary | null>(null);
  const [qa, setQa] = useState<QAMessage[]>([]);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    api.getMeeting(meetingId).then((m) => {
      setMeeting(m);
      setSegments(m.segments);
      const lastAspect = m.summaries.filter((s) => s.kind === "live_aspect").slice(-1)[0] ?? null;
      setAspect(lastAspect);
      setQa(m.qa);
    });
  }, [meetingId]);

  useMeetingSocket(meetingId, (e) => {
    if (e.type === "segment") setSegments((s) => [...s, e.segment]);
    else if (e.type === "aspect") setAspect(e.summary);
    else if (e.type === "qa") setQa((q) => [...q, e.message]);
    else if (e.type === "status" && e.status === "ended") {
      api.getMeeting(meetingId).then(setMeeting);
    }
  });

  const items = useMemo(() => {
    const merged: ({ kind: "segment"; segment: Segment; ts: string } | { kind: "qa"; message: QAMessage; ts: string })[] = [];
    for (const s of segments) merged.push({ kind: "segment", segment: s, ts: `${s.start_ts}` });
    for (const m of qa) merged.push({ kind: "qa", message: m, ts: m.created_at });
    return merged;
  }, [segments, qa]);

  async function stop() {
    setStopping(true);
    try {
      await api.stopMeeting(meetingId);
      nav(`/meetings/${meetingId}`);
    } finally {
      setStopping(false);
    }
  }

  async function ask(question: string, templateId?: number) {
    await api.ask(meetingId, question, templateId);
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-neutral-800 px-6 py-3 flex items-center gap-4">
        <button
          onClick={() => nav("/")}
          className="text-xs text-neutral-400 hover:text-neutral-100"
        >
          ← Back
        </button>
        <h1 className="text-sm font-medium truncate">
          {meeting?.title || `Meeting #${meetingId}`}
        </h1>
        <span className="text-xs text-rose-400 flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" /> Recording
        </span>
        <div className="ml-auto">
          <button
            onClick={stop}
            disabled={stopping}
            className="bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 px-3 py-1.5 rounded text-sm"
          >
            {stopping ? "Stopping…" : "■ Stop"}
          </button>
        </div>
      </div>
      <div className="flex-1 grid grid-cols-[1fr_320px] min-h-0">
        <TranscriptChat items={items} />
        <AspectsPanel latest={aspect} />
      </div>
      <PromptBar onAsk={ask} />
    </div>
  );
}
