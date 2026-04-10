import {
  BufferJSON,
  initAuthCreds,
  makeCacheableSignalKeyStore,
  proto,
  type AuthenticationCreds,
  type AuthenticationState,
  type SignalDataSet,
  type SignalDataTypeMap,
  type SignalKeyStore,
} from "./baileys-runtime";
import type { Logger } from "pino";

type SessionCredsResponse = {
  creds?: unknown;
};

type SessionKeysResponse = {
  values?: Record<string, unknown>;
};

function serializeForJson(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value, BufferJSON.replacer));
}

function deserializeFromJson<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value), BufferJSON.reviver) as T;
}

export class AuraCoreAuthStateStore {
  constructor(
    private readonly sessionId: string,
    private readonly auracoreApiBaseUrl: string,
    private readonly internalApiToken: string,
    private readonly logger: Logger,
  ) {}

  async useAuthState(): Promise<{
    state: AuthenticationState;
    saveCreds: () => Promise<void>;
  }> {
    const creds = await this.loadCreds();
    const keyStore = makeCacheableSignalKeyStore(this.buildKeyStore(), this.logger);

    return {
      state: {
        creds,
        keys: keyStore,
      },
      saveCreds: async () => {
        await this.persistCreds(creds);
      },
    };
  }

  async clearSession(): Promise<void> {
    await this.request(`/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}`, {
      method: "DELETE",
    });
  }

  private buildKeyStore(): SignalKeyStore {
    return {
      get: async <T extends keyof SignalDataTypeMap>(
        type: T,
        ids: string[],
      ): Promise<{ [id: string]: SignalDataTypeMap[T] }> => {
        const data = {} as { [id: string]: SignalDataTypeMap[T] };
        if (!ids.length) {
          return data;
        }

        const response = await this.request<SessionKeysResponse>(
          `/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}/keys/load`,
          {
            method: "POST",
            body: JSON.stringify({
              category: type,
              ids,
            }),
          },
        );

        for (const [keyId, value] of Object.entries(response.values ?? {})) {
          const parsedValue = deserializeFromJson<SignalDataTypeMap[T]>(value);
          data[keyId] =
            type === "app-state-sync-key"
              ? (proto.Message.AppStateSyncKeyData.fromObject(parsedValue as object) as unknown as SignalDataTypeMap[T])
              : parsedValue;
        }

        return data;
      },

      set: async (data: SignalDataSet): Promise<void> => {
        const updatesByCategory = new Map<string, Record<string, unknown>>();
        const deletesByCategory = new Map<string, string[]>();

        for (const [category, categoryValues] of Object.entries(data)) {
          if (!categoryValues) {
            continue;
          }

          for (const [keyId, value] of Object.entries(categoryValues)) {
            if (value) {
              const current = updatesByCategory.get(category) ?? {};
              current[keyId] = serializeForJson(value);
              updatesByCategory.set(category, current);
            } else {
              const ids = deletesByCategory.get(category) ?? [];
              ids.push(keyId);
              deletesByCategory.set(category, ids);
            }
          }
        }

        for (const [category, values] of updatesByCategory.entries()) {
          await this.request(`/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}/keys`, {
            method: "PUT",
            body: JSON.stringify({
              category,
              values,
            }),
          });
        }

        for (const [category, ids] of deletesByCategory.entries()) {
          await this.request(`/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}/keys/delete`, {
            method: "POST",
            body: JSON.stringify({
              category,
              ids,
            }),
          });
        }
      },

      clear: async (): Promise<void> => {
        await this.clearSession();
      },
    };
  }

  private async loadCreds(): Promise<AuthenticationCreds> {
    const response = await this.request<SessionCredsResponse>(
      `/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}/creds`,
      { method: "GET" },
    );

    if (!response.creds) {
      const creds = initAuthCreds();
      await this.persistCreds(creds);
      return creds;
    }

    return deserializeFromJson<AuthenticationCreds>(response.creds);
  }

  private async persistCreds(creds: AuthenticationCreds): Promise<void> {
    await this.request(`/api/internal/storage/wa-sessions/${encodeURIComponent(this.sessionId)}/creds`, {
      method: "PUT",
      body: JSON.stringify({
        creds: serializeForJson(creds),
      }),
    });
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await fetch(`${this.auracoreApiBaseUrl}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        "x-internal-api-token": this.internalApiToken,
        ...(init.headers ?? {}),
      },
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`AuraCore auth storage request failed (${response.status}): ${detail}`);
    }

    return (await response.json()) as T;
  }
}
