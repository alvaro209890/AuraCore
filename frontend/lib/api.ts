import { firebaseAuth } from "./firebase";

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

export type AuthenticatedAccount = {
  firebase_uid: string;
  app_user_id: string | null;
  username: string | null;
  email: string;
  email_verified: boolean;
  provisioned: boolean;
};

export type UsernameAvailability = {
  available: boolean;
  normalized_username: string | null;
  reason: string | null;
};

export type WhatsAppAgentStatus = {
  instance_name: string;
  connected: boolean;
  state: string;
  gateway_ready: boolean;
  auto_reply_enabled: boolean;
  reply_scope: "observer_owner_only";
  owner_number: string | null;
  qr_code: string | null;
  qr_expires_in_sec: number | null;
  last_seen_at: string | null;
  last_error: string | null;
};

export type WhatsAppAgentSettings = {
  user_id: string;
  auto_reply_enabled: boolean;
  reply_scope: "observer_owner_only";
  updated_at: string;
};

export type ProactiveIntensity = "conservative" | "moderate" | "high";
export type ProactiveCategory =
  | "agenda_followup"
  | "followup"
  | "project_nudge"
  | "routine"
  | "morning_digest"
  | "night_digest";
export type ProactiveCandidateStatus =
  | "queued"
  | "suggested"
  | "sent"
  | "dismissed"
  | "confirmed"
  | "done"
  | "expired";

export type ProactivePreferences = {
  user_id: string;
  enabled: boolean;
  intensity: ProactiveIntensity;
  quiet_hours_start: string;
  quiet_hours_end: string;
  max_unsolicited_per_day: number;
  min_interval_minutes: number;
  agenda_enabled: boolean;
  followups_enabled: boolean;
  projects_enabled: boolean;
  routine_enabled: boolean;
  morning_digest_enabled: boolean;
  night_digest_enabled: boolean;
  morning_digest_time: string;
  night_digest_time: string;
  updated_at: string;
};

export type ProactiveCandidate = {
  id: string;
  category: ProactiveCategory;
  status: ProactiveCandidateStatus;
  source_message_id: string | null;
  source_kind: string;
  thread_id: string | null;
  contact_phone: string | null;
  chat_jid: string | null;
  title: string;
  summary: string;
  confidence: number;
  priority: number;
  due_at: string | null;
  cooldown_until: string | null;
  last_nudged_at: string | null;
  payload_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProactiveDeliveryLog = {
  id: string;
  candidate_id: string | null;
  category: ProactiveCategory;
  decision: "sent" | "skipped" | "suppressed" | "failed";
  score: number;
  reason_code: string;
  reason_text: string;
  message_text: string;
  message_id: string | null;
  sent_at: string | null;
  created_at: string;
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
  new_messages_after_first_analysis: number;
  current_job: AnalysisJob | null;
  latest_completed_job: AnalysisJob | null;
  sync_in_progress: boolean;
  can_execute_analysis: boolean;
};

export type WhatsAppGroupSelection = {
  chat_jid: string;
  chat_name: string;
  enabled_for_analysis: boolean;
  last_seen_at: string | null;
  last_message_at: string | null;
  message_count: number;
  pending_message_count: number;
};

export type MemorySnapshot = {
  id: string;
  window_hours: number;
  window_start: string;
  window_end: string;
  source_message_count: number;
  distinct_contact_count: number;
  inbound_message_count: number;
  outbound_message_count: number;
  coverage_score: number;
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
  origin_source: "memory" | "manual";
  summary: string;
  status: string;
  what_is_being_built: string;
  built_for: string;
  next_steps: string[];
  evidence: string[];
  source_snapshot_id: string | null;
  last_seen_at: string | null;
  completion_source: string;
  manual_completed_at: string | null;
  manual_completion_notes: string;
  updated_at: string;
};

export type AgendaConflict = {
  id: string;
  titulo: string;
  inicio: string;
  fim: string;
  status: string;
  contato_origem: string | null;
  message_id: string;
};

export type AgendaEvent = {
  id: string;
  titulo: string;
  inicio: string;
  fim: string;
  status: "firme" | "tentativo";
  contato_origem: string | null;
  message_id: string;
  has_conflict: boolean;
  conflict: AgendaConflict | null;
  reminder_offset_minutes: number;
  reminder_eligible: boolean;
  reminder_block_reason: string | null;
  pre_reminder_at: string | null;
  pre_reminder_sent_at: string | null;
  reminder_sent_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UpdateAgendaEventInput = {
  titulo?: string;
  inicio?: string;
  fim?: string;
  status?: "firme" | "tentativo";
  contato_origem?: string;
  reminder_offset_minutes?: number;
};

export type CreateAgendaEventInput = {
  titulo: string;
  inicio: string;
  fim: string;
  status?: "firme" | "tentativo";
  contato_origem?: string;
  reminder_offset_minutes?: number;
};

export type ProjectAssistantEditResponse = {
  project: ProjectMemory;
  assistant_message: string;
};

export type CreateProjectMemoryInput = {
  project_name: string;
  summary: string;
  status?: string;
  what_is_being_built?: string;
  built_for?: string;
  next_steps?: string[];
  evidence?: string[];
};

export type PersonRelation = {
  id: string;
  person_key: string;
  contact_name: string;
  contact_phone: string | null;
  chat_jid: string | null;
  profile_summary: string;
  relationship_type: string;
  relationship_summary: string;
  salient_facts: string[];
  open_loops: string[];
  recent_topics: string[];
  source_snapshot_id: string | null;
  source_message_count: number;
  last_message_at: string | null;
  last_analyzed_at: string | null;
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


export type AnalyzeMemoryResponse = {
  current: MemoryCurrent;
  snapshot: MemorySnapshot | null;
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

export type WhatsAppGroupSelectionsListResponse = {
  groups: WhatsAppGroupSelection[];
};

export type AgendaEventsListResponse = {
  events: AgendaEvent[];
};


export type SimpleOkResponse = {
  ok: boolean;
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
  progress_percent: number;
  live_stage: string | null;
  live_status_text: string | null;
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

export type MemoryActivity = {
  sync_runs: WhatsAppSyncRun[];
  jobs: AnalysisJob[];
  model_runs: ModelRun[];
  running_job_id: string | null;
  decisions?: AutomationDecision[];
  queued_jobs_count?: number;
  daily_auto_jobs_count?: number;
  settings?: AutomationSettings | null;
};

export type MemoryLiveSummary = {
  generated_at: string;
  pending_new_messages: number;
  has_initial_analysis: boolean;
  current_job_id: string | null;
  current_job_status: string | null;
  latest_completed_job_id: string | null;
  latest_completed_job_status: string | null;
  latest_snapshot_id: string | null;
  latest_snapshot_created_at: string | null;
  latest_project_id: string | null;
  latest_project_updated_at: string | null;
  latest_relation_id: string | null;
  latest_relation_updated_at: string | null;
  memory_signature: string;
  activity_signature: string;
  projects_signature: string;
  relations_signature: string;
};

const REMOTE_FALLBACK_API_BASE_URL = "https://api.cursar.space";
const EXPLICIT_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? null;

let activeApiBaseUrl: string | null = EXPLICIT_API_BASE_URL;

function isLoopbackHost(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "[::1]";
}

function isPrivateIpv4Host(hostname: string): boolean {
  return /^(10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname)
    || /^192\.168\.\d{1,3}\.\d{1,3}$/.test(hostname)
    || /^172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}$/.test(hostname);
}

function isLocalApiBaseUrl(value: string | null | undefined): boolean {
  if (!value) {
    return false;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" && (isLoopbackHost(parsed.hostname) || isPrivateIpv4Host(parsed.hostname));
  } catch {
    return false;
  }
}

function buildApiBaseCandidates(): string[] {
  const candidates: string[] = [];
  const seen = new Set<string>();
  const addCandidate = (value: string | null | undefined): void => {
    if (!value) {
      return;
    }
    const normalized = value.replace(/\/$/, "");
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    candidates.push(normalized);
  };

  if (typeof window !== "undefined") {
    const browserHost = window.location.hostname.trim().toLowerCase();
    const isFirebaseHost = browserHost.endsWith(".web.app") || browserHost.endsWith(".firebaseapp.com");
    const localCandidates = ["http://127.0.0.1:8000", "http://localhost:8000"];
    const explicitIsLocal = isLocalApiBaseUrl(EXPLICIT_API_BASE_URL);
    const activeIsLocal = isLocalApiBaseUrl(activeApiBaseUrl);

    if (isFirebaseHost) {
      if (activeApiBaseUrl && !activeIsLocal) {
        addCandidate(activeApiBaseUrl);
      }
      if (EXPLICIT_API_BASE_URL && !explicitIsLocal) {
        addCandidate(EXPLICIT_API_BASE_URL);
      }
      addCandidate(REMOTE_FALLBACK_API_BASE_URL);
      return candidates;
    }

    if (activeApiBaseUrl) {
      addCandidate(activeApiBaseUrl);
    }

    if (isLoopbackHost(browserHost) || isPrivateIpv4Host(browserHost)) {
      addCandidate(`http://${browserHost}:8000`);
    }

    addCandidate(EXPLICIT_API_BASE_URL);
    localCandidates.forEach(addCandidate);
  } else {
    if (activeApiBaseUrl) {
      addCandidate(activeApiBaseUrl);
    }
    addCandidate(EXPLICIT_API_BASE_URL);
  }

  addCandidate(REMOTE_FALLBACK_API_BASE_URL);
  return candidates;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? undefined);
  const hasBody = init?.body !== undefined && init?.body !== null;
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const authHeader = await getAuthorizationHeaderValue();
  if (authHeader && !headers.has("Authorization")) {
    headers.set("Authorization", authHeader);
  }

  const networkErrors: string[] = [];

  for (const baseUrl of buildApiBaseCandidates()) {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers,
        cache: "no-store",
      });
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : "Falha de rede ao falar com o backend.";
      networkErrors.push(`${baseUrl}: ${message}`);
      continue;
    }

    activeApiBaseUrl = baseUrl;

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

  throw new Error(
    "Backend indisponivel, erro de rede ou resposta bloqueada pelo navegador. "
      + "Isso tambem pode acontecer quando o backend local nao esta acessivel a partir desta aba. "
      + `Bases testadas: ${networkErrors.join(" | ") || "nenhuma"}`,
  );
}

async function getAuthorizationHeaderValue(): Promise<string | null> {
  const currentUser = firebaseAuth.currentUser;
  if (!currentUser) {
    return null;
  }
  const token = await currentUser.getIdToken();
  return token ? `Bearer ${token}` : null;
}

export async function getAuthMe(): Promise<AuthenticatedAccount> {
  return request<AuthenticatedAccount>("/api/auth/me");
}

export async function checkUsernameAvailability(username: string): Promise<UsernameAvailability> {
  return request<UsernameAvailability>(`/api/auth/check-username?username=${encodeURIComponent(username)}`);
}

export async function registerAuthenticatedAccount(username: string): Promise<AuthenticatedAccount> {
  return request<AuthenticatedAccount>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
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

export async function getProactiveSettings(): Promise<ProactivePreferences> {
  return request<ProactivePreferences>("/api/whatsapp-agent/proactivity/settings");
}

export async function updateProactiveSettings(input: Partial<ProactivePreferences>): Promise<ProactivePreferences> {
  return request<ProactivePreferences>("/api/whatsapp-agent/proactivity/settings", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function listProactiveCandidates(
  limit = 30,
  statuses: ProactiveCandidateStatus[] = [],
): Promise<ProactiveCandidate[]> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  statuses.forEach((status) => params.append("status", status));
  const response = await request<{ candidates: ProactiveCandidate[] }>(
    `/api/whatsapp-agent/proactivity/candidates?${params.toString()}`,
  );
  return response.candidates;
}

export async function dismissProactiveCandidate(candidateId: string): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>(`/api/whatsapp-agent/proactivity/candidates/${encodeURIComponent(candidateId)}/dismiss`, {
    method: "POST",
  });
}

export async function confirmProactiveCandidate(candidateId: string): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>(`/api/whatsapp-agent/proactivity/candidates/${encodeURIComponent(candidateId)}/confirm`, {
    method: "POST",
  });
}

export async function completeProactiveCandidate(candidateId: string): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>(`/api/whatsapp-agent/proactivity/candidates/${encodeURIComponent(candidateId)}/complete`, {
    method: "POST",
  });
}

export async function listProactiveDeliveries(limit = 20): Promise<ProactiveDeliveryLog[]> {
  const response = await request<{ deliveries: ProactiveDeliveryLog[] }>(
    `/api/whatsapp-agent/proactivity/deliveries?limit=${limit}`,
  );
  return response.deliveries;
}

export async function runProactiveTick(): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>("/api/whatsapp-agent/proactivity/tick", {
    method: "POST",
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

export async function getMemoryActivity(): Promise<MemoryActivity> {
  return request<MemoryActivity>("/api/memories/activity");
}

export async function getMemoryLiveSummary(): Promise<MemoryLiveSummary> {
  return request<MemoryLiveSummary>("/api/memories/live-summary");
}

export async function getMemorySnapshots(limit = 20): Promise<MemorySnapshot[]> {
  const response = await request<MemorySnapshotsListResponse>(`/api/memories/snapshots?limit=${limit}`);
  return response.snapshots;
}

export async function getAgendaEvents(limit = 120, upcomingOnly = false): Promise<AgendaEvent[]> {
  const query = `?limit=${limit}&upcoming_only=${upcomingOnly ? "true" : "false"}`;
  const response = await request<AgendaEventsListResponse>(`/api/agenda${query}`);
  return response.events;
}

export async function createAgendaEvent(input: CreateAgendaEventInput): Promise<AgendaEvent> {
  return request<AgendaEvent>("/api/agenda", {
    method: "POST",
    body: JSON.stringify({
      titulo: input.titulo,
      inicio: input.inicio,
      fim: input.fim,
      status: input.status ?? "firme",
      contato_origem: input.contato_origem,
      reminder_offset_minutes: input.reminder_offset_minutes ?? 0,
    }),
  });
}

export async function updateAgendaEvent(eventId: string, input: UpdateAgendaEventInput): Promise<AgendaEvent> {
  return request<AgendaEvent>(`/api/agenda/${encodeURIComponent(eventId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function deleteAgendaEvent(eventId: string): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>(`/api/agenda/${encodeURIComponent(eventId)}`, {
    method: "DELETE",
  });
}

export async function getMemoryProjects(): Promise<ProjectMemory[]> {
  return request<ProjectMemory[]>("/api/memories/projects");
}

export async function createMemoryProject(input: CreateProjectMemoryInput): Promise<ProjectMemory> {
  return request<ProjectMemory>("/api/memories/projects", {
    method: "POST",
    body: JSON.stringify({
      project_name: input.project_name,
      summary: input.summary,
      status: input.status ?? "",
      what_is_being_built: input.what_is_being_built ?? "",
      built_for: input.built_for ?? "",
      next_steps: input.next_steps ?? [],
      evidence: input.evidence ?? [],
    }),
  });
}

export async function getMemoryRelations(): Promise<PersonRelation[]> {
  return request<PersonRelation[]>("/api/memories/relations");
}

export async function updateMemoryRelation(
  contactName: string,
  input: {
    contact_name?: string;
    relationship_type?: string;
  },
): Promise<PersonRelation> {
  return request<PersonRelation>(`/api/memories/relations/${encodeURIComponent(contactName)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function updateMemoryProjectCompletion(
  projectKey: string,
  input: { completed: boolean; completion_notes?: string },
): Promise<ProjectMemory> {
  return request<ProjectMemory>(`/api/memories/projects/${encodeURIComponent(projectKey)}`, {
    method: "PUT",
    body: JSON.stringify({
      completed: input.completed,
      completion_notes: input.completion_notes ?? "",
    }),
  });
}

export async function updateMemoryProject(
  projectKey: string,
  input: {
    completed?: boolean;
    completion_notes?: string;
    project_name?: string;
    summary?: string;
    status?: string;
    what_is_being_built?: string;
    built_for?: string;
    next_steps?: string[];
    evidence?: string[];
  },
): Promise<ProjectMemory> {
  return request<ProjectMemory>(`/api/memories/projects/${encodeURIComponent(projectKey)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function assistMemoryProjectEdit(
  projectKey: string,
  instruction: string,
): Promise<ProjectAssistantEditResponse> {
  return request<ProjectAssistantEditResponse>(`/api/memories/projects/${encodeURIComponent(projectKey)}/assist`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export async function deleteMemoryProject(projectKey: string): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>(`/api/memories/projects/${encodeURIComponent(projectKey)}`, {
    method: "DELETE",
  });
}

export async function getMemoryGroups(): Promise<WhatsAppGroupSelection[]> {
  const response = await request<WhatsAppGroupSelectionsListResponse>("/api/memories/groups");
  return response.groups;
}

export async function updateMemoryGroupSelection(
  chatJid: string,
  enabledForAnalysis: boolean,
): Promise<WhatsAppGroupSelection> {
  return request<WhatsAppGroupSelection>(`/api/memories/groups/${encodeURIComponent(chatJid)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled_for_analysis: enabledForAnalysis }),
  });
}

export async function clearSavedDatabase(): Promise<SimpleOkResponse> {
  return request<SimpleOkResponse>("/api/memories/database", {
    method: "DELETE",
  });
}

export async function analyzeMemory(windowHours: number): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>(`/api/memories/analyze?window_hours=${windowHours}`, {
    method: "POST",
  });
}

export async function runFirstMemoryAnalysis(): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/execute", {
    method: "POST",
    body: JSON.stringify({ intent: "first_analysis" }),
  });
}

export async function runNextMemoryBatch(): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/execute", {
    method: "POST",
    body: JSON.stringify({ intent: "improve_memory" }),
  });
}

export async function executeMemoryAnalysis(
  intent?: "first_analysis" | "improve_memory",
): Promise<AnalyzeMemoryResponse> {
  return request<AnalyzeMemoryResponse>("/api/memories/execute", {
    method: "POST",
    body: JSON.stringify(intent ? { intent } : {}),
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
