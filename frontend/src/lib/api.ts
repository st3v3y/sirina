export type Status = {
  llm_ok: boolean;
  whisper_loaded: boolean;
  whisper_state: "loading" | "ready" | "failed";
  whisper_error?: string | null;
  engine: string;
  configured_engine?: string; // engine the user selected (auto | faster-whisper | mlx)
  engine_note?: string | null; // set when the choice fell back (e.g. mlx unavailable)
  llm_provider: string;
  llm_model: string;
  diarization: boolean;
  diarization_supported?: boolean; // false when speaker splitting can't run here
  diarization_reason?: string | null; // why not, worded for this platform
  platform?: Platform;
};

export type Platform = "macos" | "windows" | "linux";

export type LlmProvider = {
  key: string;
  label: string;
  base_url: string;
  requires_key: boolean;
  is_cloud: boolean;
};

export type LlmProbe = {
  provider: string;
  base_url?: string;
  api_key?: string;
  model?: string;
};

export type LlmTestResult = {
  ok: boolean;
  detail?: string;
  models?: string[];
};

export type ProcessingStage =
  | "queued"
  | "preparing_model"
  | "drafting"
  | "transcribing"
  | "diarizing"
  | "summarizing"
  | "compressing"
  | "done";

export type Progress = {
  stage: ProcessingStage;
  fraction: number | null;
  elapsed_s?: number | null;
  estimated?: boolean;
  power_note?: string | null;
  final_until_s?: number | null;
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
  is_default?: boolean; // the host's default input
};

export type StartRecordingRequest = {
  title?: string;
  device?: string;
  system_device?: string;
  system_source?: "native" | "device" | "none";
  live_transcribe?: boolean;
  live_captions?: boolean;
};

export type AudioCapabilities = {
  native_system_audio: boolean;
  native_system_audio_reason?: string | null; // why native capture is unavailable
  captions_available?: boolean;
  captions_reason?: string | null;
  live_transcribe_available?: boolean;
  live_transcribe_reason?: string | null;
  diarization_reason?: string | null;
  live_captions_default?: boolean;
  live_transcribe_default?: boolean;
};

export type Caption = { start: number; end: number; text: string };
export type TrackCaptions = { settled: Caption[]; provisional: Caption | null; failed: boolean };

export type ActiveInfo = {
  id: number;
  elapsed_s: number;
  level: number;
  mic_level: number;
  system_level: number;
  mic_healthy?: boolean;
  system_healthy?: boolean | null; // null when there is no system track
  system_restarts?: number;
  live_captions?: boolean;
  live_transcribe?: boolean;
  live?: { final_until_s: number; paused: string | null; enabled: boolean; failed: string | null } | null;
  captions?: Record<string, TrackCaptions>; // track name (mic | system) -> captions
  captions_available?: boolean;
  live_transcribe_available?: boolean;
  captions_reason?: string | null;
  live_transcribe_reason?: string | null;
};

export type Segment = {
  id: number;
  recording_id: number;
  speaker_id: number | null;
  start_ts: number;
  end_ts: number;
  text: string;
  is_draft?: boolean; // fast on-device draft, replaced by the final transcript window by window
};

export type Speaker = {
  id: number;
  label: string;
  name: string; // resolved display name (Person name or label)
  person_id: number | null;
  color: string | null;
  is_self?: boolean; // the app user, captured on the mic track
};

export type Person = {
  id: number;
  name: string;
  recording_count: number;
  last_recording_at: string | null;
  is_self?: boolean; // the app user ("You")
  has_voiceprint?: boolean; // voice enrolled — auto-recognised in future recordings
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

export type SettingSection = "ai" | "transcription" | "diarization" | "advanced";
export type SettingType = "string" | "text" | "int" | "float" | "bool" | "enum";
export type SettingRestart = "none" | "reload_engine" | "restart_app";

export type SettingField = {
  key: string;
  label: string;
  section: SettingSection;
  type: SettingType;
  options: string[] | null;
  options_source: string | null;
  secret: boolean;
  restart: SettingRestart;
  help: string | null;
  value?: unknown; // omitted for secrets
  is_set?: boolean | null; // secrets only
};

export type SettingsResponse = {
  fields: SettingField[];
  data_dir: string;
  diarization_supported: boolean;
  diarization_reason?: string | null;
  reload_required: boolean;
};

export type ReloadEngineResult = {
  ok: boolean;
  busy?: boolean;
  detail?: string;
  engine?: string;
};

export type TrimSuggestion = {
  leading_s: number;
  trailing_s: number;
  start_s: number;
  end_s: number;
  duration_s: number;
};

export type RecordingDetail = Recording & {
  language: string | null;
  warning?: string | null; // non-fatal capture issue, e.g. a source track ended short
  // Set when the recording was stopped with long leading/trailing silence and is HELD
  // (not transcribing) awaiting the user's trim decision.
  pending_trim?: TrimSuggestion | null;
  tags: Tag[];
  tracks: string[]; // available audio tracks: mixed | mic | system
  speakers: Speaker[];
  segments: Segment[];
  final_until_s?: number | null; // transcript is final up to here (recording seconds)
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

export type SpeechModel = {
  id: string;
  name: string;
  engine: "whisperkit" | "faster-whisper" | "speakerkit" | "apple" | "unused";
  approx_mb: number;
  installed: boolean;
  size_bytes: number;
  in_use: boolean;
  state: "installed" | "not_installed" | "downloading" | "failed";
  progress: number | null;
  error: string | null;
  managed_by_os: boolean;
};

export type SpeechModelsResponse = {
  models: SpeechModel[];
  helper: { whisperkit?: boolean; speakerkit?: boolean; apple_speech?: boolean; apple_speech_asset_installed?: boolean; macos?: string };
};

export const api = {
  status: () => request<Status>("/api/status"),
  listAudioDevices: (refresh = false) =>
    request<AudioDevice[]>(`/api/audio/devices${refresh ? "?refresh=true" : ""}`),
  getAudioCapabilities: () => request<AudioCapabilities>("/api/audio/capabilities"),

  listRecordings: (tagId?: number) =>
    request<Recording[]>(`/api/recordings${tagId != null ? `?tag_id=${tagId}` : ""}`),
  getRecording: (id: number) => request<RecordingDetail>(`/api/recordings/${id}`),
  updateActiveRecording: (body: { live_transcribe?: boolean; live_captions?: boolean }) =>
    request<ActiveInfo>("/api/recordings/active", { method: "PATCH", body: JSON.stringify(body) }),
  startRecording: (body: StartRecordingRequest) =>
    request<{ id: number }>("/api/recordings/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stopRecording: (id: number) =>
    request<{ ok: boolean; trim?: TrimSuggestion | null }>(`/api/recordings/${id}/stop`, {
      method: "POST",
    }),
  trimDecision: (id: number, trim: boolean) =>
    request<{ ok: boolean }>(`/api/recordings/${id}/trim-decision`, {
      method: "POST",
      body: JSON.stringify({ trim }),
    }),
  renameRecording: (id: number, title: string) =>
    request<Recording>(`/api/recordings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  reprocessRecording: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/reprocess`, { method: "POST" }),
  cancelDiarization: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/cancel-diarization`, { method: "POST" }),
  cancelProcessing: (id: number) =>
    request<{ ok: true }>(`/api/recordings/${id}/cancel-processing`, { method: "POST" }),
  deleteRecording: (id: number) =>
    request<void>(`/api/recordings/${id}`, { method: "DELETE" }),
  deleteRecordingAudio: (id: number) =>
    request<void>(`/api/recordings/${id}/audio`, { method: "DELETE" }),
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

  getSettings: () => request<SettingsResponse>("/api/settings"),
  updateSettings: (updates: Record<string, unknown>) =>
    request<SettingsResponse>("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    }),
  reloadEngine: () =>
    request<ReloadEngineResult>("/api/settings/reload-engine", { method: "POST" }),
  listSpeechModels: () => request<SpeechModelsResponse>("/api/models"),
  installSpeechModel: (id: string) =>
    request<{ ok: boolean }>(`/api/models/${encodeURIComponent(id)}/install`, { method: "POST" }),
  deleteSpeechModel: (id: string) =>
    request<{ ok: boolean; freed_bytes: number }>(`/api/models/${encodeURIComponent(id)}`, { method: "DELETE" }),
  revealDataDir: () =>
    request<{ ok: boolean }>("/api/settings/reveal-data-dir", { method: "POST" }),

  getLlmProviders: () => request<LlmProvider[]>("/api/llm/providers"),
  listLlmModels: (cfg: LlmProbe) =>
    request<{ models: string[] }>("/api/llm/models", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),
  testLlm: (cfg: LlmProbe) =>
    request<LlmTestResult>("/api/llm/test", { method: "POST", body: JSON.stringify(cfg) }),

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
