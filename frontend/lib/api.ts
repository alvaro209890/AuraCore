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

export type AnalyzeMemoryResponse = {
  current: MemoryCurrent;
  snapshot: MemorySnapshot;
};

export type MemorySnapshotsListResponse = {
  snapshots: MemorySnapshot[];
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
