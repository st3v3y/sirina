import { useEffect, useState } from "react";
import { api, type SpeechModel, type SpeechModelsResponse } from "../lib/api";
import { confirmDialog } from "../lib/confirm";
import { Icon } from "./Icon";
import { Badge, Button, Card } from "./ui";

function fmtSize(bytes: number, approxMb: number): string {
  const mb = bytes ? bytes / 1e6 : approxMb;
  if (!mb) return "—";
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

/** Settings card: speech models are downloaded on demand and can be removed again. */
export function SpeechModelsCard() {
  const [data, setData] = useState<SpeechModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setData(await api.listSpeechModels());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    api.listSpeechModels().then(setData).catch((e) => setError(String(e)));
  }, []);

  // Poll while something downloads, so progress moves without a reload.
  const downloading = data?.models.some((m) => m.state === "downloading");
  useEffect(() => {
    if (!downloading) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [downloading]);

  async function install(m: SpeechModel) {
    try {
      await api.installSpeechModel(m.id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(m: SpeechModel) {
    const warn = m.in_use
      ? `“${m.name}” is in use. The next transcription will download it again (or use another engine). Delete it?`
      : `Delete “${m.name}” and free ${fmtSize(m.size_bytes, m.approx_mb)}?`;
    if (!(await confirmDialog(warn))) return;
    try {
      await api.deleteSpeechModel(m.id);
      await load();
    } catch (e) {
      setError(String(e).replace(/^\d+ [^:]*: /, ""));
    }
  }

  const known = data?.models.filter((m) => m.engine !== "unused") ?? [];
  const unused = data?.models.filter((m) => m.engine === "unused") ?? [];

  const row = (m: SpeechModel) => (
    <div key={m.id} className="flex items-center gap-3 py-2.5 border-t border-line-2 first:border-t-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-[13.5px] text-ink">
          <span className="truncate">{m.name}</span>
          {m.in_use && <Badge tone="ok">in use</Badge>}
        </div>
        <div className="text-xs text-muted">
          {m.managed_by_os
            ? m.installed
              ? "Installed · managed by macOS"
              : "Not installed · downloaded by macOS"
            : m.state === "downloading"
              ? `Downloading… ${m.progress != null ? Math.round(m.progress * 100) + "%" : ""}`
              : m.state === "failed"
                ? `Download failed: ${m.error ?? "unknown error"}`
                : `${m.installed ? "Installed" : "Not installed"} · ${fmtSize(m.size_bytes, m.approx_mb)}`}
        </div>
      </div>
      {m.state === "downloading" ? (
        <span className="text-xs text-muted">…</span>
      ) : !m.installed ? (
        <Button onClick={() => install(m)}>{m.state === "failed" ? "Retry" : "Download"}</Button>
      ) : m.managed_by_os ? null : (
        <Button onClick={() => remove(m)}>Delete</Button>
      )}
    </div>
  );

  return (
    <Card className="p-6">
      <div className="flex items-start gap-3 mb-4">
        <span
          className="w-8 h-8 shrink-0 rounded-[9px] flex items-center justify-center"
          style={{ background: "color-mix(in srgb, var(--color-cat-sky) 12%, transparent)", color: "var(--color-cat-sky)" }}
        >
          <Icon name="download" size={16} />
        </span>
        <div className="flex-1">
          <div className="flex items-center gap-2.5">
            <span className="text-base font-bold">Speech models</span>
            <Badge tone="neutral">Downloaded on demand</Badge>
          </div>
          <div className="text-xs text-muted mt-0.5">
            Models aren’t part of the app. Download what you use, delete what you don’t.
          </div>
        </div>
      </div>
      {error && <p className="text-xs text-signal mb-2">{error}</p>}
      {!data ? (
        <p className="text-xs text-muted">Loading…</p>
      ) : (
        <>
          <div>{known.map(row)}</div>
          {unused.length > 0 && (
            <>
              <div className="text-xs font-semibold text-muted mt-4 mb-1">No longer used</div>
              <div>{unused.map(row)}</div>
            </>
          )}
        </>
      )}
    </Card>
  );
}
