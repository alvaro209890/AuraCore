"use client";

import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertCircle,
  Archive,
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
  Play,
  Plus,
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
  createChatThread,
  getAutomationStatus,
  connectAgent,
  connectObserver,
  getAgentStatus,
  getAgentWorkspace,
  getChatWorkspace,
  getCurrentMemory,
  getMemoryProjects,
  getImportantMessages,
  getMemoryStatus,
  getMemorySnapshots,
  getObserverStatus,
  refreshObserverMessages,
  refineMemory,
  resetAgent,
  resetObserver,
  runFirstMemoryAnalysis,
  runNextMemoryBatch,
  runAutomationTick,
  sendChatMessageStream,
  updateAgentSettings,
  updateAutomationSettings,
  type AutomationSettings,
  type AutomationStatus,
  type AutomationDecision,
  type AnalysisJob,
  type ChatMessage,
  type ChatThread,
  type ChatWorkspace,
  type ImportantMessage,
  type MemoryAnalysisDetailMode,
  type MemoryCurrent,
  type MemoryStatus,
  type MemorySnapshot,
  type ModelRun,
  type ObserverStatus,
  type WhatsAppAgentMessage,
  type WhatsAppAgentContactMemory,
  type WhatsAppAgentSession,
  type WhatsAppAgentSettings,
  type WhatsAppAgentStatus,
  type WhatsAppAgentThread,
  type WhatsAppAgentWorkspace,
  type ProjectMemory,
  type WhatsAppSyncRun,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";
type AgentMode = "idle" | "analyze" | "refine";
type AgentIntent = "first_analysis" | "improve_memory" | "refine_saved";
type TabId =
  | "overview"
  | "observer"
  | "agent"
  | "memory"
  | "important"
  | "projects"
  | "chat"
  | "activity"
  | "automation"
  | "manual";
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

type AutomationDraft = {
  auto_sync_enabled: boolean;
  auto_analyze_enabled: boolean;
  auto_refine_enabled: boolean;
  min_new_messages_threshold: number;
  stale_hours_threshold: number;
  pruned_messages_threshold: number;
  default_detail_mode: MemoryAnalysisDetailMode;
  default_target_message_count: number;
  default_lookback_hours: number;
  daily_budget_usd: number;
  max_auto_jobs_per_day: number;
};

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

const CONNECTING_STATUS_POLL_INTERVAL_MS = 700;
const LIVE_STATUS_POLL_INTERVAL_MS = 1200;
const QR_REFRESH_INTERVAL_MS = 25000;
const ATTENTION_REFRESH_THROTTLE_MS = 800;
const LIVE_REFRESH_INTERVALS: Record<TabId, number> = {
  overview: 1800,
  observer: 1600,
  agent: 1400,
  memory: 2200,
  important: 2400,
  projects: 2400,
  chat: 1600,
  activity: 2200,
  automation: 2200,
  manual: 2200,
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
      { id: "agent", label: "WhatsApp Agente", icon: Bot },
      { id: "memory", label: "Memória", icon: Database },
      { id: "important", label: "Importantes", icon: Archive },
    ],
  },
  {
    title: "Operações",
    items: [
      { id: "projects", label: "Projetos", icon: FolderGit2 },
      { id: "chat", label: "Chat Pessoal", icon: MessageSquare },
    ],
  },
  {
    title: "Sistema",
    items: [
      { id: "activity", label: "Atividade", icon: Activity },
      { id: "automation", label: "Automação", icon: Settings },
      { id: "manual", label: "Manual", icon: FileText },
    ],
  },
];

const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

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
    label: "Consolidando memoria",
    detail: "Transformando sinais dispersos em um perfil mais util e mais fiel ao dono.",
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
      return "Atualizar Sistema com Novas Mensagens";
    case "refine_saved":
      return "Refinar Memória Já Salva";
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
      "Esta rota compara mensagens diretas recentes com a memoria ja consolidada para reforcar o que mudou sem perder continuidade do perfil.",
    );
  } else {
    lines.push(
      "Esta rota nao reler o WhatsApp; ela limpa e reorganiza somente o que ja esta salvo no Supabase para reduzir ruido.",
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

function toAutomationDraft(settings: AutomationSettings): AutomationDraft {
  return {
    auto_sync_enabled: settings.auto_sync_enabled,
    auto_analyze_enabled: settings.auto_analyze_enabled,
    auto_refine_enabled: settings.auto_refine_enabled,
    min_new_messages_threshold: settings.min_new_messages_threshold,
    stale_hours_threshold: settings.stale_hours_threshold,
    pruned_messages_threshold: settings.pruned_messages_threshold,
    default_detail_mode: settings.default_detail_mode,
    default_target_message_count: settings.default_target_message_count,
    default_lookback_hours: settings.default_lookback_hours,
    daily_budget_usd: settings.daily_budget_usd,
    max_auto_jobs_per_day: settings.max_auto_jobs_per_day,
  };
}

function buildPersistedActivityLogs(status: AutomationStatus | null): AgentLog[] {
  if (!status) {
    return [];
  }

  const syncLogs = status.sync_runs.slice(0, 3).map((syncRun) => ({
    id: `sync-${syncRun.id}`,
    tone: (syncRun.status === "failed" ? "error" : "info") as LogTone,
    createdAt: syncRun.finished_at ?? syncRun.last_activity_at ?? syncRun.started_at,
    message: `Sync ${syncRun.status}: ${syncRun.messages_saved_count} salvas, ${syncRun.messages_ignored_count} ignoradas e ${syncRun.messages_pruned_count} podadas.`,
  }));
  const decisionLogs = status.decisions.slice(0, 3).map((decision) => ({
    id: `decision-${decision.id}`,
    tone: (decision.action === "queue" ? "success" : "info") as LogTone,
    createdAt: decision.created_at,
    message: `Decisao ${decision.action}: ${decision.intent} com score ${decision.score}/100. ${decision.explanation}`,
  }));
  const jobLogs = status.jobs.slice(0, 4).map((job) => ({
    id: `job-${job.id}`,
    tone: (job.status === "failed" ? "error" : job.status === "succeeded" ? "success" : "info") as LogTone,
    createdAt: job.finished_at ?? job.started_at ?? job.created_at,
    message: `Job ${job.status}: ${getIntentTitle(job.intent as AgentIntent)} em ${job.detail_mode}, alvo ${job.target_message_count} msgs.`,
  }));

  return [...syncLogs, ...decisionLogs, ...jobLogs].sort((left, right) => (
    new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
  ));
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
      detail: `${latestSyncRun.messages_saved_count} mensagens diretas salvas, ${latestSyncRun.messages_ignored_count} ignoradas e ${latestSyncRun.messages_pruned_count} podadas na janela mais recente.`,
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

export function ConnectionDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
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
  const [projects, setProjects] = useState<ProjectMemory[]>([]);
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [importantMessages, setImportantMessages] = useState<ImportantMessage[]>([]);
  const [chatThreads, setChatThreads] = useState<ChatThread[]>([]);
  const [activeChatThreadId, setActiveChatThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatThreadTitle, setChatThreadTitle] = useState("Conversa principal");
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [automationDraft, setAutomationDraft] = useState<AutomationDraft | null>(null);
  const [chatDraft, setChatDraft] = useState("");
  const [queuedJobId, setQueuedJobId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [agentConnectionError, setAgentConnectionError] = useState<string | null>(null);
  const [agentMessagesError, setAgentMessagesError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [importantMessagesError, setImportantMessagesError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [messageRefreshError, setMessageRefreshError] = useState<string | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
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
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [isTickingAutomation, setIsTickingAutomation] = useState(false);
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

  const liveRefreshIntervalMs = useMemo(() => getLiveRefreshInterval(activeTab), [activeTab]);
  const lastQrRefreshAtRef = useRef<number | null>(null);
  const lastAgentQrRefreshAtRef = useRef<number | null>(null);
  const lastAttentionRefreshAtRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const agentTimerRef = useRef<number | null>(null);
  const agentStepIndexRef = useRef(0);
  const observerStatusInFlightRef = useRef(false);
  const agentStatusInFlightRef = useRef(false);
  const dashboardRefreshInFlightRef = useRef(false);
  const pollStatusRef = useRef<((announceTransition?: boolean) => Promise<void>) | null>(null);
  const pollAgentStatusRef = useRef<((announceTransition?: boolean) => Promise<void>) | null>(null);
  const refreshLiveDataRef = useRef<(() => Promise<void>) | null>(null);

  const latestSnapshot = snapshots[0] ?? null;
  const memoryIsEstablished = memoryStatus?.has_initial_analysis ?? false;
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

  const currentSteps = useMemo(() => getStepsForMode(agentState.mode), [agentState.mode]);
  const insightMetrics = useMemo(() => getSignalMetrics(latestSnapshot), [latestSnapshot]);
  const persistedActivityLogs = useMemo(() => buildPersistedActivityLogs(automationStatus), [automationStatus]);
  const activityLogs = useMemo(
    () =>
      [...persistedActivityLogs, ...agentLogs]
        .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())
        .slice(0, 28),
    [agentLogs, persistedActivityLogs],
  );

  function applyObserverStatus(nextStatus: ObserverStatus, announceTransition = true): void {
    const wasConnected = status?.connected ?? false;
    startTransition(() => {
      setStatus((previous) => mergeStatus(previous, nextStatus));
      setPollingEnabled(!nextStatus.connected);
      setViewState(nextStatus.connected ? "connected" : "waiting");
      setConnectionError(null);
    });

    if (announceTransition && nextStatus.connected && !wasConnected) {
      pushAgentLog("success", "Observador conectado. As mensagens diretas ja podem alimentar a memoria.");
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
      const nextStatus = shouldRefreshQr ? await connectObserver() : await getObserverStatus(false);

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
      activeTab === "overview" ||
      activeTab === "manual" ||
      activeTab === "chat" ||
      activeTab === "memory" ||
      activeTab === "projects"
    ) && !isLoadingChatThread && !isCreatingChatThread && !isSendingChat && streamingText === null;
    const shouldRefreshAgentWorkspace = (
      activeTab === "overview" ||
      activeTab === "manual" ||
      activeTab === "agent"
    ) && !isAgentConnecting && !isAgentResetting;
    const shouldRefreshMemoryStatus = (
      activeTab === "overview" ||
      activeTab === "manual" ||
      activeTab === "observer" ||
      activeTab === "memory" ||
      activeTab === "activity" ||
      activeTab === "automation"
    );
    const shouldRefreshSnapshots = activeTab === "overview" || activeTab === "manual" || activeTab === "memory";
    const shouldRefreshImportantMessages = activeTab === "overview" || activeTab === "manual" || activeTab === "important";
    const shouldRefreshAutomation = (
      activeTab === "overview" ||
      activeTab === "manual" ||
      activeTab === "activity" ||
      activeTab === "automation"
    ) && !isTickingAutomation;

    dashboardRefreshInFlightRef.current = true;
    try {
      const [
        agentWorkspaceResult,
        chatWorkspaceResult,
        memoryStatusResult,
        snapshotsResult,
        importantMessagesResult,
        automationResult,
      ] = await Promise.allSettled([
        shouldRefreshAgentWorkspace ? getAgentWorkspace(activeAgentThreadId ?? undefined) : Promise.resolve(null),
        shouldRefreshChatWorkspace ? getChatWorkspace(activeChatThreadId ?? undefined) : Promise.resolve(null),
        shouldRefreshMemoryStatus ? getMemoryStatus() : Promise.resolve(null),
        shouldRefreshSnapshots ? getMemorySnapshots(6) : Promise.resolve(null),
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
      }

      if (importantMessagesResult.status === "fulfilled" && importantMessagesResult.value) {
        const nextImportantMessages = importantMessagesResult.value;
        startTransition(() => {
          setImportantMessages(nextImportantMessages);
          setImportantMessagesError(null);
        });
      } else if (importantMessagesResult.status === "rejected" && shouldRefreshImportantMessages) {
        setImportantMessagesError(getErrorMessage(importantMessagesResult.reason));
      }

      if (automationResult.status === "fulfilled" && automationResult.value) {
        const nextAutomation = automationResult.value;
        startTransition(() => {
          setAutomationStatus(nextAutomation);
          setAutomationError(null);
          setAutomationDraft((previous) => previous ?? toAutomationDraft(nextAutomation.settings));
        });
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
    return () => {
      if (agentTimerRef.current) {
        window.clearInterval(agentTimerRef.current);
      }
    };
  }, []);

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

    const [
      statusResult,
      agentWorkspaceResult,
      chatResult,
      memoryStatusResult,
      snapshotsResult,
      importantMessagesResult,
      automationResult,
    ] = await Promise.allSettled([
      getObserverStatus(false),
      getAgentWorkspace(activeAgentThreadId ?? undefined),
      getChatWorkspace(activeChatThreadId ?? undefined),
      getMemoryStatus(),
      getMemorySnapshots(6),
      getImportantMessages(80),
      getAutomationStatus(),
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

    if (agentWorkspaceResult.status === "fulfilled") {
      applyAgentWorkspace(agentWorkspaceResult.value);
    } else {
      const message = getErrorMessage(agentWorkspaceResult.reason);
      setAgentConnectionError(message);
      setAgentViewState("error");
      setAgentPollingEnabled(false);
    }

    if (chatResult.status === "fulfilled") {
      applyChatWorkspace(chatResult.value);
    } else {
      const message = getErrorMessage(chatResult.reason);
      setChatError(message);
      setMemoryError(message);
    }

    if (memoryStatusResult.status === "fulfilled") {
      setMemoryStatus(memoryStatusResult.value);
    }

    if (snapshotsResult.status === "fulfilled") {
      setSnapshots(snapshotsResult.value);
    }

    if (importantMessagesResult.status === "fulfilled") {
      setImportantMessages(importantMessagesResult.value);
      setImportantMessagesError(null);
    } else {
      setImportantMessagesError(getErrorMessage(importantMessagesResult.reason));
    }

    if (automationResult.status === "fulfilled") {
      const snap = automationResult.value;
      setAutomationStatus(snap);
      setAutomationError(null);
      setAutomationDraft((previous) => previous ?? toAutomationDraft(snap.settings));

      // Se temos um job em fila, verifica se ele terminou
      if (queuedJobId) {
        const matchingJob = snap.jobs.find(j => j.id === queuedJobId);
        if (matchingJob) {
          if (matchingJob.status === "succeeded") {
            setQueuedJobId(null);
            const intent = agentState.intent || "first_analysis";
            
            // Recarrega os dados agora que o processo terminou
            getCurrentMemory().then(setMemory);
            getMemoryProjects().then(setProjects);
            getMemoryStatus().then(setMemoryStatus);
            getImportantMessages(80).then(setImportantMessages).catch(() => {});
            
            finishAgentRunSuccess(
              intent,
              intent === "first_analysis" 
                ? "Primeira analise concluida. A base inicial do dono foi criada."
                : intent === "refine_saved"
                ? "Refinamento concluido. A memoria consolidada ficou mais precisa."
                : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado."
            );
          } else if (matchingJob.status === "failed") {
            setQueuedJobId(null);
            finishAgentRunError(agentState.intent || "first_analysis", matchingJob.error_text || "Ocorreu um erro desconhecido durante a análise.");
          }
        }
      }
    } else {
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
      setAutomationStatus((previous) =>
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
      setAutomationDraft(toAutomationDraft(nextSettings));
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
      setAutomationDraft((previous) => previous ?? toAutomationDraft(snapshot.settings));
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
      pushAgentLog("info", "Releitura concluída. Vou processar a fila agora para atualizar o resumo do dono.");

      try {
        const snapshot = await runAutomationTick();
        setAutomationStatus(snapshot);
        setAutomationDraft((previous) => previous ?? toAutomationDraft(snapshot.settings));
        pushAgentLog("success", "Fila processada após a releitura. O resumo e a memória já foram recalculados quando havia mensagens válidas.");
      } catch (tickError) {
        pushAgentLog("error", `A releitura terminou, mas o tick automático falhou: ${getErrorMessage(tickError)}`);
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
    setMemoryError(null);
    startAgentRun(intent);

    try {
        const response = intent === "first_analysis"
          ? await runFirstMemoryAnalysis()
          : await runNextMemoryBatch();
        
        // Response now contains the queued job
        if (response.job && response.job.status === "queued") {
          setQueuedJobId(response.job.id);
          pushAgentLog("info", "Tarefa registrada na fila do servidor. Iniciando processamento em segundo plano...");
        } else {
           setMemory(response.current);
           setProjects(response.projects);
           setSnapshots((previous) => [response.snapshot, ...previous.filter((snapshot) => snapshot.id !== response.snapshot.id)].slice(0, 6));
           finishAgentRunSuccess(
             intent,
             intent === "first_analysis"
               ? "Primeira analise concluida. A base inicial do dono foi criada."
               : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado.",
           );
        }
      } else {
        const response = await refineMemory();
        if (response.job && response.job.status === "queued") {
          setQueuedJobId(response.job.id);
          pushAgentLog("info", "Tarefa de refinamento registrada na fila. Otimizando a base de dados nos bastidores...");
        } else {
          setMemory(response.current);
          setProjects(response.projects);
          finishAgentRunSuccess("refine_saved", "Refinamento concluido. A memoria consolidada ficou mais precisa.");
        }
      }

    } catch (error) {
      const message = getErrorMessage(error);
      setMemoryError(message);
      finishAgentRunError(intent, message);
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
          <span>Agente</span>
          <div className={`ac-status-badge status-${agentViewState}`}>
            <span className="status-dot" />
            {agentStatusLabel}
          </div>
        </div>
          <div className="ac-quick-status">
            <span>Mensagens novas</span>
            <strong>{memoryStatus ? formatTokenCount(memoryStatus.pending_new_message_count) : "..."}</strong>
          </div>
          <div className="ac-quick-status">
            <span>Próximo lote</span>
            <strong>{memoryStatus ? formatTokenCount(memoryStatus.next_process_message_count) : "..."}</strong>
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
              disabled={
                agentState.running ||
                (memoryIsEstablished ? !memoryStatus?.can_run_next_batch : !memoryStatus?.can_run_first_analysis)
              }
              type="button"
            >
              <Play size={15} />
              {agentState.running && agentState.mode === "analyze"
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
              <p>Buscando status do observador, perfil atual, snapshots, projetos e histórico do chat.</p>
            </Card>
          ) : (
            <>
              {activeTab === "overview" ? (
                <OverviewTab
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  projects={projects}
                  status={status}
                  agentStatus={agentStatus}
                  agentSettings={agentSettings}
                  connectionError={connectionError}
                  memoryError={memoryError}
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

              {activeTab === "agent" ? (
                <AgentTab
                  status={agentStatus}
                  statusLabel={agentStatusLabel}
                  viewState={agentViewState}
                  settings={agentSettings}
                  activeSession={agentActiveSession}
                  contactMemory={agentContactMemory}
                  threads={agentThreads}
                  messages={agentMessages}
                  activeThreadId={activeAgentThreadId}
                  isConnecting={isAgentConnecting}
                  isResetting={isAgentResetting}
                  isSaving={isAgentSaving}
                  connectionError={agentConnectionError}
                  messagesError={agentMessagesError}
                  onConnect={() => void startAgentConnection()}
                  onReset={() => void resetAgentConnection()}
                  onToggleAutoReply={(value) => void toggleAgentAutoReply(value)}
                  onSelectThread={(threadId) => void openAgentThread(threadId)}
                  onRefresh={() => void refreshAgentWorkspace(activeAgentThreadId ?? undefined)}
                />
              ) : null}

              {activeTab === "memory" ? (
                <MemoryTab
                  memoryStatus={memoryStatus}
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  memoryError={memoryError}
                  agentState={agentState}
                  onInitialAnalysis={() => void runMemoryJob("first_analysis")}
                  onImproveMemory={() => void runMemoryJob("improve_memory")}
                />
              ) : null}

              {activeTab === "important" ? (
                <ImportantMessagesTab
                  messages={importantMessages}
                  error={importantMessagesError}
                  onRefresh={() => void hydrateDashboard("manual")}
                />
              ) : null}

              {activeTab === "projects" ? <ProjectsTab projects={projects} /> : null}

              {activeTab === "chat" ? (
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
                  chatScrollRef={chatScrollRef}
                  onChatDraftChange={setChatDraft}
                  onSelectThread={(threadId) => void openChatThread(threadId)}
                  onCreateThread={() => void startNewChatThread()}
                  onApplyPrompt={setChatDraft}
                  onSubmit={() => void submitChatMessage()}
                />
              ) : null}

              {activeTab === "activity" ? (
                <ActivityTab
                  agentState={agentState}
                  steps={currentSteps}
                  logs={activityLogs}
                  memory={memory}
                  latestSnapshot={latestSnapshot}
                  projectsCount={projects.length}
                  snapshotsCount={snapshots.length}
                  automationStatus={automationStatus}
                  automationError={automationError}
                />
              ) : null}

              {activeTab === "automation" ? (
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

              {activeTab === "manual" ? (
                <ManualTab
                  status={status}
                  agentStatus={agentStatus}
                  agentSettings={agentSettings}
                  memory={memory}
                  projects={projects}
                  snapshots={snapshots}
                  importantMessages={importantMessages}
                  chatThreads={chatThreads}
                  chatMessages={chatMessages}
                  automationStatus={automationStatus}
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
  status,
  agentStatus,
  agentSettings,
  connectionError,
  memoryError,
  insightMetrics,
  onGoToObserver,
  onGoToMemory,
  onGoToChat,
}: {
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projects: ProjectMemory[];
  status: ObserverStatus | null;
  agentStatus: WhatsAppAgentStatus | null;
  agentSettings: WhatsAppAgentSettings | null;
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
  const latestUpdateLabel = memory?.last_analyzed_at
    ? formatShortDateTime(memory.last_analyzed_at)
    : latestSnapshot?.created_at
      ? formatShortDateTime(latestSnapshot.created_at)
      : "Pendente";

  return (
    <div className="page-stack">
      <Card className="hero-panel">
        <div className="hero-copy">
          <div className="hero-kicker">
            <Brain size={14} />
            AuraCore Ativo
          </div>
          <h3>Seu painel central do WhatsApp organiza sinais, memórias, contatos importantes e frentes ativas em um só lugar.</h3>
          <p>O observador lê apenas conversas diretas, a memória consolida o que importa e os lotes novos atualizam o histórico sem complicar a operação.</p>
        </div>
        <div className="hero-actions">
          <button className="ac-secondary-button" onClick={onGoToObserver} type="button">
            <Eye size={15} />
            Ver Observador
          </button>
          <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
            <Database size={15} />
            Abrir Memória
          </button>
          <button className="ac-primary-button" onClick={onGoToChat} type="button">
            <MessageSquare size={15} />
            Abrir Chat
          </button>
        </div>
      </Card>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Painel de Resumo", "Mapa Estrutural", "Sinais Recentes"]}
          selected={
            subTab === "summary" ? "Painel de Resumo" : subTab === "mapping" ? "Mapa Estrutural" : "Sinais Recentes"
          }
          onChange={(val) => {
            if (val === "Painel de Resumo") setSubTab("summary");
            if (val === "Mapa Estrutural") setSubTab("mapping");
            if (val === "Sinais Recentes") setSubTab("signals");
          }}
        />
      </div>

      {subTab === "summary" ? (
        <>
          <div className="stats-grid modern-stats-grid">
            <ModernStatCard
              label="Observador"
              value={status?.connected ? "Online" : "Aguardando"}
              meta={status?.connected ? "Captura pronta" : "Sem sessão ativa"}
              icon={Eye}
              tone="emerald"
            />
            <ModernStatCard
              label="Número conectado"
              value={status?.owner_number ?? "Sem número"}
              meta="Dono do observador"
              icon={Smartphone}
            />
            <ModernStatCard
              label="Última atualização"
              value={latestUpdateLabel}
              meta={memory?.last_analyzed_at ? "Memória consolidada" : "Base inicial pendente"}
              icon={Clock}
              tone="amber"
            />
            <ModernStatCard
              label="Projetos ativos"
              value={String(projects.length)}
              meta={projects.length > 0 ? "Frentes consolidadas" : "Ainda sem frentes consolidadas"}
              icon={Database}
              tone="indigo"
            />
          </div>

          <Card>
            <SectionTitle title="Resumo do Dono (Atual)" icon={Fingerprint} />
            <p className="lead-copy">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Ainda não existe um perfil consolidado. Conecte o observador, deixe sinais suficientes chegarem e execute a primeira leitura."}
            </p>
          </Card>
        </>
      ) : null}

      {subTab === "mapping" ? (
        <Card>
          <SectionTitle title="Mapeamento Estrutural" icon={Brain} />
          <div className="dual-column-grid">
            <div className="signal-cluster">
              <h4>Áreas Fortes</h4>
              <SignalBlock
                title="Forcas Cumulativas"
                lines={structuralStrengths}
                emptyLabel="Sem forcas recorrentes consolidadas."
              />
              <SignalBlock
                title="Rotina Detectada"
                lines={structuralRoutines}
                emptyLabel="Sem sinais fortes de rotina ainda."
              />
              <SignalBlock
                title="Preferências Operacionais"
                lines={structuralPreferences}
                emptyLabel="Sem preferências consolidadas ainda."
              />
            </div>

            <div className="signal-cluster">
              <h4 className="amber">Pontos Frágeis</h4>
              <SignalBlock
                title="Lacunas Ainda Abertas"
                lines={structuralOpenQuestions}
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
      ) : null}

      {subTab === "signals" ? (
        <div className="dual-column-grid">
          <Card className="score-card-modern">
            <SectionTitle title="Resumo da Última Janela" icon={BarChart3} />
            <p className="support-copy">
              {latestSnapshot?.window_summary ??
                "Quando a primeira leitura concluir, este bloco passa a resumir o momento mais recente consolidado do dono."}
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
  const allowedContact = settings?.allowed_contact_phone ?? status?.allowed_contact_phone ?? "NÃ£o definido";
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
            Escaneie o QR do agente. Ele responde apenas pelo nÃºmero secundÃ¡rio e sÃ³ conversa com o nÃºmero conectado no observador.
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
            <StatusLine label="Contato permitido" value={allowedContact} tone="amber" />
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
              O agente responde somente para o nÃºmero conectado no observador. Esse contato Ã© atualizado automaticamente.
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
  const allowedContact = settings?.allowed_contact_phone ?? status?.allowed_contact_phone ?? "Nao definido";
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
            O numero secundario responde pelo proprio canal do agente e so aceita conversa do numero conectado no observador.
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
            label="Contato autorizado"
            value={allowedContact}
            meta="Atualizado automaticamente a partir do observador"
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
                <StatusLine label="Contato permitido" value={allowedContact} tone="amber" />
                <StatusLine label="Ultima atividade" value={formatDateTime(status?.last_seen_at)} tone="zinc" />
              </div>
              <div className="agent-note-panel">
                <strong>Regra central</strong>
                <p>O agente responde somente para o numero conectado no observador. Nenhum outro contato recebe resposta automatica.</p>
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

function MemoryTab({
  memoryStatus,
  memory,
  latestSnapshot,
  memoryError,
  agentState,
  onInitialAnalysis,
  onImproveMemory,
}: {
  memoryStatus: MemoryStatus | null;
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  memoryError: string | null;
  agentState: AgentState;
  onInitialAnalysis: () => void;
  onImproveMemory: () => void;
}) {
  const memoryReady = memoryStatus?.has_initial_analysis ?? false;
  const structuralStrengths = memory?.structural_strengths ?? [];
  const structuralRoutines = memory?.structural_routines ?? [];
  const structuralPreferences = memory?.structural_preferences ?? [];
  const structuralOpenQuestions = memory?.structural_open_questions ?? [];
  const pendingNewMessages = memoryStatus?.pending_new_message_count ?? 0;
  const nextProcessCount = memoryStatus?.next_process_message_count ?? 0;
  const messagesUntilAutoProcess = memoryStatus?.messages_until_auto_process ?? 0;
  const canRunFirstAnalysis = memoryStatus?.can_run_first_analysis ?? false;
  const canRunNextBatch = memoryStatus?.can_run_next_batch ?? false;
  const firstAnalysisLabel = nextProcessCount > 0
    ? pendingNewMessages > nextProcessCount
      ? `Fazer Primeira Analise (${formatTokenCount(nextProcessCount)} das ${formatTokenCount(pendingNewMessages)} mais recentes)`
      : `Fazer Primeira Analise (${formatTokenCount(nextProcessCount)} mensagens)`
    : "Fazer Primeira Analise";
  const nextBatchLabel = nextProcessCount > 0
    ? `Atualizar Sistema com ${formatTokenCount(nextProcessCount)} Mensagens Novas`
    : "Aguardando mensagens novas suficientes";

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle title="Estado da Memoria" icon={Database} />
        <p className="support-copy">
          Depois da primeira analise, este painel passa a contar apenas mensagens novas desde a ultima consolidacao.
          O backend trabalha com lotes economicos pequenos para manter custo baixo e contexto mais preciso.
        </p>
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
            meta="Mensagens novas desde a ultima analise concluida"
            tone="indigo"
          />
          <MemorySignalCard
            label="Proximo processamento"
            value={formatTokenCount(nextProcessCount)}
            meta={
              memoryReady
                ? nextProcessCount > 0
                  ? "O proximo processamento vai consumir exatamente esse lote"
                  : "Ainda nao ha lote suficiente para o processamento incremental"
                : "Na primeira analise entra uma selecao balanceada das mensagens mais relevantes"
            }
            tone="amber"
          />
          <MemorySignalCard
            label="Faltam para o automatico"
            value={memoryReady ? formatTokenCount(messagesUntilAutoProcess) : "--"}
            meta={
              memoryReady
                ? messagesUntilAutoProcess > 0
                  ? "Quando essa contagem chegar a zero, o backend enfileira 1 lote automatico"
                  : "Ja existe volume suficiente para o proximo lote automatico"
                : "O automatico so passa a valer depois da primeira analise"
            }
            tone="emerald"
          />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Acoes" icon={Zap} />
        {!memoryReady ? (
          <>
            <p className="support-copy">
              A primeira analise roda uma unica vez e usa uma selecao balanceada de mensagens diretas recentes, evitando inflar tokens com historico desnecessario.
            </p>
            <button
              className="ac-success-button"
              onClick={onInitialAnalysis}
              disabled={agentState.running || !!queuedJobId || !canRunFirstAnalysis}
              type="button"
            >
              <Play size={15} />
              {agentState.running && agentState.intent === "first_analysis" ? "Executando..." : !!queuedJobId ? "Aguardando fila..." : firstAnalysisLabel}
            </button>
          </>
        ) : (
          <>
            <p className="support-copy">
              Depois da base inicial, cada atualizacao usa apenas o proximo lote economico de mensagens novas. Isso mantem a memoria viva sem reprocessar tudo de novo.
            </p>
            <button
              className="ac-primary-button"
              onClick={onImproveMemory}
              disabled={agentState.running || !!queuedJobId || !canRunNextBatch}
              type="button"
            >
              <Sparkles size={15} />
              {agentState.running && agentState.intent === "improve_memory" ? "Processando..." : !!queuedJobId ? "Fila ativa..." : nextBatchLabel}
            </button>
          </>
        )}
      </Card>

      <Card>
        <SectionTitle title="Ultima Janela Recente" icon={FileText} />
        {latestSnapshot ? (
          <div className="manual-list">
            <p>{latestSnapshot.window_summary}</p>
            <p>
              Baseado em {formatTokenCount(latestSnapshot.source_message_count)} mensagens entre{" "}
              {formatDateTime(latestSnapshot.window_start)} e {formatDateTime(latestSnapshot.window_end)}.
            </p>
            <p>Este bloco mostra somente a janela mais recente. O retrato cumulativo do dono fica logo abaixo.</p>
          </div>
        ) : (
          <div className="empty-hint">
            <Database size={18} />
            <p>Sem snapshot ainda. A primeira leitura cria a base consolidada do dono.</p>
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle title="Memoria Atual do Dono" icon={Fingerprint} />
        <p className="lead-copy">
          {memory?.life_summary?.trim()
            ? memory.life_summary
            : "Nenhum resumo consolidado ainda. Assim que a primeira leitura rodar, este bloco vira a visao mais util do dono para o chat e para futuras atualizacoes automaticas."}
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

      {memoryError ? <InlineError title="Falha na memoria" message={memoryError} /> : null}
    </div>
  );
}

function ProjectsTab({ projects }: { projects: ProjectMemory[] }) {
  const [subTab, setSubTab] = useState<"overview" | "details" | "roadmap">("overview");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const totalSteps = projects.reduce((sum, p) => sum + p.next_steps.length, 0);
  const totalEvidence = projects.reduce((sum, p) => sum + p.evidence.length, 0);
  const avgStrength = projects.length > 0 ? Math.round(projects.reduce((sum, p) => sum + getProjectStrength(p), 0) / projects.length) : 0;
  const latestUpdated = projects.length > 0
    ? projects.reduce((latest, p) => (p.updated_at > latest ? p.updated_at : latest), projects[0].updated_at)
    : null;

  if (projects.length === 0) {
    return (
      <div className="page-stack">
        <Card className="proj-empty-hero">
          <div className="proj-empty-icon">
            <FolderGit2 size={40} />
          </div>
          <h3>Nenhum projeto consolidado</h3>
          <p>Assim que a memória tiver sinal suficiente, as frentes de trabalho reais aparecem aqui com detalhes completos, próximos passos e evidências.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="page-stack">
      {/* ── Hero Stats Row ── */}
      <div className="proj-stats-row">
        <ModernStatCard label="Projetos Ativos" value={String(projects.length)} meta="Frentes consolidadas" icon={FolderGit2} tone="indigo" />
        <ModernStatCard label="Próximos Passos" value={String(totalSteps)} meta="Ações pendentes totais" icon={ChevronRight} tone="amber" />
        <ModernStatCard label="Evidências" value={String(totalEvidence)} meta="Sinais de progresso" icon={CheckCircle2} tone="emerald" />
        <ModernStatCard label="Sinal Médio" value={`${avgStrength}%`} meta={latestUpdated ? `Últ. atualização ${formatRelativeTime(latestUpdated)}` : "Sem data"} icon={BarChart3} />
      </div>

      {/* ── Sub-tab Selector ── */}
      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Visão Geral", "Detalhes Completos", "Roadmap"]}
          selected={subTab === "overview" ? "Visão Geral" : subTab === "details" ? "Detalhes Completos" : "Roadmap"}
          onChange={(val) => {
            if (val === "Visão Geral") setSubTab("overview");
            if (val === "Detalhes Completos") setSubTab("details");
            if (val === "Roadmap") setSubTab("roadmap");
          }}
        />
      </div>

      {/* ═══ SUB-TAB: Visão Geral ═══ */}
      {subTab === "overview" ? (
        <>
          {/* Focus Cards */}
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
                <ProgressBar value={getProjectStrength(project)} tone={index === 0 ? "indigo" : "amber"} label="Densidade de sinal" />
                <p>{project.summary}</p>
                <div className="proj-focus-footer">
                  <div className="proj-focus-meta">
                    <Clock size={12} />
                    <span>{project.last_seen_at ? formatRelativeTime(project.last_seen_at) : "Sem data"}</span>
                  </div>
                  <div className="proj-focus-meta">
                    <User size={12} />
                    <span>{getAudienceLabel(project)}</span>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Quick Summary Grid for remaining projects */}
          {projects.length > 2 ? (
            <>
              <SectionTitle title={`Outros Projetos (${projects.length - 2})`} icon={GitBranch} />
              <div className="proj-summary-grid">
                {projects.slice(2).map((project) => (
                  <Card key={`${project.id}-summary`} className="proj-summary-card">
                    <div className="proj-summary-head">
                      <div className="proj-summary-name">
                        <GitBranch size={14} />
                        <h4>{project.project_name}</h4>
                      </div>
                      <div className={`micro-status micro-status-${project.status?.toLowerCase().includes("ativo") || project.status?.toLowerCase().includes("andamento") ? "emerald" : "amber"}`}>
                        {project.status || "Em progresso"}
                      </div>
                    </div>
                    <p className="proj-summary-text">{truncateText(project.summary, 120)}</p>
                    <div className="proj-summary-footer">
                      <ProgressBar value={getProjectStrength(project)} tone="zinc" />
                      <div className="proj-summary-meta">
                        <span>{project.next_steps.length} passos</span>
                        <span>•</span>
                        <span>{project.evidence.length} evidências</span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : null}

      {/* ═══ SUB-TAB: Detalhes Completos ═══ */}
      {subTab === "details" ? (
        <div className="proj-details-stack">
          {projects.map((project) => {
            const isExpanded = expandedId === project.id;
            const strength = getProjectStrength(project);
            return (
              <Card key={project.id} className={`proj-detail-card${isExpanded ? " proj-detail-card-expanded" : ""}`}>
                {/* Card Header - always visible */}
                <button className="proj-detail-header" onClick={() => setExpandedId(isExpanded ? null : project.id)} type="button">
                  <div className="proj-detail-header-left">
                    <div className="proj-detail-icon-wrap">
                      <FolderGit2 size={18} />
                    </div>
                    <div>
                      <h3>{project.project_name}</h3>
                      <span className="proj-detail-key">{project.project_key}</span>
                    </div>
                  </div>
                  <div className="proj-detail-header-right">
                    <div className={`micro-status micro-status-${strength >= 60 ? "emerald" : strength >= 40 ? "amber" : "zinc"}`}>
                      {project.status || "Em progresso"}
                    </div>
                    <div className="proj-detail-strength">
                      <span>{strength}%</span>
                      <div className="proj-detail-strength-bar">
                        <div style={{ width: `${strength}%` }} />
                      </div>
                    </div>
                    <ChevronRight size={16} className={`proj-expand-chevron${isExpanded ? " proj-expand-chevron-open" : ""}`} />
                  </div>
                </button>

                {/* Expanded Content */}
                {isExpanded ? (
                  <div className="proj-detail-body">
                    {/* Summary Section */}
                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <FileText size={14} />
                        <span>Resumo</span>
                      </div>
                      <p>{project.summary}</p>
                    </div>

                    {/* Two-column info */}
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

                    {/* Next Steps */}
                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <ChevronRight size={14} />
                        <span>Próximos Passos ({project.next_steps.length})</span>
                      </div>
                      {project.next_steps.length > 0 ? (
                        <ul className="proj-step-list">
                          {project.next_steps.map((step, i) => (
                            <li key={`step-${i}`}>
                              <span className="proj-step-number">{i + 1}</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">Nenhum próximo passo consolidado para este projeto.</p>
                      )}
                    </div>

                    {/* Evidence */}
                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <CheckCircle2 size={14} />
                        <span>Evidências ({project.evidence.length})</span>
                      </div>
                      {project.evidence.length > 0 ? (
                        <ul className="proj-evidence-list">
                          {project.evidence.map((ev, i) => (
                            <li key={`ev-${i}`}>
                              <CheckCircle2 size={12} />
                              <span>{ev}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">Nenhuma evidência recente consolidada.</p>
                      )}
                    </div>

                    {/* Footer Metadata */}
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
              </Card>
            );
          })}
        </div>
      ) : null}

      {/* ═══ SUB-TAB: Roadmap ═════ */}
      {subTab === "roadmap" ? (
        <div className="proj-roadmap-container">
          <Card>
            <SectionTitle title="Roadmap de Próximos Passos" icon={Zap} />
            <p className="support-copy">
              Visão consolidada de todos os próximos passos pendentes em cada projeto, organizados por prioridade de sinal.
            </p>
          </Card>

          <div className="proj-roadmap-timeline">
            {projects
              .filter((p) => p.next_steps.length > 0)
              .sort((a, b) => getProjectStrength(b) - getProjectStrength(a))
              .map((project) => (
                <div key={`roadmap-${project.id}`} className="proj-roadmap-project">
                  <div className="proj-roadmap-project-head">
                    <div className="proj-roadmap-dot" />
                    <div className="proj-roadmap-project-info">
                      <h4>{project.project_name}</h4>
                      <div className="proj-roadmap-meta-row">
                        <div className={`micro-status micro-status-${getProjectStrength(project) >= 60 ? "emerald" : "amber"}`}>
                          {project.status || "Em progresso"}
                        </div>
                        <span className="proj-roadmap-strength">{getProjectStrength(project)}% sinal</span>
                      </div>
                    </div>
                  </div>
                  <div className="proj-roadmap-steps">
                    {project.next_steps.map((step, i) => (
                      <div key={`roadmap-step-${i}`} className="proj-roadmap-step">
                        <div className="proj-roadmap-step-idx">{i + 1}</div>
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
                      {project.evidence.slice(0, 2).map((ev, i) => (
                        <p key={`roadmap-ev-${i}`} className="proj-roadmap-evidence-text">{ev}</p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}

            {projects.filter((p) => p.next_steps.length > 0).length === 0 ? (
              <Card>
                <div className="empty-hint">
                  <Zap size={18} />
                  <p>Nenhum projeto possui próximos passos definidos. Os passos aparecem conforme a memória consolida mais sinais.</p>
                </div>
              </Card>
            ) : null}
          </div>

          {/* Projects without next steps */}
          {projects.filter((p) => p.next_steps.length === 0).length > 0 ? (
            <Card>
              <SectionTitle title="Projetos sem Próximos Passos" icon={AlertCircle} />
              <div className="proj-roadmap-no-steps">
                {projects
                  .filter((p) => p.next_steps.length === 0)
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
  const credentialCount = messages.filter((message) => message.category === "credential" || message.category === "access").length;
  const businessCount = messages.filter((message) => ["project", "money", "client", "deadline"].includes(message.category)).length;
  const strongSignalsCount = messages.filter((message) => message.confidence >= 80).length;
  const lastReviewedAt = messages
    .map((message) => message.last_reviewed_at)
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0] ?? null;

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle
          title="Cofre de Mensagens Importantes"
          icon={Archive}
          action={
            <button className="ac-secondary-button" onClick={onRefresh} type="button">
              <RefreshCw size={14} />
              Atualizar
            </button>
          }
        />
        <p className="support-copy">
          Este cofre recebe automaticamente mensagens consideradas duráveis: acessos, dinheiro, projetos, riscos e
          fatos operacionais que merecem sobreviver além do lote curto de processamento.
        </p>

        <div className="important-top-grid">
          <ModernStatCard
            label="Ativas Agora"
            value={String(messages.length)}
            meta="Itens ainda úteis para memória futura"
            icon={Archive}
            tone="emerald"
          />
          <ModernStatCard
            label="Acessos & Credenciais"
            value={String(credentialCount)}
            meta="Logins, senhas e dados de acesso"
            icon={CheckCircle2}
            tone="amber"
          />
          <ModernStatCard
            label="Projetos & Dinheiro"
            value={String(businessCount)}
            meta="Operação, clientes, prazos e valores"
            icon={FolderGit2}
            tone="indigo"
          />
          <ModernStatCard
            label="Última Revisão"
            value={lastReviewedAt ? formatShortDateTime(lastReviewedAt) : "Pendente"}
            meta={lastReviewedAt ? formatRelativeTime(lastReviewedAt) : "Ainda sem revisão diária"}
            icon={Clock}
            tone="zinc"
          />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Como Isso Funciona" icon={Sparkles} />
        <div className="manual-grid">
          <ManualInfoCard title="Entrada Automática" text="Depois de cada análise de memória, o sistema separa só o que merece virar memória durável." />
          <ManualInfoCard title="Critério" text="A prioridade é guardar acessos, dinheiro, projetos, clientes, prazos, riscos e fatos operacionais reutilizáveis." />
          <ManualInfoCard title="Revisão Diária" text="O backend revisa esse cofre a partir da virada do dia em São Paulo e tira do uso ativo o que envelheceu ou perdeu valor." />
        </div>
      </Card>

      {messages.length === 0 ? (
        <Card>
          <div className="empty-hint">
            <Archive size={18} />
            <p>Nenhuma mensagem importante ativa ainda. Assim que uma análise concluir, o cofre começa a ser preenchido automaticamente.</p>
          </div>
        </Card>
      ) : (
        <div className="important-list">
          {messages.map((message) => (
            <Card key={message.id} className="important-card">
              <div className="important-card-head">
                <div>
                  <div className="important-badges">
                    <span className={`important-category-pill important-category-${message.category}`}>{formatImportantCategory(message.category)}</span>
                    <span className="micro-badge">{message.direction === "outbound" ? "Saída" : "Entrada"}</span>
                    <span className="micro-badge">{message.confidence}/100</span>
                  </div>
                  <h3>{message.contact_name || message.contact_phone || "Contato"}</h3>
                </div>
                <div className="important-card-meta">
                  <span>Capturada {formatRelativeTime(message.saved_at)}</span>
                  <strong>{formatShortDateTime(message.message_timestamp)}</strong>
                </div>
              </div>

              <p className="important-message-text">{message.message_text}</p>

              <div className="important-review-stack">
                <MiniPanel
                  title="Por Que Foi Salva"
                  tone="emerald"
                  icon={Sparkles}
                  content={message.importance_reason}
                />
                <MiniPanel
                  title="Estado da Revisão"
                  tone="amber"
                  icon={Clock}
                  content={
                    message.last_reviewed_at
                      ? `Revisada em ${formatShortDateTime(message.last_reviewed_at)}. ${message.review_notes ?? "Mantida no cofre ativo."}`
                      : "Ainda aguardando a primeira revisão diária automática."
                  }
                />
              </div>
            </Card>
          ))}
        </div>
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
  chatScrollRef,
  onChatDraftChange,
  onSelectThread,
  onCreateThread,
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
  chatScrollRef: React.RefObject<HTMLDivElement | null>;
  onChatDraftChange: (value: string) => void;
  onSelectThread: (threadId: string) => void;
  onCreateThread: () => void;
  onApplyPrompt: (value: string) => void;
  onSubmit: () => void;
}) {
  const quickPrompts = [
    "Me diga o que ficou pendente nos meus projetos.",
    "Resuma meu perfil de decisão.",
    "Monte um plano de prioridades para hoje.",
  ];

  return (
    <div className="gpt-chat-layout">
      {/* Thread Sidebar */}
      <aside className="gpt-thread-sidebar">
        <div className="gpt-thread-sidebar-top">
          <button className="gpt-new-chat-btn" onClick={onCreateThread} disabled={isCreatingChatThread} type="button">
            <Plus size={16} />
            {isCreatingChatThread ? "Criando..." : "Nova conversa"}
          </button>
        </div>

        <div className="gpt-thread-list">
          {chatThreads.length === 0 ? (
            <p className="gpt-thread-empty">Nenhuma conversa ainda.</p>
          ) : (
            chatThreads.map((thread) => {
              const active = activeChatThread?.id === thread.id;
              return (
                <button
                  key={thread.id}
                  className={`gpt-thread-item${active ? " gpt-thread-item-active" : ""}`}
                  onClick={() => onSelectThread(thread.id)}
                  type="button"
                >
                  <MessageSquare size={14} />
                  <span className="gpt-thread-title">{truncateText(thread.title, 32)}</span>
                  <span className="gpt-thread-time">{formatRelativeTime(thread.last_message_at ?? thread.updated_at)}</span>
                </button>
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
                <h3>AuraCore</h3>
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
                        <strong>{message.role === "assistant" ? "AuraCore" : "Você"}</strong>
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
                        <strong>AuraCore</strong>
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
              onChange={(event) => onChatDraftChange(event.target.value)}
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
}: {
  agentState: AgentState;
  steps: AgentStep[];
  logs: AgentLog[];
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projectsCount: number;
  snapshotsCount: number;
  automationStatus: AutomationStatus | null;
  automationError: string | null;
}) {
  const [activitySubTab, setActivitySubTab] = useState<"overview" | "persist" | "logs">("overview");
  const memoryReady = hasEstablishedMemory(memory, latestSnapshot);
  const resolvedIntent = agentState.intent ?? (memoryReady ? "improve_memory" : "first_analysis");
  const latestDecision = automationStatus?.decisions[0] ?? null;
  const latestSyncRun = automationStatus?.sync_runs[0] ?? null;
  const latestJob = automationStatus?.jobs[0] ?? null;
  const latestModelRun = automationStatus?.model_runs[0] ?? null;
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
    <div className="page-stack narrow-stack">
      {/* Sub-tab bar */}
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

      {/* Hero card — always visible */}
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
              label="Última decisão"
              value={latestDecision ? latestDecision.action : "..."}
              meta={latestDecision ? `${latestDecision.action} • ${latestDecision.reason_code}` : "Sem decisão automática persistida ainda"}
              tone="emerald"
            />
            <MemorySignalCard
              label="Jobs automáticos hoje"
              value={automationStatus ? String(automationStatus.daily_auto_jobs_count) : "..."}
              meta={
                automationStatus
                  ? `${automationStatus.queued_jobs_count} item(ns) na fila agora`
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
              meta={latestSnapshot ? `${formatTokenCount(latestSnapshot.source_message_count)} mensagens consolidadas` : "Aguardando primeira leitura"}
              tone="amber"
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
                  <p>Nenhuma decisão automática persistida ainda.</p>
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
  agentStatus,
  agentSettings,
  memory,
  projects,
  snapshots,
  importantMessages,
  chatThreads,
  chatMessages,
  automationStatus,
}: {
  status: ObserverStatus | null;
  agentStatus: WhatsAppAgentStatus | null;
  agentSettings: WhatsAppAgentSettings | null;
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
            Ele conecta o observador, filtra somente conversas diretas uteis, consolida memoria do dono, salva memoria por
            pessoa, identifica mensagens importantes, organiza projetos e ainda oferece um chat pessoal que responde usando
            esse contexto inteiro.
          </p>
        </div>
        <div className="manual-hero-stats">
          <ModernStatCard
            label="Observador"
            value={status?.connected ? "Online" : "Pendente"}
            meta={status?.connected ? "Capturando conversas diretas" : "Conecte o WhatsApp primeiro"}
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
                <p>O Observador cuida da entrada. A Memoria cuida da consolidacao. Importantes e Projetos guardam o que merece sobreviver. O Chat usa tudo isso para responder. Atividade e Automacao mostram o que o backend fez ou esta fazendo.</p>
              </div>
              <div className="manual-list">
                <p>Para o usuario final, a ideia e simples: conectar, fazer a primeira analise, deixar a automacao manter o contexto e usar o chat pessoal como uma camada de apoio persistente.</p>
                <p>Para voce localizar qualquer problema, pense assim: entrada de dados em Observador, consolidacao em Memoria, armazenamento em Supabase e leitura do estado em Atividade.</p>
              </div>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Mapa Das Abas" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="Visao Geral" text="Painel-resumo do estado atual: conexao, memoria, projetos, sinais e atalhos para o fluxo principal." />
              <ManualInfoCard title="Observador" text="Ponto de entrada do WhatsApp. Mostra QR, estado da instancia, sessao e a saude da captura." />
              <ManualInfoCard title="Memoria" text="Aqui nasce e evolui a memoria central. Primeira analise, lotes economicos de mensagens novas, estado da fila e resumo do dono." />
              <ManualInfoCard title="Importantes" text="Cofre de fatos duraveis: acessos, valores, clientes, prazos, riscos e sinais operacionais reaproveitaveis." />
              <ManualInfoCard title="Projetos" text="Organiza frentes reais detectadas nas conversas, com resumo, status, evidencias e proximos passos." />
              <ManualInfoCard title="Chat Pessoal" text="Thread por assunto usando a memoria central. Bom para separar estrategia, rotina, vendas, produto e operacao." />
              <ManualInfoCard title="Atividade" text="Mostra o pipeline trabalhando: logs, lotes, trilha de execucao e o melhor raciocinio operacional salvo." />
              <ManualInfoCard title="Automacao" text="Mostra a fila automatica e o estado do loop de processamento sem expor configuracoes tecnicas desnecessarias." />
            </div>
          </Card>

          <Card>
            <SectionTitle title="WhatsApp Agente" icon={Bot} />
            <div className="status-line-list">
              <StatusLine label="Status" value={agentStatus?.connected ? "Online" : "Pendente"} tone="indigo" />
              <StatusLine label="Auto-reply" value={agentSettings?.auto_reply_enabled ? "Ativo" : "Desligado"} tone="amber" />
              <StatusLine label="Contato permitido" value={agentSettings?.allowed_contact_phone ?? "NÃ£o definido"} tone="zinc" />
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "flow" ? (
        <>
          <Card>
            <SectionTitle title="Fluxo Real Do Site" icon={Terminal} />
            <div className="manual-sequence">
              <ManualStep title="1. Conectar o observador" text="Voce gera o QR, conecta o WhatsApp e libera a captura. A partir daqui o sistema passa a receber somente o que interessa para memoria." />
              <ManualStep title="2. Filtrar a entrada" text="Nem tudo entra. A ingestao prioriza chats diretos uteis e evita grupo, broadcast, newsletter, status e lixo operacional sem texto relevante." />
              <ManualStep title="3. Criar a memoria base" text="A primeira analise e manual e usa uma selecao balanceada das mensagens diretas mais relevantes e recentes. Ela cria o primeiro retrato consolidado do dono." />
              <ManualStep title="4. Atualizar por contato" text="Durante as analises, o sistema tenta entender com quem e cada conversa e atualiza memorias separadas por pessoa de forma cumulativa." />
              <ManualStep title="5. Processar lotes incrementais" text="Depois da base inicial, o backend passa a trabalhar em lotes economicos de mensagens novas, contando apenas o que chegou desde a ultima consolidacao." />
              <ManualStep title="6. Salvar o que dura" text="O processamento atualiza resumo do dono, snapshots, projetos, memorias por pessoa e o cofre de mensagens importantes." />
              <ManualStep title="7. Reutilizar no chat" text="O chat pessoal consome a memoria consolidada, projetos, contexto da thread atual e sinais importantes para responder melhor." />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Botoes Principais" icon={Zap} />
            <div className="manual-grid">
              <ManualInfoCard title="Puxar Novas Mensagens do WhatsApp" text="Forca uma releitura das conversas diretas recentes e atualiza a fila operacional no banco." />
              <ManualInfoCard title="Fazer Primeira Analise" text="Cria a base inicial da memoria quando o sistema ainda nao conhece bem o dono." />
              <ManualInfoCard title="Processar Proximo Lote" text="Consome o proximo lote de mensagens novas quando ja existe memoria base e ha volume suficiente." />
              <ManualInfoCard title="Refinar Memoria Ja Salva" text="Nao busca novas mensagens; apenas reorganiza e melhora o que ja esta consolidado." />
              <ManualInfoCard title="Nova Conversa" text="Abre uma thread nova no chat sem perder a memoria central nem o restante do historico salvo." />
              <ManualInfoCard title="Rodar Tick Agora" text="Executa o ciclo da automacao manualmente: fecha syncs, registra decisoes e tenta processar a fila." />
            </div>
          </Card>
        </>
      ) : null}

      {manualSubTab === "architecture" ? (
        <>
          <Card>
            <SectionTitle title="Arquitetura Em Camadas" icon={Server} />
            <div className="manual-grid">
              <ManualInfoCard title="Frontend" text="O painel organiza as abas de operacao, memoria, atividade e chat. Ele consulta a API e mostra o estado persistido do sistema." />
              <ManualInfoCard title="Backend FastAPI" text="Coordena observador, memoria, automacao, chat e persistencia. E onde ficam as regras de selecao de mensagens e atualizacao de contexto." />
              <ManualInfoCard title="Supabase" text="Armazena mensagens operacionais, snapshots, persona, projetos, memorias por pessoa, threads do chat e trilhas da automacao." />
              <ManualInfoCard title="Modelos" text="O motor de analise consolida memoria e o chat responde usando o contexto salvo. O frontend nao inventa raciocinio que o backend nao persistiu." />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Como Cada Parte Se Conversa" icon={GitBranch} />
            <div className="manual-list">
              <p>Observador envia mensagens para o backend. O backend decide o que entra em `mensagens` e atualiza a fila operacional.</p>
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
            <SectionTitle title="O Que Vai Para O Supabase" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="mensagens" text="Fila operacional de conversas diretas aproveitaveis que ainda podem alimentar analise e memoria." />
              <ManualInfoCard title="persona e memory_snapshots" text="Resumo principal do dono e historico de janelas consolidadas ao longo do tempo." />
              <ManualInfoCard title="person_memories" text="Memoria separada por contato, atualizada progressivamente para cada pessoa relevante nas conversas." />
              <ManualInfoCard title="project_memories" text="Projetos, frentes, entregas, clientes e proximos passos com base nas conversas consolidadas." />
              <ManualInfoCard title="important_messages" text="Cofre de itens duraveis como acesso, dinheiro, prazo, risco e fatos operacionais." />
              <ManualInfoCard title="chat_threads e chat_messages" text="Threads do chat pessoal usadas para separar contextos sem perder a memoria central." />
              <ManualInfoCard title="wa_sync_runs, automation_decisions, analysis_jobs, model_runs" text="Auditoria do que foi sincronizado, decidido, processado e executado." />
              <ManualInfoCard title="wa_sessions e wa_session_keys" text="Estado de sessao e chaves do observador do WhatsApp." />
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
              />
              <ManualInfoCard
                title="Ultimo Snapshot"
                text={
                  latestSnapshot
                    ? `Ultima janela consolidada em ${formatShortDateTime(latestSnapshot.created_at)} com ${latestSnapshot.source_message_count} mensagens.`
                    : "Nenhum snapshot consolidado ainda."
                }
              />
              <ManualInfoCard
                title="Mensagens Importantes"
                text={
                  importantCount > 0
                    ? `${importantCount} item(ns) ativos no cofre com revisao automatica diaria.`
                    : "Nenhuma mensagem importante ativa ainda."
                }
              />
              <ManualInfoCard
                title="Projetos e Threads"
                text={`${projectCount} projeto(s) consolidado(s), ${threadCount} thread(s) no chat e ${chatMessages.length} mensagem(ns) na thread aberta.`}
              />
              <ManualInfoCard
                title="Fila Automatica"
                text={
                  automationStatus
                    ? `${automationStatus.queued_jobs_count} job(s) na fila e ${automationStatus.daily_auto_jobs_count} processamento(s) automaticos hoje.`
                    : "Status da automacao ainda nao carregado."
                }
              />
            </div>
          </Card>

          <Card>
            <SectionTitle title="Como Diagnosticar Rapido" icon={AlertCircle} />
            <div className="manual-grid">
              <ManualInfoCard title="Sem mensagens novas" text="Olhe primeiro a aba Observador e a releitura manual. Se nao houver entrada, a memoria nao tem o que processar." />
              <ManualInfoCard title="Sem memoria base" text="A automacao nao inicia a base sozinha. Rode manualmente a primeira analise na aba Memoria." />
              <ManualInfoCard title="Chat ruim ou vazio" text="Confira se ja existe memoria consolidada, se ha snapshots e se a thread atual tem historico suficiente." />
              <ManualInfoCard title="Fila travada" text="Use Atividade e Automacao para ver ultimo sync, decisao, job e rastro do pipeline." />
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function ManualInfoCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="manual-info-card">
      <strong>{title}</strong>
      <p>{text}</p>
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

function ManualStep({ title, text }: { title: string; text: string }) {
  const [stepLabel, ...titleParts] = title.split(". ");
  const heading = titleParts.length > 0 ? titleParts.join(". ") : title;
  return (
    <div className="manual-step">
      <span>{stepLabel}</span>
      <strong>{heading}</strong>
      <p>{text}</p>
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
