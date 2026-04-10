import cors from "cors";
import express, { type NextFunction, type Request, type Response } from "express";

import { config } from "./config";
import { buildGatewayRunId, WhatsAppGatewayChannel } from "./whatsapp";

const app = express();
const observerGateway = new WhatsAppGatewayChannel("observer", config.observerInstanceName, config.observerInstanceName);
const agentGateway = new WhatsAppGatewayChannel("agent", config.agentInstanceName, config.agentInstanceName);
const runId = buildGatewayRunId();

function requireInternalToken(req: Request, res: Response, next: NextFunction): void {
  const token = req.header("x-internal-api-token")?.trim();
  if (!token || token !== config.internalApiToken) {
    res.status(403).json({ detail: "Invalid internal API token." });
    return;
  }
  next();
}

app.use(cors());
app.use(express.json({ limit: "2mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", run_id: runId });
});

app.use("/internal", requireInternalToken);

app.get("/internal/observer/status", (_req, res) => {
  res.json(observerGateway.getStatus());
});

app.post("/internal/observer/connect", async (_req, res, next) => {
  try {
    const status = await observerGateway.connectSession();
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/reset", async (_req, res, next) => {
  try {
    await observerGateway.resetSession();
    res.json(observerGateway.getStatus());
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/messages/refresh", async (_req, res, next) => {
  try {
    const status = await observerGateway.refreshDirectHistory();
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/send", async (req, res, next) => {
  try {
    const chatJid = String(req.body?.chat_jid ?? "").trim();
    const messageText = String(req.body?.message_text ?? "").trim();
    const result = await observerGateway.sendTextMessage(chatJid, messageText);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

app.get("/internal/agent/status", (_req, res) => {
  res.json(agentGateway.getStatus());
});

app.post("/internal/agent/connect", async (_req, res, next) => {
  try {
    const status = await agentGateway.connectSession();
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/agent/reset", async (_req, res, next) => {
  try {
    await agentGateway.resetSession();
    res.json(agentGateway.getStatus());
  } catch (error) {
    next(error);
  }
});

app.post("/internal/agent/send", async (req, res, next) => {
  try {
    const chatJid = String(req.body?.chat_jid ?? "").trim();
    const messageText = String(req.body?.message_text ?? "").trim();
    const result = await agentGateway.sendTextMessage(chatJid, messageText);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

app.use((error: unknown, _req: Request, res: Response, _next: NextFunction) => {
  const message = error instanceof Error ? error.message : "Internal gateway error.";
  res.status(500).json({ detail: message });
});

const server = app.listen(config.port, "127.0.0.1", () => {
  console.log(`AuraCore WhatsApp gateway listening on 127.0.0.1:${config.port}`);
});

void observerGateway.start().catch((error) => {
  console.error("Failed to start AuraCore WhatsApp gateway", error);
});
void agentGateway.start().catch((error) => {
  console.error("Failed to start AuraCore WhatsApp agent gateway", error);
});

async function shutdown(signal: string): Promise<void> {
  console.warn(`Received ${signal}; shutting down AuraCore WhatsApp gateway.`);
  server.close();
  await observerGateway.shutdown();
  await agentGateway.shutdown();
  process.exit(0);
}

process.on("SIGTERM", () => {
  void shutdown("SIGTERM");
});

process.on("SIGINT", () => {
  void shutdown("SIGINT");
});

process.on("uncaughtException", (error) => {
  console.error("Uncaught exception in AuraCore WhatsApp gateway", error);
});

process.on("unhandledRejection", (reason) => {
  console.error("Unhandled rejection in AuraCore WhatsApp gateway", reason);
});
