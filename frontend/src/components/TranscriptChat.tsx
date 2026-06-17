import { useEffect, useRef, useState } from "react";
import type { Segment, QAMessage, Speaker } from "../lib/api";

type ChatItem =
  | { kind: "segment"; segment: Segment }
  | { kind: "qa"; message: QAMessage };

const COLORS: Record<string, string> = {
  sky: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  emerald: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  violet: "bg-violet-500/15 text-violet-200 border-violet-500/30",
  amber: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  rose: "bg-rose-500/15 text-rose-200 border-rose-500/30",
  teal: "bg-teal-500/15 text-teal-200 border-teal-500/30",
};
const DEFAULT_COLOR = "bg-neutral-800 text-neutral-300 border-neutral-700";

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
};

export default function TranscriptChat({ items, speakers = {}, peopleNames = [], onRename }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [items]);

  function currentName(speakerId: number): string {
    const sp = speakers[speakerId];
    return sp?.name ?? sp?.label ?? "Speaker";
  }

  async function commit(speakerId: number, value?: string) {
    const name = (value ?? draft).trim();
    setEditing(null);
    if (!onRename) return;
    const cur = currentName(speakerId);
    // No-op when nothing changed (prevents committing the pre-filled default
    // label, which used to create junk "Speaker 1"/"You" People).
    if (name === cur) return;
    // Empty only acts as a clear when the speaker is actually linked to a Person.
    if (!name && speakers[speakerId]?.person_id == null) return;
    await onRename(speakerId, name);
  }

  // People not already equal to the current draft, filtered by what's typed.
  function suggestions(): string[] {
    const q = draft.trim().toLowerCase();
    const seen = new Set<string>();
    return peopleNames.filter((n) => {
      const key = n.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return !q || key.includes(q);
    });
  }

  return (
    <div ref={ref} className="h-full overflow-y-auto p-4 space-y-3">
      {items.length === 0 && <p className="text-neutral-500 text-sm">No transcript yet.</p>}
      {items.map((it, i) => {
        if (it.kind === "segment") {
          const seg = it.segment;
          const sp = seg.speaker_id != null ? speakers[seg.speaker_id] : undefined;
          const color = (sp?.color && COLORS[sp.color]) || DEFAULT_COLOR;
          const name = sp?.name ?? "Speaker";
          return (
            <div key={`s-${seg.id}-${i}`} className="flex gap-3">
              {editing === seg.id && seg.speaker_id != null ? (
                <div className="relative shrink-0 w-40">
                  <input
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commit(seg.speaker_id!);
                      if (e.key === "Escape") setEditing(null);
                    }}
                    onBlur={() => commit(seg.speaker_id!)}
                    placeholder="Name or pick…"
                    className="w-full text-xs px-2 py-0.5 rounded border border-neutral-600 bg-neutral-950"
                  />
                  {suggestions().length > 0 && (
                    <div className="absolute z-10 mt-1 w-44 max-h-44 overflow-y-auto bg-neutral-900 border border-neutral-800 rounded shadow-lg p-1">
                      <p className="text-[10px] uppercase tracking-wide text-neutral-500 px-2 py-0.5">
                        Existing people
                      </p>
                      {suggestions().map((n) => (
                        <button
                          key={n}
                          // onMouseDown fires before the input's onBlur, so the pick wins.
                          onMouseDown={(e) => {
                            e.preventDefault();
                            commit(seg.speaker_id!, n);
                          }}
                          className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-neutral-800"
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
                    if (onRename && seg.speaker_id != null) {
                      setEditing(seg.id);
                      setDraft(name);
                    }
                  }}
                  disabled={!onRename || seg.speaker_id == null}
                  title={onRename ? "Click to rename this speaker" : undefined}
                  className={`shrink-0 text-xs px-2 py-0.5 h-fit rounded border ${color} ${onRename ? "hover:brightness-125 cursor-pointer" : ""}`}
                >
                  {name}
                </button>
              )}
              <div className="text-sm leading-snug">
                <span className="text-neutral-500 text-xs mr-2">{ts(seg.start_ts)}</span>
                {seg.text}
              </div>
            </div>
          );
        }
        const m = it.message;
        const isUser = m.role === "user";
        return (
          <div key={`q-${m.id}-${i}`} className="flex gap-3">
            <span
              className={`shrink-0 text-xs px-2 py-0.5 h-fit rounded border ${
                isUser ? DEFAULT_COLOR : "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/30"
              }`}
            >
              {isUser ? "You" : "AI"}
            </span>
            <div className="text-sm leading-snug whitespace-pre-wrap">{m.content}</div>
          </div>
        );
      })}
    </div>
  );
}
