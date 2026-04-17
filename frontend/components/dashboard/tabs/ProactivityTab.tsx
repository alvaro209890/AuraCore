import type { ProactivityDraft } from '../../connection-dashboard';
import type { ProactivePreferences, ProactiveCandidate, ProactiveDeliveryLog } from '@/lib/api';
import {   AlertCircle, BadgeCheck, BarChart3, Brain, Check, CheckCircle2, ChevronRight, Database, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Send, Settings, Sparkles, Terminal, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';

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
  onDraftChange: React.Dispatch<React.SetStateAction<ProactivityDraft | null>>;
  onSave: () => void;
  onTick: () => void;
  onDismissCandidate: (candidateId: string) => void;
  onConfirmCandidate: (candidateId: string) => void;
  onCompleteCandidate: (candidateId: string) => void;
}) {
  const effectiveSettings: ProactivePreferences = {
    user_id: proactiveSettings?.user_id ?? "",
    enabled: proactiveSettings?.enabled ?? false,
    intensity: proactiveSettings?.intensity ?? "moderate",
    quiet_hours_start: proactiveSettings?.quiet_hours_start ?? "22:00",
    quiet_hours_end: proactiveSettings?.quiet_hours_end ?? "08:00",
    max_unsolicited_per_day: proactiveSettings?.max_unsolicited_per_day ?? 4,
    min_interval_minutes: proactiveSettings?.min_interval_minutes ?? 90,
    agenda_enabled: proactiveSettings?.agenda_enabled ?? true,
    followups_enabled: proactiveSettings?.followups_enabled ?? true,
    projects_enabled: proactiveSettings?.projects_enabled ?? true,
    routine_enabled: proactiveSettings?.routine_enabled ?? true,
    morning_digest_enabled: proactiveSettings?.morning_digest_enabled ?? true,
    night_digest_enabled: proactiveSettings?.night_digest_enabled ?? true,
    morning_digest_time: proactiveSettings?.morning_digest_time ?? "08:30",
    night_digest_time: proactiveSettings?.night_digest_time ?? "20:30",
    updated_at: proactiveSettings?.updated_at ?? "",
    ...(proactivityDraft ?? {}),
  };
  const activeCandidates = proactiveCandidates.filter((candidate) => candidate.status !== "done" && candidate.status !== "dismissed");
  const lastDelivery = proactiveDeliveries[0] ?? null;
  const enabledCategoriesCount = [
    effectiveSettings?.agenda_enabled,
    effectiveSettings?.followups_enabled,
    effectiveSettings?.projects_enabled,
    effectiveSettings?.routine_enabled,
    effectiveSettings?.morning_digest_enabled,
    effectiveSettings?.night_digest_enabled,
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
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle
          title="Proatividade do Assistente"
          icon={Sparkles}
          action={
            effectiveSettings.updated_at ? (
              <span className="micro-badge">{formatShortDateTime(effectiveSettings.updated_at)}</span>
            ) : null
          }
        />
        <p className="support-copy">
          Aqui voce controla quando o Orion pode abrir conversa sozinho, quais tipos de ajuda entram no radar e com
          qual intensidade o motor proativo pode insistir.
        </p>

        <div className="automation-top-grid">
          <MemorySignalCard
            label="Proatividade"
            value={effectiveSettings.enabled ? "Ativa" : "Desligada"}
            meta={proactiveSettings ? `Intensidade ${effectiveSettings.intensity}` : "Carregando preferencias"}
            
          />
          <MemorySignalCard
            label="Categorias ligadas"
            value={String(enabledCategoriesCount)}
            meta="Agenda, follow-up, projetos, rotina e digests"
            tone="indigo"
          />
          <MemorySignalCard
            label="Fila ativa"
            value={String(activeCandidates.length)}
            meta={activeCandidates[0] ? getProactiveCategoryLabel(activeCandidates[0].category) : "Sem item aguardando"}
            tone="emerald"
          />
          <MemorySignalCard
            label="Ultimo envio"
            value={lastDelivery ? getProactiveDecisionLabel(lastDelivery.decision) : "..."}
            meta={lastDelivery ? formatShortDateTime(lastDelivery.created_at) : "Sem log de entrega"}
            tone="amber"
          />
        </div>

        <div className="hero-actions">
          <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onTick} disabled={isTickingProactivity} type="button">
            <RefreshCw size={15} className={isTickingProactivity ? "spin" : ""} />
            {isTickingProactivity ? "Reavaliando..." : "Rodar Tick Agora"}
          </button>
          <button className="ac-success-button" onClick={onSave} disabled={isSavingProactivity || !proactivityDraft} type="button">
            <Check size={15} />
            {isSavingProactivity ? "Salvando..." : "Salvar Configuração"}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Configuração" icon={Settings} />
        {proactiveSettings ? (
          <div className="page-stack" style={{ gap: "1rem" }}>
            <div className="manual-grid">
              <label className="manual-info-card manual-info-card-emerald" style={{ cursor: "pointer" }}>
                <div className="manual-info-card-content">
                  <strong>Ativar proatividade</strong>
                  <p>Permite mensagens não solicitadas com score, cooldown e horário de silêncio.</p>
                </div>
                <input
                  type="checkbox"
                  checked={effectiveSettings.enabled}
                  onChange={(event) => patchDraft({ enabled: event.target.checked })}
                />
              </label>
              <label className="manual-info-card manual-info-card-indigo">
                <div className="manual-info-card-content">
                  <strong>Intensidade</strong>
                  <p>Controla o quanto o agente pode insistir em nudges e retomadas.</p>
                </div>
                <select
                  value={effectiveSettings.intensity}
                  onChange={(event) => patchDraft({ intensity: event.target.value as ProactivePreferences["intensity"] })}
                  style={{ minWidth: "150px" }}
                >
                  <option value="conservative">Conservadora</option>
                  <option value="moderate">Moderada</option>
                  <option value="high">Alta</option>
                </select>
              </label>
            </div>

            <div className="manual-grid">
              <label className="manual-info-card manual-info-card-zinc">
                <div className="manual-info-card-content">
                  <strong>Silêncio inicial</strong>
                  <p>Horário local em Brasília para começar a segurar nudges normais.</p>
                </div>
                <input
                  type="time"
                  value={effectiveSettings.quiet_hours_start}
                  onChange={(event) => patchDraft({ quiet_hours_start: event.target.value })}
                />
              </label>
              <label className="manual-info-card manual-info-card-zinc">
                <div className="manual-info-card-content">
                  <strong>Silêncio final</strong>
                  <p>Quando o agente pode retomar envios não urgentes.</p>
                </div>
                <input
                  type="time"
                  value={effectiveSettings.quiet_hours_end}
                  onChange={(event) => patchDraft({ quiet_hours_end: event.target.value })}
                />
              </label>
            </div>

            <div className="manual-grid">
              <AutomationNumberField description="" 
                label="Máximo por dia"
                value={effectiveSettings.max_unsolicited_per_day}
                onChange={(value: any) => patchDraft({ max_unsolicited_per_day: Math.max(0, value) })}
              />
              <AutomationNumberField description="" 
                label="Intervalo mínimo em minutos"
                value={effectiveSettings.min_interval_minutes}
                onChange={(value: any) => patchDraft({ min_interval_minutes: Math.max(0, value) })}
              />
            </div>

            <div className="manual-grid">
              {[
                ["agenda_enabled", "Agenda", "Lembretes e preparação de compromisso."],
                ["followups_enabled", "Follow-ups", "Cobrança leve de promessas e respostas pendentes."],
                ["projects_enabled", "Projetos", "Retomada de frentes abertas e próximos passos."],
                ["routine_enabled", "Rotina", "Ajustes leves de foco, carga e organização."],
                ["morning_digest_enabled", "Digest manhã", "Resumo curto para abrir o dia."],
                ["night_digest_enabled", "Digest noite", "Fechamento com pendências e replanejamento."],
              ].map(([field, label, description]) => {
                const checked = Boolean(effectiveSettings[field as keyof ProactivePreferences]);
                return (
                  <label key={field} className="manual-info-card manual-info-card-zinc" style={{ cursor: "pointer" }}>
                    <div className="manual-info-card-content">
                      <strong>{label}</strong>
                      <p>{description}</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => patchDraft({ [field]: event.target.checked } as Partial<ProactivePreferences>)}
                    />
                  </label>
                );
              })}
            </div>

            <div className="manual-grid">
              <label className="manual-info-card manual-info-card-amber">
                <div className="manual-info-card-content">
                  <strong>Digest da manhã</strong>
                  <p>Horário padrão para agenda, focos e risco do dia.</p>
                </div>
                <input
                  type="time"
                  value={effectiveSettings.morning_digest_time}
                  onChange={(event) => patchDraft({ morning_digest_time: event.target.value })}
                />
              </label>
              <label className="manual-info-card manual-info-card-indigo">
                <div className="manual-info-card-content">
                  <strong>Digest da noite</strong>
                  <p>Horário para fechamento e retomada de pendências.</p>
                </div>
                <input
                  type="time"
                  value={effectiveSettings.night_digest_time}
                  onChange={(event) => patchDraft({ night_digest_time: event.target.value })}
                />
              </label>
            </div>
          </div>
        ) : (
          <p className="support-copy">Carregando preferências de proatividade...</p>
        )}
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Candidatos Ativos" icon={MessageSquare} />
        {activeCandidates.length === 0 ? (
          <p className="support-copy">Nenhuma sugestão ativa no momento. O motor proativo ainda não viu motivo forte para incomodar.</p>
        ) : (
          <div className="page-stack" style={{ gap: "0.9rem" }}>
            {activeCandidates.map((candidate) => (
              <div key={candidate.id} className="activity-persist-block">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                    flexWrap: "wrap",
                    alignItems: "center",
                    marginBottom: "0.65rem",
                  }}
                >
                  <div>
                    <strong>{candidate.title}</strong>
                    <p className="support-copy" style={{ marginTop: "0.35rem" }}>{candidate.summary}</p>
                  </div>
                  <span className="micro-badge">{getProactiveStatusLabel(candidate.status)}</span>
                </div>

                <div className="activity-meta-row">
                  <span>{getProactiveCategoryLabel(candidate.category)}</span>
                  <span>Confiança {formatConfidence(candidate.confidence)}</span>
                  <span>Prioridade {candidate.priority}/100</span>
                </div>
                <div className="activity-meta-row">
                  <span>Vence {candidate.due_at ? formatShortDateTime(candidate.due_at) : "sem prazo"}</span>
                  <span>Último nudge {candidate.last_nudged_at ? formatRelativeTime(candidate.last_nudged_at) : "ainda não enviado"}</span>
                  <span>Atualizado {formatRelativeTime(candidate.updated_at)}</span>
                </div>

                <div className="hero-actions" style={{ marginTop: "0.9rem" }}>
                  <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={() => onDismissCandidate(candidate.id)} type="button">
                    <X size={15} />
                    Dispensar
                  </button>
                  <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={() => onConfirmCandidate(candidate.id)} type="button">
                    <BadgeCheck size={15} />
                    Confirmar
                  </button>
                  <button className="ac-success-button" onClick={() => onCompleteCandidate(candidate.id)} type="button">
                    <CheckCircle2 size={15} />
                    Concluir
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Entregas Recentes" icon={Send} />
        {proactiveDeliveries.length === 0 ? (
          <p className="support-copy">Ainda não existe histórico de entrega da proatividade.</p>
        ) : (
          <div className="automation-history-grid">
            {proactiveDeliveries.map((delivery) => (
              <div key={delivery.id} className="activity-persist-block">
                <strong>{getProactiveCategoryLabel(delivery.category)}</strong>
                <div className="activity-meta-row">
                  <span>{getProactiveDecisionLabel(delivery.decision)}</span>
                  <span>Score {delivery.score.toFixed(2)}</span>
                  <span>{formatShortDateTime(delivery.created_at)}</span>
                </div>
                <p className="support-copy" style={{ marginTop: "0.65rem" }}>{delivery.reason_text || delivery.reason_code}</p>
                {delivery.message_text ? (
                  <p className="support-copy" style={{ marginTop: "0.45rem" }}>
                    “{truncateText(delivery.message_text, 180)}”
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      {proactiveError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na proatividade</strong><p>{proactiveError}</p></div> : null}
    </div>
  );
}
