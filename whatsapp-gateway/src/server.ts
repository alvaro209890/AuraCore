import cors from "cors";
import express, { type NextFunction, type Request, type Response } from "express";

import { config } from "./config";
import { AuraCoreGatewayManager } from "./gateway-manager";
import { buildGatewayRunId } from "./whatsapp";

const app = express();
const gatewayManager = new AuraCoreGatewayManager();
const runId = buildGatewayRunId();

type AuraCoreUserContext = {
  appUserId: string;
  username: string;
};

function requireInternalToken(req: Request, res: Response, next: NextFunction): void {
  const token = req.header("x-internal-api-token")?.trim();
  if (!token || token !== config.internalApiToken) {
    res.status(403).json({ detail: "Invalid internal API token." });
    return;
  }
  next();
}

function resolveAuraCoreUser(req: Request, res: Response): AuraCoreUserContext | null {
  const appUserId = req.header("x-auracore-user-id")?.trim() ?? "";
  const username = req.header("x-auracore-username")?.trim() ?? appUserId;
  if (!appUserId) {
    res.status(400).json({ detail: "Missing x-auracore-user-id header." });
    return null;
  }
  return { appUserId, username };
}

app.use(cors());
app.use(express.json({ limit: "2mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", run_id: runId });
});

app.use("/internal", requireInternalToken);

app.get("/internal/observer/status", (req, res) => {
  const user = resolveAuraCoreUser(req, res);
  if (!user) {
    return;
  }
  res.json(gatewayManager.getStatus(user.appUserId, user.username, "observer"));
});

app.post("/internal/observer/connect", async (req, res, next) => {
  const user = resolveAuraCoreUser(req, res);
  if (!user) {
    return;
  }
  try {
    const status = await gatewayManager.connect(user.appUserId, user.username, "observer");
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/reset", async (req, res, next) => {
  const user = resolveAuraCoreUser(req, res);
  if (!user) {
    return;
  }
  try {
    const status = await gatewayManager.reset(user.appUserId, user.username, "observer");
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/messages/refresh", async (req, res, next) => {
  const user = resolveAuraCoreUser(req, res);
  if (!user) {
    return;
  }
  try {
    const status = await gatewayManager.refreshObserverHistory(user.appUserId, user.username);
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/send", async (req, res, next) => {
  const user = resolveAuraCoreUser(req, res);
  if (!user) {
    return;
  }
  try {
    const chatJid = String(req.body?.chat_jid ?? "").trim();
    const messageText = String(req.body?.message_text ?? "").trim();
    const result = await gatewayManager.sendTextMessage(user.appUserId, user.username, "observer", chatJid, messageText);
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

void gatewayManager.start().catch((error) => {
  console.error("Failed to bootstrap AuraCore WhatsApp gateway manager", error);
});

async function shutdown(signal: string): Promise<void> {
  console.warn(`Received ${signal}; shutting down AuraCore WhatsApp gateway.`);
  server.close();
  await gatewayManager.shutdown();
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
