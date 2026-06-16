import type { Summary } from "../lib/api";

export default function AspectsPanel({ latest }: { latest: Summary | null }) {
  const bullets = latest?.content
    .split("\n")
    .map((l) => l.replace(/^[-*•\s]+/, "").trim())
    .filter(Boolean) ?? [];

  return (
    <div className="h-full overflow-y-auto p-4 border-l border-neutral-800 bg-neutral-950/30">
      <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">
        Live aspects
      </h3>
      {bullets.length === 0 ? (
        <p className="text-sm text-neutral-500">
          The AI will summarise the discussion here as it progresses.
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {bullets.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-neutral-600">•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
      )}
      {latest && (
        <p className="text-[10px] text-neutral-600 mt-4">
          updated {new Date(latest.created_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
