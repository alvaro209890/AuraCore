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
};

export type RefineMemoryResponse = {
  current: MemoryCurrent;
  projects: ProjectMemory[];
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

export async function getChatSession(): Promise<ChatSession> {
  return request<ChatSession>("/api/chat/session");
}

export async function sendChatMessage(messageText: string): Promise<ChatSession> {
  return request<ChatSession>("/api/chat/messages", {
    method: "POST",
    body: JSON.stringify({ message_text: messageText }),
  });
}
