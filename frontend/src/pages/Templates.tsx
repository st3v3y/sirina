import { useEffect, useState } from "react";
import { api, type PromptTemplate } from "../lib/api";

const KINDS = ["aspects", "summary", "qa"] as const;

export default function Templates() {
  const [items, setItems] = useState<PromptTemplate[]>([]);
  const [editing, setEditing] = useState<PromptTemplate | null>(null);

  async function refresh() {
    setItems(await api.listTemplates());
  }
  useEffect(() => {
    refresh();
  }, []);

  function startNew() {
    setEditing({ id: 0, name: "Untitled", kind: "summary", body: "", is_default: false });
  }

  async function save() {
    if (!editing) return;
    if (editing.id === 0) {
      await api.createTemplate({ name: editing.name, kind: editing.kind, body: editing.body });
    } else {
      await api.updateTemplate(editing.id, {
        name: editing.name,
        kind: editing.kind,
        body: editing.body,
      });
    }
    setEditing(null);
    refresh();
  }

  async function del(id: number) {
    if (!confirm("Delete this template?")) return;
    await api.deleteTemplate(id);
    refresh();
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium">Prompt templates</h2>
        <button
          onClick={startNew}
          className="text-sm px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700"
        >
          + New
        </button>
      </div>
      <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
        {items.map((t) => (
          <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-sm">
            <span className="flex-1 truncate">{t.name}</span>
            <span className="text-xs text-neutral-500 w-20">{t.kind}</span>
            {t.is_default && (
              <span className="text-xs text-emerald-400">default</span>
            )}
            <button
              onClick={() => setEditing(t)}
              className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
            >
              Edit
            </button>
            <button
              onClick={() => del(t.id)}
              className="text-xs px-2 py-1 rounded text-neutral-400 hover:text-rose-400"
              disabled={t.is_default}
              title={t.is_default ? "Default templates can't be deleted" : ""}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>

      {editing && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg max-w-2xl w-full p-5 space-y-3">
            <div className="flex items-center gap-2">
              <input
                className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm"
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              />
              <select
                value={editing.kind}
                onChange={(e) => setEditing({ ...editing, kind: e.target.value as PromptTemplate["kind"] })}
                className="bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </div>
            <textarea
              className="w-full h-64 bg-neutral-950 border border-neutral-800 rounded p-3 text-xs font-mono"
              value={editing.body}
              onChange={(e) => setEditing({ ...editing, body: e.target.value })}
              placeholder="Use {{transcript}}, {{new_transcript}}, {{previous_aspects}}, {{qa_history}}, {{question}} as placeholders."
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setEditing(null)}
                className="text-sm px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700"
              >
                Cancel
              </button>
              <button
                onClick={save}
                className="text-sm px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
