import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type AudioDevice, type Recording, type RecordingStatus, type Tag } from "../lib/api";
import { TagChip, AddTagButton, TAG_COLORS, tagChipClass } from "../components/TagUI";

const STATUS_BADGE: Record<RecordingStatus, string> = {
  recording: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  processing: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed: "bg-neutral-700/40 text-neutral-300 border-neutral-600",
};

const LS_MIC = "lastMicDevice";
const LS_SYSTEM = "lastSystemDevice";

function lsGet(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function lsSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* localStorage unavailable (private mode / restricted webview) — ignore */
  }
}

function fmtDuration(s: number | null) {
  if (s == null) return "";
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
}

export default function Dashboard() {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [title, setTitle] = useState("");
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [device, setDevice] = useState<string>("");
  const [systemDevice, setSystemDevice] = useState<string>("");
  const [picking, setPicking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [filterTag, setFilterTag] = useState<number | null>(null);
  const [managing, setManaging] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const nav = useNavigate();

  async function refresh(tagId: number | null = filterTag) {
    try {
      setRecordings(await api.listRecordings(tagId ?? undefined));
    } catch (e) {
      setError(String(e));
    }
  }

  async function loadTags() {
    setTags(await api.listTags());
  }

  function applyFilter(tagId: number | null) {
    setFilterTag(tagId);
    refresh(tagId);
  }

  async function addTag(recordingId: number, tagId: number) {
    await api.addTagToRecording(recordingId, tagId);
    refresh();
  }
  async function removeTag(recordingId: number, tagId: number) {
    await api.removeTagFromRecording(recordingId, tagId);
    refresh();
  }
  async function createAndAssign(recordingId: number, name: string) {
    const t = await api.createTag(name, TAG_COLORS[tags.length % TAG_COLORS.length]);
    await api.addTagToRecording(recordingId, t.id);
    await loadTags();
    refresh();
  }

  useEffect(() => {
    refresh();
    loadTags();
    api
      .listAudioDevices()
      .then((d) => {
        setDevices(d);
        // Prefer the last-used devices (if still present), else auto-detect a mic.
        const names = new Set(d.map((x) => x.name));
        const savedMic = lsGet(LS_MIC);
        const savedSys = lsGet(LS_SYSTEM);
        const mic = (savedMic && names.has(savedMic) && savedMic) ||
          (d.find((x) => /microphone|mic/i.test(x.name)) ?? d[0])?.name || "";
        setDevice(mic);
        setSystemDevice(savedSys && names.has(savedSys) ? savedSys : "");
      })
      .catch(() => setDevices([]));
  }, []);

  // Keep the list fresh (and the progress % advancing) while anything is processing.
  const anyProcessing = recordings.some((r) => r.status === "processing");
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(() => refresh(), 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyProcessing]);

  function openPicker() {
    setError(null);
    setPicking(true);
  }

  async function confirmStart() {
    if (!device && !systemDevice) {
      setError("Select a microphone or a system-audio source.");
      return;
    }
    setStarting(true);
    setError(null);
    try {
      lsSet(LS_MIC, device);
      lsSet(LS_SYSTEM, systemDevice);
      const { id } = await api.startRecording({
        title: title || undefined,
        device: device || undefined,
        system_device: systemDevice || undefined,
      });
      nav(`/recordings/live/${id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }

  async function del(id: number) {
    if (!confirm("Delete this recording and all its data?")) return;
    await api.deleteRecording(id);
    refresh();
  }

  async function retry(id: number) {
    await api.reprocessRecording(id);
    refresh();
  }

  async function commitTitle(id: number, current: string | null) {
    const v = editTitle.trim();
    setEditingId(null);
    if (v !== (current ?? "")) {
      await api.renameRecording(id, v);
      refresh();
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
        <h2 className="text-base font-medium mb-3">Start a recording</h2>

        <div className="flex flex-wrap gap-2 items-center">
          <input
            className="bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm flex-1 min-w-[10rem]"
            placeholder="Title (optional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button
            onClick={openPicker}
            disabled={starting}
            className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 px-4 py-1.5 rounded text-sm font-medium"
          >
            {starting ? "Starting…" : "● Start recording"}
          </button>
        </div>

        <p className="text-xs text-neutral-500 mt-2">
          Records to disk only — transcription and the AI summary run after you stop. You'll choose
          the audio source when you start.
        </p>
        {error && !picking && <p className="text-rose-400 text-xs mt-2">{error}</p>}
      </section>

      {picking && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-20">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg max-w-md w-full p-5 space-y-4">
            <h3 className="text-sm font-medium">Choose audio source</h3>

            <div>
              <label className="block text-xs text-neutral-500 mb-1">Microphone</label>
              <select
                className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm"
                value={device}
                onChange={(e) => setDevice(e.target.value)}
              >
                <option value="">None</option>
                {devices.map((d) => (
                  <option key={`m-${d.index}`} value={d.name}>
                    {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-neutral-500 mb-1">System audio</label>
              <select
                className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm"
                value={systemDevice}
                onChange={(e) => setSystemDevice(e.target.value)}
              >
                <option value="">None</option>
                {devices.map((d) => (
                  <option key={`s-${d.index}`} value={d.name}>
                    {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
                  </option>
                ))}
              </select>
            </div>

            <p className="text-xs text-neutral-500">
              Pick at least one. Use a system-audio device (e.g. BlackHole) to capture a call as a
              second track.
            </p>
            {error && <p className="text-rose-400 text-xs">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setPicking(false)}
                disabled={starting}
                className="text-sm px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700"
              >
                Cancel
              </button>
              <button
                onClick={confirmStart}
                disabled={starting || (!device && !systemDevice)}
                className="text-sm px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-500 disabled:opacity-50 font-medium"
              >
                {starting ? "Starting…" : "● Start"}
              </button>
            </div>
          </div>
        </div>
      )}

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-medium">Recordings</h2>
          {tags.length > 0 && (
            <button
              onClick={() => setManaging((m) => !m)}
              className="text-xs text-neutral-400 hover:text-neutral-200"
            >
              {managing ? "Done" : "Manage tags"}
            </button>
          )}
        </div>

        {tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            <button
              onClick={() => applyFilter(null)}
              className={`text-[11px] px-2 py-0.5 rounded border ${filterTag == null ? "bg-neutral-700 text-neutral-100 border-neutral-600" : "border-neutral-800 text-neutral-400 hover:text-neutral-200"}`}
            >
              All
            </button>
            {tags.map((t) => (
              <button key={t.id} onClick={() => applyFilter(t.id)} className={filterTag === t.id ? "ring-1 ring-neutral-400 rounded" : ""}>
                <TagChip tag={t} />
              </button>
            ))}
          </div>
        )}

        {managing && (
          <div className="mb-3 rounded-lg border border-neutral-800 divide-y divide-neutral-800">
            {tags.map((t) => (
              <div key={t.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <span className={`text-[11px] px-1.5 py-0.5 rounded border ${tagChipClass(t.color)}`}>{t.name}</span>
                <input
                  defaultValue={t.name}
                  onBlur={async (e) => {
                    const v = e.target.value.trim();
                    if (v && v !== t.name) { await api.updateTag(t.id, { name: v }); loadTags(); refresh(); }
                  }}
                  className="bg-neutral-950 border border-neutral-800 rounded px-2 py-0.5 text-xs w-32"
                />
                <select
                  value={t.color ?? "neutral"}
                  onChange={async (e) => { await api.updateTag(t.id, { color: e.target.value }); loadTags(); refresh(); }}
                  className="bg-neutral-950 border border-neutral-800 rounded px-1 py-0.5 text-xs"
                >
                  {TAG_COLORS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <button
                  onClick={async () => { if (confirm(`Delete tag "${t.name}"?`)) { await api.deleteTag(t.id); if (filterTag === t.id) setFilterTag(null); loadTags(); refresh(filterTag === t.id ? null : filterTag); } }}
                  className="ml-auto text-xs text-neutral-400 hover:text-rose-400"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}

        {recordings.length === 0 ? (
          <p className="text-sm text-neutral-500">{filterTag != null ? "No recordings with this tag." : "No recordings yet."}</p>
        ) : (
          <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
            {recordings.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <span className="text-neutral-500 text-xs w-40 shrink-0">
                  {new Date(r.started_at).toLocaleString()}
                </span>
                <span
                  className={`text-[10px] uppercase px-1.5 py-0.5 rounded border shrink-0 ${STATUS_BADGE[r.status]}`}
                  title={r.status === "failed" && r.error ? r.error : undefined}
                >
                  {r.status}
                </span>
                {r.status === "processing" && r.progress?.fraction != null && (
                  <span className="text-[10px] text-amber-300 tabular-nums shrink-0">
                    {Math.round(r.progress.fraction * 100)}%
                  </span>
                )}
                {editingId === r.id ? (
                  <input
                    autoFocus
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => commitTitle(r.id, r.title)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitTitle(r.id, r.title);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    placeholder={`Recording #${r.id}`}
                    className="min-w-0 flex-shrink bg-neutral-950 border border-neutral-700 rounded px-2 py-0.5 text-sm w-48"
                  />
                ) : (
                  <button
                    onClick={() => {
                      setEditingId(r.id);
                      setEditTitle(r.title ?? "");
                    }}
                    title="Click to rename"
                    className="truncate min-w-0 text-left hover:text-neutral-100"
                  >
                    {r.title || `Recording #${r.id}`}
                  </button>
                )}
                <div className="flex flex-wrap items-center gap-1 flex-1">
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
                <span className="text-xs text-neutral-500 w-12 text-right">{fmtDuration(r.duration_s)}</span>
                {r.status === "failed" && (
                  <button
                    onClick={() => retry(r.id)}
                    className="text-xs px-2 py-1 rounded bg-amber-600/80 hover:bg-amber-500 text-amber-50"
                    title={r.error ?? "Re-run transcription"}
                  >
                    Retry
                  </button>
                )}
                <Link
                  to={r.status === "recording" ? `/recordings/live/${r.id}` : `/recordings/${r.id}`}
                  className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
                >
                  Open
                </Link>
                <button
                  onClick={() => del(r.id)}
                  className="text-xs px-2 py-1 rounded text-neutral-400 hover:text-rose-400"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
