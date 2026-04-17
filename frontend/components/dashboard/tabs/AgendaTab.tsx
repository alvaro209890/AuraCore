import toast from 'react-hot-toast';
import type { ReactNode } from 'react';
import { AlertCircle, BellRing, Check, Clock, Edit2, Plus, RefreshCw, Trash2, Users, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  formatAgendaReminderRule,
  formatBrazilDateTimeInput,
  formatRelativeTime,
  formatShortDateTime,
  parseBrazilDateTimeInput,
  SectionTitle,
} from '../../connection-dashboard';
import type { AgendaEvent, CreateAgendaEventInput, UpdateAgendaEventInput } from '@/lib/api';

type Tone = 'emerald' | 'indigo' | 'amber';

type AgendaEditDraft = {
  titulo: string;
  inicio: string;
  fim: string;
  status: 'firme' | 'tentativo';
  contato_origem: string;
  reminder_offset_minutes: string;
};

const STATUS_OPTIONS: Array<{
  value: AgendaEditDraft['status'];
  title: string;
  description: string;
  tone: Tone;
}> = [
  {
    value: 'firme',
    title: 'Firme',
    description: 'Compromisso confirmado e pronto para lembrete normal.',
    tone: 'emerald',
  },
  {
    value: 'tentativo',
    title: 'Tentativo',
    description: 'Mantém o horário visível, mas preserva incerteza operacional.',
    tone: 'amber',
  },
];

const REMINDER_PRESETS = [0, 15, 30, 60, 120];

function AgendaField({
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

function buildEventDraft(event: AgendaEvent): AgendaEditDraft {
  return {
    titulo: event.titulo,
    inicio: formatBrazilDateTimeInput(event.inicio),
    fim: formatBrazilDateTimeInput(event.fim),
    status: event.status,
    contato_origem: event.contato_origem ?? '',
    reminder_offset_minutes: String(event.reminder_offset_minutes ?? 0),
  };
}

function buildEmptyDraft(): AgendaEditDraft {
  const start = new Date();
  start.setSeconds(0, 0);
  const roundedMinutes = Math.ceil(start.getMinutes() / 15) * 15;
  start.setMinutes(roundedMinutes >= 60 ? 0 : roundedMinutes);
  if (roundedMinutes >= 60) {
    start.setHours(start.getHours() + 1);
  }
  const end = new Date(start.getTime() + 60 * 60 * 1000);

  return {
    titulo: '',
    inicio: formatBrazilDateTimeInput(start.toISOString()),
    fim: formatBrazilDateTimeInput(end.toISOString()),
    status: 'firme',
    contato_origem: '',
    reminder_offset_minutes: '0',
  };
}

function parseDraftPayload(draft: AgendaEditDraft): CreateAgendaEventInput | null {
  const titulo = draft.titulo.trim();
  const inicio = parseBrazilDateTimeInput(draft.inicio);
  const fim = parseBrazilDateTimeInput(draft.fim);
  const reminderOffsetMinutes = Number.parseInt(draft.reminder_offset_minutes || '0', 10);

  if (!titulo) {
    toast.error('Informe um título para o compromisso.');
    return null;
  }
  if (Number.isNaN(inicio.getTime()) || Number.isNaN(fim.getTime())) {
    toast.error('Preencha início e fim com datas válidas.');
    return null;
  }
  if (fim.getTime() <= inicio.getTime()) {
    toast.error('O horário final precisa ser depois do início.');
    return null;
  }
  if (Number.isNaN(reminderOffsetMinutes) || reminderOffsetMinutes < 0) {
    toast.error('A antecedência do lembrete precisa ser um número igual ou maior que zero.');
    return null;
  }

  return {
    titulo,
    inicio: inicio.toISOString(),
    fim: fim.toISOString(),
    status: draft.status,
    contato_origem: draft.contato_origem.trim() || undefined,
    reminder_offset_minutes: reminderOffsetMinutes,
  };
}

function formatReminderLead(minutesValue: string): string {
  const minutes = Number.parseInt(minutesValue || '0', 10);
  if (Number.isNaN(minutes) || minutes < 0) {
    return 'Antecedência inválida';
  }
  if (minutes === 0) {
    return 'Lembrete no horário do compromisso';
  }
  if (minutes < 60) {
    return `Lembrete ${minutes} min antes`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (remainder === 0) {
    return `Lembrete ${hours}h antes`;
  }
  return `Lembrete ${hours}h${remainder}min antes`;
}

function formatWindowSummary(draft: AgendaEditDraft): string {
  const inicio = parseBrazilDateTimeInput(draft.inicio);
  const fim = parseBrazilDateTimeInput(draft.fim);
  if (Number.isNaN(inicio.getTime()) || Number.isNaN(fim.getTime())) {
    return 'Preencha o horário para ver a janela final do compromisso.';
  }
  return `${formatShortDateTime(inicio.toISOString())} até ${formatShortDateTime(fim.toISOString())}`;
}

function AgendaEditor({
  title,
  description,
  draft,
  disabled,
  submitLabel,
  submittingLabel,
  onChange,
  onSubmit,
  onCancel,
}: {
  title: string;
  description: string;
  draft: AgendaEditDraft;
  disabled: boolean;
  submitLabel: string;
  submittingLabel: string;
  onChange: (patch: Partial<AgendaEditDraft>) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="ops-form-shell">
      <div className="ops-form-head">
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
      </div>

      <div className="ops-form-grid ops-form-grid-dual">
        <AgendaField full hint="Use um título objetivo e reconhecível no painel." label="Título do compromisso">
          <InputShell hint="Evite nomes genéricos como reunião ou call solta." icon={<Edit2 size={16} />} tone="indigo">
            <input
              className="ops-input"
              onChange={(event) => onChange({ titulo: event.target.value })}
              placeholder="Ex.: Revisão do deploy com cliente X"
              type="text"
              value={draft.titulo}
            />
          </InputShell>
        </AgendaField>

        <AgendaField hint="Horário inicial em Brasília." label="Início">
          <InputShell hint="Ponto de entrada do compromisso." icon={<Clock size={16} />} tone="indigo">
            <input
              className="ops-input"
              onChange={(event) => onChange({ inicio: event.target.value })}
              type="datetime-local"
              value={draft.inicio}
            />
          </InputShell>
        </AgendaField>

        <AgendaField hint="Horário final em Brasília." label="Fim">
          <InputShell hint="Define a duração visível e conflito." icon={<Clock size={16} />} tone="amber">
            <input
              className="ops-input"
              onChange={(event) => onChange({ fim: event.target.value })}
              type="datetime-local"
              value={draft.fim}
            />
          </InputShell>
        </AgendaField>

        <AgendaField hint="Pessoa, grupo ou origem livre do compromisso." label="Origem / contato">
          <InputShell hint="Ajuda a rastrear de onde saiu o compromisso." icon={<Users size={16} />} tone="emerald">
            <input
              className="ops-input"
              onChange={(event) => onChange({ contato_origem: event.target.value })}
              placeholder="Ex.: WhatsApp, cliente, equipe interna"
              type="text"
              value={draft.contato_origem}
            />
          </InputShell>
        </AgendaField>

        <AgendaField hint="Minutos antes do evento em que o lembrete deve sair." label="Antecedência do lembrete">
          <InputShell hint="O guardião usa esse lead time para o pré-aviso." icon={<BellRing size={16} />} tone="amber">
            <input
              className="ops-input"
              min="0"
              onChange={(event) => onChange({ reminder_offset_minutes: event.target.value })}
              step="1"
              type="number"
              value={draft.reminder_offset_minutes}
            />
          </InputShell>
        </AgendaField>
      </div>

      <AgendaField
        full
        hint="Troque o tipo do compromisso sem depender de select simples. O estado fica mais legível."
        label="Status operacional"
      >
        <div className="ops-pill-grid">
          {STATUS_OPTIONS.map((option) => {
            const isActive = draft.status === option.value;
            return (
              <button
                key={option.value}
                className={`ops-pill-button${isActive ? ` ops-pill-button-active ops-pill-button-active-${option.tone}` : ''}`}
                onClick={() => onChange({ status: option.value })}
                type="button"
              >
                <strong>{option.title}</strong>
                <span>{option.description}</span>
              </button>
            );
          })}
        </div>
      </AgendaField>

      <div className="ops-inline-note">
        <strong>{formatWindowSummary(draft)}</strong>
        <span>{formatReminderLead(draft.reminder_offset_minutes)}</span>
      </div>

      <AgendaField
        full
        hint="Atalhos rápidos para não digitar toda vez a mesma antecedência."
        label="Presets de lembrete"
      >
        <div className="ops-pill-grid">
          {REMINDER_PRESETS.map((minutes) => {
            const isActive = draft.reminder_offset_minutes === String(minutes);
            return (
              <button
                key={minutes}
                className={`ops-pill-button${isActive ? ' ops-pill-button-active ops-pill-button-active-amber' : ''}`}
                onClick={() => onChange({ reminder_offset_minutes: String(minutes) })}
                type="button"
              >
                <strong>{minutes === 0 ? 'No horário' : `${minutes} min`}</strong>
                <span>{minutes === 0 ? 'Sem antecedência extra' : `Disparar ${minutes} min antes`}</span>
              </button>
            );
          })}
        </div>
      </AgendaField>

      <div className="project-inline-actions">
        <button className="ops-hero-button ops-hero-button-primary" disabled={disabled} onClick={onSubmit} type="button">
          {disabled ? <RefreshCw className="spin" size={15} /> : <Check size={15} />}
          {disabled ? submittingLabel : submitLabel}
        </button>
        <button className="ops-hero-button ops-hero-button-ghost" disabled={disabled} onClick={onCancel} type="button">
          <X size={15} />
          Cancelar
        </button>
      </div>
    </div>
  );
}

export default function AgendaTab({
  events,
  error,
  actionError,
  onRefresh,
  onCreateEvent,
  onSaveEvent,
  onDeleteEvent,
  savingAgendaIds,
  deletingAgendaIds,
  isCreatingEvent,
}: {
  events: AgendaEvent[];
  error: string | null;
  actionError: string | null;
  onRefresh: () => void;
  onCreateEvent: (input: CreateAgendaEventInput) => Promise<AgendaEvent>;
  onSaveEvent: (event: AgendaEvent, input: UpdateAgendaEventInput) => Promise<AgendaEvent>;
  onDeleteEvent: (event: AgendaEvent) => Promise<void>;
  savingAgendaIds: string[];
  deletingAgendaIds: string[];
  isCreatingEvent: boolean;
}) {
  const [filter, setFilter] = useState<'all' | 'upcoming' | 'firm' | 'tentative' | 'conflicts'>('all');
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [agendaDrafts, setAgendaDrafts] = useState<Record<string, AgendaEditDraft>>({});
  const [creatingEvent, setCreatingEvent] = useState(events.length === 0);
  const [createDraft, setCreateDraft] = useState<AgendaEditDraft>(() => buildEmptyDraft());

  const now = Date.now();
  const sortedEvents = useMemo(
    () => [...events].sort((left, right) => new Date(left.inicio).getTime() - new Date(right.inicio).getTime()),
    [events],
  );
  const upcomingEvents = useMemo(
    () => sortedEvents.filter((event) => new Date(event.fim).getTime() >= now),
    [now, sortedEvents],
  );
  const firmCount = events.filter((event) => event.status === 'firme').length;
  const tentativeCount = events.length - firmCount;
  const conflictCount = events.filter((event) => event.has_conflict).length;
  const nextEvent = upcomingEvents[0] ?? null;

  const filterOptions = [
    { id: 'all' as const, label: 'Todos', count: sortedEvents.length },
    { id: 'upcoming' as const, label: 'Próximos', count: upcomingEvents.length },
    { id: 'firm' as const, label: 'Firmes', count: firmCount },
    { id: 'tentative' as const, label: 'Tentativos', count: tentativeCount },
    { id: 'conflicts' as const, label: 'Conflitos', count: conflictCount },
  ];

  const filteredEvents = useMemo(() => {
    switch (filter) {
      case 'upcoming':
        return upcomingEvents;
      case 'firm':
        return sortedEvents.filter((event) => event.status === 'firme');
      case 'tentative':
        return sortedEvents.filter((event) => event.status !== 'firme');
      case 'conflicts':
        return sortedEvents.filter((event) => event.has_conflict);
      default:
        return sortedEvents;
    }
  }, [filter, sortedEvents, upcomingEvents]);

  const openEdit = (event: AgendaEvent): void => {
    setEditingEventId(event.id);
    setAgendaDrafts((current) => ({
      ...current,
      [event.id]: current[event.id] ?? buildEventDraft(event),
    }));
  };

  const closeEdit = (): void => {
    setEditingEventId(null);
  };

  const toggleCreate = (): void => {
    setCreatingEvent((current) => {
      const next = !current;
      if (next) {
        setCreateDraft(buildEmptyDraft());
      }
      return next;
    });
  };

  async function handleCreate(): Promise<void> {
    const payload = parseDraftPayload(createDraft);
    if (!payload) {
      return;
    }

    try {
      await onCreateEvent(payload);
      setCreateDraft(buildEmptyDraft());
      setCreatingEvent(false);
      toast.success('Compromisso criado.');
    } catch {
      // O estado de erro já é controlado na camada superior.
    }
  }

  async function handleSave(event: AgendaEvent): Promise<void> {
    const payload = parseDraftPayload(agendaDrafts[event.id] ?? buildEventDraft(event));
    if (!payload) {
      return;
    }

    try {
      await onSaveEvent(event, payload);
      setEditingEventId(null);
      toast.success('Compromisso atualizado.');
    } catch {
      // O estado de erro já é controlado na camada superior.
    }
  }

  return (
    <div className="page-stack">
      <div className="projects-hero-card agenda-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Clock size={14} />
            Guardião do Tempo
          </div>
          <h3>Agenda com criação manual mais sólida, conflito legível e formulários consistentes com o restante do painel.</h3>
          <p>
            Esta visão reúne compromissos detectados nas mensagens e lançamentos manuais. A criação e a edição agora
            usam shells modernos, presets de lembrete e um status visual mais claro.
          </p>
          <div className="ops-hero-actions">
            <button className="ops-hero-button ops-hero-button-primary" onClick={toggleCreate} type="button">
              <Plus size={15} />
              {creatingEvent ? 'Fechar criação' : 'Novo compromisso'}
            </button>
            <button className="ops-hero-button ops-hero-button-ghost" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar agenda
            </button>
          </div>
        </div>

        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Total</span>
            <strong>{events.length}</strong>
            <small>{upcomingEvents.length} ainda por acontecer</small>
          </div>
          <div className="projects-hero-metric">
            <span>Firmes</span>
            <strong>{firmCount}</strong>
            <small>{tentativeCount} tentativos</small>
          </div>
          <div className="projects-hero-metric">
            <span>Conflitos</span>
            <strong>{conflictCount}</strong>
            <small>{conflictCount > 0 ? 'pedem revisão' : 'sem sobreposição agora'}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Próximo</span>
            <strong>{nextEvent ? formatShortDateTime(nextEvent.inicio) : 'Sem próximo'}</strong>
            <small>{nextEvent ? nextEvent.titulo : 'Nenhum evento futuro detectado'}</small>
          </div>
        </div>
      </div>

      <div className="ops-surface">
        <SectionTitle
          title="Compromissos"
          icon={Clock}
          action={<span className="micro-badge">Formulário em horário de Brasília</span>}
        />

        <div className="projects-toolbar">
          <div className="projects-filter-pills">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`projects-filter-pill${filter === option.id ? ' projects-filter-pill-active' : ''}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>

        {creatingEvent ? (
          <AgendaEditor
            description="Preencha o bloco inteiro sem campos crus. Título, faixa de horário, origem e lembrete ficam no mesmo shell operacional."
            disabled={isCreatingEvent}
            draft={createDraft}
            onCancel={toggleCreate}
            onChange={(patch) => setCreateDraft((current) => ({ ...current, ...patch }))}
            onSubmit={() => void handleCreate()}
            submitLabel="Salvar compromisso"
            submittingLabel="Criando..."
            title="Novo compromisso manual"
          />
        ) : null}

        <div className="project-list-modern">
          {filteredEvents.map((event) => {
            const isEditing = editingEventId === event.id;
            const draft = agendaDrafts[event.id] ?? buildEventDraft(event);
            const isSaving = savingAgendaIds.includes(event.id);
            const isDeleting = deletingAgendaIds.includes(event.id);

            return (
              <div
                key={event.id}
                className={`project-card-modern agenda-event-card${event.has_conflict ? ' project-card-modern-attention' : ''}`}
              >
                <div className="project-card-head">
                  <div>
                    <strong>{event.titulo}</strong>
                    <span>
                      {formatShortDateTime(event.inicio)} até {formatShortDateTime(event.fim)}
                    </span>
                  </div>
                  <div className="project-card-actions">
                    <span className={`micro-status micro-status-${event.status === 'firme' ? 'emerald' : 'amber'}`}>
                      {event.status === 'firme' ? 'Firme' : 'Tentativo'}
                    </span>
                    {event.has_conflict ? <span className="micro-status micro-status-amber">Conflito</span> : null}
                    <button
                      className="ops-hero-button ops-hero-button-ghost"
                      disabled={isSaving || isDeleting}
                      onClick={() => (isEditing ? closeEdit() : openEdit(event))}
                      type="button"
                    >
                      {isEditing ? <X size={14} /> : <Edit2 size={14} />}
                      {isEditing ? 'Fechar' : 'Editar'}
                    </button>
                    <button
                      className="ac-danger-button"
                      disabled={isSaving || isDeleting}
                      onClick={() => void onDeleteEvent(event)}
                      type="button"
                    >
                      <Trash2 size={14} />
                      Excluir
                    </button>
                  </div>
                </div>

                {isEditing ? (
                  <AgendaEditor
                    description="Ajuste rapidamente horário, status, origem e lembrete sem cair em campos brancos e soltos."
                    disabled={isSaving || isDeleting}
                    draft={draft}
                    onCancel={closeEdit}
                    onChange={(patch) =>
                      setAgendaDrafts((current) => ({
                        ...current,
                        [event.id]: { ...draft, ...patch },
                      }))
                    }
                    onSubmit={() => void handleSave(event)}
                    submitLabel="Salvar alterações"
                    submittingLabel="Salvando..."
                    title="Editar compromisso"
                  />
                ) : (
                  <>
                    <div className="ops-meta-grid">
                      <div className="ops-meta-card">
                        <span>Origem</span>
                        <strong>{event.contato_origem || 'Não identificada'}</strong>
                        <small>Atualizado {formatRelativeTime(event.updated_at)}</small>
                      </div>
                      <div className="ops-meta-card">
                        <span>Lembrete</span>
                        <strong>{formatAgendaReminderRule(event)}</strong>
                        <small>
                          {event.pre_reminder_at
                            ? `Pré-lembrete ${event.pre_reminder_sent_at ? 'enviado' : 'programado'}`
                            : event.reminder_eligible
                              ? 'Sem pré-lembrete configurado'
                              : 'Lembretes automáticos desativados'}
                        </small>
                      </div>
                      <div className="ops-meta-card">
                        <span>Mensagem de origem</span>
                        <strong>{event.message_id.startsWith('manual:') ? 'Manual' : 'WhatsApp'}</strong>
                        <small>{event.message_id}</small>
                      </div>
                    </div>

                    <div className="project-summary-stack">
                      <p className="support-copy">
                        {event.reminder_sent_at
                          ? `Lembrete principal enviado em ${formatShortDateTime(event.reminder_sent_at)}.`
                          : event.reminder_eligible
                            ? 'Lembrete principal ainda pendente.'
                            : 'Evento não elegível para lembrete no horário.'}
                      </p>
                      {event.conflict ? (
                        <div className="danger-box">
                          <h4>
                            <AlertCircle size={16} />
                            Possível conflito
                          </h4>
                          <p>
                            Já existe <strong>{event.conflict.titulo}</strong> em{' '}
                            {formatShortDateTime(event.conflict.inicio)} até {formatShortDateTime(event.conflict.fim)}.
                          </p>
                        </div>
                      ) : null}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>

        {filteredEvents.length === 0 ? (
          <div className="ops-empty-state">Nenhum compromisso bate com o filtro atual.</div>
        ) : null}
      </div>

      {error ? (
        <div className="danger-box">
          <h4>Falha na agenda</h4>
          <p>{error}</p>
        </div>
      ) : null}
      {actionError ? (
        <div className="danger-box">
          <h4>Falha na edição da agenda</h4>
          <p>{actionError}</p>
        </div>
      ) : null}
    </div>
  );
}
