import makeWASocket, {
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  extractMessageContent,
  type WASocket,
  type BaileysProto,
} from "./baileys-runtime";
import { randomUUID } from "node:crypto";

import Pino from "pino";
import QRCode from "qrcode";

import { AuraCoreAuthStateStore } from "./auracore-auth-state";
import { config } from "./config";

const logger = Pino({ level: config.nodeEnv === "development" ? "debug" : "info" });
const baileysLogger = Pino({ level: "silent" });

export type ObserverState = "open" | "connecting" | "reconnecting" | "close";

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

export type GatewaySendResult = {
  message_id: string | null;
  timestamp: string | null;
};

type ContactNameSource =
  | "saved_contact"
  | "verified_name"
  | "verified_business"
  | "push_name"
  | "cached_history"
  | "phone";

type IngestMessagePayload = {
  message_id: string;
  chat_type: "direct" | "group";
  chat_name: string;
  direction: "inbound" | "outbound";
  from_me: boolean;
  contact_name: string;
  contact_name_source: string;
  chat_jid: string;
  contact_phone: string | null;
  participant_name: string | null;
  participant_phone: string | null;
  participant_jid: string | null;
  message_text: string;
  timestamp: string;
  source: "baileys";
  source_event: string;
};

type ContactProfile = {
  name?: string | null;
  notify?: string | null;
  verifiedName?: string | null;
  verifiedBizName?: string | null;
  subject?: string | null;
};

type GatewayContactLike = ContactProfile & {
  id?: string | null;
  lid?: string | null;
};

type GatewayHistorySync = {
  messages: BaileysProto.IWebMessageInfo[];
  isLatest?: boolean;
  contacts?: GatewayContactLike[];
};

type GatewayGroupMetadata = {
  id?: string | null;
  subject?: string | null;
  notify?: string | null;
  name?: string | null;
};

type MessageKeyWithLid = BaileysProto.IMessageKey & {
  participantPn?: string | null;
  remoteJidAlt?: string | null;
};

type BufferedLidMessage = {
  message: BaileysProto.IWebMessageInfo;
  sourceEvent: string;
  bufferedAt: number;
};

type PendingBackendBatch = {
  messages: IngestMessagePayload[];
  sourceEvent: string;
  queuedAt: number;
  attempts: number;
};

const LID_BUFFER_TTL_MS = 30_000;
const LID_BUFFER_MAX_PER_JID = 32;
const SENT_MESSAGE_CACHE_MAX = 100;

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

function extractMessageText(message: BaileysProto.IWebMessageInfo): string {
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

export class WhatsAppGatewayChannel {
  private readonly authStore: AuraCoreAuthStateStore;
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
  private readonly knownContactNameSources = new Map<string, string>();
  private readonly lidToPhoneJid = new Map<string, string>();
  private readonly pendingLidMessages = new Map<string, BufferedLidMessage[]>();
  private readonly sentMessagesCache = new Map<string, BaileysProto.IMessage>();
  private readonly pendingBackendBatches: PendingBackendBatch[] = [];
  private readonly knownGroupNames = new Map<string, string>();
  private backendRetryTimer: NodeJS.Timeout | null = null;
  private backendDeliveryInFlight = false;

  constructor(
    private readonly channelName: "observer" | "agent",
    private readonly sessionId: string,
    private readonly instanceName: string,
  ) {
    this.authStore = new AuraCoreAuthStateStore(
      sessionId,
      config.auracoreApiBaseUrl,
      config.internalApiToken,
      logger,
    );
  }

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
    this.clearBackendRetryTimer();
  }

  getStatus(): GatewayObserverStatus {
    return {
      instance_name: this.instanceName,
      connected: this.connected,
      state: this.state,
      owner_number: this.ownerNumber,
      qr_code: this.getActiveQrCode(),
      qr_expires_in_sec: this.getQrExpiresInSeconds(),
      last_seen_at: new Date().toISOString(),
      last_error: this.lastError,
    };
  }

  async connectSession(): Promise<GatewayObserverStatus> {
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
    logger.warn({ channel: this.channelName }, "Resetting WhatsApp session.");
    this.allowReconnect = false;
    this.clearReconnectTimer();
    await this.cleanupSocket(false);
    await this.authStore.clearSession();
    this.clearQr();
    this.connected = false;
    this.state = "connecting";
    this.ownerNumber = null;
    this.lastError = "session_reset";
    this.lidToPhoneJid.clear();
    this.pendingLidMessages.clear();
    this.knownGroupNames.clear();
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
      syncFullHistory: this.channelName === "observer",
      shouldIgnoreJid: (jid) => {
        if (isStatusJid(jid) || isBroadcastJid(jid) || isNewsletterJid(jid)) {
          return true;
        }
        if (this.channelName === "observer") {
          return false;
        }
        return !isDirectUserJid(jid);
      },
      browser: Browsers.macOS(`AuraCore-${this.instanceName}`),
      // Let Baileys recover linked-device decrypt retries that show up as
      // "Aguardando mensagem" by looking up the original outgoing payload.
      getMessage: async (key) => {
        if (key.id && this.sentMessagesCache.has(key.id)) {
          return this.sentMessagesCache.get(key.id);
        }
        return undefined;
      },
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
      void this.handleMessagesUpsert(upsert as { messages: BaileysProto.IWebMessageInfo[]; type: string });
    });

    socket.ev.on("contacts.upsert", (contacts) => {
      if (this.connectionEpoch !== epoch) return;
      this.absorbContactLidMappings(contacts as GatewayContactLike[], "contacts_upsert");
    });

    socket.ev.on("contacts.update", (contacts) => {
      if (this.connectionEpoch !== epoch) return;
      this.absorbContactLidMappings(contacts as GatewayContactLike[], "contacts_update");
    });

    socket.ev.on("messaging-history.set", (historySet) => {
      if (this.connectionEpoch !== epoch) return;
      void this.handleHistorySync(historySet as GatewayHistorySync);
    });

    socket.ev.on("groups.upsert", (groups) => {
      if (this.connectionEpoch !== epoch) return;
      void this.absorbGroupMetadata(groups as GatewayGroupMetadata[], "groups_upsert");
    });

    socket.ev.on("groups.update", (groups) => {
      if (this.connectionEpoch !== epoch) return;
      void this.absorbGroupMetadata(groups as GatewayGroupMetadata[], "groups_update");
    });

    const ws = socket.ws as { on?: (event: string, listener: (node: unknown) => void) => void } | undefined;
    if (ws?.on) {
      ws.on("CB:message", (node: unknown) => {
        if (this.connectionEpoch !== epoch) return;
        this.absorbRawSenderPhone(node, "cb_message");
      });
      ws.on("CB:receipt", (node: unknown) => {
        if (this.connectionEpoch !== epoch) return;
        this.absorbRawSenderPhone(node, "cb_receipt");
      });
    }
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
      await this.refreshKnownGroups();
      logger.info({ channel: this.channelName, ownerNumber: this.ownerNumber }, "WhatsApp channel connected.");
      return;
    }

    if (update.connection === "close") {
      const disconnectCode = asDisconnectCode(update.lastDisconnect?.error);
      const shouldReconnect =
        this.running &&
        this.allowReconnect &&
        disconnectCode !== DisconnectReason.loggedOut;

      this.connected = false;
      this.state = shouldReconnect ? "reconnecting" : "close";
      this.clearQr();
      this.lastError =
        disconnectCode === DisconnectReason.loggedOut
          ? "logged_out"
          : update.lastDisconnect?.error instanceof Error
            ? update.lastDisconnect.error.message
            : "connection_closed";

      logger.warn(
        { disconnectCode, lastError: this.lastError, shouldReconnect },
        "WhatsApp channel connection closed.",
      );

      if (shouldReconnect) {
        this.scheduleReconnect();
      }
    }
  }

  private async handleMessagesUpsert(upsert: {
    messages: BaileysProto.IWebMessageInfo[];
    type: string;
  }): Promise<void> {
    await this.ingestMessages(upsert.messages, "live_upsert");
  }

  private async handleHistorySync(historySet: GatewayHistorySync): Promise<void> {
    if (historySet.contacts?.length) {
      this.absorbContactLidMappings(historySet.contacts, "history_sync");
    }
    await this.ingestMessages(historySet.messages, historySet.isLatest ? "history_sync_latest" : "history_sync");
  }

  private async refreshKnownGroups(): Promise<void> {
    if (this.channelName !== "observer" || !this.socket?.groupFetchAllParticipating) {
      return;
    }
    try {
      const groups = await this.socket.groupFetchAllParticipating();
      await this.absorbGroupMetadata(Object.values(groups ?? {}) as GatewayGroupMetadata[], "group_fetch_all");
    } catch (error) {
      logger.warn(
        {
          channel: this.channelName,
          errorMessage: error instanceof Error ? error.message : String(error),
        },
        "Failed to refresh WhatsApp group metadata.",
      );
    }
  }

  private async absorbGroupMetadata(groups: GatewayGroupMetadata[] | undefined, source: string): Promise<void> {
    if (!groups || groups.length === 0) {
      return;
    }

    const payload: Array<{ chat_jid: string; chat_name: string; seen_at: string }> = [];
    const seen = new Set<string>();
    for (const group of groups) {
      const jid = String(group?.id ?? "").trim();
      if (!jid || !isGroupJid(jid) || seen.has(jid)) {
        continue;
      }
      const candidates = [group?.subject, group?.name, group?.notify];
      let resolvedName = "";
      for (const candidate of candidates) {
        const text = String(candidate ?? "").trim();
        if (text) {
          resolvedName = text;
          break;
        }
      }
      if (!resolvedName) {
        continue;
      }
      seen.add(jid);
      this.knownGroupNames.set(jid, resolvedName);
      payload.push({
        chat_jid: jid,
        chat_name: resolvedName,
        seen_at: new Date().toISOString(),
      });
    }

    if (payload.length === 0) {
      return;
    }

    try {
      const response = await fetch(`${config.auracoreApiBaseUrl}/api/internal/observer/groups/upsert`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-internal-api-token": config.internalApiToken,
        },
        body: JSON.stringify({ groups: payload }),
      });
      if (!response.ok) {
        const detail = await response.text();
        logger.warn(
          { channel: this.channelName, source, count: payload.length, status: response.status, detail },
          "AuraCore backend rejected group metadata upsert.",
        );
        return;
      }
      logger.info({ channel: this.channelName, source, count: payload.length }, "Delivered group metadata to AuraCore backend.");
    } catch (error) {
      logger.warn(
        {
          channel: this.channelName,
          source,
          count: payload.length,
          errorMessage: error instanceof Error ? error.message : String(error),
        },
        "Failed to deliver group metadata to AuraCore backend.",
      );
    }
  }

  private async ingestMessages(
    messages: BaileysProto.IWebMessageInfo[] | undefined,
    sourceEvent: string,
  ): Promise<void> {
    if (!messages || messages.length === 0) {
      return;
    }

    const batch: IngestMessagePayload[] = [];
    for (const message of messages) {
      const normalized = this.normalizeMessage(message, sourceEvent);
      if (normalized) {
        batch.push(normalized);
      }
    }

    if (batch.length === 0) {
      logger.debug({ sourceEvent, candidateCount: messages.length }, "No analyzable direct text messages in batch.");
      return;
    }

    const delivered = await this.deliverBatch(batch, sourceEvent, 1);
    if (!delivered) {
      this.enqueueBackendBatch(batch, sourceEvent, 1);
    }
  }

  private async deliverBatch(
    batch: IngestMessagePayload[],
    sourceEvent: string,
    attemptNumber: number,
  ): Promise<boolean> {
    const ingestPath =
      this.channelName === "observer"
        ? "/api/internal/observer/messages/ingest"
        : "/api/internal/agent/messages/inbound";

    try {
      const response = await fetch(`${config.auracoreApiBaseUrl}${ingestPath}`, {
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
          {
            channel: this.channelName,
            sourceEvent,
            attemptNumber,
            count: batch.length,
            status: response.status,
            detail,
          },
          "AuraCore backend rejected the message batch.",
        );
        return response.status < 500 ? true : false;
      }

      logger.info(
        { channel: this.channelName, sourceEvent, attemptNumber, count: batch.length },
        "Delivered message batch to AuraCore backend.",
      );
      return true;
    } catch (error) {
      logger.error(
        {
          channel: this.channelName,
          sourceEvent,
          attemptNumber,
          count: batch.length,
          errorMessage: error instanceof Error ? error.message : String(error),
        },
        "Failed to deliver messages to AuraCore backend.",
      );
      return false;
    }
  }

  private enqueueBackendBatch(
    batch: IngestMessagePayload[],
    sourceEvent: string,
    attempts: number,
  ): void {
    const dedupedMessages = Array.from(
      new Map(batch.map((message) => [message.message_id, message])).values(),
    );

    this.pendingBackendBatches.push({
      messages: dedupedMessages,
      sourceEvent,
      queuedAt: Date.now(),
      attempts,
    });

    logger.warn(
      {
        channel: this.channelName,
        sourceEvent,
        count: dedupedMessages.length,
        queuedBatches: this.pendingBackendBatches.length,
      },
      "Queued message batch for backend retry.",
    );
    this.scheduleBackendRetry();
  }

  private scheduleBackendRetry(): void {
    if (this.backendRetryTimer || !this.running) {
      return;
    }

    this.backendRetryTimer = setTimeout(() => {
      this.backendRetryTimer = null;
      void this.flushPendingBackendBatches();
    }, config.reconnectDelayMs);
  }

  private clearBackendRetryTimer(): void {
    if (!this.backendRetryTimer) {
      return;
    }
    clearTimeout(this.backendRetryTimer);
    this.backendRetryTimer = null;
  }

  private async flushPendingBackendBatches(): Promise<void> {
    if (this.backendDeliveryInFlight || this.pendingBackendBatches.length === 0) {
      return;
    }

    this.backendDeliveryInFlight = true;
    try {
      while (this.pendingBackendBatches.length > 0) {
        const current = this.pendingBackendBatches[0];
        const delivered = await this.deliverBatch(
          current.messages,
          current.sourceEvent,
          current.attempts + 1,
        );
        if (!delivered) {
          current.attempts += 1;
          this.scheduleBackendRetry();
          return;
        }
        this.pendingBackendBatches.shift();
      }
    } finally {
      this.backendDeliveryInFlight = false;
    }
  }

  private normalizeMessage(message: BaileysProto.IWebMessageInfo, sourceEvent: string): IngestMessagePayload | null {
    const key = message.key;
    if (!key || !key.id || !key.remoteJid) {
      return null;
    }

    const rawRemoteJid = String(key.remoteJid);
    const resolvedChatJid = this.resolveIncomingRemoteJid(key);
    if (rawRemoteJid.endsWith("@lid") && resolvedChatJid.endsWith("@lid")) {
      this.bufferLidMessage(rawRemoteJid, message, sourceEvent);
      this.requestPhoneForLidJid(rawRemoteJid, message);
      logger.info(
        { channel: this.channelName, sourceEvent, rawRemoteJid, messageId: key.id },
        "Buffered unresolved LID message until phone mapping is available.",
      );
      return null;
    }

    const isGroupChat = isGroupJid(rawRemoteJid) || isGroupJid(resolvedChatJid);
    if (isGroupChat && this.channelName !== "observer") {
      return null;
    }

    if (!isGroupChat && !isDirectUserJid(resolvedChatJid)) {
      return null;
    }

    if (this.isDuplicate(key.id)) {
      return null;
    }

    const messageText = extractMessageText(message).trim();
    if (!messageText) {
      return null;
    }

    if (isGroupChat) {
      const chatName = this.resolveGroupName(rawRemoteJid, resolvedChatJid);
      const participant = this.resolveParticipantIdentity(message, key);
      return {
        message_id: key.id,
        chat_type: "group",
        chat_name: chatName,
        direction: key.fromMe ? "outbound" : "inbound",
        from_me: Boolean(key.fromMe),
        contact_name: participant.value,
        contact_name_source: participant.source,
        chat_jid: rawRemoteJid,
        contact_phone: participant.phone,
        participant_name: participant.value,
        participant_phone: participant.phone,
        participant_jid: participant.jid,
        message_text: messageText,
        timestamp: toIsoTimestamp(message.messageTimestamp),
        source: "baileys",
        source_event: sourceEvent,
      };
    }

    const contactPhone = jidToPhone(resolvedChatJid);
    if (!contactPhone) {
      return null;
    }

    const { value: contactName, source: contactNameSource } = this.resolveContactName(
      message,
      rawRemoteJid,
      resolvedChatJid,
      contactPhone,
    );
    return {
      message_id: key.id,
      chat_type: "direct",
      chat_name: contactName || contactPhone,
      direction: key.fromMe ? "outbound" : "inbound",
      from_me: Boolean(key.fromMe),
      contact_name: contactName || contactPhone,
      contact_name_source: contactNameSource,
      chat_jid: resolvedChatJid,
      contact_phone: contactPhone,
      participant_name: null,
      participant_phone: null,
      participant_jid: null,
      message_text: messageText,
      timestamp: toIsoTimestamp(message.messageTimestamp),
      source: "baileys",
      source_event: sourceEvent,
    };
  }

  private resolveGroupName(rawRemoteJid: string, resolvedChatJid: string): string {
    const cachedResolvedName = this.knownGroupNames.get(resolvedChatJid);
    if (cachedResolvedName) {
      return cachedResolvedName;
    }
    const cachedRawName = this.knownGroupNames.get(rawRemoteJid);
    if (cachedRawName) {
      return cachedRawName;
    }
    const socketWithContacts = this.socket as
      | (WASocket & {
          contacts?: Record<string, ContactProfile>;
        })
      | null;
    const resolvedContact = socketWithContacts?.contacts?.[resolvedChatJid];
    const rawContact = socketWithContacts?.contacts?.[rawRemoteJid];
    const candidates = [
      resolvedContact?.subject,
      rawContact?.subject,
      resolvedContact?.name,
      rawContact?.name,
      resolvedContact?.notify,
      rawContact?.notify,
    ];

    for (const candidate of candidates) {
      const text = String(candidate ?? "").trim();
      if (text) {
        const groupJid = isGroupJid(resolvedChatJid) ? resolvedChatJid : rawRemoteJid;
        if (groupJid) {
          this.knownGroupNames.set(groupJid, text);
        }
        return text;
      }
    }

    const groupId = (rawRemoteJid || resolvedChatJid).split("@")[0] ?? "";
    return groupId ? `Grupo ${groupId}` : "Grupo";
  }

  private resolveParticipantIdentity(
    message: BaileysProto.IWebMessageInfo,
    key: BaileysProto.IMessageKey,
  ): { value: string; source: ContactNameSource; phone: string | null; jid: string | null } {
    if (key.fromMe) {
      return { value: "Dono", source: "phone", phone: this.ownerNumber, jid: this.socket?.user?.id ?? null };
    }

    const participantJid = this.resolveParticipantJid(key);
    const normalizedParticipantJid = this.normalizePhoneJidCandidate(participantJid) ?? participantJid?.trim() ?? null;
    const participantPhone = normalizedParticipantJid ? jidToPhone(normalizedParticipantJid) || null : null;
    const socketWithContacts = this.socket as
      | (WASocket & {
          contacts?: Record<string, ContactProfile>;
        })
      | null;
    const participantContact = normalizedParticipantJid ? socketWithContacts?.contacts?.[normalizedParticipantJid] : null;
    const rawContact = participantJid ? socketWithContacts?.contacts?.[participantJid] : null;
    const cachedName = participantPhone ? this.knownContactNames.get(participantPhone) : null;
    const cachedSource = participantPhone ? this.knownContactNameSources.get(participantPhone) : null;
    const candidates: Array<{ value: string | null | undefined; source: ContactNameSource }> = [
      { value: participantContact?.name || rawContact?.name, source: "saved_contact" },
      { value: participantContact?.verifiedBizName || rawContact?.verifiedBizName, source: "verified_business" },
      { value: participantContact?.verifiedName || rawContact?.verifiedName, source: "verified_name" },
      { value: message.pushName || participantContact?.notify || rawContact?.notify, source: "push_name" },
      {
        value: cachedName,
        source:
          cachedSource && cachedSource !== "phone"
            ? (cachedSource as ContactNameSource)
            : "cached_history",
      },
    ];

    for (const candidate of candidates) {
      const text = String(candidate.value ?? "").trim();
      if (!this.isUsefulContactName(text, participantPhone)) {
        continue;
      }
      if (participantPhone) {
        this.rememberContactName(participantPhone, text, candidate.source);
      }
      return { value: text, source: candidate.source, phone: participantPhone, jid: normalizedParticipantJid };
    }

    if (participantPhone) {
      return { value: participantPhone, source: "phone", phone: participantPhone, jid: normalizedParticipantJid };
    }

    if (normalizedParticipantJid) {
      return { value: normalizedParticipantJid.split("@")[0] ?? "Participante", source: "phone", phone: null, jid: normalizedParticipantJid };
    }

    return { value: "Participante", source: "phone", phone: null, jid: null };
  }

  private resolveParticipantJid(key: BaileysProto.IMessageKey): string | null {
    const enrichedKey = key as MessageKeyWithLid;
    const candidates = [key.participant, enrichedKey.participantPn, enrichedKey.remoteJidAlt];
    for (const candidate of candidates) {
      const trimmed = String(candidate ?? "").trim();
      if (!trimmed) {
        continue;
      }
      const normalizedPhoneJid = this.normalizePhoneJidCandidate(trimmed);
      if (normalizedPhoneJid) {
        return normalizedPhoneJid;
      }
      if (trimmed.endsWith("@lid")) {
        const normalized = this.normalizePhoneJidCandidate(trimmed);
        if (normalized) {
          return normalized;
        }
      }
      return trimmed;
    }
    return null;
  }

  private resolveContactName(
    message: BaileysProto.IWebMessageInfo,
    rawRemoteJid: string,
    resolvedChatJid: string,
    contactPhone: string,
  ): { value: string; source: ContactNameSource } {
    const socketWithContacts = this.socket as
      | (WASocket & {
          contacts?: Record<
            string,
            ContactProfile
          >;
        })
      | null;
    const resolvedContact = socketWithContacts?.contacts?.[resolvedChatJid];
    const rawContact = socketWithContacts?.contacts?.[rawRemoteJid];
    const cachedName = this.knownContactNames.get(contactPhone);
    const cachedSource = this.knownContactNameSources.get(contactPhone);
    const candidates: Array<{ value: string | null | undefined; source: ContactNameSource }> = [
      { value: resolvedContact?.name || rawContact?.name, source: "saved_contact" },
      { value: resolvedContact?.verifiedBizName || rawContact?.verifiedBizName, source: "verified_business" },
      { value: resolvedContact?.verifiedName || rawContact?.verifiedName, source: "verified_name" },
      { value: message.pushName || resolvedContact?.notify || rawContact?.notify, source: "push_name" },
      {
        value: cachedName,
        source:
          cachedSource && cachedSource !== "phone"
            ? (cachedSource as ContactNameSource)
            : "cached_history",
      },
    ];

    for (const candidate of candidates) {
      const text = String(candidate.value ?? "").trim();
      if (!this.isUsefulContactName(text, contactPhone)) {
        continue;
      }
      this.rememberContactName(contactPhone, text, candidate.source);
      return { value: text, source: candidate.source };
    }

    return { value: contactPhone, source: "phone" };
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

  private resolveIncomingRemoteJid(key: BaileysProto.IMessageKey): string {
    const enrichedKey = key as MessageKeyWithLid;
    const remoteJid = String(key.remoteJid ?? "");
    if (!remoteJid.endsWith("@lid")) {
      return this.normalizePhoneJidCandidate(remoteJid) ?? remoteJid;
    }

    const candidates = [enrichedKey.remoteJidAlt, enrichedKey.participantPn, key.participant];
    for (const candidate of candidates) {
      const normalized = this.normalizePhoneJidCandidate(candidate);
      if (normalized) {
        this.rememberLidMapping(remoteJid, normalized, "message_candidate");
        return normalized;
      }
    }

    const exact = this.lidToPhoneJid.get(remoteJid);
    if (exact) {
      return exact;
    }

    const baseLidJid = this.toBaseLidJid(remoteJid);
    const baseMatch = this.lidToPhoneJid.get(baseLidJid);
    if (baseMatch) {
      return baseMatch;
    }

    const lidNumber = baseLidJid.split("@")[0];
    for (const [knownLidJid, mappedPhoneJid] of this.lidToPhoneJid.entries()) {
      if (knownLidJid.startsWith(lidNumber)) {
        return mappedPhoneJid;
      }
    }

    return remoteJid;
  }

  private normalizePhoneJidCandidate(value: string | null | undefined): string | null {
    if (!value) {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed || isStatusJid(trimmed) || isGroupJid(trimmed) || trimmed.endsWith("@lid")) {
      return null;
    }

    const phone = jidToPhone(trimmed);
    if (phone.length < 8) {
      return null;
    }
    return `${phone}@s.whatsapp.net`;
  }

  private rememberLidMapping(
    lidJid: string | null | undefined,
    phoneJid: string | null | undefined,
    source: "contacts_upsert" | "contacts_update" | "history_sync" | "message_candidate" | "cb_message" | "cb_receipt",
  ): void {
    if (!lidJid || !lidJid.endsWith("@lid")) {
      return;
    }
    const normalizedPhoneJid = this.normalizePhoneJidCandidate(phoneJid);
    if (!normalizedPhoneJid) {
      return;
    }

    const baseLidJid = this.toBaseLidJid(lidJid);
    const previous = this.lidToPhoneJid.get(baseLidJid);
    this.lidToPhoneJid.set(baseLidJid, normalizedPhoneJid);
    this.lidToPhoneJid.set(lidJid, normalizedPhoneJid);

    if (previous !== normalizedPhoneJid) {
      logger.info(
        { channel: this.channelName, lidJid, baseLidJid, phoneJid: normalizedPhoneJid, source },
        "Resolved LID to phone JID.",
      );
    }

    this.replayBufferedLidMessages(baseLidJid);
    if (baseLidJid !== lidJid) {
      this.replayBufferedLidMessages(lidJid);
    }
  }

  private absorbContactLidMappings(
    contacts: GatewayContactLike[] | undefined,
    source: "contacts_upsert" | "contacts_update" | "history_sync",
  ): void {
    if (!contacts?.length) {
      return;
    }

    for (const contact of contacts) {
      const contactId = typeof contact.id === "string" ? contact.id.trim() : "";
      const lidRaw = typeof contact.lid === "string" ? contact.lid.trim() : "";
      const lidJid = lidRaw ? (lidRaw.includes("@") ? lidRaw : `${lidRaw}@lid`) : contactId.endsWith("@lid") ? contactId : "";
      const phoneJid = this.normalizePhoneJidCandidate(contactId);
      if (lidJid && phoneJid) {
        this.rememberLidMapping(lidJid, phoneJid, source);
      }

      const contactPhone = phoneJid ? jidToPhone(phoneJid) : "";
      const preferredName =
        (typeof contact.name === "string" ? contact.name.trim() : "") ||
        (typeof contact.verifiedBizName === "string" ? contact.verifiedBizName.trim() : "") ||
        (typeof contact.verifiedName === "string" ? contact.verifiedName.trim() : "") ||
        (typeof contact.notify === "string" ? contact.notify.trim() : "");
      if (contactPhone && this.isUsefulContactName(preferredName, contactPhone)) {
        this.rememberContactName(contactPhone, preferredName, "saved_contact");
      }
    }
  }

  private absorbRawSenderPhone(node: unknown, source: "cb_message" | "cb_receipt"): void {
    const attrs = (node as { attrs?: Record<string, string> } | undefined)?.attrs;
    if (!attrs) {
      return;
    }
    const lidJid = attrs.from;
    const senderPhoneJid = attrs.sender_pn;
    if (lidJid?.endsWith("@lid") && senderPhoneJid) {
      this.rememberLidMapping(lidJid, senderPhoneJid, source);
    }
  }

  private bufferLidMessage(lidJid: string, message: BaileysProto.IWebMessageInfo, sourceEvent: string): void {
    const now = Date.now();
    const existing = this.pendingLidMessages.get(lidJid) ?? [];
    const fresh = existing.filter((entry) => now - entry.bufferedAt < LID_BUFFER_TTL_MS);
    if (fresh.length >= LID_BUFFER_MAX_PER_JID) {
      fresh.shift();
    }
    fresh.push({ message, sourceEvent, bufferedAt: now });
    this.pendingLidMessages.set(lidJid, fresh);
  }

  private replayBufferedLidMessages(lidJid: string): void {
    const entries = this.pendingLidMessages.get(lidJid);
    if (!entries?.length) {
      return;
    }

    this.pendingLidMessages.delete(lidJid);
    const freshEntries = entries.filter((entry) => Date.now() - entry.bufferedAt < LID_BUFFER_TTL_MS);
    if (!freshEntries.length) {
      return;
    }

    for (const entry of freshEntries) {
      void this.ingestMessages([entry.message], entry.sourceEvent);
    }
  }

  private requestPhoneForLidJid(lidJid: string, message?: BaileysProto.IWebMessageInfo): void {
    const socket = this.socket;
    if (!socket || this.lidToPhoneJid.has(lidJid)) {
      return;
    }

    void (async () => {
      try {
        await socket.presenceSubscribe(lidJid);
      } catch {
        // Best effort only.
      }

      if (message?.key) {
        try {
          await socket.readMessages([message.key]);
        } catch {
          // Best effort only.
        }
      }
    })();
  }

  private rememberContactName(contactPhone: string, name: string, source: ContactNameSource): void {
    if (!this.isUsefulContactName(name, contactPhone)) {
      return;
    }
    this.knownContactNames.set(contactPhone, name.trim());
    this.knownContactNameSources.set(contactPhone, source);
  }

  private isUsefulContactName(name: string | null | undefined, contactPhone: string | null | undefined): boolean {
    const trimmed = String(name ?? "").trim();
    if (!trimmed) {
      return false;
    }
    if (!contactPhone) {
      return true;
    }
    if (trimmed === contactPhone) {
      return false;
    }
    const nameDigits = trimmed.replace(/[^\d]/g, "");
    const phoneDigits = contactPhone.replace(/[^\d]/g, "");
    return !nameDigits || nameDigits !== phoneDigits;
  }

  private toBaseLidJid(lidJid: string): string {
    return lidJid.replace(/:\d+@lid$/, "@lid");
  }

  private resolveDeliveryJid(chatJid: string): string {
    const trimmed = chatJid.trim();
    if (!trimmed) {
      throw new Error("WhatsApp chat JID is required.");
    }

    if (trimmed.endsWith("@lid")) {
      const exact = this.lidToPhoneJid.get(trimmed);
      const base = this.lidToPhoneJid.get(this.toBaseLidJid(trimmed));
      return exact || base || trimmed;
    }

    if (
      isGroupJid(trimmed) ||
      isStatusJid(trimmed) ||
      isBroadcastJid(trimmed) ||
      isNewsletterJid(trimmed)
    ) {
      return trimmed;
    }

    const phone = jidToPhone(trimmed);
    if (!phone) {
      throw new Error("WhatsApp chat JID is invalid.");
    }
    return `${phone}@s.whatsapp.net`;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect().catch((error) => {
        logger.error({ channel: this.channelName, error }, "Failed to reconnect WhatsApp channel.");
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
      this.socket.ev.removeAllListeners("contacts.upsert");
      this.socket.ev.removeAllListeners("contacts.update");
      this.socket.ev.removeAllListeners("messaging-history.set");
      (this.socket as unknown as { ws?: { close: () => void } }).ws?.close();
    } catch {
      // Ignore cleanup errors.
    }

    this.socket = null;
  }

  async sendTextMessage(chatJid: string, messageText: string): Promise<GatewaySendResult> {
    const socket = this.socket;
    if (!socket || !this.connected) {
      throw new Error("WhatsApp channel is not connected.");
    }
    const trimmed = messageText.trim();
    if (!trimmed) {
      throw new Error("Cannot send empty WhatsApp message.");
    }
    const deliveryJid = this.resolveDeliveryJid(chatJid);
    const result = await socket.sendMessage(deliveryJid, { text: trimmed });
    if (result?.key?.id && result.message) {
      this.sentMessagesCache.set(result.key.id, result.message);
      if (this.sentMessagesCache.size > SENT_MESSAGE_CACHE_MAX) {
        const oldest = this.sentMessagesCache.keys().next().value;
        if (oldest) {
          this.sentMessagesCache.delete(oldest);
        }
      }
    }
    const messageId = result?.key?.id ?? null;
    const timestamp = result?.messageTimestamp ? toIsoTimestamp(result.messageTimestamp) : new Date().toISOString();
    return {
      message_id: messageId,
      timestamp,
    };
  }
}

export function buildGatewayRunId(): string {
  return randomUUID();
}
