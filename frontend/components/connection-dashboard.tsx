"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  connectObserver,
  getChatWorkspace,
  getImportantMessages,
  getMemoryStatus,
  getMemorySnapshots,
  getObserverStatus,
  previewMemoryAnalysis,
  refreshObserverMessages,
  refineMemory,
  resetObserver,
  runFirstMemoryAnalysis,
  runNextMemoryBatch,
  runAutomationTick,
  sendChatMessageStream,
  updateAutomationSettings,
  type AutomationSettings,
  type AutomationStatus,
  type ChatMessage,
  type ChatThread,
  type ChatWorkspace,
  type ImportantMessage,
  type MemoryAnalysisDetailMode,
  type MemoryAnalysisPreview,
  type MemoryCurrent,
  type MemoryStatus,
  type MemorySnapshot,
  type ObserverStatus,
  type ProjectMemory,
} from "@/lib/api";

type ViewState = "idle" | "loading" | "waiting" | "connected" | "error";
type AgentMode = "idle" | "analyze" | "refine";
type AgentIntent = "first_analysis" | "improve_memory" | "refine_saved";
type TabId = "overview" | "observer" | "memory" | "important" | "projects" | "chat" | "activity" | "automation" | "manual";
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
    message: `Job ${job.status}: ${getIntentTitle(job.intent as AgentIntent)} em ${job.detail_mode}, alvo ${job.target_message_count} msgs, custo teto ${formatUsd(job.estimated_cost_ceiling_usd)}.`,
  }));

  return [...syncLogs, ...decisionLogs, ...jobLogs].sort((left, right) => (
    new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
  ));
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

// ── Smart context builder ──────────────────────────────────────────────────────
// Scores important messages, projects, snapshots and memory by relevance to the
// user's question. Picks the best items across all sources, staying within a
// tight character budget so token cost stays low.
// Does NOT include raw WhatsApp messages — that is DeepSeek's job during analysis.

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
    addPart("Cofre de mensagens importantes (identificadas pelo DeepSeek nas conversas do WhatsApp):");
    for (const { item: m } of relevantMessages) {
      if (!addPart(`- [${m.category}] ${m.contact_name || "?"}: ${truncateText(m.message_text, 100)}`)) break;
    }
  }

  if (relevantProjects.length > 0) {
    addPart("Projetos relevantes (consolidados pelo DeepSeek):");
    for (const { item: p } of relevantProjects) {
      if (!addPart(`- ${p.project_name}: ${truncateText(p.summary, 80)} [${p.status}]`)) break;
      if (p.next_steps.length > 0) addPart(`  Proximos: ${p.next_steps.slice(0, 2).join("; ")}`);
    }
  }

  if (relevantInsights.length > 0) {
    addPart("Insights do DeepSeek (analises recentes):");
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
  const [filters, setFilters] = useState<MemoryFilters>({
    targetMessageCount: 200,
    maxLookbackHours: 72,
    detailMode: "balanced",
  });
  const [preview, setPreview] = useState<MemoryAnalysisPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [importantMessagesError, setImportantMessagesError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [messageRefreshError, setMessageRefreshError] = useState<string | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingMessages, setIsRefreshingMessages] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [isLoadingChatThread, setIsLoadingChatThread] = useState(false);
  const [isCreatingChatThread, setIsCreatingChatThread] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [isTickingAutomation, setIsTickingAutomation] = useState(false);
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

  const latestSnapshot = snapshots[0] ?? null;
  const memoryIsEstablished = memoryStatus?.has_initial_analysis ?? hasEstablishedMemory(memory, latestSnapshot);
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

  async function hydrateDashboard(mode: "initial" | "manual" = "initial"): Promise<void> {
    if (mode === "manual") {
      setIsRefreshing(true);
    } else {
      setIsHydrating(true);
    }

    const [statusResult, chatResult, memoryStatusResult, snapshotsResult, importantMessagesResult, automationResult] = await Promise.allSettled([
      getObserverStatus(false),
      getChatWorkspace(activeChatThreadId ?? undefined),
      getMemoryStatus(),
      getMemorySnapshots(6),
      getImportantMessages(80),
      getAutomationStatus(),
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
      setAutomationStatus(automationResult.value);
      setAutomationError(null);
      setAutomationDraft((previous) => previous ?? toAutomationDraft(automationResult.value.settings));
    } else {
      setAutomationError(getErrorMessage(automationResult.reason));
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
      if (intent === "first_analysis" || intent === "improve_memory") {
        const response = intent === "first_analysis"
          ? await runFirstMemoryAnalysis()
          : await runNextMemoryBatch();
        setMemory(response.current);
        setProjects(response.projects);
        setSnapshots((previous) => [response.snapshot, ...previous.filter((snapshot) => snapshot.id !== response.snapshot.id)].slice(0, 6));
        finishAgentRunSuccess(
          intent,
          intent === "first_analysis"
            ? "Primeira analise concluida. A base inicial do dono foi criada."
            : "Leitura concluida. As mensagens novas foram cruzadas com a memoria existente e o perfil foi melhorado.",
        );
        const [automationSnapshot, nextMemoryStatus, nextImportantMessagesResult] = await Promise.all([
          getAutomationStatus(),
          getMemoryStatus(),
          getImportantMessages(80).then((messages) => ({ ok: true as const, messages })).catch((error: unknown) => ({ ok: false as const, error })),
        ]);
        setAutomationStatus(automationSnapshot);
        setAutomationDraft((previous) => previous ?? toAutomationDraft(automationSnapshot.settings));
        setMemoryStatus(nextMemoryStatus);
        if (nextImportantMessagesResult.ok) {
          setImportantMessages(nextImportantMessagesResult.messages);
          setImportantMessagesError(null);
        } else {
          setImportantMessagesError(getErrorMessage(nextImportantMessagesResult.error));
        }
      } else {
        const response = await refineMemory();
        setMemory(response.current);
        setProjects(response.projects);
        finishAgentRunSuccess("refine_saved", "Refinamento concluido. A memoria consolidada ficou mais precisa.");
        const [automationSnapshot, nextMemoryStatus, nextImportantMessagesResult] = await Promise.all([
          getAutomationStatus(),
          getMemoryStatus(),
          getImportantMessages(80).then((messages) => ({ ok: true as const, messages })).catch((error: unknown) => ({ ok: false as const, error })),
        ]);
        setAutomationStatus(automationSnapshot);
        setAutomationDraft((previous) => previous ?? toAutomationDraft(automationSnapshot.settings));
        setMemoryStatus(nextMemoryStatus);
        if (nextImportantMessagesResult.ok) {
          setImportantMessages(nextImportantMessagesResult.messages);
          setImportantMessagesError(null);
        } else {
          setImportantMessagesError(getErrorMessage(nextImportantMessagesResult.error));
        }
      }

      await refreshPreview();
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
      setChatError("Escreva uma mensagem para conversar com a IA.");
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
                  preview={preview}
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
                  memory={memory}
                  preview={preview}
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
  const [subTab, setSubTab] = useState<"summary" | "mapping" | "engine">("summary");

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

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Painel de Resumo", "Mapa Estrutural", "Métricas Engine"]}
          selected={
            subTab === "summary" ? "Painel de Resumo" : subTab === "mapping" ? "Mapa Estrutural" : "Métricas Engine"
          }
          onChange={(val) => {
            if (val === "Painel de Resumo") setSubTab("summary");
            if (val === "Mapa Estrutural") setSubTab("mapping");
            if (val === "Métricas Engine") setSubTab("engine");
          }}
        />
      </div>

      {subTab === "summary" ? (
        <>
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
      ) : null}

      {subTab === "engine" ? (
        <div className="dual-column-grid">
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
      ) : null}

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
  const memoryReady = memoryStatus?.has_initial_analysis ?? hasEstablishedMemory(memory, latestSnapshot);
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
    ? `Processar Proximo Lote de ${formatTokenCount(nextProcessCount)} Agora`
    : "Aguardando 10 mensagens novas";

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle title="Estado da Memoria" icon={Database} />
        <p className="support-copy">
          Esta contagem considera mensagens recebidas e enviadas. Depois da primeira analise, o backend atualiza memoria,
          projetos e mensagens importantes em lotes fixos de 10 mensagens novas.
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
            meta="Fila operacional atual do WhatsApp, somando recebidas e enviadas"
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
                : "Na primeira analise entram ate 250 mensagens recentes"
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
              A primeira analise roda uma unica vez e usa sempre as mensagens diretas mais recentes disponiveis, com teto de 250.
            </p>
            <button
              className="ac-success-button"
              onClick={onInitialAnalysis}
              disabled={agentState.running || !canRunFirstAnalysis}
              type="button"
            >
              <Play size={15} />
              {agentState.running && agentState.intent === "first_analysis" ? "Executando..." : firstAnalysisLabel}
            </button>
          </>
        ) : (
          <>
            <p className="support-copy">
              Depois da base inicial, cada atualizacao usa apenas o proximo lote de 10 mensagens novas. O botao abaixo adianta manualmente esse proximo lote quando ele ja estiver disponivel.
            </p>
            <button
              className="ac-primary-button"
              onClick={onImproveMemory}
              disabled={agentState.running || !canRunNextBatch}
              type="button"
            >
              <Sparkles size={15} />
              {agentState.running && agentState.intent === "improve_memory" ? "Processando..." : nextBatchLabel}
            </button>
          </>
        )}
      </Card>

      <Card>
        <SectionTitle title="Ultimo Snapshot" icon={FileText} />
        {latestSnapshot ? (
          <div className="manual-list">
            <p>{latestSnapshot.window_summary}</p>
            <p>
              Baseado em {formatTokenCount(latestSnapshot.source_message_count)} mensagens entre{" "}
              {formatDateTime(latestSnapshot.window_start)} e {formatDateTime(latestSnapshot.window_end)}.
            </p>
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

      {memoryError ? <InlineError title="Falha na memoria" message={memoryError} /> : null}
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
          Este cofre recebe automaticamente mensagens que a IA considera duráveis: acessos, dinheiro, projetos,
          riscos e fatos operacionais que merecem sobreviver além do lote curto de processamento.
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
          <ManualInfoCard title="Entrada Automática" text="Depois de cada análise de memória, o DeepSeek escolhe só o que merece virar memória durável." />
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
          <p className="gpt-composer-note">
            AuraCore usa sua memória consolidada para responder. Pressione Enter para enviar.
          </p>
        </div>
      </section>
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
  automationStatus,
  automationError,
}: {
  agentState: AgentState;
  steps: AgentStep[];
  logs: AgentLog[];
  preview: MemoryAnalysisPreview | null;
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
    preview,
    intent: resolvedIntent,
    hasMemory: memoryReady,
    projectsCount,
    snapshotsCount,
  });
  const resolvedThinking = latestDecision?.explanation
    ? [latestDecision.explanation, ...thinkingLines]
    : thinkingLines;
  const costRangeLabel = preview
    ? `${formatUsd(preview.estimated_cost_total_floor_usd)}-${formatUsd(preview.estimated_cost_total_ceiling_usd)}`
    : "...";

  const subTabs = [
    { id: "overview" as const, label: "Visão Geral", icon: BarChart3 },
    { id: "persist" as const, label: "Persistência", icon: Database },
    { id: "logs" as const, label: "Logs", icon: Terminal },
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
              value={latestDecision ? `${latestDecision.score}/100` : "..."}
              meta={latestDecision ? `${latestDecision.action} • ${latestDecision.reason_code}` : "Sem decisão automática persistida ainda"}
              tone="emerald"
            />
            <MemorySignalCard
              label="Custo do dia"
              value={automationStatus ? formatUsd(automationStatus.daily_cost_usd) : costRangeLabel}
              meta={
                automationStatus
                  ? `${formatTokenCount(automationStatus.daily_auto_jobs_count)} jobs automáticos hoje`
                  : preview
                    ? `~${formatTokenCount(preview.estimated_total_tokens)} tokens totais`
                    : "Aguardando preview"
              }
              tone="amber"
            />
          </div>

          <Card className="activity-thinking-card">
            <SectionTitle title="Resumo do Pensamento" icon={Brain} action={<span className="micro-badge">sem CoT bruto</span>} />
            <p className="support-copy">
              O painel mostra o raciocinio operacional da execucao e o que o modelo vai considerar. A cadeia de pensamento bruta do `deepseek-reasoner` nao e exposta.
            </p>
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
              label="Último modelo"
              value={latestModelRun ? latestModelRun.model_name : "..."}
              meta={
                latestModelRun
                  ? `${latestModelRun.run_type} • ${latestModelRun.success ? "ok" : "falhou"}`
                  : "Sem execução de modelo registrada ainda"
              }
              tone="indigo"
            />
            <MemorySignalCard
              label="Janela útil"
              value={preview ? `${formatTokenCount(preview.selected_message_count)}/${formatTokenCount(preview.available_message_count)} msgs` : "..."}
              meta={preview ? `teto operacional de ${formatTokenCount(preview.stack_max_message_capacity)} msgs` : "Aguardando preview"}
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
              <SectionTitle title="Execução de Modelo" icon={Cpu} />
              {latestModelRun ? (
                <div className="activity-persist-block">
                  <strong>{latestModelRun.model_name}</strong>
                  <p>
                    {latestModelRun.run_type} • {latestModelRun.success ? "sucesso" : "falha"}
                  </p>
                  <div className="activity-meta-row">
                    <span>{latestModelRun.latency_ms ? `${latestModelRun.latency_ms} ms` : "latência n/d"}</span>
                    <span>{latestModelRun.estimated_cost_usd != null ? formatUsd(latestModelRun.estimated_cost_usd) : "custo n/d"}</span>
                  </div>
                </div>
              ) : (
                <div className="empty-hint">
                  <Cpu size={18} />
                  <p>Nenhuma execução de modelo registrada ainda.</p>
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}

      {/* === LOGS sub-tab === */}
      {activitySubTab === "logs" ? (
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
          Depois da primeira analise, o backend processa 1 lote de 10 mensagens novas por ciclo.
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
            meta={automationStatus ? `${formatUsd(automationStatus.daily_cost_usd)} consumidos hoje` : "Aguardando status"}
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

  /*

  const settings = automationStatus?.settings ?? null;
  const draft = automationDraft;

  function updateDraft<K extends keyof AutomationDraft>(key: K, value: AutomationDraft[K]): void {
    onDraftChange((previous) => {
      const base = previous ?? (settings ? toAutomationDraft(settings) : null);
      if (!base) {
        return previous;
      }
      return { ...base, [key]: value };
    });
  }

  return (
    <div className="page-stack">
      <Card>
        <SectionTitle
          title="Automação Controlada"
          icon={Settings}
          action={settings ? <span className="micro-badge">{formatShortDateTime(settings.updated_at)}</span> : null}
        />
        <p className="support-copy">
          Esta área controla quando o backend transforma uma sincronização em decisão e quando a decisão vira job automático.
        </p>

        <div className="automation-top-grid">
          <MemorySignalCard
            label="Gasto de hoje"
            value={automationStatus ? formatUsd(automationStatus.daily_cost_usd) : "..."}
            meta={automationStatus ? `${automationStatus.daily_auto_jobs_count} jobs automáticos hoje` : "Aguardando status"}
            accent
          />
          <MemorySignalCard
            label="Fila"
            value={automationStatus ? String(automationStatus.queued_jobs_count) : "..."}
            meta={automationStatus?.running_job_id ? "Há job rodando agora" : "Sem job rodando"}
            tone="indigo"
          />
          <MemorySignalCard
            label="Último sync"
            value={automationStatus?.sync_runs[0] ? automationStatus.sync_runs[0].status : "..."}
            meta={automationStatus?.sync_runs[0] ? formatShortDateTime(automationStatus.sync_runs[0].started_at) : "Sem sync persistido"}
            tone="emerald"
          />
          <MemorySignalCard
            label="Última decisão"
            value={automationStatus?.decisions[0] ? automationStatus.decisions[0].action : "..."}
            meta={automationStatus?.decisions[0] ? automationStatus.decisions[0].reason_code : "Sem decisão persistida"}
            tone="amber"
          />
        </div>

        {draft ? (
          <div className="automation-settings-grid">
            <div className="automation-setting-card">
              <SectionTitle title="Chaves de Automação" icon={Zap} />
              <label className="automation-toggle-row">
                <span>Auto sync</span>
                <input
                  type="checkbox"
                  checked={draft.auto_sync_enabled}
                  onChange={(event) => updateDraft("auto_sync_enabled", event.target.checked)}
                />
              </label>
              <label className="automation-toggle-row">
                <span>Auto analisar</span>
                <input
                  type="checkbox"
                  checked={draft.auto_analyze_enabled}
                  onChange={(event) => updateDraft("auto_analyze_enabled", event.target.checked)}
                />
              </label>
              <label className="automation-toggle-row">
                <span>Auto refinar</span>
                <input
                  type="checkbox"
                  checked={draft.auto_refine_enabled}
                  onChange={(event) => updateDraft("auto_refine_enabled", event.target.checked)}
                />
              </label>
            </div>

            <div className="automation-setting-card">
              <SectionTitle title="Thresholds" icon={BarChart3} />
              <AutomationNumberField
                label="Novas mensagens"
                value={draft.min_new_messages_threshold}
                onChange={(value) => updateDraft("min_new_messages_threshold", value)}
              />
              <AutomationNumberField
                label="Stale em horas"
                value={draft.stale_hours_threshold}
                onChange={(value) => updateDraft("stale_hours_threshold", value)}
              />
              <AutomationNumberField
                label="Podadas para reagir"
                value={draft.pruned_messages_threshold}
                onChange={(value) => updateDraft("pruned_messages_threshold", value)}
              />
            </div>

            <div className="automation-setting-card">
              <SectionTitle title="Configuração Base" icon={Cpu} />
              <div className="control-block automation-control-block">
                <div className="control-head">
                  <label>Profundidade padrão</label>
                  <span>Usada nos jobs incrementais</span>
                </div>
                <SegmentedControl
                  options={["light", "balanced", "deep"]}
                  selected={draft.default_detail_mode}
                  onChange={(value) => updateDraft("default_detail_mode", value as MemoryAnalysisDetailMode)}
                />
              </div>
              <AutomationNumberField
                label="Alvo padrão"
                value={draft.default_target_message_count}
                onChange={(value) => updateDraft("default_target_message_count", value)}
              />
              <AutomationNumberField
                label="Lookback padrão"
                value={draft.default_lookback_hours}
                onChange={(value) => updateDraft("default_lookback_hours", value)}
              />
            </div>

            <div className="automation-setting-card">
              <SectionTitle title="Orçamento" icon={Terminal} />
              <AutomationNumberField
                label="Budget diário (USD)"
                value={draft.daily_budget_usd}
                step="0.01"
                onChange={(value) => updateDraft("daily_budget_usd", value)}
              />
              <AutomationNumberField
                label="Jobs automáticos/dia"
                value={draft.max_auto_jobs_per_day}
                onChange={(value) => updateDraft("max_auto_jobs_per_day", value)}
              />
            </div>
          </div>
        ) : (
          <div className="empty-hint">
            <Settings size={18} />
            <p>Carregando configuração da automação.</p>
          </div>
        )}

        <div className="hero-actions">
          <button className="ac-secondary-button" onClick={onTick} disabled={isTickingAutomation} type="button">
            <RefreshCw size={15} className={isTickingAutomation ? "spin" : ""} />
            {isTickingAutomation ? "Processando..." : "Rodar Tick Agora"}
          </button>
          <button className="ac-primary-button" onClick={onSave} disabled={isSavingAutomation || !draft} type="button">
            <CheckCircle2 size={15} />
            {isSavingAutomation ? "Salvando..." : "Salvar Configuração"}
          </button>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Últimos Jobs e Syncs" icon={Activity} />
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

      {automationError ? <InlineError title="Falha na automação" message={automationError} /> : null}
    </div>
  );
*/
}

function ManualTab({
  status,
  memory,
  preview,
  projects,
  snapshots,
  importantMessages,
  chatThreads,
  chatMessages,
  automationStatus,
}: {
  status: ObserverStatus | null;
  memory: MemoryCurrent | null;
  preview: MemoryAnalysisPreview | null;
  projects: ProjectMemory[];
  snapshots: MemorySnapshot[];
  importantMessages: ImportantMessage[];
  chatThreads: ChatThread[];
  chatMessages: ChatMessage[];
  automationStatus: AutomationStatus | null;
}) {
  return (
    <div className="page-stack">
      <Card>
        <SectionTitle title="O Que É Este Site" icon={Brain} />
        <div className="manual-grid">
          <div className="manual-list">
            <p>O AuraCore conecta o WhatsApp, retém apenas chats diretos, monta memória consolidada, organiza projetos, registra atividade e permite conversar com a IA usando esse contexto.</p>
            <p>O backend é FastAPI. O Supabase guarda mensagens diretas, snapshots, persona, projetos, chat, automação e atividade persistida.</p>
            <p>O `deepseek-reasoner` cuida da trilha crítica da memória. O Groq fica no chat pessoal para resposta rápida.</p>
          </div>
          <div className="manual-list">
            <p>Observador: {status?.connected ? "conectado" : "desconectado"}.</p>
            <p>Memória atual: {memory?.last_analyzed_at ? `ativa desde ${formatShortDateTime(memory.last_analyzed_at)}` : "ainda não consolidada"}.</p>
            <p>Projetos salvos: {projects.length}. Snapshots: {snapshots.length}. Threads de chat: {chatThreads.length}. Mensagens na thread ativa: {chatMessages.length}.</p>
            <p>Preview atual: {preview ? `${preview.selected_message_count}/${preview.available_message_count} mensagens cabem agora` : "ainda não carregado"}.</p>
          </div>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Mapa Das Abas" icon={Database} />
        <div className="manual-grid">
          <ManualInfoCard title="Visão Geral" text="Resumo rápido do estado da memória, sinais úteis e atalhos para entrar no fluxo principal." />
          <ManualInfoCard title="Observador" text="Conecta o WhatsApp, mostra QR, estado da instância e saúde do gateway." />
          <ManualInfoCard title="Memória" text="Controla puxar mensagens, primeira análise, melhoria incremental e refinamento da memória salva." />
          <ManualInfoCard title="Importantes" text="Mostra o cofre de mensagens duráveis, alimentado automaticamente pela IA após cada análise." />
          <ManualInfoCard title="Projetos" text="Mostra o que a IA consolidou como frentes reais, próximos passos, evidências e público." />
          <ManualInfoCard title="Chat Pessoal" text="Agora trabalha com múltiplas threads: você separa estratégia, rotina e projetos sem perder a memória central." />
          <ManualInfoCard title="Atividade / Automação" text="Mostra syncs, decisões, jobs, runs de modelo, thresholds e orçamento operacional." />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Fluxo Completo" icon={Terminal} />
        <div className="manual-sequence">
          <ManualStep title="1. Conectar o observador" text="Leia o QR na aba Observador. Depois disso o gateway começa a ler só conversas diretas úteis." />
          <ManualStep title="2. Puxar mensagens" text="O botão de releitura força uma nova sincronização do WhatsApp. Grupos, broadcast e newsletter não devem subir para o Supabase." />
          <ManualStep title="3. Fazer a primeira análise" text="Quando ainda não existe memória base, a IA monta o primeiro retrato consolidado do dono." />
          <ManualStep title="4. Salvar mensagens duráveis" text="Ao fim de cada análise, a IA separa acessos, projetos, dinheiro, riscos e fatos operacionais que merecem virar memória longa." />
          <ManualStep title="5. Melhorar memória" text="Depois da base inicial, novas mensagens são cruzadas com snapshots, projetos e chat para atualizar o perfil." />
          <ManualStep title="6. Conversar por threads" text="Use threads separadas no chat para manter assuntos distintos, sem perder a memória central do dono." />
          <ManualStep title="7. Acompanhar automação" text="A aba de atividade mostra o que foi sincronizado, o que a IA decidiu e quanto custou." />
        </div>
      </Card>

      <Card>
        <SectionTitle title="Botões Principais" icon={Zap} />
        <div className="manual-grid">
          <ManualInfoCard title="Puxar Novas Mensagens do WhatsApp" text="Relê os chats diretos mais recentes e atualiza a retenção operacional no Supabase." />
          <ManualInfoCard title="Fazer Primeira Análise" text="Cria a primeira base de memória quando o perfil ainda está vazio." />
          <ManualInfoCard title="Ler Novas Mensagens e Melhorar Memória" text="Usa mensagens novas mais memória já salva para reforçar ou corrigir o retrato do dono." />
          <ManualInfoCard title="Refinar Memória Já Salva" text="Não relê o WhatsApp; apenas limpa e melhora o que já foi consolidado." />
          <ManualInfoCard title="Nova Conversa" text="Cria uma nova thread de chat para separar assuntos. Todas usam a memória central, mas cada uma mantém histórico próprio." />
          <ManualInfoCard title="Rodar Tick Agora" text="Força o backend a fechar syncs ociosos, registrar decisões e processar a fila automática." />
        </div>
      </Card>

      <Card>
        <SectionTitle title="O Que Vai Para O Supabase" icon={Server} />
        <div className="manual-list">
          <p>`mensagens`: apenas conversas diretas aproveitáveis.</p>
          <p>`important_messages`: o cofre de mensagens importantes, revisado diariamente pelo backend.</p>
          <p>`persona`, `memory_snapshots`, `project_memories`: memória consolidada e evolução do perfil.</p>
          <p>`chat_threads` e `chat_messages`: múltiplas threads do chat pessoal com a IA.</p>
          <p>`wa_sync_runs`, `automation_decisions`, `analysis_jobs`, `model_runs`: auditoria operacional da automação.</p>
        </div>
      </Card>

      <Card>
        <SectionTitle title="O Que Nunca Deve Subir" icon={XCircle} />
        <div className="manual-list">
          <p>Mensagens de grupo.</p>
          <p>Status, newsletter, broadcast e lixo sem texto útil.</p>
          <p>Cadeia de pensamento bruta do modelo. A interface mostra só resumo operacional.</p>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Estado Atual Da Operação" icon={Activity} />
        <div className="manual-grid">
          <ManualInfoCard
            title="Memória"
            text={
              memory?.last_analyzed_at
                ? `Última consolidação em ${formatDateTime(memory.last_analyzed_at)}.`
                : "Ainda sem consolidação inicial."
            }
          />
          <ManualInfoCard
            title="Preview"
            text={
              preview
                ? `Leitura atual caberia em ${preview.selected_message_count} mensagens, com score ${preview.recommendation_score}/100 e should_analyze=${preview.should_analyze ? "true" : "false"}.`
                : "Preview ainda não calculado."
            }
          />
          <ManualInfoCard
            title="Mensagens Importantes"
            text={
              importantMessages.length > 0
                ? `${importantMessages.length} item(ns) ativos no cofre, com revisão diária automática após a virada do dia.`
                : "Nenhuma mensagem importante ativa ainda."
            }
          />
          <ManualInfoCard
            title="Threads"
            text={`Há ${chatThreads.length} thread(s) salvas no chat e ${chatMessages.length} mensagem(ns) na thread atualmente aberta.`}
          />
          <ManualInfoCard
            title="Automação"
            text={
              automationStatus
                ? `${automationStatus.queued_jobs_count} job(s) na fila e custo diário de ${formatUsd(automationStatus.daily_cost_usd)}.`
                : "Status da automação ainda não carregado."
            }
          />
        </div>
      </Card>
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
