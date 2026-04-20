import { config } from "./config";
import { GatewayObserverStatus, GatewaySendResult, WhatsAppGatewayChannel } from "./whatsapp";

type ManagedAccountRecord = {
  app_user_id: string;
  username: string;
};

type ManagedObserverChannel = {
  appUserId: string;
  username: string;
  observer: WhatsAppGatewayChannel;
};

type ChannelName = "observer";

export class AuraCoreGatewayManager {
  private readonly users = new Map<string, ManagedObserverChannel>();
  private bootstrapRetryTimer: NodeJS.Timeout | null = null;

  async start(): Promise<void> {
    try {
      await this.bootstrapActiveAccounts();
      this.clearBootstrapRetryTimer();
    } catch (error) {
      this.scheduleBootstrapRetry();
      throw error;
    }
  }

  getStatus(appUserId: string, username: string, channelName: ChannelName): GatewayObserverStatus {
    const managed = this.users.get(appUserId);
    if (!managed) {
      return this.buildIdleStatus(appUserId, username, channelName);
    }
    return managed.observer.getStatus();
  }

  async connect(appUserId: string, username: string, _channelName: ChannelName): Promise<GatewayObserverStatus> {
    const managed = this.getOrCreateUser(appUserId, username);
    return managed.observer.connectSession();
  }

  async reset(appUserId: string, username: string, _channelName: ChannelName): Promise<GatewayObserverStatus> {
    const managed = this.getOrCreateUser(appUserId, username);
    await managed.observer.resetSession();
    return managed.observer.getStatus();
  }

  async refreshObserverHistory(appUserId: string, username: string): Promise<GatewayObserverStatus> {
    const managed = this.getOrCreateUser(appUserId, username);
    return managed.observer.refreshDirectHistory();
  }

  async sendTextMessage(
    appUserId: string,
    username: string,
    _channelName: ChannelName,
    chatJid: string,
    messageText: string,
  ): Promise<GatewaySendResult> {
    const managed = this.getOrCreateUser(appUserId, username);
    return managed.observer.sendTextMessage(chatJid, messageText);
  }

  async shutdown(): Promise<void> {
    this.clearBootstrapRetryTimer();
    await Promise.all(Array.from(this.users.values()).map((managed) => managed.observer.shutdown()));
    this.users.clear();
  }

  private getOrCreateUser(appUserId: string, username: string): ManagedObserverChannel {
    const existing = this.users.get(appUserId);
    if (existing) {
      return existing;
    }
    const safeUsername = this.normalizeUsername(username, appUserId);
    const managed: ManagedObserverChannel = {
      appUserId,
      username: safeUsername,
      observer: new WhatsAppGatewayChannel(
        {
          kind: "user",
          appUserId,
        },
        "observer",
        `${appUserId}:observer`,
        this.buildInstanceName(safeUsername, "observer"),
      ),
    };
    this.users.set(appUserId, managed);
    return managed;
  }

  private buildIdleStatus(appUserId: string, username: string, channelName: ChannelName): GatewayObserverStatus {
    const safeUsername = this.normalizeUsername(username, appUserId);
    return {
      instance_name: this.buildInstanceName(safeUsername, channelName),
      connected: false,
      state: "close",
      owner_number: null,
      qr_code: null,
      qr_expires_in_sec: null,
      last_seen_at: new Date().toISOString(),
      last_error: null,
    };
  }

  private buildInstanceName(username: string, channelName: ChannelName): string {
    return `${username}-${channelName}`;
  }

  private normalizeUsername(username: string, fallback: string): string {
    const normalized = username.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
    return normalized || fallback.replace(/[^a-z0-9_]+/gi, "_").toLowerCase();
  }

  private async bootstrapActiveAccounts(): Promise<void> {
    const response = await fetch(`${config.auracoreApiBaseUrl}/api/internal/accounts/active`, {
      method: "GET",
      headers: {
        "x-internal-api-token": config.internalApiToken,
      },
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Failed to bootstrap active AuraCore accounts (${response.status}): ${detail}`);
    }

    const payload = (await response.json()) as { accounts?: ManagedAccountRecord[] };
    for (const account of payload.accounts ?? []) {
      const appUserId = String(account?.app_user_id ?? "").trim();
      const username = String(account?.username ?? "").trim();
      if (!appUserId || !username) {
        continue;
      }
      const managed = this.getOrCreateUser(appUserId, username);
      await managed.observer.start();
    }
  }

  private scheduleBootstrapRetry(): void {
    if (this.bootstrapRetryTimer) {
      return;
    }
    this.bootstrapRetryTimer = setTimeout(() => {
      this.bootstrapRetryTimer = null;
      void this.start().catch((error) => {
        console.error("AuraCore gateway bootstrap retry failed", error);
      });
    }, 10_000);
  }

  private clearBootstrapRetryTimer(): void {
    if (!this.bootstrapRetryTimer) {
      return;
    }
    clearTimeout(this.bootstrapRetryTimer);
    this.bootstrapRetryTimer = null;
  }
}
