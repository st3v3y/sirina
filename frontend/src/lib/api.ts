export type Status = {
  ollama_ok: boolean;
  whisper_loaded: boolean;
  model: string;
};

export type Meeting = {
  id: number;
  title: string | null;
  guild_id: string;
  channel_id: string;
  started_at: string;
  ended_at: string | null;
  status: "recording" | "ended" | "failed";
  source: "discord" | "local";
  segment_count?: number;
};

export type AudioDevice = {
  index: number;
  name: string;
  channels: number;
  default_samplerate: number;
};

export type StartMeetingRequest = {
  title?: string;
  device?: string;
  label?: string;
};

export type Segment = {
  id: number;
  meeting_id: number;
  discord_user_id: string;
  username: string;
  start_ts: number;
  end_ts: number;
  text: string;
};

export type Summary = {
  id: number;
  meeting_id: number;
  kind: "live_aspect" | "full" | "qa_answer";
  template_id: number | null;
  content: string;
  created_at: string;
};

export type QAMessage = {
  id: number;
  meeting_id: number;
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

export type MeetingDetail = Meeting & {
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
  listMeetings: () => request<Meeting[]>("/api/meetings"),
  getMeeting: (id: number) => request<MeetingDetail>(`/api/meetings/${id}`),
  startMeeting: (body: StartMeetingRequest) =>
    request<{ meeting_id: number }>("/api/meetings/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listAudioDevices: () => request<AudioDevice[]>("/api/audio/devices"),
  stopMeeting: (id: number, body: { summary_template_id?: number | null } = {}) =>
    request<{ ok: true }>(`/api/meetings/${id}/stop`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteMeeting: (id: number) =>
    request<void>(`/api/meetings/${id}`, { method: "DELETE" }),
  summarize: (id: number, template_id: number) =>
    request<{ summary_id: number; content: string }>(
      `/api/meetings/${id}/summarize`,
      { method: "POST", body: JSON.stringify({ template_id }) }
    ),
  ask: (id: number, question: string, template_id?: number) =>
    request<{ answer: string }>(`/api/meetings/${id}/ask`, {
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
    `/api/meetings/${id}/export?format=${format}`,
};
