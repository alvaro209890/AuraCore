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
type TabId = "overview" | "observer" | "memory" | "projects" | "chat" | "activity";
type LogTone = "info" | "success" | "error";

type AgentStep = {
  threshold: number;
  label: string;
  detail: string;
};

type AgentLog = {
  id: string;
  tone: LogTone;
  createdAt: string;
  message: string;
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
const IDLE_AGENT_STATUS = "Nenhuma atualização em andamento.";

const ANALYZE_STEPS: AgentStep[] = [
  {
    threshold: 8,
    label: "Buscando mensagens diretas recentes",
    detail: "Lendo apenas conversas com contatos normais salvas no Supabase.",
  },
  {
    threshold: 24,
    label: "Filtrando sinais relevantes do dono",
    detail: "Separando hábitos, decisões, rotina, linguagem e trabalho.",
  },
  {
    threshold: 42,
    label: "Cruzando memória anterior e projetos",
    detail: "Usando resumo atual, projetos salvos e contexto de análises passadas.",
  },
  {
    threshold: 58,
    label: "Lendo o que foi conversado com a IA",
    detail: "Incluindo o histórico útil do chat para melhorar o perfil.",
  },
  {
    threshold: 78,
    label: "Pedindo consolidação ao DeepSeek",
    detail: "Gerando uma atualização mais coerente do perfil e das frentes ativas.",
  },
  {
    threshold: 94,
    label: "Persistindo o resultado",
    detail: "Atualizando memória consolidada e projetos no Supabase.",
  },
];

const REFINE_STEPS: AgentStep[] = [
  {
    threshold: 10,
    label: "Lendo a memória consolidada atual",
    detail: "Partindo do perfil salvo em vez de reprocessar tudo do zero.",
  },
  {
    threshold: 28,
    label: "Revisando projetos e contexto histórico",
    detail: "Buscando contradições, ruído e sinais fracos na memória existente.",
  },
  {
    threshold: 46,
    label: "Incluindo conversas recentes do chat",
    detail: "Usando o que o dono revelou à IA para corrigir prioridades e contexto.",
  },
  {
    threshold: 74,
    label: "Refinando o perfil com o DeepSeek",
    detail: "Pedindo uma versão mais limpa, precisa e útil para o assistente pessoal.",
  },
  {
    threshold: 94,
    label: "Salvando a memória refinada",
    detail: "Aplicando o novo resumo consolidado no Supabase.",
  },
];

const TABS: Array<{ id: TabId; label: string; kicker: string }> = [
  { id: "overview", label: "Visão Geral", kicker: "00" },
  { id: "observer", label: "Observador", kicker: "01" },
  { id: "memory", label: "Memória", kicker: "02" },
  { id: "projects", label: "Projetos", kicker: "03" },
  { id: "chat", label: "Chat", kicker: "04" },
  { id: "activity", label: "Atividade", kicker: "05" },
];

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
    return "Ainda indisponível";
  }

  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatShortDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Sem data";
  }

  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
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
  return "Não foi possível concluir a operação.";
}

function getProgressIncrement(progress: number): number {
  if (progress < 16) {
    return 7;
  }
  if (progress < 34) {
    return 5;
  }
  if (progress < 56) {
    return 4;
  }
  if (progress < 76) {
    return 3;
  }
  return 1;
}

function getStepsForMode(mode: AgentMode | null): AgentStep[] {
  return mode === "refine" ? REFINE_STEPS : ANALYZE_STEPS;
}

function getRunningStatus(mode: AgentMode, progress: number): string {
  const step = [...getStepsForMode(mode)].reverse().find((candidate) => progress >= candidate.threshold);
  return step?.label ?? "Preparando atualização";
}

function makeLog(tone: LogTone, message: string): AgentLog {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    tone,
    createdAt: new Date().toISOString(),
    message,
  };
}

export function ConnectionDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [windowHoursInput, setWindowHoursInput] = useState("24");
  const [chatDraft, setChatDraft] = useState("");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>({
    mode: null,
    running: false,
    progress: 0,
    status: IDLE_AGENT_STATUS,
    error: null,
    completedAt: null,
  });
  const [agentLogs, setAgentLogs] = useState<AgentLog[]>([
    makeLog("info", "Painel iniciado. Aguardando a próxima leitura ou refinamento."),
  ]);

  const lastQrRefreshAtRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const agentTimerRef = useRef<number | null>(null);
  const agentStepIndexRef = useRef(0);

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

  const currentSteps = useMemo(() => getStepsForMode(agentState.mode), [agentState.mode]);

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
  }, [chatMessages, activeTab]);

  useEffect(() => {
    return () => {
      if (agentTimerRef.current) {
        window.clearInterval(agentTimerRef.current);
      }
    };
  }, []);

  async function hydrateDashboard(mode: "initial" | "manual" = "initial"): Promise<void> {
    if (mode === "manual") {
      setIsRefreshing(true);
    } else {
      setIsHydrating(true);
    }

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

    if (mode === "manual") {
      setIsRefreshing(false);
    } else {
      setIsHydrating(false);
    }
  }

  function pushAgentLog(tone: LogTone, message: string): void {
    setAgentLogs((previous) => [makeLog(tone, message), ...previous].slice(0, 24));
  }

  function startAgentRun(mode: AgentMode): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }

    agentStepIndexRef.current = 0;
    setActiveTab("activity");
    setAgentState({
      mode,
      running: true,
      progress: 4,
      status: getRunningStatus(mode, 4),
      error: null,
      completedAt: null,
    });
    pushAgentLog(
      "info",
      mode === "analyze"
        ? "Nova leitura iniciada. O agente vai consolidar mensagens recentes com memória e chat."
        : "Refinamento iniciado. O agente vai limpar e fortalecer o perfil já salvo.",
    );

    agentTimerRef.current = window.setInterval(() => {
      setAgentState((previous) => {
        if (!previous.running || previous.mode !== mode) {
          return previous;
        }

        const nextProgress = Math.min(previous.progress + getProgressIncrement(previous.progress), 94);
        const steps = getStepsForMode(mode);
        while (agentStepIndexRef.current < steps.length && nextProgress >= steps[agentStepIndexRef.current].threshold) {
          const step = steps[agentStepIndexRef.current];
          pushAgentLog("info", `${step.label}. ${step.detail}`);
          agentStepIndexRef.current += 1;
        }

        return {
          ...previous,
          progress: nextProgress,
          status: getRunningStatus(mode, nextProgress),
        };
      });
    }, 520);
  }

  function finishAgentRunSuccess(mode: AgentMode, message: string): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      running: false,
      progress: 100,
      status: message,
      error: null,
      completedAt: new Date().toISOString(),
    });
    pushAgentLog("success", message);
  }

  function finishAgentRunError(mode: AgentMode, message: string): void {
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      running: false,
      progress: 0,
      status: "A atualização falhou antes de concluir.",
      error: message,
      completedAt: null,
    });
    pushAgentLog("error", message);
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
      pushAgentLog("info", "Fluxo de conexão iniciado para o observador do WhatsApp.");
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
      pushAgentLog("info", "Sessão do observador resetada. Novo QR pronto para leitura.");
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
        pushAgentLog("success", "Observador conectado. Mensagens diretas já podem alimentar a memória.");
        return;
      }

      setViewState("waiting");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(error));
    }
  }

  async function runMemoryJob(mode: AgentMode): Promise<void> {
    setMemoryError(null);
    startAgentRun(mode);

    try {
      if (mode === "analyze") {
        if (!selectedWindowHours) {
          throw new Error("Informe uma janela válida em horas.");
        }
        const response = await analyzeMemory(selectedWindowHours);
        setMemory(response.current);
        setProjects(response.projects);
        finishAgentRunSuccess("analyze", "Leitura concluída. Perfil e projetos atualizados.");
        return;
      }

      const response = await refineMemory();
      setMemory(response.current);
      setProjects(response.projects);
      finishAgentRunSuccess("refine", "Refinamento concluído. Perfil consolidado ficou mais limpo.");
    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError(mode, message);
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
      pushAgentLog("info", "Nova conversa salva no chat. Esse contexto entra nas próximas leituras da memória.");
    } catch (error) {
      setChatError(getErrorMessage(error));
      setActiveTab("chat");
    } finally {
      setIsSendingChat(false);
    }
  }

  return (
    <main className="workspace-shell">
      <aside className="workspace-sidebar">
        <div className="brand-block">
          <span className="brand-mark">AuraCore</span>
          <h1>Segundo cérebro pessoal</h1>
          <p>Abas separadas para observar, atualizar memória, acompanhar projetos e conversar com a IA.</p>
        </div>

        <nav className="tab-nav" aria-label="Navegação principal">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-button${activeTab === tab.id ? " tab-button-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              <span className="tab-kicker">{tab.kicker}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-status">
          <div className="sidebar-status-card">
            <span className="sidebar-label">Observador</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="sidebar-label">Projetos</span>
            <strong>{projects.length}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="sidebar-label">Última memória</span>
            <strong>{memory?.last_analyzed_at ? formatShortDateTime(memory.last_analyzed_at) : "Sem leitura"}</strong>
          </div>
        </div>
      </aside>

      <section className="workspace-main">
        <header className="topbar">
          <div>
            <span className="topbar-kicker">Painel principal</span>
            <h2>{getTabTitle(activeTab)}</h2>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" onClick={() => void hydrateDashboard("manual")} disabled={isRefreshing} type="button">
              {isRefreshing ? "Atualizando..." : "Atualizar painel"}
            </button>
            <button className="primary-button" onClick={() => void runMemoryJob("analyze")} disabled={agentState.running} type="button">
              {agentState.running && agentState.mode === "analyze" ? "Lendo..." : "Nova leitura"}
            </button>
          </div>
        </header>

        {isHydrating ? (
          <section className="stage-card">
            <div className="empty-state">
              <strong>Carregando o AuraCore</strong>
              <p>Buscando status do observador, perfil atual, projetos e histórico do chat.</p>
            </div>
          </section>
        ) : (
          <>
            {activeTab === "overview" ? (
              <OverviewTab
                memory={memory}
                projects={projects}
                status={status}
                statusLabel={statusLabel}
                connectionError={connectionError}
                memoryError={memoryError}
                agentState={agentState}
                onGoToObserver={() => setActiveTab("observer")}
                onGoToMemory={() => setActiveTab("memory")}
                onGoToChat={() => setActiveTab("chat")}
              />
            ) : null}

            {activeTab === "observer" ? (
              <ObserverTab
                status={status}
                statusLabel={statusLabel}
                viewState={viewState}
                isSubmitting={isSubmitting}
                isResetting={isResetting}
                connectionError={connectionError}
                onConnect={() => void startConnection()}
                onReset={() => void resetConnection()}
              />
            ) : null}

            {activeTab === "memory" ? (
              <MemoryTab
                memory={memory}
                memoryError={memoryError}
                agentState={agentState}
                selectedWindowHours={selectedWindowHours}
                windowHoursInput={windowHoursInput}
                onWindowHoursInputChange={setWindowHoursInput}
                onAnalyze={() => void runMemoryJob("analyze")}
                onRefine={() => void runMemoryJob("refine")}
              />
            ) : null}

            {activeTab === "projects" ? <ProjectsTab projects={projects} /> : null}

            {activeTab === "chat" ? (
              <ChatTab
                chatThreadTitle={chatThreadTitle}
                chatMessages={chatMessages}
                chatDraft={chatDraft}
                chatError={chatError}
                isSendingChat={isSendingChat}
                chatScrollRef={chatScrollRef}
                onChatDraftChange={setChatDraft}
                onSubmit={() => void submitChatMessage()}
              />
            ) : null}

            {activeTab === "activity" ? (
              <ActivityTab
                agentState={agentState}
                steps={currentSteps}
                logs={agentLogs}
              />
            ) : null}
          </>
        )}
      </section>
    </main>
  );
}

function getTabTitle(tab: TabId): string {
  switch (tab) {
    case "overview":
      return "Visão geral do segundo cérebro";
    case "observer":
      return "Conexão do observador do WhatsApp";
    case "memory":
      return "Leituras e refinamento da memória";
    case "projects":
      return "Projetos, frentes e contexto ativo";
    case "chat":
      return "Chat personalizado com contexto do dono";
    case "activity":
      return "Atividade do agente de memória";
  }
}

function OverviewTab({
  memory,
  projects,
  status,
  statusLabel,
  connectionError,
  memoryError,
  agentState,
  onGoToObserver,
  onGoToMemory,
  onGoToChat,
}: {
  memory: MemoryCurrent | null;
  projects: ProjectMemory[];
  status: ObserverStatus | null;
  statusLabel: string;
  connectionError: string | null;
  memoryError: string | null;
  agentState: AgentState;
  onGoToObserver: () => void;
  onGoToMemory: () => void;
  onGoToChat: () => void;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-hero">
        <span className="section-kicker">Perfil vivo</span>
        <h3>O AuraCore agora está dividido por áreas, com menos ruído e mais previsibilidade.</h3>
        <p>
          O observador alimenta o banco com mensagens diretas. A memória consolida quem é o dono,
          o agente mostra a atualização em andamento e o chat usa esse contexto para responder de forma
          pessoal.
        </p>
        <div className="hero-actions">
          <button className="primary-button" onClick={onGoToObserver} type="button">
            Abrir conexão
          </button>
          <button className="ghost-button" onClick={onGoToMemory} type="button">
            Abrir memória
          </button>
          <button className="ghost-button" onClick={onGoToChat} type="button">
            Abrir chat
          </button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="Estado do observador" value={statusLabel} />
        <StatCard label="Número conectado" value={status?.owner_number ?? "Aguardando leitura"} />
        <StatCard label="Projetos ativos" value={String(projects.length)} />
        <StatCard
          label="Última atualização"
          value={memory?.last_analyzed_at ? formatDateTime(memory.last_analyzed_at) : "Ainda sem leitura"}
        />
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Resumo atual</span>
          <span className="meta-text">
            {memory?.last_analyzed_at ? `Atualizado em ${formatDateTime(memory.last_analyzed_at)}` : "Sem resumo consolidado"}
          </span>
        </div>
        <p className="summary-copy">
          {memory?.life_summary?.trim()
            ? memory.life_summary
            : "Ainda não existe um perfil consolidado. Conecte o observador, deixe o histórico chegar e rode a primeira leitura."}
        </p>
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Estado do agente</span>
          <span className="meta-text">{agentState.mode === "refine" ? "Refinamento" : "Leitura"}</span>
        </div>
        <div className="progress-track">
          <div className={`progress-fill${agentState.running ? " progress-fill-running" : ""}`} style={{ width: `${agentState.progress}%` }} />
        </div>
        <p className="summary-copy summary-copy-tight">{agentState.status}</p>
        {agentState.error ? <InlineError title="Falha do agente" message={agentState.error} /> : null}
      </section>

      {connectionError ? <InlineError title="Falha na conexão" message={connectionError} /> : null}
      {memoryError ? <InlineError title="Falha na memória" message={memoryError} /> : null}
    </div>
  );
}

function ObserverTab({
  status,
  statusLabel,
  viewState,
  isSubmitting,
  isResetting,
  connectionError,
  onConnect,
  onReset,
}: {
  status: ObserverStatus | null;
  statusLabel: string;
  viewState: ViewState;
  isSubmitting: boolean;
  isResetting: boolean;
  connectionError: string | null;
  onConnect: () => void;
  onReset: () => void;
}) {
  return (
    <div className="content-grid observer-grid">
      <section className="stage-card observer-card">
        <div className="card-head">
          <span className="section-kicker">QR Code</span>
          <span className={`status-pill status-${viewState}`}>{statusLabel}</span>
        </div>

        {status?.qr_code ? (
          <div className="qr-frame">
            <img className="qr-image" src={status.qr_code} alt="QR Code do WhatsApp observador" />
          </div>
        ) : (
          <div className="empty-state empty-state-soft">
            <strong>QR indisponível</strong>
            <p>
              {status?.connected
                ? "A sessão já está conectada. Não é necessário gerar um novo QR."
                : "Gere uma nova sessão para exibir o QR do observador."}
            </p>
          </div>
        )}

        <div className="hero-actions">
          <button className="primary-button" onClick={onConnect} disabled={isSubmitting || viewState === "connected"} type="button">
            {viewState === "connected" ? "Observador conectado" : isSubmitting ? "Gerando QR..." : "Conectar observador"}
          </button>
          <button className="ghost-button" onClick={onReset} disabled={isResetting} type="button">
            {isResetting ? "Resetando..." : "Resetar sessão"}
          </button>
        </div>

        {connectionError ? <InlineError title="Falha na conexão" message={connectionError} /> : null}
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Status da instância</span>
          <span className="meta-text">{status?.instance_name ?? "observer"}</span>
        </div>
        <dl className="detail-list">
          <div>
            <dt>Número dono</dt>
            <dd>{status?.owner_number ?? "Aguardando leitura"}</dd>
          </div>
          <div>
            <dt>Gateway</dt>
            <dd>{status?.gateway_ready ? "Online" : "Indisponível"}</dd>
          </div>
          <div>
            <dt>Ingestão</dt>
            <dd>{status?.ingestion_ready ? "Pronta" : "Pendente"}</dd>
          </div>
          <div>
            <dt>Última atualização</dt>
            <dd>{formatDateTime(status?.last_seen_at)}</dd>
          </div>
          <div>
            <dt>Expira em</dt>
            <dd>{status?.connected ? "Sessão ativa" : status?.qr_expires_in_sec ? `${status.qr_expires_in_sec}s` : "Sem QR ativo"}</dd>
          </div>
          <div>
            <dt>Coleta</dt>
            <dd>Somente contatos diretos</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

function MemoryTab({
  memory,
  memoryError,
  agentState,
  selectedWindowHours,
  windowHoursInput,
  onWindowHoursInputChange,
  onAnalyze,
  onRefine,
}: {
  memory: MemoryCurrent | null;
  memoryError: string | null;
  agentState: AgentState;
  selectedWindowHours: number | null;
  windowHoursInput: string;
  onWindowHoursInputChange: (value: string) => void;
  onAnalyze: () => void;
  onRefine: () => void;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Leitura de memória</span>
          <span className="meta-text">DeepSeek com mensagens, memória e chat</span>
        </div>

        <div className="preset-row">
          {WINDOW_PRESETS.map((hours) => {
            const active = selectedWindowHours === hours;
            return (
              <button
                key={hours}
                className={`chip-button${active ? " chip-button-active" : ""}`}
                onClick={() => onWindowHoursInputChange(String(hours))}
                type="button"
              >
                {formatHoursLabel(hours)}
              </button>
            );
          })}
        </div>

        <label className="input-shell">
          <span>Janela personalizada em horas</span>
          <input
            type="number"
            min={1}
            step={1}
            value={windowHoursInput}
            onChange={(event) => onWindowHoursInputChange(event.target.value)}
          />
        </label>

        <p className="meta-paragraph">
          {selectedWindowHours
            ? `A próxima leitura vai consolidar as últimas ${selectedWindowHours} horas com o perfil atual e o histórico do chat.`
            : "Informe uma janela válida antes de iniciar a leitura."}
        </p>

        <div className="hero-actions">
          <button className="primary-button" onClick={onAnalyze} disabled={agentState.running || !selectedWindowHours} type="button">
            {agentState.running && agentState.mode === "analyze" ? "Lendo..." : "Analisar mensagens"}
          </button>
          <button className="ghost-button" onClick={onRefine} disabled={agentState.running} type="button">
            {agentState.running && agentState.mode === "refine" ? "Refinando..." : "Refinar memória salva"}
          </button>
        </div>
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Perfil consolidado</span>
          <span className="meta-text">
            {memory?.last_analyzed_at ? `Atualizado em ${formatDateTime(memory.last_analyzed_at)}` : "Sem atualização ainda"}
          </span>
        </div>
        <p className="summary-copy">
          {memory?.life_summary?.trim()
            ? memory.life_summary
            : "Nenhum resumo consolidado ainda. A primeira leitura vai transformar conversas diretas em um perfil mais coerente do dono."}
        </p>
        {memoryError ? <InlineError title="Falha na memória" message={memoryError} /> : null}
      </section>
    </div>
  );
}

function ProjectsTab({ projects }: { projects: ProjectMemory[] }) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-span">
        <div className="card-head">
          <span className="section-kicker">Projetos e frentes</span>
          <span className="meta-text">{projects.length} itens em contexto</span>
        </div>

        {projects.length === 0 ? (
          <div className="empty-state">
            <strong>Nenhum projeto consolidado ainda</strong>
            <p>Assim que a memória ficar mais rica, o DeepSeek passa a destacar frentes recorrentes e status de trabalho.</p>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <article key={project.id} className="project-card">
                <div className="project-card-head">
                  <strong>{project.project_name}</strong>
                  <span>{project.last_seen_at ? formatShortDateTime(project.last_seen_at) : "Sem data"}</span>
                </div>
                <p>{project.summary}</p>
                {project.status ? <div className="project-status">{project.status}</div> : null}
                {project.next_steps.length > 0 ? (
                  <div className="tag-list">
                    {project.next_steps.slice(0, 4).map((step, index) => (
                      <span key={`${project.id}-step-${index}`} className="tag-chip">
                        {step}
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ChatTab({
  chatThreadTitle,
  chatMessages,
  chatDraft,
  chatError,
  isSendingChat,
  chatScrollRef,
  onChatDraftChange,
  onSubmit,
}: {
  chatThreadTitle: string;
  chatMessages: ChatMessage[];
  chatDraft: string;
  chatError: string | null;
  isSendingChat: boolean;
  chatScrollRef: React.RefObject<HTMLDivElement | null>;
  onChatDraftChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-span">
        <div className="card-head">
          <div>
            <span className="section-kicker">Chat personalizado</span>
            <h3 className="section-title">{chatThreadTitle}</h3>
          </div>
          <span className="meta-text">O histórico daqui alimenta futuras leituras da memória</span>
        </div>

        {chatError ? <InlineError title="Falha no chat" message={chatError} /> : null}

        <div ref={chatScrollRef} className="chat-history-board">
          {chatMessages.length === 0 ? (
            <div className="empty-state">
              <strong>Sem conversa ainda</strong>
              <p>Envie a primeira mensagem para testar a IA personalizada com base no contexto atual do dono.</p>
            </div>
          ) : (
            chatMessages.map((message) => (
              <article key={message.id} className={`chat-message${message.role === "assistant" ? " chat-message-assistant" : " chat-message-user"}`}>
                <div className="chat-message-head">
                  <strong>{message.role === "assistant" ? "AuraCore" : "Você"}</strong>
                  <span>{formatShortDateTime(message.created_at)}</span>
                </div>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </div>

        <div className="composer">
          <label className="input-shell input-shell-textarea">
            <span>Mensagem para a IA</span>
            <textarea
              rows={4}
              value={chatDraft}
              onChange={(event) => onChatDraftChange(event.target.value)}
              placeholder="Ex.: O que você já entendeu sobre minha rotina e meus projetos atuais?"
            />
          </label>
          <button className="primary-button" onClick={onSubmit} disabled={isSendingChat} type="button">
            {isSendingChat ? "Respondendo..." : "Enviar para a IA"}
          </button>
        </div>
      </section>
    </div>
  );
}

function ActivityTab({
  agentState,
  steps,
  logs,
}: {
  agentState: AgentState;
  steps: AgentStep[];
  logs: AgentLog[];
}) {
  return (
    <div className="content-grid">
      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Andamento do agente</span>
          <span className="meta-text">
            {agentState.mode === "refine" ? "Refinamento manual" : agentState.mode === "analyze" ? "Leitura de mensagens" : "Aguardando"}
          </span>
        </div>

        <div className="activity-meter">
          <strong>{agentState.progress}%</strong>
          <span>{agentState.status}</span>
        </div>

        <div className="progress-track">
          <div className={`progress-fill${agentState.running ? " progress-fill-running" : ""}`} style={{ width: `${agentState.progress}%` }} />
        </div>

        <div className="steps-list">
          {steps.map((step) => {
            const completed = agentState.progress >= step.threshold;
            const active =
              agentState.running &&
              agentState.progress >= step.threshold &&
              !steps.some((candidate) => candidate.threshold > step.threshold && agentState.progress >= candidate.threshold);

            return (
              <article
                key={step.label}
                className={`step-card${completed ? " step-card-completed" : ""}${active ? " step-card-active" : ""}`}
              >
                <div className="step-card-head">
                  <strong>{step.label}</strong>
                  <span>{completed ? "ok" : "fila"}</span>
                </div>
                <p>{step.detail}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Log do agente</span>
          <span className="meta-text">{logs.length} eventos recentes</span>
        </div>
        <div className="log-list">
          {logs.map((log) => (
            <article key={log.id} className={`log-item log-item-${log.tone}`}>
              <div className="log-item-head">
                <strong>{formatShortDateTime(log.createdAt)}</strong>
                <span>{log.tone}</span>
              </div>
              <p>{log.message}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function InlineError({ title, message }: { title: string; message: string }) {
  return (
    <div className="inline-error">
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}
