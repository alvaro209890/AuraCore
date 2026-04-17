import { ManualInfoCard } from '../../connection-dashboard';
import { Activity, AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Clock, Database, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Send, Settings, Terminal, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
type AutomationDraft = any;
import type { } from '@/lib/api';

export default function AutomationTab({
  automationStatus,
  automationDraft,
  automationError,
  isSavingAutomation,
  isTickingAutomation,
  onDraftChange,
  onSave,
  onTick,
}: {
  automationStatus: any;
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
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
          <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onTick} disabled={isTickingAutomation} type="button">
            <RefreshCw size={15} className={isTickingAutomation ? "spin" : ""} />
            {isTickingAutomation ? "Processando..." : "Rodar Tick Agora"}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
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
                ? `${getIntentTitle(operationalLatestJob.intent as any)} ficou em ${operationalLatestJob.status} e foi criado em ${formatShortDateTime(operationalLatestJob.created_at)}.`
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
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Historico Recente" icon={Clock} />
        <div className="automation-history-grid">
          <div className="activity-persist-block">
            <strong>Jobs recentes</strong>
            {(automationStatus?.jobs ?? []).slice(0, 4).map((job: any) => (
              <div key={job.id} className="activity-meta-row">
                <span>{getIntentTitle(job.intent as any)}</span>
                <span>{job.status}</span>
                <span>{formatShortDateTime(job.created_at)}</span>
              </div>
            ))}
          </div>
          <div className="activity-persist-block">
            <strong>Syncs recentes</strong>
            {(automationStatus?.sync_runs ?? []).slice(0, 4).map((syncRun: any) => (
              <div key={syncRun.id} className="activity-meta-row">
                <span>{syncRun.trigger}</span>
                <span>{syncRun.status}</span>
                <span>{formatShortDateTime(syncRun.started_at)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {automationError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na automacao</strong><p>{automationError}</p></div> : null}
    </div>
  );
}
