import { useEffect, useState } from "react";
import { api, type SummaryTemplate } from "../lib/api";
import { Icon } from "./Icon";

type Props = {
  onAsk: (question: string) => Promise<void>;
  onSummarize?: (templateId: number) => Promise<void>;
  disabled?: boolean;
};

export default function PromptBar({ onAsk, onSummarize, disabled }: Props) {
  const [summaryTemplates, setSummaryTemplates] = useState<SummaryTemplate[]>([]);
  const [summaryTemplate, setSummaryTemplate] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listSummaryTemplates().then((t) => {
      setSummaryTemplates(t);
      setSummaryTemplate((t.find((x) => x.is_default) ?? t[0])?.id ?? null);
    });
  }, []);

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onAsk(text);
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

  return (
    <div className="border-t border-line-2 p-4 space-y-2 shrink-0">
      <div className="flex items-center gap-2 h-[50px] border border-line rounded-card bg-surface pl-4 pr-2 shadow-card">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit())}
          placeholder="Ask about this meeting…"
          disabled={disabled || busy}
          className="flex-1 bg-transparent text-[13.5px] text-ink placeholder:text-muted focus:outline-none disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={disabled || busy || !text.trim()}
          className="w-9 h-9 rounded-field bg-ink text-paper flex items-center justify-center disabled:opacity-40"
          title="Ask"
        >
          <Icon name="arrow-up" size={15} />
        </button>
      </div>
      {onSummarize && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted">Generate summary using:</span>
          <select
            value={summaryTemplate ?? ""}
            onChange={(e) => setSummaryTemplate(e.target.value ? Number(e.target.value) : null)}
            className="bg-surface border border-line rounded-field px-2 py-1 text-xs"
          >
            {summaryTemplates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <button
            onClick={summarize}
            disabled={disabled || busy || !summaryTemplate}
            className="border border-line text-ink-2 hover:bg-surface-2 disabled:opacity-50 px-2 py-1 rounded-field"
          >
            Generate
          </button>
        </div>
      )}
    </div>
  );
}
