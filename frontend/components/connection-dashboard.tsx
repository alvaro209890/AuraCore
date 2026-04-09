"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Bot,
  Brain,
  CheckCircle2,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Eye,
  FileText,
  FolderGit2,
  Fingerprint,
  GitBranch,
  Menu,
  MessageSquare,
  MoreVertical,
  Paperclip,
  Play,
  RefreshCw,
  Send,
  Server,
  Settings,
  Sparkles,
  Smartphone,
  Terminal,
  User,
  XCircle,
  Zap,
} from "lucide-react";

import {
  analyzeMemoryWithFilters,
  connectObserver,
  getChatSession,
  getMemorySnapshots,
  getObserverStatus,
  previewMemoryAnalysis,
  refreshObserverMessages,
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
type AgentIntent = "first_analysis" | "improve_memory" | "refine_saved";
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
  intent: AgentIntent | null;
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
  color: "emerald" | "amber" | "indigo" | "zinc";
};

type NavItem = {
  id: TabId;
  label: string;
  icon: LucideIcon;
};

const POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 25000;
const MESSAGE_TARGET_PRESETS = [80, 140, 200, 250];
const LOOKBACK_PRESETS = [24, 72, 168];
const DETAIL_OPTIONS: Array<{
  value: MemoryAnalysisDetailMode;
  label: string;
  description: string;
  badge: string;
}> = [
  { value: "light", label: "Rápida", description: "Leitura leve para checar mudança recente sem empurrar muito contexto.", badge: "~18k chars" },
  { value: "balanced", label: "Padrão", description: "Equilíbrio entre custo, cobertura do histórico recente e qualidade do retrato.", badge: "~36k chars" },
  { value: "deep", label: "Profunda", description: "Usa o teto atual da stack quando houve muita novidade ou atraso de consolidação.", badge: "~60k chars" },
];

const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Visão Geral", icon: Brain },
  { id: "observer", label: "Observador", icon: Eye },
  { id: "memory", label: "Memória", icon: Database },
  { id: "projects", label: "Projetos", icon: FolderGit2 },
  { id: "chat", label: "Chat Pessoal", icon: MessageSquare },
  { id: "activity", label: "Atividade", icon: Activity },
];

const IDLE_AGENT_STATUS = "Nenhuma atualização em andamento.";

const ANALYZE_STEPS: AgentStep[] = [
  {
    threshold: 8,
    label: "Coletando sinais recentes",
    detail: "Lendo somente conversas diretas úteis e ignorando grupos, broadcast e lixo sem texto.",
  },
  {
    threshold: 22,
    label: "Normalizando o dono",
    detail: "Agrupando linguagem, rotina, decisões, tensões, contexto profissional e prioridades.",
  },
  {
    threshold: 38,
    label: "Cruzando memória estável",
    detail: "Comparando a janela nova com snapshots antigos, projetos e contexto já consolidado.",
  },
  {
    threshold: 56,
    label: "Lendo o chat pessoal",
    detail: "Usando o que o dono já revelou para reforçar objetivos, preocupações e preferências.",
  },
  {
    threshold: 78,
    label: "Consolidando com DeepSeek",
    detail: "Transformando sinais dispersos em um perfil mais útil e mais fiel ao dono.",
  },
  {
    threshold: 94,
    label: "Salvando no Supabase",
    detail: "Persistindo resumo, projetos, contadores de retenção e novo snapshot para futuras leituras.",
  },
];

const REFINE_STEPS: AgentStep[] = [
  {
    threshold: 10,
    label: "Lendo memória consolidada",
    detail: "Partindo do que já foi salvo para remover ruído e reduzir suposições fracas.",
  },
  {
    threshold: 34,
    label: "Revisando projetos e fricções",
    detail: "Reforçando o que é recorrente e enfraquecendo o que não tem sustentação real.",
  },
  {
    threshold: 66,
    label: "Refinando com DeepSeek",
    detail: "Melhorando linguagem, prioridades e retrato comportamental do dono.",
  },
  {
    threshold: 94,
    label: "Aplicando refinamento",
    detail: "Atualizando memória atual e frentes principais sem reprocessar tudo do zero.",
  },
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

function formatUsd(value: number): string {
  const digits = value < 0.01 ? 4 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function hasEstablishedMemory(memory: MemoryCurrent | null, latestSnapshot: MemorySnapshot | null): boolean {
  return Boolean(memory?.last_analyzed_at || latestSnapshot?.id);
}

function getIntentTitle(intent: AgentIntent | null): string {
  switch (intent) {
    case "first_analysis":
      return "Fazer Primeira Análise";
    case "improve_memory":
      return "Ler Novas Mensagens e Melhorar Memória";
    case "refine_saved":
      return "Refinar Memória Já Salva";
    default:
      return "Aguardando nova ação";
  }
}

function buildActivityThinking(args: {
  preview: MemoryAnalysisPreview | null;
  intent: AgentIntent | null;
  hasMemory: boolean;
  projectsCount: number;
  snapshotsCount: number;
}): string[] {
  const { preview, intent, hasMemory, projectsCount, snapshotsCount } = args;
  const resolvedIntent = intent ?? (hasMemory ? "improve_memory" : "first_analysis");
  const lines: string[] = [];

  if (resolvedIntent === "first_analysis") {
    lines.push(
      "Esta rota cria a primeira base consolidada do dono; ainda nao existe memoria forte para cruzar, entao o foco e montar o primeiro retrato util.",
    );
  } else if (resolvedIntent === "improve_memory") {
    lines.push(
      "Esta rota compara mensagens diretas recentes com a memoria ja consolidada para reforcar o que mudou sem perder continuidade do perfil.",
    );
  } else {
    lines.push(
      "Esta rota nao reler o WhatsApp; ela limpa e reorganiza somente o que ja esta salvo no Supabase para reduzir ruido.",
    );
  }

  if (preview) {
    lines.push(
      `A leitura atual consegue encaixar ${preview.selected_message_count} de ${preview.available_message_count} mensagens diretas na janela, respeitando o teto operacional de ${preview.stack_max_message_capacity} mensagens desta stack.`,
    );
    lines.push(
      `O pacote enviado ao ${preview.deepseek_model} usa cerca de ${formatTokenCount(preview.estimated_input_tokens)} tokens de entrada e reserva ${formatTokenCount(preview.request_output_reserve_tokens)} de saida; o custo previsto fica em ${formatUsd(preview.estimated_cost_total_floor_usd)} a ${formatUsd(preview.estimated_cost_total_ceiling_usd)}.`,
    );
    lines.push(
      `Hoje existem ${preview.new_message_count} mensagens novas e ${preview.replaced_message_count} ja ficaram para tras pela retencao; isso ajuda a explicar o score atual de ${preview.recommendation_score}/100.`,
    );
  } else {
    lines.push("Sem preview carregado, o painel mostra apenas o fluxo do agente e aguarda um novo calculo da leitura.");
  }

  if (hasMemory) {
    lines.push(
      `O agente ainda cruza a janela nova com ${snapshotsCount} snapshots, ${projectsCount} projetos consolidados e o chat pessoal salvo para manter continuidade entre leituras.`,
    );
  } else {
    lines.push("Como ainda nao existe base consolidada, o modelo usa principalmente a janela atual de mensagens diretas para montar a primeira memoria util.");
  }

  return lines;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Não foi possível concluir a operação.";
}

function getProgressIncrement(progress: number): number {
  if (progress < 18) {
    return 7;
  }
  if (progress < 38) {
    return 5;
  }
  if (progress < 60) {
    return 4;
  }
  if (progress < 80) {
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

function getPreviewTone(score: number): "emerald" | "amber" | "indigo" | "rose" {
  if (score >= 80) {
    return "emerald";
  }
  if (score >= 60) {
    return "indigo";
  }
  if (score >= 38) {
    return "amber";
  }
  return "rose";
}

function getSignalMetrics(snapshot: MemorySnapshot | null): InsightMetric[] {
  return [
    {
      label: "Trabalho & Projetos",
      value: (snapshot?.key_learnings.length ?? 0) + Math.min(snapshot?.people_and_relationships.length ?? 0, 2),
      description: "Aprendizados de entregas, decisões e frentes correntes.",
      color: "emerald",
    },
    {
      label: "Rotina & Ritmo",
      value: snapshot?.routine_signals.length ?? 0,
      description: "Padrões de horário, intensidade e sequência operacional.",
      color: "amber",
    },
    {
      label: "Critérios & Preferências",
      value: snapshot?.preferences.length ?? 0,
      description: "Jeito de escolher, recusar, priorizar e decidir.",
      color: "indigo",
    },
    {
      label: "Lacunas Restantes",
      value: snapshot?.open_questions.length ?? 0,
      description: "Pontos que ainda precisam de mais sinal para a IA ficar melhor.",
      color: "zinc",
    },
  ];
}

function getProjectStrength(project: ProjectMemory): number {
  const raw = 30 + (project.next_steps.length * 10) + (project.evidence.length * 7) + (project.status ? 8 : 0);
  return Math.max(24, Math.min(100, raw));
}

function getAudienceLabel(project: ProjectMemory): string {
  if (project.built_for.trim()) {
    return project.built_for;
  }
  return "Público ainda não consolidado";
}

function getSignalColorClass(color: InsightMetric["color"]): string {
  switch (color) {
    case "emerald":
      return "bar-emerald";
    case "amber":
      return "bar-amber";
    case "indigo":
      return "bar-indigo";
    case "zinc":
      return "bar-zinc";
  }
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={`neo-card ${className}`}>{children}</section>;
}

function SectionTitle({
  title,
  icon: Icon,
  action,
}: {
  title: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-head">
      <div className="section-head-copy">
        {Icon ? (
          <span className="section-icon-shell">
            <Icon size={16} />
          </span>
        ) : null}
        <h3>{title}</h3>
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

function ProgressBar({
  value,
  max = 100,
  tone = "indigo",
  label,
}: {
  value: number;
  max?: number;
  tone?: "indigo" | "emerald" | "amber" | "rose" | "zinc";
  label?: string;
}) {
  const width = `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
  return (
    <div className="mini-progress-wrap">
      {label ? (
        <div className="mini-progress-head">
          <span>{label}</span>
          <span>{Math.round((value / max) * 100)}%</span>
        </div>
      ) : null}
      <div className="mini-progress-track">
        <div className={`mini-progress-fill tone-${tone}`} style={{ width }} />
      </div>
    </div>
  );
}

function SegmentedControl({
  options,
  selected,
  onChange,
}: {
  options: string[];
  selected: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="segmented-control">
      {options.map((option) => (
        <button
          key={option}
          onClick={() => onChange(option)}
          className={`segment-button${selected === option ? " segment-button-active" : ""}`}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export function ConnectionDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [chatDraft, setChatDraft] = useState("");
  const [filters, setFilters] = useState<MemoryFilters>({
    targetMessageCount: 200,
    maxLookbackHours: 72,
    detailMode: "balanced",
  });
  const [preview, setPreview] = useState<MemoryAnalysisPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [messageRefreshError, setMessageRefreshError] = useState<string | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingMessages, setIsRefreshingMessages] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>({
    mode: "idle",
    intent: null,
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
  const messageRefreshTimerRef = useRef<number | null>(null);

  const latestSnapshot = snapshots[0] ?? null;
  const memoryIsEstablished = hasEstablishedMemory(memory, latestSnapshot);

  const statusLabel = useMemo(() => {
    if (!status) {
      return "Pronto para iniciar";
    }
    return status.connected ? "Online" : formatState(status.state);
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
      if (messageRefreshTimerRef.current) {
        window.clearTimeout(messageRefreshTimerRef.current);
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

  function startAgentRun(intent: AgentIntent): void {
    const mode: Exclude<AgentMode, "idle"> = intent === "refine_saved" ? "refine" : "analyze";
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }

    agentStepIndexRef.current = 0;
    setActiveTab("activity");
    setAgentState({
      mode,
      intent,
      running: true,
      progress: 4,
      status: getRunningStatus(mode, 4),
      error: null,
      completedAt: null,
    });

    pushAgentLog(
      "info",
      intent === "first_analysis"
        ? "Primeira analise iniciada. O agente vai criar a base inicial do dono usando mensagens diretas recentes."
        : intent === "improve_memory"
          ? "Atualizacao incremental iniciada. O agente vai combinar mensagens novas com snapshots, projetos e chat pessoal."
          : "Refinamento iniciado. O agente vai limpar a memoria consolidada e reforcar padroes mais estaveis.",
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

  function finishAgentRunSuccess(intent: AgentIntent, message: string): void {
    const mode: Exclude<AgentMode, "idle"> = intent === "refine_saved" ? "refine" : "analyze";
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      intent,
      running: false,
      progress: 100,
      status: message,
      error: null,
      completedAt: new Date().toISOString(),
    });
    pushAgentLog("success", message);
  }

  function finishAgentRunError(intent: AgentIntent, message: string): void {
    const mode: Exclude<AgentMode, "idle"> = intent === "refine_saved" ? "refine" : "analyze";
    if (agentTimerRef.current) {
      window.clearInterval(agentTimerRef.current);
    }
    setAgentState({
      mode,
      intent,
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

  async function requestMessageRefresh(): Promise<void> {
    setIsRefreshingMessages(true);
    setMessageRefreshError(null);

    try {
      const response = await refreshObserverMessages();
      setStatus((previous) => mergeStatus(previous, response.status));
      setPollingEnabled(!response.status.connected);
      setViewState(response.status.connected ? "connected" : "waiting");
      pushAgentLog("info", response.message);

      if (messageRefreshTimerRef.current) {
        window.clearTimeout(messageRefreshTimerRef.current);
      }
      messageRefreshTimerRef.current = window.setTimeout(() => {
        void hydrateDashboard("manual");
        messageRefreshTimerRef.current = null;
      }, 4500);
    } catch (error) {
      const message = getErrorMessage(error);
      setMessageRefreshError(message);
      pushAgentLog("error", `A releitura do WhatsApp falhou: ${message}`);
    } finally {
      setIsRefreshingMessages(false);
    }
  }

  async function pollStatus(): Promise<void> {
    try {
      const shouldRefreshQr = Boolean(status?.qr_code) && (
        !lastQrRefreshAtRef.current ||
        Date.now() - lastQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS
      );

      const nextStatus = shouldRefreshQr ? await connectObserver() : await getObserverStatus(false);

      if (shouldRefreshQr) {
        lastQrRefreshAtRef.current = Date.now();
      }

      setStatus((previous) => mergeStatus(previous, nextStatus));
      setConnectionError(null);

      if (nextStatus.connected) {
        setPollingEnabled(false);
        setViewState("connected");
        pushAgentLog("success", "Observador conectado. As mensagens diretas já podem alimentar a memória.");
        return;
      }

      setViewState("waiting");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(error));
    }
  }

  async function runMemoryJob(intent: AgentIntent): Promise<void> {
    setMemoryError(null);
    startAgentRun(intent);

    try {
      if (intent !== "refine_saved") {
        const response = await analyzeMemoryWithFilters({
          target_message_count: filters.targetMessageCount,
          max_lookback_hours: filters.maxLookbackHours,
          detail_mode: filters.detailMode,
        });
        setMemory(response.current);
        setProjects(response.projects);
        setSnapshots((previous) => [response.snapshot, ...previous.filter((snapshot) => snapshot.id !== response.snapshot.id)].slice(0, 6));
        finishAgentRunSuccess(
          intent,
          intent === "first_analysis"
            ? "Primeira analise concluida. A base inicial do dono foi criada."
            : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado.",
        );
      } else {
        const response = await refineMemory();
        setMemory(response.current);
        setProjects(response.projects);
        finishAgentRunSuccess("refine_saved", "Refinamento concluido. A memoria consolidada ficou mais precisa.");
      }

      await refreshPreview();
    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError(intent, message);
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

  const currentNavTitle = NAV_ITEMS.find((item) => item.id === activeTab)?.label ?? "AuraCore";
  const previewTone = getPreviewTone(preview?.recommendation_score ?? 0);

  return (
    <div className="ac-layout-shell">
      {sidebarOpen ? (
        <button
          className="ac-sidebar-overlay"
          type="button"
          aria-label="Fechar menu"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <aside className={`ac-sidebar${sidebarOpen ? " ac-sidebar-open" : ""}`}>
        <div className="ac-sidebar-brand">
          <div className="ac-brand-mark">
            <Brain size={18} />
          </div>
          <div>
            <h1>AuraCore</h1>
            <p>Segundo Cérebro</p>
          </div>
        </div>

        <nav className="ac-sidebar-nav" aria-label="Navegação principal">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                className={`ac-nav-item${active ? " ac-nav-item-active" : ""}`}
                onClick={() => {
                  setActiveTab(item.id);
                  setSidebarOpen(false);
                }}
                type="button"
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="ac-sidebar-footer">
          <div className="ac-quick-status">
            <span>Observador</span>
            <div className={`ac-status-badge status-${viewState}`}>
              <span className="status-dot" />
              {statusLabel}
            </div>
          </div>
          <div className="ac-quick-status">
            <span>Mensagens retidas</span>
            <strong>{preview ? `${preview.retained_message_count}/${preview.retention_limit}` : "..."}</strong>
          </div>
          <div className="ac-quick-status">
            <span>Tokens previstos</span>
            <strong>{preview ? formatTokenCount(preview.estimated_total_tokens) : "..."}</strong>
          </div>
        </div>
      </aside>

      <main className="ac-main-shell">
        <header className="ac-topbar">
          <div className="ac-topbar-left">
            <button
              className="ac-icon-button ac-mobile-menu"
              onClick={() => setSidebarOpen(true)}
              type="button"
              aria-label="Abrir menu"
            >
              <Menu size={18} />
            </button>
            <div>
              <span className="ac-topbar-kicker">Painel principal</span>
              <h2>{currentNavTitle}</h2>
            </div>
          </div>

          <div className="ac-topbar-actions">
            <button className="ac-icon-button" onClick={() => void hydrateDashboard("manual")} disabled={isRefreshing} type="button">
              <RefreshCw size={16} className={isRefreshing ? "spin" : ""} />
            </button>
            <button
              className="ac-primary-button"
              onClick={() => void runMemoryJob(memoryIsEstablished ? "improve_memory" : "first_analysis")}
              disabled={agentState.running}
              type="button"
            >
              <Play size={15} />
              {agentState.running && agentState.mode === "analyze"
                ? "Lendo..."
                : memoryIsEstablished
                  ? "Melhorar Memória"
                  : "Primeira Análise"}
            </button>
          </div>
        </header>

        <div className="ac-main-scroll">
          {isHydrating ? (
            <Card className="ac-loading-card">
              <SectionTitle title="Carregando AuraCore" icon={RefreshCw} />
              <p>Buscando status do observador, perfil atual, snapshots, projetos e histórico do chat.</p>
            </Card>
          ) : (
            <>
              {activeTab === "overview" ? (
                <OverviewTab
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  projects={projects}
                  preview={preview}
                  previewTone={previewTone}
                  status={status}
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
                  messageRefreshError={messageRefreshError}
                  agentState={agentState}
                  filters={filters}
                  isRefreshingMessages={isRefreshingMessages}
                  onTargetChange={(targetMessageCount) => setFilters((previous) => ({ ...previous, targetMessageCount }))}
                  onLookbackChange={(maxLookbackHours) => setFilters((previous) => ({ ...previous, maxLookbackHours }))}
                  onDetailChange={(detailMode) => setFilters((previous) => ({ ...previous, detailMode }))}
                  onRefreshMessages={() => void requestMessageRefresh()}
                  onInitialAnalysis={() => void runMemoryJob("first_analysis")}
                  onImproveMemory={() => void runMemoryJob("improve_memory")}
                  onRefineSaved={() => void runMemoryJob("refine_saved")}
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
                  preview={preview}
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  projectsCount={projects.length}
                  snapshotsCount={snapshots.length}
                />
              ) : null}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function OverviewTab({
  memory,
  latestSnapshot,
  projects,
  preview,
  previewTone,
  status,
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
  previewTone: "emerald" | "amber" | "indigo" | "rose";
  status: ObserverStatus | null;
  connectionError: string | null;
  memoryError: string | null;
  previewError: string | null;
  insightMetrics: InsightMetric[];
  onGoToObserver: () => void;
  onGoToMemory: () => void;
  onGoToChat: () => void;
}) {
  return (
    <div className="page-stack">
      <Card className="hero-panel">
        <div className="hero-copy">
          <div className="hero-kicker">
            <Brain size={14} />
            AuraCore Ativo
          </div>
          <h3>Seu cérebro expandido está monitorando sinais, extraindo contexto e reorganizando prioridades em tempo real.</h3>
          <p>
            O observador captura apenas contatos diretos, a memória consolida padrões do dono e o planejador mostra se
            uma nova leitura realmente compensa antes de gastar tokens.
          </p>
        </div>
        <div className="hero-actions">
          <button className="ac-secondary-button" onClick={onGoToObserver} type="button">
            <Eye size={15} />
            Ver Observador
          </button>
          <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
            <Database size={15} />
            Planejar Leitura
          </button>
          <button className="ac-primary-button" onClick={onGoToChat} type="button">
            <MessageSquare size={15} />
            Falar com IA
          </button>
        </div>
      </Card>

      <div className="stats-grid modern-stats-grid">
        <ModernStatCard
          label="Observador"
          value={status?.connected ? "Online" : "Aguardando"}
          meta={status?.connected ? "Operacional" : "Sem sessão ativa"}
          icon={Eye}
          tone="emerald"
        />
        <ModernStatCard
          label="Conexão ativa"
          value={status?.owner_number ?? "Sem número"}
          meta="Dispositivo principal"
          icon={Smartphone}
        />
        <ModernStatCard
          label="Próxima leitura"
          value={preview ? `${preview.recommendation_score}%` : "--"}
          meta={preview?.recommendation_label ?? "Sem cálculo"}
          icon={Zap}
          tone={previewTone}
        />
        <ModernStatCard
          label="Mensagens salvas"
          value={preview ? String(preview.retained_message_count) : "--"}
          meta={preview ? `de ${preview.retention_limit} retidas` : "Aguardando preview"}
          icon={Database}
          tone="indigo"
        />
      </div>

      <div className="overview-grid">
        <div className="overview-main-stack">
          <Card>
            <SectionTitle title="Resumo do Dono (Atual)" icon={Fingerprint} />
            <p className="lead-copy">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Ainda não existe um perfil consolidado. Conecte o observador, deixe sinais suficientes chegarem e execute a primeira leitura."}
            </p>
          </Card>

          <Card>
            <SectionTitle title="Mapeamento Estrutural" icon={Brain} />
            <div className="dual-column-grid">
              <div className="signal-cluster">
                <h4>Áreas Fortes</h4>
                <SignalBlock
                  title="Aprendizados Recentes"
                  lines={latestSnapshot?.key_learnings ?? []}
                  emptyLabel="Sem aprendizados recentes consolidados."
                />
                <SignalBlock
                  title="Rotina Detectada"
                  lines={latestSnapshot?.routine_signals ?? []}
                  emptyLabel="Sem sinais fortes de rotina ainda."
                />
                <SignalBlock
                  title="Preferências Operacionais"
                  lines={latestSnapshot?.preferences ?? []}
                  emptyLabel="Sem preferências consolidadas ainda."
                />
              </div>

              <div className="signal-cluster">
                <h4 className="amber">Pontos Frágeis</h4>
                <SignalBlock
                  title="Lacunas Atuais"
                  lines={latestSnapshot?.open_questions ?? []}
                  emptyLabel="Sem lacunas críticas no momento."
                  subtle
                />
                <SignalBlock
                  title="Projetos em Contexto"
                  lines={projects.slice(0, 3).map((project) => `${project.project_name}: ${project.status || "sem status claro"}`)}
                  emptyLabel="Nenhum projeto relevante foi consolidado ainda."
                  subtle
                />
              </div>
            </div>
          </Card>
        </div>

        <div className="overview-side-stack">
          <Card className="score-card-modern">
            <SectionTitle title="Leitura Recomendada" icon={BarChart3} />
            <div className="score-display-row">
              <span className="score-big">{preview?.recommendation_score ?? 0}</span>
              <span className="score-small">/ 100</span>
            </div>
            <ProgressBar value={preview?.recommendation_score ?? 0} tone={previewTone} />
            <p className="support-copy">
              {preview?.recommendation_summary ??
                "A barra sobe quando o banco acumulou contexto novo suficiente para justificar uma nova leitura do DeepSeek."}
            </p>
          </Card>

          <Card>
            <SectionTitle title="Sinais Recentes" icon={Activity} />
            <div className="progress-bar-stack">
              {insightMetrics.map((metric) => (
                <ProgressBar
                  key={metric.label}
                  value={metric.value}
                  max={Math.max(...insightMetrics.map((item) => item.value), 1)}
                  tone={metric.color === "zinc" ? "amber" : metric.color}
                  label={metric.label}
                />
              ))}
            </div>
          </Card>
        </div>
      </div>

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
    <div className="page-stack observer-page">
      <div className="observer-grid-modern">
        <Card className="observer-qr-card">
          <SectionTitle title="Conexão WhatsApp" icon={Smartphone} />
          <p className="support-copy">Escaneie o QR para conectar o observador. A captura é restrita a contatos diretos úteis.</p>

          <div className="qr-display-shell">
            {status?.qr_code ? (
              <div className="qr-modern-frame">
                <img className="qr-modern-image" src={status.qr_code} alt="QR Code do WhatsApp observador" />
              </div>
            ) : (
              <div className="qr-modern-empty">
                <Smartphone size={28} />
                <strong>QR indisponível</strong>
                <p>
                  {status?.connected
                    ? "A sessão já está conectada. Não é necessário gerar um novo QR."
                    : "Gere uma nova sessão para exibir o QR do observador."}
                </p>
              </div>
            )}
            <div className="qr-expiry-tag">
              <Clock size={12} />
              {status?.connected ? "Sessão ativa" : status?.qr_expires_in_sec ? `Expira em ${status.qr_expires_in_sec}s` : "Sem QR ativo"}
            </div>
          </div>

          <div className="observer-actions">
            <button className="ac-primary-button" onClick={onConnect} disabled={isSubmitting || viewState === "connected"} type="button">
              <RefreshCw size={15} className={isSubmitting ? "spin" : ""} />
              {viewState === "connected" ? "Observador conectado" : isSubmitting ? "Gerando QR..." : "Gerar Novo QR"}
            </button>
          </div>
        </Card>

        <Card className="observer-status-card">
          <SectionTitle title="Status da Instância" icon={Server} />

          <div className="status-line-list">
            <StatusLine label="Gateway" value={status?.gateway_ready ? "Baileys online" : "Indisponível"} tone="emerald" />
            <StatusLine label="Sessão" value={status?.owner_number ?? "Aguardando leitura"} tone="indigo" />
            <StatusLine label="Ingestão" value={status?.ingestion_ready ? "Pronta" : "Pendente"} tone="amber" />
            <StatusLine label="Última sincronização" value={formatDateTime(status?.last_seen_at)} tone="zinc" />
          </div>

          <div className="danger-box">
            <h4>
              <AlertCircle size={16} />
              Zona de perigo
            </h4>
            <p>Resetar a sessão apaga as chaves atuais e força uma nova leitura do QR Code.</p>
            <button className="ac-danger-button" onClick={onReset} disabled={isResetting} type="button">
              <XCircle size={15} />
              {isResetting ? "Resetando..." : "Resetar Sessão Completa"}
            </button>
          </div>
        </Card>
      </div>

      {connectionError ? <InlineError title={`Falha do observador (${statusLabel})`} message={connectionError} /> : null}
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
  messageRefreshError,
  agentState,
  filters,
  isRefreshingMessages,
  onTargetChange,
  onLookbackChange,
  onDetailChange,
  onRefreshMessages,
  onInitialAnalysis,
  onImproveMemory,
  onRefineSaved,
}: {
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  preview: MemoryAnalysisPreview | null;
  previewError: string | null;
  previewLoading: boolean;
  memoryError: string | null;
  messageRefreshError: string | null;
  agentState: AgentState;
  filters: MemoryFilters;
  isRefreshingMessages: boolean;
  onTargetChange: (value: number) => void;
  onLookbackChange: (value: number) => void;
  onDetailChange: (value: MemoryAnalysisDetailMode) => void;
  onRefreshMessages: () => void;
  onInitialAnalysis: () => void;
  onImproveMemory: () => void;
  onRefineSaved: () => void;
}) {
  const gaugeRadius = 92;
  const gaugeCircumference = 2 * Math.PI * gaugeRadius;
  const previewScore = preview?.recommendation_score ?? 0;
  const dashOffset = gaugeCircumference - (gaugeCircumference * previewScore) / 100;
  const previewTone = getPreviewTone(previewScore);
  const memoryReady = hasEstablishedMemory(memory, latestSnapshot);
  const missingFromTarget = preview ? Math.max(0, preview.target_message_count - preview.selected_message_count) : 0;
  const costRangeLabel = preview
    ? `${formatUsd(preview.estimated_cost_total_floor_usd)}-${formatUsd(preview.estimated_cost_total_ceiling_usd)}`
    : "...";
  const modelRangeLabel = preview
    ? `${formatTokenCount(preview.model_message_capacity_floor)}-${formatTokenCount(preview.model_message_capacity_ceiling)} msgs`
    : "...";

  return (
    <div className="page-stack">
      <div className="memory-top-grid">
        <Card className="memory-planner-card">
          <SectionTitle
            title="Planejador Real do Reasoner"
            icon={Cpu}
            action={<span className="micro-badge">{preview?.deepseek_model ?? "deepseek-reasoner"}</span>}
          />

          <p className="memory-deck-copy">
            O planner cruza o transcript real da janela, a memória já salva, o prompt estrutural e a reserva de saída
            do AuraCore para mostrar o que de fato cabe antes de rodar a análise.
          </p>

          <div className="memory-capacity-grid">
            <MemorySignalCard
              label="Cabem agora"
              value={preview ? `${formatTokenCount(preview.selected_message_count)} msgs` : "..."}
              meta={preview ? `de ${formatTokenCount(preview.target_message_count)} pedidas` : "Aguardando preview"}
              accent
            />
            <MemorySignalCard
              label="Modo atual aguenta"
              value={preview ? `${formatTokenCount(preview.planner_message_capacity)} msgs` : "..."}
              meta={preview ? `${formatTokenCount(preview.current_char_budget)} chars de transcript` : "Aguardando preview"}
              tone="indigo"
            />
            <MemorySignalCard
              label="Teto desta stack"
              value={preview ? `${formatTokenCount(preview.stack_max_message_capacity)} msgs` : "..."}
              meta="Cap interno atual: 250 msgs e 60k chars"
              tone="amber"
            />
            <MemorySignalCard
              label="Teto do reasoner"
              value={modelRangeLabel}
              meta="Faixa por mensagem media desta janela"
              tone="emerald"
            />
          </div>

          <div className="memory-controls-stack">
            <div className="control-block">
              <div className="control-head">
                <label>Alvo de Mensagens</label>
                <span>Amostragem máxima por leitura</span>
              </div>
              <SegmentedControl
                options={MESSAGE_TARGET_PRESETS.map(String)}
                selected={String(filters.targetMessageCount)}
                onChange={(value) => onTargetChange(Number(value))}
              />
            </div>

            <div className="control-block">
              <div className="control-head">
                <label>Alcance Máximo</label>
                <span>Janela retrospectiva</span>
              </div>
              <SegmentedControl
                options={LOOKBACK_PRESETS.map(formatHoursLabel)}
                selected={formatHoursLabel(filters.maxLookbackHours)}
                onChange={(value) => {
                  const resolved = LOOKBACK_PRESETS.find((hours) => formatHoursLabel(hours) === value) ?? 72;
                  onLookbackChange(resolved);
                }}
              />
            </div>

            <div className="control-block">
              <div className="control-head">
                <label>Profundidade da Análise</label>
                <span>Nível de esforço do DeepSeek</span>
              </div>
              <div className="detail-card-grid">
                {DETAIL_OPTIONS.map((option) => {
                  const active = option.value === filters.detailMode;
                  return (
                    <button
                      key={option.value}
                      className={`detail-card${active ? " detail-card-active" : ""}`}
                      onClick={() => onDetailChange(option.value)}
                      type="button"
                    >
                      <div className="detail-card-head">
                        <strong>{option.label}</strong>
                        <span>{option.badge}</span>
                      </div>
                      <p>{option.description}</p>
                    </button>
                  );
                })}
              </div>
              <div className="depth-reality-strip">
                <strong>Profundidade real do modo selecionado</strong>
                <p>
                  {preview
                    ? `Este modo libera ${formatTokenCount(preview.current_char_budget)} chars de transcript, comporta ate ${formatTokenCount(preview.planner_message_capacity)} mensagens nesta janela, usa um piso seguro de ${formatTokenCount(preview.safe_input_budget_floor_tokens)} tokens de entrada e reserva ${formatTokenCount(preview.request_output_reserve_tokens)} tokens de saida.`
                    : "Assim que o preview carregar, este bloco mostra o budget real de transcript, input seguro e saida reservada do modo escolhido."}
                </p>
              </div>
            </div>
          </div>

          <div className="memory-capacity-rails">
            <CapacityRail
              label="Meta atendida pela leitura atual"
              helper={preview ? `${formatTokenCount(missingFromTarget)} ainda ficam fora do alvo escolhido` : "Aguardando preview"}
              current={preview?.selected_message_count ?? 0}
              max={preview?.target_message_count ?? 1}
              tone="indigo"
            />
            <CapacityRail
              label="Uso do piso conservador de contexto"
              helper={
                preview
                  ? `${formatTokenCount(preview.remaining_input_headroom_floor_tokens)} tokens ainda livres antes do limite seguro`
                  : "Aguardando preview"
              }
              current={preview?.estimated_input_tokens ?? 0}
              max={preview?.safe_input_budget_floor_tokens ?? 1}
              tone="amber"
            />
            <CapacityRail
              label="Uso do teto real desta stack"
              helper={
                preview
                  ? `${formatTokenCount(preview.stack_max_message_capacity)} mensagens e o maximo plausivel com este perfil`
                  : "Aguardando preview"
              }
              current={preview?.selected_message_count ?? 0}
              max={preview?.stack_max_message_capacity ?? 1}
              tone="emerald"
            />
          </div>

          <div className="memory-economics-grid">
            <MetricTile label="Tokens do transcript" value={preview ? `~${formatTokenCount(preview.selected_transcript_tokens)}` : "..."} accent />
            <MetricTile label="Tokens do contexto salvo" value={preview ? `~${formatTokenCount(preview.estimated_prompt_context_tokens)}` : "..."} tone="indigo" />
            <MetricTile label="Reasoning previsto" value={preview ? `~${formatTokenCount(preview.estimated_reasoning_tokens)}` : "..."} tone="amber" />
            <MetricTile label="Saída reservada" value={preview ? `~${formatTokenCount(preview.request_output_reserve_tokens)}` : "..."} tone="emerald" />
            <MetricTile label="Custo estimado" value={costRangeLabel} />
            <MetricTile
              label="Média por mensagem"
              value={preview ? `${formatTokenCount(preview.average_selected_message_tokens)} tk` : "..."}
              tone="zinc"
            />
          </div>

          <div className="memory-doc-grid">
            <MiniPanel
              title="Contexto"
              tone="amber"
              icon={BarChart3}
              content={
                preview?.documentation_context_note ??
                "O planner usa um piso conservador da documentacao para nao inflar o alcance visivel."
              }
            />
            <MiniPanel
              title="Custo"
              tone="emerald"
              icon={Terminal}
              content={
                preview?.documentation_pricing_note ??
                "A faixa de custo combina o gasto de entrada e saida com base nos precos oficiais atuais do DeepSeek."
              }
            />
          </div>
        </Card>

        <Card className="memory-score-card">
          <SectionTitle
            title="Compensa analisar agora?"
            icon={Zap}
            action={preview ? <span className={`micro-badge micro-badge-${previewTone}`}>{preview.recommendation_label}</span> : null}
          />

          <div className="score-gauge-wrap">
            <svg className="score-gauge" viewBox="0 0 220 220">
              <circle className="score-gauge-base" cx="110" cy="110" r={gaugeRadius} />
              <circle
                className={`score-gauge-fill score-gauge-${previewTone}`}
                cx="110"
                cy="110"
                r={gaugeRadius}
                strokeDasharray={gaugeCircumference}
                strokeDashoffset={dashOffset}
              />
            </svg>
            <div className="score-gauge-center">
              <span>{previewScore}</span>
              <small>score</small>
            </div>
          </div>

          <p className="score-summary">
            {previewLoading
              ? "Calculando custo, volume novo e ganho esperado..."
              : preview?.recommendation_summary ??
                "O AuraCore mede quantas mensagens novas chegaram, quantas já foram substituídas e quanto contexto a próxima leitura realmente deve agregar."}
          </p>

          <div className="retention-banner">
            <div>
              <span>Novas</span>
              <strong>{preview ? preview.new_message_count : "--"}</strong>
            </div>
            <div>
              <span>Perdidas pela retenção</span>
              <strong>{preview ? preview.replaced_message_count : "--"}</strong>
            </div>
            <div>
              <span>Headroom seguro</span>
              <strong>{preview ? `~${formatTokenCount(preview.remaining_input_headroom_floor_tokens)}` : "--"}</strong>
            </div>
          </div>

          <div className="memory-score-metrics">
            <MemorySignalCard
              label="Input real"
              value={preview ? `~${formatTokenCount(preview.estimated_input_tokens)} tk` : "..."}
              meta="prompt estrutural + contexto salvo + transcript"
              tone="indigo"
            />
            <MemorySignalCard
              label="Output esperado"
              value={preview ? `~${formatTokenCount(preview.estimated_output_tokens)} tk` : "..."}
              meta={preview ? `de ate ${formatTokenCount(preview.request_output_reserve_tokens)} reservados` : "Aguardando preview"}
              tone="emerald"
            />
            <MemorySignalCard
              label="Faixa de custo"
              value={costRangeLabel}
              meta="Cache miss e faixas oficiais do DeepSeek"
              tone="amber"
            />
          </div>

          <div className="memory-action-stack">
            <button
              className="ac-secondary-button"
              onClick={onRefreshMessages}
              disabled={isRefreshingMessages || agentState.running}
              type="button"
            >
              <RefreshCw size={15} className={isRefreshingMessages ? "spin" : ""} />
              {isRefreshingMessages ? "Puxando mensagens..." : "Puxar Novas Mensagens do WhatsApp"}
            </button>
            <button
              className="ac-success-button"
              onClick={onInitialAnalysis}
              disabled={agentState.running || memoryReady || !preview?.selected_message_count}
              type="button"
            >
              <Play size={15} />
              {agentState.running && agentState.intent === "first_analysis" ? "Executando..." : "Fazer Primeira Análise"}
            </button>
            <button
              className="ac-primary-button"
              onClick={onImproveMemory}
              disabled={agentState.running || !memoryReady || !preview?.selected_message_count}
              type="button"
            >
              <Sparkles size={15} />
              {agentState.running && agentState.intent === "improve_memory" ? "Melhorando..." : "Ler Novas Mensagens e Melhorar Memória"}
            </button>
          </div>

          <div className="memory-action-guides">
            <div>
              <strong>Puxar novas mensagens</strong>
              <p>Reler o historico direto do WhatsApp, ignorar grupos e manter no Supabase so o volume operacional da memoria.</p>
            </div>
            <div>
              <strong>Fazer primeira analise</strong>
              <p>Criar a primeira base consolidada do dono quando ainda nao existe memoria forte salva.</p>
            </div>
            <div>
              <strong>Melhorar memoria</strong>
              <p>Usar mensagens novas junto com snapshots, projetos e chat pessoal para atualizar o que a IA ja sabe.</p>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <SectionTitle title="Janela Atual e Alcance Máximo" icon={MessageSquare} />
        <div className="memory-breakdown-grid">
          <MemorySignalCard
            label="Mensagens disponíveis na janela"
            value={preview ? formatTokenCount(preview.available_message_count) : "..."}
            meta={preview ? `alcance configurado em ${formatHoursLabel(preview.max_lookback_hours)}` : "Aguardando preview"}
          />
          <MemorySignalCard
            label="Transcript que entra agora"
            value={preview ? `${formatTokenCount(preview.selected_transcript_chars)} chars` : "..."}
            meta={preview ? `media de ${formatTokenCount(preview.average_selected_message_chars)} chars por mensagem` : "Aguardando preview"}
            tone="indigo"
          />
          <MemorySignalCard
            label="Contexto seguro do reasoner"
            value={preview ? `${formatTokenCount(preview.safe_input_budget_floor_tokens)} tk` : "..."}
            meta={
              preview
                ? `saida docs ${formatTokenCount(preview.model_default_output_tokens)}/${formatTokenCount(preview.model_max_output_tokens)} e reserva atual ${formatTokenCount(preview.request_output_reserve_tokens)}`
                : "Aguardando preview"
            }
            tone="amber"
          />
          <MemorySignalCard
            label="Mensagens retidas no Supabase"
            value={preview ? `${formatTokenCount(preview.retained_message_count)}/${formatTokenCount(preview.retention_limit)}` : "..."}
            meta={preview ? `${formatTokenCount(preview.new_message_count)} novas ainda nao consolidadas` : "Aguardando preview"}
            tone="emerald"
          />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Snapshot Consolidado Atual" icon={FileText} />
        {latestSnapshot ? (
          <div className="snapshot-console">
            <pre>{`{
  "timestamp": "${latestSnapshot.created_at}",
  "window_summary": ${JSON.stringify(latestSnapshot.window_summary)},
  "source_message_count": ${latestSnapshot.source_message_count},
  "key_learnings": ${JSON.stringify(latestSnapshot.key_learnings.slice(0, 4), null, 2)},
  "routine_signals": ${JSON.stringify(latestSnapshot.routine_signals.slice(0, 4), null, 2)},
  "preferences": ${JSON.stringify(latestSnapshot.preferences.slice(0, 4), null, 2)}
}`}</pre>
          </div>
        ) : (
          <div className="empty-hint">
            <Database size={18} />
            <p>Sem snapshot ainda. A primeira leitura cria a base consolidada do dono.</p>
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle
          title="Ajuste Fino da Memória Salva"
          icon={Sparkles}
          action={<span className="micro-badge">sem reler WhatsApp</span>}
        />
        <p className="support-copy">
          Este ajuste opcional reescreve a memoria consolidada usando apenas o que ja esta salvo no Supabase. Ele nao puxa mensagens novas.
        </p>
        <button className="ac-secondary-button" onClick={onRefineSaved} disabled={agentState.running || !memoryReady} type="button">
          <Sparkles size={15} />
          {agentState.running && agentState.intent === "refine_saved" ? "Refinando..." : "Refinar Memória Já Salva"}
        </button>
      </Card>

      <Card>
        <SectionTitle title="Memória Atual do Dono" icon={Fingerprint} />
        <p className="lead-copy">
          {memory?.life_summary?.trim()
            ? memory.life_summary
            : "Nenhum resumo consolidado ainda. Assim que a primeira leitura rodar, este bloco vira a visão mais útil do dono para o chat e para futuros refinamentos."}
        </p>
      </Card>

      {previewError ? <InlineError title="Falha no preview" message={previewError} /> : null}
      {messageRefreshError ? <InlineError title="Falha ao reler o WhatsApp" message={messageRefreshError} /> : null}
      {memoryError ? <InlineError title="Falha na memória" message={memoryError} /> : null}
    </div>
  );
}

function ProjectsTab({ projects }: { projects: ProjectMemory[] }) {
  return (
    <div className="page-stack">
      <div className="project-focus-row">
        {projects.slice(0, 2).map((project, index) => (
          <Card key={`${project.id}-focus`} className={`project-focus-card${index === 0 ? " project-focus-card-primary" : ""}`}>
            <div className="project-focus-head">
              <div>
                <span>{index === 0 ? "Foco Principal" : "Foco Secundário"}</span>
                <h3>{project.project_name}</h3>
              </div>
              <div className={`micro-status micro-status-${index === 0 ? "emerald" : "amber"}`}>{project.status || "Em progresso"}</div>
            </div>
            <ProgressBar value={getProjectStrength(project)} tone={index === 0 ? "indigo" : "zinc"} label="Densidade de sinal da frente" />
            <p>{project.summary}</p>
          </Card>
        ))}
      </div>

      <SectionTitle title="Mapa Detalhado de Projetos" icon={FolderGit2} />

      {projects.length === 0 ? (
        <Card>
          <div className="empty-hint">
            <FolderGit2 size={18} />
            <p>Nenhum projeto consolidado ainda. Assim que a memória tiver mais sinal, as frentes reais aparecem aqui.</p>
          </div>
        </Card>
      ) : (
        <div className="project-list-stack">
          {projects.map((project) => (
            <Card key={project.id} className="project-list-card">
              <div className="project-list-grid">
                <div className="project-left-col">
                  <div className="project-name-line">
                    <GitBranch size={16} />
                    <h3>{project.project_name}</h3>
                  </div>
                  <div className="project-seen-row">
                    <Clock size={12} />
                    <span>{project.last_seen_at ? `Visto em ${formatShortDateTime(project.last_seen_at)}` : "Sem data recente"}</span>
                  </div>

                  <div className="project-core-meta">
                    <ProjectInfoBlock label="O que está sendo desenvolvido" value={project.what_is_being_built || project.summary} />
                    <ProjectInfoBlock label="Para quem" value={getAudienceLabel(project)} />
                  </div>
                </div>

                <div className="project-right-col">
                  <div>
                    <h4>Resumo Atualizado</h4>
                    <p>{project.summary}</p>
                  </div>

                  <div className="project-bottom-panels">
                    <MiniPanel
                      title="Próximos Passos"
                      tone="amber"
                      icon={ChevronRight}
                      content={project.next_steps[0] ?? "Sem próximo passo consolidado."}
                    />
                    <MiniPanel
                      title="Evidência Recente"
                      tone="emerald"
                      icon={CheckCircle2}
                      content={project.evidence[0] ?? "Sem evidência recente consolidada."}
                    />
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
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
    <div className="chat-shell-modern">
      <div className="chat-header-modern">
        <div className="chat-bot-badge">
          <div className="chat-bot-avatar">
            <Bot size={18} />
          </div>
          <div>
            <h3>{chatThreadTitle}</h3>
            <p>
              <Database size={10} />
              Contexto de memória ativo
            </p>
          </div>
        </div>
        <div className="chat-header-actions">
          <button className="ac-icon-button" type="button">
            <Settings size={16} />
          </button>
          <button className="ac-icon-button" type="button">
            <MoreVertical size={16} />
          </button>
        </div>
      </div>

      <div ref={chatScrollRef} className="chat-scroll-modern">
        <div className="chat-date-pill">Hoje</div>

        {chatMessages.length === 0 ? (
          <Card className="chat-empty-card">
            <SectionTitle title="Sem conversa ainda" icon={Bot} />
            <p>Use o chat para discutir rotina, projetos, decisões ou pedir ajuda contextual. Esse histórico também melhora as próximas leituras.</p>
          </Card>
        ) : (
          chatMessages.map((message) => (
            <div
              key={message.id}
              className={`chat-row-modern${message.role === "assistant" ? "" : " chat-row-user"}`}
            >
              <div className={`chat-avatar-modern${message.role === "assistant" ? "" : " chat-avatar-user"}`}>
                {message.role === "assistant" ? <Bot size={16} /> : <User size={16} />}
              </div>
              <div className="chat-bubble-stack">
                <div className="chat-bubble-meta">
                  <strong>{message.role === "assistant" ? "AuraCore" : "Você"}</strong>
                  <span>{formatShortDateTime(message.created_at)}</span>
                </div>
                <div className={`chat-bubble-modern${message.role === "assistant" ? "" : " chat-bubble-user"}`}>
                  <p>{message.content}</p>
                </div>
              </div>
            </div>
          ))
        )}

        <div className="quick-replies">
          <button type="button">Resumir minhas pendências de hoje</button>
          <button type="button">O que você aprendeu sobre meus projetos?</button>
        </div>
      </div>

      <div className="chat-composer-modern">
        {chatError ? <InlineError title="Falha no chat" message={chatError} /> : null}
        <div className="chat-input-row">
          <button className="ac-icon-button ac-hide-mobile" type="button">
            <Paperclip size={16} />
          </button>
          <div className="chat-textarea-shell">
            <textarea
              rows={1}
              value={chatDraft}
              onChange={(event) => onChatDraftChange(event.target.value)}
              placeholder="Discutir rotina, atualizar status de projetos ou revisar critérios de decisão..."
            />
          </div>
          <button className="ac-primary-button" onClick={onSubmit} disabled={isSendingChat} type="button">
            <Send size={15} />
            {isSendingChat ? "Enviando..." : "Enviar"}
          </button>
        </div>
        <div className="chat-footer-note">
          <Cpu size={11} />
          O agente pode usar esse chat para reforçar prioridades, projetos e padrões do dono.
        </div>
      </div>
    </div>
  );
}

function ActivityTab({
  agentState,
  steps,
  logs,
  preview,
  memory,
  latestSnapshot,
  projectsCount,
  snapshotsCount,
}: {
  agentState: AgentState;
  steps: AgentStep[];
  logs: AgentLog[];
  preview: MemoryAnalysisPreview | null;
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projectsCount: number;
  snapshotsCount: number;
}) {
  const memoryReady = hasEstablishedMemory(memory, latestSnapshot);
  const resolvedIntent = agentState.intent ?? (memoryReady ? "improve_memory" : "first_analysis");
  const thinkingLines = buildActivityThinking({
    preview,
    intent: resolvedIntent,
    hasMemory: memoryReady,
    projectsCount,
    snapshotsCount,
  });
  const costRangeLabel = preview
    ? `${formatUsd(preview.estimated_cost_total_floor_usd)}-${formatUsd(preview.estimated_cost_total_ceiling_usd)}`
    : "...";

  return (
    <div className="page-stack narrow-stack">
      <Card className="activity-hero-card">
        <div className="activity-hero-meter">
          <svg viewBox="0 0 120 120">
            <circle className="activity-ring-base" cx="60" cy="60" r="50" />
            <circle
              className="activity-ring-fill"
              cx="60"
              cy="60"
              r="50"
              strokeDasharray={314}
              strokeDashoffset={314 - (314 * agentState.progress) / 100}
            />
          </svg>
          <div className="activity-ring-center">{agentState.progress}%</div>
        </div>

        <div className="activity-hero-copy">
          <div className="activity-hero-head">
            <h3>
              <Terminal size={18} />
              {getIntentTitle(resolvedIntent)}
            </h3>
            <span className={`micro-status micro-status-${agentState.running ? "indigo" : "emerald"}`}>
              {agentState.running ? "Processando" : "Ocioso"}
            </span>
          </div>
          <p>{agentState.status}</p>
          <div className="step-pill-row">
            {steps.map((step) => {
              const completed = agentState.progress >= step.threshold;
              const active =
                agentState.running &&
                agentState.progress >= step.threshold &&
                !steps.some((candidate) => candidate.threshold > step.threshold && agentState.progress >= candidate.threshold);
              return (
                <span
                  key={step.label}
                  className={`step-pill${completed ? " step-pill-done" : ""}${active ? " step-pill-active" : ""}`}
                >
                  {completed ? <CheckCircle2 size={12} /> : active ? <RefreshCw size={12} className="spin" /> : <Clock size={12} />}
                  {step.label}
                </span>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="activity-insight-grid">
        <MemorySignalCard
          label="Ação atual"
          value={getIntentTitle(resolvedIntent)}
          meta={memoryReady ? "Memória base já existe" : "Ainda sem base consolidada"}
          accent
        />
        <MemorySignalCard
          label="Janela útil"
          value={preview ? `${formatTokenCount(preview.selected_message_count)}/${formatTokenCount(preview.available_message_count)} msgs` : "..."}
          meta={preview ? `teto operacional de ${formatTokenCount(preview.stack_max_message_capacity)} msgs` : "Aguardando preview"}
          tone="indigo"
        />
        <MemorySignalCard
          label="Base já conhecida"
          value={`${formatTokenCount(snapshotsCount)} snapshots / ${formatTokenCount(projectsCount)} projetos`}
          meta={memoryReady ? "Tambem cruza com o chat pessoal salvo" : "Primeira base ainda sera criada"}
          tone="emerald"
        />
        <MemorySignalCard
          label="Custo previsto"
          value={costRangeLabel}
          meta={preview ? `~${formatTokenCount(preview.estimated_total_tokens)} tokens totais` : "Aguardando preview"}
          tone="amber"
        />
      </div>

      <Card className="activity-thinking-card">
        <SectionTitle title="Resumo do Pensamento" icon={Brain} action={<span className="micro-badge">sem CoT bruto</span>} />
        <p className="support-copy">
          O painel mostra o raciocinio operacional da execucao e o que o modelo vai considerar. A cadeia de pensamento bruta do `deepseek-reasoner` nao e exposta.
        </p>
        <div className="activity-thinking-list">
          {thinkingLines.map((line, index) => (
            <div key={`${line.slice(0, 20)}-${index}`} className="activity-thinking-item">
              <span>{index + 1}</span>
              <p>{line}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="terminal-shell">
        <div className="terminal-header">
          <span className="terminal-dot terminal-dot-red" />
          <span className="terminal-dot terminal-dot-yellow" />
          <span className="terminal-dot terminal-dot-green" />
          <span className="terminal-title">execution.log</span>
        </div>
        <div className="terminal-body">
          {logs.map((log) => (
            <div key={log.id} className="terminal-line">
              <span className="terminal-time">{formatShortDateTime(log.createdAt)}</span>
              <span className={`terminal-tag terminal-tag-${log.tone}`}>[{log.tone}]</span>
              <span className="terminal-message">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModernStatCard({
  label,
  value,
  meta,
  icon: Icon,
  tone = "zinc",
}: {
  label: string;
  value: string;
  meta: string;
  icon: LucideIcon;
  tone?: "emerald" | "amber" | "indigo" | "rose" | "zinc";
}) {
  return (
    <Card className={`modern-stat-card modern-stat-${tone}`}>
      <div className="modern-stat-top">
        <span>{label}</span>
        <Icon size={15} />
      </div>
      <strong>{value}</strong>
      <small>{meta}</small>
    </Card>
  );
}

function SignalBlock({
  title,
  lines,
  emptyLabel,
  subtle = false,
}: {
  title: string;
  lines: string[];
  emptyLabel: string;
  subtle?: boolean;
}) {
  return (
    <div className={`signal-block${subtle ? " signal-block-subtle" : ""}`}>
      <span>{title}</span>
      {lines.length === 0 ? (
        <p>{emptyLabel}</p>
      ) : (
        <ul>
          {lines.slice(0, 3).map((line, index) => (
            <li key={`${title}-${index}`}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "emerald" | "amber" | "indigo" | "zinc";
}) {
  return (
    <div className="status-line">
      <div className="status-line-left">
        <span className={`status-line-dot tone-${tone}`} />
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
    </div>
  );
}

function MetricTile({
  label,
  value,
  accent = false,
  tone = "zinc",
}: {
  label: string;
  value: string;
  accent?: boolean;
  tone?: "emerald" | "amber" | "indigo" | "zinc";
}) {
  return (
    <div className={`metric-tile${accent ? " metric-tile-accent" : ""}${tone !== "zinc" ? ` metric-tile-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MemorySignalCard({
  label,
  value,
  meta,
  accent = false,
  tone = "zinc",
}: {
  label: string;
  value: string;
  meta: string;
  accent?: boolean;
  tone?: "emerald" | "amber" | "indigo" | "zinc";
}) {
  return (
    <div className={`memory-signal-card${accent ? " memory-signal-card-accent" : ""}${tone !== "zinc" ? ` memory-signal-card-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{meta}</p>
    </div>
  );
}

function CapacityRail({
  label,
  helper,
  current,
  max,
  tone,
}: {
  label: string;
  helper: string;
  current: number;
  max: number;
  tone: "emerald" | "amber" | "indigo" | "rose" | "zinc";
}) {
  const resolvedMax = Math.max(1, max);
  const width = `${Math.max(0, Math.min(100, (current / resolvedMax) * 100))}%`;

  return (
    <div className="capacity-rail">
      <div className="capacity-rail-head">
        <div>
          <strong>{label}</strong>
          <span>{helper}</span>
        </div>
        <b>
          {formatTokenCount(current)} / {formatTokenCount(resolvedMax)}
        </b>
      </div>
      <div className="mini-progress-track">
        <div className={`mini-progress-fill tone-${tone}`} style={{ width }} />
      </div>
    </div>
  );
}

function ProjectInfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="project-info-block">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MiniPanel({
  title,
  tone,
  icon: Icon,
  content,
}: {
  title: string;
  tone: "amber" | "emerald";
  icon: LucideIcon;
  content: string;
}) {
  return (
    <div className="mini-panel">
      <span className={`mini-panel-title tone-${tone}`}>
        <Icon size={14} />
        {title}
      </span>
      <p>{content}</p>
    </div>
  );
}

function InlineError({ title, message }: { title: string; message: string }) {
  return (
    <div className="inline-error-modern">
      <AlertCircle size={16} />
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
    </div>
  );
}
