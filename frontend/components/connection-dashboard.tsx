"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeMemory,
  connectObserver,
  getChatSession,
  getCurrentMemory,
  getMemorySnapshots,
  getObserverStatus,
  refineMemory,
  resetObserver,
  sendChatMessage,
  type ChatMessage,
  type MemoryCurrent,
  type MemorySnapshot,
  type ObserverStatus,
  type ProjectMemory,
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
  const [chatError, setChatError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isRefining, setIsRefining] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [chatDraft, setChatDraft] = useState("");
  const [windowHoursInput, setWindowHoursInput] = useState("24");
  const lastQrRefreshAtRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    if (!chatScrollRef.current) {
      return;
    }
    chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
  }, [chatMessages]);

  async function hydrateDashboard(): Promise<void> {
    setIsHydrating(true);

    const [statusResult, memoryResult, snapshotsResult, chatResult] = await Promise.allSettled([
      getObserverStatus(false),
      getCurrentMemory(),
      getMemorySnapshots(),
      getChatSession(),
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

    if (chatResult.status === "fulfilled") {
      setChatThreadTitle(chatResult.value.title);
      setChatMessages(chatResult.value.messages);
      setProjects(chatResult.value.projects);
      if (memoryResult.status !== "fulfilled") {
        setMemory(chatResult.value.current);
      }
      setChatError(null);
    } else {
      setChatError(getErrorMessage(chatResult.reason));
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

  async function resetConnection(): Promise<void> {
    setIsResetting(true);
    setConnectionError(null);
    setViewState("loading");

    try {
      const nextStatus = await resetObserver();
      setStatus(nextStatus);
      setPollingEnabled(!nextStatus.connected);
      setViewState(nextStatus.connected ? "connected" : "waiting");
      lastQrRefreshAtRef.current = Date.now();
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(error));
    } finally {
      setIsResetting(false);
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
      setProjects(response.projects);
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

  async function refineSavedMemoryAction(): Promise<void> {
    setIsRefining(true);
    setMemoryError(null);

    try {
      const response = await refineMemory();
      setMemory(response.current);
      setProjects(response.projects);
    } catch (error) {
      setMemoryError(getErrorMessage(error));
    } finally {
      setIsRefining(false);
    }
  }

  async function submitChatMessage(): Promise<void> {
    const normalized = chatDraft.trim();
    if (!normalized) {
      setChatError("Escreva uma mensagem para conversar com a IA.");
      return;
    }

    setIsSendingChat(true);
    setChatError(null);

    try {
      const session = await sendChatMessage(normalized);
      setChatMessages(session.messages);
      setProjects(session.projects);
      setMemory(session.current);
      setChatThreadTitle(session.title);
      setChatDraft("");
    } catch (error) {
      setChatError(getErrorMessage(error));
    } finally {
      setIsSendingChat(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero-panel">
        <div className="eyebrow">AuraCore / Memoria Observadora</div>
        <h1>Leia o WhatsApp, consolide sinais e converse com uma IA personalizada.</h1>
        <p className="hero-copy">
          O gateway Baileys observa chats diretos do Numero A, o backend persiste as mensagens no
          Supabase, o DeepSeek transforma janelas de conversa em memoria e projetos, e o Groq usa
          esse contexto para responder como um segundo cerebro pessoal.
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
          <div className="connection-actions">
            <button
              className="reset-button"
              onClick={() => void resetConnection()}
              disabled={isResetting}
              type="button"
            >
              {isResetting ? "Resetando..." : "Resetar sessao"}
            </button>
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
          <div className="connection-actions">
            <button
              className="reset-button"
              onClick={() => void refineSavedMemoryAction()}
              disabled={isRefining}
              type="button"
            >
              {isRefining ? "Refinando..." : "Refinar memoria salva"}
            </button>
            <button
              className="analyze-button"
              onClick={() => void analyzeSelectedWindow()}
              disabled={isAnalyzing || !selectedWindowHours}
              type="button"
            >
              {isAnalyzing ? "Analisando..." : "Analisar mensagens"}
            </button>
          </div>
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

      <section className="chat-panel panel-span">
        <div className="memory-header">
          <div>
            <span className="panel-kicker">Chat Personalizado</span>
            <h2>Converse com a IA do dono</h2>
          </div>
          <div className="chat-thread-meta">
            <span>{chatThreadTitle}</span>
            <strong>{projects.length} projetos mapeados</strong>
          </div>
        </div>

        <div className="chat-grid">
          <article className="project-panel">
            <div className="snapshot-panel-head">
              <span className="card-kicker">Projetos e frentes</span>
              <span className="summary-meta">Atualizados pelas analises</span>
            </div>

            {projects.length === 0 ? (
              <div className="snapshot-empty">
                <strong>Nenhum projeto consolidado ainda</strong>
                <p>As proximas analises vao extrair projetos, operacoes e frentes importantes do dono.</p>
              </div>
            ) : (
              <div className="project-list">
                {projects.map((project) => (
                  <article key={project.id} className="project-card">
                    <div className="snapshot-topline">
                      <strong>{project.project_name}</strong>
                      <span>{project.last_seen_at ? formatDateTime(project.last_seen_at) : "Sem data"}</span>
                    </div>
                    <p className="snapshot-summary">{project.summary}</p>
                    {project.status ? (
                      <div className="project-status-row">
                        <span className="project-status-label">Status</span>
                        <strong>{project.status}</strong>
                      </div>
                    ) : null}
                    <SignalGroup title="Proximos passos" items={project.next_steps} />
                    <SignalGroup title="Evidencias" items={project.evidence} />
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="chat-conversation-panel">
            <div className="snapshot-panel-head">
              <span className="card-kicker">Conversa com Groq</span>
              <span className="summary-meta">Respostas personalizadas com memoria + projetos</span>
            </div>

            {chatError ? (
              <div className="error-card memory-error">
                <strong>Falha no chat</strong>
                <p>{chatError}</p>
              </div>
            ) : null}

            <div ref={chatScrollRef} className="chat-history">
              {chatMessages.length === 0 ? (
                <div className="chat-empty">
                  <strong>Sem conversa ainda</strong>
                  <p>
                    Assim que voce enviar a primeira mensagem, o AuraCore responde usando o resumo do dono,
                    os snapshots recentes e os projetos consolidados.
                  </p>
                </div>
              ) : (
                chatMessages.map((message) => (
                  <article
                    key={message.id}
                    className={`chat-bubble${message.role === "assistant" ? " chat-bubble-assistant" : " chat-bubble-user"}`}
                  >
                    <div className="chat-bubble-head">
                      <strong>{message.role === "assistant" ? "AuraCore" : "Voce"}</strong>
                      <span>{formatDateTime(message.created_at)}</span>
                    </div>
                    <p>{message.content}</p>
                  </article>
                ))
              )}
            </div>

            <div className="chat-composer">
              <label className="chat-input-card">
                <span>Mensagem para a IA</span>
                <textarea
                  value={chatDraft}
                  onChange={(event) => setChatDraft(event.target.value)}
                  rows={4}
                  placeholder="Ex.: O que voce entendeu sobre meus projetos esta semana?"
                />
              </label>

              <button
                className="connect-button"
                onClick={() => void submitChatMessage()}
                disabled={isSendingChat}
                type="button"
              >
                {isSendingChat ? "Respondendo..." : "Enviar para a IA"}
              </button>
            </div>
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
