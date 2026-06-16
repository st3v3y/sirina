import { useEffect, useState } from "react";
import { api, type SummaryTemplate, type TemplateSection } from "../lib/api";

type Draft = { id: number; name: string; sections: TemplateSection[] };

export default function Templates() {
  const [items, setItems] = useState<SummaryTemplate[]>([]);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [qaBody, setQaBody] = useState<string>("");
  const [qaSaved, setQaSaved] = useState(false);

  async function refresh() {
    setItems(await api.listSummaryTemplates());
    const qa = await api.getQaTemplate();
    setQaBody(qa?.body ?? "");
  }
  useEffect(() => {
    refresh();
  }, []);

  function startNew() {
    setEditing({ id: 0, name: "Untitled", sections: [{ title: "Summary", prompt: "Summarise:\n{{transcript}}" }] });
  }
  function edit(t: SummaryTemplate) {
    setEditing({ id: t.id, name: t.name, sections: t.sections });
  }
  function clone(t: SummaryTemplate) {
    setEditing({ id: 0, name: `${t.name} (copy)`, sections: t.sections });
  }

  async function save() {
    if (!editing) return;
    if (editing.id === 0) {
      await api.createSummaryTemplate({ name: editing.name, sections: editing.sections });
    } else {
      await api.updateSummaryTemplate(editing.id, { name: editing.name, sections: editing.sections });
    }
    setEditing(null);
    refresh();
  }

  async function del(id: number) {
    if (!confirm("Delete this template?")) return;
    await api.deleteSummaryTemplate(id);
    refresh();
  }

  async function saveQa() {
    await api.updateQaTemplate(qaBody);
    setQaSaved(true);
    setTimeout(() => setQaSaved(false), 1500);
  }

  function setSection(i: number, patch: Partial<TemplateSection>) {
    if (!editing) return;
    const sections = editing.sections.map((s, j) => (j === i ? { ...s, ...patch } : s));
    setEditing({ ...editing, sections });
  }
  function addSection() {
    if (!editing) return;
    setEditing({ ...editing, sections: [...editing.sections, { title: "", prompt: "{{transcript}}" }] });
  }
  function removeSection(i: number) {
    if (!editing) return;
    setEditing({ ...editing, sections: editing.sections.filter((_, j) => j !== i) });
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-medium">Summary templates</h2>
          <button onClick={startNew} className="text-sm px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700">
            + New
          </button>
        </div>
        <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
          {items.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span className="flex-1 truncate">{t.name}</span>
              <span className="text-xs text-neutral-500">{t.sections.length} sections</span>
              {t.is_default && <span className="text-xs text-emerald-400">default</span>}
              {t.builtin && <span className="text-[10px] uppercase text-neutral-500 border border-neutral-700 rounded px-1">built-in</span>}
              {t.builtin ? (
                <button onClick={() => clone(t)} className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">
                  Clone
                </button>
              ) : (
                <button onClick={() => edit(t)} className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">
                  Edit
                </button>
              )}
              <button
                onClick={() => del(t.id)}
                disabled={t.builtin}
                className="text-xs px-2 py-1 rounded text-neutral-400 hover:text-rose-400 disabled:opacity-30"
                title={t.builtin ? "Built-in templates can't be deleted (clone to customize)" : ""}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-base font-medium mb-3">Q&amp;A prompt</h2>
        <textarea
          className="w-full h-48 bg-neutral-950 border border-neutral-800 rounded p-3 text-xs font-mono"
          value={qaBody}
          onChange={(e) => setQaBody(e.target.value)}
          placeholder="Use {{transcript}}, {{qa_history}}, {{question}}."
        />
        <div className="flex items-center gap-2 mt-2">
          <button onClick={saveQa} className="text-sm px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500">
            Save Q&amp;A prompt
          </button>
          {qaSaved && <span className="text-xs text-emerald-400">Saved</span>}
        </div>
      </section>

      {editing && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg max-w-2xl w-full p-5 space-y-3 max-h-[85vh] overflow-y-auto">
            <input
              className="w-full bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm"
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              placeholder="Template name"
            />
            <p className="text-xs text-neutral-500">
              Each section is a separate prompt. Use <code>{"{{transcript}}"}</code>, <code>{"{{title}}"}</code>, <code>{"{{date}}"}</code>.
            </p>
            {editing.sections.map((sec, i) => (
              <div key={i} className="rounded border border-neutral-800 p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-sm"
                    value={sec.title}
                    onChange={(e) => setSection(i, { title: e.target.value })}
                    placeholder="Section title"
                  />
                  <button
                    onClick={() => removeSection(i)}
                    className="text-xs px-2 py-1 rounded text-neutral-400 hover:text-rose-400"
                  >
                    Remove
                  </button>
                </div>
                <textarea
                  className="w-full h-24 bg-neutral-950 border border-neutral-800 rounded p-2 text-xs font-mono"
                  value={sec.prompt}
                  onChange={(e) => setSection(i, { prompt: e.target.value })}
                  placeholder="Section prompt"
                />
              </div>
            ))}
            <button onClick={addSection} className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">
              + Add section
            </button>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setEditing(null)} className="text-sm px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700">
                Cancel
              </button>
              <button onClick={save} className="text-sm px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
