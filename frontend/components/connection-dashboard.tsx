"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import toast, { Toaster } from "react-hot-toast";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertCircle,
  Archive,
  BadgeCheck,
  BarChart3,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock,
  Cpu,
  Database,
  Edit2,
  Check,
  Eye,
  FileText,
  FolderGit2,
  Fingerprint,
  GitBranch,
  LockKeyhole,
  Menu,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Smartphone,
  Terminal,
  Trash2,
  User,
  Users,
  X,
  XCircle,
  Zap,
} from "lucide-react";

import {
  createChatThread,
  deleteChatThread,
  connectAgent,
  connectObserver,
  clearSavedDatabase,
  assistMemoryProjectEdit,
  deleteAgendaEvent,
  executeMemoryAnalysis,
  updateMemoryRelation,
  RefineMemoryResponse,
  deleteMemoryProject,
  getAgentStatus,
  getAgentWorkspace,
  getChatWorkspace,
  getCurrentMemory,
  getMemoryActivity,
  getMemoryGroups,
  getMemoryLiveSummary,
  getMemoryProjects,
  getMemoryRelations,
  getImportantMessages,
  getMemoryStatus,
  getMemorySnapshots,
  getObserverStatus,
  refreshObserverMessages,
  resetAgent,
  resetObserver,
  sendChatMessageStream,
  getAgendaEvents,
  updateAgentSettings,
  updateAgendaEvent,
  updateAutomationSettings,
  updateMemoryGroupSelection,
  updateMemoryProject,
  updateMemoryProjectCompletion,
  runAutomationTick,
  type AuthenticatedAccount,
  type AnalysisJob,
  type AutomationStatus,
  type AutomationDecision,
  type ChatMessage,
  type ChatThread,
  type ChatWorkspace,
  type ImportantMessage,
  type MemoryActivity,
  type MemoryCurrent,
  type MemoryLiveSummary,
  type MemoryStatus,
  type MemorySnapshot,
  type ModelRun,
  type ObserverStatus,
  type AgendaEvent,
  type UpdateAgendaEventInput,
  type WhatsAppAgentMessage,
  type WhatsAppAgentContactMemory,
  type WhatsAppAgentSession,
  type WhatsAppAgentSettings,
  type WhatsAppAgentStatus,
  type WhatsAppAgentThread,
  type WhatsAppAgentWorkspace,
  type ProjectMemory,
  type PersonRelation,
  type WhatsAppGroupSelection,
  type WhatsAppSyncRun,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";
type AgentMode = "idle" | "analyze";
type AgentIntent = "first_analysis" | "improve_memory";
type TabId =
  | "overview"
  | "observer"
  | "agent"
  | "groups"
  | "memory"
  | "important"
  | "relations"
  | "agenda"
  | "projects"
  | "chat"
  | "activity"
  | "automation"
  | "manual"
  | "account";
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

type ActivityTraceItem = {
  id: string;
  title: string;
  detail: string;
  timestamp: string | null;
  tone: "info" | "success" | "error" | "active";
  meta?: string;
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

type DisplayAgentState = AgentState & {
  stageIndex: number | null;
  badgeTone: "teal" | "emerald" | "amber" | "zinc";
};

type AutomationDraft = Record<string, never> | null;

type InsightMetric = {
  label: string;
  value: number;
  description: string;
  color: "emerald" | "amber" | "indigo" | "zinc";
};

type NavGroup = {
  title: string;
  items: NavItem[];
};

type NavItem = {
  id: TabId;
  label: string;
  icon: LucideIcon;
};

type HeavyLiveResourceKey = "groups" | "projects" | "snapshots" | "important" | "relations";

const CONNECTING_STATUS_POLL_INTERVAL_MS = 3200;
const LIVE_STATUS_POLL_INTERVAL_MS = 9000;
const LIVE_MEMORY_DIGEST_POLL_INTERVAL_MS = 6000;
const ACTIVE_JOB_POLL_INTERVAL_MS = 5000;
const QR_REFRESH_INTERVAL_MS = 45000;
const ATTENTION_REFRESH_THROTTLE_MS = 2500;
const LIVE_REFRESH_INTERVALS: Record<TabId, number> = {
  overview: 14000,
  observer: 8000,
  agent: 9000,
  groups: 18000,
  memory: 16000,
  important: 20000,
  relations: 20000,
  agenda: 20000,
  projects: 20000,
  chat: 10000,
  activity: 12000,
  automation: 12000,
  manual: 20000,
  account: 20000,
};
const HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS: Record<HeavyLiveResourceKey, number> = {
  groups: 18000,
  projects: 22000,
  snapshots: 22000,
  important: 24000,
  relations: 22000,
};
const BUSY_HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS: Record<HeavyLiveResourceKey, number> = {
  groups: 12000,
  projects: 12000,
  snapshots: 12000,
  important: 14000,
  relations: 12000,
};
const NAV_GROUPS: NavGroup[] = [
  {
    title: "Painel Principal",
    items: [
      { id: "overview", label: "Visão Geral", icon: Brain },
    ],
  },
  {
    title: "Inteligência",
    items: [
      { id: "observer", label: "Observador", icon: Eye },
      { id: "groups", label: "Grupos", icon: Users },
      { id: "memory", label: "Memória", icon: Database },
      { id: "important", label: "Importantes", icon: Archive },
      { id: "relations", label: "Relações", icon: User },
    ],
  },
  {
    title: "Operações",
    items: [
      { id: "agenda", label: "Agenda", icon: Clock },
      { id: "projects", label: "Projetos", icon: FolderGit2 },
      { id: "chat", label: "Chat Pessoal", icon: MessageSquare },
    ],
  },
  {
    title: "Sistema",
    items: [
      { id: "account", label: "Minha Conta", icon: Fingerprint },
      { id: "manual", label: "Manual", icon: FileText },
    ],
  },
];

const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
const getAutomationStatus = getMemoryActivity;
const runFirstMemoryAnalysis = () => executeMemoryAnalysis("first_analysis");
const runNextMemoryBatch = () => executeMemoryAnalysis("improve_memory");

const IDLE_AGENT_STATUS = "Nenhuma atualização em andamento.";
const BRAZIL_TIMEZONE = "America/Sao_Paulo";

const ANALYZE_STEPS: AgentStep[] = [
  {
    threshold: 8,
    label: "Coletando sinais recentes",
    detail: "Lendo conversas úteis, priorizando diretas no bootstrap e respeitando grupos opt-in nas leituras futuras.",
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
    label: "Consolidando memoria",
    detail: "Transformando sinais dispersos em um perfil mais util e mais fiel ao dono.",
  },
  {
    threshold: 94,
    label: "Salvando no banco local",
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
    label: "Refinando memoria",
    detail: "Melhorando linguagem, prioridades e retrato comportamental do dono.",
  },
  {
    threshold: 94,
    label: "Aplicando refinamento",
    detail: "Atualizando memória atual e frentes principais sem reprocessar tudo do zero.",
  },
];

function getLiveRefreshInterval(tab: TabId): number {
  return LIVE_REFRESH_INTERVALS[tab];
}

function isDocumentVisible(): boolean {
  if (typeof document === "undefined") {
    return true;
  }
  return document.visibilityState === "visible";
}

function mergeStatus(previous: ObserverStatus | null, next: ObserverStatus): ObserverStatus {
  return {
    ...next,
    qr_code: next.qr_code ?? previous?.qr_code ?? null,
  };
}

function formatState(state: string): string {
  const normalized = state.trim().toLowerCase();
  if (normalized === "open") return "Online";
  if (normalized === "connecting") return "Conectando";
  if (normalized === "reconnecting") return "Reconectando";
  if (normalized === "close") return "Desconectado";
  if (normalized === "logged_out") return "Deslogado";

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
    timeZone: BRAZIL_TIMEZONE,
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
    timeZone: BRAZIL_TIMEZONE,
  });
}

function formatBrazilDateTimeInput(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: BRAZIL_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const parts = formatter.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes): string => parts.find((part) => part.type === type)?.value ?? "00";
  return `${read("year")}-${read("month")}-${read("day")}T${read("hour")}:${read("minute")}`;
}

function parseBrazilDateTimeInput(value: string): Date {
  return new Date(`${value}:00-03:00`);
}

function formatReminderOffsetLabel(minutes: number): string {
  if (minutes <= 0) {
    return "No horário";
  }
  if (minutes % 1440 === 0) {
    const days = minutes / 1440;
    return `${days} dia${days > 1 ? "s" : ""} antes`;
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hora${hours > 1 ? "s" : ""} antes`;
  }
  return `${minutes} min antes`;
}

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) {
    return "Sem atividade";
  }

  const timestamp = new Date(value).getTime();
  const deltaMinutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
  if (deltaMinutes < 1) {
    return "Agora";
  }
  if (deltaMinutes < 60) {
    return `${deltaMinutes} min`;
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours} h`;
  }
  const deltaDays = Math.round(deltaHours / 24);
  return `${deltaDays} d`;
}

function truncateText(value: string | null | undefined, maxLength: number): string {
  const normalized = (value ?? "").split(/\s+/).filter(Boolean).join(" ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 3).trimEnd()}...`;
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

function formatImportantCategory(category: string): string {
  switch (category) {
    case "credential":
      return "Credencial";
    case "access":
      return "Acesso";
    case "project":
      return "Projeto";
    case "money":
      return "Dinheiro";
    case "client":
      return "Cliente";
    case "deadline":
      return "Prazo";
    case "document":
      return "Documento";
    case "risk":
      return "Risco";
    default:
      return "Importante";
  }
}

function normalizeImportantCategory(category: string): string {
  return (category || "other").trim().toLowerCase();
}

function getImportantCategoryFamily(category: string): "access" | "operation" | "attention" | "other" {
  switch (normalizeImportantCategory(category)) {
    case "credential":
    case "access":
      return "access";
    case "project":
    case "client":
    case "money":
    case "document":
      return "operation";
    case "deadline":
    case "risk":
      return "attention";
    default:
      return "other";
  }
}

function getImportantCategoryFamilyLabel(category: string): string {
  switch (getImportantCategoryFamily(category)) {
    case "access":
      return "Acessos";
    case "operation":
      return "Operação";
    case "attention":
      return "Atenção";
    default:
      return "Diversos";
  }
}

function getImportantConfidenceBand(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 85) {
    return "high";
  }
  if (confidence >= 65) {
    return "medium";
  }
  return "low";
}

function getImportantConfidenceLabel(confidence: number): string {
  switch (getImportantConfidenceBand(confidence)) {
    case "high":
      return "Sinal forte";
    case "medium":
      return "Sinal médio";
    default:
      return "Pedir revisão";
  }
}

function formatTokenCount(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function hasEstablishedMemory(memory: MemoryCurrent | null, latestSnapshot: MemorySnapshot | null): boolean {
  return Boolean(memory?.last_analyzed_at || latestSnapshot?.id);
}

function getIntentTitle(intent: AgentIntent | null): string {
  switch (intent) {
    case "first_analysis":
      return "Fazer Primeira Análise";
    case "improve_memory":
      return "Atualizar Memória";
    default:
      return "Aguardando nova ação";
  }
}

function buildActivityThinking(args: {
  intent: AgentIntent | null;
  hasMemory: boolean;
  projectsCount: number;
  snapshotsCount: number;
}): string[] {
  const { intent, hasMemory, projectsCount, snapshotsCount } = args;
  const resolvedIntent = intent ?? (hasMemory ? "improve_memory" : "first_analysis");
  const lines: string[] = [];

  if (resolvedIntent === "first_analysis") {
    lines.push(
      "Esta rota cria a primeira base consolidada do dono; ainda nao existe memoria forte para cruzar, entao o foco e montar o primeiro retrato util.",
    );
  } else if (resolvedIntent === "improve_memory") {
    lines.push(
      "Esta rota compara mensagens recentes elegiveis com a memoria ja consolidada para reforcar o que mudou sem perder continuidade do perfil.",
    );
  } else {
    lines.push(
      "Esta rota nao reler o WhatsApp; ela limpa e reorganiza somente o que ja esta salvo no banco local para reduzir ruido.",
    );
  }

  if (hasMemory) {
    lines.push(
      `Hoje a base consolidada cruza ${snapshotsCount} snapshots, ${projectsCount} projetos e o historico do chat pessoal para manter continuidade entre leituras.`,
    );
  } else {
    lines.push("Como ainda nao existe base consolidada, a primeira leitura se apoia principalmente nas mensagens diretas mais recentes para montar a base inicial.");
  }

  return lines;
}

function buildPersistedActivityLogs(status: MemoryActivity | null): AgentLog[] {
  if (!status) {
    return [];
  }

  const syncLogs = status.sync_runs.slice(0, 3).map((syncRun) => ({
    id: `sync-${syncRun.id}`,
    tone: (syncRun.status === "failed" ? "error" : "info") as LogTone,
    createdAt: syncRun.finished_at ?? syncRun.last_activity_at ?? syncRun.started_at,
    message:
      syncRun.status === "failed"
        ? `Sync falhou depois de ver ${syncRun.messages_seen_count} mensagens. ${syncRun.error_text || "Sem detalhe adicional."}`
        : `Sync ${syncRun.status}: ${syncRun.messages_saved_count} salvas, ${syncRun.messages_ignored_count} ignoradas e ${syncRun.messages_pruned_count} podadas.`,
  }));
  const jobLogs = status.jobs.slice(0, 4).map((job) => ({
    id: `job-${job.id}`,
    tone: (job.status === "failed" ? "error" : job.status === "succeeded" ? "success" : "info") as LogTone,
    createdAt: job.finished_at ?? job.started_at ?? job.created_at,
    message:
      job.status === "failed"
        ? `Job ${job.status}: ${getIntentTitle(job.intent as AgentIntent)} falhou. ${job.error_text || "Sem detalhe persistido."}`
        : `Job ${job.status}: ${getIntentTitle(job.intent as AgentIntent)} em ${job.detail_mode}, alvo ${job.target_message_count} msgs, selecionadas ${job.selected_message_count}.`,
  }));
  const modelLogs = status.model_runs.slice(0, 3).map((run) => ({
    id: `model-${run.id}`,
    tone: (run.success ? "success" : "error") as LogTone,
    createdAt: run.created_at,
    message: run.success
      ? `${run.provider} concluiu ${run.run_type} em ${run.latency_ms ?? 0} ms${run.estimated_cost_usd ? `, teto estimado USD ${run.estimated_cost_usd.toFixed(4)}` : ""}.`
      : `${run.provider} falhou em ${run.run_type}. ${run.error_text || "Sem detalhe adicional."}`,
  }));

  return [...syncLogs, ...jobLogs, ...modelLogs].sort((left, right) => (
    new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
  ));
}

function automationStatusPlaceholder(status: MemoryActivity | null) {
  if (!status) {
    return null;
  }
  return {
    ...status,
    decisions: status.decisions ?? [],
    queued_jobs_count: status.queued_jobs_count ?? status.jobs.filter((job) => job.status === "queued").length,
    daily_auto_jobs_count: status.daily_auto_jobs_count ?? 0,
    daily_cost_usd: 0,
    settings: status.settings ?? {
      user_id: "",
      auto_sync_enabled: false,
      auto_analyze_enabled: false,
      auto_refine_enabled: false,
      min_new_messages_threshold: 20,
      stale_hours_threshold: 1,
      pruned_messages_threshold: 0,
      default_detail_mode: "balanced",
      default_target_message_count: 120,
      default_lookback_hours: 72,
      daily_budget_usd: 0,
      max_auto_jobs_per_day: 1,
      updated_at: new Date(0).toISOString(),
    },
  };
}

function getActivityToneLabel(tone: ActivityTraceItem["tone"]): string {
  switch (tone) {
    case "success":
      return "estavel";
    case "error":
      return "falha";
    case "active":
      return "ao vivo";
    default:
      return "analise";
  }
}

function isPendingAnalysisJob(job: AnalysisJob | null | undefined): job is AnalysisJob {
  return Boolean(job && (job.status === "queued" || job.status === "running"));
}

function resolvePendingAnalysisJob(args: {
  currentJob: AnalysisJob | null;
  activity: MemoryActivity | null;
  queuedJobId: string | null;
}): AnalysisJob | null {
  const { currentJob, activity, queuedJobId } = args;
  if (isPendingAnalysisJob(currentJob)) {
    return currentJob;
  }
  if (!activity) {
    return null;
  }
  if (queuedJobId) {
    const matchingJob = activity.jobs.find((job) => job.id === queuedJobId) ?? null;
    if (isPendingAnalysisJob(matchingJob)) {
      return matchingJob;
    }
  }
  return activity.jobs.find((job) => isPendingAnalysisJob(job)) ?? null;
}

function resolveRelatedSyncRun(activity: MemoryActivity | null, job: AnalysisJob | null): WhatsAppSyncRun | null {
  if (!activity) {
    return null;
  }
  if (job?.sync_run_id) {
    const matchingRun = activity.sync_runs.find((run) => run.id === job.sync_run_id) ?? null;
    if (matchingRun) {
      return matchingRun;
    }
  }
  return activity.sync_runs.find((run) => run.status === "running") ?? activity.sync_runs[0] ?? null;
}

function resolveRelatedModelRun(activity: MemoryActivity | null, job: AnalysisJob | null): ModelRun | null {
  if (!activity) {
    return null;
  }
  if (job) {
    const matchingRun = activity.model_runs.find((run) => run.job_id === job.id) ?? null;
    if (matchingRun) {
      return matchingRun;
    }
  }
  return activity.model_runs[0] ?? null;
}

function resolveLiveStageIndex(intent: AgentIntent, job: AnalysisJob | null, syncRun: WhatsAppSyncRun | null): number | null {
  if (syncRun?.status === "running" && !job) {
    return 0;
  }
  if (!job) {
    return null;
  }
  if (job.live_stage === "queued") {
    return 1;
  }
  if (job.live_stage === "analyzing") {
    return intent === "first_analysis" ? 3 : 2;
  }
  if (job.live_stage === "completed") {
    return intent === "first_analysis" ? 4 : 3;
  }
  if (job.status === "queued") {
    return 1;
  }
  if (job.status === "running") {
    return intent === "first_analysis" ? 3 : 2;
  }
  return null;
}

function resolveLiveProgress(intent: AgentIntent, job: AnalysisJob | null, syncRun: WhatsAppSyncRun | null): number {
  if (syncRun?.status === "running" && !job) {
    return 12;
  }
  if (!job) {
    return 0;
  }
  if (job.status === "succeeded") {
    return 100;
  }
  if (job.status === "failed") {
    return 0;
  }
  const backendProgress = Math.max(0, Math.min(100, Number(job.progress_percent ?? 0)));
  if (backendProgress > 0) {
    return backendProgress;
  }
  if (job.status === "queued") {
    return 24;
  }
  if (job.status === "running") {
    return intent === "first_analysis" ? 58 : 66;
  }
  return 0;
}

function resolveLiveStatus(args: {
  intent: AgentIntent;
  job: AnalysisJob | null;
  syncRun: WhatsAppSyncRun | null;
  modelRun: ModelRun | null;
}): string {
  const { intent, job, syncRun, modelRun } = args;
  if (syncRun?.status === "running" && !job) {
    return syncRun.messages_seen_count > 0
      ? `Coleta real em andamento. ${formatTokenCount(syncRun.messages_seen_count)} mensagens vistas ate agora.`
      : "Coleta real do WhatsApp em andamento.";
  }
  if (!job) {
    return IDLE_AGENT_STATUS;
  }
  if (job.status === "queued") {
    return intent === "first_analysis"
      ? "Primeira analise enfileirada no backend. O painel avanca apenas quando o servidor persistir a proxima fase."
      : "Atualizacao de memoria enfileirada no backend. O painel avanca apenas quando o servidor persistir a proxima fase.";
  }
  if (job.status === "running") {
    if (job.live_status_text) {
      return job.live_status_text;
    }
    const batchSize = syncRun?.messages_saved_count || job.selected_message_count;
    const base = intent === "first_analysis"
      ? "Primeira analise real em execucao no backend."
      : "Atualizacao real de memoria em execucao no backend.";
    if (batchSize > 0) {
      return `${base} Lote atual com ${formatTokenCount(batchSize)} mensagens uteis.`;
    }
    if (modelRun?.job_id === job.id) {
      return `${base} O motor ja devolveu resposta e o backend esta fechando a persistencia final.`;
    }
    return `${base} O andamento agora reflete apenas marcos persistidos.`;
  }
  return IDLE_AGENT_STATUS;
}

function getStepVisualState(agentState: DisplayAgentState, stepIndex: number, stepsLength: number): {
  completed: boolean;
  active: boolean;
} {
  if (agentState.running) {
    return {
      completed: agentState.stageIndex !== null && stepIndex < agentState.stageIndex,
      active: agentState.stageIndex === stepIndex,
    };
  }
  if (agentState.progress >= 100) {
    return { completed: stepIndex < stepsLength, active: false };
  }
  return { completed: false, active: false };
}

function buildActivityTrace(args: {
  agentState: AgentState;
  latestSyncRun: WhatsAppSyncRun | null;
  latestDecision: AutomationDecision | null;
  latestJob: AnalysisJob | null;
  latestModelRun: ModelRun | null;
}): ActivityTraceItem[] {
  const { agentState, latestSyncRun, latestDecision, latestJob, latestModelRun } = args;
  const items: ActivityTraceItem[] = [];

  if (agentState.running) {
    items.push({
      id: "live-agent",
      title: "Pipeline em execucao",
      detail: agentState.status,
      timestamp: new Date().toISOString(),
      tone: "active",
      meta: `${agentState.progress}% concluido`,
    });
  }

  if (latestSyncRun) {
    items.push({
      id: `trace-sync-${latestSyncRun.id}`,
      title: "Leitura operacional",
      detail: `${latestSyncRun.messages_saved_count} mensagens uteis salvas, ${latestSyncRun.messages_ignored_count} ignoradas e ${latestSyncRun.messages_pruned_count} podadas na janela mais recente.`,
      timestamp: latestSyncRun.finished_at ?? latestSyncRun.last_activity_at ?? latestSyncRun.started_at,
      tone: latestSyncRun.status === "failed" ? "error" : "success",
      meta: latestSyncRun.status,
    });
  }

  if (latestDecision) {
    items.push({
      id: `trace-decision-${latestDecision.id}`,
      title: "Sintese do raciocinio salvo",
      detail: latestDecision.explanation,
      timestamp: latestDecision.created_at,
      tone: latestDecision.should_analyze ? "success" : "info",
      meta: `${latestDecision.action} • ${latestDecision.reason_code}`,
    });
  }

  if (latestJob) {
    items.push({
      id: `trace-job-${latestJob.id}`,
      title: "Lote processado",
      detail: `${getIntentTitle(latestJob.intent as AgentIntent)} com ${formatTokenCount(latestJob.selected_message_count)} mensagens na execucao mais recente.`,
      timestamp: latestJob.finished_at ?? latestJob.started_at ?? latestJob.created_at,
      tone: latestJob.status === "failed" ? "error" : latestJob.status === "succeeded" ? "success" : "active",
      meta: `${latestJob.status} • ${latestJob.trigger_source}`,
    });
  }

  if (latestModelRun) {
    items.push({
      id: `trace-model-${latestModelRun.id}`,
      title: "Execucao do motor",
      detail: latestModelRun.success
        ? "O processamento principal terminou e devolveu atualizacoes para memoria, projetos e cofre importante."
        : latestModelRun.error_text || "A execucao mais recente falhou antes de consolidar a resposta final.",
      timestamp: latestModelRun.created_at,
      tone: latestModelRun.success ? "success" : "error",
      meta: latestModelRun.run_type,
    });
  }

  return items.sort((left, right) => {
    const leftTime = left.timestamp ? new Date(left.timestamp).getTime() : 0;
    const rightTime = right.timestamp ? new Date(right.timestamp).getTime() : 0;
    return rightTime - leftTime;
  });
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    if (error.message.includes("Backend indisponivel ou bloqueado na rede/CORS")) {
      return error.message;
    }
    return error.message;
  }
  return "Não foi possível concluir a operação.";
}

function getStepsForIntent(intent: AgentIntent | null, hasEstablishedMemory: boolean): AgentStep[] {
  const resolvedIntent = intent ?? (hasEstablishedMemory ? "improve_memory" : "first_analysis");
  return resolvedIntent === "improve_memory" ? REFINE_STEPS : ANALYZE_STEPS;
}

function makeLog(tone: LogTone, message: string): AgentLog {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    tone,
    createdAt: new Date().toISOString(),
    message,
  };
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
      description: "Pontos que ainda precisam de mais sinal para o retrato ficar mais confiavel.",
      color: "zinc",
    },
  ];
}

function getSnapshotCoverageTone(snapshot: MemorySnapshot | null): "emerald" | "amber" | "indigo" | "zinc" {
  const score = snapshot?.coverage_score ?? 0;
  if (score >= 75) {
    return "emerald";
  }
  if (score >= 55) {
    return "indigo";
  }
  if (score >= 30) {
    return "amber";
  }
  return "zinc";
}

function getSnapshotCoverageLabel(snapshot: MemorySnapshot | null): string {
  const score = snapshot?.coverage_score ?? 0;
  if (score >= 75) {
    return "Cobertura ampla do bootstrap";
  }
  if (score >= 55) {
    return "Cobertura boa para uma base inicial";
  }
  if (score >= 30) {
    return "Cobertura parcial, ainda melhorando";
  }
  return "Cobertura ainda muito curta";
}

function formatSnapshotDirectionMix(snapshot: MemorySnapshot | null): string {
  if (!snapshot) {
    return "0 enviadas / 0 recebidas";
  }
  return `${formatTokenCount(snapshot.outbound_message_count)} enviadas / ${formatTokenCount(snapshot.inbound_message_count)} recebidas`;
}

function resolveOverviewNextAction(args: {
  status: ObserverStatus | null;
  memoryStatus: MemoryStatus | null;
  latestSnapshot: MemorySnapshot | null;
}): {
  title: string;
  detail: string;
  buttonLabel: string;
  target: "observer" | "memory" | "chat" | "activity";
  tone: "emerald" | "amber" | "indigo" | "zinc";
  badge: string;
} {
  const { status, memoryStatus, latestSnapshot } = args;
  const pendingMessages = memoryStatus?.new_messages_after_first_analysis ?? 0;
  if (!status?.connected) {
    return {
      title: "Conectar o observador primeiro",
      detail: "Sem uma sessao ativa no WhatsApp, o sistema ainda nao consegue captar historico, contar mensagens novas nem preparar a primeira leitura.",
      buttonLabel: "Abrir Observador",
      target: "observer",
      tone: "amber",
      badge: "bloqueado",
    };
  }

  if (memoryStatus?.current_job) {
    return {
      title: memoryStatus.current_job.intent === "first_analysis" ? "Acompanhar a primeira leitura" : "Acompanhar a atualizacao em fila",
      detail: memoryStatus.current_job.intent === "first_analysis"
        ? "O pipeline ja esta montando a base inicial do dono. A aba de atividade mostra cada etapa sem precisar recarregar a pagina."
        : "Existe uma atualizacao de memoria em fila ou em andamento. Vale acompanhar o pipeline antes de disparar outra acao.",
      buttonLabel: "Abrir Atividade",
      target: "activity",
      tone: "indigo",
      badge: formatState(memoryStatus.current_job.status),
    };
  }

  if (!memoryStatus?.has_initial_analysis) {
    if (pendingMessages <= 0) {
      return {
        title: "Aguardar mensagens textuais uteis",
        detail: "O observador ja esta pronto, mas ainda nao ha sinais suficientes para criar uma base inicial confiavel. Deixe novas conversas chegarem primeiro.",
        buttonLabel: "Abrir Observador",
        target: "observer",
        tone: "zinc",
        badge: "coletando",
      };
    }

    return {
      title: "Criar a memoria inicial agora",
      detail: `Ja existem ${formatTokenCount(pendingMessages)} mensagens prontas para o bootstrap. Esta e a hora de montar a primeira base consolidada do dono.`,
      buttonLabel: "Abrir Memoria",
      target: "memory",
      tone: "emerald",
      badge: "pronto",
    };
  }

  if (pendingMessages > 0) {
    return {
      title: "Rodar a proxima atualizacao",
      detail: `A base inicial ja existe e ha ${formatTokenCount(pendingMessages)} mensagens novas aguardando consolidacao incremental.`,
      buttonLabel: "Abrir Memoria",
      target: "memory",
      tone: "indigo",
      badge: "lote novo",
    };
  }

  if (latestSnapshot) {
    return {
      title: "Usar a base no chat pessoal",
      detail: "Nao ha lote pendente agora. O melhor proximo passo e explorar a memoria consolidada no chat ou acompanhar a atividade ate o proximo sync.",
      buttonLabel: "Abrir Chat",
      target: "chat",
      tone: "emerald",
      badge: "estavel",
    };
  }

  return {
    title: "Revisar a atividade recente",
    detail: "A base ainda esta curta, mas o sistema ja tem sinais operacionais. A aba de atividade mostra o que foi sincronizado e o que falta consolidar.",
    buttonLabel: "Abrir Atividade",
    target: "activity",
    tone: "indigo",
    badge: "monitorando",
  };
}

function getProjectStrength(project: ProjectMemory): number {
  const raw = 30 + (project.next_steps.length * 10) + (project.evidence.length * 7) + (project.status ? 8 : 0);
  return Math.max(24, Math.min(100, raw));
}

function isProjectManuallyCompleted(project: ProjectMemory): boolean {
  return project.completion_source === "manual" && Boolean(project.manual_completed_at);
}

function getProjectStatusLabel(project: ProjectMemory): string {
  if (isProjectManuallyCompleted(project)) {
    return "Concluido manualmente";
  }
  return project.status || "Em progresso";
}

function getProjectStatusTone(project: ProjectMemory): "emerald" | "amber" | "indigo" | "zinc" {
  if (isProjectManuallyCompleted(project)) {
    return "indigo";
  }
  const normalizedStatus = project.status.toLowerCase();
  if (normalizedStatus.includes("trav") || normalizedStatus.includes("risco") || normalizedStatus.includes("bloq")) {
    return "amber";
  }
  if (normalizedStatus.includes("concl")) {
    return "indigo";
  }
  if (normalizedStatus.includes("ativo") || normalizedStatus.includes("andamento") || normalizedStatus.includes("progres")) {
    return "emerald";
  }
  return "zinc";
}

function normalizeProjectSearchText(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function getAudienceLabel(project: ProjectMemory): string {
  if (project.built_for.trim()) {
    return project.built_for;
  }
  return "Público ainda não consolidado";
}

function normalizeRelationType(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase();
  if (!normalized) {
    return "unknown";
  }
  if (["partner", "family", "friend", "work", "client", "service", "acquaintance", "other", "unknown"].includes(normalized)) {
    return normalized;
  }
  return "unknown";
}

function getRelationTypeLabel(value: string | null | undefined): string {
  const type = normalizeRelationType(value);
  if (type === "partner") return "Par romântico";
  if (type === "family") return "Família";
  if (type === "friend") return "Amizade";
  if (type === "work") return "Trabalho";
  if (type === "client") return "Cliente";
  if (type === "service") return "Serviço";
  if (type === "acquaintance") return "Conhecido";
  if (type === "other") return "Outro";
  return "Não classificado";
}

function getRelationTone(value: string | null | undefined): "rose" | "emerald" | "amber" | "indigo" | "zinc" {
  const type = normalizeRelationType(value);
  if (type === "partner") return "rose";
  if (type === "family") return "emerald";
  if (type === "friend") return "indigo";
  if (type === "work" || type === "client") return "amber";
  return "zinc";
}

function getRelationStrength(relation: PersonRelation): number {
  const raw =
    24
    + (relation.profile_summary ? 16 : 0)
    + (relation.relationship_summary ? 14 : 0)
    + (normalizeRelationType(relation.relationship_type) !== "unknown" ? 10 : 0)
    + (relation.salient_facts.length * 7)
    + (relation.open_loops.length * 7)
    + (relation.recent_topics.length * 5);
  return Math.max(20, Math.min(100, raw));
}

function getRelationSortPriority(value: string | null | undefined): number {
  const type = normalizeRelationType(value);
  if (type === "partner") return 1;
  if (type === "family") return 2;
  if (type === "friend") return 3;
  if (type === "work") return 4;
  if (type === "client") return 5;
  if (type === "service") return 6;
  if (type === "acquaintance") return 7;
  if (type === "other") return 8;
  return 9;
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
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <section 
      className={`neo-card ${className}`} 
      onClick={onClick}
      style={onClick ? { cursor: "pointer" } : undefined}
    >
      {children}
    </section>
  );
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

// ── Smart context builder ──────────────────────────────────────────────────────
// Scores important messages, projects, snapshots and memory by relevance to the
// user's question. Picks the best items across all sources while keeping the
// payload short and focused.
// Does not include raw WhatsApp messages.

const PT_STOPWORDS = new Set([
  "a", "o", "e", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
  "um", "uma", "uns", "umas", "por", "para", "com", "sem", "que", "se", "eu",
  "ele", "ela", "eles", "elas", "voce", "meu", "minha", "meus", "minhas", "seu",
  "sua", "seus", "suas", "como", "qual", "quais", "onde", "quando", "foi", "ser",
  "ter", "tem", "esta", "isso", "nao", "sim", "mais", "muito", "tambem", "ja",
  "ainda", "ai", "aqui", "ate", "sobre", "entre", "esse", "essa", "este",
  "esses", "essas", "porque", "pra", "pro", "mas", "ou", "ao", "aos",
  "me", "te", "lhe", "vos", "lhes", "oi", "ola",
]);

function extractKeywords(text: string): string[] {
  const normalized = text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ");
  return normalized
    .split(/\s+/)
    .filter((word) => word.length >= 2 && !PT_STOPWORDS.has(word));
}

function scoreByKeywords(text: string, keywords: string[]): number {
  if (keywords.length === 0) return 0;
  const normalizedText = text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  let hits = 0;
  for (const keyword of keywords) {
    if (normalizedText.includes(keyword)) hits++;
  }
  return hits / keywords.length;
}

function buildSmartContextHint(
  userQuestion: string,
  importantMsgs: ImportantMessage[],
  allProjects: ProjectMemory[],
  allSnapshots: MemorySnapshot[],
  currentMemory: MemoryCurrent | null,
): string | undefined {
  const keywords = extractKeywords(userQuestion);
  if (keywords.length === 0) return undefined;

  const CHAR_BUDGET = 1500;
  const parts: string[] = [];
  let charCount = 0;

  const addPart = (line: string): boolean => {
    if (charCount + line.length + 1 > CHAR_BUDGET) return false;
    parts.push(line);
    charCount += line.length + 1;
    return true;
  };

  // 1) Score important messages
  const scoredMessages = importantMsgs.map((m) => ({
    item: m,
    score: scoreByKeywords(
      `${m.category} ${m.contact_name} ${m.message_text} ${m.importance_reason}`,
      keywords,
    ),
  }));
  scoredMessages.sort((a, b) => b.score - a.score);
  const relevantMessages = scoredMessages.filter((s) => s.score > 0).slice(0, 4);

  // 2) Score projects
  const scoredProjects = allProjects.map((p) => ({
    item: p,
    score: scoreByKeywords(
      `${p.project_name} ${p.summary} ${p.status} ${p.what_is_being_built} ${p.built_for} ${p.next_steps.join(" ")}`,
      keywords,
    ),
  }));
  scoredProjects.sort((a, b) => b.score - a.score);
  const relevantProjects = scoredProjects.filter((s) => s.score > 0).slice(0, 3);

  // 3) Score snapshot learnings, relationships, routines
  type ScoredInsight = { text: string; source: string; score: number };
  const scoredInsights: ScoredInsight[] = [];
  for (const snap of allSnapshots.slice(0, 5)) {
    for (const learning of snap.key_learnings) {
      scoredInsights.push({ text: learning, source: "aprendizado", score: scoreByKeywords(learning, keywords) });
    }
    for (const person of snap.people_and_relationships) {
      scoredInsights.push({ text: person, source: "pessoa", score: scoreByKeywords(person, keywords) });
    }
    for (const routine of snap.routine_signals) {
      scoredInsights.push({ text: routine, source: "rotina", score: scoreByKeywords(routine, keywords) });
    }
  }
  scoredInsights.sort((a, b) => b.score - a.score);
  const relevantInsights = scoredInsights.filter((s) => s.score > 0).slice(0, 4);

  // 4) Check if life summary is relevant
  const memoryScore = currentMemory?.life_summary
    ? scoreByKeywords(currentMemory.life_summary, keywords)
    : 0;

  // Assemble — most relevant first
  if (relevantMessages.length > 0) {
    addPart("Mensagens importantes relacionadas ao pedido:");
    for (const { item: m } of relevantMessages) {
      if (!addPart(`- [${m.category}] ${m.contact_name || "?"}: ${truncateText(m.message_text, 100)}`)) break;
    }
  }

  if (relevantProjects.length > 0) {
    addPart("Projetos relevantes:");
    for (const { item: p } of relevantProjects) {
      if (!addPart(`- ${p.project_name}: ${truncateText(p.summary, 80)} [${p.status}]`)) break;
      if (p.next_steps.length > 0) addPart(`  Proximos: ${p.next_steps.slice(0, 2).join("; ")}`);
    }
  }

  if (relevantInsights.length > 0) {
    addPart("Sinais recentes relevantes:");
    for (const insight of relevantInsights) {
      if (!addPart(`- [${insight.source}] ${truncateText(insight.text, 100)}`)) break;
    }
  }

  if (memoryScore > 0.15 && currentMemory?.life_summary) {
    addPart("Resumo de vida consolidado (trecho relevante):");
    addPart(truncateText(currentMemory.life_summary, 250));
  }

  return parts.length > 0 ? parts.join("\n") : undefined;
}

export function ConnectionDashboard({
  account,
  onLogout,
}: {
  account: AuthenticatedAccount;
  onLogout: () => void;
}) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const resolvedActiveTab: TabId = activeTab === "activity" ? "memory" : activeTab;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [status, setStatus] = useState<ObserverStatus | null>(null);
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [agentStatus, setAgentStatus] = useState<WhatsAppAgentStatus | null>(null);
  const [agentViewState, setAgentViewState] = useState<ViewState>("idle");
  const [agentSettings, setAgentSettings] = useState<WhatsAppAgentSettings | null>(null);
  const [agentThreads, setAgentThreads] = useState<WhatsAppAgentThread[]>([]);
  const [agentMessages, setAgentMessages] = useState<WhatsAppAgentMessage[]>([]);
  const [agentActiveSession, setAgentActiveSession] = useState<WhatsAppAgentSession | null>(null);
  const [agentContactMemory, setAgentContactMemory] = useState<WhatsAppAgentContactMemory | null>(null);
  const [activeAgentThreadId, setActiveAgentThreadId] = useState<string | null>(null);
  const [memory, setMemory] = useState<MemoryCurrent | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatus | null>(null);
  const [memoryGroups, setMemoryGroups] = useState<WhatsAppGroupSelection[]>([]);
  const [agendaEvents, setAgendaEvents] = useState<AgendaEvent[]>([]);
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [relations, setRelations] = useState<PersonRelation[]>([]);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [importantMessages, setImportantMessages] = useState<ImportantMessage[]>([]);
  const [chatThreads, setChatThreads] = useState<ChatThread[]>([]);
  const [activeChatThreadId, setActiveChatThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [memoryActivity, setMemoryActivity] = useState<MemoryActivity | null>(null);
  const [chatDraft, setChatDraft] = useState("");
  const [queuedJobId, setQueuedJobId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [agentConnectionError, setAgentConnectionError] = useState<string | null>(null);
  const [agentMessagesError, setAgentMessagesError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [memoryGroupsError, setMemoryGroupsError] = useState<string | null>(null);
  const [importantMessagesError, setImportantMessagesError] = useState<string | null>(null);
  const [relationsError, setRelationsError] = useState<string | null>(null);
  const [agendaError, setAgendaError] = useState<string | null>(null);
  const [agendaActionError, setAgendaActionError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [messageRefreshError, setMessageRefreshError] = useState<string | null>(null);
  const [memoryActivityError, setMemoryActivityError] = useState<string | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isAgentConnecting, setIsAgentConnecting] = useState(false);
  const [isAgentResetting, setIsAgentResetting] = useState(false);
  const [isAgentSaving, setIsAgentSaving] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingMessages, setIsRefreshingMessages] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [isLoadingChatThread, setIsLoadingChatThread] = useState(false);
  const [isCreatingChatThread, setIsCreatingChatThread] = useState(false);
  const [deletingChatThreadIds, setDeletingChatThreadIds] = useState<string[]>([]);
  const [isClearingDatabase, setIsClearingDatabase] = useState(false);
  const [savingGroupJids, setSavingGroupJids] = useState<string[]>([]);
  const [savingProjectKeys, setSavingProjectKeys] = useState<string[]>([]);
  const [deletingProjectKeys, setDeletingProjectKeys] = useState<string[]>([]);
  const [editingProjectKeys, setEditingProjectKeys] = useState<string[]>([]);
  const [aiProjectKeys, setAiProjectKeys] = useState<string[]>([]);
  const [savingAgendaIds, setSavingAgendaIds] = useState<string[]>([]);
  const [deletingAgendaIds, setDeletingAgendaIds] = useState<string[]>([]);
  const [projectActionError, setProjectActionError] = useState<string | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [agentPollingEnabled, setAgentPollingEnabled] = useState(false);
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

  const automationStatus = automationStatusPlaceholder(memoryActivity);
  const setAutomationStatus = setMemoryActivity as unknown as React.Dispatch<React.SetStateAction<any>>;
  const automationError = memoryActivityError;
  const setAutomationError = setMemoryActivityError;
  const automationDraft = null;
  const setAutomationDraft = (() => undefined) as React.Dispatch<React.SetStateAction<any>>;
  const isSavingAutomation = false;
  const isTickingAutomation = false;
  const setIsSavingAutomation = (_: boolean) => undefined;
  const setIsTickingAutomation = (_: boolean) => undefined;

  const liveRefreshIntervalMs = useMemo(() => getLiveRefreshInterval(activeTab), [activeTab]);
  const lastQrRefreshAtRef = useRef<number | null>(null);
  const lastAgentQrRefreshAtRef = useRef<number | null>(null);
  const lastAttentionRefreshAtRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const observerStatusInFlightRef = useRef(false);
  const agentStatusInFlightRef = useRef(false);
  const dashboardRefreshInFlightRef = useRef(false);
  const liveSummaryInFlightRef = useRef(false);
  const liveMemorySummaryRef = useRef<MemoryLiveSummary | null>(null);
  const lastObservedSyncRef = useRef<string | null>(null);
  const lastObservedJobRef = useRef<string | null>(null);
  const lastObservedModelRunRef = useRef<string | null>(null);
  const heavyResourceRefreshedAtRef = useRef<Record<HeavyLiveResourceKey, number>>({
    groups: 0,
    projects: 0,
    snapshots: 0,
    important: 0,
    relations: 0,
  });
  const pollStatusRef = useRef<((announceTransition?: boolean) => Promise<void>) | null>(null);
  const pollAgentStatusRef = useRef<((announceTransition?: boolean) => Promise<void>) | null>(null);
  const refreshLiveDataRef = useRef<(() => Promise<void>) | null>(null);

  const latestSnapshot = snapshots[0] ?? null;
  const memoryIsEstablished = memoryStatus?.has_initial_analysis ?? false;
  const currentMemoryJob = memoryStatus?.current_job ?? null;
  const memoryJobIsPending = currentMemoryJob?.status === "queued" || currentMemoryJob?.status === "running";
  const displayAgentState = useMemo<DisplayAgentState>(() => {
    const pendingJob = resolvePendingAnalysisJob({
      currentJob: currentMemoryJob,
      activity: memoryActivity,
      queuedJobId,
    });
    const resolvedIntent = (pendingJob?.intent as AgentIntent | undefined) ?? agentState.intent ?? (memoryIsEstablished ? "improve_memory" : "first_analysis");
    const syncRun = resolveRelatedSyncRun(memoryActivity, pendingJob);
    const modelRun = resolveRelatedModelRun(memoryActivity, pendingJob);
    const stageIndex = resolveLiveStageIndex(resolvedIntent, pendingJob, syncRun);

    if (pendingJob) {
      return {
        mode: "analyze",
        intent: resolvedIntent,
        running: true,
        progress: resolveLiveProgress(resolvedIntent, pendingJob, syncRun),
        status: resolveLiveStatus({
          intent: resolvedIntent,
          job: pendingJob,
          syncRun,
          modelRun,
        }),
        error: null,
        completedAt: null,
        stageIndex,
        badgeTone: "teal",
      };
    }

    if (syncRun?.status === "running") {
      return {
        ...agentState,
        mode: "idle",
        intent: agentState.intent ?? resolvedIntent,
        running: false,
        progress: 0,
        status: resolveLiveStatus({
          intent: resolvedIntent,
          job: null,
          syncRun,
          modelRun,
        }),
        error: null,
        completedAt: null,
        stageIndex: null,
        badgeTone: "teal",
      };
    }

    return {
      ...agentState,
      intent: agentState.intent ?? resolvedIntent,
      stageIndex: null,
      badgeTone: agentState.error ? "amber" : agentState.progress >= 100 ? "emerald" : "zinc",
    };
  }, [agentState, currentMemoryJob, memoryActivity, memoryIsEstablished, queuedJobId]);
  const analysisIsBusy = memoryJobIsPending || queuedJobId !== null || displayAgentState.running;
  const activeChatThread = useMemo(
    () => chatThreads.find((thread) => thread.id === activeChatThreadId) ?? chatThreads[0] ?? null,
    [activeChatThreadId, chatThreads],
  );

  const statusLabel = useMemo(() => {
    if (!status) {
      return "Pronto para iniciar";
    }
    return status.connected ? "Online" : formatState(status.state);
  }, [status]);

  const agentStatusLabel = useMemo(() => {
    if (!agentStatus) {
      return "Pronto para iniciar";
    }
    return agentStatus.connected ? "Online" : formatState(agentStatus.state);
  }, [agentStatus]);
  const observerStatusIntervalMs = useMemo(
    () => ((pollingEnabled || !status?.connected) ? CONNECTING_STATUS_POLL_INTERVAL_MS : LIVE_STATUS_POLL_INTERVAL_MS),
    [pollingEnabled, status?.connected],
  );
  const agentStatusIntervalMs = useMemo(
    () => ((agentPollingEnabled || !agentStatus?.connected) ? CONNECTING_STATUS_POLL_INTERVAL_MS : LIVE_STATUS_POLL_INTERVAL_MS),
    [agentPollingEnabled, agentStatus?.connected],
  );

  const currentSteps = useMemo(
    () => getStepsForIntent(displayAgentState.intent, memoryIsEstablished),
    [displayAgentState.intent, memoryIsEstablished],
  );
  const insightMetrics = useMemo(() => getSignalMetrics(latestSnapshot), [latestSnapshot]);
  const persistedActivityLogs = useMemo(() => buildPersistedActivityLogs(memoryActivity), [memoryActivity]);
  const activityLogs = useMemo(
    () =>
      [...persistedActivityLogs, ...agentLogs]
        .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())
        .slice(0, 28),
    [agentLogs, persistedActivityLogs],
  );

  function markHeavyResourceRefreshed(resource: HeavyLiveResourceKey): void {
    heavyResourceRefreshedAtRef.current[resource] = Date.now();
  }

  function shouldRefreshHeavyResource(resource: HeavyLiveResourceKey, busy = false): boolean {
    const lastRefreshedAt = heavyResourceRefreshedAtRef.current[resource] ?? 0;
    const minInterval = busy
      ? BUSY_HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS[resource]
      : HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS[resource];

    return !lastRefreshedAt || Date.now() - lastRefreshedAt >= minInterval;
  }

  async function refreshMemoryArtifactsAfterJob(): Promise<void> {
    const [memoryResult, projectsResult, relationsResult, memoryStatusResult, snapshotsResult, importantMessagesResult, memoryActivityResult, groupsResult] =
      await Promise.allSettled([
        getCurrentMemory(),
        getMemoryProjects(),
        getMemoryRelations(),
        getMemoryStatus(),
        getMemorySnapshots(6),
        getImportantMessages(80),
        getMemoryActivity(),
        getMemoryGroups(),
      ]);

    startTransition(() => {
      if (memoryResult.status === "fulfilled") {
        setMemory(memoryResult.value);
      }
      if (projectsResult.status === "fulfilled") {
        setProjects(projectsResult.value);
        markHeavyResourceRefreshed("projects");
      }
      if (relationsResult.status === "fulfilled") {
        setRelations(relationsResult.value);
        setRelationsError(null);
        markHeavyResourceRefreshed("relations");
      }
      if (memoryStatusResult.status === "fulfilled") {
        setMemoryStatus(memoryStatusResult.value);
      }
      if (snapshotsResult.status === "fulfilled") {
        setSnapshots(snapshotsResult.value);
        markHeavyResourceRefreshed("snapshots");
      }
      if (importantMessagesResult.status === "fulfilled") {
        setImportantMessages(importantMessagesResult.value);
        markHeavyResourceRefreshed("important");
      }
      if (memoryActivityResult.status === "fulfilled") {
        setMemoryActivity(memoryActivityResult.value);
        setMemoryActivityError(null);
      }
      if (groupsResult.status === "fulfilled") {
        setMemoryGroups(groupsResult.value);
        setMemoryGroupsError(null);
        markHeavyResourceRefreshed("groups");
      }
    });
  }

  async function refreshFromLiveSummary(): Promise<void> {
    if (isHydrating || liveSummaryInFlightRef.current || !isDocumentVisible()) {
      return;
    }

    liveSummaryInFlightRef.current = true;
    try {
      const nextSummary = await getMemoryLiveSummary();
      const previousSummary = liveMemorySummaryRef.current;
      liveMemorySummaryRef.current = nextSummary;

      if (!previousSummary) {
        return;
      }

      const shouldRefreshMemoryCore = previousSummary.memory_signature !== nextSummary.memory_signature;
      const shouldRefreshActivity = previousSummary.activity_signature !== nextSummary.activity_signature;
      const shouldRefreshImportant = previousSummary.important_signature !== nextSummary.important_signature;
      const shouldRefreshProjects = previousSummary.projects_signature !== nextSummary.projects_signature;
      const shouldRefreshRelations = previousSummary.relations_signature !== nextSummary.relations_signature;

      if (!shouldRefreshMemoryCore && !shouldRefreshActivity && !shouldRefreshImportant && !shouldRefreshProjects && !shouldRefreshRelations) {
        return;
      }

      const [memoryResult, memoryStatusResult, snapshotsResult, memoryActivityResult, importantMessagesResult, projectsResult, relationsResult] =
        await Promise.allSettled([
          shouldRefreshMemoryCore ? getCurrentMemory() : Promise.resolve(null),
          shouldRefreshMemoryCore ? getMemoryStatus() : Promise.resolve(null),
          shouldRefreshMemoryCore ? getMemorySnapshots(6) : Promise.resolve(null),
          shouldRefreshActivity ? getMemoryActivity() : Promise.resolve(null),
          shouldRefreshImportant ? getImportantMessages(80) : Promise.resolve(null),
          shouldRefreshProjects ? getMemoryProjects() : Promise.resolve(null),
          shouldRefreshRelations ? getMemoryRelations() : Promise.resolve(null),
        ]);

      startTransition(() => {
        if (memoryResult.status === "fulfilled" && memoryResult.value) {
          setMemory(memoryResult.value);
          setMemoryError(null);
        }
        if (memoryStatusResult.status === "fulfilled" && memoryStatusResult.value) {
          setMemoryStatus(memoryStatusResult.value);
        }
        if (snapshotsResult.status === "fulfilled" && snapshotsResult.value) {
          setSnapshots(snapshotsResult.value);
          markHeavyResourceRefreshed("snapshots");
        }
        if (memoryActivityResult.status === "fulfilled" && memoryActivityResult.value) {
          setMemoryActivity(memoryActivityResult.value);
          setMemoryActivityError(null);
          syncQueuedJobFromAutomationSnapshot(memoryActivityResult.value);
        }
        if (importantMessagesResult.status === "fulfilled" && importantMessagesResult.value) {
          setImportantMessages(importantMessagesResult.value);
          setImportantMessagesError(null);
          markHeavyResourceRefreshed("important");
        }
        if (projectsResult.status === "fulfilled" && projectsResult.value) {
          setProjects(projectsResult.value);
          markHeavyResourceRefreshed("projects");
        }
        if (relationsResult.status === "fulfilled" && relationsResult.value) {
          setRelations(relationsResult.value);
          setRelationsError(null);
          markHeavyResourceRefreshed("relations");
        }
      });
    } catch {
      // Ignore digest failures and let the regular polling path keep the dashboard alive.
    } finally {
      liveSummaryInFlightRef.current = false;
    }
  }

  async function toggleGroupSelection(chatJid: string, enabledForAnalysis: boolean): Promise<void> {
    setSavingGroupJids((current) => (current.includes(chatJid) ? current : [...current, chatJid]));
    setMemoryGroups((current) =>
      current.map((group) => (
        group.chat_jid === chatJid ? { ...group, enabled_for_analysis: enabledForAnalysis } : group
      )),
    );
    setMemoryGroupsError(null);
    try {
      const updated = await updateMemoryGroupSelection(chatJid, enabledForAnalysis);
      setMemoryGroups((current) => current.map((group) => (group.chat_jid === chatJid ? updated : group)));
    } catch (error) {
      setMemoryGroups((current) =>
        current.map((group) => (
          group.chat_jid === chatJid ? { ...group, enabled_for_analysis: !enabledForAnalysis } : group
        )),
      );
      setMemoryGroupsError(getErrorMessage(error));
    } finally {
      setSavingGroupJids((current) => current.filter((value) => value !== chatJid));
    }
  }

  async function toggleProjectCompletion(project: ProjectMemory, completed: boolean): Promise<void> {
    const projectKey = project.project_key;
    setSavingProjectKeys((current) => (current.includes(projectKey) ? current : [...current, projectKey]));
    setProjectActionError(null);

    const optimisticProject: ProjectMemory = completed
      ? {
          ...project,
          status: "Concluido",
          completion_source: "manual",
          manual_completed_at: new Date().toISOString(),
          manual_completion_notes: project.manual_completion_notes,
          next_steps: [],
          updated_at: new Date().toISOString(),
        }
      : {
          ...project,
          status: "Em andamento",
          completion_source: "",
          manual_completed_at: null,
          manual_completion_notes: "",
          updated_at: new Date().toISOString(),
        };

    startTransition(() => {
      setProjects((current) => current.map((item) => (item.project_key === projectKey ? optimisticProject : item)));
    });

    try {
      const updated = await updateMemoryProjectCompletion(projectKey, { completed });
      startTransition(() => {
        setProjects((current) => current.map((item) => (item.project_key === projectKey ? updated : item)));
      });
      markHeavyResourceRefreshed("projects");
      pushAgentLog(
        "success",
        completed
          ? `Projeto ${updated.project_name} marcado como concluido manualmente. Esse sinal entra nas proximas atualizacoes de memoria.`
          : `Projeto ${updated.project_name} reaberto manualmente. O painel voltou a trata-lo como frente ativa.`,
      );
    } catch (error) {
      startTransition(() => {
        setProjects((current) => current.map((item) => (item.project_key === projectKey ? project : item)));
      });
      const message = getErrorMessage(error);
      setProjectActionError(message);
      pushAgentLog("error", `Falha ao atualizar o projeto ${project.project_name}: ${message}`);
    } finally {
      setSavingProjectKeys((current) => current.filter((value) => value !== projectKey));
    }
  }

  async function removeProject(project: ProjectMemory): Promise<void> {
    const projectKey = project.project_key;
    const confirmed = window.confirm(`Excluir o projeto "${project.project_name}" do cofre de projetos?`);
    if (!confirmed) {
      return;
    }

    setDeletingProjectKeys((current) => (current.includes(projectKey) ? current : [...current, projectKey]));
    setProjectActionError(null);
    const previousProjects = projects;
    startTransition(() => {
      setProjects((current) => current.filter((item) => item.project_key !== projectKey));
    });

    try {
      await deleteMemoryProject(projectKey);
      markHeavyResourceRefreshed("projects");
      pushAgentLog("success", `Projeto ${project.project_name} removido do cofre de projetos.`);
    } catch (error) {
      startTransition(() => {
        setProjects(previousProjects);
      });
      const message = getErrorMessage(error);
      setProjectActionError(message);
      pushAgentLog("error", `Falha ao excluir o projeto ${project.project_name}: ${message}`);
    } finally {
      setDeletingProjectKeys((current) => current.filter((value) => value !== projectKey));
    }
  }

  async function saveRelationEdits(
    contactName: string,
    input: { contact_name?: string; relationship_type?: string }
  ): Promise<void> {
    try {
      const updated = await updateMemoryRelation(contactName, input);
      setRelations((current) => current.map((item) => (item.id === updated.id || item.contact_name === contactName ? updated : item)));
      toast.success("Relação atualizada!");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function saveAgendaEdits(event: AgendaEvent, input: UpdateAgendaEventInput): Promise<AgendaEvent> {
    setSavingAgendaIds((current) => (current.includes(event.id) ? current : [...current, event.id]));
    setAgendaActionError(null);
    try {
      const updated = await updateAgendaEvent(event.id, input);
      startTransition(() => {
        setAgendaEvents((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      });
      pushAgentLog("success", `Compromisso ${updated.titulo} atualizado manualmente na agenda.`);
      return updated;
    } catch (error) {
      const message = getErrorMessage(error);
      setAgendaActionError(message);
      pushAgentLog("error", `Falha ao editar o compromisso ${event.titulo}: ${message}`);
      throw error;
    } finally {
      setSavingAgendaIds((current) => current.filter((value) => value !== event.id));
    }
  }

  async function removeAgendaEvent(event: AgendaEvent): Promise<void> {
    const confirmed = window.confirm(`Excluir o compromisso "${event.titulo}" da agenda?`);
    if (!confirmed) {
      return;
    }

    setDeletingAgendaIds((current) => (current.includes(event.id) ? current : [...current, event.id]));
    setAgendaActionError(null);
    const previousEvents = agendaEvents;
    startTransition(() => {
      setAgendaEvents((current) => current.filter((item) => item.id !== event.id));
    });

    try {
      await deleteAgendaEvent(event.id);
      pushAgentLog("success", `Compromisso ${event.titulo} removido da agenda.`);
    } catch (error) {
      startTransition(() => {
        setAgendaEvents(previousEvents);
      });
      const message = getErrorMessage(error);
      setAgendaActionError(message);
      pushAgentLog("error", `Falha ao excluir o compromisso ${event.titulo}: ${message}`);
    } finally {
      setDeletingAgendaIds((current) => current.filter((value) => value !== event.id));
    }
  }

  async function saveProjectEdits(
    project: ProjectMemory,
    input: {
      project_name: string;
      summary: string;
      status: string;
      what_is_being_built: string;
      built_for: string;
      next_steps: string[];
      evidence: string[];
    },
  ): Promise<ProjectMemory> {
    const projectKey = project.project_key;
    setEditingProjectKeys((current) => (current.includes(projectKey) ? current : [...current, projectKey]));
    setProjectActionError(null);
    try {
      const updated = await updateMemoryProject(projectKey, input);
      startTransition(() => {
        setProjects((current) => current.map((item) => (item.id === updated.id || item.project_key === projectKey ? updated : item)));
      });
      markHeavyResourceRefreshed("projects");
      pushAgentLog("success", `Projeto ${updated.project_name} atualizado manualmente.`);
      return updated;
    } catch (error) {
      const message = getErrorMessage(error);
      setProjectActionError(message);
      pushAgentLog("error", `Falha ao editar o projeto ${project.project_name}: ${message}`);
      throw error;
    } finally {
      setEditingProjectKeys((current) => current.filter((value) => value !== projectKey));
    }
  }

  async function assistProjectEdit(project: ProjectMemory, instruction: string): Promise<{ project: ProjectMemory; assistant_message: string }> {
    const projectKey = project.project_key;
    setAiProjectKeys((current) => (current.includes(projectKey) ? current : [...current, projectKey]));
    setProjectActionError(null);
    try {
      const response = await assistMemoryProjectEdit(projectKey, instruction);
      startTransition(() => {
        setProjects((current) => current.map((item) => (item.id === response.project.id || item.project_key === projectKey ? response.project : item)));
      });
      markHeavyResourceRefreshed("projects");
      pushAgentLog("success", `IA aplicou ajustes no projeto ${response.project.project_name}.`);
      return response;
    } catch (error) {
      const message = getErrorMessage(error);
      setProjectActionError(message);
      pushAgentLog("error", `Falha na edicao assistida do projeto ${project.project_name}: ${message}`);
      throw error;
    } finally {
      setAiProjectKeys((current) => current.filter((value) => value !== projectKey));
    }
  }

  function syncQueuedJobFromAutomationSnapshot(snapshot: MemoryActivity): void {
    const pendingJob = snapshot.jobs.find((job) => job.status === "queued" || job.status === "running");

    if (!queuedJobId) {
      if (pendingJob) {
        const resolvedIntent = pendingJob.intent as AgentIntent;
        if (!agentState.running || agentState.intent !== resolvedIntent) {
          startAgentRun(resolvedIntent);
          pushAgentLog(
            "info",
            pendingJob.status === "queued"
              ? `${getIntentTitle(resolvedIntent)} automatica detectada na fila do backend. Sincronizando o andamento no painel...`
              : `${getIntentTitle(resolvedIntent)} automatica detectada em execucao no backend. Sincronizando o andamento no painel...`,
          );
        }
        setQueuedJobId(pendingJob.id);
      }
      return;
    }

    const matchingJob = snapshot.jobs.find((job) => job.id === queuedJobId);
    if (!matchingJob) {
      if (!pendingJob) {
        setQueuedJobId(null);
      }
      return;
    }

    if (matchingJob.status === "queued" || matchingJob.status === "running") {
      return;
    }

    setQueuedJobId(null);
    const resolvedIntent = (agentState.intent ?? matchingJob.intent) as AgentIntent;

    if (matchingJob.status === "succeeded") {
      void refreshMemoryArtifactsAfterJob();
      finishAgentRunSuccess(
        resolvedIntent,
        resolvedIntent === "first_analysis"
          ? "Primeira analise concluida. A base inicial do dono foi criada."
          : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado.",
      );
      return;
    }

    if (matchingJob.status === "failed") {
      finishAgentRunError(
        resolvedIntent,
        matchingJob.error_text || "Ocorreu um erro desconhecido durante a análise.",
      );
    }
  }

  function applyObserverStatus(nextStatus: ObserverStatus, announceTransition = true): void {
    const wasConnected = status?.connected ?? false;
    startTransition(() => {
      setStatus((previous) => mergeStatus(previous, nextStatus));
      setPollingEnabled(!nextStatus.connected);
      setViewState(nextStatus.connected ? "connected" : "waiting");
      setConnectionError(null);
    });

    if (announceTransition && nextStatus.connected && !wasConnected) {
      pushAgentLog("success", "Observador conectado. Diretas ja entram na memoria; grupos ficam opt-in na aba Grupos.");
    }
  }

  function applyAgentStatus(nextStatus: WhatsAppAgentStatus, announceTransition = true): void {
    const wasConnected = agentStatus?.connected ?? false;
    startTransition(() => {
      setAgentStatus(nextStatus);
      setAgentPollingEnabled(!nextStatus.connected);
      setAgentViewState(nextStatus.connected ? "connected" : "waiting");
      setAgentConnectionError(null);
    });

    if (announceTransition && nextStatus.connected && !wasConnected) {
      pushAgentLog("success", "WhatsApp agente conectado. Respostas automaticas podem ser ativadas.");
    }
  }

  async function pollStatus(announceTransition = true): Promise<void> {
    if (observerStatusInFlightRef.current || isSubmitting || isResetting) {
      return;
    }

    observerStatusInFlightRef.current = true;
    try {
      const shouldRefreshQr = !status?.connected && Boolean(status?.qr_code) && (
        !lastQrRefreshAtRef.current ||
        Date.now() - lastQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS
      );
      const nextStatus = await getObserverStatus(shouldRefreshQr);

      if (shouldRefreshQr) {
        lastQrRefreshAtRef.current = Date.now();
      }

      applyObserverStatus(nextStatus, announceTransition);
    } catch (error) {
      const message = getErrorMessage(error);
      startTransition(() => {
        setConnectionError(message);
        if (!status) {
          setViewState("error");
        }
      });
    } finally {
      observerStatusInFlightRef.current = false;
    }
  }

  async function pollAgentStatus(announceTransition = true): Promise<void> {
    if (agentStatusInFlightRef.current || isAgentConnecting || isAgentResetting) {
      return;
    }

    agentStatusInFlightRef.current = true;
    try {
      const shouldRefreshQr = !agentStatus?.connected && Boolean(agentStatus?.qr_code) && (
        !lastAgentQrRefreshAtRef.current ||
        Date.now() - lastAgentQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS
      );
      const nextStatus = shouldRefreshQr ? await connectAgent() : await getAgentStatus();

      if (shouldRefreshQr) {
        lastAgentQrRefreshAtRef.current = Date.now();
      }

      applyAgentStatus(nextStatus, announceTransition);
    } catch (error) {
      const message = getErrorMessage(error);
      startTransition(() => {
        setAgentConnectionError(message);
        if (!agentStatus) {
          setAgentViewState("error");
        }
      });
    } finally {
      agentStatusInFlightRef.current = false;
    }
  }

  async function refreshLiveData(): Promise<void> {
    if (dashboardRefreshInFlightRef.current || isRefreshing || isRefreshingMessages || !isDocumentVisible()) {
      return;
    }

    const shouldRefreshChatWorkspace = (
      activeTab === "manual" ||
      activeTab === "chat"
    ) && !isLoadingChatThread && !isCreatingChatThread && !isSendingChat && streamingText === null;
    const shouldRefreshAgentWorkspace = false;
    const shouldRefreshMemoryCurrent = (
      resolvedActiveTab === "overview" ||
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "memory"
    );
    const shouldRefreshProjects = (
      resolvedActiveTab === "projects" ||
      resolvedActiveTab === "manual" ||
      (resolvedActiveTab === "overview" && analysisIsBusy)
    ) && shouldRefreshHeavyResource("projects", analysisIsBusy);
    const shouldRefreshRelations = (
      resolvedActiveTab === "relations" ||
      resolvedActiveTab === "manual"
    ) && shouldRefreshHeavyResource("relations", analysisIsBusy);
    const shouldRefreshAgenda = resolvedActiveTab === "agenda";
    const shouldRefreshMemoryStatus = (
      resolvedActiveTab === "overview" ||
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "observer" ||
      resolvedActiveTab === "memory" ||
      resolvedActiveTab === "automation"
    );
    const shouldRefreshSnapshots = (
      resolvedActiveTab === "memory" ||
      resolvedActiveTab === "manual" ||
      (resolvedActiveTab === "overview" && analysisIsBusy)
    ) && shouldRefreshHeavyResource("snapshots", analysisIsBusy);
    const shouldRefreshImportantMessages = (
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "important"
    ) && shouldRefreshHeavyResource("important", analysisIsBusy);
    const shouldRefreshAutomation = !isTickingAutomation && (
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "memory" ||
      resolvedActiveTab === "automation" ||
      queuedJobId !== null
    );
    const shouldRefreshHeavyGroups = shouldRefreshHeavyResource("groups", analysisIsBusy);
    const shouldRefreshMemoryGroups = (resolvedActiveTab === "manual" || resolvedActiveTab === "groups") && shouldRefreshHeavyGroups;

    dashboardRefreshInFlightRef.current = true;
    try {
      const [
        agentWorkspaceResult,
        chatWorkspaceResult,
        memoryResult,
        memoryGroupsResult,
        agendaResult,
        projectsResult,
        relationsResult,
        memoryStatusResult,
        snapshotsResult,
        importantMessagesResult,
        automationResult,
      ] = await Promise.allSettled([
        shouldRefreshAgentWorkspace ? getAgentWorkspace(activeAgentThreadId ?? undefined) : Promise.resolve(null),
        shouldRefreshChatWorkspace ? getChatWorkspace(activeChatThreadId ?? undefined) : Promise.resolve(null),
        shouldRefreshMemoryCurrent ? getCurrentMemory() : Promise.resolve(null),
        shouldRefreshMemoryGroups ? getMemoryGroups() : Promise.resolve(null),
        shouldRefreshAgenda ? getAgendaEvents(120, false) : Promise.resolve(null),
        shouldRefreshProjects ? getMemoryProjects() : Promise.resolve(null),
        shouldRefreshRelations ? getMemoryRelations() : Promise.resolve(null),
        shouldRefreshMemoryStatus ? getMemoryStatus() : Promise.resolve(null),
        shouldRefreshSnapshots ? getMemorySnapshots(resolvedActiveTab === "overview" ? 1 : 6) : Promise.resolve(null),
        shouldRefreshImportantMessages ? getImportantMessages(80) : Promise.resolve(null),
        shouldRefreshAutomation ? getAutomationStatus() : Promise.resolve(null),
      ]);

      if (agentWorkspaceResult.status === "fulfilled" && agentWorkspaceResult.value) {
        const nextAgentWorkspace = agentWorkspaceResult.value;
        startTransition(() => {
          applyAgentWorkspace(nextAgentWorkspace);
        });
      } else if (agentWorkspaceResult.status === "rejected" && shouldRefreshAgentWorkspace) {
        setAgentConnectionError(getErrorMessage(agentWorkspaceResult.reason));
      }

      if (chatWorkspaceResult.status === "fulfilled" && chatWorkspaceResult.value) {
        const nextChatWorkspace = chatWorkspaceResult.value;
        startTransition(() => {
          applyChatWorkspace(nextChatWorkspace);
        });
      } else if (chatWorkspaceResult.status === "rejected" && shouldRefreshChatWorkspace) {
        setChatError(getErrorMessage(chatWorkspaceResult.reason));
      }

      if (memoryResult.status === "fulfilled" && memoryResult.value) {
        const nextMemory = memoryResult.value;
        startTransition(() => {
          setMemory(nextMemory);
          setMemoryError(null);
        });
      }

      if (memoryGroupsResult.status === "fulfilled" && Array.isArray(memoryGroupsResult.value)) {
        const nextGroups = memoryGroupsResult.value;
        startTransition(() => {
          setMemoryGroups(nextGroups);
          setMemoryGroupsError(null);
        });
        markHeavyResourceRefreshed("groups");
      } else if (memoryGroupsResult.status === "rejected" && shouldRefreshMemoryGroups) {
        setMemoryGroupsError(getErrorMessage(memoryGroupsResult.reason));
      }

      if (agendaResult.status === "fulfilled" && Array.isArray(agendaResult.value)) {
        const nextAgenda = agendaResult.value;
        startTransition(() => {
          setAgendaEvents(nextAgenda);
          setAgendaError(null);
        });
      } else if (agendaResult.status === "rejected" && shouldRefreshAgenda) {
        setAgendaError(getErrorMessage(agendaResult.reason));
      }

      if (projectsResult.status === "fulfilled" && Array.isArray(projectsResult.value)) {
        const nextProjects = projectsResult.value;
        startTransition(() => {
          setProjects(nextProjects);
        });
        markHeavyResourceRefreshed("projects");
      }

      if (relationsResult.status === "fulfilled" && Array.isArray(relationsResult.value)) {
        const nextRelations = relationsResult.value;
        startTransition(() => {
          setRelations(nextRelations);
          setRelationsError(null);
        });
        markHeavyResourceRefreshed("relations");
      } else if (relationsResult.status === "rejected" && shouldRefreshRelations) {
        setRelationsError(getErrorMessage(relationsResult.reason));
      }

      if (memoryStatusResult.status === "fulfilled" && memoryStatusResult.value) {
        const nextMemoryStatus = memoryStatusResult.value;
        startTransition(() => {
          setMemoryStatus(nextMemoryStatus);
        });
      }

      if (snapshotsResult.status === "fulfilled" && snapshotsResult.value) {
        const nextSnapshots = snapshotsResult.value;
        startTransition(() => {
          setSnapshots(nextSnapshots);
        });
        markHeavyResourceRefreshed("snapshots");
      }

      if (importantMessagesResult.status === "fulfilled" && importantMessagesResult.value) {
        const nextImportantMessages = importantMessagesResult.value;
        startTransition(() => {
          setImportantMessages(nextImportantMessages);
          setImportantMessagesError(null);
        });
        markHeavyResourceRefreshed("important");
      } else if (importantMessagesResult.status === "rejected" && shouldRefreshImportantMessages) {
        setImportantMessagesError(getErrorMessage(importantMessagesResult.reason));
      }

      if (automationResult.status === "fulfilled" && automationResult.value) {
        const nextAutomation = automationResult.value;
        startTransition(() => {
          setAutomationStatus(nextAutomation);
          setAutomationError(null);
        });
        syncQueuedJobFromAutomationSnapshot(nextAutomation);
      } else if (automationResult.status === "rejected" && shouldRefreshAutomation) {
        setAutomationError(getErrorMessage(automationResult.reason));
      }
    } finally {
      dashboardRefreshInFlightRef.current = false;
    }
  }

  pollStatusRef.current = pollStatus;
  pollAgentStatusRef.current = pollAgentStatus;
  refreshLiveDataRef.current = refreshLiveData;

  useEffect(() => {
    void hydrateDashboard();
  }, []);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    void pollStatusRef.current?.(false);

    const intervalId = window.setInterval(() => {
      void pollStatusRef.current?.();
    }, observerStatusIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [isHydrating, observerStatusIntervalMs]);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    void pollAgentStatusRef.current?.(false);

    const intervalId = window.setInterval(() => {
      void pollAgentStatusRef.current?.();
    }, agentStatusIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [agentStatusIntervalMs, isHydrating]);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    void refreshLiveDataRef.current?.();
  }, [activeAgentThreadId, activeChatThreadId, activeTab, isHydrating]);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshLiveDataRef.current?.();
    }, liveRefreshIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [isHydrating, liveRefreshIntervalMs]);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    void refreshFromLiveSummary();

    const intervalId = window.setInterval(() => {
      void refreshFromLiveSummary();
    }, LIVE_MEMORY_DIGEST_POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [isHydrating]);

  useEffect(() => {
    if (isHydrating || (!queuedJobId && !memoryJobIsPending && !agentState.running)) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshLiveDataRef.current?.();
    }, ACTIVE_JOB_POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [agentState.running, isHydrating, memoryJobIsPending, queuedJobId]);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    const refreshOnAttention = (): void => {
      if (!isDocumentVisible()) {
        return;
      }

      const now = Date.now();
      if (lastAttentionRefreshAtRef.current && now - lastAttentionRefreshAtRef.current < ATTENTION_REFRESH_THROTTLE_MS) {
        return;
      }

      lastAttentionRefreshAtRef.current = now;
      void pollStatusRef.current?.(false);
      void pollAgentStatusRef.current?.(false);
      void refreshLiveDataRef.current?.();
    };

    const handleVisibilityChange = (): void => {
      if (isDocumentVisible()) {
        refreshOnAttention();
      }
    };

    window.addEventListener("focus", refreshOnAttention);
    window.addEventListener("online", refreshOnAttention);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("focus", refreshOnAttention);
      window.removeEventListener("online", refreshOnAttention);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [isHydrating]);

  useEffect(() => {
    if (!chatScrollRef.current) {
      return;
    }
    chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
  }, [chatMessages, activeTab]);

  useEffect(() => {
    if (!memoryActivity) {
      return;
    }

    const latestSyncRun = memoryActivity.sync_runs[0] ?? null;
    if (latestSyncRun && latestSyncRun.id !== lastObservedSyncRef.current) {
      lastObservedSyncRef.current = latestSyncRun.id;
      pushAgentLog(
        latestSyncRun.status === "failed" ? "error" : "info",
        latestSyncRun.status === "failed"
          ? `Sync recente falhou. ${latestSyncRun.error_text || "Sem detalhe persistido."}`
          : `Sync recente ${latestSyncRun.status}: ${latestSyncRun.messages_saved_count} mensagens úteis ficaram prontas para análise.`,
      );
    }

    const latestJob = memoryActivity.jobs[0] ?? null;
    if (latestJob) {
      const signature = `${latestJob.id}:${latestJob.status}`;
      if (signature !== lastObservedJobRef.current) {
        lastObservedJobRef.current = signature;
        pushAgentLog(
          latestJob.status === "failed" ? "error" : latestJob.status === "succeeded" ? "success" : "info",
          latestJob.status === "failed"
            ? `${getIntentTitle(latestJob.intent as AgentIntent)} falhou. ${latestJob.error_text || "Sem detalhe persistido."}`
            : latestJob.status === "succeeded"
              ? `${getIntentTitle(latestJob.intent as AgentIntent)} terminou com ${latestJob.selected_message_count} mensagens processadas.`
              : `${getIntentTitle(latestJob.intent as AgentIntent)} está ${latestJob.status} no backend.`,
        );
      }
    }

    const latestModelRun = memoryActivity.model_runs[0] ?? null;
    if (latestModelRun && latestModelRun.id !== lastObservedModelRunRef.current) {
      lastObservedModelRunRef.current = latestModelRun.id;
      pushAgentLog(
        latestModelRun.success ? "success" : "error",
        latestModelRun.success
          ? `${latestModelRun.provider} concluiu ${latestModelRun.run_type} em ${latestModelRun.latency_ms ?? 0} ms.`
          : `${latestModelRun.provider} falhou em ${latestModelRun.run_type}. ${latestModelRun.error_text || "Sem detalhe persistido."}`,
      );
    }
  }, [memoryActivity]);

  function applyChatWorkspace(workspace: ChatWorkspace): void {
    setChatThreads(workspace.threads);
    setActiveChatThreadId(workspace.active_thread_id);
    setChatThreadTitle(workspace.session.title);
    setChatMessages(workspace.session.messages);
    setProjects(workspace.session.projects);
    setMemory(workspace.session.current);
    setChatError(null);
    setMemoryError(null);
  }

  function applyAgentWorkspace(workspace: WhatsAppAgentWorkspace): void {
    setAgentStatus(workspace.status);
    setAgentSettings(workspace.settings);
    setAgentThreads(workspace.threads);
    setActiveAgentThreadId(workspace.active_thread_id);
    setAgentActiveSession(workspace.active_session);
    setAgentContactMemory(workspace.contact_memory);
    setAgentMessages(workspace.messages);
    setAgentConnectionError(null);
    setAgentMessagesError(null);
    setAgentPollingEnabled(!workspace.status.connected);
    setAgentViewState(workspace.status.connected ? "connected" : "waiting");
  }

  async function hydrateDashboard(mode: "initial" | "manual" = "initial"): Promise<void> {
    if (mode === "manual") {
      setIsRefreshing(true);
    } else {
      setIsHydrating(true);
    }

    const shouldLoadAgentWorkspace = false;
    const shouldLoadChatWorkspace = activeTab === "chat" || activeTab === "manual";
    const shouldLoadGroups = activeTab === "groups" || activeTab === "manual";
    const shouldLoadRelations = activeTab === "relations" || activeTab === "manual";
    const shouldLoadAgenda = activeTab === "agenda";
    const shouldLoadSnapshots = activeTab === "overview" || activeTab === "memory" || activeTab === "manual";
    const shouldLoadImportantMessages = activeTab === "important" || activeTab === "manual";
    const shouldLoadAutomation = resolvedActiveTab === "memory" || resolvedActiveTab === "automation" || resolvedActiveTab === "manual" || queuedJobId !== null;

    const [
      statusResult,
      agentStatusResult,
      agentWorkspaceResult,
      chatResult,
      memoryResult,
      groupsResult,
      agendaResult,
      projectsResult,
      relationsResult,
      memoryStatusResult,
      snapshotsResult,
      importantMessagesResult,
      automationResult,
    ] = await Promise.allSettled([
      getObserverStatus(false),
      Promise.resolve(null),
      shouldLoadAgentWorkspace ? getAgentWorkspace(activeAgentThreadId ?? undefined) : Promise.resolve(null),
      shouldLoadChatWorkspace ? getChatWorkspace(activeChatThreadId ?? undefined) : Promise.resolve(null),
      getCurrentMemory(),
      shouldLoadGroups ? getMemoryGroups() : Promise.resolve([]),
      shouldLoadAgenda ? getAgendaEvents(120, false) : Promise.resolve([]),
      getMemoryProjects(),
      shouldLoadRelations ? getMemoryRelations() : Promise.resolve(null),
      getMemoryStatus(),
      shouldLoadSnapshots ? getMemorySnapshots(activeTab === "overview" ? 1 : 6) : Promise.resolve([]),
      shouldLoadImportantMessages ? getImportantMessages(80) : Promise.resolve([]),
      shouldLoadAutomation ? getAutomationStatus() : Promise.resolve(null),
    ]);

    if (statusResult.status === "fulfilled") {
      setStatus(statusResult.value);
      setPollingEnabled(!statusResult.value.connected);
      setViewState(statusResult.value.connected ? "connected" : "waiting");
      setConnectionError(null);
    } else {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(statusResult.reason));
    }

    if (agentStatusResult.status === "fulfilled" && agentStatusResult.value) {
      applyAgentStatus(agentStatusResult.value, false);
    } else if (agentStatusResult.status === "rejected") {
      const message = getErrorMessage(agentStatusResult.reason);
      setAgentConnectionError(message);
      setAgentViewState("error");
      setAgentPollingEnabled(false);
    }

    if (agentWorkspaceResult.status === "fulfilled" && agentWorkspaceResult.value) {
      applyAgentWorkspace(agentWorkspaceResult.value);
    } else if (agentWorkspaceResult.status === "rejected") {
      const message = getErrorMessage(agentWorkspaceResult.reason);
      setAgentConnectionError(message);
      setAgentViewState("error");
    }

    if (chatResult.status === "fulfilled" && chatResult.value) {
      applyChatWorkspace(chatResult.value);
    } else if (chatResult.status === "rejected") {
      const message = getErrorMessage(chatResult.reason);
      setChatError(message);
    }

    if (memoryResult.status === "fulfilled") {
      setMemory(memoryResult.value);
      setMemoryError(null);
    } else if (!shouldLoadChatWorkspace) {
      setMemoryError(getErrorMessage(memoryResult.reason));
    }

    if (groupsResult.status === "fulfilled" && Array.isArray(groupsResult.value)) {
      setMemoryGroups(groupsResult.value);
      setMemoryGroupsError(null);
      markHeavyResourceRefreshed("groups");
    } else if (groupsResult.status === "rejected") {
      setMemoryGroupsError(getErrorMessage(groupsResult.reason));
    }

    if (agendaResult.status === "fulfilled" && Array.isArray(agendaResult.value)) {
      setAgendaEvents(agendaResult.value);
      setAgendaError(null);
    } else if (agendaResult.status === "rejected" && shouldLoadAgenda) {
      setAgendaError(getErrorMessage(agendaResult.reason));
    }

    if (projectsResult.status === "fulfilled" && Array.isArray(projectsResult.value)) {
      setProjects(projectsResult.value);
      markHeavyResourceRefreshed("projects");
    }

    if (relationsResult.status === "fulfilled" && Array.isArray(relationsResult.value)) {
      setRelations(relationsResult.value);
      setRelationsError(null);
      markHeavyResourceRefreshed("relations");
    } else if (relationsResult.status === "rejected" && shouldLoadRelations) {
      setRelationsError(getErrorMessage(relationsResult.reason));
    }

    if (memoryStatusResult.status === "fulfilled") {
      setMemoryStatus(memoryStatusResult.value);
    }

    if (snapshotsResult.status === "fulfilled" && snapshotsResult.value) {
      setSnapshots(snapshotsResult.value);
      markHeavyResourceRefreshed("snapshots");
    }

    if (importantMessagesResult.status === "fulfilled" && importantMessagesResult.value) {
      setImportantMessages(importantMessagesResult.value);
      setImportantMessagesError(null);
      markHeavyResourceRefreshed("important");
    } else if (importantMessagesResult.status === "rejected") {
      setImportantMessagesError(getErrorMessage(importantMessagesResult.reason));
    }

    if (automationResult.status === "fulfilled" && automationResult.value) {
      const snap = automationResult.value;
      setAutomationStatus(snap);
      setAutomationError(null);
      syncQueuedJobFromAutomationSnapshot(snap);
    } else if (automationResult.status === "rejected") {
      setAutomationError(getErrorMessage(automationResult.reason));
    }

    if (mode === "manual") {
      setIsRefreshing(false);
    } else {
      setIsHydrating(false);
    }
  }

  async function saveAutomationConfig(): Promise<void> {
    if (!automationDraft) {
      return;
    }

    setIsSavingAutomation(true);
    setAutomationError(null);
    try {
      const nextSettings = await updateAutomationSettings(automationDraft);
      setAutomationStatus((previous: any) =>
        previous
          ? { ...previous, settings: nextSettings }
          : {
              settings: nextSettings,
              sync_runs: [],
              decisions: [],
              jobs: [],
              model_runs: [],
              daily_cost_usd: 0,
              daily_auto_jobs_count: 0,
              queued_jobs_count: 0,
              running_job_id: null,
            },
      );
      pushAgentLog("success", "Configuração da automação salva no backend.");
    } catch (error) {
      const message = getErrorMessage(error);
      setAutomationError(message);
      pushAgentLog("error", `Falha ao salvar automação: ${message}`);
    } finally {
      setIsSavingAutomation(false);
    }
  }

  async function triggerAutomationNow(): Promise<void> {
    setIsTickingAutomation(true);
    setAutomationError(null);
    try {
      const snapshot = await runAutomationTick();
      setAutomationStatus(snapshot);
      pushAgentLog("info", "Tick manual da automação executado. Syncs ociosos foram fechados e a fila foi processada.");
    } catch (error) {
      const message = getErrorMessage(error);
      setAutomationError(message);
      pushAgentLog("error", `Falha ao rodar o tick manual: ${message}`);
    } finally {
      setIsTickingAutomation(false);
    }
  }

  function pushAgentLog(tone: LogTone, message: string): void {
    setAgentLogs((previous) => [makeLog(tone, message), ...previous].slice(0, 28));
  }

  function startAgentRun(intent: AgentIntent): void {
    const mode: Exclude<AgentMode, "idle"> = "analyze";
    setAgentState({
      mode,
      intent,
      running: true,
      progress: 4,
      status: "Solicitando execucao real ao backend...",
      error: null,
      completedAt: null,
    });

    pushAgentLog(
      "info",
      intent === "first_analysis"
        ? "Primeira analise iniciada. O agente vai criar a base inicial do dono usando mensagens diretas recentes."
        : "Atualizacao incremental iniciada. O agente vai combinar mensagens novas com snapshots, projetos e chat pessoal.",
    );
  }

  function finishAgentRunSuccess(intent: AgentIntent, message: string): void {
    const mode: Exclude<AgentMode, "idle"> = "analyze";
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
    const mode: Exclude<AgentMode, "idle"> = "analyze";
    setAgentState({
      mode,
      intent,
      running: false,
      progress: 0,
      status: `A atualização falhou: ${message}`,
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

  async function startAgentConnection(): Promise<void> {
    setIsAgentConnecting(true);
    setAgentConnectionError(null);
    setAgentViewState("loading");
    try {
      const nextStatus = await connectAgent();
      setAgentStatus(nextStatus);
      setAgentPollingEnabled(!nextStatus.connected);
      setAgentViewState(nextStatus.connected ? "connected" : "waiting");
      lastAgentQrRefreshAtRef.current = Date.now();
      pushAgentLog("info", "Fluxo de conexao iniciado para o WhatsApp agente.");
    } catch (error) {
      setAgentPollingEnabled(false);
      setAgentViewState("error");
      setAgentConnectionError(getErrorMessage(error));
    } finally {
      setIsAgentConnecting(false);
    }
  }

  async function resetAgentConnection(): Promise<void> {
    setIsAgentResetting(true);
    setAgentConnectionError(null);
    setAgentViewState("loading");
    try {
      const nextStatus = await resetAgent();
      setAgentStatus(nextStatus);
      setAgentPollingEnabled(!nextStatus.connected);
      setAgentViewState(nextStatus.connected ? "connected" : "waiting");
      lastAgentQrRefreshAtRef.current = Date.now();
      pushAgentLog("info", "Sessao do agente resetada. Novo QR pronto para leitura.");
    } catch (error) {
      setAgentPollingEnabled(false);
      setAgentViewState("error");
      setAgentConnectionError(getErrorMessage(error));
    } finally {
      setIsAgentResetting(false);
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
      pushAgentLog(
        "info",
        response.sync_run_id ? `${response.message} Sync ${response.sync_run_id.slice(0, 8)} aberto.` : response.message,
      );
      pushAgentLog("info", "Releitura concluída. As mensagens novas ficaram disponíveis para a próxima análise manual.");

      try {
        const snapshot = await runAutomationTick();
        setAutomationStatus(snapshot);
        pushAgentLog("info", "Atividade manual atualizada após a releitura. Execute a análise na aba de memória quando quiser consolidar o novo lote.");
      } catch (tickError) {
        pushAgentLog("error", `A releitura terminou, mas não consegui atualizar a atividade manual: ${getErrorMessage(tickError)}`);
      }

      await hydrateDashboard("manual");
    } catch (error) {
      const message = getErrorMessage(error);
      setMessageRefreshError(message);
      pushAgentLog("error", `A releitura do WhatsApp falhou: ${message}`);
    } finally {
      setIsRefreshingMessages(false);
    }
  }

  async function legacyPollStatus(): Promise<void> {
    try {
      const shouldRefreshQr = Boolean(status?.qr_code) && (
        !lastQrRefreshAtRef.current ||
        Date.now() - lastQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS
      );

      const nextStatus = await getObserverStatus(shouldRefreshQr);

      if (shouldRefreshQr) {
        lastQrRefreshAtRef.current = Date.now();
      }

      setStatus((previous) => mergeStatus(previous, nextStatus));
      setConnectionError(null);

      if (nextStatus.connected) {
        setPollingEnabled(false);
        setViewState("connected");
        pushAgentLog("success", "Observador conectado. Diretas já entram na memória; grupos ficam opt-in na aba Grupos.");
        return;
      }

      setViewState("waiting");
    } catch (error) {
      setPollingEnabled(false);
      setViewState("error");
      setConnectionError(getErrorMessage(error));
    }
  }

  async function legacyPollAgentStatus(): Promise<void> {
    try {
      const shouldRefreshQr = Boolean(agentStatus?.qr_code) && (
        !lastAgentQrRefreshAtRef.current ||
        Date.now() - lastAgentQrRefreshAtRef.current >= QR_REFRESH_INTERVAL_MS
      );

      const nextStatus = shouldRefreshQr ? await connectAgent() : await getAgentStatus();

      if (shouldRefreshQr) {
        lastAgentQrRefreshAtRef.current = Date.now();
      }

      setAgentStatus(nextStatus);
      setAgentConnectionError(null);

      if (nextStatus.connected) {
        setAgentPollingEnabled(false);
        setAgentViewState("connected");
        pushAgentLog("success", "WhatsApp agente conectado. Respostas automaticas podem ser ativadas.");
        return;
      }

      setAgentViewState("waiting");
    } catch (error) {
      setAgentPollingEnabled(false);
      setAgentViewState("error");
      setAgentConnectionError(getErrorMessage(error));
    }
  }

  async function runMemoryJob(intent: AgentIntent): Promise<void> {
    if (agentState.running || !!queuedJobId) {
       console.log("Análise já em andamento. Ignorando clique duplicado.");
       return;
    }
    setMemoryError(null);
    startAgentRun(intent);

    try {
      if (intent === "first_analysis" || intent === "improve_memory") {
        const response = intent === "first_analysis"
          ? await runFirstMemoryAnalysis()
          : await runNextMemoryBatch();
        
        // Response now contains the queued job
        if (response.job && (response.job.status === "queued" || response.job.status === "running")) {
          setQueuedJobId(response.job.id);
          pushAgentLog(
            "info",
            response.job.status === "running"
              ? "Tarefa aceita pelo servidor e já entrou em processamento."
              : "Tarefa registrada na fila do servidor. Iniciando processamento em segundo plano...",
          );
          void refreshLiveDataRef.current?.();
        } else {
           setMemory(response.current);
           setProjects(response.projects);
           markHeavyResourceRefreshed("projects");
           if (response.snapshot) {
             const nextSnapshot = response.snapshot;
             setSnapshots((previous) => [nextSnapshot, ...previous.filter((snapshot) => snapshot.id !== nextSnapshot.id)].slice(0, 6));
             markHeavyResourceRefreshed("snapshots");
           }
           finishAgentRunSuccess(
             intent,
             intent === "first_analysis"
               ? "Primeira analise concluida. A base inicial do dono foi criada."
               : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado.",
           );
        }
      }

    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError(intent, message);
    }
  }

  async function handleClearSavedDatabase(): Promise<void> {
    if (isClearingDatabase) {
      return;
    }

    const confirmed = window.confirm(
      "Isso vai apagar TODOS os dados salvos no banco de dados local, incluindo memoria, mensagens, snapshots, chat, sessoes e configuracoes persistidas. Deseja continuar?",
    );
    if (!confirmed) {
      return;
    }

    setIsClearingDatabase(true);
    setMemoryActivityError(null);

    try {
      await clearSavedDatabase();
      setQueuedJobId(null);
      setAgentState({
        mode: "idle",
        intent: null,
        running: false,
        progress: 0,
        status: IDLE_AGENT_STATUS,
        error: null,
        completedAt: new Date().toISOString(),
      });
      setAgentLogs([makeLog("success", "Todos os dados salvos no banco local foram apagados com sucesso.")]);
      await hydrateDashboard("manual");
    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryActivityError(message);
      pushAgentLog("error", `Falha ao apagar o banco salvo: ${message}`);
    } finally {
      setIsClearingDatabase(false);
    }
  }

  async function openChatThread(threadId: string): Promise<void> {
    if (!threadId || threadId === activeChatThreadId) {
      return;
    }

    setIsLoadingChatThread(true);
    setChatError(null);
    try {
      const workspace = await getChatWorkspace(threadId);
      applyChatWorkspace(workspace);
      setActiveTab("chat");
    } catch (error) {
      setChatError(getErrorMessage(error));
      setActiveTab("chat");
    } finally {
      setIsLoadingChatThread(false);
    }
  }

  async function startNewChatThread(): Promise<void> {
    setIsCreatingChatThread(true);
    setChatError(null);
    try {
      const workspace = await createChatThread();
      applyChatWorkspace(workspace);
      setChatDraft("");
      setActiveTab("chat");
      pushAgentLog("info", "Nova thread criada. O contexto da memória continua disponível nessa conversa.");
    } catch (error) {
      setChatError(getErrorMessage(error));
      setActiveTab("chat");
    } finally {
      setIsCreatingChatThread(false);
    }
  }

  async function removeChatThread(thread: ChatThread): Promise<void> {
    if (!thread.can_delete || deletingChatThreadIds.includes(thread.id)) {
      return;
    }

    const confirmed = window.confirm(`Excluir a conversa "${thread.title}"? Isso também apaga as mensagens dela no banco local.`);
    if (!confirmed) {
      return;
    }

    setDeletingChatThreadIds((previous) => [...previous, thread.id]);
    setChatError(null);
    try {
      const workspace = await deleteChatThread(thread.id);
      applyChatWorkspace(workspace);
      setChatDraft("");
      setActiveTab("chat");
      pushAgentLog("success", `Conversa pessoal excluída: ${thread.title}. Os registros também saíram do banco local.`);
    } catch (error) {
      const message = getErrorMessage(error);
      setChatError(message);
      setActiveTab("chat");
      pushAgentLog("error", `Falha ao excluir a conversa pessoal: ${message}`);
    } finally {
      setDeletingChatThreadIds((previous) => previous.filter((id) => id !== thread.id));
    }
  }

  async function submitChatMessage(): Promise<void> {
    const normalized = chatDraft.trim();
    if (!normalized) {
      setChatError("Escreva uma mensagem para enviar.");
      return;
    }

    setIsSendingChat(true);
    setChatError(null);
    setChatDraft("");

    // ── Smart context builder: scores all knowledge sources by relevance to the user's question ──
    const contextHint = buildSmartContextHint(normalized, importantMessages, projects, snapshots, memory);

    // Optimistically add user message to the list
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: normalized,
      created_at: new Date().toISOString(),
    };
    setChatMessages((prev) => [...prev, tempUserMsg]);
    setStreamingText("");

    try {
      for await (const event of sendChatMessageStream(normalized, activeChatThreadId ?? undefined, contextHint)) {
        if (event.type === "token") {
          setStreamingText((prev) => (prev ?? "") + event.content);
        } else if (event.type === "done") {
          setStreamingText(null);
          applyChatWorkspace(event.workspace);
          pushAgentLog("info", "Nova conversa salva no chat. Esse contexto entra nas próximas leituras da memória.");
        }
      }
    } catch (error) {
      setStreamingText(null);
      setChatError(getErrorMessage(error));
      setActiveTab("chat");
    } finally {
      setIsSendingChat(false);
    }
  }

  async function refreshAgentWorkspace(threadId?: string): Promise<void> {
    try {
      const workspace = await getAgentWorkspace(threadId ?? undefined);
      applyAgentWorkspace(workspace);
    } catch (error) {
      setAgentConnectionError(getErrorMessage(error));
    }
  }

  async function openAgentThread(threadId: string): Promise<void> {
    if (!threadId || threadId === activeAgentThreadId) {
      return;
    }
    setAgentMessagesError(null);
    try {
      const workspace = await getAgentWorkspace(threadId);
      applyAgentWorkspace(workspace);
    } catch (error) {
      setAgentMessagesError(getErrorMessage(error));
    }
  }

  async function toggleAgentAutoReply(nextValue: boolean): Promise<void> {
    setIsAgentSaving(true);
    setAgentMessagesError(null);
    try {
      const settings = await updateAgentSettings({ auto_reply_enabled: nextValue });
      setAgentSettings(settings);
      setAgentStatus((previous) => (previous ? { ...previous, auto_reply_enabled: settings.auto_reply_enabled } : previous));
      pushAgentLog(
        "success",
        settings.auto_reply_enabled
          ? "Resposta automatica do WhatsApp agente ativada."
          : "Resposta automatica do WhatsApp agente desativada.",
      );
    } catch (error) {
      setAgentMessagesError(getErrorMessage(error));
    } finally {
      setIsAgentSaving(false);
    }
  }

  const currentNavTitle = NAV_ITEMS.find((item) => item.id === activeTab)?.label ?? "AuraCore";

  return (
    <div className="ac-layout-shell">
      <Toaster position="bottom-right" toastOptions={{
        style: {
          background: '#27272a',
          color: '#e4e4e7',
          border: '1px solid #3f3f46',
        },
      }} />
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
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="ac-nav-group">
              <h4 className="ac-nav-group-title">{group.title}</h4>
              <div className="ac-nav-group-items">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = resolvedActiveTab === item.id;
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
                      <Icon size={16} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
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
            <span>Mensagens novas</span>
            <strong>{memoryStatus ? formatTokenCount(memoryStatus.new_messages_after_first_analysis) : "..."}</strong>
          </div>
          <div className="ac-quick-status">
            <span>Próximo lote</span>
            <strong>{memoryStatus?.current_job ? formatState(memoryStatus.current_job.status) : "Livre"}</strong>
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
            {status ? (
              <div 
                className={`micro-status micro-status-${status.connected && status.gateway_ready ? "emerald" : "amber"}`}
                style={{ marginRight: "0.5rem" }}
              >
                {status.connected ? "WhatsApp Conectado" : "WhatsApp Desconectado"}
              </div>
            ) : null}
            <button className="ac-icon-button" onClick={() => void hydrateDashboard("manual")} disabled={isRefreshing} type="button">
              <RefreshCw size={16} className={isRefreshing ? "spin" : ""} />
            </button>
            <button
              className="ac-primary-button"
              onClick={() => void runMemoryJob(memoryIsEstablished ? "improve_memory" : "first_analysis")}
              disabled={
                agentState.running ||
                memoryJobIsPending ||
                !memoryStatus?.can_execute_analysis
              }
              type="button"
            >
              <Play size={15} />
              {memoryJobIsPending
                ? currentMemoryJob?.intent === "first_analysis"
                  ? "Primeira análise em andamento"
                  : "Atualização em andamento"
                : agentState.running && agentState.mode === "analyze"
                  ? "Lendo..."
                  : memoryIsEstablished
                    ? "Atualizar Sistema"
                    : "Primeira Análise"}
            </button>
          </div>
        </header>

        <div className="ac-main-scroll">
          {isHydrating ? (
            <Card className="ac-loading-card">
              <SectionTitle title="Carregando AuraCore" icon={RefreshCw} />
              <p>Buscando status do observador, perfil atual, relações, snapshots, projetos e histórico do chat.</p>
            </Card>
          ) : (
            <>
              {resolvedActiveTab === "overview" ? (
                <OverviewTab
                  memory={memory}
                  memoryStatus={memoryStatus}
                  latestSnapshot={latestSnapshot}
                  projects={projects}
                  status={status}
                  connectionError={connectionError}
                  memoryError={memoryError}
                  insightMetrics={insightMetrics}
                  onGoToObserver={() => setActiveTab("observer")}
                  onGoToMemory={() => setActiveTab("memory")}
                  onGoToChat={() => setActiveTab("chat")}
                />
              ) : null}

              {resolvedActiveTab === "observer" ? (
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

              {resolvedActiveTab === "groups" ? (
                <GroupsTab
                  groups={memoryGroups}
                  error={memoryGroupsError}
                  isSavingJids={savingGroupJids}
                  onToggleGroup={toggleGroupSelection}
                  onRefresh={() => void hydrateDashboard("manual")}
                />
              ) : null}

              {resolvedActiveTab === "memory" ? (
                <MemoryTab
                  memoryStatus={memoryStatus}
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  memoryActivity={memoryActivity}
                  memoryError={memoryError}
                  agentState={displayAgentState}
                  steps={currentSteps}
                  logs={activityLogs}
                  projectsCount={projects.length}
                  snapshotsCount={snapshots.length}
                  automationStatus={automationStatus}
                  automationError={automationError ?? memoryActivityError}
                  isClearingDatabase={isClearingDatabase}
                  onInitialAnalysis={() => void runMemoryJob("first_analysis")}
                  onImproveMemory={() => void runMemoryJob("improve_memory")}
                  onClearDatabase={() => void handleClearSavedDatabase()}
                  queuedJobId={queuedJobId}
                />
              ) : null}

              {resolvedActiveTab === "important" ? (
                <ImportantMessagesTab
                  messages={importantMessages}
                  error={importantMessagesError}
                  onRefresh={() => void hydrateDashboard("manual")}
                />
              ) : null}

              {resolvedActiveTab === "relations" ? (
                <RelationsTab
                  relations={relations}
                  error={relationsError}
                  onRefresh={() => void hydrateDashboard("manual")}
                  onSaveRelation={saveRelationEdits}
                />
              ) : null}

              {resolvedActiveTab === "agenda" ? (
                <AgendaTab
                  events={agendaEvents}
                  error={agendaError}
                  actionError={agendaActionError}
                  onRefresh={() => void hydrateDashboard("manual")}
                  onSaveEvent={saveAgendaEdits}
                  onDeleteEvent={removeAgendaEvent}
                  savingAgendaIds={savingAgendaIds}
                  deletingAgendaIds={deletingAgendaIds}
                />
              ) : null}

              {resolvedActiveTab === "projects" ? (
                <ProjectsTab
                  projects={projects}
                  onToggleCompletion={toggleProjectCompletion}
                  onSaveProject={saveProjectEdits}
                  onAssistProject={assistProjectEdit}
                  onDeleteProject={removeProject}
                  savingProjectKeys={savingProjectKeys}
                  deletingProjectKeys={deletingProjectKeys}
                  editingProjectKeys={editingProjectKeys}
                  aiProjectKeys={aiProjectKeys}
                  actionError={projectActionError}
                />
              ) : null}

              {resolvedActiveTab === "chat" ? (
                <ChatTab
                  chatThreads={chatThreads}
                  activeChatThread={activeChatThread}
                  chatMessages={chatMessages}
                  chatDraft={chatDraft}
                  chatError={chatError}
                  streamingText={streamingText}
                  isSendingChat={isSendingChat}
                  isLoadingChatThread={isLoadingChatThread}
                  isCreatingChatThread={isCreatingChatThread}
                  deletingChatThreadIds={deletingChatThreadIds}
                  chatScrollRef={chatScrollRef}
                  onChatDraftChange={setChatDraft}
                  onSelectThread={(threadId) => void openChatThread(threadId)}
                  onCreateThread={() => void startNewChatThread()}
                  onDeleteThread={(thread) => void removeChatThread(thread)}
                  onApplyPrompt={setChatDraft}
                  onSubmit={() => void submitChatMessage()}
                />
              ) : null}

              {resolvedActiveTab === "automation" ? (
                <AutomationTab
                  automationStatus={automationStatus}
                  automationDraft={automationDraft}
                  automationError={automationError}
                  isSavingAutomation={isSavingAutomation}
                  isTickingAutomation={isTickingAutomation}
                  onDraftChange={setAutomationDraft}
                  onSave={() => void saveAutomationConfig()}
                  onTick={() => void triggerAutomationNow()}
                />
              ) : null}

              {resolvedActiveTab === "manual" ? (
                <ManualTab
                  status={status}
                  memory={memory}
                  projects={projects}
                  snapshots={snapshots}
                  importantMessages={importantMessages}
                  chatThreads={chatThreads}
                  chatMessages={chatMessages}
                  automationStatus={automationStatus}
                />
              ) : null}
              {resolvedActiveTab === "account" ? (
                <AccountTab account={account} onLogout={onLogout} />
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
  memoryStatus,
  latestSnapshot,
  projects,
  status,
  connectionError,
  memoryError,
  insightMetrics,
  onGoToObserver,
  onGoToMemory,
  onGoToChat,
}: {
  memory: MemoryCurrent | null;
  memoryStatus: MemoryStatus | null;
  latestSnapshot: MemorySnapshot | null;
  projects: ProjectMemory[];
  status: ObserverStatus | null;
  connectionError: string | null;
  memoryError: string | null;
  insightMetrics: InsightMetric[];
  onGoToObserver: () => void;
  onGoToMemory: () => void;
  onGoToChat: () => void;
}) {
  const [subTab, setSubTab] = useState<"summary" | "mapping" | "signals">("summary");
  const structuralStrengths = memory?.structural_strengths?.length ? memory.structural_strengths : (latestSnapshot?.key_learnings ?? []);
  const structuralRoutines = memory?.structural_routines?.length ? memory.structural_routines : (latestSnapshot?.routine_signals ?? []);
  const structuralPreferences = memory?.structural_preferences?.length ? memory.structural_preferences : (latestSnapshot?.preferences ?? []);
  const structuralOpenQuestions = memory?.structural_open_questions?.length ? memory.structural_open_questions : (latestSnapshot?.open_questions ?? []);
  const pendingMessages = memoryStatus?.new_messages_after_first_analysis ?? 0;
  const hasMemoryBase = memoryStatus?.has_initial_analysis ?? false;
  const currentJob = memoryStatus?.current_job ?? null;
  const nextAction = resolveOverviewNextAction({ status, memoryStatus, latestSnapshot });
  const latestSnapshotCoverageTone = getSnapshotCoverageTone(latestSnapshot);
  const latestSnapshotCoverageLabel = getSnapshotCoverageLabel(latestSnapshot);
  const latestUpdateLabel = memory?.last_analyzed_at
    ? formatShortDateTime(memory.last_analyzed_at)
    : latestSnapshot?.created_at
      ? formatShortDateTime(latestSnapshot.created_at)
      : "Pendente";
  const handlePrimaryAction = () => {
    if (nextAction.target === "observer") {
      onGoToObserver();
      return;
    }
    if (nextAction.target === "memory") {
      onGoToMemory();
      return;
    }
    if (nextAction.target === "chat") {
      onGoToChat();
      return;
    }
    onGoToMemory();
  };
  const journeySteps = [
    {
      title: "Conectar o observador",
      detail: status?.connected
        ? `Sessao ativa${status.owner_number ? ` no numero ${status.owner_number}` : ""}.`
        : "Sem sessao ativa no WhatsApp ainda.",
      state: status?.connected ? "ok" : "pending",
    },
    {
      title: "Captar sinais uteis",
      detail: pendingMessages > 0
        ? `${formatTokenCount(pendingMessages)} mensagens prontas para entrar na memoria.`
        : "Ainda sem mensagens textuais suficientes para o proximo lote.",
      state: pendingMessages > 0 ? "ok" : status?.connected ? "pending" : "blocked",
    },
    {
      title: "Criar ou atualizar a memoria",
      detail: hasMemoryBase
        ? currentJob
          ? `Existe uma execucao ${formatState(currentJob.status).toLowerCase()} agora.`
          : "A base inicial ja existe e pode receber refinamentos incrementais."
        : currentJob?.intent === "first_analysis"
          ? "A primeira leitura ja foi iniciada e esta montando o retrato inicial."
          : "A primeira leitura ainda nao rodou.",
      state: hasMemoryBase ? "ok" : currentJob ? "active" : "pending",
    },
    {
      title: "Usar no chat e nas operacoes",
      detail: hasMemoryBase
        ? "O chat pessoal e os projetos ja podem reaproveitar a memoria consolidada."
        : "Depois da primeira leitura, o chat passa a responder com base no perfil salvo.",
      state: hasMemoryBase ? "ok" : "pending",
    },
  ];

  return (
    <div className="page-stack">
      <Card className="hero-panel overview-hero-panel">
        <div className="hero-copy">
          <div className="hero-kicker">
            <Brain size={14} />
            Painel operacional
          </div>
          <h3>O que importa agora: conectar, captar sinais suficientes e montar uma memória útil sem adivinhação.</h3>
          <p>Use esta tela para entender rapidamente em que etapa o sistema está, o que já foi consolidado e qual é o próximo passo recomendado.</p>
        </div>
        <div className="hero-actions">
          <button className="ac-primary-button" onClick={handlePrimaryAction} type="button">
            <Play size={15} />
            {nextAction.buttonLabel}
          </button>
          <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
            <Database size={15} />
            Abrir Memória
          </button>
          <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
            <Activity size={15} />
            Ver Pipeline
          </button>
        </div>
      </Card>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Próxima Etapa", "Mapa Estrutural", "Pulso Recente"]}
          selected={
            subTab === "summary" ? "Próxima Etapa" : subTab === "mapping" ? "Mapa Estrutural" : "Pulso Recente"
          }
          onChange={(val) => {
            if (val === "Próxima Etapa") setSubTab("summary");
            if (val === "Mapa Estrutural") setSubTab("mapping");
            if (val === "Pulso Recente") setSubTab("signals");
          }}
        />
      </div>

      {subTab === "summary" ? (
        <div className="overview-grid">
          <div className="overview-main-stack">
            <Card className={`overview-action-card overview-action-${nextAction.tone}`}>
              <div className="overview-action-head">
                <div>
                  <div className="hero-kicker">
                    <Zap size={14} />
                    Próxima ação recomendada
                  </div>
                  <h3>{nextAction.title}</h3>
                </div>
                <span className={`micro-status micro-status-${nextAction.tone}`}>{nextAction.badge}</span>
              </div>
              <p className="lead-copy">{nextAction.detail}</p>
              <div className="hero-actions">
                <button className="ac-primary-button" onClick={handlePrimaryAction} type="button">
                  <ChevronRight size={15} />
                  {nextAction.buttonLabel}
                </button>
                <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
                  <Activity size={15} />
                  Acompanhar pipeline
                </button>
              </div>
            </Card>

            <div className="stats-grid modern-stats-grid">
              <ModernStatCard
                label="Observador"
                value={status?.connected ? "Online" : "Aguardando"}
                meta={status?.connected ? "Captura pronta para novos sinais" : "Conecte a sessao para puxar o historico"}
                icon={Eye}
                tone={status?.connected ? "emerald" : "amber"}
              />
              <ModernStatCard
                label="Mensagens prontas"
                value={formatTokenCount(pendingMessages)}
                meta={pendingMessages > 0 ? "Ja podem entrar na proxima leitura" : "Nenhum lote pronto no momento"}
                icon={MessageSquare}
                tone={pendingMessages > 0 ? "indigo" : "zinc"}
              />
              <ModernStatCard
                label="Memoria base"
                value={hasMemoryBase ? "Criada" : "Pendente"}
                meta={hasMemoryBase ? `Ultima consolidacao em ${latestUpdateLabel}` : "A primeira leitura ainda nao rodou"}
                icon={Fingerprint}
                tone={hasMemoryBase ? "emerald" : "amber"}
              />
              <ModernStatCard
                label="Projetos ativos"
                value={String(projects.length)}
                meta={projects.length > 0 ? "Frentes ja consolidadas no banco local" : "Ainda sem frentes consolidadas"}
                icon={FolderGit2}
                tone={projects.length > 0 ? "indigo" : "zinc"}
              />
            </div>

            <Card className={!memory?.life_summary?.trim() ? "overview-empty-card" : ""}>
              <SectionTitle title="Resumo do Dono (Atual)" icon={Fingerprint} />
              {memory?.life_summary?.trim() ? (
                <p className="lead-copy">{memory.life_summary}</p>
              ) : (
                <div className="overview-empty-state">
                  <p className="lead-copy">
                    Ainda nao existe um perfil consolidado. O sistema precisa primeiro capturar conversas uteis e executar a leitura inicial.
                  </p>
                  <div className="overview-empty-checklist">
                    <span>1. Conecte o observador e valide a sessao.</span>
                    <span>2. Espere mensagens textuais suficientes entrarem.</span>
                    <span>3. Rode a primeira analise para criar a base inicial.</span>
                  </div>
                </div>
              )}
            </Card>
          </div>

          <div className="overview-side-stack">
            <Card className="overview-journey-card">
              <SectionTitle title="Jornada do Sistema" icon={GitBranch} />
              <div className="overview-journey-list">
                {journeySteps.map((step, index) => (
                  <div key={step.title} className={`overview-journey-step overview-journey-${step.state}`}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>{step.title}</strong>
                      <p>{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="overview-context-card">
              <SectionTitle title="Leitura Operacional" icon={Server} />
              <div className="overview-context-list">
                <StatusLine label="Numero conectado" value={status?.owner_number ?? "Sem numero"} tone="indigo" />
                <StatusLine label="Ultima consolidacao" value={latestUpdateLabel} tone="amber" />
                <StatusLine label="Cobertura do ultimo snapshot" value={latestSnapshot ? `${latestSnapshot.coverage_score}/100` : "Sem snapshot"} tone={latestSnapshotCoverageTone} />
              </div>
            </Card>
          </div>
        </div>
      ) : null}

      {subTab === "mapping" ? (
        <Card>
          <SectionTitle title="Mapeamento Estrutural" icon={Brain} />
          <p className="support-copy">
            Este mapa mostra o que ja parece firme no comportamento do dono e o que ainda precisa de mais repeticao antes de virar memoria forte.
          </p>
          <div className="dual-column-grid">
            <div className="signal-cluster">
              <h4>O que ja esta firme</h4>
              <SignalBlock
                title="Forcas Cumulativas"
                lines={structuralStrengths}
                emptyLabel="Ainda nao existem forcas recorrentes suficientes para consolidar."
              />
              <SignalBlock
                title="Rotina Detectada"
                lines={structuralRoutines}
                emptyLabel="O ritmo do dono ainda esta cedo demais para aparecer com clareza."
              />
              <SignalBlock
                title="Preferências Operacionais"
                lines={structuralPreferences}
                emptyLabel="As preferencias de decisao e execucao ainda nao apareceram com forca."
              />
            </div>

            <div className="signal-cluster">
              <h4 className="amber">O que ainda esta fraco</h4>
              <SignalBlock
                title="Lacunas Ainda Abertas"
                lines={structuralOpenQuestions}
                emptyLabel="Ainda nao ha lacunas criticas abertas alem do proprio crescimento natural da base."
                subtle
              />
              <SignalBlock
                title="Projetos em Contexto"
                lines={projects.slice(0, 3).map((project) => `${project.project_name}: ${project.status || "sem status claro"}`)}
                emptyLabel="Nenhum projeto real foi consolidado ainda. Isso costuma aparecer depois da primeira leitura ou dos primeiros refinamentos."
                subtle
              />
            </div>
          </div>
        </Card>
      ) : null}

      {subTab === "signals" ? (
        <div className="dual-column-grid">
          <Card className="score-card-modern">
            <SectionTitle title="Resumo da Última Janela" icon={BarChart3} />
            {latestSnapshot ? (
              <>
                <p className="support-copy">{latestSnapshot.window_summary}</p>
                <div className="memory-breakdown-grid">
                  <MemorySignalCard
                    label="Cobertura"
                    value={`${latestSnapshot.coverage_score}/100`}
                    meta={latestSnapshotCoverageLabel}
                    tone={latestSnapshotCoverageTone}
                  />
                  <MemorySignalCard
                    label="Contatos distintos"
                    value={formatTokenCount(latestSnapshot.distinct_contact_count)}
                    meta="Ajuda a evitar que a leitura nasca viciada em uma conversa so."
                    tone="indigo"
                  />
                </div>
              </>
            ) : (
              <div className="overview-empty-state">
                <p className="support-copy">
                  Quando a primeira leitura concluir, este bloco passa a resumir o momento mais recente consolidado do dono.
                </p>
                <div className="overview-empty-checklist">
                  <span>Sem snapshot salvo ainda.</span>
                  <span>A primeira analise vai preencher este painel automaticamente.</span>
                </div>
              </div>
            )}
          </Card>

          <Card>
            <SectionTitle title="Sinais Recentes" icon={Activity} />
            {latestSnapshot ? (
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
            ) : (
              <div className="overview-empty-state">
                <p className="support-copy">
                  Este quadro sai do zero assim que a memoria inicial nasce. Ate la, use Memoria para acompanhar sync, fila e pipeline.
                </p>
                <div className="hero-actions">
                  <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
                    <Activity size={15} />
                    Abrir Pipeline
                  </button>
                </div>
              </div>
            )}
          </Card>
        </div>
      ) : null}

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

function AgentTabLegacy({
  status,
  statusLabel,
  viewState,
  settings,
  activeSession,
  contactMemory,
  threads,
  messages,
  activeThreadId,
  isConnecting,
  isResetting,
  isSaving,
  connectionError,
  messagesError,
  onConnect,
  onReset,
  onToggleAutoReply,
  onSelectThread,
  onRefresh,
}: {
  status: WhatsAppAgentStatus | null;
  statusLabel: string;
  viewState: ViewState;
  settings: WhatsAppAgentSettings | null;
  activeSession: WhatsAppAgentSession | null;
  contactMemory: WhatsAppAgentContactMemory | null;
  threads: WhatsAppAgentThread[];
  messages: WhatsAppAgentMessage[];
  activeThreadId: string | null;
  isConnecting: boolean;
  isResetting: boolean;
  isSaving: boolean;
  connectionError: string | null;
  messagesError: string | null;
  onConnect: () => void;
  onReset: () => void;
  onToggleAutoReply: (value: boolean) => void;
  onSelectThread: (threadId: string) => void;
  onRefresh: () => void;
}) {
  const autoReplyEnabled = settings?.auto_reply_enabled ?? false;
  const replyScopeLabel = status?.reply_scope === "all_direct_contacts" ? "Todos os contatos diretos" : "Escopo legado";
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? threads[0] ?? null;
  const sessionStartedLabel = activeSession?.started_at ? formatDateTime(activeSession.started_at) : "Sem sessao ativa";
  const sessionLastActivityLabel = activeSession?.last_activity_at ? formatDateTime(activeSession.last_activity_at) : "Sem atividade";
  const memoryHighlights = [
    ...(contactMemory?.preferences ?? []),
    ...(contactMemory?.objectives ?? []),
    ...(contactMemory?.durable_facts ?? []),
    ...(contactMemory?.recurring_instructions ?? []),
  ].slice(0, 6);

  return (
    <div className="page-stack agent-page">
      <div className="observer-grid-modern agent-grid-modern">
        <Card className="observer-qr-card agent-qr-card">
          <SectionTitle title="WhatsApp Agente" icon={Bot} />
          <p className="support-copy">
            Escaneie o QR do agente. Ele responde pelo numero secundario e atende qualquer conversa direta individual recebida nele.
          </p>

          <div className="qr-display-shell">
            {status?.qr_code ? (
              <div className="qr-modern-frame">
                <img className="qr-modern-image" src={status.qr_code} alt="QR Code do WhatsApp agente" />
              </div>
            ) : (
              <div className="qr-modern-empty">
                <Bot size={28} />
                <strong>QR indisponÃ­vel</strong>
                <p>
                  {status?.connected
                    ? "O agente jÃ¡ estÃ¡ conectado. NÃ£o Ã© necessÃ¡rio gerar um novo QR."
                    : "Gere uma nova sessÃ£o para exibir o QR do agente."}
                </p>
              </div>
            )}
            <div className="qr-expiry-tag">
              <Clock size={12} />
              {status?.connected ? "SessÃ£o ativa" : status?.qr_expires_in_sec ? `Expira em ${status.qr_expires_in_sec}s` : "Sem QR ativo"}
            </div>
          </div>

          <div className="observer-actions">
            <button className="ac-primary-button" onClick={onConnect} disabled={isConnecting || viewState === "connected"} type="button">
              <RefreshCw size={15} className={isConnecting ? "spin" : ""} />
              {viewState === "connected" ? "Agente conectado" : isConnecting ? "Gerando QR..." : "Gerar Novo QR"}
            </button>
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar status
            </button>
          </div>
        </Card>

        <Card className="observer-status-card agent-status-card">
          <SectionTitle title="Status do Agente" icon={Server} />

          <div className="status-line-list">
            <StatusLine label="Gateway" value={status?.gateway_ready ? "Baileys online" : "IndisponÃ­vel"} tone="emerald" />
            <StatusLine label="SessÃ£o" value={status?.owner_number ?? "Aguardando leitura"} tone="indigo" />
            <StatusLine label="Escopo de resposta" value={replyScopeLabel} tone="amber" />
            <StatusLine label="Resposta automÃ¡tica" value={autoReplyEnabled ? "Ativa" : "Desativada"} tone="zinc" />
          </div>

          <div className="manual-grid">
            <ManualInfoCard
              title="Sessao ativa da conversa"
              text={
                activeSession
                  ? `Iniciada em ${sessionStartedLabel} e com ultima atividade em ${sessionLastActivityLabel}.`
                  : "A proxima mensagem do dono abre uma nova sessao logica. Depois de 10 minutos sem conversa, o contexto reinicia."
              }
            />
            <ManualInfoCard
              title="Memoria propria do agente"
              text={
                contactMemory?.profile_summary?.trim()
                  ? contactMemory.profile_summary
                  : "Sem resumo duravel salvo ainda para este contato. Quando o dono disser algo recorrente ou relevante, o agente passa a guardar."
              }
            />
          </div>

          <div className="agent-action-panel">
            <button
              className={autoReplyEnabled ? "ac-danger-button" : "ac-success-button"}
              onClick={() => onToggleAutoReply(!autoReplyEnabled)}
              disabled={isSaving || !status?.connected}
              type="button"
            >
              <Bot size={15} />
              {autoReplyEnabled ? "Desativar respostas" : "Ativar respostas"}
            </button>
            <p className="support-copy">
              Quando ativado, o agente responde qualquer contato direto individual que enviar mensagem para este numero.
            </p>
          </div>

          <div className="danger-box">
            <h4>
              <AlertCircle size={16} />
              Zona de perigo
            </h4>
            <p>Resetar a sessÃ£o do agente apaga as chaves atuais e exige um novo QR.</p>
            <button className="ac-danger-button" onClick={onReset} disabled={isResetting} type="button">
              <XCircle size={15} />
              {isResetting ? "Resetando..." : "Resetar SessÃ£o do Agente"}
            </button>
          </div>
        </Card>
      </div>

      <div className="agent-conversation-grid">
        <Card className="agent-thread-card">
          <SectionTitle title="Conversas recentes" icon={MessageSquare} />
          {threads.length === 0 ? (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Nenhuma conversa registrada ainda.</p>
            </div>
          ) : (
            <div className="agent-thread-list">
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  className={`agent-thread-row${thread.id === activeThread?.id ? " agent-thread-row-active" : ""}`}
                  onClick={() => onSelectThread(thread.id)}
                  type="button"
                >
                  <div>
                    <strong>{thread.contact_name || thread.contact_phone || "Contato"}</strong>
                    <span>{thread.last_message_preview ?? "Sem mensagem recente"}</span>
                  </div>
                  <div className="agent-thread-meta">
                    <span>{thread.status}</span>
                    <small>
                      {thread.session_started_at
                        ? `sessao ${formatDateTime(thread.session_started_at)}`
                        : thread.last_message_at
                          ? formatDateTime(thread.last_message_at)
                          : "Sem data"}
                    </small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card className="agent-thread-card">
          <SectionTitle title="HistÃ³rico do agente" icon={Bot} />
          {memoryHighlights.length > 0 ? (
            <div className="signal-block signal-block-subtle">
              <span>Memoria duravel desta relacao</span>
              <ul>
                {memoryHighlights.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {activeThread ? (
            <div className="agent-message-stack">
              {messages.length === 0 ? (
                <div className="empty-hint">
                  <MessageSquare size={18} />
                  <p>Sem mensagens ainda para esta conversa.</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`agent-message-bubble agent-message-${msg.role}`}>
                    <div className="agent-message-top">
                      <strong>{msg.role === "assistant" ? "Agente" : "Contato"}</strong>
                      <span>{formatDateTime(msg.message_timestamp)}</span>
                    </div>
                    <p>{msg.content}</p>
                    <small>{msg.processing_status}{msg.send_status ? ` â€¢ ${msg.send_status}` : ""}</small>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Selecione um contato para ver as mensagens.</p>
            </div>
          )}
        </Card>
      </div>

      {connectionError ? <InlineError title={`Falha do agente (${statusLabel})`} message={connectionError} /> : null}
      {messagesError ? <InlineError title="Falha nas mensagens do agente" message={messagesError} /> : null}
    </div>
  );
}

void AgentTabLegacy;

function AgentTab({
  status,
  statusLabel,
  viewState,
  settings,
  activeSession,
  contactMemory,
  threads,
  messages,
  activeThreadId,
  isConnecting,
  isResetting,
  isSaving,
  connectionError,
  messagesError,
  onConnect,
  onReset,
  onToggleAutoReply,
  onSelectThread,
  onRefresh,
}: {
  status: WhatsAppAgentStatus | null;
  statusLabel: string;
  viewState: ViewState;
  settings: WhatsAppAgentSettings | null;
  activeSession: WhatsAppAgentSession | null;
  contactMemory: WhatsAppAgentContactMemory | null;
  threads: WhatsAppAgentThread[];
  messages: WhatsAppAgentMessage[];
  activeThreadId: string | null;
  isConnecting: boolean;
  isResetting: boolean;
  isSaving: boolean;
  connectionError: string | null;
  messagesError: string | null;
  onConnect: () => void;
  onReset: () => void;
  onToggleAutoReply: (value: boolean) => void;
  onSelectThread: (threadId: string) => void;
  onRefresh: () => void;
}) {
  const autoReplyEnabled = settings?.auto_reply_enabled ?? false;
  const replyScopeLabel = status?.reply_scope === "all_direct_contacts" ? "Todos os contatos diretos" : "Escopo legado";
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? threads[0] ?? null;
  const sessionStartedLabel = activeSession?.started_at ? formatDateTime(activeSession.started_at) : "Sem sessao ativa";
  const sessionLastActivityLabel = activeSession?.last_activity_at ? formatDateTime(activeSession.last_activity_at) : "Sem atividade";
  const connectedNumber = status?.owner_number ?? "Aguardando leitura";
  const connectionModeLabel = status?.connected ? "Online" : statusLabel;
  const replyModeLabel = autoReplyEnabled ? "Ativa" : "Desativada";
  const learnedCountLabel = String(contactMemory?.learned_message_count ?? 0);
  const memorySummary = contactMemory?.profile_summary?.trim()
    ? contactMemory.profile_summary.trim()
    : "Sem resumo duravel salvo ainda para este contato. Quando o dono repetir preferencias, objetivos ou restricoes, o agente passa a consolidar isso aqui.";
  const activeThreadLastTouch = activeThread?.session_last_activity_at ?? activeThread?.last_message_at ?? null;
  const memoryHighlights = [
    ...(contactMemory?.preferences ?? []),
    ...(contactMemory?.objectives ?? []),
    ...(contactMemory?.durable_facts ?? []),
    ...(contactMemory?.recurring_instructions ?? []),
    ...(contactMemory?.constraints ?? []),
  ].slice(0, 8);

  return (
    <div className="page-stack agent-page">
      <Card className="agent-command-deck">
        <div className="agent-command-copy">
          <div className="agent-command-kicker">
            <span className={`agent-state-pill${status?.connected ? " agent-state-live" : ""}`}>{connectionModeLabel}</span>
            <span className="agent-state-note">Canal de atendimento separado do observador</span>
          </div>
          <h2>WhatsApp Agente</h2>
          <p className="lead-copy">
            O numero secundario responde pelo proprio canal do agente e atende qualquer conversa direta individual recebida nele.
          </p>
          <div className="agent-command-actions">
            <button className="ac-primary-button" onClick={onConnect} disabled={isConnecting || viewState === "connected"} type="button">
              <RefreshCw size={15} className={isConnecting ? "spin" : ""} />
              {viewState === "connected" ? "Agente conectado" : isConnecting ? "Gerando QR..." : "Gerar novo QR"}
            </button>
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar status
            </button>
            <button
              className={autoReplyEnabled ? "ac-danger-button" : "ac-success-button"}
              onClick={() => onToggleAutoReply(!autoReplyEnabled)}
              disabled={isSaving || !status?.connected}
              type="button"
            >
              <Bot size={15} />
              {autoReplyEnabled ? "Desativar respostas" : "Ativar respostas"}
            </button>
          </div>
        </div>

        <div className="agent-command-metrics">
          <AgentMetricPanel
            label="Numero do agente"
            value={connectedNumber}
            meta={status?.connected ? "Sessao conectada no canal secundario" : "Leia o QR para conectar"}
          />
          <AgentMetricPanel
            label="Escopo de resposta"
            value={replyScopeLabel}
            meta="Qualquer conversa direta individual pode receber resposta automatica"
          />
          <AgentMetricPanel
            label="Resposta automatica"
            value={replyModeLabel}
            meta={autoReplyEnabled ? "Groq responde no proprio WhatsApp agente" : "Fluxo em modo manual"}
          />
          <AgentMetricPanel
            label="Memoria aprendida"
            value={learnedCountLabel}
            meta={contactMemory ? "Itens relevantes guardados para este contato" : "Nada aprendido ainda"}
          />
        </div>
      </Card>

      <div className="agent-workspace-grid">
        <Card className="agent-connection-card">
          <div className="agent-card-heading">
            <SectionTitle title="Conexao e QR" icon={Bot} />
            <div className="agent-qr-badge">
              <Clock size={12} />
              {status?.connected ? "Sessao ativa" : status?.qr_expires_in_sec ? `Expira em ${status.qr_expires_in_sec}s` : "Sem QR ativo"}
            </div>
          </div>

          <div className="agent-connection-layout">
            <div className="agent-qr-column">
              <div className="qr-display-shell agent-qr-shell">
                {status?.qr_code ? (
                  <div className="qr-modern-frame">
                    <img className="qr-modern-image" src={status.qr_code} alt="QR Code do WhatsApp agente" />
                  </div>
                ) : (
                  <div className="qr-modern-empty">
                    <Bot size={28} />
                    <strong>QR indisponivel</strong>
                    <p>
                      {status?.connected
                        ? "A sessao ja esta conectada. Nao e necessario gerar um novo QR."
                        : "Gere uma nova sessao para exibir o QR do agente."}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="agent-connection-details">
              <p className="support-copy">
                O observador continua cuidando de memoria e ingestao. Este painel existe so para operar o canal ativo do agente sem misturar os dois papeis.
              </p>
              <div className="agent-status-grid">
                <StatusLine label="Gateway" value={status?.gateway_ready ? "Baileys online" : "Indisponivel"} tone="emerald" />
                <StatusLine label="Sessao" value={connectedNumber} tone="indigo" />
                <StatusLine label="Escopo de resposta" value={replyScopeLabel} tone="amber" />
                <StatusLine label="Ultima atividade" value={formatDateTime(status?.last_seen_at)} tone="zinc" />
              </div>
              <div className="agent-note-panel">
                <strong>Regra central</strong>
                <p>O agente responde qualquer conversa direta individual recebida neste numero. Grupos e mensagens do proprio numero continuam ignorados.</p>
              </div>
            </div>
          </div>
        </Card>

        <Card className="agent-operations-card">
          <SectionTitle title="Operacao do agente" icon={Server} />
          <div className="agent-operations-grid">
            <div className="agent-summary-panel">
              <span>Sessao logica da conversa</span>
              <strong>{activeSession ? "Sessao aberta" : "Aguardando nova conversa"}</strong>
              <p>
                {activeSession
                  ? `Iniciada em ${sessionStartedLabel} e com ultima atividade em ${sessionLastActivityLabel}.`
                  : "Depois de 10 minutos sem conversa, o contexto reinicia e a proxima mensagem abre uma nova sessao."}
              </p>
            </div>
            <div className="agent-summary-panel">
              <span>Memoria propria do agente</span>
              <strong>{contactMemory ? "Resumo disponivel" : "Ainda sem perfil salvo"}</strong>
              <p>{memorySummary}</p>
            </div>
          </div>

          {memoryHighlights.length > 0 ? (
            <div className="agent-chip-cloud">
              {memoryHighlights.map((item, index) => (
                <span key={`${item}-${index}`} className="agent-memory-chip">{item}</span>
              ))}
            </div>
          ) : null}

          <div className="agent-danger-strip">
            <div>
              <strong>Zona de perigo</strong>
              <p>Resetar a sessao do agente apaga as chaves atuais e exige um novo QR.</p>
            </div>
            <button className="ac-danger-button" onClick={onReset} disabled={isResetting} type="button">
              <XCircle size={15} />
              {isResetting ? "Resetando..." : "Resetar sessao do agente"}
            </button>
          </div>
        </Card>
      </div>

      <div className="agent-inbox-grid">
        <Card className="agent-list-card">
          <div className="agent-list-header">
            <SectionTitle title="Conversas recentes" icon={MessageSquare} />
            <span>{threads.length} ativas</span>
          </div>
          {threads.length === 0 ? (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Nenhuma conversa registrada ainda.</p>
            </div>
          ) : (
            <div className="agent-thread-list">
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  className={`agent-thread-row${thread.id === activeThread?.id ? " agent-thread-row-active" : ""}`}
                  onClick={() => onSelectThread(thread.id)}
                  type="button"
                >
                  <div className="agent-thread-main">
                    <strong>{thread.contact_name || thread.contact_phone || "Contato"}</strong>
                    <span>{thread.last_message_preview ?? "Sem mensagem recente"}</span>
                  </div>
                  <div className="agent-thread-meta">
                    <span>{thread.active_session_id ? "sessao aberta" : thread.status}</span>
                    <small>
                      {thread.session_started_at
                        ? `sessao ${formatDateTime(thread.session_started_at)}`
                        : thread.last_message_at
                          ? formatDateTime(thread.last_message_at)
                          : "Sem data"}
                    </small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card className="agent-detail-card">
          <div className="agent-detail-header">
            <div>
              <SectionTitle title="Historico do agente" icon={Bot} />
              <p className="support-copy">
                {activeThread
                  ? `Contato atual: ${activeThread.contact_name || activeThread.contact_phone || "Contato sem nome"}`
                  : "Selecione uma thread para abrir o historico completo do agente."}
              </p>
            </div>
            <div className="agent-detail-meta">
              <span>{activeThread?.active_session_id ? "Sessao em andamento" : "Sem sessao aberta"}</span>
              <strong>{activeThreadLastTouch ? formatDateTime(activeThreadLastTouch) : "Sem atividade"}</strong>
            </div>
          </div>

          {contactMemory ? (
            <div className="agent-memory-summary">
              <div className="agent-memory-summary-copy">
                <span>Memoria duravel desta relacao</span>
                <p>{memorySummary}</p>
              </div>
              {memoryHighlights.length > 0 ? (
                <div className="agent-chip-cloud">
                  {memoryHighlights.map((item, index) => (
                    <span key={`${item}-detail-${index}`} className="agent-memory-chip">{item}</span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {activeThread ? (
            <div className="agent-message-stack">
              {messages.length === 0 ? (
                <div className="empty-hint">
                  <MessageSquare size={18} />
                  <p>Sem mensagens ainda para esta conversa.</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`agent-message-bubble agent-message-${msg.role}`}>
                    <div className="agent-message-top">
                      <strong>{msg.role === "assistant" ? "Agente" : "Contato"}</strong>
                      <span>{formatDateTime(msg.message_timestamp)}</span>
                    </div>
                    <p>{msg.content}</p>
                    <small>{msg.processing_status}{msg.send_status ? ` | ${msg.send_status}` : ""}</small>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Selecione um contato para ver as mensagens.</p>
            </div>
          )}
        </Card>
      </div>

      {connectionError ? <InlineError title={`Falha do agente (${statusLabel})`} message={connectionError} /> : null}
      {messagesError ? <InlineError title="Falha nas mensagens do agente" message={messagesError} /> : null}
    </div>
  );
}

function GroupsTab({
  groups,
  error,
  isSavingJids,
  onToggleGroup,
  onRefresh,
}: {
  groups: WhatsAppGroupSelection[];
  error: string | null;
  isSavingJids: string[];
  onToggleGroup: (chatJid: string, enabledForAnalysis: boolean) => Promise<void>;
  onRefresh: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedJids, setSelectedJids] = useState<Set<string>>(new Set());
  const deferredSearch = useDeferredValue(search);
  const filteredGroups = useMemo(() => {
    let result = groups;
    if (filter === "active") result = result.filter(g => g.enabled_for_analysis);
    else if (filter === "inactive") result = result.filter(g => !g.enabled_for_analysis);
    else if (filter === "pending") result = result.filter(g => g.pending_message_count > 0);

    const query = deferredSearch.trim().toLowerCase();
    if (query) {
      result = result.filter((group) => (
        group.chat_name.toLowerCase().includes(query) ||
        group.chat_jid.toLowerCase().includes(query)
      ));
    }
    return result;
  }, [groups, deferredSearch, filter]);
  const enabledCount = groups.filter((group) => group.enabled_for_analysis).length;

  const handleSelectAll = () => {
    if (selectedJids.size === filteredGroups.length) {
      setSelectedJids(new Set());
    } else {
      setSelectedJids(new Set(filteredGroups.map(g => g.chat_jid)));
    }
  };

  const handleToggleSelection = (jid: string) => {
    const next = new Set(selectedJids);
    if (next.has(jid)) next.delete(jid);
    else next.add(jid);
    setSelectedJids(next);
  };

  const executeMassAction = async (activate: boolean) => {
    if (selectedJids.size === 0) return;
    const toastId = toast.loading("Processando...");
    try {
      const promises = Array.from(selectedJids).map(jid => {
        const group = groups.find(g => g.chat_jid === jid);
        if (group && group.enabled_for_analysis !== activate) {
          return onToggleGroup(jid, activate);
        }
        return Promise.resolve();
      });
      await Promise.all(promises);
      toast.success(`${selectedJids.size} grupo(s) modificado(s)!`, { id: toastId });
      setSelectedJids(new Set());
    } catch (e) {
      toast.error("Alguns grupos falharam.", { id: toastId });
    }
  };

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle title="Grupos para Analise" icon={Users} />
        <p className="support-copy">
          Os grupos abaixo aparecem sempre desativados por padrão. Ative apenas os que realmente devem entrar
          nas leituras futuras de memória.
        </p>
        <div className="groups-banner">
          <strong>Regra fixa:</strong>
          <span>A primeira analise nunca usa grupos. Esta seleção só vale para atualizações futuras da memória.</span>
        </div>
        <div className="memory-breakdown-grid">
          <MemorySignalCard
            label="Grupos observados"
            value={formatTokenCount(groups.length)}
            meta="Lista montada a partir do histórico já sincronizado pelo observador."
            tone="indigo"
          />
          <MemorySignalCard
            label="Grupos ativos"
            value={formatTokenCount(enabledCount)}
            meta="Somente estes grupos podem entrar nas leituras incrementais."
            tone="emerald"
          />
          <MemorySignalCard
            label="Pendências em grupos ativos"
            value={formatTokenCount(groups.filter((group) => group.enabled_for_analysis).reduce((sum, group) => sum + group.pending_message_count, 0))}
            meta="Mensagens de grupo elegíveis que ainda não passaram por análise."
            tone="amber"
          />
        </div>
      </Card>

      <Card>
        <div className="groups-toolbar">
          <div>
            <SectionTitle title="Selecao de Grupos" icon={Database} />
            <p className="support-copy">
              O DeepSeek passa a enxergar corretamente grupo e participante no contexto incremental, sem contaminar o bootstrap inicial.
            </p>
          </div>
          <button className="ac-secondary-button" onClick={onRefresh} type="button">
            <RefreshCw size={15} />
            Atualizar lista
          </button>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <input
            className="ac-input groups-search-input"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome do grupo ou JID..."
            type="text"
            value={search}
            style={{ flex: 1, margin: 0 }}
          />
          <SegmentedControl 
            options={["Todos", "Ativos", "Desativados", "Com Pendências"]} 
            selected={filter === "all" ? "Todos" : filter === "active" ? "Ativos" : filter === "inactive" ? "Desativados" : "Com Pendências"}
            onChange={(sel) => setFilter(sel === "Todos" ? "all" : sel === "Ativos" ? "active" : sel === "Desativados" ? "inactive" : "pending")}
          />
        </div>

        {selectedJids.size > 0 && (
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', background: 'var(--zinc-800)', padding: '0.5rem', borderRadius: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--zinc-400)', marginRight: 'auto' }}>{selectedJids.size} selecionado(s)</span>
            <button className="ac-secondary-button" onClick={() => executeMassAction(true)}>
              <CheckCircle2 size={16} style={{ color: 'var(--emerald-500)' }}/> Ativar
            </button>
            <button className="ac-secondary-button" onClick={() => executeMassAction(false)}>
              <XCircle size={16} style={{ color: 'var(--zinc-500)' }}/> Desativar
            </button>
          </div>
        )}

        {filteredGroups.length === 0 ? (
          <div className="empty-hint">
            <Users size={18} />
            <p>
              {groups.length === 0
                ? "Nenhum grupo apareceu no histórico sincronizado ainda."
                : "Nenhum grupo bateu com a busca atual."}
            </p>
          </div>
        ) : (
          <div className="groups-list">
            {filteredGroups.map((group) => {
              const isSaving = isSavingJids.includes(group.chat_jid);
              return (
                <div key={group.chat_jid} className={`group-row${group.enabled_for_analysis ? " group-row-enabled" : ""}`}>
                  <input
                    type="checkbox"
                    checked={selectedJids.has(group.chat_jid)}
                    onChange={() => handleToggleSelection(group.chat_jid)}
                    style={{ marginRight: '1rem', cursor: 'pointer', accentColor: 'var(--indigo-500)', width: '18px', height: '18px' }}
                  />
                  <div className="group-row-main" style={{ marginLeft: '1rem' }}>
                    <div className="group-row-top">
                      <strong>{group.chat_name}</strong>
                      <span>{group.enabled_for_analysis ? "ativo para analise" : "desativado"}</span>
                    </div>
                    <p>{group.chat_jid}</p>
                    <div className="group-row-meta">
                      <span>{formatTokenCount(group.message_count)} mensagens salvas</span>
                      <span>{formatTokenCount(group.pending_message_count)} pendentes</span>
                      <span>{group.last_message_at ? `Ultima mensagem ${formatDateTime(group.last_message_at)}` : "Sem mensagem recente"}</span>
                    </div>
                  </div>
                  <button
                    className={`group-toggle${group.enabled_for_analysis ? " group-toggle-enabled" : ""}`}
                    disabled={isSaving}
                    onClick={() => {
                      if (!isSaving) {
                        onToggleGroup(group.chat_jid, !group.enabled_for_analysis);
                        toast.success(group.enabled_for_analysis ? "Grupo desativado" : "Grupo ativado");
                      }
                    }}
                    type="button"
                  >
                    {isSaving ? <span className="ac-spinner" style={{ marginRight: 8, width: 14, height: 14 }} /> : null}
                    <span>{group.enabled_for_analysis ? "Ativado" : "Ativar"}</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {error ? <InlineError title="Falha ao carregar grupos" message={error} /> : null}
    </div>
  );
}

function MemoryTab({
  memoryStatus,
  memory,
  latestSnapshot,
  memoryActivity,
  memoryError,
  agentState,
  steps,
  logs,
  projectsCount,
  snapshotsCount,
  automationStatus,
  automationError,
  isClearingDatabase,
  queuedJobId,
  onInitialAnalysis,
  onImproveMemory,
  onClearDatabase,
}: {
  memoryStatus: MemoryStatus | null;
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  memoryActivity: MemoryActivity | null;
  memoryError: string | null;
  agentState: DisplayAgentState;
  steps: AgentStep[];
  logs: AgentLog[];
  projectsCount: number;
  snapshotsCount: number;
  automationStatus: AutomationStatus | null;
  automationError: string | null;
  isClearingDatabase: boolean;
  queuedJobId: string | null;
  onInitialAnalysis: () => void;
  onImproveMemory: () => void;
  onClearDatabase: () => void;
}) {
  const [memorySubTab, setMemorySubTab] = useState<"overview" | "profile" | "snapshot" | "pipeline">("overview");
  const memoryReady = memoryStatus?.has_initial_analysis ?? false;
  const structuralStrengths = memory?.structural_strengths ?? [];
  const structuralRoutines = memory?.structural_routines ?? [];
  const structuralPreferences = memory?.structural_preferences ?? [];
  const structuralOpenQuestions = memory?.structural_open_questions ?? [];
  const pendingNewMessages = memoryStatus?.new_messages_after_first_analysis ?? 0;
  const currentJob = memoryStatus?.current_job ?? null;
  const latestCompletedJob = memoryStatus?.latest_completed_job ?? null;
  const canExecuteAnalysis = memoryStatus?.can_execute_analysis ?? false;
  const currentJobIsPending = currentJob?.status === "queued" || currentJob?.status === "running";
  const autoInitialSyncInProgress = !memoryReady && (memoryStatus?.sync_in_progress ?? false);
  const hasPendingJob = currentJobIsPending || !!queuedJobId || autoInitialSyncInProgress;
  const latestSyncRun = memoryActivity?.sync_runs[0] ?? null;
  const latestJob = memoryActivity?.jobs[0] ?? latestCompletedJob;
  const latestModelRun = memoryActivity?.model_runs[0] ?? null;
  const latestSnapshotCoverageTone = getSnapshotCoverageTone(latestSnapshot);
  const traceItems = buildActivityTrace({
    agentState,
    latestSyncRun,
    latestDecision: null,
    latestJob,
    latestModelRun,
  }).slice(0, 4);
  const displayedLogs = logs.slice(0, 8);
  const memorySubTabs = [
    { id: "overview" as const, label: "Painel", icon: Database },
    { id: "profile" as const, label: "Perfil", icon: Fingerprint },
    { id: "snapshot" as const, label: "Janela", icon: FileText },
    { id: "pipeline" as const, label: "Pipeline", icon: Activity },
  ];
  const executeLabel = !memoryReady
    ? pendingNewMessages > 0
      ? `Fazer Primeira Analise (${formatTokenCount(pendingNewMessages)} mensagens disponiveis)`
      : "Fazer Primeira Analise"
    : pendingNewMessages > 0
      ? `Executar Analise (${formatTokenCount(pendingNewMessages)} novas)`
      : "Aguardando mensagens novas";
  const blockedReason = autoInitialSyncInProgress
    ? "O backend ainda está fechando a coleta inicial automática do WhatsApp. A primeira análise será colocada na fila sozinha assim que esse lote for persistido."
    : currentJobIsPending
    ? currentJob.intent === "first_analysis"
      ? currentJob.status === "queued"
        ? "A primeira analise ja foi colocada na fila automatica pelo backend."
        : "A primeira analise ja foi iniciada automaticamente pelo backend usando o lote inicial do WhatsApp."
      : currentJob.status === "queued"
        ? "Ja existe uma atualizacao de memoria na fila."
        : "Ja existe uma atualizacao de memoria em andamento."
    : !canExecuteAnalysis
      ? !memoryReady
        ? "Ainda nao ha mensagens textuais novas disponiveis para criar a base inicial."
        : pendingNewMessages > 0
          ? "Ainda nao ha sinal suficiente para rodar o proximo lote manual."
          : "Ainda nao ha mensagens novas pendentes para atualizar a memoria."
      : null;

  return (
    <div className="page-stack">
      <Card className="memory-shell-card">
        <div className="memory-shell-head">
          <div>
            <div className="hero-kicker">
              <Database size={14} />
              Central de Memória
            </div>
            <h3>Memória, progresso e manutenção agora vivem no mesmo lugar.</h3>
            <p className="support-copy">
              Separei o fluxo em painéis menores para deixar claro o que já foi consolidado, o que ainda está chegando e como o pipeline está se comportando em tempo real.
            </p>
          </div>
          <div className="memory-shell-status">
            <span className={`micro-status micro-status-${agentState.running || hasPendingJob ? "teal" : "zinc"}`}>
              {agentState.running || hasPendingJob ? "pipeline ativo" : "monitorando"}
            </span>
            <span className={`micro-status micro-status-${memoryReady ? "emerald" : "amber"}`}>
              {memoryReady ? "base criada" : "base pendente"}
            </span>
          </div>
        </div>

        <div className="memory-shell-tabs">
          {memorySubTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`activity-subtab${memorySubTab === tab.id ? " activity-subtab-active" : ""}`}
                onClick={() => setMemorySubTab(tab.id)}
                type="button"
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </Card>

      {memorySubTab === "overview" ? (
        <>
          <div className="memory-breakdown-grid">
            <MemorySignalCard
              label="Status da memoria"
              value={memoryReady ? "Base criada" : "Primeira analise pendente"}
              meta={
                memoryStatus?.last_analyzed_at
                  ? `Ultima atualizacao em ${formatDateTime(memoryStatus.last_analyzed_at)}`
                  : "Ainda sem consolidacao inicial"
              }
              accent
            />
            <MemorySignalCard
              label="Mensagens novas"
              value={formatTokenCount(pendingNewMessages)}
              meta={memoryReady ? "Diretas recebidas e enviadas desde a ultima analise" : "Mensagens disponiveis para criar a base inicial"}
              tone="indigo"
            />
            <MemorySignalCard
              label="Job atual"
              value={currentJob ? formatState(currentJob.status) : "Livre"}
              meta={
                currentJob
                  ? `${getIntentTitle(currentJob.intent as AgentIntent)} • ${formatShortDateTime(currentJob.created_at)}`
                  : "Nenhuma analise em execucao no momento"
              }
              tone="amber"
            />
            <MemorySignalCard
              label="Ultimo job concluido"
              value={latestCompletedJob ? formatState(latestCompletedJob.status) : "--"}
              meta={
                latestCompletedJob
                  ? `${getIntentTitle(latestCompletedJob.intent as AgentIntent)} • ${formatShortDateTime(latestCompletedJob.finished_at ?? latestCompletedJob.created_at)}`
                  : "Nenhuma execucao concluida ainda"
              }
              tone="emerald"
            />
          </div>

          <div className="memory-surface-grid">
            <Card className="memory-panel-card">
              <SectionTitle title="Ações" icon={Zap} />
              {!memoryReady ? (
                <div className="memory-inline-stack">
                  <p className="support-copy">
                    A primeira analise mistura recencia, diversidade de contatos e mensagens do proprio dono para montar uma base inicial menos enviesada.
                  </p>
                  <button
                    className="ac-success-button"
                    onClick={onInitialAnalysis}
                    disabled={agentState.running || hasPendingJob || !canExecuteAnalysis}
                    type="button"
                  >
                    <Play size={15} />
                    {currentJobIsPending
                      ? currentJob.status === "queued"
                        ? "Primeira analise na fila..."
                        : "Primeira analise em andamento..."
                      : agentState.running && agentState.intent === "first_analysis"
                        ? "Executando..."
                        : !!queuedJobId
                          ? "Aguardando fila..."
                          : executeLabel}
                  </button>
                  {blockedReason ? <p className="support-copy">{blockedReason}</p> : null}
                </div>
              ) : (
                <div className="memory-inline-stack">
                  <p className="support-copy">
                    O refinamento incremental reaproveita a memória já salva e processa apenas o lote novo pendente.
                  </p>
                  <button
                    className="ac-primary-button"
                    onClick={onImproveMemory}
                    disabled={agentState.running || hasPendingJob || !canExecuteAnalysis}
                    type="button"
                  >
                    <Sparkles size={15} />
                    {currentJobIsPending
                      ? currentJob.status === "queued"
                        ? "Atualizacao na fila..."
                        : "Atualizacao em andamento..."
                      : agentState.running && agentState.intent === "improve_memory"
                        ? "Processando..."
                        : !!queuedJobId
                          ? "Fila ativa..."
                          : executeLabel}
                  </button>
                  {blockedReason ? <p className="support-copy">{blockedReason}</p> : null}
                </div>
              )}
            </Card>

            <Card className="memory-panel-card">
              <SectionTitle title="Pulso do Pipeline" icon={Cpu} />
              <p className="support-copy">
                O backend avança sozinho entre fila, execução e conclusão. Este resumo reflete o estado real persistido.
              </p>
              <div className="step-pill-row">
                {steps.map((step, stepIndex) => {
                  const { completed, active } = getStepVisualState(agentState, stepIndex, steps.length);
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
              <div className="activity-trace-list">
                {traceItems.length > 0 ? (
                  traceItems.map((item) => (
                    <div key={item.id} className={`activity-trace-item activity-trace-${item.tone}`}>
                      <div className="activity-trace-dot" />
                      <div className="activity-trace-content">
                        <div className="activity-trace-top">
                          <strong>{item.title}</strong>
                          <span>{item.timestamp ? formatShortDateTime(item.timestamp) : "Agora"}</span>
                        </div>
                        <p>{item.detail}</p>
                        <div className="activity-trace-meta">
                          <span>{getActivityToneLabel(item.tone)}</span>
                          {item.meta ? <span>{item.meta}</span> : null}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty-hint">
                    <Terminal size={18} />
                    <p>Nenhum evento recente ainda. Assim que a análise começar, a linha do tempo aparece aqui.</p>
                  </div>
                )}
              </div>
            </Card>
          </div>

          <div className="terminal-shell activity-terminal-shell">
            <div className="terminal-header activity-terminal-header">
              <div className="activity-terminal-leds">
                <span className="terminal-dot terminal-dot-red" />
                <span className="terminal-dot terminal-dot-yellow" />
                <span className="terminal-dot terminal-dot-green" />
              </div>
              <div className="activity-terminal-titles">
                <strong>memory-analysis.log</strong>
                <span>eventos reais e estados interpretados do pipeline</span>
              </div>
              <span className={`micro-status micro-status-${agentState.running || hasPendingJob ? "indigo" : "zinc"}`}>
                {agentState.running || hasPendingJob ? "auto-refresh ligado" : "monitorando"}
              </span>
            </div>
            <div className="terminal-body">
              {displayedLogs.length > 0 ? (
                displayedLogs.map((log) => (
                  <div key={log.id} className={`terminal-line activity-terminal-line activity-terminal-${log.tone}`}>
                    <span className="terminal-time">{formatShortDateTime(log.createdAt)}</span>
                    <span>{log.message}</span>
                  </div>
                ))
              ) : (
                <div className="empty-hint">
                  <Terminal size={18} />
                  <p>Sem logs recentes por enquanto.</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : null}

      {memorySubTab === "profile" ? (
        <>
          <Card>
            <SectionTitle title="Memoria Atual do Dono" icon={Fingerprint} />
            <p className="lead-copy">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Nenhum resumo consolidado ainda. Assim que a primeira leitura rodar, este bloco vira a visao mais util do dono para o chat e para futuras atualizacoes manuais."}
            </p>
          </Card>

          <Card>
            <SectionTitle title="Mapa Estrutural Cumulativo" icon={Brain} />
            <div className="dual-column-grid">
              <div className="signal-cluster">
                <SignalBlock
                  title="Forcas recorrentes"
                  lines={structuralStrengths}
                  emptyLabel="Sem forcas recorrentes consolidadas ainda."
                />
                <SignalBlock
                  title="Rotina detectada"
                  lines={structuralRoutines}
                  emptyLabel="Sem rotina consolidada ainda."
                />
              </div>
              <div className="signal-cluster">
                <SignalBlock
                  title="Preferencias operacionais"
                  lines={structuralPreferences}
                  emptyLabel="Sem preferencias fortes consolidadas ainda."
                  subtle
                />
                <SignalBlock
                  title="Lacunas ainda abertas"
                  lines={structuralOpenQuestions}
                  emptyLabel="Sem lacunas importantes em aberto."
                  subtle
                />
              </div>
            </div>
          </Card>
        </>
      ) : null}

      {memorySubTab === "snapshot" ? (
        <Card>
          <SectionTitle title="Ultima Janela Recente" icon={FileText} />
          {latestSnapshot ? (
            <div className="manual-list">
              <p>{latestSnapshot.window_summary}</p>
              <p>
                Baseado em {formatTokenCount(latestSnapshot.source_message_count)} mensagens entre{" "}
                {formatDateTime(latestSnapshot.window_start)} e {formatDateTime(latestSnapshot.window_end)}.
              </p>
              <div className="memory-breakdown-grid">
                <MemorySignalCard
                  label="Cobertura do lote"
                  value={`${latestSnapshot.coverage_score}/100`}
                  meta={`${getSnapshotCoverageLabel(latestSnapshot)} com ${formatTokenCount(latestSnapshot.distinct_contact_count)} contatos distintos.`}
                  tone={latestSnapshotCoverageTone}
                />
                <MemorySignalCard
                  label="Direcao das mensagens"
                  value={formatSnapshotDirectionMix(latestSnapshot)}
                  meta="Ajuda a separar o que o dono afirma, pede e decide do que foi dito pelos contatos."
                  tone="indigo"
                />
                <MemorySignalCard
                  label="Amplitude temporal"
                  value={`${formatTokenCount(latestSnapshot.window_hours)}h`}
                  meta="A primeira leitura tenta cobrir curto prazo e historico recente para nao nascer viciada em um unico momento."
                  tone="amber"
                />
              </div>
              <p>Este bloco mostra somente a janela mais recente. O retrato cumulativo do dono fica na aba Perfil.</p>
            </div>
          ) : (
            <div className="empty-hint">
              <Database size={18} />
              <p>Sem snapshot ainda. A primeira leitura vai criar a base consolidada do dono com um lote inicial balanceado.</p>
            </div>
          )}
        </Card>
      ) : null}

      {memorySubTab === "pipeline" ? (
        <ActivityTab
          agentState={agentState}
          steps={steps}
          logs={logs}
          memory={memory}
          latestSnapshot={latestSnapshot}
          projectsCount={projectsCount}
          snapshotsCount={snapshotsCount}
          automationStatus={automationStatus}
          automationError={automationError}
          isClearingDatabase={isClearingDatabase}
          onClearDatabase={onClearDatabase}
          embedded
        />
      ) : null}

      {memoryError ? <InlineError title="Falha na memoria" message={memoryError} /> : null}
    </div>
  );
}

function RelationsTab({
  relations,
  error,
  onRefresh,
  onSaveRelation,
}: {
  relations: PersonRelation[];
  error: string | null;
  onRefresh: () => void;
  onSaveRelation: (contactName: string, input: { contact_name?: string; relationship_type?: string }) => Promise<void>;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<
    "all"
    | "with_open_loops"
    | "partner"
    | "family"
    | "friend"
    | "work"
    | "client"
        | "service"
    | "acquaintance"
    | "other"
    | "unknown"
  >("all");
  const [editingRelationId, setEditingRelationId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState("");

  const deferredSearch = useDeferredValue(search.trim());
  const normalizedSearch = useMemo(() => normalizeProjectSearchText(deferredSearch), [deferredSearch]);

  const sortedRelations = useMemo(
    () =>
      [...relations].sort((left, right) => {
        const priorityDelta = getRelationSortPriority(left.relationship_type) - getRelationSortPriority(right.relationship_type);
        if (priorityDelta !== 0) {
          return priorityDelta;
        }
        const leftTime = new Date(left.last_message_at ?? left.updated_at).getTime();
        const rightTime = new Date(right.last_message_at ?? right.updated_at).getTime();
        return rightTime - leftTime;
      }),
    [relations],
  );

  const filteredRelations = useMemo(
    () =>
      sortedRelations.filter((relation) => {
        const matchesFilter =
          filter === "all"
            ? true
            : filter === "with_open_loops"
              ? relation.open_loops.length > 0
              : normalizeRelationType(relation.relationship_type) === filter;
        if (!matchesFilter) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        const haystack = normalizeProjectSearchText(
          [
            relation.contact_name,
            relation.contact_phone ?? "",
            relation.chat_jid ?? "",
            relation.profile_summary,
            relation.relationship_summary,
            relation.relationship_type,
            relation.salient_facts.join(" "),
            relation.open_loops.join(" "),
            relation.recent_topics.join(" "),
          ].join(" "),
        );
        return haystack.includes(normalizedSearch);
      }),
    [filter, normalizedSearch, sortedRelations],
  );

  const closeCircleCount = useMemo(
    () =>
      relations.filter((relation) => {
        const type = normalizeRelationType(relation.relationship_type);
        return type === "partner" || type === "family" || type === "friend";
      }).length,
    [relations],
  );
  const operatingCircleCount = useMemo(
    () =>
      relations.filter((relation) => {
        const type = normalizeRelationType(relation.relationship_type);
        return type === "work" || type === "client" || type === "service";
      }).length,
    [relations],
  );
  const withOpenLoopsCount = useMemo(
    () => relations.filter((relation) => relation.open_loops.length > 0).length,
    [relations],
  );
  const typedCount = useMemo(
    () => relations.filter((relation) => normalizeRelationType(relation.relationship_type) !== "unknown").length,
    [relations],
  );
  const latestTouchedRelation = filteredRelations[0] ?? sortedRelations[0] ?? null;

  const filterOptions = useMemo(
    () => {
      const orderedTypes = ["partner", "family", "friend", "work", "client", "service", "acquaintance", "other", "unknown"] as const;
      const counts = new Map<string, number>();
      for (const relation of relations) {
        const type = normalizeRelationType(relation.relationship_type);
        counts.set(type, (counts.get(type) ?? 0) + 1);
      }
      const dynamicOptions = orderedTypes
        .map((type) => ({ id: type, label: getRelationTypeLabel(type), count: counts.get(type) ?? 0 }))
        .filter((option) => option.count > 0);
      return [
        { id: "all" as const, label: "Todos", count: relations.length },
        { id: "with_open_loops" as const, label: "Com pendências", count: withOpenLoopsCount },
        ...dynamicOptions,
      ];
    },
    [relations, withOpenLoopsCount],
  );

  if (relations.length === 0) {
    return (
      <div className="page-stack">
        <Card className="proj-empty-hero">
          <div className="proj-empty-icon">
            <Users size={40} />
          </div>
          <h3>Nenhuma relação consolidada ainda</h3>
          <p>Depois da próxima atualização de memória, os contatos relevantes passam a aparecer aqui com tipo de vínculo, dinâmica atual, fatos duráveis e pendências abertas.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <Card className="relations-hero-card">
        <div className="relations-hero-copy">
          <div className="hero-kicker">
            <Sparkles size={14} />
            Mapa social do dono
          </div>
          <h3>Relações que a memória está consolidando</h3>
          <p>
            A cada atualização de memória, o backend refina quem é cada pessoa, qual é o tipo de vínculo e o estado atual da relação. Esta aba mostra esse retrato vivo sem depender de passos inventados.
          </p>
        </div>
        <div className="relations-hero-metrics">
          <div className="relations-hero-metric">
            <span>Pessoas mapeadas</span>
            <strong>{relations.length}</strong>
            <small>{typedCount} já têm tipo de relação claro</small>
          </div>
          <div className="relations-hero-metric">
            <span>Círculo pessoal</span>
            <strong>{closeCircleCount}</strong>
            <small>par, família e amizades</small>
          </div>
          <div className="relations-hero-metric">
            <span>Frente operacional</span>
            <strong>{operatingCircleCount}</strong>
            <small>trabalho, clientes e serviços</small>
          </div>
          <div className="relations-hero-metric">
            <span>Pendências abertas</span>
            <strong>{withOpenLoopsCount}</strong>
            <small>{latestTouchedRelation ? `último contato forte: ${latestTouchedRelation.contact_name}` : "sem destaques recentes"}</small>
          </div>
        </div>
      </Card>

      <Card className="relations-toolbar-card">
        <div className="relations-toolbar">
          <label className="relation-search-shell">
            <Search size={16} />
            <input
              className="ac-input relation-search-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por nome, resumo, fatos, pendências ou tópicos..."
              type="text"
              value={search}
            />
          </label>

          <div className="relation-filter-row">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`relation-filter-chip${filter === option.id ? " relation-filter-chip-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>

        {error ? <InlineError title="Falha ao carregar relações" message={error} /> : null}
      </Card>

      <div className="proj-stats-row">
        <ModernStatCard label="Visíveis agora" value={String(filteredRelations.length)} meta="Resultado do filtro atual" icon={Users} tone="indigo" />
        <ModernStatCard label="Com pendências" value={String(filteredRelations.filter((relation) => relation.open_loops.length > 0).length)} meta="Laços que exigem acompanhamento" icon={AlertCircle} tone="amber" />
        <ModernStatCard label="Categorizadas" value={String(filteredRelations.filter((relation) => normalizeRelationType(relation.relationship_type) !== "unknown").length)} meta="Tipo de relação já inferido" icon={Fingerprint} tone="emerald" />
        <ModernStatCard label="Atualização recente" value={latestTouchedRelation?.last_analyzed_at ? formatRelativeTime(latestTouchedRelation.last_analyzed_at) : "Pendente"} meta={latestTouchedRelation ? latestTouchedRelation.contact_name : "Sem relação recente"} icon={RefreshCw} />
      </div>

      {filteredRelations.length === 0 ? (
        <Card>
          <div className="empty-hint">
            <Users size={18} />
            <p>{normalizedSearch ? "Nenhuma relação bateu com a busca atual." : "Nenhuma relação se encaixa no filtro atual."}</p>
          </div>
        </Card>
      ) : (
        <div className="relation-grid">
          {filteredRelations.map((relation) => {
            const relationType = normalizeRelationType(relation.relationship_type);
            const tone = getRelationTone(relationType);
            const signalStrength = getRelationStrength(relation);
            const identifier = relation.contact_phone ?? relation.chat_jid ?? relation.person_key;
            return (
              <Card key={relation.id} className="relation-card">
                <div className="relation-card-head">
                  <div className={`project-modern-icon project-modern-icon-${tone === "rose" ? "indigo" : tone === "zinc" ? "amber" : tone}`}>
                    <User size={18} />
                  </div>
                  {editingRelationId === relation.id ? (
                    <div className="relation-card-copy" style={{ flex: 1 }}>
                      <input
                        type="text"
                        className="ac-input"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Nome do contato"
                        style={{ marginBottom: "0.25rem", padding: "0.25rem 0.5rem" }}
                      />
                      <div className="relation-card-meta">
                        <select
                          className="ac-input"
                          value={editType}
                          onChange={(e) => setEditType(e.target.value)}
                          style={{ width: "auto", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        >
                          <option value="partner">Parceiro(a)</option>
                          <option value="family">Família</option>
                          <option value="friend">Amigo(a)</option>
                          <option value="work">Trabalho</option>
                          <option value="client">Cliente</option>
                          <option value="service">Serviço</option>
                          <option value="acquaintance">Conhecido(a)</option>
                          <option value="other">Outro</option>
                          <option value="unknown">Desconhecido</option>
                        </select>
                        <span>{identifier}</span>
                        <span>{relation.last_message_at ? formatRelativeTime(relation.last_message_at) : "sem mensagem recente"}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="relation-card-copy">
                      <h3>{relation.contact_name}</h3>
                      <div className="relation-card-meta">
                        <span className={`relation-badge relation-badge-${relationType}`}>{getRelationTypeLabel(relationType)}</span>
                        <span>{identifier}</span>
                        <span>{relation.last_message_at ? formatRelativeTime(relation.last_message_at) : "sem mensagem recente"}</span>
                      </div>
                    </div>
                  )}

                  <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
                    {editingRelationId === relation.id ? (
                      <>
                        <button
                          type="button"
                          className="ac-button ac-button-primary ac-button-sm"
                          onClick={() => {
                            void onSaveRelation(relation.contact_name, { contact_name: editName, relationship_type: editType });
                            setEditingRelationId(null);
                          }}
                        >
                          <Check size={14} />
                        </button>
                        <button
                          type="button"
                          className="ac-button ac-button-outline ac-button-sm"
                          onClick={() => setEditingRelationId(null)}
                        >
                          <X size={14} />
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="ac-button ac-button-outline ac-button-sm"
                        onClick={() => {
                          setEditingRelationId(relation.id);
                          setEditName(relation.contact_name);
                          setEditType(relationType);
                        }}
                      >
                        <Edit2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                <ProgressBar value={signalStrength} tone={tone} label="Força da memória desta relação" />

                <div className="relation-panels">
                  <div className="relation-panel">
                    <span>Quem é</span>
                    <p>{relation.profile_summary || "Ainda sem resumo consolidado."}</p>
                  </div>
                  <div className="relation-panel">
                    <span>Dinâmica atual</span>
                    <p>{relation.relationship_summary || "A dinâmica entre dono e contato ainda está sendo refinada."}</p>
                  </div>
                </div>

                <div className="relation-panels">
                  <div className="relation-panel">
                    <span>Fatos duráveis</span>
                    {relation.salient_facts.length > 0 ? (
                      <ul>
                        {relation.salient_facts.slice(0, 4).map((fact, index) => (
                          <li key={`${relation.id}-fact-${index}`}>{fact}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>Nenhum fato durável consolidado ainda.</p>
                    )}
                  </div>
                  <div className="relation-panel">
                    <span>Pendências abertas</span>
                    {relation.open_loops.length > 0 ? (
                      <ul>
                        {relation.open_loops.slice(0, 4).map((loop, index) => (
                          <li key={`${relation.id}-loop-${index}`}>{loop}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>Sem pendências abertas registradas.</p>
                    )}
                  </div>
                </div>

                <div className="relation-panel">
                  <span>Tópicos recentes</span>
                  {relation.recent_topics.length > 0 ? (
                    <div className="relation-topic-row">
                      {relation.recent_topics.slice(0, 5).map((topic, index) => (
                        <span key={`${relation.id}-topic-${index}`} className="relation-topic-chip">{topic}</span>
                      ))}
                    </div>
                  ) : (
                    <p>Sem tópicos recentes consolidados para este vínculo.</p>
                  )}
                </div>

                <div className="relation-card-footer">
                  <span>{relation.source_message_count} mensagem(ns) contribuíram para esta memória</span>
                  <strong>{relation.last_analyzed_at ? `Atualizado ${formatShortDateTime(relation.last_analyzed_at)}` : `Registrado ${formatShortDateTime(relation.updated_at)}`}</strong>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Card>
        <SectionTitle title="Como manter isso melhor" icon={MessageSquare} action={<button className="ac-secondary-button" onClick={onRefresh} type="button">Recarregar</button>} />
        <p className="support-copy">
          Quando você roda a próxima atualização de memória, o modelo cruza mensagens novas com esta base de pessoas. Isso melhora tipo de vínculo, fatos recorrentes, pendências e tom da relação de forma cumulativa.
        </p>
      </Card>
    </div>
  );
}

function AgendaTab({
  events,
  error,
  actionError,
  onRefresh,
  onSaveEvent,
  onDeleteEvent,
  savingAgendaIds,
  deletingAgendaIds,
}: {
  events: AgendaEvent[];
  error: string | null;
  actionError: string | null;
  onRefresh: () => void;
  onSaveEvent: (event: AgendaEvent, input: UpdateAgendaEventInput) => Promise<AgendaEvent>;
  onDeleteEvent: (event: AgendaEvent) => Promise<void>;
  savingAgendaIds: string[];
  deletingAgendaIds: string[];
}) {
  type AgendaEditDraft = {
    titulo: string;
    inicio: string;
    fim: string;
    status: "firme" | "tentativo";
    contato_origem: string;
    reminder_offset_minutes: string;
  };

  const [filter, setFilter] = useState<"all" | "upcoming" | "firm" | "tentative" | "conflicts">("all");
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [agendaDrafts, setAgendaDrafts] = useState<Record<string, AgendaEditDraft>>({});
  const now = Date.now();
  const sortedEvents = useMemo(
    () => [...events].sort((left, right) => new Date(left.inicio).getTime() - new Date(right.inicio).getTime()),
    [events],
  );
  const upcomingEvents = useMemo(
    () => sortedEvents.filter((event) => new Date(event.fim).getTime() >= now),
    [now, sortedEvents],
  );
  const firmCount = events.filter((event) => event.status === "firme").length;
  const tentativeCount = events.filter((event) => event.status !== "firme").length;
  const conflictCount = events.filter((event) => event.has_conflict).length;
  const nextEvent = upcomingEvents[0] ?? null;

  const filteredEvents = useMemo(() => {
    switch (filter) {
      case "upcoming":
        return upcomingEvents;
      case "firm":
        return sortedEvents.filter((event) => event.status === "firme");
      case "tentative":
        return sortedEvents.filter((event) => event.status !== "firme");
      case "conflicts":
        return sortedEvents.filter((event) => event.has_conflict);
      default:
        return sortedEvents;
    }
  }, [filter, sortedEvents, upcomingEvents]);

  const filterOptions = [
    { id: "all" as const, label: "Todos", count: sortedEvents.length },
    { id: "upcoming" as const, label: "Próximos", count: upcomingEvents.length },
    { id: "firm" as const, label: "Firmes", count: firmCount },
    { id: "tentative" as const, label: "Tentativos", count: tentativeCount },
    { id: "conflicts" as const, label: "Conflitos", count: conflictCount },
  ];

  const buildDraft = (event: AgendaEvent): AgendaEditDraft => ({
    titulo: event.titulo,
    inicio: formatBrazilDateTimeInput(event.inicio),
    fim: formatBrazilDateTimeInput(event.fim),
    status: event.status,
    contato_origem: event.contato_origem ?? "",
    reminder_offset_minutes: String(event.reminder_offset_minutes ?? 0),
  });

  const openEdit = (event: AgendaEvent): void => {
    setEditingEventId(event.id);
    setAgendaDrafts((current) => ({
      ...current,
      [event.id]: current[event.id] ?? buildDraft(event),
    }));
  };

  const closeEdit = (): void => {
    setEditingEventId(null);
  };

  async function handleSave(event: AgendaEvent): Promise<void> {
    const draft = agendaDrafts[event.id] ?? buildDraft(event);
    const titulo = draft.titulo.trim();
    const inicio = parseBrazilDateTimeInput(draft.inicio);
    const fim = parseBrazilDateTimeInput(draft.fim);
    const reminderOffsetMinutes = Number.parseInt(draft.reminder_offset_minutes || "0", 10);

    if (!titulo) {
      toast.error("Informe um título para o compromisso.");
      return;
    }
    if (Number.isNaN(inicio.getTime()) || Number.isNaN(fim.getTime())) {
      toast.error("Preencha início e fim com datas válidas.");
      return;
    }
    if (fim.getTime() <= inicio.getTime()) {
      toast.error("O horário final precisa ser depois do início.");
      return;
    }
    if (Number.isNaN(reminderOffsetMinutes) || reminderOffsetMinutes < 0) {
      toast.error("A antecedência do lembrete precisa ser um número igual ou maior que zero.");
      return;
    }

    try {
      await onSaveEvent(event, {
        titulo,
        inicio: inicio.toISOString(),
        fim: fim.toISOString(),
        status: draft.status,
        contato_origem: draft.contato_origem.trim() || undefined,
        reminder_offset_minutes: reminderOffsetMinutes,
      });
      closeEdit();
      toast.success("Compromisso atualizado.");
    } catch {
      // A camada superior já registra o erro e mantém a UI em edição.
    }
  }

  if (events.length === 0) {
    return (
      <div className="page-stack">
        <Card className="proj-empty-hero">
          <div className="proj-empty-icon">
            <Clock size={40} />
          </div>
          <h3>Nenhum compromisso detectado ainda</h3>
          <p>
            Assim que o Guardião do Tempo encontrar uma combinação de data e horário nas mensagens recebidas pelo Observador
            ou pelo agente do WhatsApp, os compromissos aparecem aqui.
          </p>
          <div className="hero-actions">
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar agenda
            </button>
          </div>
          {error ? <InlineError title="Falha na agenda" message={error} /> : null}
          {actionError ? <InlineError title="Falha na edição da agenda" message={actionError} /> : null}
        </Card>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <Card className="projects-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Clock size={14} />
            Guardião do Tempo
          </div>
          <h3>Compromissos detectados no WhatsApp</h3>
          <p>
            Esta visão concentra os eventos extraídos pelo backend, já com status, contato de origem, lembrete automático e
            marcação de conflito quando houver sobreposição de horário.
          </p>
        </div>
        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Total</span>
            <strong>{events.length}</strong>
            <small>{upcomingEvents.length} ainda por acontecer</small>
          </div>
          <div className="projects-hero-metric">
            <span>Firmes</span>
            <strong>{firmCount}</strong>
            <small>{tentativeCount} tentativos</small>
          </div>
          <div className="projects-hero-metric">
            <span>Conflitos</span>
            <strong>{conflictCount}</strong>
            <small>{conflictCount > 0 ? "requerem atenção" : "sem sobreposição agora"}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Próximo</span>
            <strong>{nextEvent ? formatShortDateTime(nextEvent.inicio) : "Sem próximo"}</strong>
            <small>{nextEvent ? nextEvent.titulo : "Nenhum compromisso futuro detectado"}</small>
          </div>
        </div>
      </Card>

      <Card>
        <SectionTitle
          title="Agenda"
          icon={Clock}
          action={
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={14} />
              Atualizar
            </button>
          }
        />
        <div className="projects-toolbar">
          <div className="projects-filter-pills">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`projects-filter-pill${filter === option.id ? " projects-filter-pill-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>

        <div className="project-list-modern">
          {filteredEvents.map((event) => {
            const isEditing = editingEventId === event.id;
            const draft = agendaDrafts[event.id] ?? buildDraft(event);
            const isSaving = savingAgendaIds.includes(event.id);
            const isDeleting = deletingAgendaIds.includes(event.id);

            return (
              <div
                key={event.id}
                className={`project-card-modern${event.has_conflict ? " project-card-modern-attention" : ""}`}
              >
                <div className="project-card-head">
                  <div>
                    <strong>{event.titulo}</strong>
                    <span>
                      {formatShortDateTime(event.inicio)} até {formatShortDateTime(event.fim)}
                    </span>
                  </div>
                  <div className="project-card-actions">
                    <span className={`micro-status micro-status-${event.status === "firme" ? "emerald" : "amber"}`}>
                      {event.status === "firme" ? "Firme" : "Tentativo"}
                    </span>
                    {event.has_conflict ? (
                      <span className="micro-status micro-status-amber">Conflito</span>
                    ) : null}
                    <button
                      className="ac-button ac-button-outline ac-button-sm"
                      disabled={isSaving || isDeleting}
                      onClick={() => (isEditing ? closeEdit() : openEdit(event))}
                      type="button"
                    >
                      {isEditing ? <X size={14} /> : <Edit2 size={14} />}
                    </button>
                    <button
                      className="ac-button ac-button-outline ac-button-sm"
                      disabled={isSaving || isDeleting}
                      onClick={() => void onDeleteEvent(event)}
                      type="button"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {isEditing ? (
                  <div className="project-summary-stack" style={{ gap: "0.85rem" }}>
                    <label>
                      <span className="support-copy">Título</span>
                      <input
                        className="ac-input"
                        onChange={(editEvent) =>
                          setAgendaDrafts((current) => ({
                            ...current,
                            [event.id]: { ...draft, titulo: editEvent.target.value },
                          }))
                        }
                        type="text"
                        value={draft.titulo}
                      />
                    </label>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Início</span>
                        <input
                          className="ac-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, inicio: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.inicio}
                        />
                      </label>
                      <label>
                        <span className="support-copy">Fim</span>
                        <input
                          className="ac-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, fim: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.fim}
                        />
                      </label>
                    </div>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Status</span>
                        <select
                          className="ac-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: {
                                ...draft,
                                status: editEvent.target.value === "firme" ? "firme" : "tentativo",
                              },
                            }))
                          }
                          value={draft.status}
                        >
                          <option value="firme">Firme</option>
                          <option value="tentativo">Tentativo</option>
                        </select>
                      </label>
                      <label>
                        <span className="support-copy">Origem</span>
                        <input
                          className="ac-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, contato_origem: editEvent.target.value },
                            }))
                          }
                          type="text"
                          value={draft.contato_origem}
                        />
                      </label>
                    </div>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Antecedência do lembrete em Brasília</span>
                        <input
                          className="ac-input"
                          min="0"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, reminder_offset_minutes: editEvent.target.value },
                            }))
                          }
                          step="1"
                          type="number"
                          value={draft.reminder_offset_minutes}
                        />
                      </label>
                      <div className="support-copy" style={{ alignSelf: "end", paddingBottom: "0.75rem" }}>
                        Horário do formulário: Brasília (UTC-3)
                      </div>
                    </div>
                    <div className="hero-actions">
                      <button
                        className="ac-primary-button"
                        disabled={isSaving || isDeleting}
                        onClick={() => void handleSave(event)}
                        type="button"
                      >
                        <Check size={14} />
                        {isSaving ? "Salvando..." : "Salvar alterações"}
                      </button>
                      <button className="ac-secondary-button" disabled={isSaving} onClick={closeEdit} type="button">
                        <X size={14} />
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="project-summary-stack">
                    <p className="support-copy">
                      {event.contato_origem ? `Origem: ${event.contato_origem}.` : "Origem não identificada."}
                    </p>
                    <p className="support-copy">
                      ID da mensagem: <code>{event.message_id}</code>
                    </p>
                    <p className="support-copy">
                      Regra de lembrete: {formatReminderOffsetLabel(event.reminder_offset_minutes)} em horário de Brasília.
                    </p>
                    <p className="support-copy">
                      {event.pre_reminder_at
                        ? event.pre_reminder_sent_at
                          ? `Lembrete antecipado enviado em ${formatShortDateTime(event.pre_reminder_sent_at)}.`
                          : `Lembrete antecipado programado para ${formatShortDateTime(event.pre_reminder_at)}.`
                        : "Sem lembrete antecipado configurado."}
                    </p>
                    <p className="support-copy">
                      {event.reminder_sent_at
                        ? `Lembrete do horário enviado em ${formatShortDateTime(event.reminder_sent_at)}.`
                        : "Lembrete do horário ainda pendente."}
                    </p>
                    {event.conflict ? (
                      <div className="danger-box" style={{ marginTop: 12 }}>
                        <h4>
                          <AlertCircle size={16} />
                          Possível conflito
                        </h4>
                        <p>
                          Já existe <strong>{event.conflict.titulo}</strong> em {formatShortDateTime(event.conflict.inicio)} até{" "}
                          {formatShortDateTime(event.conflict.fim)}.
                        </p>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {filteredEvents.length === 0 ? (
          <div className="empty-hint">
            <Clock size={18} />
            <p>Nenhum compromisso bate com o filtro atual.</p>
          </div>
        ) : null}
      </Card>

      {error ? <InlineError title="Falha na agenda" message={error} /> : null}
      {actionError ? <InlineError title="Falha na edição da agenda" message={actionError} /> : null}
    </div>
  );
}

function ProjectsTab({
  projects,
  onToggleCompletion,
  onSaveProject,
  onAssistProject,
  onDeleteProject,
  savingProjectKeys,
  deletingProjectKeys,
  editingProjectKeys,
  aiProjectKeys,
  actionError,
}: {
  projects: ProjectMemory[];
  onToggleCompletion: (project: ProjectMemory, completed: boolean) => Promise<void>;
  onSaveProject: (
    project: ProjectMemory,
    input: {
      project_name: string;
      summary: string;
      status: string;
      what_is_being_built: string;
      built_for: string;
      next_steps: string[];
      evidence: string[];
    },
  ) => Promise<ProjectMemory>;
  onAssistProject: (project: ProjectMemory, instruction: string) => Promise<{ project: ProjectMemory; assistant_message: string }>;
  onDeleteProject: (project: ProjectMemory) => Promise<void>;
  savingProjectKeys: string[];
  deletingProjectKeys: string[];
  editingProjectKeys: string[];
  aiProjectKeys: string[];
  actionError: string | null;
}) {
  type ProjectEditDraft = {
    project_name: string;
    summary: string;
    status: string;
    what_is_being_built: string;
    built_for: string;
    next_steps_text: string;
    evidence_text: string;
  };

  type ProjectChatEntry = {
    id: string;
    role: "user" | "assistant";
    text: string;
  };

  const [subTab, setSubTab] = useState<"overview" | "details" | "roadmap">("overview");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [compactExpandedId, setCompactExpandedId] = useState<string | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [aiProjectId, setAiProjectId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "completed" | "no_steps">("all");
  const [projectDrafts, setProjectDrafts] = useState<Record<string, ProjectEditDraft>>({});
  const [projectAiDrafts, setProjectAiDrafts] = useState<Record<string, string>>({});
  const [projectAiChats, setProjectAiChats] = useState<Record<string, ProjectChatEntry[]>>({});

  useEffect(() => {
    if (!aiProjectId) {
      return;
    }

    const handlePointerDown = (event: MouseEvent): void => {
      const target = event.target;
      if (!(target instanceof Element)) {
        closeProjectAi();
        return;
      }

      if (target.closest(`[data-project-ai-root="${aiProjectId}"]`)) {
        return;
      }

      closeProjectAi();
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [aiProjectId]);

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((left, right) => {
        const leftCompleted = isProjectManuallyCompleted(left);
        const rightCompleted = isProjectManuallyCompleted(right);
        if (leftCompleted !== rightCompleted) {
          return Number(leftCompleted) - Number(rightCompleted);
        }

        if (leftCompleted && rightCompleted) {
          const leftTime = new Date(left.manual_completed_at ?? left.updated_at).getTime();
          const rightTime = new Date(right.manual_completed_at ?? right.updated_at).getTime();
          return rightTime - leftTime;
        }

        const strengthDelta = getProjectStrength(right) - getProjectStrength(left);
        if (strengthDelta !== 0) {
          return strengthDelta;
        }

        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      }),
    [projects],
  );

  const activeProjects = useMemo(
    () => sortedProjects.filter((project) => !isProjectManuallyCompleted(project)),
    [sortedProjects],
  );
  const completedProjects = useMemo(
    () => sortedProjects.filter((project) => isProjectManuallyCompleted(project)),
    [sortedProjects],
  );
  const deferredSearch = useDeferredValue(search);
  const normalizedSearch = useMemo(() => normalizeProjectSearchText(deferredSearch.trim()), [deferredSearch]);

  const filteredProjects = useMemo(
    () =>
      sortedProjects.filter((project) => {
        const completed = isProjectManuallyCompleted(project);
        const matchesFilter =
          filter === "all"
            ? true
            : filter === "active"
              ? !completed
              : filter === "completed"
                ? completed
                : project.next_steps.length === 0;
        if (!matchesFilter) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        const haystack = normalizeProjectSearchText(
          [
            project.project_name,
            project.summary,
            project.status,
            project.what_is_being_built,
            project.built_for,
            project.manual_completion_notes,
            project.next_steps.join(" "),
            project.evidence.join(" "),
          ].join(" "),
        );
        return haystack.includes(normalizedSearch);
      }),
    [filter, normalizedSearch, sortedProjects],
  );

  const filteredActiveProjects = useMemo(
    () => filteredProjects.filter((project) => !isProjectManuallyCompleted(project)),
    [filteredProjects],
  );
  const filteredCompletedProjects = useMemo(
    () => filteredProjects.filter((project) => isProjectManuallyCompleted(project)),
    [filteredProjects],
  );

  const totalEvidence = projects.reduce((sum, project) => sum + project.evidence.length, 0);
  const openSteps = activeProjects.reduce((sum, project) => sum + project.next_steps.length, 0);
  const noStepProjects = activeProjects.filter((project) => project.next_steps.length === 0).length;
  const completionRate = projects.length > 0 ? Math.round((completedProjects.length / projects.length) * 100) : 0;
  const avgStrength =
    activeProjects.length > 0 ? Math.round(activeProjects.reduce((sum, project) => sum + getProjectStrength(project), 0) / activeProjects.length) : 0;
  const latestUpdated =
    sortedProjects.length > 0
      ? sortedProjects.reduce((latest, project) => (
          new Date(project.updated_at).getTime() > new Date(latest).getTime() ? project.updated_at : latest
        ), sortedProjects[0].updated_at)
      : null;
  const latestCompletedProject = completedProjects[0] ?? null;

  if (projects.length === 0) {
    return (
      <div className="page-stack">
        <Card className="proj-empty-hero">
          <div className="proj-empty-icon">
            <FolderGit2 size={40} />
          </div>
          <h3>Nenhum projeto consolidado</h3>
          <p>Assim que a memória tiver sinal suficiente, as frentes reais aparecem aqui com status, próximos passos e fechamento manual quando você quiser encerrar uma delas.</p>
        </Card>
      </div>
    );
  }

  const filterOptions = [
    { id: "all" as const, label: "Todos", count: projects.length },
    { id: "active" as const, label: "Ativos", count: activeProjects.length },
    { id: "completed" as const, label: "Concluídos", count: completedProjects.length },
    { id: "no_steps" as const, label: "Sem passos", count: noStepProjects },
  ];

  const emptyLabel =
    normalizedSearch.length > 0
      ? "Nenhum projeto bateu com a busca atual."
      : filter === "completed"
        ? "Ainda não existe nenhum projeto concluído manualmente."
        : filter === "no_steps"
          ? "Todos os projetos ativos já têm próximos passos."
          : "Nada para mostrar com o filtro atual.";

  function buildProjectDraft(project: ProjectMemory): ProjectEditDraft {
    return {
      project_name: project.project_name,
      summary: project.summary,
      status: project.status,
      what_is_being_built: project.what_is_being_built,
      built_for: project.built_for,
      next_steps_text: project.next_steps.join("\n"),
      evidence_text: project.evidence.join("\n"),
    };
  }

  function parseProjectLines(value: string): string[] {
    return value.split("\n").map((line) => line.trim()).filter(Boolean);
  }

  function openProjectEditor(project: ProjectMemory): void {
    setEditingProjectId(project.id);
    setProjectDrafts((current) => ({
      ...current,
      [project.id]: current[project.id] ?? buildProjectDraft(project),
    }));
  }

  function closeProjectEditor(): void {
    setEditingProjectId(null);
  }

  function updateProjectDraft(projectId: string, field: keyof ProjectEditDraft, value: string): void {
    setProjectDrafts((current) => ({
      ...current,
      [projectId]: {
        ...(current[projectId] ?? {
          project_name: "",
          summary: "",
          status: "",
          what_is_being_built: "",
          built_for: "",
          next_steps_text: "",
          evidence_text: "",
        }),
        [field]: value,
      },
    }));
  }

  async function submitProjectDraft(project: ProjectMemory): Promise<void> {
    const draft = projectDrafts[project.id] ?? buildProjectDraft(project);
    const updated = await onSaveProject(project, {
      project_name: draft.project_name.trim(),
      summary: draft.summary.trim(),
      status: draft.status.trim(),
      what_is_being_built: draft.what_is_being_built.trim(),
      built_for: draft.built_for.trim(),
      next_steps: parseProjectLines(draft.next_steps_text),
      evidence: parseProjectLines(draft.evidence_text),
    });
    setProjectDrafts((current) => ({
      ...current,
      [updated.id]: buildProjectDraft(updated),
    }));
    setEditingProjectId(null);
  }

  function openProjectAi(project: ProjectMemory): void {
    setAiProjectId(project.id);
    setProjectAiDrafts((current) => ({ ...current, [project.id]: current[project.id] ?? "" }));
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: current[project.id] ?? [
        {
          id: `${project.id}-assistant-intro`,
          role: "assistant",
          text: "Descreva o que deve mudar no projeto. Eu ajusto resumo, status, público, próximos passos e evidências sem sair da aba.",
        },
      ],
    }));
  }

  function closeProjectAi(): void {
    setAiProjectId(null);
  }

  async function submitProjectAiInstruction(project: ProjectMemory): Promise<void> {
    const instruction = (projectAiDrafts[project.id] ?? "").trim();
    if (!instruction) {
      return;
    }
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: [
        ...(current[project.id] ?? []),
        { id: `${Date.now()}-${project.id}-user`, role: "user", text: instruction },
      ],
    }));
    setProjectAiDrafts((current) => ({ ...current, [project.id]: "" }));
    const response = await onAssistProject(project, instruction);
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: [
        ...(current[project.id] ?? []),
        { id: `${Date.now()}-${project.id}-assistant`, role: "assistant", text: response.assistant_message },
      ],
    }));
    setProjectDrafts((current) => ({
      ...current,
      [response.project.id]: buildProjectDraft(response.project),
    }));
  }

  function renderProjectAction(project: ProjectMemory) {
    const completed = isProjectManuallyCompleted(project);
    const saving = savingProjectKeys.includes(project.project_key);
    return (
      <button
        className={completed ? "ac-secondary-button project-action-button" : "ac-success-button project-action-button"}
        disabled={saving}
        onClick={() => void onToggleCompletion(project, !completed)}
        type="button"
      >
        {saving ? <RefreshCw size={14} className="spin" /> : completed ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
        {saving ? "Salvando..." : completed ? "Reabrir projeto" : "Marcar concluído"}
      </button>
    );
  }

  function renderProjectDeleteAction(project: ProjectMemory) {
    const deleting = deletingProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button project-delete-button"
        disabled={deleting}
        onClick={() => void onDeleteProject(project)}
        type="button"
      >
        {deleting ? <RefreshCw size={14} className="spin" /> : <Trash2 size={14} />}
        {deleting ? "Excluindo..." : "Excluir"}
      </button>
    );
  }

  function renderProjectEditAction(project: ProjectMemory) {
    const editing = editingProjectId === project.id;
    const saving = editingProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button"
        disabled={saving}
        onClick={() => (editing ? closeProjectEditor() : openProjectEditor(project))}
        type="button"
      >
        {saving ? <RefreshCw size={14} className="spin" /> : <Settings size={14} />}
        {saving ? "Salvando..." : editing ? "Fechar edição" : "Editar"}
      </button>
    );
  }

  function renderProjectAiAction(project: ProjectMemory) {
    const open = aiProjectId === project.id;
    const loading = aiProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button project-ai-button"
        data-project-ai-root={project.id}
        disabled={loading}
        onClick={() => (open ? closeProjectAi() : openProjectAi(project))}
        type="button"
      >
        {loading ? <RefreshCw size={14} className="spin" /> : <Bot size={14} />}
        {loading ? "IA editando..." : open ? "Fechar IA" : "IA"}
      </button>
    );
  }

  function renderProjectEditor(project: ProjectMemory) {
    if (editingProjectId !== project.id) {
      return null;
    }
    const draft = projectDrafts[project.id] ?? buildProjectDraft(project);
    const saving = editingProjectKeys.includes(project.project_key);
    return (
      <div className="project-inline-editor">
        <div className="project-inline-grid">
          <label className="project-inline-field">
            <span>Nome</span>
            <input className="ac-input" type="text" value={draft.project_name} onChange={(event) => updateProjectDraft(project.id, "project_name", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Status</span>
            <input className="ac-input" type="text" value={draft.status} onChange={(event) => updateProjectDraft(project.id, "status", event.target.value)} />
          </label>
          <label className="project-inline-field project-inline-field-full">
            <span>Resumo</span>
            <textarea className="ac-input project-inline-textarea" value={draft.summary} onChange={(event) => updateProjectDraft(project.id, "summary", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>O que está sendo construído</span>
            <textarea className="ac-input project-inline-textarea" value={draft.what_is_being_built} onChange={(event) => updateProjectDraft(project.id, "what_is_being_built", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Público</span>
            <textarea className="ac-input project-inline-textarea" value={draft.built_for} onChange={(event) => updateProjectDraft(project.id, "built_for", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Próximos passos</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.next_steps_text} onChange={(event) => updateProjectDraft(project.id, "next_steps_text", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Evidências</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.evidence_text} onChange={(event) => updateProjectDraft(project.id, "evidence_text", event.target.value)} />
          </label>
        </div>
        <div className="project-inline-actions">
          <button className="ac-primary-button" disabled={saving} onClick={() => void submitProjectDraft(project)} type="button">
            {saving ? <RefreshCw size={14} className="spin" /> : <BadgeCheck size={14} />}
            {saving ? "Salvando..." : "Salvar projeto"}
          </button>
          <button className="ac-secondary-button" disabled={saving} onClick={closeProjectEditor} type="button">
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  function renderProjectAiPanel(project: ProjectMemory) {
    if (aiProjectId !== project.id) {
      return null;
    }
    const entries = projectAiChats[project.id] ?? [];
    const draft = projectAiDrafts[project.id] ?? "";
    const loading = aiProjectKeys.includes(project.project_key);
    return (
      <div className="project-ai-panel" data-project-ai-root={project.id}>
        <div className="project-ai-messages">
          {entries.map((entry) => (
            <div key={entry.id} className={`project-ai-message project-ai-message-${entry.role}`}>
              <strong>{entry.role === "assistant" ? "IA" : "Você"}</strong>
              <p>{entry.text}</p>
            </div>
          ))}
          {loading ? (
            <div className="project-ai-loading">
              <RefreshCw size={14} className="spin" />
              <span>DeepSeek editando o projeto...</span>
            </div>
          ) : null}
        </div>
        <div className="project-ai-compose">
          <textarea
            className="ac-input project-ai-textarea"
            placeholder="Ex.: atualize o resumo, deixe o status como em validação, limpe evidências vagas e reescreva os próximos passos."
            value={draft}
            onChange={(event) => setProjectAiDrafts((current) => ({ ...current, [project.id]: event.target.value }))}
          />
          <div className="project-inline-actions">
            <button className="ac-primary-button" disabled={loading || !draft.trim()} onClick={() => void submitProjectAiInstruction(project)} type="button">
              {loading ? <RefreshCw size={14} className="spin" /> : <Send size={14} />}
              {loading ? "Editando..." : "Enviar para IA"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <Card className="projects-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Sparkles size={14} />
            Portfólio vivo do dono
          </div>
          <h3>Projetos rastreados pela memória</h3>
          <p>
            {completedProjects.length > 0
              ? `${completedProjects.length} projeto(s) já foram concluídos manualmente e seguem entrando como contexto nas próximas atualizações de memória.`
              : "Use esta aba para revisar frentes ativas, limpar o que já terminou e manter o retrato operacional coerente com a realidade."}
          </p>
        </div>
        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Frentes ativas</span>
            <strong>{activeProjects.length}</strong>
            <small>{openSteps} próximos passos em aberto</small>
          </div>
          <div className="projects-hero-metric">
            <span>Fechamento manual</span>
            <strong>{completionRate}%</strong>
            <small>{completedProjects.length} concluído(s)</small>
          </div>
          <div className="projects-hero-metric">
            <span>Sinal médio</span>
            <strong>{avgStrength}%</strong>
            <small>{totalEvidence} evidências mapeadas</small>
          </div>
          <div className="projects-hero-metric">
            <span>Última revisão</span>
            <strong>{latestUpdated ? formatRelativeTime(latestUpdated) : "Agora"}</strong>
            <small>{latestCompletedProject ? `${latestCompletedProject.project_name} foi fechado manualmente por último` : "Sem encerramentos manuais ainda"}</small>
          </div>
        </div>
      </Card>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Visão Geral", "Detalhes Completos", "Roadmap"]}
          selected={subTab === "overview" ? "Visão Geral" : subTab === "details" ? "Detalhes Completos" : "Roadmap"}
          onChange={(value) => {
            if (value === "Visão Geral") setSubTab("overview");
            if (value === "Detalhes Completos") setSubTab("details");
            if (value === "Roadmap") setSubTab("roadmap");
          }}
        />
      </div>

      <Card className="projects-toolbar-card">
        <div className="projects-toolbar">
          <label className="project-search-shell">
            <Search size={16} />
            <input
              className="ac-input project-search-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por projeto, resumo, público, evidência..."
              type="text"
              value={search}
            />
          </label>
          <div className="project-filter-row">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`project-filter-chip${filter === option.id ? " project-filter-chip-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>
        {actionError ? <InlineError title="Falha ao salvar projeto" message={actionError} /> : null}
      </Card>

      {filteredProjects.length === 0 ? (
        <Card>
          <div className="empty-hint">
            <FolderGit2 size={18} />
            <p>{emptyLabel}</p>
          </div>
        </Card>
      ) : null}

      {subTab === "overview" && filteredProjects.length > 0 ? (
        <>
          <div className="proj-stats-row">
            <ModernStatCard label="Projetos visíveis" value={String(filteredProjects.length)} meta="Resultado do filtro atual" icon={FolderGit2} tone="indigo" />
            <ModernStatCard label="Passos em aberto" value={String(filteredActiveProjects.reduce((sum, project) => sum + project.next_steps.length, 0))} meta="Somente frentes ainda ativas" icon={ChevronRight} tone="amber" />
            <ModernStatCard label="Concluídos manualmente" value={String(filteredCompletedProjects.length)} meta="Fechados por ação do usuário" icon={CheckCircle2} tone="emerald" />
            <ModernStatCard label="Sem passos" value={String(filteredActiveProjects.filter((project) => project.next_steps.length === 0).length)} meta="Precisam de mais sinal ou revisão" icon={AlertCircle} />
          </div>

          <div className="project-modern-grid">
            {filteredProjects.map((project) => {
              const completed = isProjectManuallyCompleted(project);
              const compactExpanded = compactExpandedId === project.id;
              const statusTone = getProjectStatusTone(project);
              const previewSteps = completed ? [] : project.next_steps.slice(0, compactExpanded ? 4 : 2);
              const previewEvidence = project.evidence.slice(0, compactExpanded ? 4 : 2);
              return (
                <Card
                  key={`project-overview-${project.id}`}
                  className={`project-modern-card project-modern-card-compact${completed ? " project-modern-card-completed" : ""}${compactExpanded ? " project-modern-card-expanded" : ""}${aiProjectId === project.id ? " project-card-with-ai-open" : ""}`}
                >
                  <div className="project-modern-head">
                    <div className="project-modern-title">
                      <div className={`project-modern-icon project-modern-icon-${statusTone}`}>
                        <FolderGit2 size={18} />
                      </div>
                      <div>
                        <h3>{project.project_name}</h3>
                        <p>{truncateText(project.summary, compactExpanded ? 220 : 110)}</p>
                      </div>
                    </div>
                    <div className="project-modern-actions">
                      <div className={`micro-status micro-status-${statusTone}`}>{getProjectStatusLabel(project)}</div>
                      <div className="project-action-row">
                        {renderProjectAiAction(project)}
                        {renderProjectEditAction(project)}
                        <button
                          className="ac-secondary-button project-action-button project-detail-toggle"
                          onClick={() => setCompactExpandedId(compactExpanded ? null : project.id)}
                          type="button"
                        >
                          {compactExpanded ? "Retrair" : "Expandir"}
                          <ChevronRight size={15} className={compactExpanded ? "proj-expand-chevron proj-expand-chevron-open" : "proj-expand-chevron"} />
                        </button>
                        {renderProjectAction(project)}
                        {renderProjectDeleteAction(project)}
                      </div>
                    </div>
                  </div>

                  {completed ? (
                    <div className="project-completion-banner">
                      <CheckCircle2 size={16} />
                      <div>
                        <strong>Conclusão manual salva</strong>
                        <p>
                          {project.manual_completed_at ? `Marcado em ${formatShortDateTime(project.manual_completed_at)}.` : "Marcado manualmente."} Esse fechamento entra nas próximas atualizações de memória.
                        </p>
                        {project.manual_completion_notes ? <small>{project.manual_completion_notes}</small> : null}
                      </div>
                    </div>
                  ) : null}

                  <ProgressBar
                    value={completed ? 100 : getProjectStrength(project)}
                    tone={completed ? "emerald" : statusTone === "amber" ? "amber" : "indigo"}
                    label={completed ? "Encerrado pelo usuário" : "Força do contexto atual"}
                  />

                  <div className="project-modern-meta">
                    <ProjectInfoBlock label="Público" value={getAudienceLabel(project)} />
                    <ProjectInfoBlock label="Construindo" value={project.what_is_being_built || "Ainda não consolidado"} />
                    <ProjectInfoBlock label="Último sinal" value={project.last_seen_at ? formatRelativeTime(project.last_seen_at) : "Sem data"} />
                    <ProjectInfoBlock label="Atualizado" value={formatRelativeTime(project.updated_at)} />
                  </div>

                  <div className="project-modern-panels">
                    <div className="project-modern-panel">
                      <span>Próximos passos</span>
                      {previewSteps.length > 0 ? (
                        <ul>
                          {previewSteps.map((step, index) => (
                            <li key={`${project.id}-step-preview-${index}`}>{step}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>{completed ? "Projeto encerrado pelo usuário, sem pendências abertas." : "Nenhum próximo passo consolidado ainda."}</p>
                      )}
                    </div>
                    <div className="project-modern-panel">
                      <span>Evidências</span>
                      {previewEvidence.length > 0 ? (
                        <ul>
                          {previewEvidence.map((evidence, index) => (
                            <li key={`${project.id}-evidence-preview-${index}`}>{evidence}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>Sem evidências recentes registradas.</p>
                      )}
                    </div>
                  </div>

                  {compactExpanded ? (
                    <div className="project-modern-expand-area">
                      <div className="project-modern-panel">
                        <span>Resumo operacional</span>
                        <p>{project.what_is_being_built || "Sem descrição detalhada ainda."}</p>
                      </div>
                      {project.manual_completion_notes ? (
                        <div className="project-modern-panel">
                          <span>Notas de fechamento</span>
                          <p>{project.manual_completion_notes}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {renderProjectEditor(project)}
                  {renderProjectAiPanel(project)}
                </Card>
              );
            })}
          </div>
        </>
      ) : null}

      {subTab === "details" && filteredProjects.length > 0 ? (
        <div className="proj-details-stack">
          {filteredProjects.map((project) => {
            const isExpanded = expandedId === project.id;
            const completed = isProjectManuallyCompleted(project);
            const statusTone = getProjectStatusTone(project);
            return (
              <Card key={`project-detail-${project.id}`} className={`project-detail-modern-card${completed ? " project-detail-modern-card-completed" : ""}${aiProjectId === project.id ? " project-card-with-ai-open" : ""}`}>
                <div className="project-detail-modern-head">
                  <div className="project-detail-modern-copy">
                    <div className="project-detail-modern-title">
                      <FolderGit2 size={18} />
                      <div>
                        <h3>{project.project_name}</h3>
                        <span>{project.project_key}</span>
                      </div>
                    </div>
                    <p>{truncateText(project.summary, isExpanded ? 320 : 170)}</p>
                  </div>
                  <div className="project-detail-modern-actions">
                    <div className={`micro-status micro-status-${statusTone}`}>{getProjectStatusLabel(project)}</div>
                    <div className="project-action-row">
                      {renderProjectAiAction(project)}
                      {renderProjectEditAction(project)}
                      {renderProjectAction(project)}
                      {renderProjectDeleteAction(project)}
                      <button
                        className="ac-secondary-button project-detail-toggle"
                        onClick={() => setExpandedId(isExpanded ? null : project.id)}
                        type="button"
                      >
                        {isExpanded ? "Ocultar detalhes" : "Abrir detalhes"}
                        <ChevronRight size={15} className={isExpanded ? "proj-expand-chevron proj-expand-chevron-open" : "proj-expand-chevron"} />
                      </button>
                    </div>
                  </div>
                </div>

                {completed ? (
                  <div className="project-completion-banner">
                    <CheckCircle2 size={16} />
                    <div>
                      <strong>Fechado manualmente</strong>
                      <p>
                        {project.manual_completed_at ? `O usuário marcou este projeto como concluído em ${formatShortDateTime(project.manual_completed_at)}.` : "O usuário marcou este projeto como concluído."}
                      </p>
                      {project.manual_completion_notes ? <small>{project.manual_completion_notes}</small> : null}
                    </div>
                  </div>
                ) : null}

                {isExpanded ? (
                  <div className="project-detail-modern-body">
                    <div className="proj-detail-two-col">
                      <div className="proj-detail-section">
                        <div className="proj-detail-section-title">
                          <Terminal size={14} />
                          <span>O que está sendo construído</span>
                        </div>
                        <p>{project.what_is_being_built || "Sem descrição detalhada ainda."}</p>
                      </div>
                      <div className="proj-detail-section">
                        <div className="proj-detail-section-title">
                          <User size={14} />
                          <span>Público-alvo</span>
                        </div>
                        <p>{getAudienceLabel(project)}</p>
                      </div>
                    </div>

                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <ChevronRight size={14} />
                        <span>Próximos passos ({project.next_steps.length})</span>
                      </div>
                      {project.next_steps.length > 0 ? (
                        <ul className="proj-step-list">
                          {project.next_steps.map((step, index) => (
                            <li key={`${project.id}-detail-step-${index}`}>
                              <span className="proj-step-number">{index + 1}</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">{completed ? "Projeto concluído manualmente, sem passos restantes." : "Nenhum próximo passo consolidado para este projeto."}</p>
                      )}
                    </div>

                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <CheckCircle2 size={14} />
                        <span>Evidências ({project.evidence.length})</span>
                      </div>
                      {project.evidence.length > 0 ? (
                        <ul className="proj-evidence-list">
                          {project.evidence.map((evidence, index) => (
                            <li key={`${project.id}-detail-evidence-${index}`}>
                              <CheckCircle2 size={12} />
                              <span>{evidence}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">Nenhuma evidência recente consolidada.</p>
                      )}
                    </div>

                    <div className="proj-detail-footer-meta">
                      <div>
                        <Clock size={12} />
                        <span>Visto: {project.last_seen_at ? formatShortDateTime(project.last_seen_at) : "—"}</span>
                      </div>
                      <div>
                        <RefreshCw size={12} />
                        <span>Atualizado: {formatShortDateTime(project.updated_at)}</span>
                      </div>
                    </div>
                  </div>
                ) : null}

                {renderProjectEditor(project)}
                {renderProjectAiPanel(project)}
              </Card>
            );
          })}
        </div>
      ) : null}

      {subTab === "roadmap" && filteredProjects.length > 0 ? (
        <div className="proj-roadmap-container">
          <Card>
            <SectionTitle title="Roadmap de próximos passos" icon={Zap} />
            <p className="support-copy">
              A trilha abaixo destaca apenas frentes ainda abertas. Projetos concluídos manualmente ficam separados para que o histórico continue claro sem contaminar a fila operacional.
            </p>
          </Card>

          <div className="proj-roadmap-timeline">
            {filteredActiveProjects
              .filter((project) => project.next_steps.length > 0)
              .map((project) => (
                <div key={`roadmap-${project.id}`} className="proj-roadmap-project">
                  <div className="proj-roadmap-project-head">
                    <div className="proj-roadmap-dot" />
                    <div className="proj-roadmap-project-info">
                      <h4>{project.project_name}</h4>
                      <div className="proj-roadmap-meta-row">
                        <div className={`micro-status micro-status-${getProjectStatusTone(project)}`}>{getProjectStatusLabel(project)}</div>
                        <span className="proj-roadmap-strength">{getProjectStrength(project)}% sinal</span>
                      </div>
                    </div>
                    {renderProjectAction(project)}
                  </div>
                  <div className="proj-roadmap-steps">
                    {project.next_steps.map((step, index) => (
                      <div key={`${project.id}-roadmap-step-${index}`} className="proj-roadmap-step">
                        <div className="proj-roadmap-step-idx">{index + 1}</div>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                  {project.evidence.length > 0 ? (
                    <div className="proj-roadmap-evidence-block">
                      <span className="proj-roadmap-evidence-title">
                        <CheckCircle2 size={12} />
                        Evidências que sustentam
                      </span>
                      {project.evidence.slice(0, 2).map((evidence, index) => (
                        <p key={`${project.id}-roadmap-evidence-${index}`} className="proj-roadmap-evidence-text">{evidence}</p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}

            {filteredActiveProjects.filter((project) => project.next_steps.length > 0).length === 0 ? (
              <Card>
                <div className="empty-hint">
                  <Zap size={18} />
                  <p>Nenhum projeto ativo possui próximos passos definidos no filtro atual.</p>
                </div>
              </Card>
            ) : null}
          </div>

          {filteredCompletedProjects.length > 0 ? (
            <Card>
              <SectionTitle title="Concluídos manualmente" icon={CheckCircle2} />
              <div className="project-completed-grid">
                {filteredCompletedProjects.map((project) => (
                  <div key={`completed-${project.id}`} className="project-completed-card">
                    <div className="project-completed-head">
                      <strong>{project.project_name}</strong>
                      <span>{project.manual_completed_at ? formatShortDateTime(project.manual_completed_at) : "Fechado manualmente"}</span>
                    </div>
                    <p>{truncateText(project.summary, 150)}</p>
                    <small>{project.manual_completion_notes || "Esse encerramento continua entrando como contexto nas próximas leituras de memória."}</small>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

          {filteredActiveProjects.filter((project) => project.next_steps.length === 0).length > 0 ? (
            <Card>
              <SectionTitle title="Projetos ativos sem próximos passos" icon={AlertCircle} />
              <div className="proj-roadmap-no-steps">
                {filteredActiveProjects
                  .filter((project) => project.next_steps.length === 0)
                  .map((project) => (
                    <div key={`no-steps-${project.id}`} className="proj-roadmap-no-step-item">
                      <GitBranch size={14} />
                      <span>{project.project_name}</span>
                      <span className="proj-roadmap-no-step-hint">Precisa de mais sinal</span>
                    </div>
                  ))}
              </div>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ImportantMessagesTab({
  messages,
  error,
  onRefresh,
}: {
  messages: ImportantMessage[];
  error: string | null;
  onRefresh: () => void;
}) {
  const [importantSubTab, setImportantSubTab] = useState<"overview" | "access" | "operation" | "attention">("overview");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const normalizedSearch = deferredSearch.trim().toLowerCase();
  const credentialCount = messages.filter((message) => getImportantCategoryFamily(message.category) === "access").length;
  const operationCount = messages.filter((message) => getImportantCategoryFamily(message.category) === "operation").length;
  const attentionCount = messages.filter((message) => getImportantCategoryFamily(message.category) === "attention").length;
  const strongSignalsCount = messages.filter((message) => getImportantConfidenceBand(message.confidence) === "high").length;
  const needsReviewCount = messages.filter((message) => !message.last_reviewed_at || message.confidence < 65).length;
  const lastReviewedAt = messages
    .map((message) => message.last_reviewed_at)
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0] ?? null;
  const importantSubTabs = [
    { id: "overview" as const, label: "Painel", count: messages.length, icon: Archive },
    { id: "access" as const, label: "Acessos", count: credentialCount, icon: LockKeyhole },
    { id: "operation" as const, label: "Operação", count: operationCount, icon: FolderGit2 },
    { id: "attention" as const, label: "Atenção", count: attentionCount, icon: AlertCircle },
  ];
  const filteredMessages = useMemo(
    () =>
      messages.filter((message) => {
        const family = getImportantCategoryFamily(message.category);
        const matchesTab =
          importantSubTab === "overview"
            ? true
            : importantSubTab === "access"
              ? family === "access"
              : importantSubTab === "operation"
                ? family === "operation"
                : family === "attention";
        if (!matchesTab) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        const haystack = [
          message.contact_name,
          message.contact_phone ?? "",
          message.message_text,
          message.importance_reason,
          formatImportantCategory(message.category),
          getImportantCategoryFamilyLabel(message.category),
          message.review_notes ?? "",
        ].join(" ").toLowerCase();
        return haystack.includes(normalizedSearch);
      }),
    [importantSubTab, messages, normalizedSearch],
  );
  const groupedMessages = useMemo(() => {
    const groups = new Map<string, ImportantMessage[]>();
    for (const message of filteredMessages) {
      const key = formatImportantCategory(message.category);
      const current = groups.get(key) ?? [];
      current.push(message);
      groups.set(key, current);
    }
    return Array.from(groups.entries()).sort((left, right) => right[1].length - left[1].length);
  }, [filteredMessages]);
  const latestMessages = useMemo(
    () => [...messages].sort((left, right) => new Date(right.saved_at).getTime() - new Date(left.saved_at).getTime()).slice(0, 3),
    [messages],
  );
  const strongestMessages = useMemo(
    () => [...messages].sort((left, right) => right.confidence - left.confidence).slice(0, 3),
    [messages],
  );
  const reviewQueue = useMemo(
    () =>
      [...messages]
        .filter((message) => !message.last_reviewed_at || getImportantConfidenceBand(message.confidence) === "low")
        .sort((left, right) => new Date(right.saved_at).getTime() - new Date(left.saved_at).getTime())
        .slice(0, 4),
    [messages],
  );

  return (
    <div className="page-stack">
      <Card className="important-shell-card">
        <div className="important-shell-head">
          <div>
            <div className="hero-kicker">
              <Archive size={14} />
              Cofre operacional
            </div>
            <h3>As mensagens importantes agora ficam separadas por frente de uso.</h3>
            <p className="support-copy">
              O painel abaixo divide o cofre entre acessos, operação e atenção crítica. Assim fica mais fácil localizar o que é sensível, o que sustenta trabalho e o que exige revisão rápida.
            </p>
          </div>
          <div className="important-shell-actions">
            <label className="relation-search-shell important-search-shell">
              <Search size={16} />
              <input
                className="ac-input relation-search-input"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Buscar por contato, conteúdo, motivo ou categoria..."
                type="text"
                value={search}
              />
            </label>
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={14} />
              Atualizar
            </button>
          </div>
        </div>

        <div className="important-shell-tabs">
          {importantSubTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`activity-subtab${importantSubTab === tab.id ? " activity-subtab-active" : ""}`}
                onClick={() => setImportantSubTab(tab.id)}
                type="button"
              >
                <Icon size={14} />
                {tab.label}
                <strong>{tab.count}</strong>
              </button>
            );
          })}
        </div>

        <div className="important-top-grid">
          <ModernStatCard
            label="Ativas Agora"
            value={String(messages.length)}
            meta="Itens ainda úteis para memória futura"
            icon={Archive}
            tone="emerald"
          />
          <ModernStatCard
            label="Acessos"
            value={String(credentialCount)}
            meta="Logins, senhas e dados de acesso"
            icon={LockKeyhole}
            tone="amber"
          />
          <ModernStatCard
            label="Operação"
            value={String(operationCount)}
            meta="Projeto, cliente, documento e dinheiro"
            icon={FolderGit2}
            tone="indigo"
          />
          <ModernStatCard
            label="Fila de Revisão"
            value={String(needsReviewCount)}
            meta={lastReviewedAt ? `Última revisão ${formatRelativeTime(lastReviewedAt)}` : "Ainda sem revisão diária"}
            icon={AlertCircle}
            tone="zinc"
          />
        </div>
      </Card>

      {messages.length === 0 ? (
        <Card>
          <div className="empty-hint">
            <Archive size={18} />
            <p>Nenhuma mensagem importante ativa ainda. Assim que a primeira análise ou o próximo lote concluir, o cofre começa a ser preenchido.</p>
          </div>
        </Card>
      ) : importantSubTab === "overview" ? (
        <>
          <div className="important-overview-grid">
            <Card className="important-overview-card">
              <SectionTitle title="Sinal Forte" icon={BarChart3} />
              <p className="support-copy">
                Os itens abaixo tendem a ser os melhores candidatos para reuso futuro em contexto, operação e decisão.
              </p>
              <div className="important-list">
                {strongestMessages.map((message) => (
                  <CompactImportantCard key={message.id} message={message} type="signal" />
                ))}
              </div>
            </Card>

            <Card className="important-overview-card">
              <SectionTitle title="Revisar Primeiro" icon={Clock} />
              <p className="support-copy">
                Entram aqui mensagens ainda sem revisão automática ou com confiança mais baixa.
              </p>
              <div className="important-list">
                {reviewQueue.length > 0 ? reviewQueue.map((message) => (
                  <CompactImportantCard key={message.id} message={message} type="review" />
                )) : (
                  <div className="empty-hint">
                    <CheckCircle2 size={18} />
                    <p>Nenhum item fraco na fila agora.</p>
                  </div>
                )}
              </div>
            </Card>
          </div>

          <Card>
            <SectionTitle title="Entradas Mais Recentes" icon={Sparkles} />
            <div className="important-list">
              {latestMessages.map((message) => (
                <CompactImportantCard key={message.id} message={message} type="signal" />
              ))}
            </div>
          </Card>
        </>
      ) : (
        groupedMessages.length > 0 ? (
          groupedMessages.map(([groupLabel, groupMessages]) => (
            <Card key={groupLabel}>
              <SectionTitle title={`${groupLabel} (${groupMessages.length})`} icon={Archive} />
              <div className="important-list">
                {groupMessages.map((message) => (
                  <CompactImportantCard key={message.id} message={message} type="signal" />
                ))}
              </div>
            </Card>
          ))
        ) : (
          <Card>
            <div className="empty-hint">
              <Search size={18} />
              <p>Nenhuma mensagem bateu com a busca atual nessa subaba.</p>
            </div>
          </Card>
        )
      )}

      {error ? <InlineError title="Falha nas mensagens importantes" message={error} /> : null}
      {messages.length > 0 ? (
        <Card>
          <SectionTitle title="Sinal Forte" icon={BarChart3} />
          <p className="support-copy">
            Há {strongSignalsCount} item(ns) com confiança acima de 80. Eles costumam ser os melhores candidatos para
            reaproveitamento futuro em rotinas, projetos, acessos e dinheiro.
          </p>
        </Card>
      ) : null}
    </div>
  );
}

function ImportantMessageCard({ message }: { message: ImportantMessage }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <Card
      className={`important-card-collapsible ${isExpanded ? "important-card-expanded" : ""}`}
      onClick={() => setIsExpanded(!isExpanded)}
    >
      <div className="important-card-head">
        <div className="important-card-main-info">
          <div className="important-badges">
            <span className={`important-category-pill important-category-${message.category}`}>
              {formatImportantCategory(message.category)}
            </span>
            <span className="micro-badge">{getImportantCategoryFamilyLabel(message.category)}</span>
            <span className="micro-badge">{message.confidence}/100</span>
          </div>
          <h3>{message.contact_name || message.contact_phone || "Contato"}</h3>
          {!isExpanded && (
            <p className="important-message-preview">
              {truncateText(message.message_text, 120)}
            </p>
          )}
        </div>
        <div className="important-card-right">
          <div className="important-card-meta">
            <div className="important-date-group">
              <span>{formatRelativeTime(message.saved_at)}</span>
            </div>
            <div className={`expand-icon-wrap ${isExpanded ? "expand-icon-active" : ""}`}>
              <ChevronDown size={18} />
            </div>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="important-card-expanded-content">
          <div className="important-expanded-body">
            <div className="important-expanded-section">
              <div className="important-body-label">
                <MessageSquare size={14} />
                Conteúdo Original
              </div>
              <p className="important-message-text">{message.message_text}</p>
            </div>

            <div className="important-review-stack">
              <MiniPanel
                title="Por Que Foi Salva"
                tone="emerald"
                icon={Sparkles}
                content={message.importance_reason}
              />
              <MiniPanel
                title="Estado da Revisão"
                tone={getImportantConfidenceBand(message.confidence) === "low" ? "amber" : "emerald"}
                icon={Clock}
                content={
                  message.last_reviewed_at
                    ? `Revisada em ${formatShortDateTime(message.last_reviewed_at)}. ${message.review_notes ?? "Mantida no cofre ativo."}`
                    : "Ainda aguardando a primeira revisão diária automática."
                }
              />
            </div>
          </div>
          <div className="important-card-timestamp-footer">
            <Clock size={12} />
            <span>Mensagem de {formatShortDateTime(message.message_timestamp)}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function CompactImportantCard({ message, type }: { message: ImportantMessage, type?: "signal" | "review" }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <Card
      className={`important-card-collapsible important-compact-card ${isExpanded ? "important-card-expanded" : ""}`}
      onClick={() => setIsExpanded(!isExpanded)}
    >
      <div className="important-compact-head">
        <div className="important-compact-main">
          <span>{type === "review" ? getImportantConfidenceLabel(message.confidence) : formatImportantCategory(message.category)}</span>
          <strong>{message.contact_name || message.contact_phone || "Contato"}</strong>
          {!isExpanded && <p>{truncateText(type === "review" ? message.message_text : message.importance_reason, 90)}</p>}
        </div>
        <div className="important-compact-right">
          <div className="important-compact-meta">
            {type === "review" ? formatImportantCategory(message.category) : `${message.confidence}/100`}
          </div>
          <div className="important-compact-date">{formatRelativeTime(message.saved_at)}</div>
          <div className={`expand-icon-wrap ${isExpanded ? "expand-icon-active" : ""}`} style={{ width: 24, height: 24 }}>
            <ChevronDown size={14} />
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="important-compact-expanded-body">
          <div className="important-expanded-section">
            <div className="important-body-label">
              <MessageSquare size={12} />
              Conteúdo Original
            </div>
            <p className="important-message-text">{message.message_text}</p>
          </div>
          <div className="important-expanded-section">
            <div className="important-body-label">
              <Sparkles size={12} />
              Raciocínio da IA
            </div>
            <p className="support-copy" style={{ fontSize: "0.85rem", margin: 0 }}>
              {message.importance_reason}
            </p>
          </div>
          <div className="important-card-timestamp-footer">
            <Clock size={10} />
            <span>Mensagem de {formatShortDateTime(message.message_timestamp)}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function ChatTab({
  chatThreads,
  activeChatThread,
  chatMessages,
  chatDraft,
  chatError,
  streamingText,
  isSendingChat,
  isLoadingChatThread,
  isCreatingChatThread,
  deletingChatThreadIds,
  chatScrollRef,
  onChatDraftChange,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
  onApplyPrompt,
  onSubmit,
}: {
  chatThreads: ChatThread[];
  activeChatThread: ChatThread | null;
  chatMessages: ChatMessage[];
  chatDraft: string;
  chatError: string | null;
  streamingText: string | null;
  isSendingChat: boolean;
  isLoadingChatThread: boolean;
  isCreatingChatThread: boolean;
  deletingChatThreadIds: string[];
  chatScrollRef: React.RefObject<HTMLDivElement | null>;
  onChatDraftChange: (value: string) => void;
  onSelectThread: (threadId: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (thread: ChatThread) => void;
  onApplyPrompt: (value: string) => void;
  onSubmit: () => void;
}) {
  const quickPrompts = [
    "Me diga o que ficou pendente nos meus projetos.",
    "Resuma meu perfil de decisão.",
    "Monte um plano de prioridades para hoje.",
  ];

  const [threadSearch, setThreadSearch] = useState("");

  const filteredThreads = useMemo(() => {
    if (!threadSearch.trim()) return chatThreads;
    const lowerSearch = threadSearch.toLowerCase();
    return chatThreads.filter((t) => t.title.toLowerCase().includes(lowerSearch));
  }, [chatThreads, threadSearch]);

  const handleDraftChange = (val: string) => {
    // Regex shortcuts
    let newDraft = val;
    // Replace "/hoje" with current localized date
    newDraft = newDraft.replace(/(?:\b|^)\/hoje\b/gi, new Date().toLocaleDateString("pt-BR"));
    newDraft = newDraft.replace(/(?:\b|^)\/amanha\b/gi, () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      return tomorrow.toLocaleDateString("pt-BR");
    });
    // Replace "/tarefas" with quick prompt
    newDraft = newDraft.replace(/(?:\b|^)\/tarefas\b/gi, "liste as tarefas pendentes extraídas da minha memória");
    
    onChatDraftChange(newDraft);
  };

  return (
    <div className="gpt-chat-layout">
      {/* Thread Sidebar */}
      <aside className="gpt-thread-sidebar">
        <div className="gpt-thread-sidebar-top">
          <button className="gpt-new-chat-btn" onClick={onCreateThread} disabled={isCreatingChatThread} type="button">
            <Plus size={16} />
            {isCreatingChatThread ? "Criando..." : "Nova conversa"}
          </button>
          <div className="gpt-thread-search-box" style={{ marginTop: "0.75rem", position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--color-zinc-400)" }} />
            <input 
              type="text" 
              className="ac-input" 
              placeholder="Buscar histórico..." 
              value={threadSearch}
              onChange={(e) => setThreadSearch(e.target.value)}
              style={{ paddingLeft: "1.8rem", width: "100%", fontSize: "0.85rem" }}
            />
          </div>
        </div>

        <div className="gpt-thread-list">
          {filteredThreads.length === 0 ? (
            <p className="gpt-thread-empty">Nenhuma conversa encontrada.</p>
          ) : (
            filteredThreads.map((thread) => {
              const active = activeChatThread?.id === thread.id;
              const isDeleting = deletingChatThreadIds.includes(thread.id);
              return (
                <div key={thread.id} className={`gpt-thread-item${active ? " gpt-thread-item-active" : ""}`}>
                  <button
                    className="gpt-thread-item-main"
                    onClick={() => onSelectThread(thread.id)}
                    type="button"
                  >
                    <MessageSquare size={14} />
                    <span className="gpt-thread-title">{truncateText(thread.title, 32)}</span>
                    <span className="gpt-thread-time">{formatRelativeTime(thread.last_message_at ?? thread.updated_at)}</span>
                  </button>
                  {thread.can_delete ? (
                    <button
                      className="gpt-thread-delete-btn"
                      onClick={() => onDeleteThread(thread)}
                      type="button"
                      disabled={isDeleting}
                      aria-label={`Excluir conversa ${thread.title}`}
                      title={isDeleting ? "Excluindo..." : "Excluir conversa"}
                    >
                      <Trash2 size={14} />
                    </button>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <section className="gpt-chat-main">
        {/* Messages */}
        <div ref={chatScrollRef} className="gpt-messages-scroll">
          <div className="gpt-messages-container">
            {isLoadingChatThread ? (
              <div className="gpt-empty-state">
                <RefreshCw size={20} className="spin" />
                <p>Carregando conversa...</p>
              </div>
            ) : chatMessages.length === 0 && streamingText === null ? (
              <div className="gpt-empty-state">
                <div className="gpt-empty-icon">
                  <Brain size={32} />
                </div>
                <h3>Orion</h3>
                <p>Como posso ajudar você hoje?</p>
                <div className="gpt-suggestions">
                  {quickPrompts.map((prompt) => (
                    <button key={prompt} onClick={() => onApplyPrompt(prompt)} type="button" className="gpt-suggestion-btn">
                      <Sparkles size={14} />
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {chatMessages.map((message) => (
                  <div key={message.id} className={`gpt-message-row${message.role === "user" ? " gpt-message-user" : ""}`}>
                    <div className={`gpt-msg-avatar${message.role === "user" ? " gpt-msg-avatar-user" : ""}`}>
                      {message.role === "assistant" ? <Bot size={16} /> : <User size={16} />}
                    </div>
                    <div className="gpt-msg-content">
                      <div className="gpt-msg-meta">
                        <strong>{message.role === "assistant" ? "Orion" : "Você"}</strong>
                        <span>{formatShortDateTime(message.created_at)}</span>
                      </div>
                      <div className={`gpt-msg-bubble${message.role === "user" ? " gpt-msg-bubble-user" : ""}`}>
                        <p>{message.content}</p>
                      </div>
                    </div>
                  </div>
                ))}

                {/* Streaming response */}
                {streamingText !== null ? (
                  <div className="gpt-message-row">
                    <div className="gpt-msg-avatar">
                      <Bot size={16} />
                    </div>
                    <div className="gpt-msg-content">
                      <div className="gpt-msg-meta">
                        <strong>Orion</strong>
                        <span className="gpt-typing-indicator">digitando...</span>
                      </div>
                      <div className="gpt-msg-bubble">
                        <p>{streamingText}<span className="gpt-cursor">▊</span></p>
                      </div>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="gpt-composer-wrap">
          {chatError ? <InlineError title="Falha no chat" message={chatError} /> : null}
          <div className="gpt-composer">
            <textarea
              rows={1}
              value={chatDraft}
              onChange={(event) => handleDraftChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onSubmit();
                }
              }}
              placeholder="Envie uma mensagem..."
              disabled={isSendingChat}
            />
            <button className="gpt-send-btn" onClick={onSubmit} disabled={isSendingChat || !chatDraft.trim()} type="button">
              <Send size={18} />
            </button>
          </div>
          <p className="gpt-composer-note">Pressione Enter para enviar.</p>
        </div>
      </section>
    </div>
  );
}


function ActivityTab({
  agentState,
  steps,
  logs,
  memory,
  latestSnapshot,
  projectsCount,
  snapshotsCount,
  automationStatus,
  automationError,
  isClearingDatabase,
  onClearDatabase,
  embedded = false,
}: {
  agentState: DisplayAgentState;
  steps: AgentStep[];
  logs: AgentLog[];
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projectsCount: number;
  snapshotsCount: number;
  automationStatus: AutomationStatus | null;
  automationError: string | null;
  isClearingDatabase: boolean;
  onClearDatabase: () => void;
  embedded?: boolean;
}) {
  const [activitySubTab, setActivitySubTab] = useState<"overview" | "persist" | "logs">("overview");
  const memoryReady = hasEstablishedMemory(memory, latestSnapshot);
  const resolvedIntent = agentState.intent ?? (memoryReady ? "improve_memory" : "first_analysis");
  const latestDecision = automationStatus?.decisions[0] ?? null;
  const latestSyncRun = automationStatus?.sync_runs[0] ?? null;
  const latestJob = automationStatus?.jobs[0] ?? null;
  const latestModelRun = automationStatus?.model_runs[0] ?? null;
  const hasPendingDatabaseWork = Boolean(
    agentState.running ||
    automationStatus?.running_job_id ||
    automationStatus?.queued_jobs_count,
  );
  const thinkingLines = buildActivityThinking({
    intent: resolvedIntent,
    hasMemory: memoryReady,
    projectsCount,
    snapshotsCount,
  });
  const resolvedThinking = latestDecision?.explanation
    ? [latestDecision.explanation, ...thinkingLines]
    : thinkingLines;
  const traceItems = useMemo(
    () =>
      buildActivityTrace({
        agentState,
        latestSyncRun,
        latestDecision,
        latestJob,
        latestModelRun,
      }),
    [agentState, latestDecision, latestJob, latestModelRun, latestSyncRun],
  );
  const displayedLogs = logs.slice(0, 18);
  const hasSavedDeepSeekThought = Boolean(latestDecision?.explanation?.trim());

  const subTabs = [
    { id: "overview" as const, label: "Visão Geral", icon: BarChart3 },
    { id: "persist" as const, label: "Persistência", icon: Database },
    { id: "logs" as const, label: "Lab IA", icon: Terminal },
  ];

  return (
    <div className={`page-stack narrow-stack${embedded ? " memory-embedded-activity" : ""}`}>
      <div className="section-head">
        <div className="activity-subtab-bar">
          {subTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`activity-subtab${activitySubTab === tab.id ? " activity-subtab-active" : ""}`}
                onClick={() => setActivitySubTab(tab.id)}
                type="button"
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <span className={`micro-status micro-status-${agentState.running ? "teal" : "zinc"}`}>
          {agentState.running ? "pipeline ativo" : "monitorando"}
        </span>
      </div>

      {/* Hero card — always visible */}
      <Card className="activity-hero-card">
        <div className="activity-hero-meter">
          <svg viewBox="0 0 120 120">
            <circle className="activity-ring-base" cx="60" cy="60" r="50" />
            <circle
              className={`activity-ring-fill${agentState.running ? " activity-ring-fill-live" : ""}${agentState.error ? " activity-ring-fill-error" : ""}${agentState.progress >= 100 && !agentState.error ? " activity-ring-fill-complete" : ""}`}
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
            <span className={`micro-status micro-status-${agentState.badgeTone}`}>
              {agentState.running ? "Processando" : "Ocioso"}
            </span>
          </div>
          <p>{agentState.status}</p>
          <div className="step-pill-row">
            {steps.map((step, stepIndex) => {
              const { completed, active } = getStepVisualState(agentState, stepIndex, steps.length);
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

      {/* === OVERVIEW sub-tab === */}
      {activitySubTab === "overview" ? (
        <>
          <div className="activity-insight-grid">
            <MemorySignalCard
              label="Ação atual"
              value={latestJob ? getIntentTitle(latestJob.intent as AgentIntent) : getIntentTitle(resolvedIntent)}
              meta={latestJob ? `${latestJob.status} via ${latestJob.trigger_source}` : memoryReady ? "Memória base já existe" : "Ainda sem base consolidada"}
              accent
            />
            <MemorySignalCard
              label="Último sync"
              value={latestSyncRun ? `${formatTokenCount(latestSyncRun.messages_saved_count)} salvas` : "..."}
              meta={
                latestSyncRun
                  ? `${latestSyncRun.status} • ${formatShortDateTime(latestSyncRun.finished_at ?? latestSyncRun.started_at)}`
                  : "Aguardando primeira sincronização persistida"
              }
              tone="indigo"
            />
            <MemorySignalCard
              label="Último modelo"
              value={latestModelRun ? latestModelRun.run_type : "..."}
              meta={latestModelRun ? `${latestModelRun.success ? "sucesso" : "falha"} • ${formatShortDateTime(latestModelRun.created_at)}` : "Sem execução de modelo persistida ainda"}
              tone="emerald"
            />
            <MemorySignalCard
              label="Fila manual"
              value={automationStatus ? String(automationStatus.queued_jobs_count) : "..."}
              meta={
                automationStatus
                  ? `${automationStatus.running_job_id ? "Existe 1 job em execução agora" : "Nenhum job rodando agora"}`
                  : "Aguardando status"
              }
              tone="amber"
            />
          </div>

          <Card className="activity-thinking-card">
            <SectionTitle title="Linha Operacional" icon={Brain} />
            <p className="support-copy">Este bloco resume o estado atual da rotina de leitura e o que foi entendido do processo recente.</p>
            <div className="activity-thinking-list">
              {resolvedThinking.map((line, index) => (
                <div key={`${line.slice(0, 20)}-${index}`} className="activity-thinking-item">
                  <span>{index + 1}</span>
                  <p>{line}</p>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : null}

      {/* === PERSIST sub-tab === */}
      {activitySubTab === "persist" ? (
        <>
          <div className="activity-insight-grid">
            <MemorySignalCard
              label="Fila"
              value={automationStatus ? String(automationStatus.queued_jobs_count) : "..."}
              meta={automationStatus?.running_job_id ? "Há job rodando agora" : "Sem job em execução"}
            />
            <MemorySignalCard
              label="Base já conhecida"
              value={`${formatTokenCount(snapshotsCount)} snapshots / ${formatTokenCount(projectsCount)} projetos`}
              meta={memoryReady ? "Também cruza com o chat pessoal salvo" : "Primeira base ainda será criada"}
              tone="zinc"
            />
            <MemorySignalCard
              label="Último processamento"
              value={latestJob ? latestJob.status : "..."}
              meta={
                latestJob
                  ? `${getIntentTitle(latestJob.intent as AgentIntent)} • ${formatShortDateTime(latestJob.created_at)}`
                  : "Sem processamento registrado ainda"
              }
              tone="indigo"
            />
            <MemorySignalCard
              label="Último snapshot"
              value={latestSnapshot ? formatShortDateTime(latestSnapshot.created_at) : "..."}
              meta={
                latestSnapshot
                  ? `${formatTokenCount(latestSnapshot.source_message_count)} mensagens • ${formatTokenCount(latestSnapshot.distinct_contact_count)} contatos • cobertura ${latestSnapshot.coverage_score}/100`
                  : "Aguardando primeira leitura"
              }
              tone={getSnapshotCoverageTone(latestSnapshot)}
            />
          </div>

          <div className="activity-persist-grid">
            <Card>
              <SectionTitle title="Sync Persistido" icon={RefreshCw} />
              {latestSyncRun ? (
                <div className="activity-persist-list">
                  <StatusLine label="Status" value={latestSyncRun.status} tone={latestSyncRun.status === "failed" ? "amber" : "emerald"} />
                  <StatusLine label="Mensagens vistas" value={formatTokenCount(latestSyncRun.messages_seen_count)} tone="indigo" />
                  <StatusLine label="Salvas" value={formatTokenCount(latestSyncRun.messages_saved_count)} tone="emerald" />
                  <StatusLine label="Podadas" value={formatTokenCount(latestSyncRun.messages_pruned_count)} tone="amber" />
                </div>
              ) : (
                <div className="empty-hint">
                  <RefreshCw size={18} />
                  <p>Nenhum sync persistido ainda.</p>
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle title="Decisão Persistida" icon={Zap} />
              {latestDecision ? (
                <div className="activity-persist-block">
                  <strong>{latestDecision.intent}</strong>
                  <p>{latestDecision.explanation}</p>
                  <div className="activity-meta-row">
                    <span>{latestDecision.action}</span>
                    <span>{latestDecision.reason_code}</span>
                    <span>{latestDecision.score}/100</span>
                  </div>
                </div>
              ) : (
                <div className="empty-hint">
                  <Zap size={18} />
                  <p>Nenhuma decisão persistida ainda.</p>
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle title="Execução Recente" icon={Cpu} />
              {latestModelRun ? (
                <div className="activity-persist-block">
                  <strong>{latestModelRun.run_type}</strong>
                  <p>{latestModelRun.success ? "Concluída com sucesso" : "Concluída com falha"}</p>
                  <div className="activity-meta-row">
                    <span>{latestModelRun.latency_ms ? `${latestModelRun.latency_ms} ms` : "latência n/d"}</span>
                    <span>{formatShortDateTime(latestModelRun.created_at)}</span>
                  </div>
                </div>
              ) : (
                <div className="empty-hint">
                  <Cpu size={18} />
                  <p>Nenhuma execução registrada ainda.</p>
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}

      {/* === LOGS sub-tab === */}
      {activitySubTab === "logs" ? (
        <div className="activity-lab-grid">
          <Card className="activity-lab-hero">
            <div className="activity-lab-head">
              <div>
                <div className="hero-kicker">
                  <Sparkles size={14} />
                  DeepSeek Workspace
                </div>
                <h3>Rastro do processamento</h3>
                <p>
                  Esta area tenta mostrar como o pipeline esta pensando e executando usando apenas os sinais que o backend
                  realmente persiste.
                </p>
              </div>
              <div className="activity-lab-badges">
                <span className={`micro-status micro-status-${agentState.running ? "indigo" : "emerald"}`}>
                  {agentState.running ? "Analisando agora" : "Em espera"}
                </span>
                <span className="micro-status micro-status-zinc">
                  {latestModelRun?.provider === "deepseek" ? "DeepSeek ativo" : "Sem motor recente"}
                </span>
              </div>
            </div>

            <div className="activity-lab-metrics">
              <div className="activity-lab-metric">
                <span>Estado atual</span>
                <strong>{agentState.running ? "Processando lote" : latestJob?.status ?? "Sem execucao"}</strong>
                <small>{agentState.running ? agentState.status : "Ultimo estado conhecido do pipeline"}</small>
              </div>
              <div className="activity-lab-metric">
                <span>Sintese salva</span>
                <strong>{hasSavedDeepSeekThought ? "Disponivel" : "Limitada"}</strong>
                <small>
                  {hasSavedDeepSeekThought
                    ? "Existe uma explicacao persistida da decisao mais recente."
                    : "O backend nao salva o pensamento bruto completo do modelo hoje."}
                </small>
              </div>
              <div className="activity-lab-metric">
                <span>Ultima atividade</span>
                <strong>
                  {traceItems[0]?.timestamp ? formatShortDateTime(traceItems[0].timestamp) : "Sem atividade"}
                </strong>
                <small>{traceItems[0]?.title ?? "Aguardando novo ciclo"}</small>
              </div>
            </div>
          </Card>

          <div className="activity-lab-columns">
            <Card className="activity-trace-card">
              <SectionTitle title="Linha de Pensamento Disponivel" icon={Brain} />
              {hasSavedDeepSeekThought ? (
                <div className="activity-thought-stack">
                  <div className="activity-thought-primary">
                    <span className="activity-thought-label">Sintese persistida</span>
                    <p>{latestDecision?.explanation}</p>
                  </div>
                  <div className="activity-thought-secondary">
                    {resolvedThinking.map((line, index) => (
                      <div key={`${line.slice(0, 20)}-${index}`} className="activity-thought-chip">
                        <span>{index + 1}</span>
                        <p>{line}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="activity-thought-empty">
                  <Brain size={18} />
                  <p>
                    O pensamento bruto do DeepSeek nao e salvo no backend neste momento. O que aparece aqui e a melhor
                    sintese operacional persistida: status atual, decisao registrada e trilha de execucao.
                  </p>
                </div>
              )}
            </Card>

            <Card className="activity-trace-card">
              <SectionTitle title="Timeline de Execucao" icon={GitBranch} />
              <div className="activity-trace-list">
                {traceItems.length > 0 ? (
                  traceItems.map((item) => (
                    <div key={item.id} className={`activity-trace-item activity-trace-${item.tone}`}>
                      <div className="activity-trace-dot" />
                      <div className="activity-trace-content">
                        <div className="activity-trace-top">
                          <strong>{item.title}</strong>
                          <span>{item.timestamp ? formatShortDateTime(item.timestamp) : "Agora"}</span>
                        </div>
                        <p>{item.detail}</p>
                        <div className="activity-trace-meta">
                          <span>{getActivityToneLabel(item.tone)}</span>
                          {item.meta ? <span>{item.meta}</span> : null}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="activity-thought-empty">
                    <GitBranch size={18} />
                    <p>Nenhum rastro persistido ainda. Assim que o pipeline rodar, esta timeline comeca a se preencher.</p>
                  </div>
                )}
              </div>
            </Card>
          </div>

          <div className="terminal-shell activity-terminal-shell">
            <div className="terminal-header activity-terminal-header">
              <div className="activity-terminal-leds">
                <span className="terminal-dot terminal-dot-red" />
                <span className="terminal-dot terminal-dot-yellow" />
                <span className="terminal-dot terminal-dot-green" />
              </div>
              <div className="activity-terminal-titles">
                <strong>deepseek-runtime.log</strong>
                <span>eventos recentes do pipeline</span>
              </div>
              <span className={`micro-status micro-status-${agentState.running ? "indigo" : "zinc"}`}>
                {agentState.running ? "stream ativo" : "aguardando"}
              </span>
            </div>
            <div className="terminal-body">
              {displayedLogs.map((log, index) => (
                <div key={log.id} className={`terminal-line activity-terminal-line activity-terminal-${log.tone}`}>
                  <span className="activity-terminal-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="terminal-time">{formatShortDateTime(log.createdAt)}</span>
                  <span className={`terminal-tag terminal-tag-${log.tone}`}>[{log.tone}]</span>
                  <span className="terminal-message">{log.message}</span>
                </div>
              ))}
              {displayedLogs.length === 0 ? (
                <div className="activity-thought-empty">
                  <Terminal size={18} />
                  <p>Sem logs recentes por enquanto.</p>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      <Card className="activity-maintenance-card">
        <div className="activity-maintenance-copy">
          <SectionTitle title="Zona de Manutenção" icon={Trash2} />
          <p className="support-copy">
            Esta acao existe para reinicios realmente limpos. Ela apaga os dados persistidos do ambiente local, incluindo
            mensagens, memoria, snapshots, sessoes e configuracoes salvas.
          </p>
          <p className="support-copy">
            {hasPendingDatabaseWork
              ? "A manutencao total esta bloqueada porque ainda existe fila manual ou pipeline ativo."
              : "Nenhum job esta rodando agora. Se precisar zerar o ambiente local, a exclusao total ja pode ser usada."}
          </p>
        </div>
        <button
          className="ac-danger-button"
          onClick={onClearDatabase}
          disabled={isClearingDatabase || hasPendingDatabaseWork}
          type="button"
          title={hasPendingDatabaseWork ? "Aguarde a fila e os jobs terminarem antes de apagar o banco." : "Apagar todos os dados salvos no banco local"}
        >
          <Trash2 size={15} />
          {isClearingDatabase ? "Apagando banco..." : "Excluir todo o banco"}
        </button>
      </Card>

      {automationError ? <InlineError title="Falha na automação" message={automationError} /> : null}
    </div>
  );
}

function AutomationTab({
  automationStatus,
  automationDraft,
  automationError,
  isSavingAutomation,
  isTickingAutomation,
  onDraftChange,
  onSave,
  onTick,
}: {
  automationStatus: AutomationStatus | null;
  automationDraft: AutomationDraft | null;
  automationError: string | null;
  isSavingAutomation: boolean;
  isTickingAutomation: boolean;
  onDraftChange: React.Dispatch<React.SetStateAction<AutomationDraft | null>>;
  onSave: () => void;
  onTick: () => void;
}) {
  const operationalLatestJob = automationStatus?.jobs?.[0] ?? null;
  const operationalLatestSync = automationStatus?.sync_runs?.[0] ?? null;
  const operationalLatestDecision = automationStatus?.decisions?.[0] ?? null;
  const operationalSettingsUpdatedAt = automationStatus?.settings?.updated_at ?? null;

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle
          title="Automacao Controlada"
          icon={Settings}
          action={
            operationalSettingsUpdatedAt ? (
              <span className="micro-badge">{formatShortDateTime(operationalSettingsUpdatedAt)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Esta area mostra so o estado operacional do loop automatico. Sem memoria inicial, nada entra na fila sozinho.
          Depois da primeira analise, o backend processa 1 lote economico de mensagens novas por ciclo.
        </p>

        <div className="automation-top-grid">
          <MemorySignalCard
            label="Fila"
            value={automationStatus ? String(automationStatus.queued_jobs_count) : "..."}
            meta={automationStatus?.running_job_id ? "Ha job rodando agora" : "Sem job rodando"}
            accent
          />
          <MemorySignalCard
            label="Jobs automaticos hoje"
            value={automationStatus ? String(automationStatus.daily_auto_jobs_count) : "..."}
            meta={automationStatus ? "Lotes concluidos automaticamente hoje" : "Aguardando status"}
            tone="indigo"
          />
          <MemorySignalCard
            label="Ultimo sync"
            value={operationalLatestSync ? operationalLatestSync.status : "..."}
            meta={operationalLatestSync ? formatShortDateTime(operationalLatestSync.started_at) : "Sem sync persistido"}
            tone="emerald"
          />
          <MemorySignalCard
            label="Ultima decisao"
            value={operationalLatestDecision ? operationalLatestDecision.action : "..."}
            meta={operationalLatestDecision ? operationalLatestDecision.reason_code : "Sem decisao persistida"}
            tone="amber"
          />
        </div>

        <div className="hero-actions">
          <button className="ac-secondary-button" onClick={onTick} disabled={isTickingAutomation} type="button">
            <RefreshCw size={15} className={isTickingAutomation ? "spin" : ""} />
            {isTickingAutomation ? "Processando..." : "Rodar Tick Agora"}
          </button>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Leitura Operacional" icon={Activity} />
        <div className="manual-grid">
          <ManualInfoCard
            title="Ultima decisao"
            text={
              operationalLatestDecision
                ? `${operationalLatestDecision.action} por ${operationalLatestDecision.reason_code} em ${formatShortDateTime(operationalLatestDecision.created_at)}.`
                : "Ainda nao existe nenhuma decisao persistida."
            }
          />
          <ManualInfoCard
            title="Ultimo job"
            text={
              operationalLatestJob
                ? `${getIntentTitle(operationalLatestJob.intent as AgentIntent)} ficou em ${operationalLatestJob.status} e foi criado em ${formatShortDateTime(operationalLatestJob.created_at)}.`
                : "Nenhum job foi salvo ainda."
            }
          />
          <ManualInfoCard
            title="Ultimo sync"
            text={
              operationalLatestSync
                ? `${operationalLatestSync.status} via ${operationalLatestSync.trigger} em ${formatShortDateTime(operationalLatestSync.started_at)}.`
                : "Nenhum sync foi persistido ainda."
            }
          />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Historico Recente" icon={Clock} />
        <div className="automation-history-grid">
          <div className="activity-persist-block">
            <strong>Jobs recentes</strong>
            {(automationStatus?.jobs ?? []).slice(0, 4).map((job) => (
              <div key={job.id} className="activity-meta-row">
                <span>{getIntentTitle(job.intent as AgentIntent)}</span>
                <span>{job.status}</span>
                <span>{formatShortDateTime(job.created_at)}</span>
              </div>
            ))}
          </div>
          <div className="activity-persist-block">
            <strong>Syncs recentes</strong>
            {(automationStatus?.sync_runs ?? []).slice(0, 4).map((syncRun) => (
              <div key={syncRun.id} className="activity-meta-row">
                <span>{syncRun.trigger}</span>
                <span>{syncRun.status}</span>
                <span>{formatShortDateTime(syncRun.started_at)}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {automationError ? <InlineError title="Falha na automacao" message={automationError} /> : null}
    </div>
  );
}

function ManualTab({
  status,
  memory,
  projects,
  snapshots,
  importantMessages,
  chatThreads,
  chatMessages,
  automationStatus,
}: {
  status: ObserverStatus | null;
  memory: MemoryCurrent | null;
  projects: ProjectMemory[];
  snapshots: MemorySnapshot[];
  importantMessages: ImportantMessage[];
  chatThreads: ChatThread[];
  chatMessages: ChatMessage[];
  automationStatus: AutomationStatus | null;
}) {
  const [manualSubTab, setManualSubTab] = useState<"overview" | "flow" | "architecture" | "data" | "operations">("overview");
  const latestSnapshot = snapshots[0] ?? null;
  const memoryReady = Boolean(memory?.last_analyzed_at);
  const projectCount = projects.length;
  const importantCount = importantMessages.length;
  const threadCount = chatThreads.length;
  const manualTabs = [
    "Visao Geral",
    "Fluxo Real",
    "Arquitetura",
    "Dados",
    "Operacao",
  ];

  return (
    <div className="page-stack">
      <Card className="manual-hero-card">
        <div className="manual-hero-copy">
          <div className="hero-kicker">
            <FileText size={14} />
            Central de Operacao
          </div>
          <h3>O AuraCore e um operador de contexto pessoal em cima do WhatsApp.</h3>
          <p>
            Ele conecta o observador, filtra conversas uteis, consolida memoria do dono, salva memoria por
            pessoa, identifica mensagens importantes, organiza projetos e ainda oferece um chat pessoal que responde usando
            esse contexto inteiro. Grupos so entram depois da base inicial e apenas quando voce ativa na aba Grupos.
          </p>
        </div>
        <div className="manual-hero-stats">
          <ModernStatCard
            label="Observador"
            value={status?.connected ? "Online" : "Pendente"}
            meta={status?.connected ? "Capturando diretas e grupos observados" : "Conecte o WhatsApp primeiro"}
            icon={Eye}
            tone="emerald"
          />
          <ModernStatCard
            label="Memoria Base"
            value={memoryReady ? "Pronta" : "Nao criada"}
            meta={memoryReady ? `Desde ${formatShortDateTime(memory?.last_analyzed_at ?? null)}` : "Primeira analise ainda nao foi rodada"}
            icon={Database}
            tone="indigo"
          />
          <ModernStatCard
            label="Memorias por pessoa"
            value={String(projectCount > 0 || importantCount > 0 || snapshots.length > 0 ? "Ativas" : "Vazias")}
            meta="Atualizadas progressivamente por contato"
            icon={User}
            tone="amber"
          />
        </div>
      </Card>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={manualTabs}
          selected={
            manualSubTab === "overview"
              ? "Visao Geral"
              : manualSubTab === "flow"
                ? "Fluxo Real"
                : manualSubTab === "architecture"
                  ? "Arquitetura"
                  : manualSubTab === "data"
                    ? "Dados"
                    : "Operacao"
          }
          onChange={(value) => {
            if (value === "Visao Geral") setManualSubTab("overview");
            if (value === "Fluxo Real") setManualSubTab("flow");
            if (value === "Arquitetura") setManualSubTab("architecture");
            if (value === "Dados") setManualSubTab("data");
            if (value === "Operacao") setManualSubTab("operations");
          }}
        />
      </div>

      {manualSubTab === "overview" ? (
        <>
          <Card>
            <SectionTitle title="Como Ler Este Produto" icon={Brain} />
            <div className="manual-grid">
              <div className="manual-list">
                <p>O site e dividido em duas camadas. A primeira e operacional: conectar o WhatsApp, ler mensagens, acompanhar a fila e ver os jobs. A segunda e cognitiva: consolidar memoria, mapear projetos, salvar sinais importantes e conversar com contexto.</p>
                <p>O Observador cuida da entrada. A Memoria cuida da consolidacao. Importantes e Projetos guardam o que merece sobreviver. O Chat usa tudo isso para responder. Atividade mostra o que o backend fez ou esta fazendo.</p>
              </div>
              <div className="manual-list">
                <p>Para o usuario final, a ideia e simples: conectar, fazer a primeira analise, puxar mensagens novas quando quiser e rodar a analise manual para manter o contexto vivo.</p>
                <p>Para voce localizar qualquer problema, pense assim: entrada de dados em Observador, consolidacao em Memoria, armazenamento no banco local e leitura do estado em Atividade.</p>
              </div>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Mapa Das Abas" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="Visao Geral" text="Painel-resumo do estado atual: conexao, memoria, projetos, sinais e atalhos para o fluxo principal." icon={BarChart3} tone="indigo" />
              <ManualInfoCard title="Observador" text="Ponto de entrada do WhatsApp. Mostra QR, estado da instancia, sessao e a saude da captura." icon={Eye} tone="emerald" />
              <ManualInfoCard title="Grupos" text="Lista os grupos vistos no historico sincronizado. Todos nascem desativados e so entram na memoria incremental quando voce ativa." icon={Users} tone="amber" />
              <ManualInfoCard title="Memoria" text="Aqui nasce e evolui a memoria central. Primeira analise, lotes economicos de mensagens novas, estado da fila e resumo do dono." icon={Database} tone="indigo" />
              <ManualInfoCard title="Importantes" text="Cofre de fatos duraveis: acessos, valores, clientes, prazos, riscos e sinais operacionais reaproveitaveis." icon={Archive} tone="amber" />
              <ManualInfoCard title="Projetos" text="Organiza frentes reais detectadas nas conversas, com resumo, status, evidencias e proximos passos." icon={FolderGit2} tone="emerald" />
              <ManualInfoCard title="Chat Pessoal" text="Thread por assunto usando a memoria central. Bom para separar estrategia, rotina, vendas, produto e operacao." icon={MessageSquare} tone="indigo" />
              <ManualInfoCard title="Atividade" text="Mostra o pipeline trabalhando: logs, lotes, trilha de execucao e o melhor raciocinio operacional salvo." icon={Activity} tone="emerald" />
              <ManualInfoCard title="Atividade Manual" text="Mostra syncs recentes, jobs manuais e execucoes de modelo persistidas no backend." icon={Terminal} tone="zinc" />
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "flow" ? (
        <>
          <Card>
            <SectionTitle title="Fluxo Real Do Site" icon={Terminal} />
            <div className="manual-sequence">
              <ManualStep title="1. Conectar o observador" text="Voce gera o QR, conecta o WhatsApp e libera a captura. A partir daqui o sistema passa a receber somente o que interessa para memoria." icon={Eye} tone="emerald" />
              <ManualStep title="2. Filtrar a entrada" text="Nem tudo entra. A ingestao evita status, broadcast, newsletter e lixo sem texto relevante. Conversas diretas entram por padrao; grupos ficam opt-in para leituras futuras." icon={Activity} tone="indigo" />
              <ManualStep title="3. Criar a memoria base" text="A primeira analise e manual e usa uma selecao balanceada das mensagens diretas mais relevantes e recentes." icon={Database} tone="amber" />
              <ManualStep title="4. Atualizar por contato" text="Durante as analises, o sistema tenta entender com quem e cada conversa e atualiza memorias separadas por pessoa." icon={User} tone="indigo" />
              <ManualStep title="5. Processar em lotes" text="Depois da base inicial, o backend passa a trabalhar em lotes economicos de mensagens novas." icon={RefreshCw} tone="emerald" />
              <ManualStep title="6. Salvar o que dura" text="O processamento atualiza resumo do dono, snapshots, projetos, e itens duraveis." icon={Archive} tone="amber" />
              <ManualStep title="7. Reutilizar no chat" text="O chat pessoal consome a memoria consolidada, projetos, contexto da thread e sinais importantes." icon={MessageSquare} tone="indigo" />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Botoes Principais" icon={Zap} />
            <div className="manual-grid">
              <ManualInfoCard title="Puxar Novas Mensagens" text="Forca uma releitura das conversas recentes e atualiza a fila operacional no banco." icon={RefreshCw} tone="indigo" />
              <ManualInfoCard title="Primeira Analise" text="Cria a base inicial da memoria quando o sistema ainda nao conhece bem o dono." icon={Play} tone="emerald" />
              <ManualInfoCard title="Executar Analise" text="Usa as mensagens pendentes mais a memoria ja salva para atualizar resumo, importantes e projetos de forma incremental." icon={Sparkles} tone="indigo" />
              <ManualInfoCard title="Nova Conversa" text="Abre uma thread nova no chat sem perder a memoria central nem o restante do historico salvo." icon={Plus} tone="amber" />
              <ManualInfoCard title="Rodar Tick" text="Executa o ciclo da automacao manualmente: fecha syncs, registra decisoes e tenta processar a fila." icon={Zap} tone="emerald" />
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "architecture" ? (
        <>
          <Card>
            <SectionTitle title="Arquitetura Em Camadas" icon={Server} />
            <div className="manual-grid">
              <ManualInfoCard title="Frontend" text="O painel organiza as abas de operacao, memoria, atividade e chat. Ele consulta a API e mostra o estado persistido do sistema." icon={Smartphone} tone="indigo" />
              <ManualInfoCard title="Backend FastAPI" text="Coordena observador, memoria, automacao, chat e persistencia. E onde ficam as regras de selecao de mensagens." icon={Server} tone="emerald" />
              <ManualInfoCard title="Banco local SQLite" text="Armazena mensagens operacionais, snapshots, persona, projetos, memorias por pessoa, threads do chat e trilhas." icon={Database} tone="amber" />
              <ManualInfoCard title="Modelos de IA" text="O motor de analise consolida memoria e o chat responde usando o contexto salvo do banco de dados local." icon={Brain} tone="indigo" />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Como Cada Parte Se Conversa" icon={GitBranch} />
            <div className="manual-list">
              <p>Observador envia mensagens para o backend. O backend decide o que entra em `mensagens`, separa diretas de grupos e atualiza a fila operacional.</p>
              <p>A Memoria seleciona uma janela ou um lote, monta o prompt com contexto consolidado e grava de volta os resultados mais importantes.</p>
              <p>O Chat nao le o WhatsApp cru. Ele conversa em cima da memoria consolidada, do historico da thread atual, dos projetos e dos sinais duraveis.</p>
              <p>A Automacao observa se existe memoria base, conta mensagens novas e enfileira no maximo um lote automatico por ciclo quando faz sentido.</p>
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "data" ? (
        <>
          <Card>
            <SectionTitle title="O Que Vai Para O Banco Local" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="mensagens" text="Fila operacional de mensagens aproveitaveis." icon={MessageSquare} tone="zinc" />
              <ManualInfoCard title="persona & snapshots" text="Resumo principal do dono e historico consolidado." icon={Fingerprint} tone="emerald" />
              <ManualInfoCard title="person_memories" text="Memoria separada por contato ou participante progressivamente." icon={User} tone="amber" />
              <ManualInfoCard title="project_memories" text="Projetos, frentes, entregas com base nas conversas." icon={FolderGit2} tone="indigo" />
              <ManualInfoCard title="important_messages" text="Cofre de itens duraveis como acessos, valores." icon={Archive} tone="amber" />
              <ManualInfoCard title="chat_threads" text="Threads do chat pessoal para separar contextos." icon={MessageSquare} tone="zinc" />
              <ManualInfoCard title="Logs do motor" text="Auditoria operacional sincronizada, processada e executada." icon={Activity} tone="emerald" />
              <ManualInfoCard title="wa_sessions" text="Estado de sessao e chaves locais." icon={Eye} tone="zinc" />
            </div>
          </Card>

          <Card>
            <SectionTitle title="O Que Nunca Deve Subir" icon={XCircle} />
            <div className="manual-list">
              <p>Grupos, canais, newsletter, broadcast e status.</p>
              <p>Ruido sem valor contextual, lixo sem texto util e mensagens puramente sistemicas.</p>
              <p>Explicacoes internas do pipeline na interface final quando elas nao ajudam o usuario a operar o sistema.</p>
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "operations" ? (
        <>
          <Card>
            <SectionTitle title="Estado Atual Da Operacao" icon={Activity} />
            <div className="manual-grid">
              <ManualInfoCard
                title="Observador"
                text={status?.connected ? `Conectado com ${status.owner_number ?? "numero ainda nao lido"}.` : "Desconectado ou aguardando leitura do QR."}
              />
              <ManualInfoCard
                title="Memoria Central"
                text={
                  memory?.last_analyzed_at
                    ? `Ultima consolidacao em ${formatDateTime(memory.last_analyzed_at)}.`
                    : "Ainda sem consolidacao inicial."
                }
                icon={memory?.last_analyzed_at ? Database : AlertCircle}
                tone={memory?.last_analyzed_at ? "indigo" : "amber"}
              />
              <ManualInfoCard
                title="Ultimo Snapshot"
                text={
                  latestSnapshot
                    ? `Ultima janela consolidada em ${formatShortDateTime(latestSnapshot.created_at)} com ${latestSnapshot.source_message_count} mensagens.`
                    : "Nenhum snapshot consolidado ainda."
                }
                icon={latestSnapshot ? Fingerprint : Brain}
                tone={latestSnapshot ? "emerald" : "zinc"}
              />
              <ManualInfoCard
                title="Mensagens Importantes"
                text={
                  importantCount > 0
                    ? `${importantCount} item(ns) ativos no cofre, atualizados pelas execucoes manuais de analise.`
                    : "Nenhuma mensagem importante ativa ainda."
                }
                icon={Archive}
                tone={importantCount > 0 ? "amber" : "zinc"}
              />
              <ManualInfoCard
                title="Projetos e Threads"
                text={`${projectCount} projeto(s) consolidado(s), ${threadCount} thread(s) no chat e ${chatMessages.length} mensagem(ns) na thread aberta.`}
              />
              <ManualInfoCard
                title="Fila Manual"
                text={
                  automationStatus
                    ? `${automationStatus.queued_jobs_count} job(s) na fila e ${automationStatus.running_job_id ? "1 execucao em andamento" : "nenhuma execucao rodando agora"}.`
                    : "Status da atividade manual ainda nao carregado."
                }
                icon={automationStatus?.running_job_id ? Zap : Clock}
                tone={automationStatus?.running_job_id ? "emerald" : "zinc"}
              />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Como Diagnosticar Rapido" icon={AlertCircle} />
            <div className="manual-grid">
              <ManualInfoCard title="Sem mensagens" text="Olhe primeiro a aba Observador e a releitura manual." icon={AlertCircle} tone="amber" />
              <ManualInfoCard title="Sem memoria base" text="Rode manualmente a primeira analise na aba Memoria." icon={Database} tone="indigo" />
              <ManualInfoCard title="Chat ruim/vazio" text="Confira se ja existe memoria consolidada e historico." icon={XCircle} tone="emerald" />
              <ManualInfoCard title="Fila travada" text="Use Atividade e Automacao para ver rastro." icon={Terminal} tone="zinc" />
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function ManualInfoCard({ 
  title, 
  text, 
  icon: Icon, 
  tone = "zinc" 
}: { 
  title: string; 
  text: string; 
  icon?: LucideIcon; 
  tone?: "emerald" | "amber" | "indigo" | "zinc" 
}) {
  return (
    <div className={`manual-info-card manual-info-card-${tone}`}>
      <div className="manual-info-card-icon">
        {Icon && <Icon size={20} />}
      </div>
      <div className="manual-info-card-content">
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </div>
  );
}

function AgentMetricPanel({
  label,
  value,
  meta,
}: {
  label: string;
  value: string;
  meta: string;
}) {
  return (
    <div className="agent-metric-panel">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{meta}</small>
    </div>
  );
}

function ManualStep({ 
  title, 
  text, 
  icon: Icon, 
  tone = "indigo" 
}: { 
  title: string; 
  text: string; 
  icon?: LucideIcon; 
  tone?: "emerald" | "amber" | "indigo" | "zinc" 
}) {
  const [stepLabel, ...titleParts] = title.split(". ");
  const heading = titleParts.length > 0 ? titleParts.join(". ") : title;
  return (
    <div className={`manual-step manual-step-${tone}`}>
      <div className="manual-step-indicator">
        {Icon ? <Icon size={16} /> : <span>{stepLabel}</span>}
      </div>
      <div className="manual-step-content">
        <strong>{heading}</strong>
        <p>{text}</p>
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

function AutomationNumberField({
  label,
  value,
  onChange,
  step = "1",
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
}) {
  return (
    <label className="automation-number-field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
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

function AccountTab({
  account,
  onLogout,
}: {
  account: AuthenticatedAccount;
  onLogout: () => void;
}) {
  return (
    <div className="ac-tab-content">
      <SectionTitle title="Minha Conta" icon={Fingerprint} />
      
      <div className="auth-account-dock" style={{ 
        position: 'relative', 
        bottom: 'auto', 
        right: 'auto', 
        width: '100%', 
        maxWidth: '460px', 
        margin: '24px 0',
        padding: '32px'
      }}>
        <div className="auth-account-dock-eyebrow" style={{ fontSize: '0.8rem', letterSpacing: '0.15em' }}>CONTA ATIVA</div>
        <strong style={{ fontSize: '2rem', marginTop: '8px', display: 'block' }}>@{account?.username || 'usuario'}</strong>
        <span style={{ fontSize: '1.1rem', opacity: 0.7, display: 'block', marginTop: '4px' }}>{account?.email || 'email-nao-disponivel'}</span>
        
        <div style={{ marginTop: '32px' }}>
          <button 
            className="auth-dock-button" 
            type="button" 
            onClick={onLogout} 
            style={{ 
              width: 'auto', 
              padding: '14px 48px',
              fontSize: '1rem',
              fontWeight: '500'
            }}
          >
            Sair desta conta
          </button>
        </div>
      </div>

      <div className="ac-manual-grid" style={{ marginTop: '32px' }}>
        <div className="ac-manual-card" style={{ padding: '24px' }}>
          <SectionTitle title="Segurança e Isolamento" icon={LockKeyhole} />
          <p style={{ color: 'var(--muted)', fontSize: '0.95rem', lineHeight: '1.7', marginTop: '12px' }}>
            Seu AuraCore utiliza uma arquitetura de <strong>workspace isolado</strong>. 
            Isso significa que todas as suas mensagens do WhatsApp, aprendizados de memória, 
            estatísticas e projetos estão salvos em um banco de dados SQLite local, 
            vinculado exclusivamente à sua conta Firebase <strong>@{account?.username || 'usuario'}</strong>.
          </p>
          <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
            <div className="auth-feature-pill" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
              <BadgeCheck size={14} />
              <span>Banco de dados exclusivo</span>
            </div>
            <div className="auth-feature-pill" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
              <ShieldCheck size={14} />
              <span>Sessão criptografada</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
