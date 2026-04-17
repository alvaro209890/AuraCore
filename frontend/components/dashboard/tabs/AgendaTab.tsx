import toast from 'react-hot-toast';
import type { ReactNode } from 'react';
import { AlertCircle, Check, Clock, Edit2, Plus, RefreshCw, Trash2, X } from 'lucide-react';
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

type AgendaEditDraft = {
  titulo: string;
  inicio: string;
  fim: string;
  status: 'firme' | 'tentativo';
  contato_origem: string;
  reminder_offset_minutes: string;
};

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
          <h3>Agenda mais clara, com criação manual melhor resolvida e leitura rápida dos conflitos.</h3>
          <p>
            Esta visão reúne compromissos detectados nas mensagens e os que foram adicionados manualmente. O foco aqui
            é deixar status, lembretes e edição bem mais legíveis.
          </p>
          <div className="hero-actions">
            <button className="ac-button ac-button-primary" onClick={toggleCreate} type="button">
              <Plus size={15} />
              {creatingEvent ? 'Fechar criação' : 'Novo compromisso'}
            </button>
            <button className="ac-button ac-button-outline" onClick={onRefresh} type="button">
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
          action={
            <div className="hero-actions" style={{ margin: 0 }}>
              <span className="micro-badge">Formulário em horário de Brasília</span>
            </div>
          }
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
          <div className="ops-form-shell">
            <div className="ops-form-head">
              <div>
                <strong>Novo compromisso manual</strong>
                <p>Preencha título, faixa de horário, origem e regra de lembrete num bloco único e mais limpo.</p>
              </div>
            </div>
            <div className="ops-form-grid">
              <AgendaField full hint="Use um título objetivo para o compromisso." label="Título">
                <input
                  className="ops-input"
                  onChange={(event) => setCreateDraft((current) => ({ ...current, titulo: event.target.value }))}
                  placeholder="Ex.: Reunião com cliente X"
                  type="text"
                  value={createDraft.titulo}
                />
              </AgendaField>

              <AgendaField label="Início">
                <input
                  className="ops-input"
                  onChange={(event) => setCreateDraft((current) => ({ ...current, inicio: event.target.value }))}
                  type="datetime-local"
                  value={createDraft.inicio}
                />
              </AgendaField>

              <AgendaField label="Fim">
                <input
                  className="ops-input"
                  onChange={(event) => setCreateDraft((current) => ({ ...current, fim: event.target.value }))}
                  type="datetime-local"
                  value={createDraft.fim}
                />
              </AgendaField>

              <AgendaField hint="Firme entra como compromisso consolidado; tentativo mantém incerteza." label="Status">
                <select
                  className="ops-select"
                  onChange={(event) =>
                    setCreateDraft((current) => ({
                      ...current,
                      status: event.target.value === 'tentativo' ? 'tentativo' : 'firme',
                    }))
                  }
                  value={createDraft.status}
                >
                  <option value="firme">Firme</option>
                  <option value="tentativo">Tentativo</option>
                </select>
              </AgendaField>

              <AgendaField hint="Contato, grupo ou origem livre do compromisso." label="Origem / contato">
                <input
                  className="ops-input"
                  onChange={(event) =>
                    setCreateDraft((current) => ({ ...current, contato_origem: event.target.value }))
                  }
                  placeholder="Ex.: WhatsApp, cliente, equipe"
                  type="text"
                  value={createDraft.contato_origem}
                />
              </AgendaField>

              <AgendaField hint="Quantos minutos antes o lembrete deve sair." label="Antecedência do lembrete">
                <input
                  className="ops-input"
                  min="0"
                  onChange={(event) =>
                    setCreateDraft((current) => ({ ...current, reminder_offset_minutes: event.target.value }))
                  }
                  step="1"
                  type="number"
                  value={createDraft.reminder_offset_minutes}
                />
              </AgendaField>
            </div>

            <div className="project-inline-actions">
              <button
                className="ac-button ac-button-primary"
                disabled={isCreatingEvent}
                onClick={() => void handleCreate()}
                type="button"
              >
                {isCreatingEvent ? <RefreshCw className="spin" size={15} /> : <Check size={15} />}
                {isCreatingEvent ? 'Criando...' : 'Salvar compromisso'}
              </button>
              <button className="ac-button ac-button-outline" disabled={isCreatingEvent} onClick={toggleCreate} type="button">
                <X size={15} />
                Cancelar
              </button>
            </div>
          </div>
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
                      className="ac-button ac-button-outline ac-button-sm"
                      disabled={isSaving || isDeleting}
                      onClick={() => (isEditing ? closeEdit() : openEdit(event))}
                      type="button"
                    >
                      {isEditing ? <X size={14} /> : <Edit2 size={14} />}
                    </button>
                    <button
                      className="ac-button ac-button-outline ac-button-sm project-delete-button"
                      disabled={isSaving || isDeleting}
                      onClick={() => void onDeleteEvent(event)}
                      type="button"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {isEditing ? (
                  <div className="ops-form-shell">
                    <div className="ops-form-grid">
                      <AgendaField full label="Título">
                        <input
                          className="ops-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, titulo: editEvent.target.value },
                            }))
                          }
                          type="text"
                          value={draft.titulo}
                        />
                      </AgendaField>

                      <AgendaField label="Início">
                        <input
                          className="ops-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, inicio: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.inicio}
                        />
                      </AgendaField>

                      <AgendaField label="Fim">
                        <input
                          className="ops-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, fim: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.fim}
                        />
                      </AgendaField>

                      <AgendaField label="Status">
                        <select
                          className="ops-select"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: {
                                ...draft,
                                status: editEvent.target.value === 'firme' ? 'firme' : 'tentativo',
                              },
                            }))
                          }
                          value={draft.status}
                        >
                          <option value="firme">Firme</option>
                          <option value="tentativo">Tentativo</option>
                        </select>
                      </AgendaField>

                      <AgendaField label="Origem / contato">
                        <input
                          className="ops-input"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, contato_origem: editEvent.target.value },
                            }))
                          }
                          type="text"
                          value={draft.contato_origem}
                        />
                      </AgendaField>

                      <AgendaField hint="Minutos antes do evento." label="Antecedência do lembrete">
                        <input
                          className="ops-input"
                          min="0"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, reminder_offset_minutes: editEvent.target.value },
                            }))
                          }
                          step="1"
                          type="number"
                          value={draft.reminder_offset_minutes}
                        />
                      </AgendaField>
                    </div>

                    <div className="project-inline-actions">
                      <button
                        className="ac-button ac-button-primary"
                        disabled={isSaving || isDeleting}
                        onClick={() => void handleSave(event)}
                        type="button"
                      >
                        {isSaving ? <RefreshCw className="spin" size={15} /> : <Check size={15} />}
                        {isSaving ? 'Salvando...' : 'Salvar alterações'}
                      </button>
                      <button className="ac-button ac-button-outline" disabled={isSaving} onClick={closeEdit} type="button">
                        <X size={15} />
                        Cancelar
                      </button>
                    </div>
                  </div>
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
