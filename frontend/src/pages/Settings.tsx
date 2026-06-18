import { useEffect, useMemo, useState } from "react";
import {
  api,
  type SettingField,
  type SettingSection,
  type SettingsResponse,
  type Status,
} from "../lib/api";

const SECTIONS: { id: SettingSection; title: string }[] = [
  { id: "ai", title: "AI model" },
  { id: "transcription", title: "Transcription" },
  { id: "diarization", title: "Speaker diarization" },
  { id: "advanced", title: "Advanced" },
];

const RESTART_LABEL: Record<string, string> = {
  reload_engine: "needs engine reload",
  restart_app: "needs app restart",
};

export default function Settings() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  // Edited non-secret values, mirrored from the response; secrets edited separately.
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
    api.listOllamaModels().then((r) => setOllamaModels(r.models)).catch(() => setOllamaModels([]));
  }, []);

  const dirty = useMemo(() => {
    if (!data) return false;
    const nonSecretChanged = Object.keys(values).some(
      (k) => JSON.stringify(values[k]) !== JSON.stringify(original[k])
    );
    const secretChanged = Object.values(secrets).some((s) => s !== "");
    return nonSecretChanged || secretChanged;
  }, [data, values, original, secrets]);

  function optionsFor(f: SettingField): string[] | null {
    let opts = f.options ?? null;
    if (f.options_source === "ollama_models") {
      opts = ollamaModels.length ? ollamaModels : f.options ?? null;
    }
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
    return (
      <div className="max-w-3xl mx-auto p-6 text-sm text-neutral-400">
        {error ?? "Loading settings…"}
      </div>
    );
  }

  const inputCls =
    "bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-sm focus:outline-none focus:border-neutral-600";

  function control(f: SettingField) {
    if (f.secret) {
      return (
        <input
          type="password"
          className={`${inputCls} w-64`}
          value={secrets[f.key] ?? ""}
          placeholder={f.is_set ? "•••••••• (set — blank keeps it)" : "not set"}
          onChange={(e) => setSecrets((s) => ({ ...s, [f.key]: e.target.value }))}
        />
      );
    }
    if (f.type === "bool") {
      return (
        <input
          type="checkbox"
          className="h-4 w-4 accent-fuchsia-600"
          checked={Boolean(values[f.key])}
          onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.checked }))}
        />
      );
    }
    const opts = optionsFor(f);
    if (opts) {
      return (
        <select
          className={`${inputCls} w-64`}
          value={String(values[f.key] ?? "")}
          onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
        >
          {opts.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );
    }
    if (f.type === "int" || f.type === "float") {
      return (
        <input
          type="number"
          step={f.type === "float" ? "any" : 1}
          className={`${inputCls} w-32`}
          value={values[f.key] === "" || values[f.key] == null ? "" : String(values[f.key])}
          onChange={(e) =>
            setValues((v) => ({
              ...v,
              [f.key]: e.target.value === "" ? "" : Number(e.target.value),
            }))
          }
        />
      );
    }
    if (f.type === "text") {
      return (
        <textarea
          className={`${inputCls} w-64 h-16 font-mono text-xs`}
          value={String(values[f.key] ?? "")}
          onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
        />
      );
    }
    return (
      <input
        type="text"
        className={`${inputCls} w-64`}
        value={String(values[f.key] ?? "")}
        onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
      />
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Settings</h1>
        <div className="flex items-center gap-3">
          {saved && <span className="text-xs text-emerald-400">Saved</span>}
          <button
            onClick={save}
            disabled={!dirty || saving}
            className="text-sm px-3 py-1.5 rounded bg-fuchsia-600 hover:bg-fuchsia-500 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      {/* Status (read-only, reuses /api/status) */}
      <section className="rounded-lg border border-neutral-800 p-4 text-sm">
        <h2 className="text-xs uppercase tracking-wide text-neutral-500 mb-2">Status</h2>
        <div className="flex flex-wrap gap-x-8 gap-y-1 text-neutral-300">
          <span>
            Engine: <span className="text-neutral-100">{status?.engine ?? "—"}</span>
          </span>
          <span>
            Whisper:{" "}
            <span className={status?.whisper_loaded ? "text-emerald-400" : "text-amber-400"}>
              {status?.whisper_loaded ? "loaded" : "loading…"}
            </span>
          </span>
          <span>
            Ollama:{" "}
            <span className={status?.ollama_ok ? "text-emerald-400" : "text-rose-400"}>
              {status?.ollama_ok ? "reachable" : "unreachable"}
            </span>
          </span>
        </div>
      </section>

      {error && (
        <div className="rounded border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">
          {error}
        </div>
      )}

      {SECTIONS.map(({ id, title }) => {
        const fields = data.fields.filter((f) => f.section === id);
        if (!fields.length) return null;
        return (
          <section key={id}>
            <h2 className="text-base font-medium mb-3">{title}</h2>
            {id === "diarization" && !data.diarization_supported && (
              <p className="text-xs text-amber-400/90 mb-3">
                Diarization isn't available in this build (the model runtime isn't bundled yet);
                these settings are saved but won't take effect.
              </p>
            )}
            <div className="rounded-lg border border-neutral-800 divide-y divide-neutral-800">
              {fields.map((f) => (
                <div key={f.key} className="flex items-start gap-4 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{f.label}</span>
                      {f.restart !== "none" && (
                        <span className="text-[10px] uppercase text-amber-400 border border-amber-700/60 rounded px-1">
                          {RESTART_LABEL[f.restart]}
                        </span>
                      )}
                    </div>
                    {f.help && <p className="text-xs text-neutral-500 mt-0.5">{f.help}</p>}
                  </div>
                  <div className="shrink-0 pt-0.5">{control(f)}</div>
                </div>
              ))}
              {id === "advanced" && (
                <div className="flex items-center gap-4 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">Data folder</div>
                    <p className="text-xs text-neutral-500 mt-0.5 truncate">{data.data_dir}</p>
                  </div>
                  <button
                    onClick={reveal}
                    className="shrink-0 text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700"
                  >
                    Open in Finder
                  </button>
                </div>
              )}
            </div>

            {id === "transcription" && (
              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={reload}
                  disabled={reloading}
                  className={`text-sm px-3 py-1.5 rounded disabled:opacity-40 ${
                    reloadRequired
                      ? "bg-amber-600 hover:bg-amber-500"
                      : "bg-neutral-800 hover:bg-neutral-700"
                  }`}
                >
                  {reloading ? "Reloading…" : "Reload transcription engine"}
                </button>
                {reloadRequired && (
                  <span className="text-xs text-amber-400">
                    A change needs a reload to take effect.
                  </span>
                )}
                {reloadMsg && <span className="text-xs text-neutral-400">{reloadMsg}</span>}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
