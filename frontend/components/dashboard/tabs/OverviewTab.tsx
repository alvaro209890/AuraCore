import { StatusLine, SignalBlock, formatState, getSnapshotCoverageTone, getSnapshotCoverageLabel, resolveOverviewNextAction } from '../../connection-dashboard';
import type { InsightMetric } from '../../connection-dashboard';
import {   Activity, AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Database, Eye, Fingerprint, FolderGit2, GitBranch, MessageSquare, Pause, Play, RefreshCw, Send, Server, Settings, Terminal, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useState } from 'react';
import type {  MemoryCurrent, MemorySnapshot, ObserverStatus, ProjectMemory , MemoryStatus } from '@/lib/api';;

export default function OverviewTab({
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
      title: "Usar nas operacoes",
      detail: hasMemoryBase
        ? "Os projetos ja podem reaproveitar a memoria consolidada."
        : "Depois da primeira leitura, o sistema passa a trabalhar com base no perfil salvo.",
      state: hasMemoryBase ? "ok" : "pending",
    },
  ];

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm hero-panel overview-hero-panel">
        <div className="hero-copy">
          <div className="hero-kicker">
            <Brain size={14} />
            Painel operacional
          </div>
          <h3>O que importa agora: conectar, captar sinais suficientes e montar uma memória útil sem adivinhação.</h3>
          <p>Use esta tela para entender rapidamente em que etapa o sistema está, o que já foi consolidado e qual é o próximo passo recomendado.</p>
        </div>
        <div className="hero-actions">
          <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" onClick={handlePrimaryAction} type="button">
            <Play size={15} />
            {nextAction.buttonLabel}
          </button>
          <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onGoToMemory} type="button">
            <Database size={15} />
            Abrir Memória
          </button>
          <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onGoToMemory} type="button">
            <Activity size={15} />
            Ver Pipeline
          </button>
        </div>
      </div>

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
            <div className={`bg-white rounded-xl border border-zinc-200 p-6 shadow-sm overview-action-card overview-action-${nextAction.tone}`}>
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
                <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" onClick={handlePrimaryAction} type="button">
                  <ChevronRight size={15} />
                  {nextAction.buttonLabel}
                </button>
                <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onGoToMemory} type="button">
                  <Activity size={15} />
                  Acompanhar pipeline
                </button>
              </div>
            </div>

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

            <div className={`bg-white rounded-xl border border-zinc-200 p-6 shadow-sm ${!memory?.life_summary?.trim() ? "overview-empty-card" : ""}`}>
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
            </div>
          </div>

          <div className="overview-side-stack">
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm overview-journey-card">
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
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm overview-context-card">
              <SectionTitle title="Leitura Operacional" icon={Server} />
              <div className="overview-context-list">
                <StatusLine label="Numero conectado" value={status?.owner_number ?? "Sem numero"} tone="indigo" />
                <StatusLine label="Ultima consolidacao" value={latestUpdateLabel} tone="amber" />
                <StatusLine label="Cobertura do ultimo snapshot" value={latestSnapshot ? `${latestSnapshot.coverage_score}/100` : "Sem snapshot"} tone={latestSnapshotCoverageTone} />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {subTab === "mapping" ? (
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
        </div>
      ) : null}

      {subTab === "signals" ? (
        <div className="dual-column-grid">
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm score-card-modern">
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
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
                  <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onGoToMemory} type="button">
                    <Activity size={15} />
                    Abrir Pipeline
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {connectionError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na conexão</strong><p>{connectionError}</p></div> : null}
      {memoryError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na memória</strong><p>{memoryError}</p></div> : null}
    </div>
  );
}
