import { resolvePendingAnalysisJob } from '../../connection-dashboard';
import type { MemoryActivity } from '../../connection-dashboard';
import { SignalBlock, formatDateTime, getActivityToneLabel, formatState, getSnapshotCoverageTone, getSnapshotCoverageLabel, formatSnapshotDirectionMix } from '../../connection-dashboard';
import { AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Clock, Database, FileText, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Send, Settings, Sparkles, Terminal, Users, X, Zap, Activity, Cpu } from 'lucide-react';
import ActivityTab from './ActivityTab';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useState } from 'react';
import type {  MemoryCurrent, MemorySnapshot , MemoryStatus } from '@/lib/api';;

export default function MemoryTab({
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
  agentState: any;
  steps: any[];
  logs: any[];
  projectsCount: number;
  snapshotsCount: number;
  automationStatus: any;
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
  const memoryActivityJobs = memoryActivity?.jobs ?? [];
  const automationJobs = automationStatus?.jobs ?? [];
  const activityJobs = memoryActivityJobs.length > 0 ? memoryActivityJobs : automationJobs;
  const automationPendingJob =
    activityJobs.find((job: any) => (
      (job.status === "queued" || job.status === "running")
      && (job.intent === "first_analysis" || job.intent === "improve_memory")
    )) ?? null;
  const latestAutomationDecision = memoryActivity?.decisions?.[0] ?? automationStatus?.decisions?.[0] ?? null;
  const currentJob = memoryStatus?.current_job ?? automationPendingJob ?? null;
  const latestCompletedJob =
    memoryStatus?.latest_completed_job
    ?? activityJobs.find((job: any) => job.status === "succeeded" || job.status === "failed")
    ?? null;
  const canExecuteAnalysis = memoryStatus?.can_execute_analysis ?? false;
  const currentJobIsPending = currentJob?.status === "queued" || currentJob?.status === "running";
  const autoInitialSyncInProgress = !memoryReady && (memoryStatus?.sync_in_progress ?? false);
  const hasPendingJob = currentJobIsPending || !!queuedJobId || autoInitialSyncInProgress;
  const displayedJob = resolvePendingAnalysisJob({
    currentJob,
    activity: memoryActivity,
    queuedJobId,
  }) ?? memoryActivity?.jobs[0] ?? latestCompletedJob;
  const latestSyncRun = memoryActivity?.sync_runs[0] ?? null;
  const latestModelRun = memoryActivity?.model_runs[0] ?? null;
  const latestSnapshotCoverageTone = getSnapshotCoverageTone(latestSnapshot);
  const traceItems = buildActivityTrace({
    agentState,
    latestSyncRun,
    latestDecision: null,
    latestJob: displayedJob,
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
  const automaticJobNotice = currentJobIsPending && currentJob?.trigger_source === "automation"
    ? currentJob.status === "queued"
      ? currentJob.intent === "first_analysis"
        ? "A primeira análise automática já está na fila do backend."
        : "A atualização automática já está na fila do backend."
      : currentJob.intent === "first_analysis"
        ? "A primeira análise automática está em andamento agora."
        : "A análise automática está em andamento agora."
    : null;
  const latestAutomationNotice = !automaticJobNotice && latestAutomationDecision
    ? latestAutomationDecision.explanation
    : null;
  const blockedReason = autoInitialSyncInProgress
    ? "O backend ainda está fechando a coleta inicial automática do WhatsApp. A primeira análise será colocada na fila sozinha assim que esse lote for persistido."
    : currentJobIsPending
    ? currentJob.intent === "first_analysis"
      ? currentJob.status === "queued"
        ? currentJob.trigger_source === "automation"
          ? "A primeira analise ja foi colocada na fila automatica pelo backend."
          : "A primeira analise ja foi colocada na fila."
        : currentJob.trigger_source === "automation"
          ? "A primeira analise ja foi iniciada automaticamente pelo backend usando o lote inicial do WhatsApp."
          : "A primeira analise ja esta em andamento."
      : currentJob.status === "queued"
        ? currentJob.trigger_source === "automation"
          ? "Ja existe uma atualizacao automatica de memoria na fila."
          : "Ja existe uma atualizacao de memoria na fila."
        : currentJob.trigger_source === "automation"
          ? "Ja existe uma atualizacao automatica de memoria em andamento."
          : "Ja existe uma atualizacao de memoria em andamento."
    : !canExecuteAnalysis
      ? !memoryReady
        ? "Ainda nao ha mensagens textuais novas disponiveis para criar a base inicial."
        : pendingNewMessages > 0
          ? latestAutomationNotice ?? "Ainda nao ha sinal suficiente para rodar o proximo lote manual."
          : "Ainda nao ha mensagens novas pendentes para atualizar a memoria."
      : null;

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm memory-shell-card">
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
      </div>

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
                  ? `${getIntentTitle(currentJob.intent as any)} • ${formatShortDateTime(currentJob.created_at)}`
                  : "Nenhuma analise em execucao no momento"
              }
              tone="amber"
            />
            <MemorySignalCard
              label="Ultimo job concluido"
              value={latestCompletedJob ? formatState(latestCompletedJob.status) : "--"}
              meta={
                latestCompletedJob
                  ? `${getIntentTitle(latestCompletedJob.intent as any)} • ${formatShortDateTime(latestCompletedJob.finished_at ?? latestCompletedJob.created_at)}`
                  : "Nenhuma execucao concluida ainda"
              }
              tone="emerald"
            />
          </div>

          <div className="memory-surface-grid">
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm memory-panel-card">
              <SectionTitle title="Ações" icon={Zap} />
              {!memoryReady ? (
                <div className="memory-inline-stack">
                  <p className="support-copy">
                    A primeira analise mistura recencia, diversidade de contatos e mensagens do proprio dono para montar uma base inicial menos enviesada.
                  </p>
                  {automaticJobNotice ? <p className="support-copy">{automaticJobNotice}</p> : null}
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
                  {automaticJobNotice ? <p className="support-copy">{automaticJobNotice}</p> : null}
                  <button
                    className="ac-primary-button"
                    onClick={onImproveMemory}
                    disabled={agentState.running || hasPendingJob || !canExecuteAnalysis}
                    type="button"
                  >
                    <Sparkles size={15} />
                    {currentJobIsPending
                      ? currentJob.status === "queued"
                        ? currentJob.trigger_source === "automation"
                          ? "Analise automatica na fila..."
                          : "Atualizacao na fila..."
                        : currentJob.trigger_source === "automation"
                          ? "Analise automatica em andamento..."
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
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm memory-panel-card">
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
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm memory-panel-card">
            <div className="activity-lab-log-head">
              <SectionTitle title="Stream de Logs" icon={Terminal} />
              <span className={`micro-status micro-status-${agentState.running || hasPendingJob ? "indigo" : "zinc"}`}>
                {agentState.running || hasPendingJob ? "auto-refresh ligado" : "monitorando"}
              </span>
            </div>
            <div className="activity-log-stream">
              {displayedLogs.length > 0 ? (
                displayedLogs.map((log, index) => (
                  <div key={index} className="activity-log-item">
                    <span className="activity-log-time">{formatShortDateTime(log.timestamp)}</span>
                    <span className={`activity-log-level activity-log-level-${(log.level ?? "info").toLowerCase()}`}>{log.level ?? "info"}</span>
                    <span className="activity-log-message">{log.message}</span>
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
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Memoria Atual do Dono" icon={Fingerprint} />
            <p className="lead-copy">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Nenhum resumo consolidado ainda. Assim que a primeira leitura rodar, este bloco vira a visao mais util do dono para futuras atualizacoes manuais."}
            </p>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
          </div>
        </>
      ) : null}

      {memorySubTab === "snapshot" ? (
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
        </div>
      ) : null}

      {memorySubTab === "pipeline" ? (
        <ActivityTab
          agentState={agentState}
          steps={steps}
          logs={logs}
          memory={memory}
          memoryActivity={memoryActivity}
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

      {memoryError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na memoria</strong><p>{memoryError}</p></div> : null}
    </div>
  );
}
