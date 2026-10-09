import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api, type Status, type Tag } from "../lib/api";
import { useRecorder } from "../lib/useRecorder";
import { confirmDialog } from "../lib/confirm";
import { TAG_COLORS, catColor } from "../lib/tagColors";
import { ShellContext } from "../lib/shell";
import { Icon } from "./Icon";
import {
  getThemeChoice,
  setThemeChoice,
  subscribeTheme,
  type ThemeChoice,
} from "../theme";
import mark from "../assets/sirina-mark.svg";

function fmtTimer(s: number) {
  const sec = Math.max(0, Math.floor(s));
  const m = Math.floor(sec / 60);
  const ss = (sec % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
}

const NAV = [
  { to: "/", label: "Recordings", icon: "clock", end: true },
  { to: "/ask", label: "Ask", icon: "message-circle", end: false },
  { to: "/people", label: "People", icon: "users", end: false },
  { to: "/templates", label: "Templates", icon: "file-text", end: false },
];

export default function Shell({ children }: { children: ReactNode }) {
  const nav = useNavigate();
  const rec = useRecorder();

  const [tags, setTags] = useState<Tag[]>([]);
  const [filterTag, setFilterTag] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [editingTag, setEditingTag] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("neutral");

  const reloadTags = async () => setTags(await api.listTags());
  useEffect(() => {
    api.listTags().then(setTags).catch(() => {});
  }, []);

  async function createTag() {
    const name = newTag.trim();
    if (!name) {
      setAdding(false);
      return;
    }
    await api.createTag(name, TAG_COLORS[tags.length % TAG_COLORS.length]);
    setNewTag("");
    setAdding(false);
    reloadTags();
  }
  function startEdit(t: Tag) {
    setEditingTag(t.id);
    setEditName(t.name);
    setEditColor(t.color ?? "neutral");
  }
  async function commitEdit(t: Tag) {
    const name = editName.trim();
    const body: { name?: string; color?: string } = {};
    if (name && name !== t.name) body.name = name;
    if (editColor !== (t.color ?? "neutral")) body.color = editColor;
    if (Object.keys(body).length) {
      await api.updateTag(t.id, body);
      await reloadTags();
    }
    setEditingTag(null);
  }
  async function deleteTag(t: Tag) {
    if (!(await confirmDialog(`Delete tag "${t.name}"?`))) return;
    await api.deleteTag(t.id);
    if (filterTag === t.id) setFilterTag(null);
    setEditingTag(null);
    reloadTags();
  }

  const navItem = ({ to, label, icon, end }: (typeof NAV)[number]) => (
    <NavLink
      key={to}
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] text-sm ${
          isActive
            ? "bg-surface text-ink font-semibold shadow-card border border-line-2"
            : "text-ink-2 hover:text-ink"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <Icon name={icon} size={17} className={isActive ? "text-signal" : ""} />
          {label}
        </>
      )}
    </NavLink>
  );

  const deviceLabel = rec.nativeAudio
    ? `${rec.device || "No mic"} · System audio`
    : `${rec.device || "No mic"}${rec.systemDevice ? ` · ${rec.systemDevice}` : ""}`;

  return (
    <ShellContext.Provider value={{ tags, reloadTags, filterTag, setFilterTag }}>
      <div className="flex h-screen overflow-hidden text-ink">
        <aside className="w-[252px] shrink-0 bg-sidebar border-r border-line flex flex-col px-3.5 py-[18px] overflow-y-auto">
          {/* logo */}
          <div className="flex items-center gap-2.5 px-2 pb-5">
            <img src={mark} alt="Sirina" className="app-logo w-9 h-9" />
            <span className="font-serif text-xl font-semibold tracking-tight">Sirina</span>
          </div>

          {/* record / live */}
          {rec.active ? (
            <button
              onClick={() => nav(`/recordings/live/${rec.active!.id}`)}
              className="bg-signal-grad text-white h-12 rounded-[12px] flex items-center gap-2.5 px-4 mb-2 shadow-[var(--shadow-rec)]"
            >
              <span className="w-2.5 h-2.5 rounded-full bg-white animate-recpulse" />
              <span className="text-sm font-semibold flex-1 text-left">Recording</span>
              <span className="font-mono text-[13px] tabular-nums opacity-90">
                {fmtTimer(rec.active.elapsed_s)}
              </span>
            </button>
          ) : (
            <button
              onClick={rec.openPicker}
              className="bg-signal-grad text-white h-12 rounded-[12px] flex items-center justify-center gap-2.5 mb-2 text-[15px] font-semibold shadow-[var(--shadow-rec)]"
            >
              <span className="w-3 h-3 rounded-full bg-white shadow-[0_0_0_3px_rgba(255,255,255,0.28)]" />
              Record
            </button>
          )}
          <button
            onClick={rec.openPicker}
            className="flex items-center justify-center gap-1.5 text-[11.5px] text-muted mb-6 hover:text-ink-2"
          >
            <Icon name="mic" size={11} />
            <span className="truncate max-w-[180px]">{deviceLabel}</span>
            <Icon name="chevron-down" size={10} />
          </button>

          {/* nav */}
          <nav className="flex flex-col gap-0.5">{NAV.map(navItem)}</nav>

          {/* tags */}
          <div className="mt-6 px-1">
            <div className="flex items-center justify-between mb-3 px-2">
              <span className="text-[11px] uppercase tracking-wider text-label">Tags</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <button
                onClick={() => {
                  setFilterTag(null);
                  nav("/");
                }}
                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13.5px] ${
                  filterTag == null ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:text-ink"
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-muted/40" />
                <span className="flex-1 text-left">All recordings</span>
              </button>
              {tags.map((t) => {
                const selected = filterTag === t.id;
                const editing = editingTag === t.id;
                return (
                  <div
                    key={t.id}
                    className={`flex items-center gap-2 px-2.5 py-2 rounded-lg text-[13.5px] ${
                      selected || editing ? "bg-surface text-ink shadow-card" : "text-ink-2"
                    }`}
                  >
                    {editing ? (
                      <>
                        <select
                          value={editColor}
                          onChange={(e) => setEditColor(e.target.value)}
                          title="Colour"
                          className="bg-paper border border-line rounded px-1 py-0.5 text-[11px] shrink-0"
                          style={{ color: catColor(editColor) }}
                        >
                          {TAG_COLORS.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                        <input
                          autoFocus
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") commitEdit(t);
                            if (e.key === "Escape") setEditingTag(null);
                          }}
                          className="flex-1 min-w-0 bg-paper border border-line rounded px-1.5 py-0.5 text-xs"
                        />
                        <button onClick={() => commitEdit(t)} title="Save" className="text-ok-deep hover:opacity-70 shrink-0">
                          <Icon name="check" size={15} />
                        </button>
                      </>
                    ) : (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: catColor(t.color) }} />
                        <button
                          onClick={() => {
                            setFilterTag(t.id);
                            nav("/");
                          }}
                          className="flex-1 text-left truncate hover:text-ink"
                        >
                          {t.name}
                        </button>
                        {selected && (
                          <>
                            <button onClick={() => startEdit(t)} title="Edit tag" className="text-muted hover:text-ink-2 shrink-0">
                              <Icon name="pencil" size={12} />
                            </button>
                            <button onClick={() => deleteTag(t)} title="Delete tag" className="text-muted hover:text-signal shrink-0">
                              <Icon name="trash-2" size={12} />
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
              {adding ? (
                <div className="flex items-center gap-2 px-2.5 py-1.5">
                  <span className="w-2.5 h-2.5 rounded-full border border-dashed border-line-3 shrink-0" />
                  <input
                    autoFocus
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") createTag();
                      if (e.key === "Escape") {
                        setAdding(false);
                        setNewTag("");
                      }
                    }}
                    placeholder="New tag…"
                    className="flex-1 min-w-0 bg-paper border border-line rounded px-1.5 py-0.5 text-xs"
                  />
                  <button onClick={createTag} title="Add tag" className="text-ok-deep hover:opacity-70 shrink-0">
                    <Icon name="check" size={15} />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setAdding(true)}
                  className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-muted hover:text-ink-2"
                >
                  <span className="w-2.5 h-2.5 rounded-full border border-dashed border-line-3" />
                  New tag
                </button>
              )}
            </div>
          </div>

          <div className="flex-1" />

          {/* settings + theme + status */}
          {navItem({ to: "/settings", label: "Settings", icon: "settings", end: false })}
          <div className="flex items-center justify-between border-t border-line mt-2 pt-2.5 px-2">
            <StatusFooter />
            <ThemeToggle />
          </div>
        </aside>

        <main className="flex-1 min-w-0 overflow-y-auto bg-paper">{children}</main>
      </div>

      {rec.picking && <DeviceModal rec={rec} />}
    </ShellContext.Provider>
  );
}

function StatusFooter() {
  const [status, setStatus] = useState<Status | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.status();
        if (!alive) return;
        setStatus(s);
        if (s.whisper_state === "loading") setTimeout(tick, 3000); // poll until ready/failed
      } catch {
        if (alive) setTimeout(tick, 3000);
      }
    };
    tick();
    return () => {
      alive = false;
    };
  }, [nonce]);

  if (status?.whisper_state === "failed") {
    return (
      <span className="flex items-center gap-2 text-xs text-signal" title={status.whisper_error ?? undefined}>
        <span className="w-[7px] h-[7px] rounded-full bg-signal" />
        Whisper failed
        <button
          onClick={async () => {
            await api.reloadEngine().catch(() => {});
            setNonce((n) => n + 1);
          }}
          className="underline hover:text-ink-2"
        >
          retry
        </button>
      </span>
    );
  }
  const ready = status?.whisper_state === "ready";
  return (
    <span className="flex items-center gap-2 text-xs text-muted">
      <span
        className={`w-[7px] h-[7px] rounded-full ${ready ? "bg-ok" : "bg-warn"}`}
        style={{ boxShadow: ready ? "0 0 0 3px rgba(74,140,95,0.16)" : undefined }}
      />
      {status ? (ready ? `Local · ${status.engine} ready` : "Local · loading…") : "Connecting…"}
    </span>
  );
}

function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(getThemeChoice());
  useEffect(() => subscribeTheme(() => setChoice(getThemeChoice())), []);
  const opts: { c: ThemeChoice; icon: string }[] = [
    { c: "auto", icon: "monitor" },
    { c: "light", icon: "sun" },
    { c: "dark", icon: "moon" },
  ];
  return (
    <span className="flex items-center gap-0.5">
      {opts.map(({ c, icon }) => (
        <button
          key={c}
          onClick={() => setThemeChoice(c)}
          title={c}
          className={`p-1 rounded ${choice === c ? "text-signal bg-surface" : "text-muted hover:text-ink-2"}`}
        >
          <Icon name={icon} size={13} />
        </button>
      ))}
    </span>
  );
}

function OptionRow({
  label, hint, checked, disabled, onChange,
}: { label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={`flex items-start gap-2.5 ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked && !disabled}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm text-ink">{label}</span>
        <span className="block text-xs text-muted">{hint}</span>
      </span>
    </label>
  );
}

function DeviceModal({ rec }: { rec: ReturnType<typeof useRecorder> }) {
  const field =
    "w-full bg-paper border border-line rounded-field px-2 py-1.5 text-sm focus:outline-none focus:border-line-3";
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-30">
      <div className="bg-surface border border-line rounded-card max-w-md w-full p-5 space-y-4 shadow-pop">
        <h3 className="text-sm font-semibold">Start a recording</h3>
        <div>
          <label className="block text-xs text-muted mb-1">Title (optional)</label>
          <input
            className={field}
            placeholder="e.g. Acme Corp — Discovery call"
            value={rec.title}
            onChange={(e) => rec.setTitle(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-muted mb-1">Microphone</label>
          <select className={field} value={rec.device} onChange={(e) => rec.setDevice(e.target.value)}>
            <option value="">None</option>
            {rec.devices.map((d) => (
              <option key={`m-${d.index}`} value={d.name}>
                {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
              </option>
            ))}
          </select>
        </div>
        {rec.nativeAudio ? (
          <p className="text-xs text-ok-deep bg-ok/10 border border-ok/20 rounded-field px-2 py-1.5">
            System audio (other participants) is captured automatically — no extra device needed.
          </p>
        ) : (
          <div>
            <label className="block text-xs text-muted mb-1">System audio</label>
            <select
              className={field}
              value={rec.systemDevice}
              onChange={(e) => rec.setSystemDevice(e.target.value)}
            >
              <option value="">None</option>
              {rec.devices.map((d) => (
                <option key={`s-${d.index}`} value={d.name}>
                  {d.name} ({d.channels}ch · {Math.round(d.default_samplerate)} Hz)
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="space-y-2 border-t border-line-2 pt-3">
          <OptionRow
            label="Transcribe during recording"
            hint={
              rec.caps?.live_transcribe_available
                ? "Transcript is ready about a minute after the call. Uses the Neural Engine, barely any CPU."
                : "Needs the WhisperKit engine (Apple Silicon)."
            }
            checked={rec.liveTranscribe}
            disabled={!rec.caps?.live_transcribe_available}
            onChange={rec.setLiveTranscribe}
          />
          <OptionRow
            label="Live captions"
            hint={
              rec.caps?.captions_available
                ? "Shows what's said as it's said (on-device, ~2.5% of one CPU core)."
                : "Needs macOS 26 or newer."
            }
            checked={rec.liveCaptions}
            disabled={!rec.caps?.captions_available}
            onChange={rec.setLiveCaptions}
          />
          <p className="text-[11px] text-label">For this recording only — defaults are in Settings.</p>
        </div>
        {rec.error && <p className="text-signal text-xs">{rec.error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={rec.closePicker}
            disabled={rec.starting}
            className="text-sm px-3 py-1.5 rounded-field border border-line text-ink-2 hover:bg-surface-2"
          >
            Cancel
          </button>
          <button
            onClick={rec.confirmStart}
            disabled={rec.starting || (!rec.device && !rec.nativeAudio && !rec.systemDevice)}
            className="text-sm px-4 py-1.5 rounded-field bg-signal-grad text-white font-semibold disabled:opacity-50"
          >
            {rec.starting ? "Starting…" : "Record"}
          </button>
        </div>
      </div>
    </div>
  );
}
