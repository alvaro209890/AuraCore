import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { BadgeCheck, Check, CheckCircle2, MessageSquare, RefreshCw, Send, Sparkles, X } from 'lucide-react';
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

type CategoryField = {
  key: keyof ProactivePreferences;
  title: string;
  description: string;
  tone: 'emerald' | 'indigo' | 'amber';
};

const CATEGORY_FIELDS: CategoryField[] = [
  {
    key: 'agenda_enabled',
    title: 'Agenda',
    description: 'Lembretes, follow-up de compromisso e preparação de horários.',
    tone: 'emerald',
  },
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

function SettingField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="ops-field">
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
    effectiveSettings.agenda_enabled,
    effectiveSettings.followups_enabled,
    effectiveSettings.projects_enabled,
    effectiveSettings.routine_enabled,
    effectiveSettings.morning_digest_enabled,
    effectiveSettings.night_digest_enabled,
  ].filter(Boolean).length;

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
          <h3>Mensagens espontâneas com critério, janela de silêncio e categorias bem separadas.</h3>
          <p>
            A configuração abaixo deixa explícito quando o Orion pode iniciar conversa, o quanto ele pode insistir e
            quais rotinas entram no radar ao longo do dia.
          </p>
          <div className="hero-actions">
            <button
              className="ac-button ac-button-outline"
              disabled={isTickingProactivity}
              onClick={onTick}
              type="button"
            >
              <RefreshCw className={isTickingProactivity ? 'spin' : ''} size={15} />
              {isTickingProactivity ? 'Reavaliando...' : 'Rodar tick agora'}
            </button>
            <button
              className="ac-button ac-button-primary"
              disabled={isSavingProactivity || !proactivityDraft}
              onClick={onSave}
              type="button"
            >
              <Check size={15} />
              {isSavingProactivity ? 'Salvando...' : 'Salvar configuração'}
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
            <span>Categorias</span>
            <strong>{enabledCategoriesCount}</strong>
            <small>Agenda, follow-up, projetos, rotina e digests</small>
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
          title="Configuração da Proatividade"
          icon={Sparkles}
          action={
            effectiveSettings.updated_at ? (
              <span className="micro-badge">{formatShortDateTime(effectiveSettings.updated_at)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Os controles abaixo definem janela de silêncio, intensidade, frequência máxima e os tipos de nudges que o
          sistema pode produzir.
        </p>

        <div className="ops-toggle-grid">
          <ToggleCard
            checked={effectiveSettings.enabled}
            description="Permite mensagens não solicitadas com score, cooldown e checagem de momento."
            onChange={(checked) => patchDraft({ enabled: checked })}
            title="Ativar proatividade"
            tone="emerald"
          />
          <ToggleCard
            checked={effectiveSettings.morning_digest_enabled}
            description="Mantém o resumo da manhã como parte do ritual automático."
            onChange={(checked) => patchDraft({ morning_digest_enabled: checked })}
            title="Digest matinal"
            tone="indigo"
          />
          <ToggleCard
            checked={effectiveSettings.night_digest_enabled}
            description="Mantém o fechamento do dia com retomada e replanejamento."
            onChange={(checked) => patchDraft({ night_digest_enabled: checked })}
            title="Digest noturno"
            tone="amber"
          />
        </div>

        <div className="ops-form-shell">
          <div className="ops-form-grid">
            <SettingField hint="Controla o quanto o agente pode insistir antes de esperar." label="Intensidade">
              <select
                className="ops-select"
                onChange={(event) =>
                  patchDraft({ intensity: event.target.value as ProactivePreferences['intensity'] })
                }
                value={effectiveSettings.intensity}
              >
                <option value="conservative">Conservadora</option>
                <option value="moderate">Moderada</option>
                <option value="high">Alta</option>
              </select>
            </SettingField>

            <SettingField hint="Início do período em que nudges normais ficam retidos." label="Silêncio começa">
              <input
                className="ops-input"
                onChange={(event) => patchDraft({ quiet_hours_start: event.target.value })}
                type="time"
                value={effectiveSettings.quiet_hours_start}
              />
            </SettingField>

            <SettingField hint="Fim da janela em que os envios leves podem voltar." label="Silêncio termina">
              <input
                className="ops-input"
                onChange={(event) => patchDraft({ quiet_hours_end: event.target.value })}
                type="time"
                value={effectiveSettings.quiet_hours_end}
              />
            </SettingField>

            <SettingField hint="Teto de iniciativas espontâneas no mesmo dia." label="Máximo por dia">
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ max_unsolicited_per_day: Math.max(0, Number(event.target.value) || 0) })
                }
                step="1"
                type="number"
                value={effectiveSettings.max_unsolicited_per_day}
              />
            </SettingField>

            <SettingField hint="Cooldown mínimo entre dois envios não solicitados." label="Intervalo mínimo (min)">
              <input
                className="ops-input"
                min="0"
                onChange={(event) =>
                  patchDraft({ min_interval_minutes: Math.max(0, Number(event.target.value) || 0) })
                }
                step="5"
                type="number"
                value={effectiveSettings.min_interval_minutes}
              />
            </SettingField>

            <SettingField hint="Horário padrão do resumo de abertura do dia." label="Digest da manhã">
              <input
                className="ops-input"
                onChange={(event) => patchDraft({ morning_digest_time: event.target.value })}
                type="time"
                value={effectiveSettings.morning_digest_time}
              />
            </SettingField>

            <SettingField hint="Horário padrão do resumo de fechamento." label="Digest da noite">
              <input
                className="ops-input"
                onChange={(event) => patchDraft({ night_digest_time: event.target.value })}
                type="time"
                value={effectiveSettings.night_digest_time}
              />
            </SettingField>
          </div>
        </div>

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

                <div className="hero-actions">
                  <button
                    className="ac-button ac-button-outline"
                    onClick={() => onDismissCandidate(candidate.id)}
                    type="button"
                  >
                    <X size={15} />
                    Dispensar
                  </button>
                  <button
                    className="ac-button ac-button-outline"
                    onClick={() => onConfirmCandidate(candidate.id)}
                    type="button"
                  >
                    <BadgeCheck size={15} />
                    Confirmar
                  </button>
                  <button
                    className="ac-button ac-button-primary"
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
