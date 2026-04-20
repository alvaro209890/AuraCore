import { StatusLine, getActivityToneLabel, getSnapshotCoverageTone } from '../../connection-dashboard';
import type { MemoryActivity } from '../../connection-dashboard';
import { AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Clock, Database, Fingerprint, GitBranch, MessageSquare, Pause, Play, RefreshCw, Send, Settings, Sparkles, Terminal, Trash2, Users, X, Zap, Cpu } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useMemo, useState } from 'react';
import type { MemoryCurrent, MemorySnapshot } from '@/lib/api';

export default function ActivityTab({
  agentState,
  steps,
  logs,
  memory,
  memoryActivity = null,
  latestSnapshot,
  projectsCount,
  snapshotsCount,
  automationStatus,
  automationError,
  isClearingDatabase,
  onClearDatabase,
  embedded = false,
}: {
  agentState: any;
  steps: any[];
  logs: any[];
  memory: MemoryCurrent | null;
  memoryActivity?: MemoryActivity | null;
  latestSnapshot: MemorySnapshot | null;
  projectsCount: number;
  snapshotsCount: number;
  automationStatus: any;
  automationError: string | null;
  isClearingDatabase: boolean;
  onClearDatabase: () => void;
  embedded?: boolean;
}) {
  const [activitySubTab, setActivitySubTab] = useState<"overview" | "persist" | "logs">("overview");
  const memoryReady = hasEstablishedMemory(memory, latestSnapshot);
  const resolvedIntent = agentState.intent ?? (memoryReady ? "improve_memory" : "first_analysis");
  const latestDecision = memoryActivity?.decisions?.[0] ?? automationStatus?.decisions?.[0] ?? null;
  const latestSyncRun = memoryActivity?.sync_runs[0] ?? automationStatus?.sync_runs[0] ?? null;
  const latestJob = memoryActivity?.jobs[0] ?? automationStatus?.jobs?.[0] ?? null;
  const displayedJob = latestJob ?? null;
  const latestModelRun = memoryActivity?.model_runs[0] ?? automationStatus?.model_runs?.[0] ?? null;
  const queuedJobsCount = memoryActivity?.queued_jobs_count ?? automationStatus?.queued_jobs_count ?? 0;
  const runningJobId = memoryActivity?.running_job_id ?? automationStatus?.running_job_id ?? null;
  const hasPendingDatabaseWork = Boolean(
    agentState.running ||
    runningJobId ||
    queuedJobsCount,
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
        latestJob: displayedJob,
        latestModelRun,
      }),
    [agentState, displayedJob, latestDecision, latestModelRun, latestSyncRun],
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
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-hero-card">
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
      </div>

      {/* === OVERVIEW sub-tab === */}
      {activitySubTab === "overview" ? (
        <>
          <div className="activity-insight-grid">
            <MemorySignalCard
              label="Ação atual"
              value={displayedJob ? getIntentTitle(displayedJob.intent as any) : getIntentTitle(resolvedIntent)}
              meta={displayedJob ? `${displayedJob.status} via ${displayedJob.trigger_source}` : memoryReady ? "Memória base já existe" : "Ainda sem base consolidada"}
              
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
              value={String(queuedJobsCount)}
              meta={
                runningJobId
                  ? "Existe 1 job em execução agora"
                  : automationStatus || memoryActivity
                    ? "Nenhum job rodando agora"
                    : "Aguardando status"
              }
              tone="amber"
            />
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-thinking-card">
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
          </div>
        </>
      ) : null}

      {/* === PERSIST sub-tab === */}
      {activitySubTab === "persist" ? (
        <>
          <div className="activity-insight-grid">
            <MemorySignalCard
              label="Fila"
              value={String(queuedJobsCount)}
              meta={runningJobId ? "Há job rodando agora" : "Sem job em execução"}
            />
            <MemorySignalCard
              label="Base já conhecida"
              value={`${formatTokenCount(snapshotsCount)} snapshots / ${formatTokenCount(projectsCount)} projetos`}
              meta={memoryReady ? "Pronta para uso nas operações" : "Primeira base ainda será criada"}
              tone="zinc"
            />
            <MemorySignalCard
              label="Último processamento"
              value={displayedJob ? displayedJob.status : "..."}
              meta={
                displayedJob
                  ? `${getIntentTitle(displayedJob.intent as any)} • ${formatShortDateTime(displayedJob.created_at)}`
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
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
            </div>
          </div>
        </>
      ) : null}

      {/* === LOGS sub-tab === */}
      {activitySubTab === "logs" ? (
        <div className="activity-lab-grid">
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-lab-hero">
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
                <strong>{agentState.running ? "Processando lote" : displayedJob?.status ?? "Sem execucao"}</strong>
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
          </div>

          <div className="activity-lab-columns">
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-trace-card">
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
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-trace-card">
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
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-lab-logs">
            <div className="activity-lab-log-head">
              <SectionTitle title="Stream do Backend" icon={Terminal} />
              <span className={`micro-status micro-status-${agentState.running ? "indigo" : "zinc"}`}>
                {agentState.running ? "stream ativo" : "aguardando"}
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
                <div className="activity-thought-empty">
                  <Terminal size={18} />
                  <p>Sem logs recentes por enquanto.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm activity-maintenance-card">
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
          className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-red-500 text-zinc-50 hover:bg-red-500/90 h-9 px-4 py-2"
          onClick={onClearDatabase}
          disabled={isClearingDatabase || hasPendingDatabaseWork}
          type="button"
          title={hasPendingDatabaseWork ? "Aguarde a fila e os jobs terminarem antes de apagar o banco." : "Apagar todos os dados salvos no banco local"}
        >
          <Trash2 size={15} />
          {isClearingDatabase ? "Apagando banco..." : "Excluir todo o banco"}
        </button>
      </div>

      {automationError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na automação</strong><p>{automationError}</p></div> : null}
    </div>
  );
}
