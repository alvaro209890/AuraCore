"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeMemory,
  connectObserver,
  getChatSession,
  getObserverStatus,
  refineMemory,
  resetObserver,
  sendChatMessage,
  type ChatMessage,
  type MemoryCurrent,
  type ObserverStatus,
  type ProjectMemory,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";
type AgentMode = "analyze" | "refine";

type AgentStep = {
  threshold: number;
  label: string;
};

type AgentState = {
  mode: AgentMode | null;
  running: boolean;
  progress: number;
  status: string;
  error: string | null;
  completedAt: string | null;
};

const POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 25000;
const WINDOW_PRESETS = [6, 24, 72, 168];

const ANALYZE_STEPS: AgentStep[] = [
  { threshold: 8, label: "Lendo mensagens observadas do WhatsApp" },
  { threshold: 22, label: "Filtrando trechos com sinais úteis sobre o dono" },
  { threshold: 38, label: "Consultando resumo, projetos e memória já salvos" },
  { threshold: 56, label: "Cruzando o que o dono falou no chat com a IA" },
  { threshold: 76, label: "Pedindo ao DeepSeek para consolidar comportamento e projetos" },
  { threshold: 92, label: "Recebendo e aplicando a atualização do perfil" },
];

const REFINE_STEPS: AgentStep[] = [
  { threshold: 10, label: "Lendo o resumo consolidado já salvo" },
  { threshold: 28, label: "Revisando snapshots e projetos persistidos" },
  { threshold: 48, label: "Considerando as conversas recentes com a IA" },
  { threshold: 72, label: "Pedindo ao DeepSeek para limpar ruído e contradições" },
  { threshold: 92, label: "Gravando a versão refinada do perfil no Supabase" },
];

const IDLE_AGENT_STATUS = "Pronto para atualizar a memória do dono.";

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

function getAgentSteps(mode: AgentMode | null): AgentStep[] {
  if (mode === "refine") {
    return REFINE_STEPS;
  }
  return ANALYZE_STEPS;
}

function getRunningStatus(mode: AgentMode, progress: number): string {
  const activeStep = [...getAgentSteps(mode)].reverse().find((step) => progress >= step.threshold);
  return activeStep?.label ?? "Preparando contexto da atualização";
}

function getProgressIncrement(progress: number): number {
  if (progress < 20) {
    return 6;
  }
  if (progress < 40) {
    return 5;
  }
  if (progress < 65) {
    return 4;
  }
  if (progress < 82) {
    return 3;
  }
  return 1;
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
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [chatDraft, setChatDraft] = useState("");
  const [windowHoursInput, setWindowHoursInput] = useState("24");
  const [agentState, setAgentState] = useState<AgentState>({
    mode: null,
    running: false,
    progress: 0,
    status: IDLE_AGENT_STATUS,
    error: null,
    completedAt: null,
  });
  const lastQrRefreshAtRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const agentTimerRef = useRef<number | null>(null);

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

  const activeAgentSteps = useMemo(() => getAgentSteps(agentState.mode), [agentState.mode]);

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

  useEffect(() => {
    return () => {
      if (agentTimerRef.current) {
        window.clearInterval(agentTimerRef.current);
      }
    };
  }, []);

  async function hydrateDashboard(): Promise<void> {
    setIsHydrating(true);

    const [statusResult, chatResult] = await Promise.allSettled([
      getObserverStatus(false),
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

    if (chatResult.status === "fulfilled") {
      setChatThreadTitle(chatResult.value.title);
      setChatMessages(chatResult.value.messages);
      setProjects(chatResult.value.projects);
      setMemory(chatResult.value.current);
      setChatError(null);
      setMemoryError(null);
    } else {
      const message = getErrorMessage(chatResult.reason);
      setChatError(message);
      setMemoryError(message);
    }

    setIsHydrating(false);
  }

  function startAgentRun(mode: AgentMode): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }

    setAgentState({
      mode,
      running: true,
      progress: 4,
      status: getRunningStatus(mode, 4),
      error: null,
      completedAt: null,
    });

    agentTimerRef.current = window.setInterval(() => {
      setAgentState((previous) => {
        if (!previous.running || previous.mode !== mode) {
          return previous;
        }

        const nextProgress = Math.min(previous.progress + getProgressIncrement(previous.progress), 94);
        return {
          ...previous,
          progress: nextProgress,
          status: getRunningStatus(mode, nextProgress),
        };
      });
    }, 520);
  }

  function finishAgentRunSuccess(mode: AgentMode, statusText: string): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      running: false,
      progress: 100,
      status: statusText,
      error: null,
      completedAt: new Date().toISOString(),
    });
  }

  function finishAgentRunError(mode: AgentMode, errorText: string): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      running: false,
      progress: 0,
      status: "A atualização falhou antes de concluir.",
      error: errorText,
      completedAt: null,
    });
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

    setMemoryError(null);
    startAgentRun("analyze");

    try {
      const response = await analyzeMemory(selectedWindowHours);
      setMemory(response.current);
      setProjects(response.projects);
      finishAgentRunSuccess("analyze", "Memória atualizada com a nova leitura do DeepSeek.");
    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError("analyze", message);
    }
  }

  async function refineSavedMemoryAction(): Promise<void> {
    setMemoryError(null);
    startAgentRun("refine");

    try {
      const response = await refineMemory();
      setMemory(response.current);
      setProjects(response.projects);
      finishAgentRunSuccess("refine", "Memória refinada com foco no perfil já salvo.");
    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError("refine", message);
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
    <main className="shell shell-wide">
      <section className="hero-panel panel-span">
        <div className="eyebrow">AuraCore / Perfil Vivo</div>
        <h1>Um segundo cerebro que observa, consolida e conversa como se ja te conhecesse.</h1>
        <p className="hero-copy">
          O Numero A alimenta a memoria. O DeepSeek consolida comportamento, rotina e projetos. O
          Groq responde com esse contexto. O painel abaixo mostra a conexao, o perfil atual e o
          que o agente esta fazendo enquanto a memoria evolui.
        </p>

        <div className="metric-strip">
          <div className="metric-card">
            <span className="metric-label">Estado do observador</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">Projetos rastreados</span>
            <strong>{projects.length}</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">Ultima memoria</span>
            <strong>{memory?.last_analyzed_at ? formatDateTime(memory.last_analyzed_at) : "Ainda sem consolidacao"}</strong>
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
                  : "Clique no botao para abrir uma nova sessao e gerar o QR Code."}
              </p>
            </div>
          )}

          <div className="status-copy">
            <span className={`status-pill status-${viewState}`}>{statusLabel}</span>
            <p>
              {status?.connected
                ? "O gateway esta online e os chats diretos passam a alimentar a memoria do dono."
                : "Depois de escanear o QR, o painel atualiza automaticamente ate a conexao ficar ativa."}
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
            <dt>Ultima atualizacao</dt>
            <dd>{formatDateTime(status?.last_seen_at)}</dd>
          </div>
        </dl>
      </section>

      <section className="memory-hub-panel">
        <div className="memory-header">
          <div>
            <span className="panel-kicker">Memoria do Dono</span>
            <h2>Perfil atual e frentes ativas</h2>
          </div>
          <div className="connection-actions">
            <button
              className="reset-button"
              onClick={() => void refineSavedMemoryAction()}
              disabled={agentState.running}
              type="button"
            >
              {agentState.running && agentState.mode === "refine" ? "Refinando..." : "Refinar memoria salva"}
            </button>
            <button
              className="analyze-button"
              onClick={() => void analyzeSelectedWindow()}
              disabled={agentState.running || !selectedWindowHours}
              type="button"
            >
              {agentState.running && agentState.mode === "analyze" ? "Analisando..." : "Analisar mensagens"}
            </button>
          </div>
        </div>

        <div className="analysis-controls analysis-controls-tight">
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
            <span>Janela para a proxima leitura</span>
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
              ? `A proxima leitura junta as mensagens das ultimas ${selectedWindowHours} horas e cruza isso com memoria, projetos e chat.`
              : "Informe um numero inteiro de horas para montar a janela de analise."}
          </div>
        </div>

        {memoryError ? (
          <div className="error-card memory-error">
            <strong>Falha na atualizacao da memoria</strong>
            <p>{memoryError}</p>
          </div>
        ) : null}

        <div className="memory-hub-grid">
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

          <article className="project-rail">
            <div className="snapshot-panel-head">
              <span className="card-kicker">Projetos e frentes</span>
              <span className="summary-meta">{projects.length} itens ativos</span>
            </div>

            {projects.length === 0 ? (
              <div className="snapshot-empty">
                <strong>Nenhum projeto consolidado ainda</strong>
                <p>Assim que a memoria ficar mais rica, o DeepSeek passa a destacar as frentes mais recorrentes do dono.</p>
              </div>
            ) : (
              <div className="project-mini-list">
                {projects.map((project) => (
                  <article key={project.id} className="project-mini-card">
                    <div className="project-mini-top">
                      <strong>{project.project_name}</strong>
                      <span>{project.last_seen_at ? formatDateTime(project.last_seen_at) : "Sem data"}</span>
                    </div>
                    <p>{project.summary}</p>
                    {project.status ? <div className="project-mini-status">{project.status}</div> : null}
                  </article>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>

      <section className="agent-panel panel-span">
        <div className="memory-header">
          <div>
            <span className="panel-kicker">Agente de Memoria</span>
            <h2>Atualizacao em andamento</h2>
          </div>
          <div className="agent-meta">
            <span>
              {agentState.mode === null
                ? "Aguardando comando"
                : agentState.mode === "refine"
                  ? "Modo refinamento"
                  : "Modo leitura"}
            </span>
            <strong>{agentState.progress}%</strong>
          </div>
        </div>

        <div className="agent-grid">
          <article className="agent-progress-card">
            <div className="agent-current-line">
              <strong>{agentState.running ? "Executando agora" : "Estado atual"}</strong>
              <span>{agentState.status}</span>
            </div>

            <div className="progress-track" aria-hidden="true">
              <div
                className={`progress-fill${agentState.running ? " progress-fill-running" : ""}`}
                style={{ width: `${agentState.progress}%` }}
              />
            </div>

            <div className="agent-progress-meta">
              <span>{agentState.running ? "DeepSeek trabalhando com contexto vivo" : "Pronto para a proxima rodada"}</span>
              <span>{agentState.completedAt ? `Concluido em ${formatDateTime(agentState.completedAt)}` : "Sem rodada concluida agora"}</span>
            </div>

            {agentState.error ? (
              <div className="error-card agent-inline-error">
                <strong>Falha no agente</strong>
                <p>{agentState.error}</p>
              </div>
            ) : null}
          </article>

          <article className="agent-activity-card">
            <div className="snapshot-panel-head">
              <span className="card-kicker">Atividades</span>
              <span className="summary-meta">
                {agentState.running ? "Fluxo em execucao" : "Fila aguardando comando"}
              </span>
            </div>

            <div className="agent-activity-list">
              {activeAgentSteps.map((step) => {
                const isCompleted = agentState.progress >= step.threshold;
                const isActive =
                  agentState.running &&
                  agentState.progress >= step.threshold &&
                  !activeAgentSteps.some(
                    (candidate) => candidate.threshold > step.threshold && agentState.progress >= candidate.threshold,
                  );

                return (
                  <div
                    key={step.label}
                    className={`agent-activity${isCompleted ? " agent-activity-completed" : ""}${isActive ? " agent-activity-active" : ""}`}
                  >
                    <span className="agent-activity-dot" />
                    <div>
                      <strong>{step.label}</strong>
                      <p>
                        {isActive
                          ? "Etapa atual"
                          : isCompleted
                            ? "Concluida nesta rodada"
                            : "Na fila da atualizacao"}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
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
            <strong>{projects.length} projetos no contexto</strong>
          </div>
        </div>

        <div className="chat-stage-hint">
          O que voce conversa aqui tambem passa a influenciar futuras leituras e refinamentos de perfil.
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
                Quando voce enviar a primeira mensagem, o AuraCore responde usando memoria do dono,
                projetos salvos e o contexto observado no WhatsApp.
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
              placeholder="Ex.: O que voce entendeu sobre minha rotina e meus projetos esta semana?"
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
      </section>
    </main>
  );
}
