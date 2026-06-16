import { useEffect, useState } from "react";
import { api, type Person } from "../lib/api";

export default function People() {
  const [people, setPeople] = useState<Person[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  async function refresh() {
    setPeople(await api.listPeople());
  }
  useEffect(() => {
    refresh();
  }, []);

  async function rename(id: number) {
    const name = draft.trim();
    setEditingId(null);
    if (name) {
      await api.renamePerson(id, name);
      refresh();
    }
  }

  async function del(id: number) {
    if (!confirm("Delete this person? Their speakers revert to default labels; recordings are kept.")) return;
    await api.deletePerson(id);
    refresh();
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h2 className="text-base font-medium mb-4">People</h2>
      {people.length === 0 ? (
        <p className="text-sm text-neutral-500">
          No people yet. Rename a speaker in a recording to create one.
        </p>
      ) : (
        <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
          {people.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              {editingId === p.id ? (
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") rename(p.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onBlur={() => rename(p.id)}
                  className="flex-1 bg-neutral-950 border border-neutral-700 rounded px-2 py-1 text-sm"
                />
              ) : (
                <span className="flex-1 truncate">{p.name}</span>
              )}
              <span className="text-xs text-neutral-500 w-24 text-right">
                {p.recording_count} {p.recording_count === 1 ? "meeting" : "meetings"}
              </span>
              <span className="text-xs text-neutral-500 w-40 text-right">
                {p.last_recording_at ? new Date(p.last_recording_at).toLocaleDateString() : "—"}
              </span>
              <button
                onClick={() => {
                  setEditingId(p.id);
                  setDraft(p.name);
                }}
                className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
              >
                Rename
              </button>
              <button
                onClick={() => del(p.id)}
                className="text-xs px-2 py-1 rounded text-neutral-400 hover:text-rose-400"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
