"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeMemoryWithFilters,
  connectObserver,
  getChatSession,
  getMemorySnapshots,
  getObserverStatus,
  previewMemoryAnalysis,
  refineMemory,
  resetObserver,
  sendChatMessage,
  type ChatMessage,
  type MemoryAnalysisDetailMode,
  type MemoryAnalysisPreview,
  type MemoryCurrent,
  type MemorySnapshot,
  type ObserverStatus,
  type ProjectMemory,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";
type AgentMode = "idle" | "analyze" | "refine";
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
  mode: AgentMode;
  running: boolean;
  progress: number;
  status: string;
  error: string | null;
  completedAt: string | null;
};

type MemoryFilters = {
  targetMessageCount: number;
  maxLookbackHours: number;
  detailMode: MemoryAnalysisDetailMode;
};

type InsightMetric = {
  label: string;
  value: number;
  description: string;
};

const POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 25000;
const MESSAGE_TARGET_PRESETS = [80, 140, 220, 320];
const LOOKBACK_PRESETS = [24, 72, 168];
const DETAIL_OPTIONS: Array<{ value: MemoryAnalysisDetailMode; label: string; description: string }> = [
  { value: "light", label: "Leve", description: "Menos contexto, menos tokens." },
  { value: "balanced", label: "Equilibrada", description: "Boa profundidade para rotina e projetos." },
  { value: "deep", label: "Profunda", description: "Mais contexto e leitura mais cara." },
];

const IDLE_AGENT_STATUS = "Nenhuma atualização em andamento.";

const ANALYZE_STEPS: AgentStep[] = [
  {
    threshold: 8,
    label: "Buscando mensagens diretas recentes",
    detail: "Lendo apenas contatos normais salvos no Supabase, sem grupos.",
  },
  {
    threshold: 24,
    label: "Separando sinais do dono",
    detail: "Mapeando rotina, linguagem, decisões, trabalho e relações úteis.",
  },
  {
    threshold: 42,
    label: "Cruzando memória e projetos",
    detail: "Comparando a janela nova com o perfil salvo e com as frentes já consolidadas.",
  },
  {
    threshold: 60,
    label: "Lendo contexto do chat pessoal",
    detail: "Incluindo o que o dono revelou nas conversas com a IA.",
  },
  {
    threshold: 80,
    label: "Pedindo consolidação ao DeepSeek",
    detail: "Gerando resumo comportamental, sinais do dono e atualização de projetos.",
  },
  {
    threshold: 94,
    label: "Persistindo no Supabase",
    detail: "Salvando snapshot, resumo atual e projetos enriquecidos.",
  },
];

const REFINE_STEPS: AgentStep[] = [
  {
    threshold: 10,
    label: "Lendo memória consolidada atual",
    detail: "Partindo do que já foi salvo para remover ruído e contradições.",
  },
  {
    threshold: 34,
    label: "Revisando projetos e chat",
    detail: "Usando os sinais já consolidados e as conversas recentes com a IA.",
  },
  {
    threshold: 70,
    label: "Refinando o perfil com o DeepSeek",
    detail: "Fortalecendo o que é recorrente e enfraquecendo o que é fraco.",
  },
  {
    threshold: 94,
    label: "Aplicando o refinamento",
    detail: "Atualizando resumo atual e frentes de trabalho no banco.",
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

function formatTokenCount(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
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

function getStepsForMode(mode: AgentMode): AgentStep[] {
  return mode === "refine" ? REFINE_STEPS : ANALYZE_STEPS;
}

function getRunningStatus(mode: AgentMode, progress: number): string {
  if (mode === "idle") {
    return IDLE_AGENT_STATUS;
  }
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

function getPreviewTone(score: number): string {
  if (score >= 78) {
    return "high";
  }
  if (score >= 55) {
    return "medium";
  }
  if (score >= 32) {
    return "soft";
  }
  return "low";
}

function getSignalMetrics(snapshot: MemorySnapshot | null): InsightMetric[] {
  return [
    {
      label: "Aprendizados",
      value: snapshot?.key_learnings.length ?? 0,
      description: "Sinais concretos do jeito de agir e das prioridades do dono.",
    },
    {
      label: "Rotina",
      value: snapshot?.routine_signals.length ?? 0,
      description: "Pistas de horários, cadência e hábitos recorrentes.",
    },
    {
      label: "Preferências",
      value: snapshot?.preferences.length ?? 0,
      description: "Gostos, padrões de escolha e critérios do dono.",
    },
    {
      label: "Lacunas",
      value: snapshot?.open_questions.length ?? 0,
      description: "Pontos ainda frágeis para a IA aprender melhor.",
    },
  ];
}

function getProjectStrength(project: ProjectMemory): number {
  const raw = 26 + (project.next_steps.length * 12) + (project.evidence.length * 8);
  return Math.max(22, Math.min(100, raw));
}

function getAudienceLabel(project: ProjectMemory): string {
  if (project.built_for.trim()) {
    return project.built_for;
  }
  return "Público ainda não consolidado";
}

export function ConnectionDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [chatDraft, setChatDraft] = useState("");
  const [filters, setFilters] = useState<MemoryFilters>({
    targetMessageCount: 140,
    maxLookbackHours: 72,
    detailMode: "balanced",
  });
  const [preview, setPreview] = useState<MemoryAnalysisPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>({
    mode: "idle",
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

  const latestSnapshot = snapshots[0] ?? null;

  const statusLabel = useMemo(() => {
    if (!status) {
      return "Pronto para iniciar";
    }
    return status.connected ? "Conectado ao WhatsApp" : formatState(status.state);
  }, [status]);

  const currentSteps = useMemo(() => getStepsForMode(agentState.mode), [agentState.mode]);

  const insightMetrics = useMemo(() => getSignalMetrics(latestSnapshot), [latestSnapshot]);

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

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void refreshPreview();
    }, 180);

    return () => window.clearTimeout(timeoutId);
  }, [filters, isHydrating, memory?.last_analyzed_at]);

  async function hydrateDashboard(mode: "initial" | "manual" = "initial"): Promise<void> {
    if (mode === "manual") {
      setIsRefreshing(true);
    } else {
      setIsHydrating(true);
    }

    const [statusResult, chatResult, snapshotsResult] = await Promise.allSettled([
      getObserverStatus(false),
      getChatSession(),
      getMemorySnapshots(6),
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

    if (snapshotsResult.status === "fulfilled") {
      setSnapshots(snapshotsResult.value);
    }

    if (mode === "manual") {
      setIsRefreshing(false);
    } else {
      setIsHydrating(false);
    }
  }

  async function refreshPreview(): Promise<void> {
    setIsPreviewLoading(true);
    try {
      const nextPreview = await previewMemoryAnalysis({
        target_message_count: filters.targetMessageCount,
        max_lookback_hours: filters.maxLookbackHours,
        detail_mode: filters.detailMode,
      });
      setPreview(nextPreview);
      setPreviewError(null);
    } catch (error) {
      setPreviewError(getErrorMessage(error));
    } finally {
      setIsPreviewLoading(false);
    }
  }

  function pushAgentLog(tone: LogTone, message: string): void {
    setAgentLogs((previous) => [makeLog(tone, message), ...previous].slice(0, 28));
  }

  function startAgentRun(mode: Exclude<AgentMode, "idle">): void {
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
        ? "Nova leitura iniciada. O agente vai consolidar mensagens diretas, memória anterior, projetos e chat."
        : "Refinamento iniciado. O agente vai limpar a memória já salva sem reprocessar tudo do zero.",
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

  function finishAgentRunSuccess(mode: Exclude<AgentMode, "idle">, message: string): void {
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

  function finishAgentRunError(mode: Exclude<AgentMode, "idle">, message: string): void {
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

  async function runMemoryJob(mode: Exclude<AgentMode, "idle">): Promise<void> {
    setMemoryError(null);
    startAgentRun(mode);

    try {
      if (mode === "analyze") {
        const response = await analyzeMemoryWithFilters({
          target_message_count: filters.targetMessageCount,
          max_lookback_hours: filters.maxLookbackHours,
          detail_mode: filters.detailMode,
        });
        setMemory(response.current);
        setProjects(response.projects);
        setSnapshots((previous) => [response.snapshot, ...previous.filter((snapshot) => snapshot.id !== response.snapshot.id)].slice(0, 6));
        finishAgentRunSuccess("analyze", "Leitura concluída. Perfil, sinais do dono e projetos foram atualizados.");
      } else {
        const response = await refineMemory();
        setMemory(response.current);
        setProjects(response.projects);
        finishAgentRunSuccess("refine", "Refinamento concluído. O perfil consolidado ficou mais limpo.");
      }

      await refreshPreview();
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
          <p>Menos ruído, mais contexto útil sobre o dono, seus projetos, sua rotina e o ganho de cada nova leitura.</p>
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
            <span className="sidebar-label">Score da próxima leitura</span>
            <strong>{preview ? `${preview.recommendation_score}/100` : "Carregando"}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="sidebar-label">Projetos ativos</span>
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
              <p>Buscando status do observador, perfil atual, snapshots, projetos e histórico do chat.</p>
            </div>
          </section>
        ) : (
          <>
            {activeTab === "overview" ? (
              <OverviewTab
                memory={memory}
                latestSnapshot={latestSnapshot}
                projects={projects}
                preview={preview}
                status={status}
                statusLabel={statusLabel}
                connectionError={connectionError}
                memoryError={memoryError}
                previewError={previewError}
                insightMetrics={insightMetrics}
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
                latestSnapshot={latestSnapshot}
                preview={preview}
                previewError={previewError}
                previewLoading={isPreviewLoading}
                memoryError={memoryError}
                agentState={agentState}
                filters={filters}
                onTargetChange={(targetMessageCount) => setFilters((previous) => ({ ...previous, targetMessageCount }))}
                onLookbackChange={(maxLookbackHours) => setFilters((previous) => ({ ...previous, maxLookbackHours }))}
                onDetailChange={(detailMode) => setFilters((previous) => ({ ...previous, detailMode }))}
                onAnalyze={() => void runMemoryJob("analyze")}
                onRefine={() => void runMemoryJob("refine")}
              />
            ) : null}

            {activeTab === "projects" ? (
              <ProjectsTab
                projects={projects}
                latestSnapshot={latestSnapshot}
              />
            ) : null}

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
      return "Planejamento e treinamento da memória";
    case "projects":
      return "Projetos, entregas e público alvo";
    case "chat":
      return "Chat personalizado com contexto do dono";
    case "activity":
      return "Atividade do agente de memória";
  }
}

function OverviewTab({
  memory,
  latestSnapshot,
  projects,
  preview,
  status,
  statusLabel,
  connectionError,
  memoryError,
  previewError,
  insightMetrics,
  onGoToObserver,
  onGoToMemory,
  onGoToChat,
}: {
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projects: ProjectMemory[];
  preview: MemoryAnalysisPreview | null;
  status: ObserverStatus | null;
  statusLabel: string;
  connectionError: string | null;
  memoryError: string | null;
  previewError: string | null;
  insightMetrics: InsightMetric[];
  onGoToObserver: () => void;
  onGoToMemory: () => void;
  onGoToChat: () => void;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-hero">
        <span className="section-kicker">Perfil vivo</span>
        <h3>O painel agora mostra não só o que a IA sabe, mas também se vale a pena aprender mais agora.</h3>
        <p>
          O observador alimenta o banco com contatos diretos, o planejador estima custo e ganho da próxima leitura
          e o perfil consolidado foca em comportamento, rotina e projetos do dono.
        </p>
        <div className="hero-actions">
          <button className="primary-button" onClick={onGoToMemory} type="button">
            Abrir planejador
          </button>
          <button className="ghost-button" onClick={onGoToObserver} type="button">
            Ver conexão
          </button>
          <button className="ghost-button" onClick={onGoToChat} type="button">
            Conversar com a IA
          </button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="Estado do observador" value={statusLabel} />
        <StatCard label="Número conectado" value={status?.owner_number ?? "Aguardando leitura"} />
        <StatCard label="Score da leitura" value={preview ? `${preview.recommendation_score}/100` : "Sem preview"} />
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
          <span className="section-kicker">Leitura recomendada</span>
          <span className="meta-text">{preview?.recommendation_label ?? "Sem cálculo ainda"}</span>
        </div>
        <div className="recommendation-gauge">
          <div
            className={`recommendation-gauge-fill recommendation-gauge-${getPreviewTone(preview?.recommendation_score ?? 0)}`}
            style={{ width: `${preview?.recommendation_score ?? 0}%` }}
          />
        </div>
        <div className="recommendation-copy">
          <strong>{preview ? `${preview.recommendation_score}/100` : "Sem score"}</strong>
          <p>{preview?.recommendation_summary ?? "Escolha uma configuração na aba Memória para calcular o ganho da próxima leitura."}</p>
        </div>
      </section>

      <section className="stage-card stage-card-span">
        <div className="card-head">
          <span className="section-kicker">Sinais recentes sobre o dono</span>
          <span className="meta-text">
            {latestSnapshot ? `Baseado na leitura de ${formatDateTime(latestSnapshot.created_at)}` : "Sem snapshot ainda"}
          </span>
        </div>
        <div className="insight-bars">
          {insightMetrics.map((metric) => (
            <InsightBar key={metric.label} metric={metric} maxValue={Math.max(...insightMetrics.map((item) => item.value), 1)} />
          ))}
        </div>
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Áreas mais fortes</span>
          <span className="meta-text">{projects.length} projetos em contexto</span>
        </div>
        {latestSnapshot ? (
          <div className="signal-columns">
            <SignalColumn title="Aprendizados" items={latestSnapshot.key_learnings} emptyLabel="Sem aprendizados consolidados ainda." />
            <SignalColumn title="Rotina" items={latestSnapshot.routine_signals} emptyLabel="Sem sinais de rotina ainda." />
            <SignalColumn title="Preferências" items={latestSnapshot.preferences} emptyLabel="Sem preferências fortes ainda." />
          </div>
        ) : (
          <div className="empty-state empty-state-soft">
            <strong>Sem leitura recente</strong>
            <p>Assim que o DeepSeek consolidar uma nova janela, esse bloco passa a destacar sinais mais úteis sobre o dono.</p>
          </div>
        )}
      </section>

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Pontos ainda frágeis</span>
          <span className="meta-text">Lacunas que orientam a próxima leitura</span>
        </div>
        <SignalColumn title="Lacunas abertas" items={latestSnapshot?.open_questions ?? []} emptyLabel="Nenhuma lacuna relevante por enquanto." />
      </section>

      {connectionError ? <InlineError title="Falha na conexão" message={connectionError} /> : null}
      {memoryError ? <InlineError title="Falha na memória" message={memoryError} /> : null}
      {previewError ? <InlineError title="Falha no preview" message={previewError} /> : null}
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
  latestSnapshot,
  preview,
  previewError,
  previewLoading,
  memoryError,
  agentState,
  filters,
  onTargetChange,
  onLookbackChange,
  onDetailChange,
  onAnalyze,
  onRefine,
}: {
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  preview: MemoryAnalysisPreview | null;
  previewError: string | null;
  previewLoading: boolean;
  memoryError: string | null;
  agentState: AgentState;
  filters: MemoryFilters;
  onTargetChange: (value: number) => void;
  onLookbackChange: (value: number) => void;
  onDetailChange: (value: MemoryAnalysisDetailMode) => void;
  onAnalyze: () => void;
  onRefine: () => void;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-span">
        <div className="card-head">
          <div>
            <span className="section-kicker">Planejador de leitura</span>
            <h3 className="section-title">Escolha o volume, o alcance e a profundidade antes de gastar tokens.</h3>
          </div>
          <span className="meta-text">Preview barato, sem mandar o conteúdo bruto para o modelo leve</span>
        </div>

        <div className="planner-grid">
          <div className="planner-block">
            <span className="planner-label">Mensagens alvo</span>
            <div className="preset-row">
              {MESSAGE_TARGET_PRESETS.map((count) => (
                <button
                  key={count}
                  className={`chip-button${filters.targetMessageCount === count ? " chip-button-active" : ""}`}
                  onClick={() => onTargetChange(count)}
                  type="button"
                >
                  {count}
                </button>
              ))}
            </div>
          </div>

          <div className="planner-block">
            <span className="planner-label">Alcance máximo</span>
            <div className="preset-row">
              {LOOKBACK_PRESETS.map((hours) => (
                <button
                  key={hours}
                  className={`chip-button${filters.maxLookbackHours === hours ? " chip-button-active" : ""}`}
                  onClick={() => onLookbackChange(hours)}
                  type="button"
                >
                  {formatHoursLabel(hours)}
                </button>
              ))}
            </div>
          </div>

          <div className="planner-block">
            <span className="planner-label">Profundidade</span>
            <div className="detail-option-row">
              {DETAIL_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  className={`detail-option${filters.detailMode === option.value ? " detail-option-active" : ""}`}
                  onClick={() => onDetailChange(option.value)}
                  type="button"
                >
                  <strong>{option.label}</strong>
                  <span>{option.description}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="stats-grid planner-stats-grid">
          <StatCard label="Disponíveis na janela" value={preview ? String(preview.available_message_count) : "..." } />
          <StatCard label="Entram na leitura" value={preview ? String(preview.selected_message_count) : "..."} />
          <StatCard label="Novas desde a última análise" value={preview ? String(preview.new_message_count) : "..."} />
          <StatCard label="Já substituídas pela retenção" value={preview ? String(preview.replaced_message_count) : "..."} />
          <StatCard label="Tokens de entrada" value={preview ? formatTokenCount(preview.estimated_input_tokens) : "..."} />
          <StatCard label="Tokens totais estimados" value={preview ? formatTokenCount(preview.estimated_total_tokens) : "..."} />
        </div>

        <div className="planner-bottom">
          <div className="recommendation-panel">
            <div className="card-head">
              <span className="section-kicker">Compensa analisar agora?</span>
              <span className="meta-text">{preview?.recommendation_label ?? "Aguardando cálculo"}</span>
            </div>
            <div className="recommendation-gauge recommendation-gauge-large">
              <div
                className={`recommendation-gauge-fill recommendation-gauge-${getPreviewTone(preview?.recommendation_score ?? 0)}`}
                style={{ width: `${preview?.recommendation_score ?? 0}%` }}
              />
            </div>
            <div className="recommendation-copy">
              <strong>{preview ? `${preview.recommendation_score}/100` : "Sem score"}</strong>
              <p>
                {previewLoading
                  ? "Calculando ganho esperado da próxima leitura..."
                  : preview?.recommendation_summary ??
                    "Defina a configuração para ver o ganho estimado da próxima análise."}
              </p>
            </div>
            <div className="retention-strip">
              <span>{preview ? `${preview.new_message_count} novas no banco` : "..."}</span>
              <span>{preview ? `${preview.replaced_message_count} já substituídas` : "..."}</span>
              <span>{preview ? `${preview.retained_message_count}/${preview.retention_limit} retidas agora` : "..."}</span>
            </div>
          </div>

          <div className="memory-actions-panel">
            <button className="primary-button" onClick={onAnalyze} disabled={agentState.running || !preview?.selected_message_count} type="button">
              {agentState.running && agentState.mode === "analyze" ? "Lendo..." : "Executar leitura"}
            </button>
            <button className="ghost-button" onClick={onRefine} disabled={agentState.running} type="button">
              {agentState.running && agentState.mode === "refine" ? "Refinando..." : "Refinar memória salva"}
            </button>
            <div className="action-bar-caption">
              <div className="recommendation-gauge recommendation-gauge-inline">
                <div
                  className={`recommendation-gauge-fill recommendation-gauge-${getPreviewTone(preview?.recommendation_score ?? 0)}`}
                  style={{ width: `${preview?.recommendation_score ?? 0}%` }}
                />
              </div>
              <p>
                {preview
                  ? `${preview.recommendation_score}/100 de ganho esperado com esta configuração.`
                  : "O preview mostra o custo estimado e o quanto a IA deve aprender com a próxima leitura."}
              </p>
            </div>
          </div>
        </div>

        {previewError ? <InlineError title="Falha no preview" message={previewError} /> : null}
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

      <section className="stage-card">
        <div className="card-head">
          <span className="section-kicker">Última leitura</span>
          <span className="meta-text">{latestSnapshot ? formatDateTime(latestSnapshot.created_at) : "Sem snapshot"}</span>
        </div>
        {latestSnapshot ? (
          <>
            <p className="summary-copy">{latestSnapshot.window_summary}</p>
            <div className="signal-columns">
              <SignalColumn title="Aprendizados" items={latestSnapshot.key_learnings} emptyLabel="Sem aprendizados." />
              <SignalColumn title="Rotina" items={latestSnapshot.routine_signals} emptyLabel="Sem sinais de rotina." />
              <SignalColumn title="Preferências" items={latestSnapshot.preferences} emptyLabel="Sem preferências." />
            </div>
          </>
        ) : (
          <div className="empty-state empty-state-soft">
            <strong>Sem snapshot recente</strong>
            <p>Depois da próxima leitura, esta área mostra o resumo da janela mais recente e os sinais extraídos.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function ProjectsTab({
  projects,
  latestSnapshot,
}: {
  projects: ProjectMemory[];
  latestSnapshot: MemorySnapshot | null;
}) {
  return (
    <div className="content-grid">
      <section className="stage-card stage-card-span">
        <div className="card-head">
          <div>
            <span className="section-kicker">Projetos e frentes</span>
            <h3 className="section-title">Agora cada projeto destaca o que o dono está construindo e para quem.</h3>
          </div>
          <span className="meta-text">{projects.length} itens em contexto</span>
        </div>

        {projects.length === 0 ? (
          <div className="empty-state">
            <strong>Nenhum projeto consolidado ainda</strong>
            <p>Assim que a memória ficar mais rica, o DeepSeek passa a destacar frentes recorrentes, entregas e público alvo.</p>
          </div>
        ) : (
          <>
            <div className="project-focus-grid">
              {projects.slice(0, 4).map((project) => (
                <article key={`${project.id}-focus`} className="focus-card">
                  <span>{project.project_name}</span>
                  <strong>{getProjectStrength(project)}%</strong>
                  <div className="focus-bar">
                    <div className="focus-bar-fill" style={{ width: `${getProjectStrength(project)}%` }} />
                  </div>
                  <p>{project.what_is_being_built || project.summary}</p>
                </article>
              ))}
            </div>

            <div className="project-grid">
              {projects.map((project) => (
                <article key={project.id} className="project-card project-card-rich">
                  <div className="project-card-head">
                    <strong>{project.project_name}</strong>
                    <span>{project.last_seen_at ? formatShortDateTime(project.last_seen_at) : "Sem data"}</span>
                  </div>

                  <div className="project-meta-grid">
                    <ProjectMeta label="O que está sendo desenvolvido" value={project.what_is_being_built || project.summary} />
                    <ProjectMeta label="Para quem" value={getAudienceLabel(project)} />
                    <ProjectMeta label="Status" value={project.status || "Sem status consolidado"} />
                  </div>

                  <p>{project.summary}</p>

                  {project.next_steps.length > 0 ? (
                    <>
                      <span className="project-subtitle">Próximos passos</span>
                      <div className="tag-list">
                        {project.next_steps.slice(0, 5).map((step, index) => (
                          <span key={`${project.id}-step-${index}`} className="tag-chip">
                            {step}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : null}

                  {project.evidence.length > 0 ? (
                    <>
                      <span className="project-subtitle">Evidências recentes</span>
                      <div className="tag-list">
                        {project.evidence.slice(0, 4).map((evidence, index) => (
                          <span key={`${project.id}-evidence-${index}`} className="tag-chip tag-chip-soft">
                            {evidence}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : null}
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="stage-card stage-card-span">
        <div className="card-head">
          <span className="section-kicker">Pistas recentes da leitura</span>
          <span className="meta-text">
            {latestSnapshot ? `Baseado em ${formatDateTime(latestSnapshot.created_at)}` : "Sem snapshot recente"}
          </span>
        </div>
        <SignalColumn
          title="Projetos e relações da última leitura"
          items={latestSnapshot?.people_and_relationships ?? []}
          emptyLabel="A última leitura ainda não consolidou relações e projetos suficientes."
        />
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
          <span className="meta-text">O histórico daqui também entra nas próximas leituras da memória</span>
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
              placeholder="Ex.: O que você já entendeu sobre minha rotina, meus projetos e meus critérios de decisão?"
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

function InsightBar({ metric, maxValue }: { metric: InsightMetric; maxValue: number }) {
  const width = `${Math.max(12, Math.round((metric.value / Math.max(maxValue, 1)) * 100))}%`;
  return (
    <article className="insight-bar-card">
      <div className="insight-bar-head">
        <strong>{metric.label}</strong>
        <span>{metric.value}</span>
      </div>
      <div className="insight-bar-track">
        <div className="insight-bar-fill" style={{ width }} />
      </div>
      <p>{metric.description}</p>
    </article>
  );
}

function SignalColumn({
  title,
  items,
  emptyLabel,
}: {
  title: string;
  items: string[];
  emptyLabel: string;
}) {
  return (
    <div className="signal-column">
      <strong>{title}</strong>
      {items.length === 0 ? (
        <p>{emptyLabel}</p>
      ) : (
        <ul className="signal-list">
          {items.slice(0, 5).map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="project-meta-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
