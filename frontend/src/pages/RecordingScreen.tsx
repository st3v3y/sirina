import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type ActiveInfo, type Caption } from "../lib/api";
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

function LiveSwitch({ label, on, disabled, onChange }: { label: string; on: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={`flex items-center gap-2 ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      <input type="checkbox" checked={on} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

const TRACK_LABEL: Record<string, string> = { mic: "You", system: "Others" };

/** Live captions: recent settled lines of both tracks in time order, plus what's being said now. */
function CaptionsPanel({ info }: { info: ActiveInfo }) {
  const tracks = Object.entries(info.captions ?? {});
  const settled: (Caption & { who: string })[] = tracks
    .flatMap(([name, c]) => c.settled.map((x) => ({ ...x, who: TRACK_LABEL[name] ?? name })))
    .sort((a, b) => a.start - b.start)
    .slice(-6);
  const live = tracks
    .filter(([, c]) => c.provisional)
    .map(([name, c]) => ({ ...(c.provisional as Caption), who: TRACK_LABEL[name] ?? name }));
  const failed = tracks.some(([, c]) => c.failed);
  return (
    <div className="w-full max-w-xl rounded-card border border-line-2 bg-surface/70 px-4 py-3 space-y-1 text-[14px] leading-relaxed">
      {settled.length === 0 && live.length === 0 && <p className="text-muted text-[13px]">Listening…</p>}
      {settled.map((c, i) => (
        <p key={`s-${i}-${c.start}`}>
          <span className="font-semibold text-ink-2 mr-1.5">{c.who}:</span>
          {c.text}
        </p>
      ))}
      {live.map((c) => (
        <p key={`p-${c.who}`} className="text-muted">
          <span className="font-semibold mr-1.5">{c.who}:</span>
          {c.text}
        </p>
      ))}
      {failed && <p className="text-[12px] text-warn-deep">Captions stopped (the recording continues).</p>}
    </div>
  );
}

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
  const [info, setInfo] = useState<ActiveInfo | null>(null);
  const [toggling, setToggling] = useState(false);
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
          setInfo(info);
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

  async function setOption(body: { live_transcribe?: boolean; live_captions?: boolean }) {
    setToggling(true);
    try {
      setInfo(await api.updateActiveRecording(body));
    } catch (e) {
      setError(String(e));
    } finally {
      setToggling(false);
    }
  }

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

      {info?.live_captions && <CaptionsPanel info={info} />}

      <div className="flex flex-col items-center gap-1.5">
        <div className="flex items-center gap-5 text-[13px] text-ink-2">
          <LiveSwitch
            label="Transcribe as I go"
            on={Boolean(info?.live_transcribe)}
            disabled={toggling || !info?.live_transcribe_available}
            onChange={(v) => setOption({ live_transcribe: v })}
          />
          <LiveSwitch
            label="Live captions"
            on={Boolean(info?.live_captions)}
            disabled={toggling || !info?.captions_available}
            onChange={(v) => setOption({ live_captions: v })}
          />
        </div>
        {info?.live_transcribe && info.live && (
          <p className="text-[12px] text-muted">
            {info.live.failed
              ? "Live transcription stopped — the rest is done after you stop."
              : info.live.paused === "low_power"
                ? "Paused while Low Power Mode is on — it catches up later."
                : info.live.final_until_s > 0
                  ? `Final transcript ready up to ${fmt(info.live.final_until_s)}`
                  : "The first part turns final after about 4 minutes."}
          </p>
        )}
      </div>

      <button
        onClick={stop}
        disabled={stopping}
        className="flex items-center gap-2.5 h-13 px-7 py-3 rounded-full bg-signal-grad text-white font-semibold shadow-[var(--shadow-rec)] disabled:opacity-50"
      >
        <Icon name="square" size={14} /> {stopping ? "Stopping…" : "Stop recording"}
      </button>

      <p className="max-w-sm text-center text-[13px] leading-relaxed text-muted">
        {info?.live_transcribe
          ? "Audio is being saved and transcribed as you go — after you stop, only the last minutes, speakers and the summary remain."
          : "Audio is being saved to disk. Transcription and the summary run automatically after you stop."}
      </p>
      {error && <p className="text-signal text-xs">{error}</p>}
    </div>
  );
}
