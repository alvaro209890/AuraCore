import dotenv from "dotenv";

dotenv.config();

function getRequired(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function getOptional(name: string, fallback: string): string {
  return process.env[name]?.trim() || fallback;
}

function parseInteger(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue || rawValue.trim().length === 0) {
    return fallback;
  }

  const parsed = Number(rawValue);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid integer environment variable: ${name}`);
  }
  return parsed;
}

function normalizeUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export const config = {
  port: parseInteger("PORT", 10001),
  nodeEnv: getOptional("NODE_ENV", "development"),
  instanceName: getOptional("INSTANCE_NAME", "observer"),
  observerInstanceName: getOptional("OBSERVER_INSTANCE_NAME", getOptional("INSTANCE_NAME", "observer")),
  agentInstanceName: getOptional("AGENT_INSTANCE_NAME", "agent"),
  supabaseUrl: normalizeUrl(getRequired("SUPABASE_URL")),
  supabaseServiceRoleKey: getRequired("SUPABASE_SERVICE_ROLE_KEY"),
  auracoreApiBaseUrl: normalizeUrl(getRequired("AURACORE_API_BASE_URL")),
  internalApiToken: getRequired("INTERNAL_API_TOKEN"),
  qrExpiresSeconds: parseInteger("QR_EXPIRES_SECONDS", 60),
  reconnectDelayMs: parseInteger("RECONNECT_DELAY_MS", 5000),
};
