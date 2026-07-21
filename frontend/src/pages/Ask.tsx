import { useEffect, useMemo, useState } from "react";
import { api, type ChatSession } from "../lib/api";
import { confirmDialog } from "../lib/confirm";
import { Icon } from "../components/Icon";

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
    if (!(await confirmDialog("Delete this chat session?"))) return;
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
      // Show the question immediately; the spinner below runs until the answer arrives.
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  { id: Date.now(), session_id: sessionId!, role: "user", content: question, created_at: new Date().toISOString() },
                ],
              }
            : s
        )
      );
      let answerText: string;
      try {
        const { answer } = await api.askChatSession(sessionId, question);
        answerText = answer || "_(The AI returned an empty answer.)_";
      } catch (e) {
        // Surface the failure in the chat instead of leaving a dangling question bubble.
        answerText = `⚠️ Couldn't get an answer: ${e instanceof Error ? e.message : String(e)}`;
      }
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  { id: Date.now() + 1, session_id: sessionId!, role: "assistant", content: answerText, created_at: new Date().toISOString() },
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
      <aside className="w-60 shrink-0 border-r border-line-2 flex flex-col min-h-0">
        <div className="p-3 border-b border-line-2">
          <button
            onClick={newSession}
            className="w-full text-sm px-3 py-2 rounded-field bg-signal-grad text-white font-semibold"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && <p className="text-xs text-muted px-2 py-1">No chats yet.</p>}
          {sessions.map((s) => {
            const label =
              s.title ||
              s.messages.find((m) => m.role === "user")?.content.slice(0, 40) ||
              `Chat #${s.id}`;
            return (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-lg px-2.5 py-2 text-sm cursor-pointer ${
                  activeId === s.id ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:bg-surface-2"
                }`}
                onClick={() => setActiveId(s.id)}
              >
                <span className="truncate flex-1">{label}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-muted hover:text-signal text-xs"
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
        <div className="flex-1 overflow-y-auto px-7 py-6 space-y-4">
          {!active || active.messages.length === 0 ? (
            <div className="text-sm text-muted max-w-lg mx-auto mt-10 text-center space-y-2">
              <p className="font-serif text-lg text-ink-2">Ask across all your recordings.</p>
              <p>e.g. “Recap this week's meetings”, “Which issues are impacting our customers?”</p>
            </div>
          ) : (
            active.messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[74%] px-4 py-3 text-[13.5px] leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-ink text-paper rounded-[16px_16px_5px_16px]"
                      : "bg-surface border border-line-2 text-ink rounded-[16px_16px_16px_5px] shadow-card"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))
          )}
          {busy && active && (
            <div className="flex justify-start">
              <div className="bg-surface border border-line-2 rounded-[16px_16px_16px_5px] shadow-card px-4 py-3">
                <span className="inline-block w-4 h-4 rounded-full border-2 border-line-3 border-t-signal animate-spin" />
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-line-2 p-4">
          <div className="flex items-center gap-2 h-[50px] border border-line rounded-card bg-surface pl-4 pr-2 shadow-card">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="Ask across all recordings…"
              disabled={busy}
              className="flex-1 bg-transparent text-[13.5px] text-ink placeholder:text-muted focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={busy || !text.trim()}
              className="w-9 h-9 rounded-field bg-ink text-paper flex items-center justify-center disabled:opacity-40"
            >
              <Icon name="arrow-up" size={15} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
