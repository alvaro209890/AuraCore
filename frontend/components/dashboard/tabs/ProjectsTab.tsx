import toast from 'react-hot-toast';
import { AlertCircle, BadgeCheck, BarChart3, Bot, Brain, CheckCircle2, ChevronRight, Clock, Database, Fingerprint, FolderGit2, GitBranch, MessageSquare, Pause, Play, Plus, RefreshCw, Search, Send, Settings, Sparkles, Terminal, Trash2, User, Users, X, XCircle, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import type {  ProjectMemory , CreateProjectMemoryInput } from '@/lib/api';;

export default function ProjectsTab({
  projects,
  onCreateProject,
  onToggleCompletion,
  onSaveProject,
  onAssistProject,
  onDeleteProject,
  savingProjectKeys,
  deletingProjectKeys,
  editingProjectKeys,
  aiProjectKeys,
  actionError,
  isCreatingProject,
}: {
  projects: ProjectMemory[];
  onCreateProject: (input: CreateProjectMemoryInput) => Promise<ProjectMemory>;
  onToggleCompletion: (project: ProjectMemory, completed: boolean) => Promise<void>;
  onSaveProject: (
    project: ProjectMemory,
    input: {
      project_name: string;
      summary: string;
      status: string;
      what_is_being_built: string;
      built_for: string;
      aliases: string[];
      stage: string;
      priority: string;
      blockers: string[];
      next_steps: string[];
      evidence: string[];
    },
  ) => Promise<ProjectMemory>;
  onAssistProject: (project: ProjectMemory, instruction: string) => Promise<{ project: ProjectMemory; assistant_message: string }>;
  onDeleteProject: (project: ProjectMemory) => Promise<void>;
  savingProjectKeys: string[];
  deletingProjectKeys: string[];
  editingProjectKeys: string[];
  aiProjectKeys: string[];
  actionError: string | null;
  isCreatingProject: boolean;
}) {
  type ProjectEditDraft = {
    project_name: string;
    summary: string;
    status: string;
    what_is_being_built: string;
    built_for: string;
    aliases_text: string;
    stage: string;
    priority: string;
    blockers_text: string;
    next_steps_text: string;
    evidence_text: string;
  };

  type ProjectChatEntry = {
    id: string;
    role: "user" | "assistant";
    text: string;
  };

  const [subTab, setSubTab] = useState<"overview" | "details" | "roadmap">("overview");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [compactExpandedId, setCompactExpandedId] = useState<string | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [aiProjectId, setAiProjectId] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(projects.length === 0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "completed" | "no_steps">("all");
  const [projectDrafts, setProjectDrafts] = useState<Record<string, ProjectEditDraft>>({});
  const [projectAiDrafts, setProjectAiDrafts] = useState<Record<string, string>>({});
  const [projectAiChats, setProjectAiChats] = useState<Record<string, ProjectChatEntry[]>>({});
  const [createProjectDraft, setCreateProjectDraft] = useState<ProjectEditDraft>(() => buildEmptyProjectDraft());

  useEffect(() => {
    if (!aiProjectId) {
      return;
    }

    const handlePointerDown = (event: MouseEvent): void => {
      const target = event.target;
      if (!(target instanceof Element)) {
        closeProjectAi();
        return;
      }

      if (target.closest(`[data-project-ai-root="${aiProjectId}"]`)) {
        return;
      }

      closeProjectAi();
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [aiProjectId]);

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((left, right) => {
        const leftCompleted = isProjectManuallyCompleted(left);
        const rightCompleted = isProjectManuallyCompleted(right);
        if (leftCompleted !== rightCompleted) {
          return Number(leftCompleted) - Number(rightCompleted);
        }

        if (leftCompleted && rightCompleted) {
          const leftTime = new Date(left.manual_completed_at ?? left.updated_at).getTime();
          const rightTime = new Date(right.manual_completed_at ?? right.updated_at).getTime();
          return rightTime - leftTime;
        }

        const strengthDelta = getProjectStrength(right) - getProjectStrength(left);
        if (strengthDelta !== 0) {
          return strengthDelta;
        }

        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      }),
    [projects],
  );

  const activeProjects = useMemo(
    () => sortedProjects.filter((project) => !isProjectManuallyCompleted(project)),
    [sortedProjects],
  );
  const completedProjects = useMemo(
    () => sortedProjects.filter((project) => isProjectManuallyCompleted(project)),
    [sortedProjects],
  );
  const deferredSearch = useDeferredValue(search);
  const normalizedSearch = useMemo(() => normalizeProjectSearchText(deferredSearch.trim()), [deferredSearch]);

  const filteredProjects = useMemo(
    () =>
      sortedProjects.filter((project) => {
        const completed = isProjectManuallyCompleted(project);
        const matchesFilter =
          filter === "all"
            ? true
            : filter === "active"
              ? !completed
              : filter === "completed"
                ? completed
                : project.next_steps.length === 0;
        if (!matchesFilter) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        const haystack = normalizeProjectSearchText(
          [
            project.project_name,
            project.summary,
            project.status,
            project.what_is_being_built,
            project.built_for,
            project.manual_completion_notes,
            project.next_steps.join(" "),
            project.evidence.join(" "),
          ].join(" "),
        );
        return haystack.includes(normalizedSearch);
      }),
    [filter, normalizedSearch, sortedProjects],
  );

  const filteredActiveProjects = useMemo(
    () => filteredProjects.filter((project) => !isProjectManuallyCompleted(project)),
    [filteredProjects],
  );
  const filteredCompletedProjects = useMemo(
    () => filteredProjects.filter((project) => isProjectManuallyCompleted(project)),
    [filteredProjects],
  );

  const totalEvidence = projects.reduce((sum, project) => sum + project.evidence.length, 0);
  const openSteps = activeProjects.reduce((sum, project) => sum + project.next_steps.length, 0);
  const noStepProjects = activeProjects.filter((project) => project.next_steps.length === 0).length;
  const completionRate = projects.length > 0 ? Math.round((completedProjects.length / projects.length) * 100) : 0;
  const avgStrength =
    activeProjects.length > 0 ? Math.round(activeProjects.reduce((sum, project) => sum + getProjectStrength(project), 0) / activeProjects.length) : 0;
  const latestUpdated =
    sortedProjects.length > 0
      ? sortedProjects.reduce((latest, project) => (
          new Date(project.updated_at).getTime() > new Date(latest).getTime() ? project.updated_at : latest
        ), sortedProjects[0].updated_at)
      : null;
  const latestCompletedProject = completedProjects[0] ?? null;

  const filterOptions = [
    { id: "all" as const, label: "Todos", count: projects.length },
    { id: "active" as const, label: "Ativos", count: activeProjects.length },
    { id: "completed" as const, label: "Concluídos", count: completedProjects.length },
    { id: "no_steps" as const, label: "Sem passos", count: noStepProjects },
  ];

  const emptyLabel =
    normalizedSearch.length > 0
      ? "Nenhum projeto bateu com a busca atual."
      : filter === "completed"
        ? "Ainda não existe nenhum projeto concluído manualmente."
        : filter === "no_steps"
          ? "Todos os projetos ativos já têm próximos passos."
          : "Nada para mostrar com o filtro atual.";

  function getStageLabel(stage: string | null | undefined): string {
    const rawStage = (stage ?? "").trim();
    const normalized = rawStage.toLowerCase();
    if (normalized === "planning") return "Planejamento";
    if (normalized === "active") return "Ativo";
    if (normalized === "review") return "Revisão";
    if (normalized === "blocked") return "Bloqueado";
    if (normalized === "completed") return "Concluído";
    return rawStage || "Sem etapa";
  }

  function getPriorityLabel(priority: string | null | undefined): string {
    const rawPriority = (priority ?? "").trim();
    const normalized = rawPriority.toLowerCase();
    if (normalized === "high") return "Alta";
    if (normalized === "medium") return "Média";
    if (normalized === "low") return "Baixa";
    return rawPriority || "Sem prioridade";
  }

  function getPriorityTone(priority: string | null | undefined): "emerald" | "amber" | "indigo" | "zinc" {
    const normalized = (priority ?? "").trim().toLowerCase();
    if (normalized === "high") return "amber";
    if (normalized === "medium") return "indigo";
    if (normalized === "low") return "zinc";
    return "zinc";
  }

  function buildProjectDraft(project: ProjectMemory): ProjectEditDraft {
    return {
      project_name: project.project_name ?? "",
      summary: project.summary ?? "",
      status: project.status ?? "",
      what_is_being_built: project.what_is_being_built ?? "",
      built_for: project.built_for ?? "",
      aliases_text: Array.isArray(project.aliases) ? project.aliases.join("\n") : "",
      stage: project.stage ?? "",
      priority: project.priority ?? "",
      blockers_text: Array.isArray(project.blockers) ? project.blockers.join("\n") : "",
      next_steps_text: Array.isArray(project.next_steps) ? project.next_steps.join("\n") : "",
      evidence_text: Array.isArray(project.evidence) ? project.evidence.join("\n") : "",
    };
  }

  function buildEmptyProjectDraft(): ProjectEditDraft {
    return {
      project_name: "",
      summary: "",
      status: "",
      what_is_being_built: "",
      built_for: "",
      aliases_text: "",
      stage: "",
      priority: "",
      blockers_text: "",
      next_steps_text: "",
      evidence_text: "",
    };
  }

  function parseProjectLines(value: string): string[] {
    return value.split("\n").map((line) => line.trim()).filter(Boolean);
  }

  function toggleCreateProject(): void {
    setCreatingProject((current) => {
      const next = !current;
      if (next) {
        setCreateProjectDraft(buildEmptyProjectDraft());
      }
      return next;
    });
  }

  function openProjectEditor(project: ProjectMemory): void {
    setEditingProjectId(project.id);
    setProjectDrafts((current) => ({
      ...current,
      [project.id]: current[project.id] ?? buildProjectDraft(project),
    }));
  }

  function closeProjectEditor(): void {
    setEditingProjectId(null);
  }

  function updateProjectDraft(projectId: string, field: keyof ProjectEditDraft, value: string): void {
    setProjectDrafts((current) => ({
      ...current,
      [projectId]: {
        ...(current[projectId] ?? buildEmptyProjectDraft()),
        [field]: value,
      },
    }));
  }

  async function submitCreateProject(): Promise<void> {
    const draft = createProjectDraft;
    const projectName = draft.project_name.trim();
    const summary = draft.summary.trim();
    if (!projectName) {
      toast.error("Informe um nome para o projeto.");
      return;
    }
    if (!summary) {
      toast.error("Informe um resumo para o projeto.");
      return;
    }

    try {
      await onCreateProject({
        project_name: projectName,
        summary,
        status: draft.status.trim(),
        what_is_being_built: draft.what_is_being_built.trim(),
        built_for: draft.built_for.trim(),
        aliases: parseProjectLines(draft.aliases_text),
        stage: draft.stage.trim(),
        priority: draft.priority.trim(),
        blockers: parseProjectLines(draft.blockers_text),
        next_steps: parseProjectLines(draft.next_steps_text),
        evidence: parseProjectLines(draft.evidence_text),
      });
      setCreateProjectDraft(buildEmptyProjectDraft());
      setCreatingProject(false);
      toast.success("Projeto criado.");
    } catch {
      // Camada superior já registra e expõe erro.
    }
  }

  async function submitProjectDraft(project: ProjectMemory): Promise<void> {
    const draft = projectDrafts[project.id] ?? buildProjectDraft(project);
    const updated = await onSaveProject(project, {
      project_name: draft.project_name.trim(),
      summary: draft.summary.trim(),
      status: draft.status.trim(),
      what_is_being_built: draft.what_is_being_built.trim(),
      built_for: draft.built_for.trim(),
      aliases: parseProjectLines(draft.aliases_text),
      stage: draft.stage.trim(),
      priority: draft.priority.trim(),
      blockers: parseProjectLines(draft.blockers_text),
      next_steps: parseProjectLines(draft.next_steps_text),
      evidence: parseProjectLines(draft.evidence_text),
    });
    setProjectDrafts((current) => ({
      ...current,
      [updated.id]: buildProjectDraft(updated),
    }));
    setEditingProjectId(null);
  }

  function openProjectAi(project: ProjectMemory): void {
    setAiProjectId(project.id);
    setProjectAiDrafts((current) => ({ ...current, [project.id]: current[project.id] ?? "" }));
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: current[project.id] ?? [
        {
          id: `${project.id}-assistant-intro`,
          role: "assistant",
          text: "Descreva o que deve mudar no projeto. Eu ajusto resumo, status, público, próximos passos e evidências sem sair da aba.",
        },
      ],
    }));
  }

  function closeProjectAi(): void {
    setAiProjectId(null);
  }

  async function submitProjectAiInstruction(project: ProjectMemory): Promise<void> {
    const instruction = (projectAiDrafts[project.id] ?? "").trim();
    if (!instruction) {
      return;
    }
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: [
        ...(current[project.id] ?? []),
        { id: `${Date.now()}-${project.id}-user`, role: "user", text: instruction },
      ],
    }));
    setProjectAiDrafts((current) => ({ ...current, [project.id]: "" }));
    const response = await onAssistProject(project, instruction);
    setProjectAiChats((current) => ({
      ...current,
      [project.id]: [
        ...(current[project.id] ?? []),
        { id: `${Date.now()}-${project.id}-assistant`, role: "assistant", text: response.assistant_message },
      ],
    }));
    setProjectDrafts((current) => ({
      ...current,
      [response.project.id]: buildProjectDraft(response.project),
    }));
  }

  function renderProjectAction(project: ProjectMemory) {
    const completed = isProjectManuallyCompleted(project);
    const saving = savingProjectKeys.includes(project.project_key);
    return (
      <button
        className={completed ? "ac-secondary-button project-action-button" : "ac-success-button project-action-button"}
        disabled={saving}
        onClick={() => void onToggleCompletion(project, !completed)}
        type="button"
      >
        {saving ? <RefreshCw size={14} className="spin" /> : completed ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
        {saving ? "Salvando..." : completed ? "Reabrir projeto" : "Marcar concluído"}
      </button>
    );
  }

  function renderProjectDeleteAction(project: ProjectMemory) {
    const deleting = deletingProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button project-delete-button"
        disabled={deleting}
        onClick={() => void onDeleteProject(project)}
        type="button"
      >
        {deleting ? <RefreshCw size={14} className="spin" /> : <Trash2 size={14} />}
        {deleting ? "Excluindo..." : "Excluir"}
      </button>
    );
  }

  function renderProjectEditAction(project: ProjectMemory) {
    const editing = editingProjectId === project.id;
    const saving = editingProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button"
        disabled={saving}
        onClick={() => (editing ? closeProjectEditor() : openProjectEditor(project))}
        type="button"
      >
        {saving ? <RefreshCw size={14} className="spin" /> : <Settings size={14} />}
        {saving ? "Salvando..." : editing ? "Fechar edição" : "Editar"}
      </button>
    );
  }

  function renderProjectAiAction(project: ProjectMemory) {
    const open = aiProjectId === project.id;
    const loading = aiProjectKeys.includes(project.project_key);
    return (
      <button
        className="ac-secondary-button project-action-button project-ai-button"
        data-project-ai-root={project.id}
        disabled={loading}
        onClick={() => (open ? closeProjectAi() : openProjectAi(project))}
        type="button"
      >
        {loading ? <RefreshCw size={14} className="spin" /> : <Bot size={14} />}
        {loading ? "IA editando..." : open ? "Fechar IA" : "IA"}
      </button>
    );
  }

  function renderProjectEditor(project: ProjectMemory) {
    if (editingProjectId !== project.id) {
      return null;
    }
    const draft = projectDrafts[project.id] ?? buildProjectDraft(project);
    const saving = editingProjectKeys.includes(project.project_key);
    return (
      <div className="project-inline-editor">
        <div className="project-inline-grid">
          <label className="project-inline-field">
            <span>Nome</span>
            <input className="ac-input" type="text" value={draft.project_name} onChange={(event) => updateProjectDraft(project.id, "project_name", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Status</span>
            <input className="ac-input" type="text" value={draft.status} onChange={(event) => updateProjectDraft(project.id, "status", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Etapa</span>
            <input className="ac-input" type="text" value={draft.stage} onChange={(event) => updateProjectDraft(project.id, "stage", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Prioridade</span>
            <input className="ac-input" type="text" value={draft.priority} onChange={(event) => updateProjectDraft(project.id, "priority", event.target.value)} />
          </label>
          <label className="project-inline-field project-inline-field-full">
            <span>Resumo</span>
            <textarea className="ac-input project-inline-textarea" value={draft.summary} onChange={(event) => updateProjectDraft(project.id, "summary", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>O que está sendo construído</span>
            <textarea className="ac-input project-inline-textarea" value={draft.what_is_being_built} onChange={(event) => updateProjectDraft(project.id, "what_is_being_built", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Público</span>
            <textarea className="ac-input project-inline-textarea" value={draft.built_for} onChange={(event) => updateProjectDraft(project.id, "built_for", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Aliases</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.aliases_text} onChange={(event) => updateProjectDraft(project.id, "aliases_text", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Bloqueios</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.blockers_text} onChange={(event) => updateProjectDraft(project.id, "blockers_text", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Próximos passos</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.next_steps_text} onChange={(event) => updateProjectDraft(project.id, "next_steps_text", event.target.value)} />
          </label>
          <label className="project-inline-field">
            <span>Evidências</span>
            <textarea className="ac-input project-inline-textarea project-inline-list" value={draft.evidence_text} onChange={(event) => updateProjectDraft(project.id, "evidence_text", event.target.value)} />
          </label>
        </div>
        <div className="project-inline-actions">
          <button className="ac-primary-button" disabled={saving} onClick={() => void submitProjectDraft(project)} type="button">
            {saving ? <RefreshCw size={14} className="spin" /> : <BadgeCheck size={14} />}
            {saving ? "Salvando..." : "Salvar projeto"}
          </button>
          <button className="ac-secondary-button" disabled={saving} onClick={closeProjectEditor} type="button">
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  function renderProjectAiPanel(project: ProjectMemory) {
    if (aiProjectId !== project.id) {
      return null;
    }
    const entries = projectAiChats[project.id] ?? [];
    const draft = projectAiDrafts[project.id] ?? "";
    const loading = aiProjectKeys.includes(project.project_key);
    return (
      <div className="project-ai-panel" data-project-ai-root={project.id}>
        <div className="project-ai-messages">
          {entries.map((entry) => (
            <div key={entry.id} className={`project-ai-message project-ai-message-${entry.role}`}>
              <strong>{entry.role === "assistant" ? "IA" : "Você"}</strong>
              <p>{entry.text}</p>
            </div>
          ))}
          {loading ? (
            <div className="project-ai-loading">
              <RefreshCw size={14} className="spin" />
              <span>DeepSeek editando o projeto...</span>
            </div>
          ) : null}
        </div>
        <div className="project-ai-compose">
          <textarea
            className="ac-input project-ai-textarea"
            placeholder="Ex.: atualize o resumo, deixe o status como em validação, limpe evidências vagas e reescreva os próximos passos."
            value={draft}
            onChange={(event) => setProjectAiDrafts((current) => ({ ...current, [project.id]: event.target.value }))}
          />
          <div className="project-inline-actions">
            <button className="ac-primary-button" disabled={loading || !draft.trim()} onClick={() => void submitProjectAiInstruction(project)} type="button">
              {loading ? <RefreshCw size={14} className="spin" /> : <Send size={14} />}
              {loading ? "Editando..." : "Enviar para IA"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="page-stack">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm proj-empty-hero">
          <div className="proj-empty-icon">
            <FolderGit2 size={40} />
          </div>
          <h3>Nenhum projeto consolidado</h3>
          <p>Agora você pode criar um projeto manualmente e deixar a IA enriquecer isso depois, sem depender da primeira detecção automática da memória.</p>
          <div className="hero-actions">
            <button className="ac-primary-button" onClick={toggleCreateProject} type="button">
              <Plus size={15} />
              {creatingProject ? "Fechar criação manual" : "Novo projeto"}
            </button>
          </div>
          {creatingProject ? (
            <div className="project-inline-editor" style={{ marginTop: "1.5rem", width: "100%" }}>
              <div className="project-inline-grid">
                <label className="project-inline-field">
                  <span>Nome</span>
                  <input className="ac-input" type="text" value={createProjectDraft.project_name} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, project_name: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Status</span>
                  <input className="ac-input" type="text" value={createProjectDraft.status} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, status: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Etapa</span>
                  <input className="ac-input" type="text" value={createProjectDraft.stage} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, stage: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Prioridade</span>
                  <input className="ac-input" type="text" value={createProjectDraft.priority} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, priority: event.target.value }))} />
                </label>
                <label className="project-inline-field project-inline-field-full">
                  <span>Resumo</span>
                  <textarea className="ac-input project-inline-textarea" value={createProjectDraft.summary} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, summary: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>O que está sendo construído</span>
                  <textarea className="ac-input project-inline-textarea" value={createProjectDraft.what_is_being_built} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, what_is_being_built: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Público</span>
                  <textarea className="ac-input project-inline-textarea" value={createProjectDraft.built_for} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, built_for: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Aliases</span>
                  <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.aliases_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, aliases_text: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Bloqueios</span>
                  <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.blockers_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, blockers_text: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Próximos passos</span>
                  <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.next_steps_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, next_steps_text: event.target.value }))} />
                </label>
                <label className="project-inline-field">
                  <span>Evidências</span>
                  <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.evidence_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, evidence_text: event.target.value }))} />
                </label>
              </div>
              <div className="project-inline-actions">
                <button className="ac-primary-button" disabled={isCreatingProject} onClick={() => void submitCreateProject()} type="button">
                  {isCreatingProject ? <RefreshCw size={14} className="spin" /> : <BadgeCheck size={14} />}
                  {isCreatingProject ? "Criando..." : "Salvar projeto"}
                </button>
                <button className="ac-secondary-button" disabled={isCreatingProject} onClick={toggleCreateProject} type="button">
                  Cancelar
                </button>
              </div>
            </div>
          ) : null}
          {actionError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha ao salvar projeto</strong><p>{actionError}</p></div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm projects-hero-card">
        <div className="projects-hero-copy">
          <div className="hero-kicker">
            <Sparkles size={14} />
            Portfólio vivo do dono
          </div>
          <h3>Projetos rastreados pela memória</h3>
          <p>
            {completedProjects.length > 0
              ? `${completedProjects.length} projeto(s) já foram concluídos manualmente e seguem entrando como contexto nas próximas atualizações de memória.`
              : "Use esta aba para revisar frentes ativas, limpar o que já terminou e manter o retrato operacional coerente com a realidade."}
          </p>
        </div>
        <div className="projects-hero-metrics">
          <div className="projects-hero-metric">
            <span>Frentes ativas</span>
            <strong>{activeProjects.length}</strong>
            <small>{openSteps} próximos passos em aberto</small>
          </div>
          <div className="projects-hero-metric">
            <span>Fechamento manual</span>
            <strong>{completionRate}%</strong>
            <small>{completedProjects.length} concluído(s)</small>
          </div>
          <div className="projects-hero-metric">
            <span>Sinal médio</span>
            <strong>{avgStrength}%</strong>
            <small>{totalEvidence} evidências mapeadas</small>
          </div>
          <div className="projects-hero-metric">
            <span>Última revisão</span>
            <strong>{latestUpdated ? formatRelativeTime(latestUpdated) : "Agora"}</strong>
            <small>{latestCompletedProject ? `${latestCompletedProject.project_name} foi fechado manualmente por último` : "Sem encerramentos manuais ainda"}</small>
          </div>
        </div>
      </div>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Visão Geral", "Detalhes Completos", "Roadmap"]}
          selected={subTab === "overview" ? "Visão Geral" : subTab === "details" ? "Detalhes Completos" : "Roadmap"}
          onChange={(value: any) => {
            if (value === "Visão Geral") setSubTab("overview");
            if (value === "Detalhes Completos") setSubTab("details");
            if (value === "Roadmap") setSubTab("roadmap");
          }}
        />
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm projects-toolbar-card">
        <div className="projects-toolbar">
          <label className="project-search-shell">
            <Search size={16} />
            <input
              className="ac-input project-search-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por projeto, resumo, público, evidência..."
              type="text"
              value={search}
            />
          </label>
          <div className="project-filter-row">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`project-filter-chip${filter === option.id ? " project-filter-chip-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>
        <div className="hero-actions" style={{ marginTop: "1rem" }}>
          <button className="ac-primary-button" onClick={toggleCreateProject} type="button">
            <Plus size={14} />
            {creatingProject ? "Fechar criação" : "Novo projeto"}
          </button>
        </div>
        {creatingProject ? (
          <div className="project-inline-editor" style={{ marginTop: "1rem" }}>
            <div className="project-inline-grid">
              <label className="project-inline-field">
                <span>Nome</span>
                <input className="ac-input" type="text" value={createProjectDraft.project_name} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, project_name: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Status</span>
                <input className="ac-input" type="text" value={createProjectDraft.status} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, status: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Etapa</span>
                <input className="ac-input" type="text" value={createProjectDraft.stage} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, stage: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Prioridade</span>
                <input className="ac-input" type="text" value={createProjectDraft.priority} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, priority: event.target.value }))} />
              </label>
              <label className="project-inline-field project-inline-field-full">
                <span>Resumo</span>
                <textarea className="ac-input project-inline-textarea" value={createProjectDraft.summary} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, summary: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>O que está sendo construído</span>
                <textarea className="ac-input project-inline-textarea" value={createProjectDraft.what_is_being_built} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, what_is_being_built: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Público</span>
                <textarea className="ac-input project-inline-textarea" value={createProjectDraft.built_for} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, built_for: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Aliases</span>
                <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.aliases_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, aliases_text: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Bloqueios</span>
                <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.blockers_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, blockers_text: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Próximos passos</span>
                <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.next_steps_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, next_steps_text: event.target.value }))} />
              </label>
              <label className="project-inline-field">
                <span>Evidências</span>
                <textarea className="ac-input project-inline-textarea project-inline-list" value={createProjectDraft.evidence_text} onChange={(event) => setCreateProjectDraft((current) => ({ ...current, evidence_text: event.target.value }))} />
              </label>
            </div>
            <div className="project-inline-actions">
              <button className="ac-primary-button" disabled={isCreatingProject} onClick={() => void submitCreateProject()} type="button">
                {isCreatingProject ? <RefreshCw size={14} className="spin" /> : <BadgeCheck size={14} />}
                {isCreatingProject ? "Criando..." : "Salvar projeto"}
              </button>
              <button className="ac-secondary-button" disabled={isCreatingProject} onClick={toggleCreateProject} type="button">
                Cancelar
              </button>
            </div>
          </div>
        ) : null}
        {actionError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha ao salvar projeto</strong><p>{actionError}</p></div> : null}
      </div>

      {filteredProjects.length === 0 ? (
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
          <div className="empty-hint">
            <FolderGit2 size={18} />
            <p>{emptyLabel}</p>
          </div>
        </div>
      ) : null}

      {subTab === "overview" && filteredProjects.length > 0 ? (
        <>
          <div className="proj-stats-row">
            <ModernStatCard label="Projetos visíveis" value={String(filteredProjects.length)} meta="Resultado do filtro atual" icon={FolderGit2} tone="indigo" />
            <ModernStatCard label="Passos em aberto" value={String(filteredActiveProjects.reduce((sum, project) => sum + project.next_steps.length, 0))} meta="Somente frentes ainda ativas" icon={ChevronRight} tone="amber" />
            <ModernStatCard label="Concluídos manualmente" value={String(filteredCompletedProjects.length)} meta="Fechados por ação do usuário" icon={CheckCircle2} tone="emerald" />
            <ModernStatCard label="Sem passos" value={String(filteredActiveProjects.filter((project) => project.next_steps.length === 0).length)} meta="Precisam de mais sinal ou revisão" icon={AlertCircle} />
          </div>

          <div className="project-modern-grid">
            {filteredProjects.map((project) => {
              const completed = isProjectManuallyCompleted(project);
              const compactExpanded = compactExpandedId === project.id;
              const statusTone = getProjectStatusTone(project);
              const previewSteps = completed ? [] : project.next_steps.slice(0, compactExpanded ? 4 : 2);
              const previewEvidence = project.evidence.slice(0, compactExpanded ? 4 : 2);
              return (
                <div
                  key={`project-overview-${project.id}`}
                  className={`bg-white rounded-xl border border-zinc-200 p-6 shadow-sm project-modern-card project-modern-card-compact${completed ? " project-modern-card-completed" : ""}${compactExpanded ? " project-modern-card-expanded" : ""}${aiProjectId === project.id ? " project-card-with-ai-open" : ""}`}
                >
                  <div className="project-modern-head">
                    <div className="project-modern-title">
                      <div className={`project-modern-icon project-modern-icon-${statusTone}`}>
                        <FolderGit2 size={18} />
                      </div>
                      <div>
                        <h3>{project.project_name}</h3>
                        <p>{truncateText(project.summary, compactExpanded ? 220 : 110)}</p>
                      </div>
                    </div>
                    <div className="project-modern-actions">
                      <div className={`micro-status micro-status-${statusTone}`}>{getProjectStatusLabel(project)}</div>
                      {project.stage ? <div className="micro-status micro-status-zinc">{getStageLabel(project.stage)}</div> : null}
                      {project.priority ? <div className={`micro-status micro-status-${getPriorityTone(project.priority)}`}>{getPriorityLabel(project.priority)}</div> : null}
                      {project.origin_source === "manual" ? <div className="micro-status micro-status-zinc">Manual</div> : null}
                      <div className="project-action-row">
                        {renderProjectAiAction(project)}
                        {renderProjectEditAction(project)}
                        <button
                          className="ac-secondary-button project-action-button project-detail-toggle"
                          onClick={() => setCompactExpandedId(compactExpanded ? null : project.id)}
                          type="button"
                        >
                          {compactExpanded ? "Retrair" : "Expandir"}
                          <ChevronRight size={15} className={compactExpanded ? "proj-expand-chevron proj-expand-chevron-open" : "proj-expand-chevron"} />
                        </button>
                        {renderProjectAction(project)}
                        {renderProjectDeleteAction(project)}
                      </div>
                    </div>
                  </div>

                  {completed ? (
                    <div className="project-completion-banner">
                      <CheckCircle2 size={16} />
                      <div>
                        <strong>Conclusão manual salva</strong>
                        <p>
                          {project.manual_completed_at ? `Marcado em ${formatShortDateTime(project.manual_completed_at)}.` : "Marcado manualmente."} Esse fechamento entra nas próximas atualizações de memória.
                        </p>
                        {project.manual_completion_notes ? <small>{project.manual_completion_notes}</small> : null}
                      </div>
                    </div>
                  ) : null}

                  <ProgressBar
                    value={completed ? 100 : getProjectStrength(project)}
                    tone={completed ? "emerald" : statusTone === "amber" ? "amber" : "indigo"}
                    label={completed ? "Encerrado pelo usuário" : "Força do contexto atual"}
                  />

                  <div className="project-modern-meta">
                    <ProjectInfoBlock label="Público" value={getAudienceLabel(project)} />
                    <ProjectInfoBlock label="Construindo" value={project.what_is_being_built || "Ainda não consolidado"} />
                    <ProjectInfoBlock label="Último sinal" value={project.last_material_update_at ? formatRelativeTime(project.last_material_update_at) : project.last_seen_at ? formatRelativeTime(project.last_seen_at) : "Sem data"} />
                    <ProjectInfoBlock label="Atualizado" value={formatRelativeTime(project.updated_at)} />
                  </div>

                  <div className="project-modern-panels">
                    <div className="project-modern-panel">
                      <span>Próximos passos</span>
                      {previewSteps.length > 0 ? (
                        <ul>
                          {previewSteps.map((step, index) => (
                            <li key={`${project.id}-step-preview-${index}`}>{step}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>{completed ? "Projeto encerrado pelo usuário, sem pendências abertas." : "Nenhum próximo passo consolidado ainda."}</p>
                      )}
                    </div>
                    <div className="project-modern-panel">
                      <span>Evidências</span>
                      {previewEvidence.length > 0 ? (
                        <ul>
                          {previewEvidence.map((evidence, index) => (
                            <li key={`${project.id}-evidence-preview-${index}`}>{evidence}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>Sem evidências recentes registradas.</p>
                      )}
                    </div>
                  </div>

                  {compactExpanded ? (
                    <div className="project-modern-expand-area">
                      <div className="project-modern-panel">
                        <span>Resumo operacional</span>
                        <p>{project.what_is_being_built || "Sem descrição detalhada ainda."}</p>
                      </div>
                      {project.blockers.length > 0 ? (
                        <div className="project-modern-panel">
                          <span>Bloqueios</span>
                          <ul>
                            {project.blockers.slice(0, 3).map((blocker, index) => (
                              <li key={`${project.id}-blocker-${index}`}>{blocker}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {project.manual_completion_notes ? (
                        <div className="project-modern-panel">
                          <span>Notas de fechamento</span>
                          <p>{project.manual_completion_notes}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {renderProjectEditor(project)}
                  {renderProjectAiPanel(project)}
                </div>
              );
            })}
          </div>
        </>
      ) : null}

      {subTab === "details" && filteredProjects.length > 0 ? (
        <div className="proj-details-stack">
          {filteredProjects.map((project) => {
            const isExpanded = expandedId === project.id;
            const completed = isProjectManuallyCompleted(project);
            const statusTone = getProjectStatusTone(project);
            return (
              <div key={`project-detail-${project.id}`} className={`bg-white rounded-xl border border-zinc-200 p-6 shadow-sm project-detail-modern-card${completed ? " project-detail-modern-card-completed" : ""}${aiProjectId === project.id ? " project-card-with-ai-open" : ""}`}>
                <div className="project-detail-modern-head">
                  <div className="project-detail-modern-copy">
                    <div className="project-detail-modern-title">
                      <FolderGit2 size={18} />
                      <div>
                        <h3>{project.project_name}</h3>
                        <span>{project.project_key}</span>
                      </div>
                    </div>
                    <p>{truncateText(project.summary, isExpanded ? 320 : 170)}</p>
                  </div>
                  <div className="project-detail-modern-actions">
                    <div className={`micro-status micro-status-${statusTone}`}>{getProjectStatusLabel(project)}</div>
                    {project.stage ? <div className="micro-status micro-status-zinc">{getStageLabel(project.stage)}</div> : null}
                    {project.priority ? <div className={`micro-status micro-status-${getPriorityTone(project.priority)}`}>{getPriorityLabel(project.priority)}</div> : null}
                    {project.origin_source === "manual" ? <div className="micro-status micro-status-zinc">Manual</div> : null}
                    <div className="project-action-row">
                      {renderProjectAiAction(project)}
                      {renderProjectEditAction(project)}
                      {renderProjectAction(project)}
                      {renderProjectDeleteAction(project)}
                      <button
                        className="ac-secondary-button project-detail-toggle"
                        onClick={() => setExpandedId(isExpanded ? null : project.id)}
                        type="button"
                      >
                        {isExpanded ? "Ocultar detalhes" : "Abrir detalhes"}
                        <ChevronRight size={15} className={isExpanded ? "proj-expand-chevron proj-expand-chevron-open" : "proj-expand-chevron"} />
                      </button>
                    </div>
                  </div>
                </div>

                {completed ? (
                  <div className="project-completion-banner">
                    <CheckCircle2 size={16} />
                    <div>
                      <strong>Fechado manualmente</strong>
                      <p>
                        {project.manual_completed_at ? `O usuário marcou este projeto como concluído em ${formatShortDateTime(project.manual_completed_at)}.` : "O usuário marcou este projeto como concluído."}
                      </p>
                      {project.manual_completion_notes ? <small>{project.manual_completion_notes}</small> : null}
                    </div>
                  </div>
                ) : null}

                {isExpanded ? (
                  <div className="project-detail-modern-body">
                    <div className="proj-detail-two-col">
                      <div className="proj-detail-section">
                        <div className="proj-detail-section-title">
                          <Terminal size={14} />
                          <span>O que está sendo construído</span>
                        </div>
                        <p>{project.what_is_being_built || "Sem descrição detalhada ainda."}</p>
                      </div>
                      <div className="proj-detail-section">
                        <div className="proj-detail-section-title">
                          <User size={14} />
                          <span>Público-alvo</span>
                        </div>
                        <p>{getAudienceLabel(project)}</p>
                      </div>
                    </div>

                    {project.blockers.length > 0 ? (
                      <div className="proj-detail-section">
                        <div className="proj-detail-section-title">
                          <AlertCircle size={14} />
                          <span>Bloqueios ({project.blockers.length})</span>
                        </div>
                        <ul className="proj-evidence-list">
                          {project.blockers.map((blocker, index) => (
                            <li key={`${project.id}-detail-blocker-${index}`}>
                              <AlertCircle size={12} />
                              <span>{blocker}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <ChevronRight size={14} />
                        <span>Próximos passos ({project.next_steps.length})</span>
                      </div>
                      {project.next_steps.length > 0 ? (
                        <ul className="proj-step-list">
                          {project.next_steps.map((step, index) => (
                            <li key={`${project.id}-detail-step-${index}`}>
                              <span className="proj-step-number">{index + 1}</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">{completed ? "Projeto concluído manualmente, sem passos restantes." : "Nenhum próximo passo consolidado para este projeto."}</p>
                      )}
                    </div>

                    <div className="proj-detail-section">
                      <div className="proj-detail-section-title">
                        <CheckCircle2 size={14} />
                        <span>Evidências ({project.evidence.length})</span>
                      </div>
                      {project.evidence.length > 0 ? (
                        <ul className="proj-evidence-list">
                          {project.evidence.map((evidence, index) => (
                            <li key={`${project.id}-detail-evidence-${index}`}>
                              <CheckCircle2 size={12} />
                              <span>{evidence}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="proj-detail-empty">Nenhuma evidência recente consolidada.</p>
                      )}
                    </div>

                    <div className="proj-detail-footer-meta">
                      <div>
                        <Clock size={12} />
                        <span>Visto: {project.last_material_update_at ? formatShortDateTime(project.last_material_update_at) : project.last_seen_at ? formatShortDateTime(project.last_seen_at) : "—"}</span>
                      </div>
                      <div>
                        <RefreshCw size={12} />
                        <span>Atualizado: {formatShortDateTime(project.updated_at)}</span>
                      </div>
                    </div>
                  </div>
                ) : null}

                {renderProjectEditor(project)}
                {renderProjectAiPanel(project)}
              </div>
            );
          })}
        </div>
      ) : null}

      {subTab === "roadmap" && filteredProjects.length > 0 ? (
        <div className="proj-roadmap-container">
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Roadmap de próximos passos" icon={Zap} />
            <p className="support-copy">
              A trilha abaixo destaca apenas frentes ainda abertas. Projetos concluídos manualmente ficam separados para que o histórico continue claro sem contaminar a fila operacional.
            </p>
          </div>

          <div className="proj-roadmap-timeline">
            {filteredActiveProjects
              .filter((project) => project.next_steps.length > 0)
              .map((project) => (
                <div key={`roadmap-${project.id}`} className="proj-roadmap-project">
                  <div className="proj-roadmap-project-head">
                    <div className="proj-roadmap-dot" />
                    <div className="proj-roadmap-project-info">
                      <h4>{project.project_name}</h4>
                      <div className="proj-roadmap-meta-row">
                        <div className={`micro-status micro-status-${getProjectStatusTone(project)}`}>{getProjectStatusLabel(project)}</div>
                        <span className="proj-roadmap-strength">{getProjectStrength(project)}% sinal</span>
                      </div>
                    </div>
                    {renderProjectAction(project)}
                  </div>
                  <div className="proj-roadmap-steps">
                    {project.next_steps.map((step, index) => (
                      <div key={`${project.id}-roadmap-step-${index}`} className="proj-roadmap-step">
                        <div className="proj-roadmap-step-idx">{index + 1}</div>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                  {project.evidence.length > 0 ? (
                    <div className="proj-roadmap-evidence-block">
                      <span className="proj-roadmap-evidence-title">
                        <CheckCircle2 size={12} />
                        Evidências que sustentam
                      </span>
                      {project.evidence.slice(0, 2).map((evidence, index) => (
                        <p key={`${project.id}-roadmap-evidence-${index}`} className="proj-roadmap-evidence-text">{evidence}</p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}

            {filteredActiveProjects.filter((project) => project.next_steps.length > 0).length === 0 ? (
              <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
                <div className="empty-hint">
                  <Zap size={18} />
                  <p>Nenhum projeto ativo possui próximos passos definidos no filtro atual.</p>
                </div>
              </div>
            ) : null}
          </div>

          {filteredCompletedProjects.length > 0 ? (
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
              <SectionTitle title="Concluídos manualmente" icon={CheckCircle2} />
              <div className="project-completed-grid">
                {filteredCompletedProjects.map((project) => (
                  <div key={`completed-${project.id}`} className="project-completed-card">
                    <div className="project-completed-head">
                      <strong>{project.project_name}</strong>
                      <span>{project.manual_completed_at ? formatShortDateTime(project.manual_completed_at) : "Fechado manualmente"}</span>
                    </div>
                    <p>{truncateText(project.summary, 150)}</p>
                    <small>{project.manual_completion_notes || "Esse encerramento continua entrando como contexto nas próximas leituras de memória."}</small>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {filteredActiveProjects.filter((project) => project.next_steps.length === 0).length > 0 ? (
            <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
              <SectionTitle title="Projetos ativos sem próximos passos" icon={AlertCircle} />
              <div className="proj-roadmap-no-steps">
                {filteredActiveProjects
                  .filter((project) => project.next_steps.length === 0)
                  .map((project) => (
                    <div key={`no-steps-${project.id}`} className="proj-roadmap-no-step-item">
                      <GitBranch size={14} />
                      <span>{project.project_name}</span>
                      <span className="proj-roadmap-no-step-hint">Precisa de mais sinal</span>
                    </div>
                  ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
