import toast from 'react-hot-toast';
import { AlertCircle, BarChart3, Brain, Check, CheckCircle2, ChevronRight, Clock, Database, Edit2, Fingerprint, MessageSquare, Pause, Play, Plus, RefreshCw, Send, Settings, Terminal, Trash2, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField, formatBrazilDateTimeInput, parseBrazilDateTimeInput, formatAgendaReminderRule } from '../../connection-dashboard';
import { useMemo, useState } from 'react';
import type { AgendaEvent, CreateAgendaEventInput, UpdateAgendaEventInput } from '@/lib/api';

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
  type AgendaEditDraft = {
    titulo: string;
    inicio: string;
    fim: string;
    status: "firme" | "tentativo";
    contato_origem: string;
    reminder_offset_minutes: string;
  };

  const [filter, setFilter] = useState<"all" | "upcoming" | "firm" | "tentative" | "conflicts">("all");
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [agendaDrafts, setAgendaDrafts] = useState<Record<string, AgendaEditDraft>>({});
  const [creatingEvent, setCreatingEvent] = useState(events.length === 0);
  const now = Date.now();
  const sortedEvents = useMemo(
    () => [...events].sort((left, right) => new Date(left.inicio).getTime() - new Date(right.inicio).getTime()),
    [events],
  );
  const upcomingEvents = useMemo(
    () => sortedEvents.filter((event) => new Date(event.fim).getTime() >= now),
    [now, sortedEvents],
  );
  const firmCount = events.filter((event) => event.status === "firme").length;
  const tentativeCount = events.filter((event) => event.status !== "firme").length;
  const conflictCount = events.filter((event) => event.has_conflict).length;
  const nextEvent = upcomingEvents[0] ?? null;

  const filteredEvents = useMemo(() => {
    switch (filter) {
      case "upcoming":
        return upcomingEvents;
      case "firm":
        return sortedEvents.filter((event) => event.status === "firme");
      case "tentative":
        return sortedEvents.filter((event) => event.status !== "firme");
      case "conflicts":
        return sortedEvents.filter((event) => event.has_conflict);
      default:
        return sortedEvents;
    }
  }, [filter, sortedEvents, upcomingEvents]);

  const filterOptions = [
    { id: "all" as const, label: "Todos", count: sortedEvents.length },
    { id: "upcoming" as const, label: "Próximos", count: upcomingEvents.length },
    { id: "firm" as const, label: "Firmes", count: firmCount },
    { id: "tentative" as const, label: "Tentativos", count: tentativeCount },
    { id: "conflicts" as const, label: "Conflitos", count: conflictCount },
  ];

  const buildDraft = (event: AgendaEvent): AgendaEditDraft => ({
    titulo: event.titulo,
    inicio: formatBrazilDateTimeInput(event.inicio),
    fim: formatBrazilDateTimeInput(event.fim),
    status: event.status,
    contato_origem: event.contato_origem ?? "",
    reminder_offset_minutes: String(event.reminder_offset_minutes ?? 0),
  });
  const buildEmptyDraft = (): AgendaEditDraft => {
    const start = new Date();
    start.setSeconds(0, 0);
    const roundedMinutes = Math.ceil(start.getMinutes() / 15) * 15;
    start.setMinutes(roundedMinutes >= 60 ? 0 : roundedMinutes);
    if (roundedMinutes >= 60) {
      start.setHours(start.getHours() + 1);
    }
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    return {
      titulo: "",
      inicio: formatBrazilDateTimeInput(start.toISOString()),
      fim: formatBrazilDateTimeInput(end.toISOString()),
      status: "firme",
      contato_origem: "",
      reminder_offset_minutes: "0",
    };
  };
  const [createDraft, setCreateDraft] = useState<AgendaEditDraft>(() => buildEmptyDraft());

  const openEdit = (event: AgendaEvent): void => {
    setEditingEventId(event.id);
    setAgendaDrafts((current) => ({
      ...current,
      [event.id]: current[event.id] ?? buildDraft(event),
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
    const titulo = createDraft.titulo.trim();
    const inicio = parseBrazilDateTimeInput(createDraft.inicio);
    const fim = parseBrazilDateTimeInput(createDraft.fim);
    const reminderOffsetMinutes = Number.parseInt(createDraft.reminder_offset_minutes || "0", 10);

    if (!titulo) {
      toast.error("Informe um título para o compromisso.");
      return;
    }
    if (Number.isNaN(inicio.getTime()) || Number.isNaN(fim.getTime())) {
      toast.error("Preencha início e fim com datas válidas.");
      return;
    }
    if (fim.getTime() <= inicio.getTime()) {
      toast.error("O horário final precisa ser depois do início.");
      return;
    }
    if (Number.isNaN(reminderOffsetMinutes) || reminderOffsetMinutes < 0) {
      toast.error("A antecedência do lembrete precisa ser um número igual ou maior que zero.");
      return;
    }

    try {
      await onCreateEvent({
        titulo,
        inicio: inicio.toISOString(),
        fim: fim.toISOString(),
        status: createDraft.status,
        contato_origem: createDraft.contato_origem.trim() || undefined,
        reminder_offset_minutes: reminderOffsetMinutes,
      });
      setCreateDraft(buildEmptyDraft());
      setCreatingEvent(false);
      toast.success("Compromisso criado.");
    } catch {
      // Camada superior já registra e expõe erro.
    }
  }

  async function handleSave(event: AgendaEvent): Promise<void> {
    const draft = agendaDrafts[event.id] ?? buildDraft(event);
    const titulo = draft.titulo.trim();
    const inicio = parseBrazilDateTimeInput(draft.inicio);
    const fim = parseBrazilDateTimeInput(draft.fim);
    const reminderOffsetMinutes = Number.parseInt(draft.reminder_offset_minutes || "0", 10);

    if (!titulo) {
      toast.error("Informe um título para o compromisso.");
      return;
    }
    if (Number.isNaN(inicio.getTime()) || Number.isNaN(fim.getTime())) {
      toast.error("Preencha início e fim com datas válidas.");
      return;
    }
    if (fim.getTime() <= inicio.getTime()) {
      toast.error("O horário final precisa ser depois do início.");
      return;
    }
    if (Number.isNaN(reminderOffsetMinutes) || reminderOffsetMinutes < 0) {
      toast.error("A antecedência do lembrete precisa ser um número igual ou maior que zero.");
      return;
    }

    try {
      await onSaveEvent(event, {
        titulo,
        inicio: inicio.toISOString(),
        fim: fim.toISOString(),
        status: draft.status,
        contato_origem: draft.contato_origem.trim() || undefined,
        reminder_offset_minutes: reminderOffsetMinutes,
      });
      closeEdit();
      toast.success("Compromisso atualizado.");
    } catch {
      // A camada superior já registra o erro e mantém a UI em edição.
    }
  }

  if (events.length === 0) {
    return (
      <div className="page-stack">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm proj-empty-hero">
          <div className="proj-empty-icon">
            <Clock size={40} />
          </div>
          <h3>Nenhum compromisso detectado ainda</h3>
          <p>
            Assim que o Guardião do Tempo encontrar uma combinação de data e horário nas mensagens recebidas pelo Observador
            ou pelo agente do WhatsApp, os compromissos aparecem aqui.
          </p>
          <div className="hero-actions">
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" onClick={toggleCreate} type="button">
              <Plus size={15} />
              {creatingEvent ? "Fechar criação manual" : "Novo compromisso"}
            </button>
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar agenda
            </button>
          </div>
          {creatingEvent ? (
            <div className="project-inline-editor" style={{ marginTop: "1.5rem", width: "100%" }}>
              <div className="project-inline-grid">
                <label className="project-inline-field project-inline-field-full">
                  <span>Título</span>
                  <input
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    type="text"
                    value={createDraft.titulo}
                    onChange={(event) => setCreateDraft((current) => ({ ...current, titulo: event.target.value }))}
                  />
                </label>
                <label className="project-inline-field">
                  <span>Início</span>
                  <input
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    type="datetime-local"
                    value={createDraft.inicio}
                    onChange={(event) => setCreateDraft((current) => ({ ...current, inicio: event.target.value }))}
                  />
                </label>
                <label className="project-inline-field">
                  <span>Fim</span>
                  <input
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    type="datetime-local"
                    value={createDraft.fim}
                    onChange={(event) => setCreateDraft((current) => ({ ...current, fim: event.target.value }))}
                  />
                </label>
                <label className="project-inline-field">
                  <span>Status</span>
                  <select
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    value={createDraft.status}
                    onChange={(event) =>
                      setCreateDraft((current) => ({
                        ...current,
                        status: event.target.value === "tentativo" ? "tentativo" : "firme",
                      }))
                    }
                  >
                    <option value="firme">Firme</option>
                    <option value="tentativo">Tentativo</option>
                  </select>
                </label>
                <label className="project-inline-field">
                  <span>Origem / contato</span>
                  <input
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    type="text"
                    value={createDraft.contato_origem}
                    onChange={(event) => setCreateDraft((current) => ({ ...current, contato_origem: event.target.value }))}
                  />
                </label>
                <label className="project-inline-field">
                  <span>Antecedência do lembrete</span>
                  <input
                    className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                    type="number"
                    min="0"
                    step="1"
                    value={createDraft.reminder_offset_minutes}
                    onChange={(event) =>
                      setCreateDraft((current) => ({ ...current, reminder_offset_minutes: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="project-inline-actions">
                <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" disabled={isCreatingEvent} onClick={() => void handleCreate()} type="button">
                  {isCreatingEvent ? <RefreshCw size={14} className="spin" /> : <Check size={14} />}
                  {isCreatingEvent ? "Criando..." : "Salvar compromisso"}
                </button>
                <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" disabled={isCreatingEvent} onClick={toggleCreate} type="button">
                  Cancelar
                </button>
              </div>
            </div>
          ) : null}
          {error ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na agenda</strong><p>{error}</p></div> : null}
          {actionError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na edição da agenda</strong><p>{actionError}</p></div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm projects-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Clock size={14} />
            Guardião do Tempo
          </div>
          <h3>Compromissos detectados no WhatsApp</h3>
          <p>
            Esta visão concentra os eventos extraídos pelo backend, já com status, contato de origem, lembrete automático e
            marcação de conflito quando houver sobreposição de horário.
          </p>
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
            <small>{conflictCount > 0 ? "requerem atenção" : "sem sobreposição agora"}</small>
          </div>
          <div className="projects-hero-metric">
            <span>Próximo</span>
            <strong>{nextEvent ? formatShortDateTime(nextEvent.inicio) : "Sem próximo"}</strong>
            <small>{nextEvent ? nextEvent.titulo : "Nenhum compromisso futuro detectado"}</small>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle
          title="Agenda"
          icon={Clock}
          action={
            <div className="hero-actions" style={{ margin: 0 }}>
              <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" onClick={toggleCreate} type="button">
                <Plus size={14} />
                {creatingEvent ? "Fechar criação" : "Novo compromisso"}
              </button>
              <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onRefresh} type="button">
                <RefreshCw size={14} />
                Atualizar
              </button>
            </div>
          }
        />
        {creatingEvent ? (
          <div className="project-inline-editor" style={{ marginBottom: "1rem" }}>
            <div className="project-inline-grid">
              <label className="project-inline-field project-inline-field-full">
                <span>Título</span>
                <input
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  type="text"
                  value={createDraft.titulo}
                  onChange={(event) => setCreateDraft((current) => ({ ...current, titulo: event.target.value }))}
                />
              </label>
              <label className="project-inline-field">
                <span>Início</span>
                <input
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  type="datetime-local"
                  value={createDraft.inicio}
                  onChange={(event) => setCreateDraft((current) => ({ ...current, inicio: event.target.value }))}
                />
              </label>
              <label className="project-inline-field">
                <span>Fim</span>
                <input
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  type="datetime-local"
                  value={createDraft.fim}
                  onChange={(event) => setCreateDraft((current) => ({ ...current, fim: event.target.value }))}
                />
              </label>
              <label className="project-inline-field">
                <span>Status</span>
                <select
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  value={createDraft.status}
                  onChange={(event) =>
                    setCreateDraft((current) => ({
                      ...current,
                      status: event.target.value === "tentativo" ? "tentativo" : "firme",
                    }))
                  }
                >
                  <option value="firme">Firme</option>
                  <option value="tentativo">Tentativo</option>
                </select>
              </label>
              <label className="project-inline-field">
                <span>Origem / contato</span>
                <input
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  type="text"
                  value={createDraft.contato_origem}
                  onChange={(event) => setCreateDraft((current) => ({ ...current, contato_origem: event.target.value }))}
                />
              </label>
              <label className="project-inline-field">
                <span>Antecedência do lembrete</span>
                <input
                  className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                  type="number"
                  min="0"
                  step="1"
                  value={createDraft.reminder_offset_minutes}
                  onChange={(event) =>
                    setCreateDraft((current) => ({ ...current, reminder_offset_minutes: event.target.value }))
                  }
                />
              </label>
            </div>
            <div className="project-inline-actions">
              <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" disabled={isCreatingEvent} onClick={() => void handleCreate()} type="button">
                {isCreatingEvent ? <RefreshCw size={14} className="spin" /> : <Check size={14} />}
                {isCreatingEvent ? "Criando..." : "Salvar compromisso"}
              </button>
              <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" disabled={isCreatingEvent} onClick={toggleCreate} type="button">
                Cancelar
              </button>
            </div>
          </div>
        ) : null}
        <div className="projects-toolbar">
          <div className="projects-filter-pills">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`projects-filter-pill${filter === option.id ? " projects-filter-pill-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>

        <div className="project-list-modern">
          {filteredEvents.map((event) => {
            const isEditing = editingEventId === event.id;
            const draft = agendaDrafts[event.id] ?? buildDraft(event);
            const isSaving = savingAgendaIds.includes(event.id);
            const isDeleting = deletingAgendaIds.includes(event.id);

            return (
              <div
                key={event.id}
                className={`project-card-modern${event.has_conflict ? " project-card-modern-attention" : ""}`}
              >
                <div className="project-card-head">
                  <div>
                    <strong>{event.titulo}</strong>
                    <span>
                      {formatShortDateTime(event.inicio)} até {formatShortDateTime(event.fim)}
                    </span>
                  </div>
                  <div className="project-card-actions">
                    <span className={`micro-status micro-status-${event.status === "firme" ? "emerald" : "amber"}`}>
                      {event.status === "firme" ? "Firme" : "Tentativo"}
                    </span>
                    {event.has_conflict ? (
                      <span className="micro-status micro-status-amber">Conflito</span>
                    ) : null}
                    <button
                      className="ac-button ac-button-outline ac-button-sm"
                      disabled={isSaving || isDeleting}
                      onClick={() => (isEditing ? closeEdit() : openEdit(event))}
                      type="button"
                    >
                      {isEditing ? <X size={14} /> : <Edit2 size={14} />}
                    </button>
                    <button
                      className="ac-button ac-button-outline ac-button-sm"
                      disabled={isSaving || isDeleting}
                      onClick={() => void onDeleteEvent(event)}
                      type="button"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {isEditing ? (
                  <div className="project-summary-stack" style={{ gap: "0.85rem" }}>
                    <label>
                      <span className="support-copy">Título</span>
                      <input
                        className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                        onChange={(editEvent) =>
                          setAgendaDrafts((current) => ({
                            ...current,
                            [event.id]: { ...draft, titulo: editEvent.target.value },
                          }))
                        }
                        type="text"
                        value={draft.titulo}
                      />
                    </label>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Início</span>
                        <input
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, inicio: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.inicio}
                        />
                      </label>
                      <label>
                        <span className="support-copy">Fim</span>
                        <input
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, fim: editEvent.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.fim}
                        />
                      </label>
                    </div>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Status</span>
                        <select
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: {
                                ...draft,
                                status: editEvent.target.value === "firme" ? "firme" : "tentativo",
                              },
                            }))
                          }
                          value={draft.status}
                        >
                          <option value="firme">Firme</option>
                          <option value="tentativo">Tentativo</option>
                        </select>
                      </label>
                      <label>
                        <span className="support-copy">Origem</span>
                        <input
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                          onChange={(editEvent) =>
                            setAgendaDrafts((current) => ({
                              ...current,
                              [event.id]: { ...draft, contato_origem: editEvent.target.value },
                            }))
                          }
                          type="text"
                          value={draft.contato_origem}
                        />
                      </label>
                    </div>
                    <div className="dual-column-grid" style={{ marginTop: 0 }}>
                      <label>
                        <span className="support-copy">Antecedência do lembrete em Brasília</span>
                        <input
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
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
                      </label>
                      <div className="support-copy" style={{ alignSelf: "end", paddingBottom: "0.75rem" }}>
                        Horário do formulário: Brasília (UTC-3)
                      </div>
                    </div>
                    <div className="hero-actions">
                      <button
                        className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2"
                        disabled={isSaving || isDeleting}
                        onClick={() => void handleSave(event)}
                        type="button"
                      >
                        <Check size={14} />
                        {isSaving ? "Salvando..." : "Salvar alterações"}
                      </button>
                      <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" disabled={isSaving} onClick={closeEdit} type="button">
                        <X size={14} />
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="project-summary-stack">
                    <p className="support-copy">
                      {event.contato_origem ? `Origem: ${event.contato_origem}.` : "Origem não identificada."}
                    </p>
                    <p className="support-copy">
                      ID da mensagem: <code>{event.message_id}</code>
                    </p>
                    <p className="support-copy">
                      Regra de lembrete: {formatAgendaReminderRule(event)}
                    </p>
                    <p className="support-copy">
                      {event.pre_reminder_at
                        ? event.pre_reminder_sent_at
                          ? `Lembrete antecipado enviado em ${formatShortDateTime(event.pre_reminder_sent_at)}.`
                          : `Lembrete antecipado programado para ${formatShortDateTime(event.pre_reminder_at)}.`
                        : event.reminder_eligible
                          ? "Sem lembrete antecipado configurado."
                          : "Lembretes automáticos desativados para este evento."}
                    </p>
                    <p className="support-copy">
                      {event.reminder_sent_at
                        ? `Lembrete do horário enviado em ${formatShortDateTime(event.reminder_sent_at)}.`
                        : event.reminder_eligible
                          ? "Lembrete do horário ainda pendente."
                          : "Evento não elegível para lembrete no horário."}
                    </p>
                    {event.conflict ? (
                      <div className="danger-box" style={{ marginTop: 12 }}>
                        <h4>
                          <AlertCircle size={16} />
                          Possível conflito
                        </h4>
                        <p>
                          Já existe <strong>{event.conflict.titulo}</strong> em {formatShortDateTime(event.conflict.inicio)} até{" "}
                          {formatShortDateTime(event.conflict.fim)}.
                        </p>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {filteredEvents.length === 0 ? (
          <div className="empty-hint">
            <Clock size={18} />
            <p>Nenhum compromisso bate com o filtro atual.</p>
          </div>
        ) : null}
      </div>

      {error ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na agenda</strong><p>{error}</p></div> : null}
      {actionError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha na edição da agenda</strong><p>{actionError}</p></div> : null}
    </div>
  );
}
