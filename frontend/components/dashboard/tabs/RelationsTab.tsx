import type { PersonRelation } from '@/lib/api';
import { AlertCircle, BarChart3, Brain, Check, CheckCircle2, ChevronRight, Database, Edit2, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Search, Send, Settings, Sparkles, Terminal, User, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useDeferredValue, useMemo, useState } from 'react';

export default function RelationsTab({
  relations,
  error,
  onRefresh,
  onSaveRelation,
}: {
  relations: PersonRelation[];
  error: string | null;
  onRefresh: () => void;
  onSaveRelation: (contactName: string, input: { contact_name?: string; relationship_type?: string }) => Promise<void>;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<
    "all"
    | "with_open_loops"
    | "partner"
    | "family"
    | "friend"
    | "work"
    | "client"
        | "service"
    | "acquaintance"
    | "other"
    | "unknown"
  >("all");
  const [editingRelationId, setEditingRelationId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState("");

  const deferredSearch = useDeferredValue(search.trim());
  const normalizedSearch = useMemo(() => normalizeProjectSearchText(deferredSearch), [deferredSearch]);

  const sortedRelations = useMemo(
    () =>
      [...relations].sort((left, right) => {
        const priorityDelta = getRelationSortPriority(left.relationship_type) - getRelationSortPriority(right.relationship_type);
        if (priorityDelta !== 0) {
          return priorityDelta;
        }
        const leftTime = new Date(left.last_message_at ?? left.updated_at).getTime();
        const rightTime = new Date(right.last_message_at ?? right.updated_at).getTime();
        return rightTime - leftTime;
      }),
    [relations],
  );

  const filteredRelations = useMemo(
    () =>
      sortedRelations.filter((relation) => {
        const matchesFilter =
          filter === "all"
            ? true
            : filter === "with_open_loops"
              ? relation.open_loops.length > 0
              : normalizeRelationType(relation.relationship_type) === filter;
        if (!matchesFilter) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        const haystack = normalizeProjectSearchText(
          [
            relation.contact_name,
            relation.contact_phone ?? "",
            relation.chat_jid ?? "",
            relation.profile_summary,
            relation.relationship_summary,
            relation.relationship_type,
            relation.salient_facts.join(" "),
            relation.open_loops.join(" "),
            relation.recent_topics.join(" "),
          ].join(" "),
        );
        return haystack.includes(normalizedSearch);
      }),
    [filter, normalizedSearch, sortedRelations],
  );

  const closeCircleCount = useMemo(
    () =>
      relations.filter((relation) => {
        const type = normalizeRelationType(relation.relationship_type);
        return type === "partner" || type === "family" || type === "friend";
      }).length,
    [relations],
  );
  const operatingCircleCount = useMemo(
    () =>
      relations.filter((relation) => {
        const type = normalizeRelationType(relation.relationship_type);
        return type === "work" || type === "client" || type === "service";
      }).length,
    [relations],
  );
  const withOpenLoopsCount = useMemo(
    () => relations.filter((relation) => relation.open_loops.length > 0).length,
    [relations],
  );
  const typedCount = useMemo(
    () => relations.filter((relation) => normalizeRelationType(relation.relationship_type) !== "unknown").length,
    [relations],
  );
  const latestTouchedRelation = filteredRelations[0] ?? sortedRelations[0] ?? null;

  const filterOptions = useMemo(
    () => {
      const orderedTypes = ["partner", "family", "friend", "work", "client", "service", "acquaintance", "other", "unknown"] as const;
      const counts = new Map<string, number>();
      for (const relation of relations) {
        const type = normalizeRelationType(relation.relationship_type);
        counts.set(type, (counts.get(type) ?? 0) + 1);
      }
      const dynamicOptions = orderedTypes
        .map((type) => ({ id: type, label: getRelationTypeLabel(type), count: counts.get(type) ?? 0 }))
        .filter((option) => option.count > 0);
      return [
        { id: "all" as const, label: "Todos", count: relations.length },
        { id: "with_open_loops" as const, label: "Com pendências", count: withOpenLoopsCount },
        ...dynamicOptions,
      ];
    },
    [relations, withOpenLoopsCount],
  );

  if (relations.length === 0) {
    return (
      <div className="page-stack">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm proj-empty-hero">
          <div className="proj-empty-icon">
            <Users size={40} />
          </div>
          <h3>Nenhuma relação consolidada ainda</h3>
          <p>Depois da próxima atualização de memória, os contatos relevantes passam a aparecer aqui com tipo de vínculo, dinâmica atual, fatos duráveis e pendências abertas.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm relations-hero-card">
        <div className="relations-hero-copy">
          <div className="hero-kicker">
            <Sparkles size={14} />
            Mapa social do dono
          </div>
          <h3>Relações que a memória está consolidando</h3>
          <p>
            A cada atualização de memória, o backend refina quem é cada pessoa, qual é o tipo de vínculo e o estado atual da relação. Esta aba mostra esse retrato vivo sem depender de passos inventados.
          </p>
        </div>
        <div className="relations-hero-metrics">
          <div className="relations-hero-metric">
            <span>Pessoas mapeadas</span>
            <strong>{relations.length}</strong>
            <small>{typedCount} já têm tipo de relação claro</small>
          </div>
          <div className="relations-hero-metric">
            <span>Círculo pessoal</span>
            <strong>{closeCircleCount}</strong>
            <small>par, família e amizades</small>
          </div>
          <div className="relations-hero-metric">
            <span>Frente operacional</span>
            <strong>{operatingCircleCount}</strong>
            <small>trabalho, clientes e serviços</small>
          </div>
          <div className="relations-hero-metric">
            <span>Pendências abertas</span>
            <strong>{withOpenLoopsCount}</strong>
            <small>{latestTouchedRelation ? `último contato forte: ${latestTouchedRelation.contact_name}` : "sem destaques recentes"}</small>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm relations-toolbar-card">
        <div className="relations-toolbar">
          <label className="relation-search-shell">
            <Search size={16} />
            <input
              className="ac-input relation-search-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por nome, resumo, fatos, pendências ou tópicos..."
              type="text"
              value={search}
            />
          </label>

          <div className="relation-filter-row">
            {filterOptions.map((option) => (
              <button
                key={option.id}
                className={`relation-filter-chip${filter === option.id ? " relation-filter-chip-active" : ""}`}
                onClick={() => setFilter(option.id)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{option.count}</strong>
              </button>
            ))}
          </div>
        </div>

        {error ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha ao carregar relações</strong><p>{error}</p></div> : null}
      </div>

      <div className="proj-stats-row">
        <ModernStatCard label="Visíveis agora" value={String(filteredRelations.length)} meta="Resultado do filtro atual" icon={Users} tone="indigo" />
        <ModernStatCard label="Com pendências" value={String(filteredRelations.filter((relation) => relation.open_loops.length > 0).length)} meta="Laços que exigem acompanhamento" icon={AlertCircle} tone="amber" />
        <ModernStatCard label="Categorizadas" value={String(filteredRelations.filter((relation) => normalizeRelationType(relation.relationship_type) !== "unknown").length)} meta="Tipo de relação já inferido" icon={Fingerprint} tone="emerald" />
        <ModernStatCard label="Atualização recente" value={latestTouchedRelation?.last_analyzed_at ? formatRelativeTime(latestTouchedRelation.last_analyzed_at) : "Pendente"} meta={latestTouchedRelation ? latestTouchedRelation.contact_name : "Sem relação recente"} icon={RefreshCw} />
      </div>

      {filteredRelations.length === 0 ? (
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
          <div className="empty-hint">
            <Users size={18} />
            <p>{normalizedSearch ? "Nenhuma relação bateu com a busca atual." : "Nenhuma relação se encaixa no filtro atual."}</p>
          </div>
        </div>
      ) : (
        <div className="relation-grid">
          {filteredRelations.map((relation) => {
            const relationType = normalizeRelationType(relation.relationship_type);
            const tone = getRelationTone(relationType);
            const signalStrength = getRelationStrength(relation);
            const identifier = relation.contact_phone ?? relation.chat_jid ?? relation.person_key;
            return (
              <div key={relation.id} className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm relation-card">
                <div className="relation-card-head">
                  <div className={`project-modern-icon project-modern-icon-${tone === "rose" ? "indigo" : tone === "zinc" ? "amber" : tone}`}>
                    <User size={18} />
                  </div>
                  {editingRelationId === relation.id ? (
                    <div className="relation-card-copy" style={{ flex: 1 }}>
                      <input
                        type="text"
                        className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Nome do contato"
                        style={{ marginBottom: "0.25rem", padding: "0.25rem 0.5rem" }}
                      />
                      <div className="relation-card-meta">
                        <select
                          className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
                          value={editType}
                          onChange={(e) => setEditType(e.target.value)}
                          style={{ width: "auto", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        >
                          <option value="partner">Parceiro(a)</option>
                          <option value="family">Família</option>
                          <option value="friend">Amigo(a)</option>
                          <option value="work">Trabalho</option>
                          <option value="client">Cliente</option>
                          <option value="service">Serviço</option>
                          <option value="acquaintance">Conhecido(a)</option>
                          <option value="other">Outro</option>
                          <option value="unknown">Desconhecido</option>
                        </select>
                        <span>{identifier}</span>
                        <span>{relation.last_message_at ? formatRelativeTime(relation.last_message_at) : "sem mensagem recente"}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="relation-card-copy">
                      <h3>{relation.contact_name}</h3>
                      <div className="relation-card-meta">
                        <span className={`relation-badge relation-badge-${relationType}`}>{getRelationTypeLabel(relationType)}</span>
                        <span>{identifier}</span>
                        <span>{relation.last_message_at ? formatRelativeTime(relation.last_message_at) : "sem mensagem recente"}</span>
                      </div>
                    </div>
                  )}

                  <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
                    {editingRelationId === relation.id ? (
                      <>
                        <button
                          type="button"
                          className="ac-button ac-button-primary ac-button-sm"
                          onClick={() => {
                            void onSaveRelation(relation.contact_name, { contact_name: editName, relationship_type: editType });
                            setEditingRelationId(null);
                          }}
                        >
                          <Check size={14} />
                        </button>
                        <button
                          type="button"
                          className="ac-button ac-button-outline ac-button-sm"
                          onClick={() => setEditingRelationId(null)}
                        >
                          <X size={14} />
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="ac-button ac-button-outline ac-button-sm"
                        onClick={() => {
                          setEditingRelationId(relation.id);
                          setEditName(relation.contact_name);
                          setEditType(relationType);
                        }}
                      >
                        <Edit2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                <ProgressBar value={signalStrength} tone={tone} label="Força da memória desta relação" />

                <div className="relation-panels">
                  <div className="relation-panel">
                    <span>Quem é</span>
                    <p>{relation.profile_summary || "Ainda sem resumo consolidado."}</p>
                  </div>
                  <div className="relation-panel">
                    <span>Dinâmica atual</span>
                    <p>{relation.relationship_summary || "A dinâmica entre dono e contato ainda está sendo refinada."}</p>
                  </div>
                </div>

                <div className="relation-panels">
                  <div className="relation-panel">
                    <span>Fatos duráveis</span>
                    {relation.salient_facts.length > 0 ? (
                      <ul>
                        {relation.salient_facts.slice(0, 4).map((fact: any, index: number) => (
                          <li key={`${relation.id}-fact-${index}`}>{fact}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>Nenhum fato durável consolidado ainda.</p>
                    )}
                  </div>
                  <div className="relation-panel">
                    <span>Pendências abertas</span>
                    {relation.open_loops.length > 0 ? (
                      <ul>
                        {relation.open_loops.slice(0, 4).map((loop: any, index: number) => (
                          <li key={`${relation.id}-loop-${index}`}>{loop}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>Sem pendências abertas registradas.</p>
                    )}
                  </div>
                </div>

                <div className="relation-panel">
                  <span>Tópicos recentes</span>
                  {relation.recent_topics.length > 0 ? (
                    <div className="relation-topic-row">
                      {relation.recent_topics.slice(0, 5).map((topic: any, index: number) => (
                        <span key={`${relation.id}-topic-${index}`} className="relation-topic-chip">{topic}</span>
                      ))}
                    </div>
                  ) : (
                    <p>Sem tópicos recentes consolidados para este vínculo.</p>
                  )}
                </div>

                <div className="relation-card-footer">
                  <span>{relation.source_message_count} mensagem(ns) contribuíram para esta memória</span>
                  <strong>{relation.last_analyzed_at ? `Atualizado ${formatShortDateTime(relation.last_analyzed_at)}` : `Registrado ${formatShortDateTime(relation.updated_at)}`}</strong>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Como manter isso melhor" icon={MessageSquare} action={<button className="ac-secondary-button" onClick={onRefresh} type="button">Recarregar</button>} />
        <p className="support-copy">
          Quando você roda a próxima atualização de memória, o modelo cruza mensagens novas com esta base de pessoas. Isso melhora tipo de vínculo, fatos recorrentes, pendências e tom da relação de forma cumulativa.
        </p>
      </div>
    </div>
  );
}
