import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { Activity, Brain, Check, Clock3, Coins, RefreshCw, Settings2, Zap } from 'lucide-react';
import {
  formatShortDateTime,
  formatTokenCount,
  getIntentTitle,
  SectionTitle,
} from '../../connection-dashboard';
import type { AutomationDecision, AutomationSettings, AutomationStatus } from '@/lib/api';

type AutomationDraft = Partial<AutomationSettings>;

type ToggleField = {
  key: keyof AutomationSettings;
  title: string;
  description: string;
  tone: 'emerald' | 'indigo' | 'amber';
};

const TOGGLE_FIELDS: ToggleField[] = [
  {
    key: 'auto_sync_enabled',
    title: 'Auto sync',
    description: 'Puxa mensagens novas sem depender de ação manual.',
    tone: 'emerald',
  },
  {
    key: 'auto_analyze_enabled',
    title: 'Auto análise',
    description: 'Permite criar jobs automaticamente quando o score justificar.',
    tone: 'indigo',
  },
  {
    key: 'auto_refine_enabled',
    title: 'Refino incremental',
    description: 'Aprimora memória e contexto depois que a base inicial já existe.',
    tone: 'amber',
  },
];

function SettingField({
  label,
  hint,
  full = false,
  children,
}: {
  label: string;
  hint?: string;
  full?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`ops-field${full ? ' ops-field-full' : ''}`}>
      <span className="ops-field-label">{label}</span>
      {children}
      {hint ? <span className="ops-field-caption">{hint}</span> : null}
    </label>
  );
}

function ToggleCard({
  title,
  description,
  checked,
  onChange,
  tone,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  tone: 'emerald' | 'indigo' | 'amber';
}) {
  return (
    <label className={`ops-toggle-card ops-toggle-card-${tone}`}>
      <div className="ops-toggle-copy">
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <span className="ops-toggle-switch">
        <input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
        <span className="ops-toggle-slider" />
      </span>
    </label>
  );
}

function HistoryItem({
  title,
  meta,
  detail,
  badge,
}: {
  title: string;
  meta: string;
  detail: string;
  badge?: string;
}) {
  return (
    <div className="ops-history-item">
      <div className="ops-history-head">
        <div>
          <strong>{title}</strong>
          <span>{meta}</span>
        </div>
        {badge ? <span className="micro-status micro-status-indigo">{badge}</span> : null}
      </div>
      <p>{detail}</p>
    </div>
  );
}

function buildAutomationDefaults(settings?: AutomationSettings | null): AutomationSettings {
  return {
    user_id: settings?.user_id ?? '',
    auto_sync_enabled: settings?.auto_sync_enabled ?? true,
    auto_analyze_enabled: settings?.auto_analyze_enabled ?? true,
    auto_refine_enabled: settings?.auto_refine_enabled ?? true,
    min_new_messages_threshold: settings?.min_new_messages_threshold ?? 6,
    stale_hours_threshold: settings?.stale_hours_threshold ?? 12,
    pruned_messages_threshold: settings?.pruned_messages_threshold ?? 2000,
    default_detail_mode: settings?.default_detail_mode ?? 'balanced',
    default_target_message_count: settings?.default_target_message_count ?? 60,
    default_lookback_hours: settings?.default_lookback_hours ?? 168,
    daily_budget_usd: settings?.daily_budget_usd ?? 1.5,
    max_auto_jobs_per_day: settings?.max_auto_jobs_per_day ?? 8,
    updated_at: settings?.updated_at ?? '',
  };
}

function formatDecisionSummary(decision: AutomationDecision): string {
  return `${decision.action} · ${decision.reason_code} · ${decision.selected_message_count} msgs`;
}

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
  automationStatus: AutomationStatus | null;
  automationDraft: any;
  automationError: string | null;
  isSavingAutomation: boolean;
  isTickingAutomation: boolean;
  onDraftChange: Dispatch<SetStateAction<any>>;
  onSave: () => void;
  onTick: () => void;
}) {
  const operationalLatestJob = automationStatus?.jobs?.[0] ?? null;
  const operationalLatestSync = automationStatus?.sync_runs?.[0] ?? null;
  const operationalLatestDecision = automationStatus?.decisions?.[0] ?? null;
  const operationalLatestModelRun = automationStatus?.model_runs?.[0] ?? null;
  const effectiveSettings: AutomationSettings = {
    ...buildAutomationDefaults(automationStatus?.settings),
    ...(automationDraft ?? {}),
  };
  const hasDraft = Boolean(automationDraft);

  const patchDraft = (patch: Partial<AutomationSettings>): void => {
    onDraftChange((previous: any) => ({
      ...buildAutomationDefaults(automationStatus?.settings),
      ...(previous ?? {}),
      ...patch,
    }));
  };

  return (
    <div className="page-stack">
      <div className="projects-hero-card automation-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Settings2 size={14} />
            Loop operacional
          </div>
          <h3>Automação sob controle, com leitura clara do que roda sozinho e do que ainda depende de contexto.</h3>
          <p>
            Esta aba separa configuração, pulso do loop e histórico recente. A ideia é enxergar rapidamente limite,
            cadência e custo antes de deixar o backend agir sozinho.
          </p>
          <div className="hero-actions">
            <button
              className="ac-button ac-button-outline"
              disabled={isTickingAutomation}
              onClick={onTick}
              type="button"
            >
              <RefreshCw className={isTickingAutomation ? 'spin' : ''} size={15} />
              {isTickingAutomation ? 'Rodando tick...' : 'Rodar tick agora'}
            </button>
            <button
              className="ac-button ac-button-primary"
              disabled={isSavingAutomation || !hasDraft}
              onClick={onSave}
              type="button"
            >
              <Check size={15} />
              {isSavingAutomation ? 'Salvando...' : 'Salvar configuração'}
            </button>
          </div>
        </div>

        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Fila ativa</span>
            <strong>{automationStatus ? String(automationStatus.queued_jobs_count) : '...'}</strong>
            <small>{automationStatus?.running_job_id ? 'Existe job rodando agora' : 'Nenhum job em execução'}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Jobs hoje</span>
            <strong>{automationStatus ? String(automationStatus.daily_auto_jobs_count) : '...'}</strong>
            <small>Lotes automáticos concluídos no dia</small>
          </div>
          <div className="projects-hero-metric">
            <span>Custo diário</span>
            <strong>{automationStatus ? `$${automationStatus.daily_cost_usd.toFixed(2)}` : '...'}</strong>
            <small>Comparado ao teto configurado</small>
          </div>
          <div className="projects-hero-metric">
            <span>Última decisão</span>
            <strong>{operationalLatestDecision ? operationalLatestDecision.action : 'Sem decisão'}</strong>
            <small>
              {operationalLatestDecision
                ? formatShortDateTime(operationalLatestDecision.created_at)
                : 'Nenhuma decisão persistida ainda'}
            </small>
          </div>
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle
          title="Configuração do Loop"
          icon={Brain}
          action={
            effectiveSettings.updated_at ? (
              <span className="micro-badge">{formatShortDateTime(effectiveSettings.updated_at)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Ajuste o comportamento automático sem perder previsibilidade. Os campos abaixo controlam entrada mínima,
          janela de leitura, teto operacional e profundidade padrão das análises.
        </p>

        <div className="ops-toggle-grid">
          {TOGGLE_FIELDS.map((field) => (
            <ToggleCard
              key={field.key}
              checked={Boolean(effectiveSettings[field.key])}
              description={field.description}
              onChange={(checked) => patchDraft({ [field.key]: checked } as Partial<AutomationSettings>)}
              title={field.title}
              tone={field.tone}
            />
          ))}
        </div>

        <div className="ops-form-shell">
          <div className="ops-form-grid">
            <SettingField
              hint="Quantidade mínima de mensagens novas antes de disparar uma análise econômica."
              label="Novo volume mínimo"
            >
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ min_new_messages_threshold: Math.max(0, Number(event.target.value) || 0) })
                }
                step="1"
                type="number"
                value={effectiveSettings.min_new_messages_threshold}
              />
            </SettingField>

            <SettingField
              hint="Se o contexto estiver velho além disso, o sistema considera uma retomada."
              label="Janela de estagnação (h)"
            >
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ stale_hours_threshold: Math.max(0, Number(event.target.value) || 0) })
                }
                step="1"
                type="number"
                value={effectiveSettings.stale_hours_threshold}
              />
            </SettingField>

            <SettingField
              hint="Quando a fila de pruned messages passa disso, o loop fica mais conservador."
              label="Pruned threshold"
            >
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ pruned_messages_threshold: Math.max(0, Number(event.target.value) || 0) })
                }
                step="50"
                type="number"
                value={effectiveSettings.pruned_messages_threshold}
              />
            </SettingField>

            <SettingField
              hint="Quantidade alvo de mensagens por job automático."
              label="Mensagens por job"
            >
              <input
                className="ops-input"
                min="1"
                onChange={(event) =>
                  patchDraft({ default_target_message_count: Math.max(1, Number(event.target.value) || 1) })
                }
                step="1"
                type="number"
                value={effectiveSettings.default_target_message_count}
              />
            </SettingField>

            <SettingField
              hint="Quantas horas para trás o recorte automático pode olhar."
              label="Lookback padrão (h)"
            >
              <input
                className="ops-input"
                min="1"
                onChange={(event) =>
                  patchDraft({ default_lookback_hours: Math.max(1, Number(event.target.value) || 1) })
                }
                step="1"
                type="number"
                value={effectiveSettings.default_lookback_hours}
              />
            </SettingField>

            <SettingField
              hint="Limite máximo de execuções automáticas no mesmo dia."
              label="Máximo de jobs por dia"
            >
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ max_auto_jobs_per_day: Math.max(0, Number(event.target.value) || 0) })
                }
                step="1"
                type="number"
                value={effectiveSettings.max_auto_jobs_per_day}
              />
            </SettingField>

            <SettingField
              hint="Teto de custo para o orçamento diário do loop."
              label="Budget diário (USD)"
            >
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ daily_budget_usd: Math.max(0, Number(event.target.value) || 0) })
                }
                step="0.1"
                type="number"
                value={effectiveSettings.daily_budget_usd}
              />
            </SettingField>

            <SettingField
              hint="Define quanto detalhe o pipeline pede quando não houver override explícito."
              label="Detalhe padrão"
            >
              <select
                className="ops-select"
                onChange={(event) =>
                  patchDraft({
                    default_detail_mode: event.target.value as AutomationSettings['default_detail_mode'],
                  })
                }
                value={effectiveSettings.default_detail_mode}
              >
                <option value="light">Light</option>
                <option value="balanced">Balanced</option>
                <option value="deep">Deep</option>
              </select>
            </SettingField>
          </div>
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle title="Leitura Operacional" icon={Activity} />
        <div className="ops-history-grid">
          <HistoryItem
            badge={operationalLatestDecision ? operationalLatestDecision.reason_code : undefined}
            detail={
              operationalLatestDecision
                ? `${formatDecisionSummary(operationalLatestDecision)} com score ${operationalLatestDecision.score.toFixed(2)}.`
                : 'Ainda não existe decisão persistida.'
            }
            meta={
              operationalLatestDecision
                ? formatShortDateTime(operationalLatestDecision.created_at)
                : 'Sem decisão recente'
            }
            title="Última decisão"
          />
          <HistoryItem
            badge={operationalLatestJob?.status}
            detail={
              operationalLatestJob
                ? `${getIntentTitle(operationalLatestJob.intent as any)} com ${formatTokenCount(
                    operationalLatestJob.selected_message_count,
                  )} mensagens selecionadas.`
                : 'Nenhum job salvo até agora.'
            }
            meta={operationalLatestJob ? formatShortDateTime(operationalLatestJob.created_at) : 'Sem job recente'}
            title="Último job"
          />
          <HistoryItem
            badge={operationalLatestSync?.status}
            detail={
              operationalLatestSync
                ? `${formatTokenCount(operationalLatestSync.messages_saved_count)} mensagens úteis salvas no último sync.`
                : 'Nenhum sync persistido ainda.'
            }
            meta={operationalLatestSync ? formatShortDateTime(operationalLatestSync.started_at) : 'Sem sync recente'}
            title="Último sync"
          />
          <HistoryItem
            badge={operationalLatestModelRun?.success ? 'ok' : operationalLatestModelRun ? 'falha' : undefined}
            detail={
              operationalLatestModelRun
                ? `${operationalLatestModelRun.provider} em ${operationalLatestModelRun.run_type} com latência ${
                    operationalLatestModelRun.latency_ms ?? 0
                  } ms.`
                : 'Nenhuma rodada de modelo registrada.'
            }
            meta={
              operationalLatestModelRun
                ? formatShortDateTime(operationalLatestModelRun.created_at)
                : 'Sem model run recente'
            }
            title="Última execução de modelo"
          />
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle title="Histórico Recente" icon={Clock3} />
        <div className="ops-dual-grid">
          <div className="ops-list-card">
            <div className="ops-list-card-head">
              <div className="ops-list-card-title">
                <Zap size={16} />
                <strong>Jobs automáticos</strong>
              </div>
              <span className="micro-badge">{(automationStatus?.jobs ?? []).length} registros</span>
            </div>
            <div className="ops-history-stack">
              {(automationStatus?.jobs ?? []).slice(0, 5).map((job) => (
                <div key={job.id} className="ops-list-row">
                  <div>
                    <strong>{getIntentTitle(job.intent as any)}</strong>
                    <span>{formatShortDateTime(job.created_at)}</span>
                  </div>
                  <div className="ops-list-row-meta">
                    <span>{job.status}</span>
                    <span>{formatTokenCount(job.selected_message_count)} msgs</span>
                  </div>
                </div>
              ))}
              {!automationStatus?.jobs?.length ? (
                <div className="ops-empty-state">Nenhum job automático persistido ainda.</div>
              ) : null}
            </div>
          </div>

          <div className="ops-list-card">
            <div className="ops-list-card-head">
              <div className="ops-list-card-title">
                <RefreshCw size={16} />
                <strong>Syncs recentes</strong>
              </div>
              <span className="micro-badge">{(automationStatus?.sync_runs ?? []).length} registros</span>
            </div>
            <div className="ops-history-stack">
              {(automationStatus?.sync_runs ?? []).slice(0, 5).map((syncRun) => (
                <div key={syncRun.id} className="ops-list-row">
                  <div>
                    <strong>{syncRun.trigger}</strong>
                    <span>{formatShortDateTime(syncRun.started_at)}</span>
                  </div>
                  <div className="ops-list-row-meta">
                    <span>{syncRun.status}</span>
                    <span>{formatTokenCount(syncRun.messages_saved_count)} úteis</span>
                  </div>
                </div>
              ))}
              {!automationStatus?.sync_runs?.length ? (
                <div className="ops-empty-state">Nenhum sync recente persistido.</div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="ops-dual-grid">
          <div className="ops-list-card">
            <div className="ops-list-card-head">
              <div className="ops-list-card-title">
                <Brain size={16} />
                <strong>Decisões</strong>
              </div>
              <span className="micro-badge">{(automationStatus?.decisions ?? []).length} registros</span>
            </div>
            <div className="ops-history-stack">
              {(automationStatus?.decisions ?? []).slice(0, 5).map((decision) => (
                <div key={decision.id} className="ops-list-row">
                  <div>
                    <strong>{decision.action}</strong>
                    <span>{decision.reason_code}</span>
                  </div>
                  <div className="ops-list-row-meta">
                    <span>{decision.score.toFixed(2)}</span>
                    <span>{formatShortDateTime(decision.created_at)}</span>
                  </div>
                </div>
              ))}
              {!automationStatus?.decisions?.length ? (
                <div className="ops-empty-state">Sem decisões registradas até agora.</div>
              ) : null}
            </div>
          </div>

          <div className="ops-list-card">
            <div className="ops-list-card-head">
              <div className="ops-list-card-title">
                <Coins size={16} />
                <strong>Modelo e custo</strong>
              </div>
              <span className="micro-badge">
                teto ${effectiveSettings.daily_budget_usd.toFixed(2)}
              </span>
            </div>
            <div className="ops-history-stack">
              {(automationStatus?.model_runs ?? []).slice(0, 5).map((run) => (
                <div key={run.id} className="ops-list-row">
                  <div>
                    <strong>{run.provider}</strong>
                    <span>{run.model_name}</span>
                  </div>
                  <div className="ops-list-row-meta">
                    <span>{run.success ? 'ok' : 'falha'}</span>
                    <span>{run.estimated_cost_usd ? `$${run.estimated_cost_usd.toFixed(3)}` : 'sem custo'}</span>
                  </div>
                </div>
              ))}
              {!automationStatus?.model_runs?.length ? (
                <div className="ops-empty-state">Nenhuma execução de modelo persistida.</div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {automationError ? (
        <div className="danger-box">
          <h4>Falha na automação</h4>
          <p>{automationError}</p>
        </div>
      ) : null}
    </div>
  );
}
