import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  api,
  type LlmProvider,
  type Platform,
  type SettingField,
  type SettingSection,
  type SettingsResponse,
  type Status,
} from "../lib/api";
import { Icon } from "../components/Icon";
import { SpeechModelsCard } from "../components/SpeechModels";
import { Badge, Button, Card, FieldRow, Select, Slider, Stepper, Toggle } from "../components/ui";

type SectionMeta = {
  id: SettingSection;
  title: string;
  icon: string;
  tint: string; // CSS color
  badge: { tone: "ok" | "warn" | "neutral"; label: string };
  desc: string;
};

const SECTIONS: SectionMeta[] = [
  { id: "ai", title: "AI model", icon: "sparkles", tint: "var(--color-signal)", badge: { tone: "ok", label: "Applies instantly" }, desc: "Used for summaries and the Ask assistant." },
  { id: "transcription", title: "Transcription", icon: "audio-lines", tint: "var(--color-cat-sky)", badge: { tone: "warn", label: "Restart required" }, desc: "Engine & model changes reload after restart." },
  { id: "diarization", title: "Speaker splitting", icon: "users", tint: "var(--color-cat-teal)", badge: { tone: "ok", label: "Applies instantly" }, desc: "Separate & label who spoke, on this computer. Off by default." },
  { id: "advanced", title: "Advanced", icon: "settings", tint: "var(--color-cat-amber)", badge: { tone: "neutral", label: "Mixed" }, desc: "Performance tuning & local storage." },
];

const INPUT =
  "h-[38px] min-w-[230px] px-3 border border-line rounded-field bg-surface text-[13.5px] text-ink focus:outline-none focus:border-line-3";

// Plain-language explanations shown via a (?) tooltip next to a field — aimed at users
// who don't know the underlying ML knobs. Keyed by setting key (see settings_store.FIELDS).
const HELP_HINTS: Record<string, string> = {
  transcription_engine:
    "How transcription runs. On Apple Silicon Macs, “WhisperKit” runs the large-v3-turbo model on the Neural Engine: fast, light on memory and battery. “faster-whisper” uses the CPU (slower, uses much more memory) and works everywhere. “Auto” picks the best engine this computer has — leave it on Auto if unsure. Changing this needs a reload.",
  whisper_model:
    "The CPU engine’s model (faster-whisper only; WhisperKit always uses large-v3-turbo). Bigger models (medium, large) are more accurate but slower and use more memory; smaller ones (tiny, small) are faster. “medium” is a good balance; pick “large-v3” for best accuracy.",
  whisper_compute_type:
    "A speed/accuracy trade-off for the CPU engine (faster-whisper only). “int8” is fastest and lightest; “float16”/“float32” are slightly more accurate but slower. “int8” is fine for most people.",
  whisper_beam_size:
    "How many wording alternatives the model weighs before choosing. 1 is fastest (greedy); higher (e.g. 5) can be a little more accurate but slower. Leave at 1 unless you want to chase accuracy.",
  whisper_initial_prompt:
    "Names, jargon, or product terms the model tends to mishear — list a few so it spells them right (e.g. “Sirina, BlackHole, pyannote”). Keep it short: long lists can make it repeat words.",
  whisper_cpu_threads:
    "How many CPU cores transcription may use (faster-whisper only). 0 = one per performance core (recommended; the slower efficiency cores would hold the others back). Lower it only if you want to keep the computer responsive for other work.",
  transcribe_chunk_seconds:
    "Audio is finalized in windows of about this many seconds (cut at a pause), so the transcript turns final step by step and memory stays bounded. 180 (3 min) is a good default; 0 = one window for the whole recording.",
  silence_peak_threshold:
    "Audio quieter than this (0–1) is treated as silent and skipped, so the model doesn’t invent captions over silence (e.g. an empty system-audio track). 0.005 works well; 0 disables the check.",
  diarization_enabled:
    "Splits the other participants’ audio into separate speakers (Speaker 1, Speaker 2, …) so you can tell who said what. Runs on-device; the small speaker model (~60 MB) downloads the first time. Adds about a minute per 2 hours of audio.",
  diarization_timing:
    "“after_stop” splits speakers once, when the recording ends (about a minute for 2 hours). “during_recording” also does it roughly every 10 minutes while you record, so names show up sooner, at a small extra load during the call.",
};

const REVEAL_LABEL: Record<Platform, string> = {
  macos: "Open in Finder",
  windows: "Show in Explorer",
  linux: "Open folder",
};

function HelpTip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex shrink-0">
      <Icon name="circle-question-mark" size={13} className="text-muted hover:text-ink-2 cursor-help" />
      <span className="pointer-events-none absolute left-0 top-5 z-30 hidden group-hover:block w-64 rounded-lg bg-ink text-paper text-[12px] leading-snug px-3 py-2 shadow-pop normal-case font-normal tracking-normal">
        {text}
      </span>
    </span>
  );
}

export default function Settings() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [original, setOriginal] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadRequired, setReloadRequired] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [reloadMsg, setReloadMsg] = useState<string | null>(null);

  function hydrate(res: SettingsResponse) {
    const v: Record<string, unknown> = {};
    for (const f of res.fields) if (!f.secret) v[f.key] = f.value;
    setData(res);
    setValues(v);
    setOriginal(v);
    setSecrets({});
    setReloadRequired(res.reload_required);
  }

  async function refreshStatus() {
    api.status().then(setStatus).catch(() => setStatus(null));
  }

  useEffect(() => {
    api.getSettings().then(hydrate).catch((e) => setError(String(e)));
    refreshStatus();
  }, []);

  const dirty = useMemo(() => {
    if (!data) return false;
    const nonSecretChanged = Object.keys(values).some(
      (k) => JSON.stringify(values[k]) !== JSON.stringify(original[k])
    );
    return nonSecretChanged || Object.values(secrets).some((s) => s !== "");
  }, [data, values, original, secrets]);

  function optionsFor(f: SettingField): string[] | null {
    let opts = f.options ?? null;
    if (opts) {
      const cur = String(values[f.key] ?? "");
      if (cur && !opts.includes(cur)) opts = [cur, ...opts];
    }
    return opts;
  }

  async function save() {
    if (!data) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updates: Record<string, unknown> = {};
      for (const f of data.fields) {
        if (f.secret) {
          if (secrets[f.key]) updates[f.key] = secrets[f.key];
        } else if (JSON.stringify(values[f.key]) !== JSON.stringify(original[f.key])) {
          updates[f.key] = values[f.key];
        }
      }
      const res = await api.updateSettings(updates);
      hydrate(res);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
      refreshStatus();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function reload() {
    setReloading(true);
    setReloadMsg(null);
    try {
      const res = await api.reloadEngine();
      if (res.busy) {
        setReloadMsg(res.detail ?? "Busy — try again when processing finishes.");
      } else {
        setReloadRequired(false);
        setReloadMsg(`Engine reloaded (${res.engine ?? "ok"}).`);
        setTimeout(() => setReloadMsg(null), 2500);
        refreshStatus();
      }
    } catch (e) {
      setReloadMsg(String(e));
    } finally {
      setReloading(false);
    }
  }

  async function reveal() {
    try {
      await api.revealDataDir();
    } catch (e) {
      setError(String(e));
    }
  }

  if (!data) {
    return <div className="p-7 text-sm text-muted">{error ?? "Loading settings…"}</div>;
  }

  const setValue = (k: string, v: unknown) => setValues((s) => ({ ...s, [k]: v }));

  // When to split speakers only matters once diarization is enabled.
  const diarOn = Boolean(values.diarization_enabled);
  const fieldVisible = (f: SettingField) =>
    !(f.section === "diarization" && f.key === "diarization_timing" && !diarOn);

  function control(f: SettingField): ReactNode {
    if (f.secret) {
      const typed = (secrets[f.key] ?? "").length > 0;
      return (
        <div className="flex items-center gap-2">
          <input
            type="password"
            className={INPUT}
            value={secrets[f.key] ?? ""}
            placeholder={f.is_set ? "•••••••• (set — blank keeps it)" : "not set"}
            onChange={(e) => setSecrets((s) => ({ ...s, [f.key]: e.target.value }))}
          />
          {f.is_set && !typed ? (
            <Badge tone="ok">Set</Badge>
          ) : (
            !typed && <Badge tone="warn">Not set</Badge>
          )}
        </div>
      );
    }
    if (f.type === "bool") {
      return <Toggle checked={Boolean(values[f.key])} onChange={(v) => setValue(f.key, v)} />;
    }
    const opts = optionsFor(f);
    if (opts) {
      return (
        <Select value={String(values[f.key] ?? "")} onChange={(v) => setValue(f.key, v)}>
          {opts.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Select>
      );
    }
    if (f.type === "int") {
      return (
        <Stepper
          value={values[f.key] === "" || values[f.key] == null ? "" : Number(values[f.key])}
          onChange={(v) => setValue(f.key, v)}
        />
      );
    }
    if (f.type === "float") {
      const n = Number(values[f.key] ?? 0);
      return (
        <div className="flex items-center gap-3">
          <Slider value={n} onChange={(v) => setValue(f.key, v)} />
          <span className="w-14 text-right text-[13px] font-mono text-ink-2">{n}</span>
        </div>
      );
    }
    if (f.type === "text") {
      return (
        <textarea
          className={`${INPUT} min-w-[300px] h-16 py-2 font-mono text-xs`}
          value={String(values[f.key] ?? "")}
          onChange={(e) => setValue(f.key, e.target.value)}
        />
      );
    }
    return (
      <input
        type="text"
        className={INPUT}
        value={String(values[f.key] ?? "")}
        onChange={(e) => setValue(f.key, e.target.value)}
      />
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3.5 px-7 h-16 border-b border-line-2 shrink-0">
        <h1 className="font-serif text-xl font-semibold">Settings</h1>
        <div className="flex-1" />
        {saved && <span className="text-xs text-ok-deep">Saved</span>}
        <Button variant="primary" onClick={save} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-7 py-7">
        <div className="max-w-[840px] mx-auto space-y-[18px]">
          {error && (
            <div className="rounded-field border border-signal/40 bg-signal/5 px-3 py-2 text-sm text-signal">
              {error}
            </div>
          )}

          {SECTIONS.map((sec) => {
            const fields = data.fields.filter((f) => f.section === sec.id);
            if (!fields.length) return null;
            return (
              <Card key={sec.id} className="p-6">
                {/* header */}
                <div className="flex items-start gap-3 mb-4">
                  <span
                    className="w-8 h-8 shrink-0 rounded-[9px] flex items-center justify-center"
                    style={{ background: `color-mix(in srgb, ${sec.tint} 12%, transparent)`, color: sec.tint }}
                  >
                    <Icon name={sec.icon} size={16} />
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2.5">
                      <span className="text-base font-bold">{sec.title}</span>
                      <Badge tone={sec.badge.tone}>{sec.badge.label}</Badge>
                    </div>
                    <div className="text-xs text-muted mt-0.5">{sec.desc}</div>
                  </div>
                </div>

                {sec.id === "diarization" && !data.diarization_supported && (
                  <p className="text-xs text-warn-deep bg-warn/10 border border-warn/20 rounded-field px-3 py-2 mb-2">
                    {data.diarization_reason ?? "Speaker separation isn't available here."} These settings are
                    saved but won't take effect.
                  </p>
                )}

                {sec.id === "ai" ? (
                  <AiSection
                    values={values}
                    setValue={setValue}
                    secrets={secrets}
                    setSecret={(k, v) => setSecrets((s) => ({ ...s, [k]: v }))}
                    apiKeyIsSet={Boolean(data.fields.find((f) => f.key === "llm_api_key")?.is_set)}
                  />
                ) : (
                  <div>
                    {fields.filter(fieldVisible).map((f) => (
                      <FieldRow
                        key={f.key}
                        label={
                          <span className="flex items-center gap-2">
                            {f.label}
                            {HELP_HINTS[f.key] && <HelpTip text={HELP_HINTS[f.key]} />}
                            {f.restart !== "none" && <Badge tone="warn">reload</Badge>}
                          </span>
                        }
                        help={f.help ?? undefined}
                      >
                        {control(f)}
                      </FieldRow>
                    ))}
                    {sec.id === "advanced" && (
                      <FieldRow label="Data folder" help={data.data_dir}>
                        <Button onClick={reveal}>{REVEAL_LABEL[status?.platform ?? "macos"]}</Button>
                      </FieldRow>
                    )}
                  </div>
                )}

                {sec.id === "transcription" && (
                  <>
                    <div className="flex items-center gap-3 pt-4 border-t border-line-2 mt-1">
                      <Button
                        variant={reloadRequired ? "primary" : "secondary"}
                        onClick={reload}
                        disabled={reloading}
                      >
                        {reloading ? "Reloading…" : "Reload transcription engine"}
                      </Button>
                      {reloadRequired && (
                        <span className="text-xs text-warn-deep">A change needs a reload to take effect.</span>
                      )}
                      {reloadMsg && <span className="text-xs text-muted">{reloadMsg}</span>}
                    </div>
                    {status && (
                      <p className="text-xs text-muted mt-2">
                        Active engine: <span className="font-mono text-ink-2">{status.engine}</span>
                        {status.engine_note && (
                          <span className="text-warn-deep"> · {status.engine_note}</span>
                        )}
                      </p>
                    )}
                  </>
                )}
              </Card>
            );
          })}

          <SpeechModelsCard />

          {/* Status (read-only) */}
          <Card className="p-6 bg-surface-2">
            <div className="flex items-start gap-3 mb-3">
              <span className="w-8 h-8 shrink-0 rounded-[9px] flex items-center justify-center bg-surface border border-line-2 text-ink-2">
                <Icon name="circle-check" size={16} />
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="text-base font-bold">Status</span>
                  <Badge tone="neutral">Read-only</Badge>
                </div>
                <div className="text-xs text-muted mt-0.5">Live runtime health.</div>
              </div>
            </div>
            <StatusRow ok={status?.whisper_loaded} label="Transcription engine" value={`${status?.engine ?? "—"}${status?.whisper_loaded ? " · loaded" : " · loading"}`} />
            <StatusRow ok={status?.llm_ok} label="AI provider" value={`${status?.llm_provider ?? "—"}${status?.llm_ok ? " · reachable" : " · unreachable"}`} />
            <StatusRow ok={status?.diarization} warn label="Diarization" value={status?.diarization ? "enabled" : "disabled"} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ ok, warn, label, value }: { ok?: boolean; warn?: boolean; label: string; value: string }) {
  const color = ok ? "var(--color-ok)" : warn ? "var(--color-warn)" : "var(--color-signal)";
  return (
    <div className="flex items-center gap-3 py-2.5 border-t border-line-2 first:border-t-0">
      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 16%, transparent)` }} />
      <span className="flex-1 text-[13.5px] font-semibold">{label}</span>
      <span className="text-[12.5px] text-ink-2 font-mono">{value}</span>
    </div>
  );
}

/** AI-model section: provider/model/key/base_url + dynamic discovery, test, cloud disclosure.
 *  Values live in the parent's shared state so the page's Save button picks them up. */
function AiSection({
  values,
  setValue,
  secrets,
  setSecret,
  apiKeyIsSet,
}: {
  values: Record<string, unknown>;
  setValue: (k: string, v: unknown) => void;
  secrets: Record<string, string>;
  setSecret: (k: string, v: string) => void;
  apiKeyIsSet: boolean;
}) {
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [customModel, setCustomModel] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const provider = String(values.llm_provider ?? "ollama");
  const baseUrl = String(values.llm_base_url ?? "");
  const model = String(values.llm_model ?? "");
  const apiKey = secrets.llm_api_key ?? "";

  const preset = providers.find((p) => p.key === provider);
  const effBase = baseUrl || preset?.base_url || "";
  const isCustom = provider === "custom";
  const requiresKey = preset?.requires_key ?? false;
  const loopback = /\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:|\/|$)/i.test(effBase);
  const isCloud = (preset?.is_cloud ?? false) && !(isCustom && loopback);
  const showKey = requiresKey || isCloud;

  useEffect(() => {
    api.getLlmProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  async function loadModels() {
    setLoadingModels(true);
    try {
      const r = await api.listLlmModels({ provider, base_url: baseUrl || undefined, api_key: apiKey || undefined });
      setModels(r.models);
    } catch {
      setModels([]);
    } finally {
      setLoadingModels(false);
    }
  }
  useEffect(() => {
    if (providers.length) loadModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, effBase, providers.length]);

  async function test() {
    setTesting(true);
    setTestMsg(null);
    try {
      const r = await api.testLlm({ provider, base_url: baseUrl || undefined, api_key: apiKey || undefined, model: model || undefined });
      setTestMsg({ ok: r.ok, text: r.detail ?? (r.ok ? "Reachable." : "Not reachable.") });
      if (r.models?.length) setModels(r.models);
    } catch (e) {
      setTestMsg({ ok: false, text: String(e) });
    } finally {
      setTesting(false);
    }
  }

  function onProviderChange(next: string) {
    setValue("llm_provider", next);
    setValue("llm_base_url", "");
    setCustomModel(false);
    setTestMsg(null);
  }

  const CUSTOM_MODEL = "__custom__";
  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;
  const useModelText = customModel || (!loadingModels && modelOptions.length === 0);

  return (
    <div>
      <FieldRow label="Provider" help="Local (Ollama / LM Studio) or a cloud API.">
        <Select value={provider} onChange={onProviderChange}>
          {providers.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </Select>
      </FieldRow>

      {isCustom && (
        <FieldRow label="Base URL" help="OpenAI-compatible endpoint, e.g. http://localhost:1234/v1">
          <input
            type="text"
            className={INPUT}
            value={baseUrl}
            placeholder={preset?.base_url || "https://…/v1"}
            onChange={(e) => setValue("llm_base_url", e.target.value)}
          />
        </FieldRow>
      )}

      {showKey && (
        <FieldRow label="API key" help="Required for cloud providers.">
          <div className="flex items-center gap-2">
            <input
              type="password"
              className={INPUT}
              value={apiKey}
              placeholder={apiKeyIsSet ? "•••••••• (set — blank keeps it)" : "not set"}
              onChange={(e) => setSecret("llm_api_key", e.target.value)}
            />
            {apiKeyIsSet && !apiKey && <Badge tone="ok">Set</Badge>}
          </div>
        </FieldRow>
      )}

      <FieldRow label="Model" help="Discovered from the provider; updates when you switch providers.">
        {loadingModels && modelOptions.length === 0 ? (
          <Select value="" onChange={() => {}}>
            <option>loading…</option>
          </Select>
        ) : modelOptions.length > 0 && !useModelText ? (
          <Select
            value={customModel ? CUSTOM_MODEL : model}
            onChange={(v) => {
              if (v === CUSTOM_MODEL) setCustomModel(true);
              else {
                setCustomModel(false);
                setValue("llm_model", v);
              }
            }}
          >
            {!model && <option value="">Select a model…</option>}
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
            <option value={CUSTOM_MODEL}>Custom…</option>
          </Select>
        ) : (
          <input
            type="text"
            className={`${INPUT} font-mono`}
            value={model}
            placeholder="model id"
            onChange={(e) => setValue("llm_model", e.target.value)}
          />
        )}
      </FieldRow>

      <div className="flex items-center gap-3 pt-4 border-t border-line-2">
        <Button variant="dark" onClick={test} disabled={testing}>
          {testing ? "Testing…" : "Test connection"}
        </Button>
        {testMsg && (
          <span className={`flex items-center gap-1.5 text-[12.5px] font-semibold ${testMsg.ok ? "text-ok-deep" : "text-signal"}`}>
            <Icon name={testMsg.ok ? "circle-check" : "triangle-alert"} size={14} />
            {testMsg.text}
          </span>
        )}
      </div>

      {isCloud ? (
        <div className="flex items-center gap-2.5 mt-3.5 px-3.5 py-2.5 rounded-[10px] bg-signal/[0.07] border border-signal/20 text-[12.5px] text-signal">
          <Icon name="triangle-alert" size={15} />
          Cloud providers send transcripts off-device. Use a local provider (Ollama / LM Studio) to keep everything local.
        </div>
      ) : (
        <div className="flex items-center gap-2.5 mt-3.5 px-3.5 py-2.5 rounded-[10px] bg-ok/10 border border-ok/20 text-[12.5px] text-ok-deep">
          <Icon name="circle-check" size={15} />
          Fully local — transcripts never leave this device.
        </div>
      )}
    </div>
  );
}
