import { useEffect, useState } from "react";
import { api, type Person } from "../lib/api";
import { confirmDialog } from "../lib/confirm";
import { Avatar, Button } from "../components/ui";

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
    if (!(await confirmDialog("Delete this person? Their speakers revert to default labels; recordings are kept."))) return;
    await api.deletePerson(id);
    refresh();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-7 h-16 border-b border-line-2 shrink-0">
        <h1 className="font-serif text-xl font-semibold">People</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-7 py-6">
        <div className="max-w-[760px] mx-auto">
          {people.length === 0 ? (
            <p className="text-sm text-muted">No people yet. Rename a speaker in a recording to create one.</p>
          ) : (
            <div className="rounded-card border border-line-2 bg-surface shadow-card overflow-hidden">
              {people.map((p, i) => (
                <div
                  key={p.id}
                  className={`flex items-center gap-3 px-4 py-3 text-sm ${i < people.length - 1 ? "border-b border-line-2" : ""}`}
                >
                  <Avatar name={p.name} size={32} />
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
                      className="flex-1 bg-paper border border-line rounded-field px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="flex-1 truncate font-semibold flex items-center gap-2">
                      {p.name}
                      {p.is_self && (
                        <span className="text-[10px] font-bold uppercase tracking-wide text-signal bg-signal/10 rounded-full px-1.5 py-0.5">
                          You
                        </span>
                      )}
                    </span>
                  )}
                  <span className="text-xs text-muted w-24 text-right font-mono">
                    {p.recording_count} {p.recording_count === 1 ? "meeting" : "meetings"}
                  </span>
                  <span className="text-xs text-muted w-32 text-right font-mono">
                    {p.last_recording_at ? new Date(p.last_recording_at).toLocaleDateString() : "—"}
                  </span>
                  <Button
                    onClick={() => {
                      setEditingId(p.id);
                      setDraft(p.name);
                    }}
                    className="!h-8 !px-2.5 text-xs"
                  >
                    Rename
                  </Button>
                  <button onClick={() => del(p.id)} className="text-xs px-2 py-1 rounded-field text-muted hover:text-signal">
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
