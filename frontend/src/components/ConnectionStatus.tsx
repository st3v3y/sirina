import { useEffect, useState } from "react";
import { api, type Status } from "../lib/api";
import { useStatusSocket } from "../lib/useMeetingSocket";

export default function ConnectionStatus() {
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);
  useStatusSocket(setStatus);

  const ready = status?.ollama_ok && status?.whisper_loaded;
  const color = ready ? "bg-emerald-500" : status ? "bg-amber-500" : "bg-neutral-600";
  const label = !status
    ? "Backend unreachable"
    : ready
    ? "Ready"
    : `${status.ollama_ok ? "" : "no Ollama · "}${status.whisper_loaded ? "" : "no Whisper"}`.replace(/ · $/, "");

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />
      <span className="text-neutral-400">{label}</span>
    </div>
  );
}
