"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeMemory,
  connectObserver,
  getCurrentMemory,
  getMemorySnapshots,
  getObserverStatus,
  type MemoryCurrent,
  type MemorySnapshot,
  type ObserverStatus,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";

const POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 25000;
const WINDOW_PRESETS = [6, 24, 72, 168];

function mergeStatus(previous: ObserverStatus | null, next: ObserverStatus): ObserverStatus {
  return {
    ...next,
    qr_code: next.qr_code ?? previous?.qr_code ?? null,
  };
}

function formatState(state: string): string {
  return state
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase())
    .join(" ");
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Ainda nao disponivel";
  }

  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatHoursLabel(hours: number): string {
  if (hours < 24) {
    return `${hours}h`;
  }
  if (hours % 24 === 0) {
    return `${hours / 24}d`;
  }
  return `${hours}h`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Nao foi possivel concluir a operacao.";
}

export function ConnectionDashboard() {
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [windowHoursInput, setWindowHoursInput] = useState("24");
  const lastQrRefreshAtRef = useRef<number | null>(null);

  const selectedWindowHours = useMemo(() => {
    const parsed = Number.parseInt(windowHoursInput, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [windowHoursInput]);

  const statusLabel = useMemo(() => {
    if (!status) {
      return "Pronto para iniciar";
    }
    return status.connected ? "Conectado ao WhatsApp" : formatState(status.state);
  }, [status]);

  useEffect(() => {
    void hydrateDashboard();
  }, []);

  useEffect(() => {
    if (!pollingEnabled || status?.connected) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void pollStatus();
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [pollingEnabled, status?.connected]);

  async function hydrateDashboard(): Promise<void> {
    setIsHydrating(true);

    const [statusResult, memoryResult, snapshotsResult] = await Promise.allSettled([
      getObserverStatus(false),
      getCurrentMemory(),
      getMemorySnapshots(),
    ]);

    if (statusResult.status === "fulfilled") {
      setStatus(statusResult.value);
      setPollingEnabled(!statusResult.value.connected);
      setViewState(statusResult.value.connected ? "connected" : "idle");
      setConnectionError(null);
    } else {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(statusResult.reason));
    }

    if (memoryResult.status === "fulfilled") {
      setMemory(memoryResult.value);
      setMemoryError(null);
    } else {
      setMemoryError(getErrorMessage(memoryResult.reason));
    }

    if (snapshotsResult.status === "fulfilled") {
      setSnapshots(snapshotsResult.value);
      if (memoryResult.status === "fulfilled") {
        setMemoryError(null);
      }
    } else {
      setMemoryError(getErrorMessage(snapshotsResult.reason));
    }

    setIsHydrating(false);
  }

  async function startConnection(): Promise<void> {
    setIsSubmitting(true);
    setConnectionError(null);
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
      setConnectionError(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function pollStatus(): Promise<void> {
    try {
      const shouldRefreshQr =
        !lastQrRefreshAtRef.current ||
        Date.now() - lastQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS;

      const nextStatus = shouldRefreshQr ? await connectObserver() : await getObserverStatus(false);

      if (shouldRefreshQr) {
        lastQrRefreshAtRef.current = Date.now();
      }

      setStatus((previous) => mergeStatus(previous, nextStatus));
      setConnectionError(null);

      if (nextStatus.connected) {
        setPollingEnabled(false);
        setViewState("connected");
        return;
      }

      setViewState("waiting");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(error));
    }
  }

  async function analyzeSelectedWindow(): Promise<void> {
    if (!selectedWindowHours) {
      setMemoryError("Informe uma janela valida em horas.");
      return;
    }

    setIsAnalyzing(true);
    setMemoryError(null);

    try {
      const response = await analyzeMemory(selectedWindowHours);
      setMemory(response.current);
      setSnapshots((previous) => {
        const remaining = previous.filter((snapshot) => snapshot.id !== response.snapshot.id);
        return [response.snapshot, ...remaining];
      });
    } catch (error) {
      setMemoryError(getErrorMessage(error));
    } finally {
      setIsAnalyzing(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero-panel">
        <div className="eyebrow">AuraCore / Memoria Observadora</div>
        <h1>Leia o WhatsApp, consolide sinais e gere memorias sob demanda.</h1>
        <p className="hero-copy">
          O gateway Baileys observa chats diretos do Numero A, o backend persiste as
          mensagens no Supabase e a analise com DeepSeek so acontece quando voce
          pedir. Cada rodada cria um snapshot do que foi aprendido naquela janela.
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
            <span className="metric-label">Ultima Analise</span>
            <strong>{memory?.last_analyzed_at ? formatDateTime(memory.last_analyzed_at) : "Nenhuma ainda"}</strong>
          </div>
        </div>
      </section>

      <section className="connection-panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">WhatsApp Observador</span>
            <h2>Conectar Numero A</h2>
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
                : "Conectar Meu WhatsApp"}
          </button>
        </div>

        <div className="qr-card">
          {status?.qr_code ? (
            <div className="qr-wrapper">
              <img className="qr-image" src={status.qr_code} alt="QR Code do WhatsApp observador" />
            </div>
          ) : (
            <div className="qr-placeholder">
              <span>{isHydrating ? "Carregando status" : "QR Code indisponivel"}</span>
              <p>
                {status?.connected
                  ? "A sessao ja esta conectada e nao precisa de um novo QR Code."
                  : "Clique no botao para abrir uma nova sessao de leitura e gerar o QR Code."}
              </p>
            </div>
          )}

          <div className="status-copy">
            <span className={`status-pill status-${viewState}`}>{statusLabel}</span>
            <p>
              {status?.connected
                ? "O gateway esta online e enviando mensagens diretas para o backend analisar mais tarde."
                : "Depois de escanear o QR, o painel atualiza automaticamente ate a conexao ficar aberta."}
            </p>
          </div>

          {connectionError ? (
            <div className="error-card">
              <strong>Falha na conexao com o backend</strong>
              <p>{connectionError}</p>
            </div>
          ) : null}
        </div>

        <dl className="details-grid">
          <div>
            <dt>Numero dono</dt>
            <dd>{status?.owner_number ?? "Aguardando leitura"}</dd>
          </div>
          <div>
            <dt>Gateway</dt>
            <dd>{status?.gateway_ready ? "Online" : "Indisponivel"}</dd>
          </div>
          <div>
            <dt>Ingestao</dt>
            <dd>{status?.ingestion_ready ? "Pronta" : "Pendente"}</dd>
          </div>
          <div>
            <dt>Expira em</dt>
            <dd>
              {status?.connected
                ? "Sessao ativa"
                : status?.qr_expires_in_sec
                  ? `${status.qr_expires_in_sec}s`
                  : "Sem QR ativo"}
            </dd>
          </div>
          <div>
            <dt>Ultima atualizacao</dt>
            <dd>{formatDateTime(status?.last_seen_at)}</dd>
          </div>
          <div>
            <dt>Coleta</dt>
            <dd>Chats diretos, entrada e saida</dd>
          </div>
        </dl>
      </section>

      <section className="memory-panel panel-span">
        <div className="memory-header">
          <div>
            <span className="panel-kicker">Memoria Manual</span>
            <h2>Consolidar o que a IA aprendeu</h2>
          </div>
          <button
            className="analyze-button"
            onClick={() => void analyzeSelectedWindow()}
            disabled={isAnalyzing || !selectedWindowHours}
            type="button"
          >
            {isAnalyzing ? "Analisando..." : "Analisar mensagens"}
          </button>
        </div>

        <div className="analysis-controls">
          <div className="preset-row">
            {WINDOW_PRESETS.map((hours) => {
              const active = selectedWindowHours === hours;
              return (
                <button
                  key={hours}
                  className={`preset-chip${active ? " preset-chip-active" : ""}`}
                  onClick={() => setWindowHoursInput(String(hours))}
                  type="button"
                >
                  {formatHoursLabel(hours)}
                </button>
              );
            })}
          </div>

          <label className="hours-input-card">
            <span>Janela personalizada em horas</span>
            <input
              type="number"
              min={1}
              step={1}
              value={windowHoursInput}
              onChange={(event) => setWindowHoursInput(event.target.value)}
            />
          </label>

          <div className="analysis-hint">
            {selectedWindowHours
              ? `A analise vai juntar as mensagens das ultimas ${selectedWindowHours} horas antes de chamar o DeepSeek.`
              : "Informe um numero inteiro de horas para montar a janela de analise."}
          </div>
        </div>

        {memoryError ? (
          <div className="error-card memory-error">
            <strong>Falha na analise de memoria</strong>
            <p>{memoryError}</p>
          </div>
        ) : null}

        <div className="memory-grid">
          <article className="summary-card">
            <div className="summary-card-head">
              <span className="card-kicker">Resumo atual</span>
              <span className="summary-meta">
                {memory?.last_analyzed_at ? `Atualizado em ${formatDateTime(memory.last_analyzed_at)}` : "Sem resumo ainda"}
              </span>
            </div>
            <p className="summary-text">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Nenhuma memoria consolidada ainda. Conecte o observador, deixe as mensagens chegarem e rode a primeira analise."}
            </p>
          </article>

          <article className="snapshot-panel">
            <div className="snapshot-panel-head">
              <span className="card-kicker">Snapshots</span>
              <span className="summary-meta">{snapshots.length} analises registradas</span>
            </div>

            {snapshots.length === 0 ? (
              <div className="snapshot-empty">
                <strong>Nenhum snapshot ainda</strong>
                <p>Quando voce analisar uma janela, o resultado historico aparece aqui.</p>
              </div>
            ) : (
              <div className="snapshot-list">
                {snapshots.map((snapshot) => (
                  <article key={snapshot.id} className="snapshot-card">
                    <div className="snapshot-topline">
                      <strong>{formatHoursLabel(snapshot.window_hours)}</strong>
                      <span>{formatDateTime(snapshot.created_at)}</span>
                    </div>
                    <p className="snapshot-summary">{snapshot.window_summary}</p>
                    <div className="snapshot-meta">
                      <span>{snapshot.source_message_count} mensagens</span>
                      <span>
                        {formatDateTime(snapshot.window_start)} ate {formatDateTime(snapshot.window_end)}
                      </span>
                    </div>

                    <SignalGroup title="Aprendizados" items={snapshot.key_learnings} />
                    <SignalGroup title="Pessoas e relacoes" items={snapshot.people_and_relationships} />
                    <SignalGroup title="Rotina" items={snapshot.routine_signals} />
                    <SignalGroup title="Preferencias" items={snapshot.preferences} />
                    <SignalGroup title="Lacunas" items={snapshot.open_questions} />
                  </article>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>
    </main>
  );
}

function SignalGroup({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }

  return (
    <section className="signal-group">
      <h3>{title}</h3>
      <ul className="signal-list">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
