export type Status = {
  ollama_ok: boolean;
  whisper_loaded: boolean;
  model: string;
  engine: string;
  diarization: boolean;
};

export type ProcessingStage = "queued" | "transcribing" | "diarizing" | "summarizing" | "done";

export type Progress = {
  stage: ProcessingStage;
  fraction: number | null;
  elapsed_s?: number | null;
  estimated?: boolean;
};

export type RecordingStatus = "recording" | "processing" | "ready" | "failed";

export type Tag = {
  id: number;
  name: string;
  color: string | null;
};

export type Recording = {
  id: number;
  title: string | null;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  status: RecordingStatus;
  error?: string | null;
  progress?: Progress | null;
  segment_count?: number;
  tags: Tag[];
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
  system_source?: "native" | "device" | "none";
};

export type AudioCapabilities = {
  native_system_audio: boolean;
};

export type ActiveInfo = {
  id: number;
  elapsed_s: number;
  level: number;
};

export type Segment = {
  id: number;
  recording_id: number;
  speaker_id: number | null;
  start_ts: number;
  end_ts: number;
  text: string;
};

export type Speaker = {
  id: number;
  label: string;
  name: string; // resolved display name (Person name or label)
  person_id: number | null;
  color: string | null;
};

export type Person = {
  id: number;
  name: string;
  recording_count: number;
  last_recording_at: string | null;
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
  general_context: string | null;
  is_default: boolean;
  builtin: boolean;
};

export type ChatMessage = {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ChatSession = {
  id: number;
  title: string | null;
  created_at: string;
  messages: ChatMessage[];
};

export type QATemplate = {
  id: number;
  name: string;
  body: string;
  is_default: boolean;
};

export type RecordingDetail = Recording & {
  language: string | null;
  tags: Tag[];
  tracks: string[]; // available audio tracks: mixed | mic | system
  speakers: Speaker[];
  segments: Segment[];
  summaries: Summary[];
  qa: QAMessage[];
};

// In the packaged Tauri app the backend runs on a chosen localhost port; the shell
// injects `window.__BACKEND_URL__`. In dev this is unset → relative paths go through
// the Vite proxy (unchanged).
const API_BASE: string =
  (typeof window !== "undefined" && (window as unknown as { __BACKEND_URL__?: string }).__BACKEND_URL__) || "";

export function apiUrl(path: string): string {
  return API_BASE + path;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
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
  getAudioCapabilities: () => request<AudioCapabilities>("/api/audio/capabilities"),

  listRecordings: (tagId?: number) =>
    request<Recording[]>(`/api/recordings${tagId != null ? `?tag_id=${tagId}` : ""}`),
  getRecording: (id: number) => request<RecordingDetail>(`/api/recordings/${id}`),
  startRecording: (body: StartRecordingRequest) =>
    request<{ id: number }>("/api/recordings/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stopRecording: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/stop`, { method: "POST" }),
  renameRecording: (id: number, title: string) =>
    request<Recording>(`/api/recordings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  reprocessRecording: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/reprocess`, { method: "POST" }),
  cancelDiarization: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/cancel-diarization`, { method: "POST" }),
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

  renameSpeaker: (recordingId: number, speakerId: number, name: string) =>
    request<Speaker>(`/api/recordings/${recordingId}/speakers/${speakerId}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),

  listPeople: () => request<Person[]>("/api/people"),
  renamePerson: (id: number, name: string) =>
    request<Person>(`/api/people/${id}`, { method: "PUT", body: JSON.stringify({ name }) }),
  deletePerson: (id: number) => request<void>(`/api/people/${id}`, { method: "DELETE" }),

  listTags: () => request<Tag[]>("/api/tags"),
  createTag: (name: string, color?: string | null) =>
    request<Tag>("/api/tags", { method: "POST", body: JSON.stringify({ name, color }) }),
  updateTag: (id: number, body: { name?: string; color?: string | null }) =>
    request<Tag>(`/api/tags/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTag: (id: number) => request<void>(`/api/tags/${id}`, { method: "DELETE" }),
  addTagToRecording: (recordingId: number, tagId: number) =>
    request<void>(`/api/recordings/${recordingId}/tags`, {
      method: "POST",
      body: JSON.stringify({ tag_id: tagId }),
    }),
  removeTagFromRecording: (recordingId: number, tagId: number) =>
    request<void>(`/api/recordings/${recordingId}/tags/${tagId}`, { method: "DELETE" }),

  listSummaryTemplates: () => request<SummaryTemplate[]>("/api/summary-templates"),
  createSummaryTemplate: (body: {
    name: string;
    sections: TemplateSection[];
    general_context?: string | null;
  }) =>
    request<SummaryTemplate>("/api/summary-templates", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSummaryTemplate: (
    id: number,
    body: { name?: string; sections?: TemplateSection[]; general_context?: string | null }
  ) =>
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
    apiUrl(`/api/recordings/${id}/export?format=${format}`),
  audioUrl: (id: number, track: "mixed" | "mic" | "system") =>
    apiUrl(`/api/recordings/${id}/audio?track=${track}`),
  getExportText: async (id: number, format: "md" | "txt") => {
    const res = await fetch(apiUrl(`/api/recordings/${id}/export?format=${format}`));
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.text();
  },

  listChatSessions: () => request<ChatSession[]>("/api/chat/sessions"),
  createChatSession: (title?: string) =>
    request<ChatSession>("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  askChatSession: (id: number, question: string) =>
    request<{ answer: string }>(`/api/chat/sessions/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  deleteChatSession: (id: number) =>
    request<void>(`/api/chat/sessions/${id}`, { method: "DELETE" }),
};
