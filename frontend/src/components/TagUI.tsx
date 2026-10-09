import { useState } from "react";
import type { Tag } from "../lib/api";
import { Icon } from "./Icon";
import { catColor } from "../lib/tagColors";

export function TagChip({ tag, onRemove }: { tag: Tag; onRemove?: () => void }) {
  const c = catColor(tag.color);
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold px-2.5 py-0.5 rounded-full"
      style={{ color: c, backgroundColor: `color-mix(in srgb, ${c} 14%, transparent)` }}
    >
      <span className="w-[7px] h-[7px] rounded-full" style={{ background: c }} />
      {tag.name}
      {onRemove && (
        <button onClick={onRemove} className="opacity-60 hover:opacity-100 leading-none" title="Remove tag">
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
        className="inline-flex items-center gap-1 text-[11.5px] px-2.5 py-0.5 rounded-full border border-dashed border-line-3 text-muted hover:text-ink-2"
      >
        <Icon name="plus" size={11} /> Tag
      </button>
      {open && (
        <div className="absolute z-10 mt-1 w-44 bg-surface border border-line rounded-card shadow-pop p-1.5 space-y-1">
          {available.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                onAdd(t.id);
                setOpen(false);
              }}
              className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-surface-2"
            >
              {t.name}
            </button>
          ))}
          {available.length === 0 && <p className="text-[11px] text-muted px-2 py-1">No more tags</p>}
          <div className="flex gap-1 pt-1 border-t border-line">
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
              className="flex-1 min-w-0 bg-paper border border-line rounded px-1.5 py-0.5 text-xs"
            />
          </div>
        </div>
      )}
    </span>
  );
}
