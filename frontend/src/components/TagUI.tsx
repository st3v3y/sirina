import { useState } from "react";
import type { Tag } from "../lib/api";

export const TAG_COLORS = ["sky", "emerald", "violet", "amber", "rose", "teal", "neutral"] as const;

const CHIP: Record<string, string> = {
  sky: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  emerald: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  violet: "bg-violet-500/15 text-violet-200 border-violet-500/30",
  amber: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  rose: "bg-rose-500/15 text-rose-200 border-rose-500/30",
  teal: "bg-teal-500/15 text-teal-200 border-teal-500/30",
  neutral: "bg-neutral-700/40 text-neutral-300 border-neutral-600",
};

export function tagChipClass(color: string | null): string {
  return (color && CHIP[color]) || CHIP.neutral;
}

export function TagChip({ tag, onRemove }: { tag: Tag; onRemove?: () => void }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border ${tagChipClass(tag.color)}`}>
      {tag.name}
      {onRemove && (
        <button onClick={onRemove} className="hover:text-rose-300 leading-none" title="Remove tag">
          ×
        </button>
      )}
    </span>
  );
}

type AddTagProps = {
  allTags: Tag[];
  currentIds: number[];
  onAdd: (tagId: number) => void;
  onCreate: (name: string) => void;
};

export function AddTagButton({ allTags, currentIds, onAdd, onCreate }: AddTagProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const available = allTags.filter((t) => !currentIds.includes(t.id));

  return (
    <span className="relative inline-block">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-[11px] px-1.5 py-0.5 rounded border border-dashed border-neutral-700 text-neutral-400 hover:text-neutral-200"
      >
        + Tag
      </button>
      {open && (
        <div className="absolute z-10 mt-1 w-44 bg-neutral-900 border border-neutral-800 rounded shadow-lg p-1.5 space-y-1">
          {available.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                onAdd(t.id);
                setOpen(false);
              }}
              className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-neutral-800"
            >
              {t.name}
            </button>
          ))}
          {available.length === 0 && <p className="text-[11px] text-neutral-500 px-2 py-1">No more tags</p>}
          <div className="flex gap-1 pt-1 border-t border-neutral-800">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && text.trim()) {
                  onCreate(text.trim());
                  setText("");
                  setOpen(false);
                }
              }}
              placeholder="New tag…"
              className="flex-1 min-w-0 bg-neutral-950 border border-neutral-800 rounded px-1.5 py-0.5 text-xs"
            />
          </div>
        </div>
      )}
    </span>
  );
}
