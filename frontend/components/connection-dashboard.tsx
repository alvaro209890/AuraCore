"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { connectObserver, getObserverStatus, type ObserverStatus } from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";

const POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 25000;

function mergeStatus(
  previous: ObserverStatus | null,
  next: ObserverStatus,
): ObserverStatus {
  return {
    ...next,
    qr_code: next.qr_code ?? previous?.qr_code ?? null,
    pairing_code: next.pairing_code ?? previous?.pairing_code ?? null,
  };
}

function formatState(state: string): string {
  return state
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase())
    .join(" ");
}

export function ConnectionDashboard() {
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const lastQrRefreshAtRef = useRef<number | null>(null);

  const statusLabel = useMemo(() => {
    if (!status) {
      return "Pronto para iniciar";
    }
    return status.connected ? "Conectado ao WhatsApp" : formatState(status.state);
  }, [status]);

  useEffect(() => {
    void hydrateInitialStatus();
  }, []);

  useEffect(() => {
    if (!pollingEnabled || status?.connected) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void pollStatus();
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [pollingEnabled, status?.connected, status?.qr_code]);

  async function hydrateInitialStatus(): Promise<void> {
    try {
      const nextStatus = await getObserverStatus(false);
      setStatus(nextStatus);
      setPollingEnabled(false);
      setViewState(nextStatus.connected ? "connected" : "idle");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function startConnection(): Promise<void> {
    setIsSubmitting(true);
    setErrorMessage(null);
    setViewState("loading");

    try {
      const nextStatus = await connectObserver();
      setStatus((previous) => mergeStatus(previous, nextStatus));
      setPollingEnabled(!nextStatus.connected);
      setViewState(nextStatus.connected ? "connected" : "waiting");
      lastQrRefreshAtRef.current = Date.now();
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function pollStatus(): Promise<void> {
    try {
      const shouldRefreshQr =
        !lastQrRefreshAtRef.current ||
        Date.now() - lastQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS;

      const nextStatus = shouldRefreshQr
        ? await connectObserver()
        : await getObserverStatus(false);

      if (shouldRefreshQr) {
        lastQrRefreshAtRef.current = Date.now();
      }

      setStatus((previous) => mergeStatus(previous, nextStatus));

      if (nextStatus.connected) {
        setPollingEnabled(false);
        setViewState("connected");
        return;
      }

      setViewState("waiting");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setErrorMessage(getErrorMessage(error));
    }
  }

  return (
    <main className="shell">
      <section className="hero-panel">
        <div className="eyebrow">AuraCore / Fase 1</div>
        <h1>Conecte o WhatsApp observador e comece a formar a memoria do sistema.</h1>
        <p className="hero-copy">
          Este painel prepara a instancia que apenas observa mensagens do Numero A.
          O QR Code e gerado pela Evolution API e o backend passa a receber
          <code>MESSAGES_UPSERT</code> apos a leitura.
        </p>

        <div className="metric-strip">
          <div className="metric-card">
            <span className="metric-label">Instancia</span>
            <strong>{status?.instance_name ?? "observer"}</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">Estado</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">Webhook</span>
            <strong>{status?.webhook_ready ? "Pronto" : "Ajustando"}</strong>
          </div>
        </div>
      </section>

      <section className="connection-panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">Observador</span>
            <h2>Conectar Meu WhatsApp</h2>
          </div>
          <button
            className="connect-button"
            onClick={() => void startConnection()}
            disabled={isSubmitting || viewState === "connected"}
            type="button"
          >
            {viewState === "connected"
              ? "WhatsApp conectado"
              : isSubmitting
                ? "Gerando QR..."
                : "Conectar Meu WhatsApp (Observador)"}
          </button>
        </div>

        <div className="qr-card">
          {status?.qr_code ? (
            <div className="qr-wrapper">
              <QRCodeSVG
                value={status.qr_code}
                size={260}
                level="M"
                bgColor="transparent"
                fgColor="#f8f6f0"
                includeMargin
              />
            </div>
          ) : (
            <div className="qr-placeholder">
              <span>QR Code indisponivel</span>
              <p>Clique no botao para solicitar uma nova sessao de leitura.</p>
            </div>
          )}

          <div className="status-copy">
            <span className={`status-pill status-${viewState}`}>{statusLabel}</span>
            <p>
              {viewState === "connected"
                ? "A instancia observadora esta ativa e o backend ja pode receber eventos de mensagem."
                : "Apos escanear o QR Code, o painel atualiza automaticamente ate confirmar a conexao."}
            </p>
          </div>

          {status?.pairing_code ? (
            <div className="pairing-card">
              <span className="pairing-label">Pairing code</span>
              <code>{status.pairing_code}</code>
            </div>
          ) : null}

          {errorMessage ? (
            <div className="error-card">
              <strong>Falha ao comunicar com o backend</strong>
              <p>{errorMessage}</p>
            </div>
          ) : null}
        </div>

        <dl className="details-grid">
          <div>
            <dt>Numero dono</dt>
            <dd>{status?.owner_number ?? "Aguardando leitura"}</dd>
          </div>
          <div>
            <dt>Perfil</dt>
            <dd>{status?.profile_name ?? "Nao informado"}</dd>
          </div>
          <div>
            <dt>Ultima atualizacao</dt>
            <dd>{status?.last_seen_at ? new Date(status.last_seen_at).toLocaleString() : "Agora"}</dd>
          </div>
          <div>
            <dt>Modo de coleta</dt>
            <dd>Mensagens textuais 1:1</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Nao foi possivel concluir a operacao.";
}
