import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";

function fmt(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const ss = (s % 60).toString().padStart(2, "0");
  const hh = Math.floor(m / 60);
  const mm = (m % 60).toString().padStart(2, "0");
  return hh > 0 ? `${hh}:${mm}:${ss}` : `${m}:${ss}`;
}

export default function RecordingScreen() {
  const { id } = useParams();
  const recordingId = Number(id);
  const nav = useNavigate();
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missesRef = useRef(0);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const info = await api.activeRecording();
        if (!alive) return;
        if (info && info.id === recordingId) {
          setElapsed(info.elapsed_s);
          setLevel(info.level);
          missesRef.current = 0;
        } else {
          // No active recording for this id — it was stopped elsewhere.
          missesRef.current += 1;
          if (missesRef.current > 2) nav(`/recordings/${recordingId}`);
        }
      } catch {
        /* ignore transient poll errors */
      }
    };
    poll();
    const t = setInterval(poll, 250);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [recordingId, nav]);

  async function stop() {
    setStopping(true);
    setError(null);
    try {
      await api.stopRecording(recordingId);
      nav(`/recordings/${recordingId}`);
    } catch (e) {
      setError(String(e));
      setStopping(false);
    }
  }

  const pct = Math.min(100, Math.round(level * 140));

  return (
    <div className="h-full flex flex-col items-center justify-center gap-8 p-6">
      <div className="flex items-center gap-2 text-rose-400 text-sm">
        <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" /> Recording
      </div>

      <div className="text-6xl font-mono tabular-nums tracking-tight">{fmt(elapsed)}</div>

      <div className="w-72">
        <div className="h-3 rounded-full bg-neutral-800 overflow-hidden">
          <div
            className="h-full bg-emerald-500 transition-[width] duration-75"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="text-center text-xs text-neutral-500 mt-2">input level</div>
      </div>

      <button
        onClick={stop}
        disabled={stopping}
        className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 px-6 py-2.5 rounded-full text-sm font-medium"
      >
        {stopping ? "Stopping…" : "■ Stop recording"}
      </button>

      <p className="text-xs text-neutral-500 max-w-sm text-center">
        Audio is being saved to disk. Transcription and the summary run after you stop.
      </p>
      {error && <p className="text-rose-400 text-xs">{error}</p>}
    </div>
  );
}
