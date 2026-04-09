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

export type WhatsAppAgentStatus = {
  instance_name: string;
  connected: boolean;
  state: string;
  gateway_ready: boolean;
  auto_reply_enabled: boolean;
  owner_number: string | null;
  allowed_contact_phone: string | null;
  qr_code: string | null;
  qr_expires_in_sec: number | null;
  last_seen_at: string | null;
  last_error: string | null;
};

export type WhatsAppAgentSettings = {
  user_id: string;
  auto_reply_enabled: boolean;
  allowed_contact_phone: string | null;
  updated_at: string;
};

export type WhatsAppAgentSession = {
  id: string;
  thread_id: string;
  contact_phone: string | null;
  chat_jid: string | null;
  started_at: string;
  last_activity_at: string;
  ended_at: string | null;
  reset_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type WhatsAppAgentContactMemory = {
  id: string;
  thread_id: string | null;
  contact_name: string;
  contact_phone: string | null;
  chat_jid: string | null;
  profile_summary: string;
  preferred_tone: string;
  preferences: string[];
  objectives: string[];
  durable_facts: string[];
  constraints: string[];
  recurring_instructions: string[];
  learned_message_count: number;
  last_learned_at: string | null;
  updated_at: string;
};

export type WhatsAppAgentThread = {
  id: string;
  contact_name: string;
  contact_phone: string | null;
  chat_jid: string | null;
  status: string;
  active_session_id: string | null;
  session_started_at: string | null;
  session_last_activity_at: string | null;
  session_message_count: number;
  last_message_preview: string | null;
  last_message_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_error_at: string | null;
  last_error_text: string | null;
  created_at: string;
  updated_at: string;
};

export type WhatsAppAgentMessage = {
  id: string;
  thread_id: string;
  direction: "inbound" | "outbound";
  role: "user" | "assistant";
  session_id: string | null;
  whatsapp_message_id: string | null;
  source_inbound_message_id: string | null;
  contact_phone: string | null;
  chat_jid: string | null;
  content: string;
  message_timestamp: string;
  processing_status: string;
  learning_status: string;
  send_status: string | null;
  error_text: string | null;
  response_latency_ms: number | null;
  model_run_id: string | null;
  learned_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type WhatsAppAgentWorkspace = {
  status: WhatsAppAgentStatus;
  settings: WhatsAppAgentSettings;
  observer_status: ObserverStatus;
  active_thread_id: string | null;
  active_session: WhatsAppAgentSession | null;
  contact_memory: WhatsAppAgentContactMemory | null;
  threads: WhatsAppAgentThread[];
  messages: WhatsAppAgentMessage[];
};

export type MemoryCurrent = {
  user_id: string;
  life_summary: string;
  last_analyzed_at: string | null;
  last_snapshot_id: string | null;
  structural_strengths: string[];
  structural_routines: string[];
  structural_preferences: string[];
  structural_open_questions: string[];
};

export type MemoryStatus = {
  has_initial_analysis: boolean;
  last_analyzed_at: string | null;
  pending_new_message_count: number;
  next_process_message_count: number;
  messages_until_auto_process: number;
  can_run_first_analysis: boolean;
  can_run_next_batch: boolean;
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

export type ImportantMessage = {
  id: string;
  source_message_id: string;
  contact_name: string;
  contact_phone: string | null;
  direction: "inbound" | "outbound";
  message_text: string;
  message_timestamp: string;
  category: string;
  importance_reason: string;
  confidence: number;
  status: string;
  review_notes: string | null;
  saved_at: string;
  last_reviewed_at: string | null;
  discarded_at: string | null;
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

export type ChatThread = {
  id: string;
  thread_key: string;
  title: string;
  message_count: number;
  last_message_preview: string | null;
  last_message_role: "user" | "assistant" | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
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

export type ImportantMessagesListResponse = {
  messages: ImportantMessage[];
};

export type ChatSession = {
  thread_id: string;
  title: string;
  current: MemoryCurrent;
  projects: ProjectMemory[];
  messages: ChatMessage[];
};

export type ChatWorkspace = {
  active_thread_id: string;
  threads: ChatThread[];
  session: ChatSession;
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

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error && error.message
        ? error.message
        : "Falha de rede ao falar com o backend.";
    throw new Error(
      `Backend indisponivel ou bloqueado na rede/CORS. Confira se o Render esta online e se FRONTEND_ORIGINS inclui este dominio. Detalhe: ${message}`,
    );
  }

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

export async function connectAgent(): Promise<WhatsAppAgentStatus> {
  return request<WhatsAppAgentStatus>("/api/whatsapp-agent/connect", { method: "POST" });
}

export async function resetAgent(): Promise<WhatsAppAgentStatus> {
  return request<WhatsAppAgentStatus>("/api/whatsapp-agent/reset", { method: "POST" });
}

export async function getAgentStatus(): Promise<WhatsAppAgentStatus> {
  return request<WhatsAppAgentStatus>("/api/whatsapp-agent/status");
}

export async function getAgentWorkspace(threadId?: string): Promise<WhatsAppAgentWorkspace> {
  const query = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : "";
  return request<WhatsAppAgentWorkspace>(`/api/whatsapp-agent/workspace${query}`);
}

export async function updateAgentSettings(input: Partial<WhatsAppAgentSettings>): Promise<WhatsAppAgentSettings> {
  return request<WhatsAppAgentSettings>("/api/whatsapp-agent/settings", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function listAgentThreads(limit = 24): Promise<WhatsAppAgentThread[]> {
  const response = await request<{ threads: WhatsAppAgentThread[] }>(`/api/whatsapp-agent/threads?limit=${limit}`);
  return response.threads;
}

export async function listAgentMessages(threadId: string, limit = 40): Promise<WhatsAppAgentMessage[]> {
  const response = await request<{ messages: WhatsAppAgentMessage[] }>(
    `/api/whatsapp-agent/messages?thread_id=${encodeURIComponent(threadId)}&limit=${limit}`,
  );
  return response.messages;
}

export async function getCurrentMemory(): Promise<MemoryCurrent> {
  return request<MemoryCurrent>("/api/memories/current");
}

export async function getMemoryStatus(): Promise<MemoryStatus> {
  return request<MemoryStatus>("/api/memories/status");
}

export async function getMemorySnapshots(limit = 20): Promise<MemorySnapshot[]> {
  const response = await request<MemorySnapshotsListResponse>(`/api/memories/snapshots?limit=${limit}`);
  return response.snapshots;
}

export async function getImportantMessages(limit = 80): Promise<ImportantMessage[]> {
  try {
    const response = await request<ImportantMessagesListResponse>(`/api/memories/important?limit=${limit}`);
    return response.messages;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/status 404|not found/i.test(message)) {
      return [];
    }
    throw error;
  }
}

export async function getMemoryProjects(): Promise<ProjectMemory[]> {
  return request<ProjectMemory[]>("/api/memories/projects");
}

export async function analyzeMemory(windowHours: number): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>(`/api/memories/analyze?window_hours=${windowHours}`, {
    method: "POST",
  });
}

export async function runFirstMemoryAnalysis(): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/first-analysis", {
    method: "POST",
  });
}

export async function runNextMemoryBatch(): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/process-next-batch", {
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

export async function getChatSession(threadId?: string): Promise<ChatSession> {
  const query = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : "";
  return request<ChatSession>(`/api/chat/session${query}`);
}

export async function getChatWorkspace(threadId?: string): Promise<ChatWorkspace> {
  const query = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : "";
  return request<ChatWorkspace>(`/api/chat/workspace${query}`);
}

export async function createChatThread(title?: string): Promise<ChatWorkspace> {
  return request<ChatWorkspace>("/api/chat/threads", {
    method: "POST",
    body: JSON.stringify(title ? { title } : {}),
  });
}

export async function sendChatMessage(messageText: string, threadId?: string, contextHint?: string): Promise<ChatWorkspace> {
  const body: Record<string, unknown> = { message_text: messageText };
  if (threadId) body.thread_id = threadId;
  if (contextHint) body.context_hint = contextHint;
  return request<ChatWorkspace>("/api/chat/messages", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type ChatStreamEvent =
  | { type: "token"; content: string }
  | { type: "done"; workspace: ChatWorkspace };

export async function* sendChatMessageStream(
  messageText: string,
  threadId?: string,
  contextHint?: string,
): AsyncGenerator<ChatStreamEvent> {
  const url = `${API_BASE_URL}/api/chat/messages/stream`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message_text: messageText, thread_id: threadId, context_hint: contextHint }),
      cache: "no-store",
    });
  } catch {
    // Streaming endpoint unavailable – fall back to normal request
    const workspace = await sendChatMessage(messageText, threadId, contextHint);
    const lastMsg = workspace.session.messages[workspace.session.messages.length - 1];
    if (lastMsg?.role === "assistant") {
      yield { type: "token", content: lastMsg.content };
    }
    yield { type: "done", workspace };
    return;
  }

  if (!response.ok || !response.body) {
    // Fallback: non-streaming
    const workspace = await sendChatMessage(messageText, threadId, contextHint);
    const lastMsg = workspace.session.messages[workspace.session.messages.length - 1];
    if (lastMsg?.role === "assistant") {
      yield { type: "token", content: lastMsg.content };
    }
    yield { type: "done", workspace };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") {
            // Fetch final workspace state
            const workspace = await getChatWorkspace(threadId);
            yield { type: "done", workspace };
            return;
          }
          try {
            const parsed = JSON.parse(payload) as { token?: string; workspace?: ChatWorkspace };
            if (parsed.token) {
              yield { type: "token", content: parsed.token };
            }
            if (parsed.workspace) {
              yield { type: "done", workspace: parsed.workspace };
              return;
            }
          } catch {
            // Non-JSON data line, treat as raw token
            yield { type: "token", content: payload };
          }
        }
      }
    }

    // Stream ended without explicit DONE — fetch workspace
    const workspace = await getChatWorkspace(threadId);
    yield { type: "done", workspace };
  } finally {
    reader.releaseLock();
  }
}
