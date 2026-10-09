import { useEffect, useState } from "react";
import { api, type SummaryTemplate, type TemplateSection } from "../lib/api";
import { confirmDialog } from "../lib/confirm";

type Draft = { id: number; name: string; general_context: string; sections: TemplateSection[] };

export default function Templates() {
  const [items, setItems] = useState<SummaryTemplate[]>([]);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [qaBody, setQaBody] = useState<string>("");
  const [qaSaved, setQaSaved] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  async function refresh() {
    setItems(await api.listSummaryTemplates());
    const qa = await api.getQaTemplate();
    setQaBody(qa?.body ?? "");
  }
  useEffect(() => {
    api.listSummaryTemplates().then(async (list) => {
      setItems(list);
      const qa = await api.getQaTemplate();
      setQaBody(qa?.body ?? "");
    });
  }, []);

  function startNew() {
    setEditing({ id: 0, name: "Untitled", general_context: "", sections: [{ title: "Summary", prompt: "Summarise the meeting." }] });
  }
  function edit(t: SummaryTemplate) {
    setEditing({ id: t.id, name: t.name, general_context: t.general_context ?? "", sections: t.sections });
  }
  function clone(t: SummaryTemplate) {
    setEditing({ id: 0, name: `${t.name} (copy)`, general_context: t.general_context ?? "", sections: t.sections });
  }

  async function save() {
    if (!editing) return;
    const general_context = editing.general_context.trim() || null;
    if (editing.id === 0) {
      await api.createSummaryTemplate({ name: editing.name, sections: editing.sections, general_context });
    } else {
      await api.updateSummaryTemplate(editing.id, { name: editing.name, sections: editing.sections, general_context });
    }
    setEditing(null);
    refresh();
  }

  async function del(id: number) {
    if (!(await confirmDialog("Delete this template?"))) return;
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
    setEditing({ ...editing, sections: [...editing.sections, { title: "", prompt: "" }] });
  }
  function removeSection(i: number) {
    if (!editing) return;
    setEditing({ ...editing, sections: editing.sections.filter((_, j) => j !== i) });
  }
  function moveSection(from: number, to: number) {
    if (!editing || from === to) return;
    const sections = [...editing.sections];
    const [moved] = sections.splice(from, 1);
    sections.splice(to, 0, moved);
    setEditing({ ...editing, sections });
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-medium">Summary templates</h2>
          <button onClick={startNew} className="text-sm px-3 py-1.5 rounded bg-surface border border-line hover:bg-surface-2">
            + New
          </button>
        </div>
        <ul className="divide-y divide-line-2 rounded-card border border-line-2 bg-surface shadow-card">
          {items.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span className="flex-1 truncate">{t.name}</span>
              <span className="text-xs text-muted">{t.sections.length} sections</span>
              {t.is_default && <span className="text-xs text-ok-deep">default</span>}
              {t.builtin && <span className="text-[10px] uppercase text-muted border border-line rounded px-1">built-in</span>}
              {t.builtin ? (
                <button onClick={() => clone(t)} className="text-xs px-2 py-1 rounded bg-surface border border-line hover:bg-surface-2">
                  Clone
                </button>
              ) : (
                <button onClick={() => edit(t)} className="text-xs px-2 py-1 rounded bg-surface border border-line hover:bg-surface-2">
                  Edit
                </button>
              )}
              <button
                onClick={() => del(t.id)}
                disabled={t.builtin}
                className="text-xs px-2 py-1 rounded text-muted hover:text-signal disabled:opacity-30"
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
          className="w-full h-48 bg-paper border border-line rounded p-3 text-xs font-mono"
          value={qaBody}
          onChange={(e) => setQaBody(e.target.value)}
          placeholder="Use {{transcript}}, {{qa_history}}, {{question}}."
        />
        <div className="flex items-center gap-2 mt-2">
          <button onClick={saveQa} className="text-sm px-3 py-1.5 rounded bg-signal-grad text-white">
            Save Q&amp;A prompt
          </button>
          {qaSaved && <span className="text-xs text-ok-deep">Saved</span>}
        </div>
      </section>

      {editing && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-surface border border-line rounded-lg max-w-2xl w-full p-5 space-y-3 max-h-[85vh] overflow-y-auto">
            <input
              className="w-full bg-paper border border-line rounded px-3 py-1.5 text-sm"
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              placeholder="Template name"
            />
            <div>
              <label className="block text-xs text-muted mb-1">General context (optional)</label>
              <textarea
                className="w-full h-20 bg-paper border border-line rounded p-2 text-xs"
                value={editing.general_context}
                onChange={(e) => setEditing({ ...editing, general_context: e.target.value })}
                placeholder="Describes the template's purpose / audience. Added before every section."
              />
            </div>
            <p className="text-xs text-muted">
              Each section is a separate prompt. The transcript is added automatically — just describe
              what you want. Drag a section to reorder.
            </p>
            {editing.sections.map((sec, i) => (
              <div
                key={i}
                className={`rounded border p-3 space-y-2 ${dragIndex === i ? "border-signal" : "border-line-2"}`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragIndex !== null) moveSection(dragIndex, i);
                  setDragIndex(null);
                }}
              >
                <div className="flex items-center gap-2">
                  <span
                    draggable
                    onDragStart={() => setDragIndex(i)}
                    onDragEnd={() => setDragIndex(null)}
                    title="Drag to reorder"
                    className="cursor-grab text-muted hover:text-ink select-none px-1"
                  >
                    ⠿
                  </span>
                  <input
                    className="flex-1 bg-paper border border-line rounded px-2 py-1 text-sm"
                    value={sec.title}
                    onChange={(e) => setSection(i, { title: e.target.value })}
                    placeholder="Section title"
                  />
                  <button
                    onClick={() => removeSection(i)}
                    className="text-xs px-2 py-1 rounded text-muted hover:text-signal"
                  >
                    Remove
                  </button>
                </div>
                <textarea
                  className="w-full h-24 bg-paper border border-line rounded p-2 text-xs font-mono"
                  value={sec.prompt}
                  onChange={(e) => setSection(i, { prompt: e.target.value })}
                  placeholder="What should this section produce? (e.g. List the decisions made.)"
                />
              </div>
            ))}
            <button onClick={addSection} className="text-xs px-2 py-1 rounded bg-surface border border-line hover:bg-surface-2">
              + Add section
            </button>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setEditing(null)} className="text-sm px-3 py-1.5 rounded bg-surface border border-line hover:bg-surface-2">
                Cancel
              </button>
              <button onClick={save} className="text-sm px-3 py-1.5 rounded bg-signal-grad text-white">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
