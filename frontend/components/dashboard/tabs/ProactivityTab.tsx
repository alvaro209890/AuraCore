import type { Dispatch, ReactNode, SetStateAction } from 'react';
import {
  BadgeCheck,
  BellRing,
  Check,
  CheckCircle2,
  Clock3,
  Gauge,
  LayoutGrid,
  MessageSquare,
  Moon,
  RefreshCw,
  Send,
  Sparkles,
  SunMedium,
  TimerReset,
  X,
} from 'lucide-react';
import {
  formatConfidence,
  formatRelativeTime,
  formatShortDateTime,
  getProactiveCategoryLabel,
  getProactiveDecisionLabel,
  getProactiveStatusLabel,
  SectionTitle,
  truncateText,
} from '../../connection-dashboard';
import type { ProactiveCandidate, ProactiveDeliveryLog, ProactivePreferences } from '@/lib/api';
import type { ProactivityDraft } from '../../connection-dashboard';

type Tone = 'emerald' | 'indigo' | 'amber';

type CategoryField = {
  key: keyof ProactivePreferences;
  title: string;
  description: string;
  tone: Tone;
};

const CATEGORY_FIELDS: CategoryField[] = [
  {
    key: 'followups_enabled',
    title: 'Follow-ups',
    description: 'Retomada leve de promessas, respostas e pontos pendentes.',
    tone: 'indigo',
  },
  {
    key: 'projects_enabled',
    title: 'Projetos',
    description: 'Nudges para frentes abertas, próximos passos e travas acumuladas.',
    tone: 'amber',
  },
  {
    key: 'routine_enabled',
    title: 'Rotina',
    description: 'Ajustes de foco, carga e ritmo ao longo do dia.',
    tone: 'indigo',
  },
  {
    key: 'morning_digest_enabled',
    title: 'Digest manhã',
    description: 'Resumo breve para abrir o dia com agenda e prioridades.',
    tone: 'emerald',
  },
  {
    key: 'night_digest_enabled',
    title: 'Digest noite',
    description: 'Fechamento com pendências, replanejamento e captura do dia.',
    tone: 'amber',
  },
];

const INTENSITY_OPTIONS: Array<{
  value: ProactivePreferences['intensity'];
  title: string;
  description: string;
  tone: Tone;
}> = [
  {
    value: 'conservative',
    title: 'Conservadora',
    description: 'Interrompe menos e prioriza contexto forte.',
    tone: 'emerald',
  },
  {
    value: 'moderate',
    title: 'Moderada',
    description: 'Equilíbrio entre iniciativa e discrição.',
    tone: 'indigo',
  },
  {
    value: 'high',
    title: 'Alta',
    description: 'Mais presença, com mais oportunidades ao longo do dia.',
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

function formatWindowLabel(start: string, end: string): string {
  if (!start || !end) {
    return 'Janela incompleta';
  }

  const [startHour = '0', startMinute = '0'] = start.split(':');
  const [endHour = '0', endMinute = '0'] = end.split(':');
  const startTotal = Number(startHour) * 60 + Number(startMinute);
  const endTotal = Number(endHour) * 60 + Number(endMinute);

  if (Number.isNaN(startTotal) || Number.isNaN(endTotal)) {
    return 'Janela inválida';
  }

  let duration = endTotal - startTotal;
  if (duration <= 0) {
    duration += 24 * 60;
  }
  const hours = Math.floor(duration / 60);
  const minutes = duration % 60;

  if (hours && minutes) {
    return `${hours}h ${minutes}min de silêncio`;
  }
  if (hours) {
    return `${hours}h de silêncio`;
  }
  return `${minutes}min de silêncio`;
}

export default function ProactivityTab({
  proactiveSettings,
  proactivityDraft,
  proactiveCandidates,
  proactiveDeliveries,
  proactiveError,
  isSavingProactivity,
  isTickingProactivity,
  onDraftChange,
  onSave,
  onTick,
  onDismissCandidate,
  onConfirmCandidate,
  onCompleteCandidate,
}: {
  proactiveSettings: ProactivePreferences | null;
  proactivityDraft: ProactivityDraft | null;
  proactiveCandidates: ProactiveCandidate[];
  proactiveDeliveries: ProactiveDeliveryLog[];
  proactiveError: string | null;
  isSavingProactivity: boolean;
  isTickingProactivity: boolean;
  onDraftChange: Dispatch<SetStateAction<ProactivityDraft | null>>;
  onSave: () => void;
  onTick: () => void;
  onDismissCandidate: (candidateId: string) => void;
  onConfirmCandidate: (candidateId: string) => void;
  onCompleteCandidate: (candidateId: string) => void;
}) {
  const effectiveSettings: ProactivePreferences = {
    user_id: proactiveSettings?.user_id ?? '',
    enabled: proactiveSettings?.enabled ?? false,
    intensity: proactiveSettings?.intensity ?? 'moderate',
    quiet_hours_start: proactiveSettings?.quiet_hours_start ?? '22:00',
    quiet_hours_end: proactiveSettings?.quiet_hours_end ?? '08:00',
    max_unsolicited_per_day: proactiveSettings?.max_unsolicited_per_day ?? 4,
    min_interval_minutes: proactiveSettings?.min_interval_minutes ?? 90,
    agenda_enabled: proactiveSettings?.agenda_enabled ?? true,
    followups_enabled: proactiveSettings?.followups_enabled ?? true,
    projects_enabled: proactiveSettings?.projects_enabled ?? true,
    routine_enabled: proactiveSettings?.routine_enabled ?? true,
    morning_digest_enabled: proactiveSettings?.morning_digest_enabled ?? true,
    night_digest_enabled: proactiveSettings?.night_digest_enabled ?? true,
    morning_digest_time: proactiveSettings?.morning_digest_time ?? '08:30',
    night_digest_time: proactiveSettings?.night_digest_time ?? '20:30',
    updated_at: proactiveSettings?.updated_at ?? '',
    ...(proactivityDraft ?? {}),
  };
  const activeCandidates = proactiveCandidates.filter(
    (candidate) => candidate.status !== 'done' && candidate.status !== 'dismissed',
  );
  const lastDelivery = proactiveDeliveries[0] ?? null;
  const enabledCategoriesCount = [
    effectiveSettings.followups_enabled,
    effectiveSettings.projects_enabled,
    effectiveSettings.routine_enabled,
    effectiveSettings.morning_digest_enabled,
    effectiveSettings.night_digest_enabled,
  ].filter(Boolean).length;
  const quietWindowSummary = formatWindowLabel(
    effectiveSettings.quiet_hours_start,
    effectiveSettings.quiet_hours_end,
  );
  const digestSummary = `${effectiveSettings.morning_digest_time} / ${effectiveSettings.night_digest_time}`;
  const proactiveCadenceSummary =
    effectiveSettings.max_unsolicited_per_day > 0
      ? `${effectiveSettings.max_unsolicited_per_day} iniciativas com pausa mínima de ${effectiveSettings.min_interval_minutes} min`
      : 'Sem iniciativas espontâneas liberadas';

  const patchDraft = (patch: Partial<ProactivePreferences>): void => {
    onDraftChange((previous: any) => ({
      ...(proactiveSettings ?? {}),
      ...(previous ?? {}),
      ...patch,
    }));
  };

  return (
    <div className="page-stack">
      <div className="projects-hero-card proactivity-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Sparkles size={14} />
            Radar proativo
          </div>
          <h3>Mensagens espontâneas com presença calibrada, janela de silêncio real e categorias bem separadas.</h3>
          <p>
            A configuração abaixo deixa explícito quando o Orion pode iniciar conversa, quanto espaço ele ocupa ao
            longo do dia e quais rituais automáticos entram no radar.
          </p>
          <div className="ops-hero-actions">
            <button
              className="ops-hero-button ops-hero-button-ghost"
              disabled={isTickingProactivity}
              onClick={onTick}
              type="button"
            >
              <RefreshCw className={isTickingProactivity ? 'spin' : ''} size={16} />
              {isTickingProactivity ? 'Reavaliando radar...' : 'Rodar tick agora'}
            </button>
            <button
              className="ops-hero-button ops-hero-button-primary"
              disabled={isSavingProactivity || !proactivityDraft}
              onClick={onSave}
              type="button"
            >
              <Check size={16} />
              {isSavingProactivity ? 'Salvando ajustes...' : 'Salvar configuração'}
            </button>
          </div>
        </div>

        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Status</span>
            <strong>{effectiveSettings.enabled ? 'Ativa' : 'Desligada'}</strong>
            <small>{`Intensidade ${effectiveSettings.intensity}`}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Silêncio</span>
            <strong>{quietWindowSummary}</strong>
            <small>{`${effectiveSettings.quiet_hours_start} → ${effectiveSettings.quiet_hours_end}`}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Fila viva</span>
            <strong>{activeCandidates.length}</strong>
            <small>
              {activeCandidates[0]
                ? getProactiveCategoryLabel(activeCandidates[0].category)
                : 'Nenhum candidato aguardando agora'}
            </small>
          </div>
          <div className="projects-hero-metric">
            <span>Última entrega</span>
            <strong>{lastDelivery ? getProactiveDecisionLabel(lastDelivery.decision) : 'Sem envio'}</strong>
            <small>{lastDelivery ? formatShortDateTime(lastDelivery.created_at) : 'Sem histórico recente'}</small>
          </div>
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle
          title="Arquitetura da Proatividade"
          icon={Sparkles}
          action={
            effectiveSettings.updated_at ? (
              <span className="micro-badge">{formatShortDateTime(effectiveSettings.updated_at)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Os painéis abaixo foram separados por presença, silêncio, cadência e rituais. A intenção é enxergar a lógica
          operacional do motor antes mesmo de mexer em cada campo.
        </p>

        <div className="ops-panel-grid">
          <ControlPanel
            description="Liga o motor e define quão cedo ele pode tomar a frente numa conversa não solicitada."
            eyebrow="Presença"
            icon={<Gauge size={18} />}
            title="Tom de iniciativa"
            tone="emerald"
          >
            <div className="ops-toggle-stack">
              <ToggleCard
                checked={effectiveSettings.enabled}
                description="Permite mensagens não solicitadas com score, cooldown e checagem de momento."
                onChange={(checked) => patchDraft({ enabled: checked })}
                title="Ativar proatividade"
                tone="emerald"
              />
            </div>

            <SettingField
              hint="Troca o perfil do motor sem depender de texto livre. O estado fica explícito e comparável."
              label="Intensidade operacional"
            >
              <div className="ops-pill-grid">
                {INTENSITY_OPTIONS.map((option) => {
                  const isActive = effectiveSettings.intensity === option.value;
                  return (
                    <button
                      key={option.value}
                      className={`ops-pill-button${isActive ? ` ops-pill-button-active ops-pill-button-active-${option.tone}` : ''}`}
                      onClick={() => patchDraft({ intensity: option.value })}
                      type="button"
                    >
                      <strong>{option.title}</strong>
                      <span>{option.description}</span>
                    </button>
                  );
                })}
              </div>
            </SettingField>

            <div className="ops-stat-ribbon">
              <div className="ops-stat-chip">
                <span>Categorias ligadas</span>
                <strong>{enabledCategoriesCount}</strong>
              </div>
              <div className="ops-stat-chip">
                <span>Cadência atual</span>
                <strong>{effectiveSettings.max_unsolicited_per_day}/dia</strong>
              </div>
            </div>
          </ControlPanel>

          <ControlPanel
            description="Horários sensíveis deixam de parecer um campo avulso e passam a funcionar como janela operacional real."
            eyebrow="Silêncio"
            icon={<Moon size={18} />}
            title="Janela de retenção"
            tone="indigo"
          >
            <div className="ops-form-grid ops-form-grid-dual">
              <SettingField hint="Hora em que o motor para de sugerir nudges leves." label="Silêncio inicial">
                <InputShell hint="Início do recolhimento automático." icon={<Moon size={16} />} tone="indigo">
                  <input
                    className="ops-input"
                    onChange={(event) => patchDraft({ quiet_hours_start: event.target.value })}
                    type="time"
                    value={effectiveSettings.quiet_hours_start}
                  />
                </InputShell>
              </SettingField>

              <SettingField hint="Hora em que mensagens leves voltam a competir por atenção." label="Silêncio final">
                <InputShell hint="Retorno seguro da janela ativa." icon={<SunMedium size={16} />} tone="amber">
                  <input
                    className="ops-input"
                    onChange={(event) => patchDraft({ quiet_hours_end: event.target.value })}
                    type="time"
                    value={effectiveSettings.quiet_hours_end}
                  />
                </InputShell>
              </SettingField>
            </div>

            <div className="ops-inline-note">
              <strong>{quietWindowSummary}</strong>
              <span>
                Durante esse período, o sistema segura iniciativas leves e respeita só casos mais fortes do motor.
              </span>
            </div>
          </ControlPanel>
        </div>

        <div className="ops-panel-grid">
          <ControlPanel
            description="Esses campos controlam o volume diário e o espaço mínimo entre nudges para evitar insistência artificial."
            eyebrow="Cadência"
            icon={<TimerReset size={18} />}
            title="Pressão máxima por dia"
            tone="amber"
          >
            <div className="ops-form-grid ops-form-grid-dual">
              <SettingField hint="Teto absoluto de mensagens espontâneas no mesmo dia." label="Máximo por dia">
                <InputShell hint="Teto bruto de iniciativas." icon={<BellRing size={16} />} tone="amber">
                  <input
                    className="ops-input"
                    min="1"
                    onChange={(event) =>
                      patchDraft({ max_unsolicited_per_day: Math.max(1, Number(event.target.value) || 1) })
                    }
                    step="1"
                    type="number"
                    value={effectiveSettings.max_unsolicited_per_day}
                  />
                </InputShell>
              </SettingField>

              <SettingField hint="Cooldown entre dois envios não solicitados." label="Intervalo mínimo (min)">
                <InputShell hint="Tempo de respiro entre toques." icon={<Clock3 size={16} />} tone="indigo">
                  <input
                    className="ops-input"
                    min="15"
                    onChange={(event) =>
                      patchDraft({ min_interval_minutes: Math.max(15, Number(event.target.value) || 15) })
                    }
                    step="5"
                    type="number"
                    value={effectiveSettings.min_interval_minutes}
                  />
                </InputShell>
              </SettingField>
            </div>

            <div className="ops-inline-note">
              <strong>{proactiveCadenceSummary}</strong>
              <span>
                O objetivo aqui é limitar a presença do agente sem perder as oportunidades que realmente valem a pena.
              </span>
            </div>
          </ControlPanel>

          <ControlPanel
            description="Os digests ficam agrupados num mesmo bloco porque funcionam como ritual de abertura e fechamento do dia."
            eyebrow="Rituais"
            icon={<SunMedium size={18} />}
            title="Manhã e noite"
            tone="emerald"
          >
            <div className="ops-form-grid ops-form-grid-dual">
              <SettingField hint="Horário padrão do resumo de abertura do dia." label="Digest da manhã">
                <InputShell hint="Resumo de prioridades e agenda." icon={<SunMedium size={16} />} tone="emerald">
                  <input
                    className="ops-input"
                    onChange={(event) => patchDraft({ morning_digest_time: event.target.value })}
                    type="time"
                    value={effectiveSettings.morning_digest_time}
                  />
                </InputShell>
              </SettingField>

              <SettingField hint="Horário padrão do fechamento com retomada." label="Digest da noite">
                <InputShell hint="Fechamento do dia e replanejamento." icon={<Moon size={16} />} tone="amber">
                  <input
                    className="ops-input"
                    onChange={(event) => patchDraft({ night_digest_time: event.target.value })}
                    type="time"
                    value={effectiveSettings.night_digest_time}
                  />
                </InputShell>
              </SettingField>
            </div>

            <div className="ops-stat-ribbon">
              <div className="ops-stat-chip">
                <span>Digest manhã</span>
                <strong>{effectiveSettings.morning_digest_enabled ? 'Ligado' : 'Desligado'}</strong>
              </div>
              <div className="ops-stat-chip">
                <span>Digest noite</span>
                <strong>{effectiveSettings.night_digest_enabled ? 'Ligado' : 'Desligado'}</strong>
              </div>
              <div className="ops-stat-chip">
                <span>Horários</span>
                <strong>{digestSummary}</strong>
              </div>
            </div>
          </ControlPanel>
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle title="Matriz de Categorias" icon={LayoutGrid} />
        <p className="support-copy">
          Cada cartão abaixo ativa um eixo real da proatividade. Lembretes de agenda continuam sendo tratados na aba
          de Agenda, para não misturar o motor proativo com compromissos formais.
        </p>
        <div className="ops-toggle-grid">
          {CATEGORY_FIELDS.map((field) => (
            <ToggleCard
              key={field.key}
              checked={Boolean(effectiveSettings[field.key])}
              description={field.description}
              onChange={(checked) => patchDraft({ [field.key]: checked } as Partial<ProactivePreferences>)}
              title={field.title}
              tone={field.tone}
            />
          ))}
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle title="Candidatos Ativos" icon={MessageSquare} />
        {activeCandidates.length === 0 ? (
          <div className="ops-empty-state">
            Nenhuma sugestão ativa no momento. O motor proativo ainda não encontrou motivo forte para interromper.
          </div>
        ) : (
          <div className="project-list-modern">
            {activeCandidates.map((candidate) => (
              <div key={candidate.id} className="project-card-modern proactivity-candidate-card">
                <div className="ops-list-card-head">
                  <div className="ops-list-card-title">
                    <Sparkles size={16} />
                    <strong>{candidate.title}</strong>
                  </div>
                  <div className="project-card-actions">
                    <span className="micro-status micro-status-indigo">
                      {getProactiveCategoryLabel(candidate.category)}
                    </span>
                    <span className="micro-status micro-status-amber">
                      {getProactiveStatusLabel(candidate.status)}
                    </span>
                  </div>
                </div>

                <p className="support-copy">{candidate.summary}</p>

                <div className="ops-meta-grid">
                  <div className="ops-meta-card">
                    <span>Confiança</span>
                    <strong>{formatConfidence(candidate.confidence)}</strong>
                    <small>Prioridade {candidate.priority}/100</small>
                  </div>
                  <div className="ops-meta-card">
                    <span>Prazo</span>
                    <strong>{candidate.due_at ? formatShortDateTime(candidate.due_at) : 'Sem prazo'}</strong>
                    <small>
                      {candidate.cooldown_until
                        ? `Cooldown até ${formatShortDateTime(candidate.cooldown_until)}`
                        : 'Sem cooldown ativo'}
                    </small>
                  </div>
                  <div className="ops-meta-card">
                    <span>Último nudge</span>
                    <strong>
                      {candidate.last_nudged_at ? formatRelativeTime(candidate.last_nudged_at) : 'Ainda não enviado'}
                    </strong>
                    <small>Atualizado {formatRelativeTime(candidate.updated_at)}</small>
                  </div>
                </div>

                <div className="ops-hero-actions">
                  <button
                    className="ops-hero-button ops-hero-button-ghost"
                    onClick={() => onDismissCandidate(candidate.id)}
                    type="button"
                  >
                    <X size={15} />
                    Dispensar
                  </button>
                  <button
                    className="ops-hero-button ops-hero-button-ghost"
                    onClick={() => onConfirmCandidate(candidate.id)}
                    type="button"
                  >
                    <BadgeCheck size={15} />
                    Confirmar
                  </button>
                  <button
                    className="ops-hero-button ops-hero-button-primary"
                    onClick={() => onCompleteCandidate(candidate.id)}
                    type="button"
                  >
                    <CheckCircle2 size={15} />
                    Concluir
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="ops-surface">
        <SectionTitle title="Entregas Recentes" icon={Send} />
        {proactiveDeliveries.length === 0 ? (
          <div className="ops-empty-state">Ainda não existe histórico de entrega da proatividade.</div>
        ) : (
          <div className="ops-dual-grid">
            {proactiveDeliveries.map((delivery) => (
              <div key={delivery.id} className="ops-list-card">
                <div className="ops-list-card-head">
                  <div className="ops-list-card-title">
                    <Send size={16} />
                    <strong>{getProactiveCategoryLabel(delivery.category)}</strong>
                  </div>
                  <span className="micro-status micro-status-indigo">
                    {getProactiveDecisionLabel(delivery.decision)}
                  </span>
                </div>

                <div className="ops-list-row-meta">
                  <span>Score {delivery.score.toFixed(2)}</span>
                  <span>{formatShortDateTime(delivery.created_at)}</span>
                </div>

                <p className="support-copy">{delivery.reason_text || delivery.reason_code}</p>
                {delivery.message_text ? (
                  <div className="ops-quote-box">“{truncateText(delivery.message_text, 220)}”</div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      {proactiveError ? (
        <div className="danger-box">
          <h4>Falha na proatividade</h4>
          <p>{proactiveError}</p>
        </div>
      ) : null}
    </div>
  );
}
