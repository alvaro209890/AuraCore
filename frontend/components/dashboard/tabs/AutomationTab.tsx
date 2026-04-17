import type { Dispatch, ReactNode, SetStateAction } from 'react';
import {
  Activity,
  BarChart3,
  Brain,
  Check,
  Clock3,
  Coins,
  RefreshCw,
  Search,
  Settings2,
  Shield,
  Sparkles,
  Zap,
} from 'lucide-react';
import {
  formatShortDateTime,
  formatTokenCount,
  getIntentTitle,
  SectionTitle,
} from '../../connection-dashboard';
import type { AutomationDecision, AutomationSettings, AutomationStatus } from '@/lib/api';

type Tone = 'emerald' | 'indigo' | 'amber';

type ToggleField = {
  key: keyof AutomationSettings;
  title: string;
  description: string;
  tone: Tone;
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

const DETAIL_MODE_OPTIONS: Array<{
  value: AutomationSettings['default_detail_mode'];
  title: string;
  description: string;
  tone: Tone;
}> = [
  {
    value: 'light',
    title: 'Light',
    description: 'Mais econômico e direto.',
    tone: 'emerald',
  },
  {
    value: 'balanced',
    title: 'Balanced',
    description: 'Leitura padrão para operação diária.',
    tone: 'indigo',
  },
  {
    value: 'deep',
    title: 'Deep',
    description: 'Mais profundidade quando a janela justificar.',
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
    <div className={`ops-field${full ? ' ops-field-full' : ''}`}>
      <span className="ops-field-label">{label}</span>
      {children}
      {hint ? <span className="ops-field-caption">{hint}</span> : null}
    </div>
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
  tone: Tone;
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

function ControlPanel({
  eyebrow,
  title,
  description,
  tone,
  icon,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  tone: Tone;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={`ops-control-panel ops-control-panel-${tone}`}>
      <div className="ops-control-head">
        <div className="ops-control-copy">
          <span className="ops-control-kicker">{eyebrow}</span>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
        <div className="ops-control-icon">{icon}</div>
      </div>
      {children}
    </section>
  );
}

function InputShell({
  icon,
  tone = 'indigo',
  hint,
  children,
}: {
  icon: ReactNode;
  tone?: Tone;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className={`ops-input-shell ops-input-shell-${tone}`}>
      <span className="ops-input-shell-icon">{icon}</span>
      <div className="ops-input-shell-body">
        {children}
        {hint ? <span className="ops-input-shell-hint">{hint}</span> : null}
      </div>
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
  const budgetUsage = effectiveSettings.daily_budget_usd
    ? Math.min(
        999,
        Math.round(((automationStatus?.daily_cost_usd ?? 0) / Math.max(effectiveSettings.daily_budget_usd, 0.0001)) * 100),
      )
    : 0;
  const remainingJobs = Math.max(
    0,
    effectiveSettings.max_auto_jobs_per_day - (automationStatus?.daily_auto_jobs_count ?? 0),
  );

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
          <h3>Automação com governança visual, thresholds legíveis e cadência clara antes de qualquer job rodar.</h3>
          <p>
            Esta aba agora separa o pulso do loop, os gatilhos de entrada, a janela padrão de análise e o teto diário
            de custo e volume.
          </p>
          <div className="ops-hero-actions">
            <button
              className="ops-hero-button ops-hero-button-ghost"
              disabled={isTickingAutomation}
              onClick={onTick}
              type="button"
            >
              <RefreshCw className={isTickingAutomation ? 'spin' : ''} size={16} />
              {isTickingAutomation ? 'Rodando tick...' : 'Rodar tick agora'}
            </button>
            <button
              className="ops-hero-button ops-hero-button-primary"
              disabled={isSavingAutomation || !hasDraft}
              onClick={onSave}
              type="button"
            >
              <Check size={16} />
              {isSavingAutomation ? 'Salvando ajustes...' : 'Salvar configuração'}
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
            <small>{`${remainingJobs} restantes dentro do teto`}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Custo diário</span>
            <strong>{automationStatus ? `$${automationStatus.daily_cost_usd.toFixed(2)}` : '...'}</strong>
            <small>{`${budgetUsage}% do budget configurado`}</small>
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
          title="Governança da Automação"
          icon={Brain}
          action={
            effectiveSettings.updated_at ? (
              <span className="micro-badge">{formatShortDateTime(effectiveSettings.updated_at)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Os blocos abaixo tratam o loop como operação de produção: o que liga, o que dispara, até onde pode ir e quão
          profunda fica a leitura automática.
        </p>

        <div className="ops-panel-grid">
          <ControlPanel
            description="Esses toggles controlam as camadas do pipeline. O bloco agora ficou explícito e menos parecido com um formulário técnico cru."
            eyebrow="Estados"
            icon={<Shield size={18} />}
            title="O que roda sozinho"
            tone="emerald"
          >
            <div className="ops-toggle-stack">
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
          </ControlPanel>

          <ControlPanel
            description="Resumo operacional do loop para leitura rápida: fila, custo, budget e capacidade diária restante."
            eyebrow="Pulso"
            icon={<BarChart3 size={18} />}
            title="Leitura instantânea"
            tone="indigo"
          >
            <div className="ops-stat-ribbon">
              <div className="ops-stat-chip">
                <span>Fila</span>
                <strong>{automationStatus ? automationStatus.queued_jobs_count : 0}</strong>
              </div>
              <div className="ops-stat-chip">
                <span>Budget</span>
                <strong>{`${budgetUsage}%`}</strong>
              </div>
              <div className="ops-stat-chip">
                <span>Jobs restantes</span>
                <strong>{remainingJobs}</strong>
              </div>
            </div>
            <div className="ops-inline-note">
              <strong>
                {effectiveSettings.daily_budget_usd > 0
                  ? `Teto de $${effectiveSettings.daily_budget_usd.toFixed(2)} por dia`
                  : 'Budget diário zerado'}
              </strong>
              <span>
                {operationalLatestJob
                  ? `Último job: ${getIntentTitle(operationalLatestJob.intent as any)} em ${formatShortDateTime(operationalLatestJob.created_at)}.`
                  : 'Ainda não existe job recente persistido para comparação.'}
              </span>
            </div>
          </ControlPanel>
        </div>

        <div className="ops-panel-grid">
          <ControlPanel
            description="Thresholds de entrada ficaram agrupados para facilitar leitura de sensibilidade do pipeline."
            eyebrow="Gatilhos"
            icon={<Zap size={18} />}
            title="Quando vale abrir um job"
            tone="amber"
          >
            <div className="ops-form-grid ops-form-grid-triple">
              <SettingField
                hint="Quantidade mínima de mensagens novas antes de disparar uma análise econômica."
                label="Novo volume mínimo"
              >
                <InputShell hint="Entrada mínima para justificar custo." icon={<Sparkles size={16} />} tone="amber">
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
                </InputShell>
              </SettingField>

              <SettingField
                hint="Se o contexto estiver velho além disso, o sistema considera uma retomada."
                label="Janela de estagnação (h)"
              >
                <InputShell hint="Quanto tempo o contexto pode ficar parado." icon={<Clock3 size={16} />} tone="indigo">
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
                </InputShell>
              </SettingField>

              <SettingField
                hint="Quando a fila de pruned messages passa disso, o loop fica mais conservador."
                label="Pruned threshold"
              >
                <InputShell hint="Freio de segurança para contexto inflado." icon={<Activity size={16} />} tone="emerald">
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
                </InputShell>
              </SettingField>
            </div>
          </ControlPanel>

          <ControlPanel
            description="Esse bloco controla o tamanho da leitura e a profundidade padrão usada quando não houver override explícito."
            eyebrow="Janela"
            icon={<Search size={18} />}
            title="Escopo da leitura automática"
            tone="indigo"
          >
            <div className="ops-form-grid ops-form-grid-dual">
              <SettingField hint="Quantidade alvo de mensagens por job automático." label="Mensagens por job">
                <InputShell hint="Tamanho típico do recorte." icon={<Activity size={16} />} tone="indigo">
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
                </InputShell>
              </SettingField>

              <SettingField hint="Quantas horas para trás o recorte automático pode olhar." label="Lookback padrão (h)">
                <InputShell hint="Janela máxima do contexto padrão." icon={<Clock3 size={16} />} tone="amber">
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
                </InputShell>
              </SettingField>
            </div>

            <SettingField
              hint="Troca a profundidade padrão sem depender de select simples demais. O estado fica mais legível."
              label="Detalhe padrão"
            >
              <div className="ops-pill-grid">
                {DETAIL_MODE_OPTIONS.map((option) => {
                  const isActive = effectiveSettings.default_detail_mode === option.value;
                  return (
                    <button
                      key={option.value}
                      className={`ops-pill-button${isActive ? ` ops-pill-button-active ops-pill-button-active-${option.tone}` : ''}`}
                      onClick={() => patchDraft({ default_detail_mode: option.value })}
                      type="button"
                    >
                      <strong>{option.title}</strong>
                      <span>{option.description}</span>
                    </button>
                  );
                })}
              </div>
            </SettingField>
          </ControlPanel>
        </div>

        <div className="ops-panel-grid">
          <ControlPanel
            description="Budget e limite diário agora aparecem no mesmo bloco para evitar que um campo pareça isolado do outro."
            eyebrow="Budget"
            icon={<Coins size={18} />}
            title="Teto financeiro e de volume"
            tone="emerald"
          >
            <div className="ops-form-grid ops-form-grid-dual">
              <SettingField hint="Teto de custo para o orçamento diário do loop." label="Budget diário (USD)">
                <InputShell hint="Custo total permitido por dia." icon={<Coins size={16} />} tone="emerald">
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
                </InputShell>
              </SettingField>

              <SettingField hint="Limite máximo de execuções automáticas no mesmo dia." label="Máximo de jobs por dia">
                <InputShell hint="Teto de jobs automáticos diários." icon={<Zap size={16} />} tone="amber">
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
                </InputShell>
              </SettingField>
            </div>
            <div className="ops-inline-note">
              <strong>{`${remainingJobs} jobs ainda cabem hoje dentro do limite configurado`}</strong>
              <span>
                {automationStatus
                  ? `Custo acumulado hoje: $${automationStatus.daily_cost_usd.toFixed(3)}.`
                  : 'Sem status atual disponível para custo acumulado.'}
              </span>
            </div>
          </ControlPanel>
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
              <span className="micro-badge">teto ${effectiveSettings.daily_budget_usd.toFixed(2)}</span>
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
