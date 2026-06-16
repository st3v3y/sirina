import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type AudioDevice, type Meeting } from "../lib/api";

type Source = "discord" | "local";

export default function Dashboard() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [source, setSource] = useState<Source>("discord");
  const [title, setTitle] = useState("");
  const [channelId, setChannelId] = useState("");
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [device, setDevice] = useState<string>("");
  const [label, setLabel] = useState("Room");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();

  async function refresh() {
    try {
      setMeetings(await api.listMeetings());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    api.listAudioDevices().then((d) => {
      setDevices(d);
      // Prefer BlackHole if present, otherwise the first device
      const bh = d.find((x) => /blackhole/i.test(x.name));
      setDevice(bh ? bh.name : d[0]?.name ?? "");
    }).catch(() => setDevices([]));
  }, []);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const { meeting_id } = await api.startMeeting(
        source === "discord"
          ? {
              source: "discord",
              title: title || undefined,
              channel_id: channelId || undefined,
            }
          : {
              source: "local",
              title: title || undefined,
              device: device || undefined,
              label: label || undefined,
            }
      );
      nav(`/meetings/live/${meeting_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setStarting(false);
    }
  }

  async function del(id: number) {
    if (!confirm("Delete this meeting and all its data?")) return;
    await api.deleteMeeting(id);
    refresh();
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
        <h2 className="text-base font-medium mb-3">Start a recording</h2>

        <div className="inline-flex rounded border border-neutral-800 bg-neutral-950 p-0.5 mb-3 text-xs">
          {(["discord", "local"] as Source[]).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-3 py-1.5 rounded ${
                source === s ? "bg-neutral-800 text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {s === "discord" ? "Discord (per-speaker)" : "Local audio (single track)"}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <input
            className="bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm flex-1 min-w-[10rem]"
            placeholder="Title (optional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          {source === "discord" ? (
            <input
              className="bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm w-56"
              placeholder="Voice channel ID (optional)"
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
            />
          ) : (
            <>
              <select
                className="bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-sm w-56"
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
              <input
                className="bg-neutral-950 border border-neutral-800 rounded px-3 py-1.5 text-sm w-28"
                placeholder="Label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                title="Shown in the transcript next to each line (e.g. 'Room')"
              />
            </>
          )}

          <button
            onClick={start}
            disabled={starting || (source === "local" && !device)}
            className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 px-4 py-1.5 rounded text-sm font-medium"
          >
            {starting ? "Starting…" : "● Start recording"}
          </button>
        </div>

        {source === "local" && (
          <p className="text-xs text-neutral-500 mt-2">
            Captures audio from this Mac's input device. No per-speaker labels — each line will be tagged with "{label || "Room"}". Use BlackHole or Loopback to route a call's audio into a virtual device.
          </p>
        )}
        {error && <p className="text-rose-400 text-xs mt-2">{error}</p>}
      </section>

      <section>
        <h2 className="text-base font-medium mb-3">Past recordings</h2>
        {meetings.length === 0 ? (
          <p className="text-sm text-neutral-500">No recordings yet.</p>
        ) : (
          <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
            {meetings.map((m) => (
              <li key={m.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <span className="text-neutral-500 text-xs w-40 shrink-0">
                  {new Date(m.started_at).toLocaleString()}
                </span>
                <span
                  className={`text-[10px] uppercase px-1.5 py-0.5 rounded shrink-0 ${
                    m.source === "local"
                      ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                      : "bg-sky-500/15 text-sky-300 border border-sky-500/30"
                  }`}
                >
                  {m.source}
                </span>
                <span className="flex-1 truncate">{m.title || `Meeting #${m.id}`}</span>
                <span className="text-xs text-neutral-500 w-16 text-right">
                  {m.segment_count ?? 0} lines
                </span>
                <Link
                  to={m.status === "recording" ? `/meetings/live/${m.id}` : `/meetings/${m.id}`}
                  className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
                >
                  Open
                </Link>
                <button
                  onClick={() => del(m.id)}
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
