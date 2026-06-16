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

export type SummarySection = { title: string; content: string };

export type Summary = {
  id: number;
  recording_id: number;
  template_id: number | null;
  sections: SummarySection[];
  created_at: string;
};

export type QAMessage = {
  id: number;
  recording_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type TemplateSection = { title: string; prompt: string };

export type SummaryTemplate = {
  id: number;
  name: string;
  sections: TemplateSection[];
  is_default: boolean;
  builtin: boolean;
};

export type QATemplate = {
  id: number;
  name: string;
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
    request<Summary>(`/api/recordings/${id}/summarize`, {
      method: "POST",
      body: JSON.stringify({ template_id }),
    }),
  ask: (id: number, question: string, template_id?: number) =>
    request<{ answer: string }>(`/api/recordings/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ question, template_id }),
    }),

  listSummaryTemplates: () => request<SummaryTemplate[]>("/api/summary-templates"),
  createSummaryTemplate: (body: { name: string; sections: TemplateSection[] }) =>
    request<SummaryTemplate>("/api/summary-templates", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSummaryTemplate: (id: number, body: { name?: string; sections?: TemplateSection[] }) =>
    request<SummaryTemplate>(`/api/summary-templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteSummaryTemplate: (id: number) =>
    request<void>(`/api/summary-templates/${id}`, { method: "DELETE" }),

  getQaTemplate: () => request<QATemplate | null>("/api/qa-template"),
  updateQaTemplate: (body: string) =>
    request<QATemplate>("/api/qa-template", {
      method: "PUT",
      body: JSON.stringify({ body }),
    }),
  exportUrl: (id: number, format: "md" | "txt") =>
    `/api/recordings/${id}/export?format=${format}`,
};
