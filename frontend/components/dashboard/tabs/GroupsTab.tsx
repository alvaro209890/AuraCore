import { formatDateTime } from '../../connection-dashboard';
import toast from 'react-hot-toast';
import { AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Database, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Send, Settings, Terminal, Users, X, XCircle, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useDeferredValue, useMemo, useState } from 'react';
import type { WhatsAppGroupSelection } from '@/lib/api';

export default function GroupsTab({
  groups,
  error,
  isSavingJids,
  onToggleGroup,
  onRefresh,
}: {
  groups: WhatsAppGroupSelection[];
  error: string | null;
  isSavingJids: string[];
  onToggleGroup: (chatJid: string, enabledForAnalysis: boolean) => Promise<void>;
  onRefresh: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedJids, setSelectedJids] = useState<Set<string>>(new Set());
  const deferredSearch = useDeferredValue(search);
  const filteredGroups = useMemo(() => {
    let result = groups;
    if (filter === "active") result = result.filter(g => g.enabled_for_analysis);
    else if (filter === "inactive") result = result.filter(g => !g.enabled_for_analysis);
    else if (filter === "pending") result = result.filter(g => g.pending_message_count > 0);

    const query = deferredSearch.trim().toLowerCase();
    if (query) {
      result = result.filter((group) => (
        group.chat_name.toLowerCase().includes(query) ||
        group.chat_jid.toLowerCase().includes(query)
      ));
    }
    return result;
  }, [groups, deferredSearch, filter]);
  const enabledCount = groups.filter((group) => group.enabled_for_analysis).length;

  const handleSelectAll = () => {
    if (selectedJids.size === filteredGroups.length) {
      setSelectedJids(new Set());
    } else {
      setSelectedJids(new Set(filteredGroups.map(g => g.chat_jid)));
    }
  };

  const handleToggleSelection = (jid: string) => {
    const next = new Set(selectedJids);
    if (next.has(jid)) next.delete(jid);
    else next.add(jid);
    setSelectedJids(next);
  };

  const executeMassAction = async (activate: boolean) => {
    if (selectedJids.size === 0) return;
    const toastId = toast.loading("Processando...");
    try {
      const promises = Array.from(selectedJids).map(jid => {
        const group = groups.find(g => g.chat_jid === jid);
        if (group && group.enabled_for_analysis !== activate) {
          return onToggleGroup(jid, activate);
        }
        return Promise.resolve();
      });
      await Promise.all(promises);
      toast.success(`${selectedJids.size} grupo(s) modificado(s)!`, { id: toastId });
      setSelectedJids(new Set());
    } catch (e) {
      toast.error("Alguns grupos falharam.", { id: toastId });
    }
  };

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <SectionTitle title="Grupos para Analise" icon={Users} />
        <p className="support-copy">
          Os grupos abaixo aparecem sempre desativados por padrão. Ative apenas os que realmente devem entrar
          nas leituras futuras de memória.
        </p>
        <div className="groups-banner">
          <strong>Regra fixa:</strong>
          <span>A primeira analise nunca usa grupos. Esta seleção só vale para atualizações futuras da memória.</span>
        </div>
        <div className="memory-breakdown-grid">
          <MemorySignalCard
            label="Grupos observados"
            value={formatTokenCount(groups.length)}
            meta="Lista montada a partir do histórico já sincronizado pelo observador."
            tone="indigo"
          />
          <MemorySignalCard
            label="Grupos ativos"
            value={formatTokenCount(enabledCount)}
            meta="Somente estes grupos podem entrar nas leituras incrementais."
            tone="emerald"
          />
          <MemorySignalCard
            label="Pendências em grupos ativos"
            value={formatTokenCount(groups.filter((group) => group.enabled_for_analysis).reduce((sum, group) => sum + group.pending_message_count, 0))}
            meta="Mensagens de grupo elegíveis que ainda não passaram por análise."
            tone="amber"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        <div className="groups-toolbar">
          <div>
            <SectionTitle title="Selecao de Grupos" icon={Database} />
            <p className="support-copy">
              O DeepSeek passa a enxergar corretamente grupo e participante no contexto incremental, sem contaminar o bootstrap inicial.
            </p>
          </div>
          <button className="ac-secondary-button" onClick={onRefresh} type="button">
            <RefreshCw size={15} />
            Atualizar lista
          </button>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <input
            className="ac-input groups-search-input"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome do grupo ou JID..."
            type="text"
            value={search}
            style={{ flex: 1, margin: 0 }}
          />
          <SegmentedControl 
            options={["Todos", "Ativos", "Desativados", "Com Pendências"]} 
            selected={filter === "all" ? "Todos" : filter === "active" ? "Ativos" : filter === "inactive" ? "Desativados" : "Com Pendências"}
            onChange={(sel) => setFilter(sel === "Todos" ? "all" : sel === "Ativos" ? "active" : sel === "Desativados" ? "inactive" : "pending")}
          />
        </div>

        {selectedJids.size > 0 && (
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', background: 'var(--zinc-800)', padding: '0.5rem', borderRadius: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--zinc-400)', marginRight: 'auto' }}>{selectedJids.size} selecionado(s)</span>
            <button className="ac-secondary-button" onClick={() => executeMassAction(true)}>
              <CheckCircle2 size={16} style={{ color: 'var(--emerald-500)' }}/> Ativar
            </button>
            <button className="ac-secondary-button" onClick={() => executeMassAction(false)}>
              <XCircle size={16} style={{ color: 'var(--zinc-500)' }}/> Desativar
            </button>
          </div>
        )}

        {filteredGroups.length === 0 ? (
          <div className="empty-hint">
            <Users size={18} />
            <p>
              {groups.length === 0
                ? "Nenhum grupo apareceu no histórico sincronizado ainda."
                : "Nenhum grupo bateu com a busca atual."}
            </p>
          </div>
        ) : (
          <div className="groups-list">
            {filteredGroups.map((group) => {
              const isSaving = isSavingJids.includes(group.chat_jid);
              return (
                <div key={group.chat_jid} className={`group-row${group.enabled_for_analysis ? " group-row-enabled" : ""}`}>
                  <input
                    type="checkbox"
                    checked={selectedJids.has(group.chat_jid)}
                    onChange={() => handleToggleSelection(group.chat_jid)}
                    style={{ marginRight: '1rem', cursor: 'pointer', color: 'var(--indigo-500)', width: '18px', height: '18px' }}
                  />
                  <div className="group-row-main" style={{ marginLeft: '1rem' }}>
                    <div className="group-row-top">
                      <strong>{group.chat_name}</strong>
                      <span>{group.enabled_for_analysis ? "ativo para analise" : "desativado"}</span>
                    </div>
                    <p>{group.chat_jid}</p>
                    <div className="group-row-meta">
                      <span>{formatTokenCount(group.message_count)} mensagens salvas</span>
                      <span>{formatTokenCount(group.pending_message_count)} pendentes</span>
                      <span>{group.last_message_at ? `Ultima mensagem ${formatDateTime(group.last_message_at)}` : "Sem mensagem recente"}</span>
                    </div>
                  </div>
                  <button
                    className={`group-toggle${group.enabled_for_analysis ? " group-toggle-enabled" : ""}`}
                    disabled={isSaving}
                    onClick={() => {
                      if (!isSaving) {
                        onToggleGroup(group.chat_jid, !group.enabled_for_analysis);
                        toast.success(group.enabled_for_analysis ? "Grupo desativado" : "Grupo ativado");
                      }
                    }}
                    type="button"
                  >
                    {isSaving ? <span className="ac-spinner" style={{ marginRight: 8, width: 14, height: 14 }} /> : null}
                    <span>{group.enabled_for_analysis ? "Ativado" : "Ativar"}</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {error ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha ao carregar grupos</strong><p>{error}</p></div> : null}
    </div>
  );
}
