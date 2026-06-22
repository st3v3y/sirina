import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Icon } from "../components/Icon";

function fmt(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const ss = (s % 60).toString().padStart(2, "0");
  const hh = Math.floor(m / 60);
  const mm = (m % 60).toString().padStart(2, "0");
  return hh > 0 ? `${hh}:${mm}:${ss}` : `${m}:${ss}`;
}

const BARS = 24;

export default function RecordingScreen() {
  const { id } = useParams();
  const recordingId = Number(id);
  const nav = useNavigate();
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [systemLevel, setSystemLevel] = useState(0);
  const [micHealthy, setMicHealthy] = useState(true);
  const [systemHealthy, setSystemHealthy] = useState<boolean | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missesRef = useRef(0);

  useEffect(() => {
    api.getRecording(recordingId).then((r) => setTitle(r.title)).catch(() => {});
  }, [recordingId]);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const info = await api.activeRecording();
        if (!alive) return;
        if (info && info.id === recordingId) {
          setElapsed(info.elapsed_s);
          setLevel(info.level);
          setMicLevel(info.mic_level ?? 0);
          setSystemLevel(info.system_level ?? 0);
          setMicHealthy(info.mic_healthy ?? true);
          setSystemHealthy(info.system_healthy ?? null);
          missesRef.current = 0;
        } else {
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

  const micPct = Math.min(100, Math.round(micLevel * 140));
  const systemPct = Math.min(100, Math.round(systemLevel * 140));
  const hasSystem = systemHealthy !== null || systemLevel > 0;
  const trackWarning = systemHealthy === false
    ? "System audio stopped — trying to reconnect. The other side may not be recorded."
    : !micHealthy
    ? "Microphone stopped delivering audio — check your input device."
    : null;

  return (
    <div
      className="h-full flex flex-col items-center justify-center gap-8 p-6"
      style={{
        background:
          "radial-gradient(circle at 50% 36%, rgba(214,73,47,0.07), transparent 58%)",
      }}
    >
      <div className="flex flex-col items-center gap-3.5">
        <span className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-signal/10 text-signal text-xs font-semibold uppercase tracking-wider">
          <span className="w-2.5 h-2.5 rounded-full bg-signal animate-recpulse" /> Recording
        </span>
        {title && <div className="font-serif text-xl text-ink-2">{title}</div>}
      </div>

      <div
        className="font-mono tabular-nums text-ink leading-none"
        style={{ fontSize: "88px", letterSpacing: "-0.02em" }}
      >
        {fmt(elapsed)}
      </div>

      <div className="flex flex-col items-center gap-3">
        <div className="flex items-end gap-1 h-[60px]">
          {Array.from({ length: BARS }).map((_, i) => {
            // Drive bar heights from the live level with a stable per-bar variation.
            const wobble = 0.45 + 0.55 * Math.abs(Math.sin((i + 1) * 1.7));
            const h = Math.max(8, Math.min(100, level * 140 * wobble));
            return (
              <div
                key={i}
                className="w-1 rounded-full bg-signal/70 transition-[height] duration-100"
                style={{ height: `${h}%` }}
              />
            );
          })}
        </div>
        <div className="flex flex-col gap-2 w-[300px]">
          <div className="flex items-center gap-3">
            <span className="w-12 text-[10px] uppercase tracking-wider text-muted text-right">Mic</span>
            <div className="flex-1 h-[7px] rounded-full bg-line-2 overflow-hidden">
              <div className="h-full bg-signal-grad transition-[width] duration-75" style={{ width: `${micPct}%` }} />
            </div>
          </div>
          {hasSystem && (
            <div className="flex items-center gap-3">
              <span className="w-12 text-[10px] uppercase tracking-wider text-muted text-right">System</span>
              <div className="flex-1 h-[7px] rounded-full bg-line-2 overflow-hidden">
                <div className="h-full bg-signal-grad transition-[width] duration-75" style={{ width: `${systemPct}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>

      {trackWarning && (
        <div className="flex items-center gap-2 px-4 py-2 rounded-field bg-warn/10 border border-warn/30 text-warn-deep text-[13px] max-w-md text-center">
          <span className="w-2 h-2 rounded-full bg-warn animate-recpulse shrink-0" />
          {trackWarning}
        </div>
      )}

      <button
        onClick={stop}
        disabled={stopping}
        className="flex items-center gap-2.5 h-13 px-7 py-3 rounded-full bg-signal-grad text-white font-semibold shadow-[var(--shadow-rec)] disabled:opacity-50"
      >
        <Icon name="square" size={14} /> {stopping ? "Stopping…" : "Stop recording"}
      </button>

      <p className="max-w-sm text-center text-[13px] leading-relaxed text-muted">
        Audio is being saved to disk. Transcription and the summary run automatically after you stop.
      </p>
      {error && <p className="text-signal text-xs">{error}</p>}
    </div>
  );
}
