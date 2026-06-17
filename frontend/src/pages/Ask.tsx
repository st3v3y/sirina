import { useEffect, useMemo, useState } from "react";
import { api, type ChatSession } from "../lib/api";

export default function Ask() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const active = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId]
  );

  async function refresh(selectId?: number) {
    const list = await api.listChatSessions();
    setSessions(list);
    if (selectId != null) setActiveId(selectId);
    else if (activeId == null && list.length > 0) setActiveId(list[0].id);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function newSession() {
    const s = await api.createChatSession();
    await refresh(s.id);
  }

  async function deleteSession(id: number) {
    if (!confirm("Delete this chat session?")) return;
    await api.deleteChatSession(id);
    if (activeId === id) setActiveId(null);
    refresh();
  }

  async function send() {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    try {
      let sessionId = activeId;
      if (sessionId == null) {
        const s = await api.createChatSession();
        sessionId = s.id;
        setSessions((prev) => [s, ...prev]);
        setActiveId(s.id);
      }
      setText("");
      const { answer } = await api.askChatSession(sessionId, question);
      const now = new Date().toISOString();
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  { id: Date.now(), session_id: sessionId!, role: "user", content: question, created_at: now },
                  { id: Date.now() + 1, session_id: sessionId!, role: "assistant", content: answer, created_at: now },
                ],
              }
            : s
        )
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full flex min-h-0">
      <aside className="w-60 shrink-0 border-r border-neutral-800 flex flex-col min-h-0">
        <div className="p-3 border-b border-neutral-800">
          <button
            onClick={newSession}
            className="w-full text-sm px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && (
            <p className="text-xs text-neutral-500 px-2 py-1">No chats yet.</p>
          )}
          {sessions.map((s) => {
            const label =
              s.title ||
              s.messages.find((m) => m.role === "user")?.content.slice(0, 40) ||
              `Chat #${s.id}`;
            return (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded px-2 py-1.5 text-sm cursor-pointer ${
                  activeId === s.id ? "bg-neutral-800 text-neutral-100" : "text-neutral-400 hover:bg-neutral-900"
                }`}
                onClick={() => setActiveId(s.id)}
              >
                <span className="truncate flex-1">{label}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-neutral-500 hover:text-rose-400 text-xs"
                  title="Delete"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {!active || active.messages.length === 0 ? (
            <div className="text-sm text-neutral-500 max-w-lg mx-auto mt-10 text-center space-y-2">
              <p>Ask questions across all your recordings.</p>
              <p className="text-neutral-600">
                e.g. “Recap this week's meetings”, “Which issues are impacting our customers?”
              </p>
            </div>
          ) : (
            active.messages.map((m) => (
              <div key={m.id} className="flex gap-3">
                <span
                  className={`shrink-0 text-xs px-2 py-0.5 h-fit rounded border ${
                    m.role === "user"
                      ? "bg-neutral-800 text-neutral-300 border-neutral-700"
                      : "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/30"
                  }`}
                >
                  {m.role === "user" ? "You" : "AI"}
                </span>
                <div className="text-sm leading-snug whitespace-pre-wrap">{m.content}</div>
              </div>
            ))
          )}
        </div>

        <div className="border-t border-neutral-800 bg-neutral-950/40 p-3">
          <div className="flex items-center gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="Ask across all recordings…"
              disabled={busy}
              className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-3 py-1.5 text-sm disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={busy || !text.trim()}
              className="bg-fuchsia-600 hover:bg-fuchsia-500 disabled:opacity-50 px-3 py-1.5 rounded text-sm"
            >
              {busy ? "…" : "Ask"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
