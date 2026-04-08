import cors from "cors";
import express, { type NextFunction, type Request, type Response } from "express";

import { config } from "./config";
import { buildGatewayRunId, WhatsAppObserverGateway } from "./whatsapp";

const app = express();
const gateway = new WhatsAppObserverGateway();
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
  res.json(gateway.getStatus());
});

app.post("/internal/observer/connect", async (_req, res, next) => {
  try {
    const status = await gateway.connectObserver();
    res.json(status);
  } catch (error) {
    next(error);
  }
});

app.post("/internal/observer/reset", async (_req, res, next) => {
  try {
    await gateway.resetSession();
    res.json(gateway.getStatus());
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

void gateway.start().catch((error) => {
  console.error("Failed to start AuraCore WhatsApp gateway", error);
});

async function shutdown(signal: string): Promise<void> {
  console.warn(`Received ${signal}; shutting down AuraCore WhatsApp gateway.`);
  server.close();
  await gateway.shutdown();
  process.exit(0);
}

process.on("SIGTERM", () => {
  void shutdown("SIGTERM");
});

process.on("SIGINT", () => {
  void shutdown("SIGINT");
});
