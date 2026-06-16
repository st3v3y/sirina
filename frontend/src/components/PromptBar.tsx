import { useEffect, useState } from "react";
import { api, type PromptTemplate } from "../lib/api";

type Props = {
  onAsk: (question: string, templateId?: number) => Promise<void>;
  onSummarize?: (templateId: number) => Promise<void>;
  disabled?: boolean;
};

export default function PromptBar({ onAsk, onSummarize, disabled }: Props) {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [qaTemplate, setQaTemplate] = useState<number | null>(null);
  const [summaryTemplate, setSummaryTemplate] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listTemplates().then((t) => {
      setTemplates(t);
      setQaTemplate(t.find((x) => x.kind === "qa" && x.is_default)?.id ?? null);
      setSummaryTemplate(t.find((x) => x.kind === "summary" && x.is_default)?.id ?? null);
    });
  }, []);

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onAsk(text, qaTemplate ?? undefined);
      setText("");
    } finally {
      setBusy(false);
    }
  }

  async function summarize() {
    if (!summaryTemplate || !onSummarize) return;
    setBusy(true);
    try {
      await onSummarize(summaryTemplate);
    } finally {
      setBusy(false);
    }
  }

  const qaOpts = templates.filter((t) => t.kind === "qa");
  const sumOpts = templates.filter((t) => t.kind === "summary");

  return (
    <div className="border-t border-neutral-800 bg-neutral-950/40 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <select
          value={qaTemplate ?? ""}
          onChange={(e) => setQaTemplate(e.target.value ? Number(e.target.value) : null)}
          className="bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs"
        >
          <option value="">(no template)</option>
          {qaOpts.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit())}
          placeholder="Ask a question about this meeting…"
          disabled={disabled || busy}
          className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-3 py-1.5 text-sm disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={disabled || busy || !text.trim()}
          className="bg-fuchsia-600 hover:bg-fuchsia-500 disabled:opacity-50 px-3 py-1.5 rounded text-sm"
        >
          Ask
        </button>
      </div>
      {onSummarize && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-neutral-500">Or generate full summary using:</span>
          <select
            value={summaryTemplate ?? ""}
            onChange={(e) => setSummaryTemplate(e.target.value ? Number(e.target.value) : null)}
            className="bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-xs"
          >
            {sumOpts.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <button
            onClick={summarize}
            disabled={disabled || busy || !summaryTemplate}
            className="bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 px-2 py-1 rounded"
          >
            Generate
          </button>
        </div>
      )}
    </div>
  );
}
