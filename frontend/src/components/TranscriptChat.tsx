import { useEffect, useRef, useState } from "react";
import type { Segment, QAMessage, Speaker } from "../lib/api";
import { catColor } from "./TagUI";

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
};

export default function TranscriptChat({ items, speakers = {}, peopleNames = [], onRename, pending = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [items, pending]);

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
    <div ref={ref} className="h-full overflow-y-auto px-7 py-5 space-y-4">
      {items.length === 0 && <p className="text-muted text-sm">No transcript yet.</p>}
      {items.map((it, i) => {
        if (it.kind === "segment") {
          const seg = it.segment;
          const sp = seg.speaker_id != null ? speakers[seg.speaker_id] : undefined;
          const c = catColor(sp?.color ?? null);
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
                    className="w-full text-xs px-2 py-0.5 rounded-field border border-line bg-paper"
                  />
                  {suggestions().length > 0 && (
                    <div className="absolute z-10 mt-1 w-44 max-h-44 overflow-y-auto bg-surface border border-line rounded-card shadow-pop p-1">
                      <p className="text-[10px] uppercase tracking-wide text-label px-2 py-0.5">
                        Existing people
                      </p>
                      {suggestions().map((n) => (
                        <button
                          key={n}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            commit(seg.speaker_id!, n);
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
                    if (onRename && seg.speaker_id != null) {
                      setEditing(seg.id);
                      setDraft(name);
                    }
                  }}
                  disabled={!onRename || seg.speaker_id == null}
                  title={onRename ? "Click to rename this speaker" : undefined}
                  className={`shrink-0 text-[12.5px] font-bold h-fit inline-flex items-center gap-1.5 ${onRename ? "cursor-pointer" : ""}`}
                  style={{ color: c }}
                >
                  <span className="w-2 h-2 rounded-full" style={{ background: c }} />
                  {name}
                </button>
              )}
              <div className="text-[14.5px] leading-relaxed text-ink">
                <span className="text-muted text-[11px] font-mono mr-2">{ts(seg.start_ts)}</span>
                {seg.text}
              </div>
            </div>
          );
        }
        const m = it.message;
        const isUser = m.role === "user";
        return (
          <div
            key={`q-${m.id}-${i}`}
            className={`flex ${isUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[74%] px-4 py-3 text-[13.5px] leading-relaxed whitespace-pre-wrap ${
                isUser
                  ? "bg-ink text-paper rounded-[16px_16px_5px_16px]"
                  : "bg-surface border border-line-2 text-ink rounded-[16px_16px_16px_5px] shadow-card"
              }`}
            >
              {m.content}
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
