import { useEffect, useRef } from "react";
import type { Segment, QAMessage } from "../lib/api";

type ChatItem =
  | { kind: "segment"; segment: Segment }
  | { kind: "qa"; message: QAMessage };

const palette = [
  "bg-sky-500/15 text-sky-200 border-sky-500/30",
  "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  "bg-violet-500/15 text-violet-200 border-violet-500/30",
  "bg-amber-500/15 text-amber-200 border-amber-500/30",
  "bg-rose-500/15 text-rose-200 border-rose-500/30",
  "bg-teal-500/15 text-teal-200 border-teal-500/30",
];

function colorFor(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

function ts(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function TranscriptChat({ items }: { items: ChatItem[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [items]);

  return (
    <div ref={ref} className="h-full overflow-y-auto p-4 space-y-3">
      {items.length === 0 && (
        <p className="text-neutral-500 text-sm">No transcript yet.</p>
      )}
      {items.map((it, i) => {
        if (it.kind === "segment") {
          const s = it.segment;
          const color = colorFor(s.speaker_label);
          return (
            <div key={`s-${s.id}-${i}`} className="flex gap-3">
              <span className={`shrink-0 text-xs px-2 py-0.5 h-fit rounded border ${color}`}>
                {s.speaker_label}
              </span>
              <div className="text-sm leading-snug">
                <span className="text-neutral-500 text-xs mr-2">{ts(s.start_ts)}</span>
                {s.text}
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
                isUser
                  ? "bg-neutral-800 border-neutral-700 text-neutral-300"
                  : "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/30"
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
