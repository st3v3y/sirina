import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type AudioDevice, type Recording, type RecordingStatus } from "../lib/api";

const STATUS_BADGE: Record<RecordingStatus, string> = {
  recording: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  processing: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed: "bg-neutral-700/40 text-neutral-300 border-neutral-600",
};

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
  const [label, setLabel] = useState("Room");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();

  async function refresh() {
    try {
      setRecordings(await api.listRecordings());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    api
      .listAudioDevices()
      .then((d) => {
        setDevices(d);
        const mic = d.find((x) => /microphone|mic/i.test(x.name)) ?? d[0];
        setDevice(mic?.name ?? "");
      })
      .catch(() => setDevices([]));
  }, []);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const { id } = await api.startRecording({
        title: title || undefined,
        device: device || undefined,
        system_device: systemDevice || undefined,
        label: label || undefined,
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
          <input
            className="bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm w-28"
            placeholder="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            title="Shown in the transcript next to each line (e.g. 'Room')"
          />
          <button
            onClick={start}
            disabled={starting || !device}
            className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 px-4 py-1.5 rounded text-sm font-medium"
          >
            {starting ? "Starting…" : "● Start recording"}
          </button>
        </div>

        <div className="flex flex-wrap gap-2 items-center mt-2 text-sm">
          <label className="text-xs text-neutral-500 w-20">Microphone</label>
          <select
            className="bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm flex-1 min-w-[12rem]"
            value={device}
            onChange={(e) => setDevice(e.target.value)}
          >
            {devices.length === 0 && <option value="">No input devices found</option>}
            {devices.map((d) => (
              <option key={d.index} value={d.name}>
                {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-2 items-center mt-2 text-sm">
          <label className="text-xs text-neutral-500 w-20">System audio</label>
          <select
            className="bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm flex-1 min-w-[12rem]"
            value={systemDevice}
            onChange={(e) => setSystemDevice(e.target.value)}
          >
            <option value="">None (mic only)</option>
            {devices.map((d) => (
              <option key={d.index} value={d.name}>
                {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
              </option>
            ))}
          </select>
        </div>

        <p className="text-xs text-neutral-500 mt-2">
          Records to disk only — transcription and the AI summary run after you stop. Pick a
          system-audio device (e.g. BlackHole) to also capture a call as a second track.
        </p>
        {error && <p className="text-rose-400 text-xs mt-2">{error}</p>}
      </section>

      <section>
        <h2 className="text-base font-medium mb-3">Recordings</h2>
        {recordings.length === 0 ? (
          <p className="text-sm text-neutral-500">No recordings yet.</p>
        ) : (
          <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
            {recordings.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <span className="text-neutral-500 text-xs w-40 shrink-0">
                  {new Date(r.started_at).toLocaleString()}
                </span>
                <span
                  className={`text-[10px] uppercase px-1.5 py-0.5 rounded border shrink-0 ${STATUS_BADGE[r.status]}`}
                >
                  {r.status}
                </span>
                <span className="flex-1 truncate">{r.title || `Recording #${r.id}`}</span>
                <span className="text-xs text-neutral-500 w-12 text-right">{fmtDuration(r.duration_s)}</span>
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
