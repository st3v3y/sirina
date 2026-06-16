export type Status = {
  ollama_ok: boolean;
  whisper_loaded: boolean;
  model: string;
};

export type RecordingStatus = "recording" | "processing" | "ready" | "failed";

export type Recording = {
  id: number;
  title: string | null;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  status: RecordingStatus;
  segment_count?: number;
};

export type AudioDevice = {
  index: number;
  name: string;
  channels: number;
  default_samplerate: number;
};

export type StartRecordingRequest = {
  title?: string;
  device?: string;
  system_device?: string;
  label?: string;
};

export type ActiveInfo = {
  id: number;
  elapsed_s: number;
  level: number;
};

export type Segment = {
  id: number;
  recording_id: number;
  speaker_label: string;
  start_ts: number;
  end_ts: number;
  text: string;
};

export type Summary = {
  id: number;
  recording_id: number;
  kind: "live_aspect" | "full" | "qa_answer";
  template_id: number | null;
  content: string;
  created_at: string;
};

export type QAMessage = {
  id: number;
  recording_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type PromptTemplate = {
  id: number;
  name: string;
  kind: "summary" | "aspects" | "qa";
  body: string;
  is_default: boolean;
};

export type RecordingDetail = Recording & {
  language: string | null;
  segments: Segment[];
  summaries: Summary[];
  qa: QAMessage[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("/api/status"),
  listAudioDevices: () => request<AudioDevice[]>("/api/audio/devices"),

  listRecordings: () => request<Recording[]>("/api/recordings"),
  getRecording: (id: number) => request<RecordingDetail>(`/api/recordings/${id}`),
  startRecording: (body: StartRecordingRequest) =>
    request<{ id: number }>("/api/recordings/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stopRecording: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/stop`, { method: "POST" }),
  deleteRecording: (id: number) =>
    request<void>(`/api/recordings/${id}`, { method: "DELETE" }),
  activeRecording: () => request<ActiveInfo | null>("/api/recordings/active"),

  summarize: (id: number, template_id: number) =>
    request<{ summary_id: number; content: string }>(
      `/api/recordings/${id}/summarize`,
      { method: "POST", body: JSON.stringify({ template_id }) }
    ),
  ask: (id: number, question: string, template_id?: number) =>
    request<{ answer: string }>(`/api/recordings/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ question, template_id }),
    }),

  listTemplates: () => request<PromptTemplate[]>("/api/templates"),
  createTemplate: (body: { name: string; kind: string; body: string }) =>
    request<PromptTemplate>("/api/templates", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateTemplate: (id: number, body: Partial<PromptTemplate>) =>
    request<PromptTemplate>(`/api/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteTemplate: (id: number) =>
    request<void>(`/api/templates/${id}`, { method: "DELETE" }),
  exportUrl: (id: number, format: "md" | "txt") =>
    `/api/recordings/${id}/export?format=${format}`,
};
