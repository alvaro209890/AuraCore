import makeWASocket, {
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  extractMessageContent,
  type proto,
  type WASocket,
} from "@whiskeysockets/baileys";
import { randomUUID } from "node:crypto";

import Pino from "pino";
import QRCode from "qrcode";

import { config } from "./config";
import { SupabaseAuthStateStore } from "./supabase-auth-state";

const logger = Pino({ level: config.nodeEnv === "development" ? "debug" : "info" });
const baileysLogger = Pino({ level: "silent" });

export type ObserverState = "open" | "connecting" | "close";

export type GatewayObserverStatus = {
  instance_name: string;
  connected: boolean;
  state: ObserverState | string;
  owner_number: string | null;
  qr_code: string | null;
  qr_expires_in_sec: number | null;
  last_seen_at: string;
  last_error: string | null;
};

type IngestMessagePayload = {
  message_id: string;
  direction: "inbound" | "outbound";
  contact_name: string;
  chat_jid: string;
  contact_phone: string;
  message_text: string;
  timestamp: string;
  source: "baileys";
};

function isGroupJid(jid: string | null | undefined): boolean {
  return Boolean(jid && jid.endsWith("@g.us"));
}

function isStatusJid(jid: string | null | undefined): boolean {
  return jid === "status@broadcast";
}

function isBroadcastJid(jid: string | null | undefined): boolean {
  return Boolean(jid && jid.endsWith("@broadcast"));
}

function isNewsletterJid(jid: string | null | undefined): boolean {
  return Boolean(jid && jid.endsWith("@newsletter"));
}

function jidToPhone(jid: string | null | undefined): string {
  if (!jid) return "";
  const userPart = jid.split("@")[0] ?? "";
  const phoneOnly = userPart.split(":")[0] ?? "";
  return phoneOnly.replace(/[^\d]/g, "");
}

function isDirectUserJid(jid: string | null | undefined): boolean {
  return Boolean(
    jid &&
      !isGroupJid(jid) &&
      !isStatusJid(jid) &&
      !isBroadcastJid(jid) &&
      !isNewsletterJid(jid),
  );
}

function extractMessageText(message: proto.IWebMessageInfo): string {
  const payload = extractMessageContent(message.message);
  if (!payload) return "";

  if (payload.conversation) return payload.conversation;
  if (payload.extendedTextMessage?.text) return payload.extendedTextMessage.text;
  if (payload.imageMessage?.caption) return payload.imageMessage.caption;
  if (payload.videoMessage?.caption) return payload.videoMessage.caption;
  if (payload.documentMessage?.caption) return payload.documentMessage.caption;
  if (payload.buttonsResponseMessage?.selectedDisplayText) {
    return payload.buttonsResponseMessage.selectedDisplayText;
  }
  if (payload.listResponseMessage?.title) return payload.listResponseMessage.title;
  if (payload.templateButtonReplyMessage?.selectedDisplayText) {
    return payload.templateButtonReplyMessage.selectedDisplayText;
  }
  return "";
}

function toIsoTimestamp(rawValue: unknown): string {
  if (typeof rawValue === "number") {
    return new Date(rawValue * 1000).toISOString();
  }

  if (typeof rawValue === "string" && /^\d+$/.test(rawValue)) {
    return new Date(Number(rawValue) * 1000).toISOString();
  }

  const candidateNumber = Number(rawValue);
  if (Number.isFinite(candidateNumber) && candidateNumber > 0) {
    return new Date(candidateNumber * 1000).toISOString();
  }

  return new Date().toISOString();
}

function asDisconnectCode(error: unknown): number | null {
  const statusCode = (error as { output?: { statusCode?: number } } | undefined)?.output?.statusCode;
  return typeof statusCode === "number" ? statusCode : null;
}

export class WhatsAppObserverGateway {
  private readonly authStore = new SupabaseAuthStateStore(
    config.instanceName,
    config.supabaseUrl,
    config.supabaseServiceRoleKey,
    logger,
  );
  private socket: WASocket | null = null;
  private state: ObserverState = "connecting";
  private connected = false;
  private ownerNumber: string | null = null;
  private qrText: string | null = null;
  private qrDataUrl: string | null = null;
  private qrGeneratedAt: number | null = null;
  private lastError: string | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private allowReconnect = true;
  private running = false;
  private connectionEpoch = 0;
  private readonly processedIds = new Set<string>();
  private readonly processedOrder: string[] = [];
  private readonly knownContactNames = new Map<string, string>();

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    await this.connect();
  }

  async shutdown(): Promise<void> {
    this.running = false;
    this.allowReconnect = false;
    this.clearReconnectTimer();
    await this.cleanupSocket(false);
  }

  getStatus(): GatewayObserverStatus {
    return {
      instance_name: config.instanceName,
      connected: this.connected,
      state: this.state,
      owner_number: this.ownerNumber,
      qr_code: this.getActiveQrCode(),
      qr_expires_in_sec: this.getQrExpiresInSeconds(),
      last_seen_at: new Date().toISOString(),
      last_error: this.lastError,
    };
  }

  async connectObserver(): Promise<GatewayObserverStatus> {
    if (!this.running) {
      await this.start();
      return this.getStatus();
    }

    const activeQr = this.getActiveQrCode();
    if (this.connected || activeQr) {
      return this.getStatus();
    }

    await this.resetSession();
    return this.getStatus();
  }

  async resetSession(): Promise<void> {
    logger.warn("Resetting WhatsApp observer session.");
    this.allowReconnect = false;
    this.clearReconnectTimer();
    await this.cleanupSocket(false);
    await this.authStore.clearSession();
    this.clearQr();
    this.connected = false;
    this.state = "connecting";
    this.ownerNumber = null;
    this.lastError = "session_reset";
    this.allowReconnect = true;
    await this.connect();
  }

  async refreshDirectHistory(): Promise<GatewayObserverStatus> {
    this.resetProcessedMessageCache();

    if (!this.running) {
      await this.start();
      return this.getStatus();
    }

    this.lastError = null;
    await this.connect();
    return this.getStatus();
  }

  private async connect(): Promise<void> {
    const epoch = ++this.connectionEpoch;
    this.connected = false;
    this.state = "connecting";
    await this.cleanupSocket(false);

    const { state, saveCreds } = await this.authStore.useAuthState();

    let version: [number, number, number];
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch (error) {
      logger.warn({ error }, "Failed to fetch latest Baileys version, using fallback.");
      version = [2, 3000, 1017531287];
    }

    const socket = makeWASocket({
      auth: state,
      version,
      logger: baileysLogger,
      printQRInTerminal: false,
      syncFullHistory: true,
      shouldIgnoreJid: (jid) => !isDirectUserJid(jid),
      browser: Browsers.macOS(`AuraCore-${config.instanceName}`),
    });

    this.socket = socket;

    socket.ev.on("creds.update", () => {
      if (this.connectionEpoch !== epoch) return;
      void saveCreds();
    });

    socket.ev.on("connection.update", (update) => {
      if (this.connectionEpoch !== epoch) return;
      void this.handleConnectionUpdate(update);
    });

    socket.ev.on("messages.upsert", (upsert) => {
      if (this.connectionEpoch !== epoch) return;
      void this.handleMessagesUpsert(upsert as { messages: proto.IWebMessageInfo[]; type: string });
    });

    socket.ev.on("messaging-history.set", (historySet) => {
      if (this.connectionEpoch !== epoch) return;
      void this.handleHistorySync(historySet as { messages: proto.IWebMessageInfo[]; isLatest?: boolean });
    });
  }

  private async handleConnectionUpdate(update: {
    connection?: string;
    qr?: string;
    lastDisconnect?: { error?: unknown };
  }): Promise<void> {
    if (update.qr) {
      this.qrText = update.qr;
      this.qrDataUrl = await QRCode.toDataURL(update.qr);
      this.qrGeneratedAt = Date.now();
      this.state = "connecting";
      this.connected = false;
      this.lastError = null;
      logger.info("WhatsApp QR code generated.");
    }

    if (update.connection === "open") {
      this.clearReconnectTimer();
      this.connected = true;
      this.state = "open";
      this.ownerNumber = jidToPhone(this.socket?.user?.id);
      this.lastError = null;
      this.clearQr();
      logger.info({ ownerNumber: this.ownerNumber }, "WhatsApp observer connected.");
      return;
    }

    if (update.connection === "close") {
      const disconnectCode = asDisconnectCode(update.lastDisconnect?.error);
      const shouldReconnect =
        this.running &&
        this.allowReconnect &&
        disconnectCode !== DisconnectReason.loggedOut;

      this.connected = false;
      this.state = "close";
      this.clearQr();
      this.lastError =
        disconnectCode === DisconnectReason.loggedOut
          ? "logged_out"
          : update.lastDisconnect?.error instanceof Error
            ? update.lastDisconnect.error.message
            : "connection_closed";

      logger.warn(
        { disconnectCode, lastError: this.lastError, shouldReconnect },
        "WhatsApp observer connection closed.",
      );

      if (shouldReconnect) {
        this.scheduleReconnect();
      }
    }
  }

  private async handleMessagesUpsert(upsert: {
    messages: proto.IWebMessageInfo[];
    type: string;
  }): Promise<void> {
    await this.ingestMessages(upsert.messages, "live_upsert");
  }

  private async handleHistorySync(historySet: {
    messages: proto.IWebMessageInfo[];
    isLatest?: boolean;
  }): Promise<void> {
    await this.ingestMessages(historySet.messages, historySet.isLatest ? "history_sync_latest" : "history_sync");
  }

  private async ingestMessages(
    messages: proto.IWebMessageInfo[] | undefined,
    sourceEvent: string,
  ): Promise<void> {
    if (!messages || messages.length === 0) {
      return;
    }

    const batch: IngestMessagePayload[] = [];
    for (const message of messages) {
      const normalized = this.normalizeMessage(message);
      if (normalized) {
        batch.push(normalized);
      }
    }

    if (batch.length === 0) {
      logger.debug({ sourceEvent, candidateCount: messages.length }, "No analyzable direct text messages in batch.");
      return;
    }

    try {
      const response = await fetch(`${config.auracoreApiBaseUrl}/api/internal/observer/messages/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-internal-api-token": config.internalApiToken,
        },
        body: JSON.stringify({ messages: batch }),
      });

      if (!response.ok) {
        const detail = await response.text();
        logger.error(
          { sourceEvent, count: batch.length, status: response.status, detail },
          "AuraCore backend rejected the message batch.",
        );
        return;
      }

      logger.info({ sourceEvent, count: batch.length }, "Delivered message batch to AuraCore backend.");
    } catch (error) {
      logger.error({ error, sourceEvent, count: batch.length }, "Failed to deliver messages to AuraCore backend.");
    }
  }

  private normalizeMessage(message: proto.IWebMessageInfo): IngestMessagePayload | null {
    const key = message.key;
    if (!key || !key.id || !key.remoteJid) {
      return null;
    }

    if (this.isDuplicate(key.id)) {
      return null;
    }

    const remoteJid = String(key.remoteJid);
    if (!isDirectUserJid(remoteJid)) {
      return null;
    }

    const messageText = extractMessageText(message).trim();
    if (!messageText) {
      return null;
    }

    const contactPhone = jidToPhone(remoteJid);
    if (!contactPhone) {
      return null;
    }

    const contactName = this.resolveContactName(message, remoteJid, contactPhone);
    return {
      message_id: key.id,
      direction: key.fromMe ? "outbound" : "inbound",
      contact_name: contactName || contactPhone,
      chat_jid: remoteJid,
      contact_phone: contactPhone,
      message_text: messageText,
      timestamp: toIsoTimestamp(message.messageTimestamp),
      source: "baileys",
    };
  }

  private resolveContactName(
    message: proto.IWebMessageInfo,
    remoteJid: string,
    contactPhone: string,
  ): string {
    const socketWithContacts = this.socket as
      | (WASocket & {
          contacts?: Record<
            string,
            {
              name?: string | null;
              notify?: string | null;
              verifiedName?: string | null;
              verifiedBizName?: string | null;
            }
          >;
        })
      | null;
    const contact = socketWithContacts?.contacts?.[remoteJid];
    const cachedName = this.knownContactNames.get(contactPhone);
    const candidates = [
      message.pushName,
      contact?.name,
      contact?.notify,
      contact?.verifiedName,
      contact?.verifiedBizName,
      cachedName,
      contactPhone,
    ];

    for (const candidate of candidates) {
      const text = String(candidate ?? "").trim();
      if (!text) {
        continue;
      }
      if (text !== contactPhone) {
        this.knownContactNames.set(contactPhone, text);
      }
      return text;
    }

    return contactPhone;
  }

  private isDuplicate(messageId: string): boolean {
    if (this.processedIds.has(messageId)) {
      return true;
    }

    this.processedIds.add(messageId);
    this.processedOrder.push(messageId);
    if (this.processedOrder.length > 5000) {
      const oldest = this.processedOrder.shift();
      if (oldest) {
        this.processedIds.delete(oldest);
      }
    }
    return false;
  }

  private resetProcessedMessageCache(): void {
    this.processedIds.clear();
    this.processedOrder.length = 0;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect().catch((error) => {
        logger.error({ error }, "Failed to reconnect WhatsApp observer.");
        this.scheduleReconnect();
      });
    }, config.reconnectDelayMs);
  }

  private clearReconnectTimer(): void {
    if (!this.reconnectTimer) return;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
  }

  private clearQr(): void {
    this.qrText = null;
    this.qrDataUrl = null;
    this.qrGeneratedAt = null;
  }

  private getActiveQrCode(): string | null {
    const expiresIn = this.getQrExpiresInSeconds();
    if (!this.qrDataUrl || expiresIn === null || expiresIn <= 0) {
      return null;
    }
    return this.qrDataUrl;
  }

  private getQrExpiresInSeconds(): number | null {
    if (!this.qrGeneratedAt) {
      return null;
    }
    const elapsedSeconds = Math.floor((Date.now() - this.qrGeneratedAt) / 1000);
    return Math.max(0, config.qrExpiresSeconds - elapsedSeconds);
  }

  private async cleanupSocket(logout: boolean): Promise<void> {
    if (!this.socket) return;

    try {
      if (logout && this.connected) {
        await this.socket.logout();
      }
    } catch (error) {
      logger.warn({ error }, "Failed to logout WhatsApp socket cleanly.");
    }

    try {
      this.socket.ev.removeAllListeners("connection.update");
      this.socket.ev.removeAllListeners("creds.update");
      this.socket.ev.removeAllListeners("messages.upsert");
      this.socket.ev.removeAllListeners("messaging-history.set");
      (this.socket as unknown as { ws?: { close: () => void } }).ws?.close();
    } catch {
      // Ignore cleanup errors.
    }

    this.socket = null;
  }
}

export function buildGatewayRunId(): string {
  return randomUUID();
}
