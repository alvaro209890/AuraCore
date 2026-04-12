import { firebaseAuth } from "./firebase";

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

export type GlobalAgentStatus = {
  instance_name: string;
  connected: boolean;
  state: string;
  gateway_ready: boolean;
  routing_mode: "observer_owner_phone";
  owner_number: string | null;
  qr_code: string | null;
  qr_expires_in_sec: number | null;
  last_seen_at: string | null;
  last_error: string | null;
  current_username: string | null;
  current_user_observer_phone: string | null;
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
        // noop
      }
      throw new Error(detail);
    }

    return (await response.json()) as T;
  }

  throw new Error(
    "Backend indisponivel, erro de rede ou resposta bloqueada pelo navegador. "
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

export async function getObserverStatus(refreshQr = false): Promise<ObserverStatus> {
  const query = refreshQr ? "?refresh_qr=true" : "";
  return request<ObserverStatus>(`/api/observer/status${query}`);
}

export async function getGlobalAgentStatus(): Promise<GlobalAgentStatus> {
  return request<GlobalAgentStatus>("/api/global-agent/status");
}

export async function connectGlobalAgent(): Promise<GlobalAgentStatus> {
  return request<GlobalAgentStatus>("/api/global-agent/connect", {
    method: "POST",
  });
}

export async function resetGlobalAgent(): Promise<GlobalAgentStatus> {
  return request<GlobalAgentStatus>("/api/global-agent/reset", {
    method: "POST",
  });
}
