import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Segment, QAMessage, Speaker } from "../lib/api";
import { catColor } from "../lib/tagColors";
import Markdown from "./Markdown";

type ChatItem =
  | { kind: "segment"; segment: Segment }
  | { kind: "qa"; message: QAMessage };

function ts(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type Props = {
  items: ChatItem[];
  speakers?: Record<number, Speaker>;
  peopleNames?: string[];
  onRename?: (speakerId: number, name: string) => Promise<void>;
  pending?: boolean; // show a loading bubble while an answer is in flight
  // "chat" starts pinned to the newest message; "transcript" starts at the top and is
  // never force-scrolled (so reading isn't interrupted while processing streams in more
  // segments). Either way, auto-scroll only resumes once the user returns to the bottom.
  mode?: "chat" | "transcript";
};

type SegmentRowProps = {
  seg: Segment;
  name: string;
  color: string;
  canRename: boolean;
  isEditing: boolean;
  peopleNames: string[];
  onStartEdit: (segId: number) => void;
  onCommit: (speakerId: number, name: string) => void;
  onCancel: () => void;
};

// Memoized row: during processing the whole list is re-fetched every 1.5s, and
// re-rendering 1000+ rows each poll made long transcripts crawl. The comparator
// checks the data that actually renders; handler identity is deliberately ignored
// (handlers read live state via refs in the parent).
const SegmentRow = memo(
  function SegmentRow({
    seg, name, color, canRename, isEditing, peopleNames, onStartEdit, onCommit, onCancel,
  }: SegmentRowProps) {
    const [draft, setDraft] = useState(name);
    // Reset the draft to the current name whenever editing starts (adjusting state
    // during render, rather than in an effect).
    const [wasEditing, setWasEditing] = useState(isEditing);
    if (isEditing !== wasEditing) {
      setWasEditing(isEditing);
      if (isEditing) setDraft(name);
    }

    const suggestions = (() => {
      if (!isEditing) return [];
      const q = draft.trim().toLowerCase();
      const seen = new Set<string>();
      return peopleNames.filter((n) => {
        const key = n.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return !q || key.includes(q);
      });
    })();

    return (
      <div className="flex gap-3">
        {isEditing && seg.speaker_id != null ? (
          <div className="relative shrink-0 w-40">
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onCommit(seg.speaker_id!, draft);
                if (e.key === "Escape") onCancel();
              }}
              onBlur={() => onCommit(seg.speaker_id!, draft)}
              placeholder="Name or pick…"
              className="w-full text-xs px-2 py-0.5 rounded-field border border-line bg-paper"
            />
            {suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-44 max-h-44 overflow-y-auto bg-surface border border-line rounded-card shadow-pop p-1">
                <p className="text-[10px] uppercase tracking-wide text-label px-2 py-0.5">
                  Existing people
                </p>
                {suggestions.map((n) => (
                  <button
                    key={n}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      onCommit(seg.speaker_id!, n);
                    }}
                    className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-surface-2"
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              if (canRename && seg.speaker_id != null) onStartEdit(seg.id);
            }}
            disabled={!canRename || seg.speaker_id == null}
            title={canRename ? "Click to rename this speaker" : undefined}
            className={`shrink-0 text-[12.5px] font-bold h-fit inline-flex items-center gap-1.5 ${canRename ? "cursor-pointer" : ""}`}
            style={{ color }}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            {name}
          </button>
        )}
        <div
          className={`text-[14.5px] leading-relaxed ${seg.is_draft ? "text-muted" : "text-ink"}`}
          title={seg.is_draft ? "Draft — being replaced by the final transcript" : undefined}
        >
          <span className="text-muted text-[11px] font-mono mr-2">{ts(seg.start_ts)}</span>
          {seg.text}
          {seg.is_draft && (
            <span className="ml-2 align-middle text-[10px] uppercase tracking-wide text-label border border-line-2 rounded px-1 py-px">
              draft
            </span>
          )}
        </div>
      </div>
    );
  },
  (prev, next) =>
    prev.seg.id === next.seg.id &&
    prev.seg.text === next.seg.text &&
    prev.seg.start_ts === next.seg.start_ts &&
    prev.seg.speaker_id === next.seg.speaker_id &&
    prev.seg.is_draft === next.seg.is_draft &&
    prev.name === next.name &&
    prev.color === next.color &&
    prev.canRename === next.canRename &&
    prev.isEditing === next.isEditing &&
    (!next.isEditing || prev.peopleNames === next.peopleNames)
);

export default function TranscriptChat({ items, speakers = {}, peopleNames = [], onRename, pending = false, mode = "chat" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(mode === "chat");
  const [editing, setEditing] = useState<number | null>(null);
  // Handlers passed to memoized rows read live props via refs (rows skip re-renders,
  // so a captured closure could otherwise act on stale speakers/onRename).
  const speakersRef = useRef(speakers);
  const onRenameRef = useRef(onRename);
  useLayoutEffect(() => {
    speakersRef.current = speakers;
    onRenameRef.current = onRename;
  });

  function onScroll() {
    const el = ref.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  useEffect(() => {
    if (!ref.current || !stick.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [items, pending]);

  async function commit(speakerId: number, value: string) {
    const name = value.trim();
    setEditing(null);
    const rename = onRenameRef.current;
    if (!rename) return;
    const sp = speakersRef.current[speakerId];
    const cur = sp?.name ?? sp?.label ?? "Speaker";
    // No-op when nothing changed (prevents committing the pre-filled default
    // label, which used to create junk "Speaker 1"/"You" People).
    if (name === cur) return;
    // Empty only acts as a clear when the speaker is actually linked to a Person.
    if (!name && sp?.person_id == null) return;
    await rename(speakerId, name);
  }

  return (
    <div ref={ref} onScroll={onScroll} className="h-full overflow-y-auto px-7 py-5 space-y-4">
      {items.length === 0 && <p className="text-muted text-sm">No transcript yet.</p>}
      {items.map((it, i) => {
        if (it.kind === "segment") {
          const seg = it.segment;
          const sp = seg.speaker_id != null ? speakers[seg.speaker_id] : undefined;
          const prev = i > 0 ? items[i - 1] : undefined;
          // One divider where the final transcript ends and the draft begins; it moves
          // down as each window turns final.
          const boundary =
            seg.is_draft && !(prev?.kind === "segment" && prev.segment.is_draft) ? (
              <div key={`b-${seg.id}`} className="flex items-center gap-2 text-[11px] text-label pt-1">
                <span className="h-px flex-1 bg-line-2" />
                Draft below — the final transcript replaces it as processing continues
                <span className="h-px flex-1 bg-line-2" />
              </div>
            ) : null;
          return [boundary,
            <SegmentRow
              key={`s-${seg.id}`}
              seg={seg}
              name={sp?.name ?? "Speaker"}
              color={catColor(sp?.color ?? null)}
              canRename={!!onRename}
              isEditing={editing === seg.id}
              peopleNames={peopleNames}
              onStartEdit={setEditing}
              onCommit={commit}
              onCancel={() => setEditing(null)}
            />,
          ];
        }
        const m = it.message;
        const isUser = m.role === "user";
        return (
          <div
            key={`q-${m.id}`}
            className={`flex ${isUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[74%] px-4 py-3 text-[13.5px] leading-relaxed ${
                isUser
                  ? "bg-ink text-paper rounded-[16px_16px_5px_16px] whitespace-pre-wrap"
                  : "bg-surface border border-line-2 text-ink rounded-[16px_16px_16px_5px] shadow-card"
              }`}
            >
              {isUser ? m.content : <Markdown content={m.content} />}
            </div>
          </div>
        );
      })}
      {pending && (
        <div className="flex justify-start">
          <div className="bg-surface border border-line-2 rounded-[16px_16px_16px_5px] shadow-card px-4 py-3">
            <span className="inline-block w-4 h-4 rounded-full border-2 border-line-3 border-t-signal animate-spin" />
          </div>
        </div>
      )}
    </div>
  );
}
