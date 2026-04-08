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
} from "@whiskeysockets/baileys";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Logger } from "pino";

type SessionRow = {
  session_id: string;
  creds: unknown;
};

type SessionKeyRow = {
  session_id: string;
  category: string;
  key_id: string;
  value: unknown;
  updated_at?: string;
};

function serializeForJson(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value, BufferJSON.replacer));
}

function deserializeFromJson<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value), BufferJSON.reviver) as T;
}

export class SupabaseAuthStateStore {
  private readonly client: SupabaseClient;
  private readonly logger: Logger;

  constructor(
    private readonly sessionId: string,
    supabaseUrl: string,
    supabaseKey: string,
    logger: Logger,
  ) {
    this.client = createClient(supabaseUrl, supabaseKey, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
      },
    });
    this.logger = logger;
  }

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
    const keysDelete = await this.client.from("wa_session_keys").delete().eq("session_id", this.sessionId);
    if (keysDelete.error) {
      throw new Error(`Failed to clear WhatsApp session keys: ${keysDelete.error.message}`);
    }

    const sessionDelete = await this.client.from("wa_sessions").delete().eq("session_id", this.sessionId);
    if (sessionDelete.error) {
      throw new Error(`Failed to clear WhatsApp session creds: ${sessionDelete.error.message}`);
    }
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

        const response = await this.client
          .from("wa_session_keys")
          .select("key_id,value")
          .eq("session_id", this.sessionId)
          .eq("category", type)
          .in("key_id", ids);

        if (response.error) {
          throw new Error(`Failed to load WhatsApp auth keys: ${response.error.message}`);
        }

        for (const row of (response.data ?? []) as Array<Pick<SessionKeyRow, "key_id" | "value">>) {
          const parsedValue = deserializeFromJson<SignalDataTypeMap[T]>(row.value);
          data[row.key_id] =
            type === "app-state-sync-key"
              ? (proto.Message.AppStateSyncKeyData.fromObject(parsedValue as object) as unknown as SignalDataTypeMap[T])
              : parsedValue;
        }

        return data;
      },

      set: async (data: SignalDataSet): Promise<void> => {
        const upserts: SessionKeyRow[] = [];
        const deletesByCategory = new Map<string, string[]>();

        for (const [category, categoryValues] of Object.entries(data)) {
          if (!categoryValues) {
            continue;
          }

          for (const [keyId, value] of Object.entries(categoryValues)) {
            if (value) {
              upserts.push({
                session_id: this.sessionId,
                category,
                key_id: keyId,
                value: serializeForJson(value),
                updated_at: new Date().toISOString(),
              });
            } else {
              const ids = deletesByCategory.get(category) ?? [];
              ids.push(keyId);
              deletesByCategory.set(category, ids);
            }
          }
        }

        if (upserts.length) {
          const upsertResponse = await this.client.from("wa_session_keys").upsert(upserts, {
            onConflict: "session_id,category,key_id",
          });
          if (upsertResponse.error) {
            throw new Error(`Failed to store WhatsApp auth keys: ${upsertResponse.error.message}`);
          }
        }

        for (const [category, ids] of deletesByCategory.entries()) {
          const deleteResponse = await this.client
            .from("wa_session_keys")
            .delete()
            .eq("session_id", this.sessionId)
            .eq("category", category)
            .in("key_id", ids);

          if (deleteResponse.error) {
            throw new Error(`Failed to delete WhatsApp auth keys: ${deleteResponse.error.message}`);
          }
        }
      },

      clear: async (): Promise<void> => {
        await this.clearSession();
      },
    };
  }

  private async loadCreds(): Promise<AuthenticationCreds> {
    const response = await this.client
      .from("wa_sessions")
      .select("session_id,creds")
      .eq("session_id", this.sessionId)
      .maybeSingle();

    if (response.error) {
      throw new Error(`Failed to load WhatsApp auth creds: ${response.error.message}`);
    }

    if (!response.data?.creds) {
      const creds = initAuthCreds();
      await this.persistCreds(creds);
      return creds;
    }

    return deserializeFromJson<AuthenticationCreds>((response.data as SessionRow).creds);
  }

  private async persistCreds(creds: AuthenticationCreds): Promise<void> {
    const response = await this.client.from("wa_sessions").upsert(
      {
        session_id: this.sessionId,
        creds: serializeForJson(creds),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "session_id" },
    );

    if (response.error) {
      throw new Error(`Failed to store WhatsApp auth creds: ${response.error.message}`);
    }
  }
}
