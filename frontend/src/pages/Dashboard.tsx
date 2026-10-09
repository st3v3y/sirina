import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Recording, type RecordingStatus } from "../lib/api";
import { TagChip, AddTagButton } from "../components/TagUI";
import { Icon } from "../components/Icon";
import { useShell } from "../lib/shell";

const DOT: Record<RecordingStatus, string> = {
  ready: "bg-ok",
  processing: "bg-signal animate-recpulse",
  recording: "bg-signal animate-recpulse",
  failed: "bg-muted",
};

function fmtDuration(s: number | null) {
  if (s == null) return "";
  const total = Math.floor(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const ss = (total % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

function friendlyDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return `Today ${time}`;
  if (sameDay(d, yest)) return `Yesterday ${time}`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

const GROUP_ORDER = ["Recent", "Earlier this month", "Last month", "Older"] as const;
function bucket(iso: string): (typeof GROUP_ORDER)[number] {
  const d = new Date(iso);
  const now = new Date();
  const days = (now.getTime() - d.getTime()) / 86400000;
  if (days < 7) return "Recent";
  if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth())
    return "Earlier this month";
  const lm = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  if (d.getFullYear() === lm.getFullYear() && d.getMonth() === lm.getMonth()) return "Last month";
  return "Older";
}

export default function Dashboard() {
  const nav = useNavigate();
  const { tags, reloadTags, filterTag, setFilterTag } = useShell();
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [query, setQuery] = useState("");

  async function refresh() {
    try {
      setRecordings(await api.listRecordings(filterTag ?? undefined));
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    api.listRecordings(filterTag ?? undefined).then(setRecordings).catch(() => {});
  }, [filterTag]);

  const anyProcessing = recordings.some((r) => r.status === "processing");
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyProcessing]);

  async function addTag(recordingId: number, tagId: number) {
    await api.addTagToRecording(recordingId, tagId);
    refresh();
  }
  async function removeTag(recordingId: number, tagId: number) {
    await api.removeTagFromRecording(recordingId, tagId);
    refresh();
  }
  async function createAndAssign(recordingId: number, name: string) {
    const t = await api.createTag(name);
    await api.addTagToRecording(recordingId, t.id);
    await reloadTags();
    refresh();
  }
  async function retry(id: number) {
    await api.reprocessRecording(id);
    refresh();
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? recordings.filter((r) => (r.title ?? `Recording #${r.id}`).toLowerCase().includes(q))
      : recordings;
    const groups = new Map<string, Recording[]>();
    for (const r of list) {
      const b = bucket(r.started_at);
      (groups.get(b) ?? groups.set(b, []).get(b)!).push(r);
    }
    return GROUP_ORDER.filter((g) => groups.has(g)).map((g) => [g, groups.get(g)!] as const);
  }, [recordings, query]);

  const activeTag = tags.find((t) => t.id === filterTag);

  return (
    <div className="flex flex-col h-full">
      {/* header */}
      <div className="flex items-center gap-3.5 px-7 h-16 border-b border-line-2 shrink-0">
        <h1 className="font-serif text-xl font-semibold">Recordings</h1>
        {activeTag && (
          <button
            onClick={() => setFilterTag(null)}
            className="flex items-center gap-1.5 text-xs"
            title="Clear filter"
          >
            <TagChip tag={activeTag} />
            <Icon name="x" size={12} className="text-muted" />
          </button>
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-2 w-[300px] h-[38px] px-3 border border-line rounded-field bg-surface text-muted">
          <Icon name="search" size={14} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by name…"
            className="flex-1 min-w-0 bg-transparent text-[13px] text-ink placeholder:text-muted focus:outline-none"
          />
        </div>
      </div>

      {/* list */}
      <div className="flex-1 overflow-y-auto px-7 py-6">
        {filtered.length === 0 ? (
          <p className="text-sm text-muted">
            {query || filterTag != null ? "No matching recordings." : "No recordings yet — hit Record."}
          </p>
        ) : (
          filtered.map(([group, rows]) => (
            <div key={group} className="mb-6">
              <div className="text-[11px] font-bold uppercase tracking-wider text-label mb-3">
                {group}
              </div>
              <div className="rounded-card border border-line-2 bg-surface overflow-hidden shadow-card">
                {rows.map((r, i) => {
                  const processing = r.status === "processing";
                  const pct =
                    r.progress?.fraction != null ? Math.round(r.progress.fraction * 100) : null;
                  return (
                    <div
                      key={r.id}
                      onClick={() =>
                        nav(r.status === "recording" ? `/recordings/live/${r.id}` : `/recordings/${r.id}`)
                      }
                      className={`flex items-center gap-4 px-[18px] py-4 cursor-pointer hover:bg-surface-2 ${
                        i < rows.length - 1 ? "border-b border-line-2" : ""
                      }`}
                    >
                      <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${DOT[r.status]}`} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[15px] font-semibold truncate">
                          {r.title || `Recording #${r.id}`}
                        </div>
                        <div className="text-xs text-muted mt-0.5 font-mono">
                          {processing
                            ? `Transcribing… ${pct ?? 0}%`
                            : `${friendlyDate(r.started_at)} · ${fmtDuration(r.duration_s) || "—"}`}
                        </div>
                      </div>
                      <div
                        className="flex flex-wrap items-center gap-1.5 justify-end"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.tags.map((t) => (
                          <TagChip key={t.id} tag={t} onRemove={() => removeTag(r.id, t.id)} />
                        ))}
                        <AddTagButton
                          allTags={tags}
                          currentIds={r.tags.map((t) => t.id)}
                          onAdd={(tagId) => addTag(r.id, tagId)}
                          onCreate={(name) => createAndAssign(r.id, name)}
                        />
                      </div>
                      {processing ? (
                        <div className="w-[140px] h-1.5 rounded-full bg-line-2 overflow-hidden shrink-0">
                          <div
                            className="h-full bg-signal-grad transition-all"
                            style={{ width: `${pct ?? 8}%` }}
                          />
                        </div>
                      ) : r.status === "failed" ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            retry(r.id);
                          }}
                          className="shrink-0 text-xs px-2 py-1 rounded-field bg-warn/15 text-warn-deep hover:bg-warn/25"
                        >
                          Retry
                        </button>
                      ) : (
                        <Icon name="chevron-right" size={16} className="text-line-3 shrink-0" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
