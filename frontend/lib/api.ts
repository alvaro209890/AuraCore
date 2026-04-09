export type ObserverStatus = {
  instance_name: string;
  connected: boolean;
  state: string;
  gateway_ready: boolean;
  ingestion_ready: boolean;
  owner_number: string | null;
  qr_code: string | null;
  qr_expires_in_sec: number | null;
  last_seen_at: string | null;
  last_error: string | null;
};

export type ObserverMessageRefreshResponse = {
  ok: boolean;
  refresh_started: boolean;
  status: ObserverStatus;
  message: string;
  sync_run_id: string | null;
};

export type MemoryCurrent = {
  user_id: string;
  life_summary: string;
  last_analyzed_at: string | null;
  last_snapshot_id: string | null;
};

export type MemorySnapshot = {
  id: string;
  window_hours: number;
  window_start: string;
  window_end: string;
  source_message_count: number;
  window_summary: string;
  key_learnings: string[];
  people_and_relationships: string[];
  routine_signals: string[];
  preferences: string[];
  open_questions: string[];
  created_at: string;
};

export type ProjectMemory = {
  id: string;
  project_key: string;
  project_name: string;
  summary: string;
  status: string;
  what_is_being_built: string;
  built_for: string;
  next_steps: string[];
  evidence: string[];
  source_snapshot_id: string | null;
  last_seen_at: string | null;
  updated_at: string;
};

export type MemoryAnalysisDetailMode = "light" | "balanced" | "deep";

export type MemoryAnalysisPreview = {
  target_message_count: number;
  max_lookback_hours: number;
  detail_mode: MemoryAnalysisDetailMode;
  deepseek_model: string;
  available_message_count: number;
  selected_message_count: number;
  new_message_count: number;
  replaced_message_count: number;
  retained_message_count: number;
  retention_limit: number;
  current_char_budget: number;
  selected_transcript_chars: number;
  selected_transcript_tokens: number;
  average_selected_message_chars: number;
  average_selected_message_tokens: number;
  estimated_prompt_context_tokens: number;
  model_context_limit_floor_tokens: number;
  model_context_limit_ceiling_tokens: number;
  safe_input_budget_floor_tokens: number;
  safe_input_budget_ceiling_tokens: number;
  remaining_input_headroom_floor_tokens: number;
  remaining_input_headroom_ceiling_tokens: number;
  model_default_output_tokens: number;
  model_max_output_tokens: number;
  request_output_reserve_tokens: number;
  estimated_reasoning_tokens: number;
  planner_message_capacity: number;
  stack_max_message_capacity: number;
  model_message_capacity_floor: number;
  model_message_capacity_ceiling: number;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  estimated_cost_input_floor_usd: number;
  estimated_cost_input_ceiling_usd: number;
  estimated_cost_output_floor_usd: number;
  estimated_cost_output_ceiling_usd: number;
  estimated_cost_total_floor_usd: number;
  estimated_cost_total_ceiling_usd: number;
  documentation_context_note: string;
  documentation_pricing_note: string;
  recommendation_score: number;
  recommendation_label: string;
  recommendation_summary: string;
  should_analyze: boolean;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type AnalyzeMemoryResponse = {
  current: MemoryCurrent;
  snapshot: MemorySnapshot;
  projects: ProjectMemory[];
  job: AnalysisJob | null;
};

export type RefineMemoryResponse = {
  current: MemoryCurrent;
  projects: ProjectMemory[];
  job: AnalysisJob | null;
};

export type MemorySnapshotsListResponse = {
  snapshots: MemorySnapshot[];
};

export type ChatSession = {
  thread_id: string;
  title: string;
  current: MemoryCurrent;
  projects: ProjectMemory[];
  messages: ChatMessage[];
};

export type AutomationSettings = {
  user_id: string;
  auto_sync_enabled: boolean;
  auto_analyze_enabled: boolean;
  auto_refine_enabled: boolean;
  min_new_messages_threshold: number;
  stale_hours_threshold: number;
  pruned_messages_threshold: number;
  default_detail_mode: MemoryAnalysisDetailMode;
  default_target_message_count: number;
  default_lookback_hours: number;
  daily_budget_usd: number;
  max_auto_jobs_per_day: number;
  updated_at: string;
};

export type WhatsAppSyncRun = {
  id: string;
  trigger: string;
  status: string;
  messages_seen_count: number;
  messages_saved_count: number;
  messages_ignored_count: number;
  messages_pruned_count: number;
  oldest_message_at: string | null;
  newest_message_at: string | null;
  error_text: string | null;
  started_at: string;
  finished_at: string | null;
  last_activity_at: string | null;
};

export type AutomationDecision = {
  id: string;
  sync_run_id: string | null;
  intent: string;
  action: string;
  reason_code: string;
  score: number;
  should_analyze: boolean;
  available_message_count: number;
  selected_message_count: number;
  new_message_count: number;
  replaced_message_count: number;
  estimated_total_tokens: number;
  estimated_cost_ceiling_usd: number;
  explanation: string;
  created_at: string;
};

export type AnalysisJob = {
  id: string;
  intent: string;
  status: string;
  trigger_source: string;
  decision_id: string | null;
  sync_run_id: string | null;
  target_message_count: number;
  max_lookback_hours: number;
  detail_mode: string;
  selected_message_count: number;
  selected_transcript_chars: number;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cost_floor_usd: number;
  estimated_cost_ceiling_usd: number;
  snapshot_id: string | null;
  error_text: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type ModelRun = {
  id: string;
  job_id: string | null;
  provider: string;
  model_name: string;
  run_type: string;
  success: boolean;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  estimated_cost_usd: number | null;
  error_text: string | null;
  created_at: string;
};

export type AutomationStatus = {
  settings: AutomationSettings;
  sync_runs: WhatsAppSyncRun[];
  decisions: AutomationDecision[];
  jobs: AnalysisJob[];
  model_runs: ModelRun[];
  daily_cost_usd: number;
  daily_auto_jobs_count: number;
  queued_jobs_count: number;
  running_job_id: string | null;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  (typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "https://auracore-backend-82bf2.onrender.com")
);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? undefined);
  const hasBody = init?.body !== undefined && init?.body !== null;
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const errorPayload = (await response.json()) as { detail?: string };
      if (typeof errorPayload.detail === "string" && errorPayload.detail.length > 0) {
        detail = errorPayload.detail;
      }
    } catch {
      // Ignore JSON parsing errors and keep the generic message.
    }

    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export async function connectObserver(): Promise<ObserverStatus> {
  return request<ObserverStatus>("/api/observer/connect", { method: "POST" });
}

export async function resetObserver(): Promise<ObserverStatus> {
  return request<ObserverStatus>("/api/observer/reset", { method: "POST" });
}

export async function getObserverStatus(refreshQr = false): Promise<ObserverStatus> {
  const query = refreshQr ? "?refresh_qr=true" : "";
  return request<ObserverStatus>(`/api/observer/status${query}`);
}

export async function refreshObserverMessages(): Promise<ObserverMessageRefreshResponse> {
  return request<ObserverMessageRefreshResponse>("/api/observer/messages/refresh", {
    method: "POST",
  });
}

export async function getCurrentMemory(): Promise<MemoryCurrent> {
  return request<MemoryCurrent>("/api/memories/current");
}

export async function getMemorySnapshots(limit = 20): Promise<MemorySnapshot[]> {
  const response = await request<MemorySnapshotsListResponse>(`/api/memories/snapshots?limit=${limit}`);
  return response.snapshots;
}

export async function analyzeMemory(windowHours: number): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>(`/api/memories/analyze?window_hours=${windowHours}`, {
    method: "POST",
  });
}

export async function analyzeMemoryWithFilters(input: {
  intent?: "first_analysis" | "improve_memory";
  target_message_count: number;
  max_lookback_hours: number;
  detail_mode: MemoryAnalysisDetailMode;
}): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/analyze", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function previewMemoryAnalysis(input: {
  target_message_count: number;
  max_lookback_hours: number;
  detail_mode: MemoryAnalysisDetailMode;
}): Promise<MemoryAnalysisPreview> {
  return request<MemoryAnalysisPreview>("/api/memories/preview", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function refineMemory(): Promise<RefineMemoryResponse> {
  return request<RefineMemoryResponse>("/api/memories/refine", {
    method: "POST",
  });
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  return request<AutomationStatus>("/api/automation/status");
}

export async function updateAutomationSettings(input: Partial<AutomationSettings>): Promise<AutomationSettings> {
  return request<AutomationSettings>("/api/automation/settings", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function runAutomationTick(): Promise<AutomationStatus> {
  return request<AutomationStatus>("/api/automation/tick", {
    method: "POST",
  });
}

export async function getChatSession(): Promise<ChatSession> {
  return request<ChatSession>("/api/chat/session");
}

export async function sendChatMessage(messageText: string): Promise<ChatSession> {
  return request<ChatSession>("/api/chat/messages", {
    method: "POST",
    body: JSON.stringify({ message_text: messageText }),
  });
}
