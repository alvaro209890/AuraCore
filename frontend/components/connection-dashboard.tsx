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

// --- Novas Abas Componentizadas (Shadcn-like) ---
import OverviewTab from './dashboard/tabs/OverviewTab';
import ObserverTab from './dashboard/tabs/ObserverTab';
import AgentTab from './dashboard/tabs/AgentTab';
import GroupsTab from './dashboard/tabs/GroupsTab';
import MemoryTab from './dashboard/tabs/MemoryTab';
import RelationsTab from './dashboard/tabs/RelationsTab';
import AgendaTab from './dashboard/tabs/AgendaTab';
import ProjectsTab from './dashboard/tabs/ProjectsTab';
import ActivityTab from './dashboard/tabs/ActivityTab';
import AutomationTab from './dashboard/tabs/AutomationTab';
import ProactivityTab from './dashboard/tabs/ProactivityTab';
import ManualTab from './dashboard/tabs/ManualTab';
import AccountTab from './dashboard/tabs/AccountTab';

import {
  connectAgent,
  connectObserver,
  clearSavedDatabase,
  assistMemoryProjectEdit,
  completeProactiveCandidate,
  confirmProactiveCandidate,
  createAgendaEvent,
  createMemoryProject,
  deleteAgendaEvent,
  dismissProactiveCandidate,
  executeMemoryAnalysis,
  getProactiveSettings,
  listProactiveCandidates,
  listProactiveDeliveries,
  updateMemoryRelation,
  RefineMemoryResponse,
  deleteMemoryProject,
  getAgentStatus,
  getAgentWorkspace,
  getAutomationStatus,
  getCurrentMemory,
  getMemoryActivity,
  getMemoryGroups,
  getMemoryLiveSummary,
  getMemoryProjects,
  getMemoryRelations,
  getMemoryStatus,
  getMemorySnapshots,
  getObserverStatus,
  refreshObserverMessages,
  resetAgent,
  resetObserver,
  runProactiveTick,
  getAgendaEvents,
  updateAgentSettings,
  updateAgendaEvent,
  updateAutomationSettings,
  updateMemoryGroupSelection,
  updateMemoryProject,
  updateMemoryProjectCompletion,
  updateProactiveSettings,
  runAutomationTick,
  type AuthenticatedAccount,
  type AnalysisJob,
  type AutomationStatus,
  type AutomationDecision,
  type CreateAgendaEventInput,
  type CreateProjectMemoryInput,
  type MemoryActivity,
  type MemoryCurrent,
  type MemoryLiveSummary,
  type MemoryStatus,
  type MemorySnapshot,
  type ModelRun,
  type ObserverStatus,
  type AgendaEvent,
  type ProactiveCandidate,
  type ProactiveDeliveryLog,
  type ProactivePreferences,
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
export type AgentIntent = "first_analysis" | "improve_memory";
type TabId =
  | "overview"
  | "observer"
  | "agent"
  | "groups"
  | "memory"
  | "relations"
  | "agenda"
  | "projects"
  | "activity"
  | "automation"
  | "proactivity"
  | "manual"
  | "account";
type LogTone = "info" | "success" | "error";

export type AgentStep = {
  threshold: number;
  label: string;
  detail: string;
};

export type AgentLog = {
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

export type DisplayAgentState = AgentState & {
  stageIndex: number | null;
  badgeTone: "teal" | "emerald" | "amber" | "zinc";
};

export type AutomationDraft = Record<string, never> | null;
export type ProactivityDraft = Partial<ProactivePreferences> | null;

export type InsightMetric = {
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

type HeavyLiveResourceKey = "groups" | "projects" | "snapshots" | "relations";

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
  relations: 20000,
  agenda: 20000,
  projects: 20000,
  activity: 12000,
  automation: 12000,
  proactivity: 12000,
  manual: 20000,
  account: 20000,
};
const HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS: Record<HeavyLiveResourceKey, number> = {
  groups: 18000,
  projects: 22000,
  snapshots: 22000,
  relations: 22000,
};
const BUSY_HEAVY_RESOURCE_REFRESH_MIN_INTERVAL_MS: Record<HeavyLiveResourceKey, number> = {
  groups: 12000,
  projects: 12000,
  snapshots: 12000,
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
      { id: "relations", label: "Relações", icon: User },
    ],
  },
  {
    title: "Operações",
    items: [
      { id: "agenda", label: "Agenda", icon: Clock },
      { id: "projects", label: "Projetos", icon: FolderGit2 },
      { id: "automation", label: "Automação", icon: Zap },
      { id: "proactivity", label: "Proatividade", icon: Sparkles },
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

export function formatState(state: string): string {
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

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Ainda indisponível";
  }

  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: BRAZIL_TIMEZONE,
  });
}

export function formatShortDateTime(value: string | null | undefined): string {
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

export function formatBrazilDateTimeInput(value: string | null | undefined): string {
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

export function parseBrazilDateTimeInput(value: string): Date {
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

export function formatAgendaReminderRule(event: AgendaEvent): string {
  if (!event.reminder_eligible) {
    return event.reminder_block_reason ?? "Sem lembrete automático";
  }
  return `${formatReminderOffsetLabel(event.reminder_offset_minutes)} em horário de Brasília.`;
}

export function formatRelativeTime(value: string | null | undefined): string {
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

export function formatConfidence(value: number | null | undefined): string {
  const normalized = Math.max(0, Math.min(1, value ?? 0));
  return `${Math.round(normalized * 100)}%`;
}

export function getProactiveCategoryLabel(category: ProactiveCandidate["category"] | ProactiveDeliveryLog["category"]): string {
  switch (category) {
    case "agenda_followup":
      return "Agenda";
    case "followup":
      return "Follow-up";
    case "project_nudge":
      return "Projeto";
    case "routine":
      return "Rotina";
    case "morning_digest":
      return "Digest manhã";
    case "night_digest":
      return "Digest noite";
    default:
      return category;
  }
}

export function getProactiveStatusLabel(status: ProactiveCandidate["status"]): string {
  switch (status) {
    case "queued":
      return "Na fila";
    case "suggested":
      return "Sugerido";
    case "sent":
      return "Enviado";
    case "dismissed":
      return "Dispensado";
    case "confirmed":
      return "Confirmado";
    case "done":
      return "Concluído";
    case "expired":
      return "Expirado";
    default:
      return status;
  }
}

export function getProactiveDecisionLabel(decision: ProactiveDeliveryLog["decision"]): string {
  switch (decision) {
    case "sent":
      return "Enviado";
    case "skipped":
      return "Ignorado";
    case "suppressed":
      return "Suprimido";
    case "failed":
      return "Falhou";
    default:
      return decision;
  }
}

export function truncateText(value: string | null | undefined, maxLength: number): string {
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

export function formatTokenCount(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function hasEstablishedMemory(memory: MemoryCurrent | null, latestSnapshot: MemorySnapshot | null): boolean {
  return Boolean(memory?.last_analyzed_at || latestSnapshot?.id);
}

export function getIntentTitle(intent: AgentIntent | null): string {
  switch (intent) {
    case "first_analysis":
      return "Fazer Primeira Análise";
    case "improve_memory":
      return "Atualizar Memória";
    default:
      return "Aguardando nova ação";
  }
}

export function buildActivityThinking(args: {
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
      `Hoje a base consolidada cruza ${snapshotsCount} snapshots, ${projectsCount} projetos e o historico do WhatsApp para manter continuidade entre leituras.`,
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

export function getActivityToneLabel(tone: ActivityTraceItem["tone"]): string {
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

export function resolvePendingAnalysisJob(args: {
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

export function getStepVisualState(agentState: DisplayAgentState, stepIndex: number, stepsLength: number): {
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

export function buildActivityTrace(args: {
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
        ? "O processamento principal terminou e devolveu atualizacoes para memoria e projetos."
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

export function getSnapshotCoverageTone(snapshot: MemorySnapshot | null): "emerald" | "amber" | "indigo" | "zinc" {
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

export function getSnapshotCoverageLabel(snapshot: MemorySnapshot | null): string {
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

export function formatSnapshotDirectionMix(snapshot: MemorySnapshot | null): string {
  if (!snapshot) {
    return "0 enviadas / 0 recebidas";
  }
  return `${formatTokenCount(snapshot.outbound_message_count)} enviadas / ${formatTokenCount(snapshot.inbound_message_count)} recebidas`;
}

export function resolveOverviewNextAction(args: {
  status: ObserverStatus | null;
  memoryStatus: MemoryStatus | null;
  latestSnapshot: MemorySnapshot | null;
}): {
  title: string;
  detail: string;
  buttonLabel: string;
  target: "observer" | "memory" | "manual" | "activity";
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
      title: "Explorar a memoria consolidada",
      detail: "Nao ha lote pendente agora. O melhor proximo passo e revisar a memoria no Manual ou acompanhar a atividade ate o proximo sync.",
      buttonLabel: "Abrir Manual",
      target: "manual",
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

export function getProjectStrength(project: ProjectMemory): number {
  const raw = 30 + (project.next_steps.length * 10) + (project.evidence.length * 7) + (project.status ? 8 : 0);
  return Math.max(24, Math.min(100, raw));
}

export function isProjectManuallyCompleted(project: ProjectMemory): boolean {
  return project.completion_source === "manual" && Boolean(project.manual_completed_at);
}

export function getProjectStatusLabel(project: ProjectMemory): string {
  if (isProjectManuallyCompleted(project)) {
    return "Concluido manualmente";
  }
  return project.status || "Em progresso";
}

export function getProjectStatusTone(project: ProjectMemory): "emerald" | "amber" | "indigo" | "zinc" {
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

export function normalizeProjectSearchText(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function getAudienceLabel(project: ProjectMemory): string {
  if (project.built_for.trim()) {
    return project.built_for;
  }
  return "Público ainda não consolidado";
}

export function normalizeRelationType(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().toLowerCase();
  if (!normalized) {
    return "unknown";
  }
  if (["partner", "family", "friend", "work", "client", "service", "acquaintance", "other", "unknown"].includes(normalized)) {
    return normalized;
  }
  return "unknown";
}

export function getRelationTypeLabel(value: string | null | undefined): string {
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

export function getRelationTone(value: string | null | undefined): "rose" | "emerald" | "amber" | "indigo" | "zinc" {
  const type = normalizeRelationType(value);
  if (type === "partner") return "rose";
  if (type === "family") return "emerald";
  if (type === "friend") return "indigo";
  if (type === "work" || type === "client") return "amber";
  return "zinc";
}

export function getRelationStrength(relation: PersonRelation): number {
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

export function getRelationSortPriority(value: string | null | undefined): number {
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

export function SectionTitle({
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

export function ProgressBar({
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

export function SegmentedControl({
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
// Scores projects, snapshots and memory by relevance to the
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

  // 1) Score projects
  const scoredProjects = allProjects.map((p) => ({
    item: p,
    score: scoreByKeywords(
      `${p.project_name} ${p.summary} ${p.status} ${p.what_is_being_built} ${p.built_for} ${p.next_steps.join(" ")}`,
      keywords,
    ),
  }));
  scoredProjects.sort((a, b) => b.score - a.score);
  const relevantProjects = scoredProjects.filter((s) => s.score > 0).slice(0, 3);

  // 2) Score snapshot learnings, relationships, routines
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

  // 3) Check if life summary is relevant
  const memoryScore = currentMemory?.life_summary
    ? scoreByKeywords(currentMemory.life_summary, keywords)
    : 0;

  // Assemble — most relevant first
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
  const [memoryActivity, setMemoryActivity] = useState<MemoryActivity | null>(null);
  const [queuedJobId, setQueuedJobId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [agentConnectionError, setAgentConnectionError] = useState<string | null>(null);
  const [agentMessagesError, setAgentMessagesError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [memoryGroupsError, setMemoryGroupsError] = useState<string | null>(null);
  const [relationsError, setRelationsError] = useState<string | null>(null);
  const [agendaError, setAgendaError] = useState<string | null>(null);
  const [agendaActionError, setAgendaActionError] = useState<string | null>(null);
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
  const [isClearingDatabase, setIsClearingDatabase] = useState(false);
  const [savingGroupJids, setSavingGroupJids] = useState<string[]>([]);
  const [savingProjectKeys, setSavingProjectKeys] = useState<string[]>([]);
  const [deletingProjectKeys, setDeletingProjectKeys] = useState<string[]>([]);
  const [editingProjectKeys, setEditingProjectKeys] = useState<string[]>([]);
  const [aiProjectKeys, setAiProjectKeys] = useState<string[]>([]);
  const [savingAgendaIds, setSavingAgendaIds] = useState<string[]>([]);
  const [deletingAgendaIds, setDeletingAgendaIds] = useState<string[]>([]);
  const [isCreatingAgendaEvent, setIsCreatingAgendaEvent] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
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
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
  const [automationDraft, setAutomationDraft] = useState<AutomationDraft>(null);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [isTickingAutomation, setIsTickingAutomation] = useState(false);
  const [proactiveSettings, setProactiveSettings] = useState<ProactivePreferences | null>(null);
  const [proactiveCandidates, setProactiveCandidates] = useState<ProactiveCandidate[]>([]);
  const [proactiveDeliveries, setProactiveDeliveries] = useState<ProactiveDeliveryLog[]>([]);
  const [proactiveError, setProactiveError] = useState<string | null>(null);
  const [proactivityDraft, setProactivityDraft] = useState<ProactivityDraft>(null);
  const [isSavingProactivity, setIsSavingProactivity] = useState(false);
  const [isTickingProactivity, setIsTickingProactivity] = useState(false);

  const liveRefreshIntervalMs = useMemo(() => getLiveRefreshInterval(activeTab), [activeTab]);
  const lastQrRefreshAtRef = useRef<number | null>(null);
  const lastAgentQrRefreshAtRef = useRef<number | null>(null);
  const lastAttentionRefreshAtRef = useRef<number | null>(null);
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
    const [memoryResult, projectsResult, relationsResult, memoryStatusResult, snapshotsResult, memoryActivityResult, groupsResult] =
      await Promise.allSettled([
        getCurrentMemory(),
        getMemoryProjects(),
        getMemoryRelations(),
        getMemoryStatus(),
        getMemorySnapshots(6),
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
      const shouldRefreshProjects = previousSummary.projects_signature !== nextSummary.projects_signature;
      const shouldRefreshRelations = previousSummary.relations_signature !== nextSummary.relations_signature;

      if (!shouldRefreshMemoryCore && !shouldRefreshActivity && !shouldRefreshProjects && !shouldRefreshRelations) {
        return;
      }

      const [memoryResult, memoryStatusResult, snapshotsResult, memoryActivityResult, projectsResult, relationsResult] =
        await Promise.allSettled([
          shouldRefreshMemoryCore ? getCurrentMemory() : Promise.resolve(null),
          shouldRefreshMemoryCore ? getMemoryStatus() : Promise.resolve(null),
          shouldRefreshMemoryCore ? getMemorySnapshots(6) : Promise.resolve(null),
          shouldRefreshActivity ? getMemoryActivity() : Promise.resolve(null),
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

  async function createManualAgendaEvent(input: CreateAgendaEventInput): Promise<AgendaEvent> {
    setIsCreatingAgendaEvent(true);
    setAgendaActionError(null);
    try {
      const created = await createAgendaEvent(input);
      startTransition(() => {
        setAgendaEvents((current) =>
          [...current, created].sort((left, right) => new Date(left.inicio).getTime() - new Date(right.inicio).getTime()),
        );
      });
      pushAgentLog("success", `Compromisso ${created.titulo} criado manualmente na agenda.`);
      return created;
    } catch (error) {
      const message = getErrorMessage(error);
      setAgendaActionError(message);
      pushAgentLog("error", `Falha ao criar compromisso manual: ${message}`);
      throw error;
    } finally {
      setIsCreatingAgendaEvent(false);
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

  async function createManualProject(input: CreateProjectMemoryInput): Promise<ProjectMemory> {
    setIsCreatingProject(true);
    setProjectActionError(null);
    try {
      const created = await createMemoryProject(input);
      startTransition(() => {
        setProjects((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      });
      markHeavyResourceRefreshed("projects");
      pushAgentLog("success", `Projeto ${created.project_name} criado manualmente.`);
      return created;
    } catch (error) {
      const message = getErrorMessage(error);
      setProjectActionError(message);
      pushAgentLog("error", `Falha ao criar projeto manual: ${message}`);
      throw error;
    } finally {
      setIsCreatingProject(false);
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
    const shouldRefreshAutomation = !isTickingAutomation && (
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "memory" ||
      resolvedActiveTab === "automation" ||
      queuedJobId !== null
    );
    const shouldRefreshProactivity = !isTickingProactivity && (
      resolvedActiveTab === "manual" ||
      resolvedActiveTab === "proactivity"
    );
    const shouldRefreshHeavyGroups = shouldRefreshHeavyResource("groups", analysisIsBusy);
    const shouldRefreshMemoryGroups = (resolvedActiveTab === "manual" || resolvedActiveTab === "groups") && shouldRefreshHeavyGroups;

    dashboardRefreshInFlightRef.current = true;
    try {
      const [
        agentWorkspaceResult,
        memoryResult,
        memoryGroupsResult,
        agendaResult,
        projectsResult,
        relationsResult,
        memoryStatusResult,
        snapshotsResult,
        automationResult,
        proactiveSettingsResult,
        proactiveCandidatesResult,
        proactiveDeliveriesResult,
      ] = await Promise.allSettled([
        shouldRefreshAgentWorkspace ? getAgentWorkspace(activeAgentThreadId ?? undefined) : Promise.resolve(null),
        shouldRefreshMemoryCurrent ? getCurrentMemory() : Promise.resolve(null),
        shouldRefreshMemoryGroups ? getMemoryGroups() : Promise.resolve(null),
        shouldRefreshAgenda ? getAgendaEvents(120, false) : Promise.resolve(null),
        shouldRefreshProjects ? getMemoryProjects() : Promise.resolve(null),
        shouldRefreshRelations ? getMemoryRelations() : Promise.resolve(null),
        shouldRefreshMemoryStatus ? getMemoryStatus() : Promise.resolve(null),
        shouldRefreshSnapshots ? getMemorySnapshots(resolvedActiveTab === "overview" ? 1 : 6) : Promise.resolve(null),
        shouldRefreshAutomation ? getAutomationStatus() : Promise.resolve(null),
        shouldRefreshProactivity ? getProactiveSettings() : Promise.resolve(null),
        shouldRefreshProactivity
          ? listProactiveCandidates(20, ["suggested", "sent", "confirmed"])
          : Promise.resolve(null),
        shouldRefreshProactivity ? listProactiveDeliveries(12) : Promise.resolve(null),
      ]);

      if (agentWorkspaceResult.status === "fulfilled" && agentWorkspaceResult.value) {
        const nextAgentWorkspace = agentWorkspaceResult.value;
        startTransition(() => {
          applyAgentWorkspace(nextAgentWorkspace);
        });
      } else if (agentWorkspaceResult.status === "rejected" && shouldRefreshAgentWorkspace) {
        setAgentConnectionError(getErrorMessage(agentWorkspaceResult.reason));
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

      if (proactiveSettingsResult.status === "fulfilled" && proactiveSettingsResult.value) {
        startTransition(() => {
          setProactiveSettings(proactiveSettingsResult.value);
          setProactiveError(null);
        });
      } else if (proactiveSettingsResult.status === "rejected" && shouldRefreshProactivity) {
        setProactiveError(getErrorMessage(proactiveSettingsResult.reason));
      }

      if (proactiveCandidatesResult.status === "fulfilled" && Array.isArray(proactiveCandidatesResult.value)) {
        const nextCandidates = proactiveCandidatesResult.value as ProactiveCandidate[];
        startTransition(() => {
          setProactiveCandidates(nextCandidates);
          setProactiveError(null);
        });
      } else if (proactiveCandidatesResult.status === "rejected" && shouldRefreshProactivity) {
        setProactiveError(getErrorMessage(proactiveCandidatesResult.reason));
      }

      if (proactiveDeliveriesResult.status === "fulfilled" && Array.isArray(proactiveDeliveriesResult.value)) {
        const nextDeliveries = proactiveDeliveriesResult.value as ProactiveDeliveryLog[];
        startTransition(() => {
          setProactiveDeliveries(nextDeliveries);
          setProactiveError(null);
        });
      } else if (proactiveDeliveriesResult.status === "rejected" && shouldRefreshProactivity) {
        setProactiveError(getErrorMessage(proactiveDeliveriesResult.reason));
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
  }, [activeAgentThreadId, activeTab, isHydrating]);

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

    const pendingJob = resolvePendingAnalysisJob({
      currentJob: memoryStatus?.current_job ?? null,
      activity: memoryActivity,
      queuedJobId,
    });
    const observedJob = pendingJob ?? memoryActivity.jobs[0] ?? null;
    if (observedJob) {
      const signature = `${observedJob.id}:${observedJob.status}`;
      if (signature !== lastObservedJobRef.current) {
        lastObservedJobRef.current = signature;
        pushAgentLog(
          observedJob.status === "failed" ? "error" : observedJob.status === "succeeded" ? "success" : "info",
          observedJob.status === "failed"
            ? `${getIntentTitle(observedJob.intent as AgentIntent)} falhou. ${observedJob.error_text || "Sem detalhe persistido."}`
            : observedJob.status === "succeeded"
              ? `${getIntentTitle(observedJob.intent as AgentIntent)} terminou com ${observedJob.selected_message_count} mensagens processadas.`
              : `${getIntentTitle(observedJob.intent as AgentIntent)} está ${observedJob.status} no backend.`,
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
  }, [memoryActivity, memoryStatus?.current_job, queuedJobId]);

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
    const shouldLoadGroups = activeTab === "groups" || activeTab === "manual";
    const shouldLoadRelations = activeTab === "relations" || activeTab === "manual";
    const shouldLoadAgenda = activeTab === "agenda";
    const shouldLoadSnapshots = activeTab === "overview" || activeTab === "memory" || activeTab === "manual";
    const shouldLoadAutomation = resolvedActiveTab === "memory" || resolvedActiveTab === "automation" || resolvedActiveTab === "manual" || queuedJobId !== null;
    const shouldLoadProactivity = resolvedActiveTab === "proactivity" || resolvedActiveTab === "manual";

    const [
      statusResult,
      agentStatusResult,
      agentWorkspaceResult,
      memoryResult,
      groupsResult,
      agendaResult,
      projectsResult,
      relationsResult,
      memoryStatusResult,
      snapshotsResult,
      automationResult,
      proactiveSettingsResult,
      proactiveCandidatesResult,
      proactiveDeliveriesResult,
    ] = await Promise.allSettled([
      getObserverStatus(false),
      Promise.resolve(null),
      shouldLoadAgentWorkspace ? getAgentWorkspace(activeAgentThreadId ?? undefined) : Promise.resolve(null),
      getCurrentMemory(),
      shouldLoadGroups ? getMemoryGroups() : Promise.resolve([]),
      shouldLoadAgenda ? getAgendaEvents(120, false) : Promise.resolve([]),
      getMemoryProjects(),
      shouldLoadRelations ? getMemoryRelations() : Promise.resolve(null),
      getMemoryStatus(),
      shouldLoadSnapshots ? getMemorySnapshots(activeTab === "overview" ? 1 : 6) : Promise.resolve([]),
      shouldLoadAutomation ? getAutomationStatus() : Promise.resolve(null),
      shouldLoadProactivity ? getProactiveSettings() : Promise.resolve(null),
      shouldLoadProactivity
        ? listProactiveCandidates(20, ["suggested", "sent", "confirmed"])
        : Promise.resolve([]),
      shouldLoadProactivity ? listProactiveDeliveries(12) : Promise.resolve([]),
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

    if (memoryResult.status === "fulfilled") {
      setMemory(memoryResult.value);
      setMemoryError(null);
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

    if (automationResult.status === "fulfilled" && automationResult.value) {
      const snap = automationResult.value;
      setAutomationStatus(snap);
      setAutomationError(null);
      syncQueuedJobFromAutomationSnapshot(snap);
    } else if (automationResult.status === "rejected") {
      setAutomationError(getErrorMessage(automationResult.reason));
    }

    if (proactiveSettingsResult.status === "fulfilled" && proactiveSettingsResult.value) {
      setProactiveSettings(proactiveSettingsResult.value);
      setProactiveError(null);
    } else if (proactiveSettingsResult.status === "rejected" && shouldLoadProactivity) {
      setProactiveError(getErrorMessage(proactiveSettingsResult.reason));
    }

    if (proactiveCandidatesResult.status === "fulfilled" && Array.isArray(proactiveCandidatesResult.value)) {
      const nextCandidates = proactiveCandidatesResult.value as ProactiveCandidate[];
      setProactiveCandidates(nextCandidates);
      if (shouldLoadProactivity) {
        setProactiveError(null);
      }
    } else if (proactiveCandidatesResult.status === "rejected" && shouldLoadProactivity) {
      setProactiveError(getErrorMessage(proactiveCandidatesResult.reason));
    }

    if (proactiveDeliveriesResult.status === "fulfilled" && Array.isArray(proactiveDeliveriesResult.value)) {
      const nextDeliveries = proactiveDeliveriesResult.value as ProactiveDeliveryLog[];
      setProactiveDeliveries(nextDeliveries);
      if (shouldLoadProactivity) {
        setProactiveError(null);
      }
    } else if (proactiveDeliveriesResult.status === "rejected" && shouldLoadProactivity) {
      setProactiveError(getErrorMessage(proactiveDeliveriesResult.reason));
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
      setAutomationDraft(null);
      pushAgentLog("success", "Configuração da automação salva no backend.");
    } catch (error) {
      const message = getErrorMessage(error);
      setAutomationError(message);
      pushAgentLog("error", `Falha ao salvar automação: ${message}`);
    } finally {
      setIsSavingAutomation(false);
    }
  }

  async function refreshProactivitySnapshot(): Promise<void> {
    const [settings, candidates, deliveries] = await Promise.all([
      getProactiveSettings(),
      listProactiveCandidates(20, ["suggested", "sent", "confirmed"]),
      listProactiveDeliveries(12),
    ]);
    setProactiveSettings(settings);
    setProactiveCandidates(candidates);
    setProactiveDeliveries(deliveries);
  }

  async function saveProactivityConfig(): Promise<void> {
    if (!proactivityDraft) {
      return;
    }

    setIsSavingProactivity(true);
    setProactiveError(null);
    try {
      const nextSettings = await updateProactiveSettings(proactivityDraft);
      setProactiveSettings(nextSettings);
      setProactivityDraft(null);
      pushAgentLog("success", "Configuração da proatividade salva no backend.");
      toast.success("Proatividade atualizada.");
    } catch (error) {
      const message = getErrorMessage(error);
      setProactiveError(message);
      pushAgentLog("error", `Falha ao salvar proatividade: ${message}`);
      toast.error(message);
    } finally {
      setIsSavingProactivity(false);
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

  async function triggerProactivityNow(): Promise<void> {
    setIsTickingProactivity(true);
    setProactiveError(null);
    try {
      await runProactiveTick();
      await refreshProactivitySnapshot();
      pushAgentLog("info", "Tick manual da proatividade executado. O backend reavaliou digests e nudges pendentes.");
      toast.success("Tick da proatividade executado.");
    } catch (error) {
      const message = getErrorMessage(error);
      setProactiveError(message);
      pushAgentLog("error", `Falha ao rodar o tick proativo: ${message}`);
      toast.error(message);
    } finally {
      setIsTickingProactivity(false);
    }
  }

  async function updateCandidateState(candidateId: string, action: "dismiss" | "confirm" | "complete"): Promise<void> {
    setProactiveError(null);
    try {
      if (action === "dismiss") {
        await dismissProactiveCandidate(candidateId);
      } else if (action === "confirm") {
        await confirmProactiveCandidate(candidateId);
      } else {
        await completeProactiveCandidate(candidateId);
      }
      await refreshProactivitySnapshot();
      toast.success(
        action === "dismiss"
          ? "Sugestão dispensada."
          : action === "confirm"
            ? "Sugestão confirmada."
            : "Sugestão concluída.",
      );
    } catch (error) {
      const message = getErrorMessage(error);
      setProactiveError(message);
      toast.error(message);
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
        : "Atualizacao incremental iniciada. O agente vai combinar mensagens novas com snapshots e projetos.",
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
      "Isso vai apagar TODOS os dados salvos no banco de dados local, incluindo memoria, mensagens, snapshots, sessoes e configuracoes persistidas. Deseja continuar?",
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
              <p>Buscando status do observador, perfil atual, relações, snapshots e projetos.</p>
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
                  onCreateEvent={createManualAgendaEvent}
                  onSaveEvent={saveAgendaEdits}
                  onDeleteEvent={removeAgendaEvent}
                  savingAgendaIds={savingAgendaIds}
                  deletingAgendaIds={deletingAgendaIds}
                  isCreatingEvent={isCreatingAgendaEvent}
                />
              ) : null}

              {resolvedActiveTab === "projects" ? (
                <ProjectsTab
                  projects={projects}
                  onCreateProject={createManualProject}
                  onToggleCompletion={toggleProjectCompletion}
                  onSaveProject={saveProjectEdits}
                  onAssistProject={assistProjectEdit}
                  onDeleteProject={removeProject}
                  savingProjectKeys={savingProjectKeys}
                  deletingProjectKeys={deletingProjectKeys}
                  editingProjectKeys={editingProjectKeys}
                  aiProjectKeys={aiProjectKeys}
                  actionError={projectActionError}
                  isCreatingProject={isCreatingProject}
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

              {resolvedActiveTab === "proactivity" ? (
                <ProactivityTab
                  proactiveSettings={proactiveSettings}
                  proactivityDraft={proactivityDraft}
                  proactiveCandidates={proactiveCandidates}
                  proactiveDeliveries={proactiveDeliveries}
                  proactiveError={proactiveError}
                  isSavingProactivity={isSavingProactivity}
                  isTickingProactivity={isTickingProactivity}
                  onDraftChange={setProactivityDraft}
                  onSave={() => void saveProactivityConfig()}
                  onTick={() => void triggerProactivityNow()}
                  onDismissCandidate={(candidateId) => void updateCandidateState(candidateId, "dismiss")}
                  onConfirmCandidate={(candidateId) => void updateCandidateState(candidateId, "confirm")}
                  onCompleteCandidate={(candidateId) => void updateCandidateState(candidateId, "complete")}
                />
              ) : null}

              {resolvedActiveTab === "manual" ? (
                <ManualTab
                  status={status}
                  memory={memory}
                  projects={projects}
                  snapshots={snapshots}
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


export function MemorySignalCard({ label, value, meta, tone }: { label: string; value: string; meta?: string; tone?: string }) {
  return (
    <div className={`p-4 rounded-xl border border-zinc-200 bg-white shadow-sm flex flex-col gap-1`}>
      <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className="text-xl font-semibold text-zinc-900">{value}</span>
      {meta && <span className="text-xs text-zinc-400">{meta}</span>}
    </div>
  );
}

export function ModernStatCard({ label, value, meta, tone, icon: Icon }: { label: string; value: string; meta?: string; tone?: string; icon?: any }) {
  return (
    <div className={`p-4 rounded-xl border border-zinc-200 bg-white shadow-sm flex flex-col gap-2 relative overflow-hidden`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-600">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-zinc-400" />}
      </div>
      <span className="text-2xl font-bold text-zinc-900">{value}</span>
      {meta && <span className="text-xs text-zinc-500">{meta}</span>}
    </div>
  );
}

export function ProjectInfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 mb-3">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="text-sm text-zinc-800">{value}</span>
    </div>
  );
}

export function AutomationNumberField({ label, description, value, onChange }: { label: string; description: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex flex-col gap-1 mb-4">
      <label className="text-sm font-medium text-zinc-700">{label}</label>
      <input type="number" value={value} onChange={e => onChange(Number(e.target.value))} className="border border-zinc-300 rounded-md p-2 text-sm w-full max-w-[200px]" />
      <span className="text-xs text-zinc-500">{description}</span>
    </div>
  );
}


export function StatusLine({ label, value, tone }: any) {
  return <div className="flex justify-between items-center text-sm py-2 border-b border-zinc-100 last:border-0"><span className="text-zinc-500">{label}</span><span className={`font-medium`}>{value}</span></div>;
}
export function InlineError({ title, message }: any) {
  return <div className="bg-red-50 text-red-600 p-4 rounded-lg text-sm border border-red-200 mt-4 flex flex-col gap-1"><strong>{title}</strong><p>{message}</p></div>;
}
export function SignalBlock({ label, value, tone, meta }: any) {
  return <div className="flex flex-col gap-1 p-4 bg-white border border-zinc-200 rounded-xl shadow-sm"><span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</span><span className={`text-xl font-bold`}>{value}</span>{meta && <span className="text-xs text-zinc-400 mt-1">{meta}</span>}</div>;
}
export function ManualInfoCard({ title, text, icon: Icon, tone }: any) {
  return <div className="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm flex flex-col gap-3">{Icon && <Icon className={`w-5 h-5 text-zinc-400`} />}<h3 className="font-semibold text-zinc-900">{title}</h3><p className="text-sm text-zinc-600 leading-relaxed">{text}</p></div>;
}
export function ManualStep({ title, text, icon: Icon, tone }: any) {
  return <div className="p-4 bg-white border border-zinc-200 rounded-xl shadow-sm flex gap-4"><div className={`p-2 bg-zinc-50 border border-zinc-100 rounded-lg h-fit`}>{Icon && <Icon className={`w-5 h-5 text-zinc-500`} />}</div><div className="flex flex-col gap-1"><h3 className="font-semibold text-zinc-900">{title}</h3><p className="text-sm text-zinc-600 leading-relaxed">{text}</p></div></div>;
}

export type { MemoryActivity };
