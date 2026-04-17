import { StatusLine, InlineError, formatDateTime } from '../../connection-dashboard';
import { AlertCircle, BarChart3, Bot, Brain, CheckCircle2, ChevronRight, Clock, Database, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Search, Send, Server, Settings, Terminal, Users, X, XCircle, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useDeferredValue, useMemo, useState } from 'react';
type ViewState = any;
const AgentMetricPanel = (props: any) => null;
import type { WhatsAppAgentContactMemory, WhatsAppAgentMessage, WhatsAppAgentSession, WhatsAppAgentSettings, WhatsAppAgentStatus, WhatsAppAgentThread } from '@/lib/api';

export default function AgentTab({
  status,
  statusLabel,
  viewState,
  settings,
  activeSession,
  contactMemory,
  threads,
  messages,
  activeThreadId,
  isConnecting,
  isResetting,
  isSaving,
  connectionError,
  messagesError,
  onConnect,
  onReset,
  onToggleAutoReply,
  onSelectThread,
  onRefresh,
}: {
  status: WhatsAppAgentStatus | null;
  statusLabel: string;
  viewState: ViewState;
  settings: WhatsAppAgentSettings | null;
  activeSession: WhatsAppAgentSession | null;
  contactMemory: WhatsAppAgentContactMemory | null;
  threads: WhatsAppAgentThread[];
  messages: WhatsAppAgentMessage[];
  activeThreadId: string | null;
  isConnecting: boolean;
  isResetting: boolean;
  isSaving: boolean;
  connectionError: string | null;
  messagesError: string | null;
  onConnect: () => void;
  onReset: () => void;
  onToggleAutoReply: (value: boolean) => void;
  onSelectThread: (threadId: string) => void;
  onRefresh: () => void;
}) {
  const autoReplyEnabled = settings?.auto_reply_enabled ?? false;
  const replyScopeLabel = status?.reply_scope === "all_direct_contacts" ? "Todos os contatos diretos" : "Escopo legado";
  const [threadSearch, setThreadSearch] = useState("");
  const deferredThreadSearch = useDeferredValue(threadSearch);
  const normalizedThreadSearch = deferredThreadSearch.trim().toLowerCase();
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? threads[0] ?? null;
  const visibleThreads = useMemo(() => {
    if (!normalizedThreadSearch) {
      return threads;
    }
    return threads.filter((thread) => {
      const haystack = [
        thread.contact_name,
        thread.contact_phone ?? "",
        thread.chat_jid ?? "",
        thread.last_message_preview ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedThreadSearch);
    });
  }, [normalizedThreadSearch, threads]);
  const sessionStartedLabel = activeSession?.started_at ? formatDateTime(activeSession.started_at) : "Sem sessao ativa";
  const sessionLastActivityLabel = activeSession?.last_activity_at ? formatDateTime(activeSession.last_activity_at) : "Sem atividade";
  const connectedNumber = status?.owner_number ?? "Aguardando leitura";
  const connectionModeLabel = status?.connected ? "Online" : statusLabel;
  const replyModeLabel = autoReplyEnabled ? "Ativa" : "Desativada";
  const learnedCountLabel = String(contactMemory?.learned_message_count ?? 0);
  const memorySummary = contactMemory?.profile_summary?.trim()
    ? contactMemory.profile_summary.trim()
    : "Sem resumo duravel salvo ainda para este contato. Quando o dono repetir preferencias, objetivos ou restricoes, o agente passa a consolidar isso aqui.";
  const activeThreadLastTouch = activeThread?.session_last_activity_at ?? activeThread?.last_message_at ?? null;
  const activeThreadsCount = threads.filter((thread) => thread.status === "active").length;
  const totalMessagesCount = messages.length;
  const memoryHighlights = [
    ...(contactMemory?.preferences ?? []),
    ...(contactMemory?.objectives ?? []),
    ...(contactMemory?.durable_facts ?? []),
    ...(contactMemory?.recurring_instructions ?? []),
    ...(contactMemory?.constraints ?? []),
  ].slice(0, 8);

  return (
    <div className="page-stack agent-page">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm agent-command-deck">
        <div className="agent-command-copy">
          <div className="agent-command-kicker">
            <span className={`agent-state-pill${status?.connected ? " agent-state-live" : ""}`}>{connectionModeLabel}</span>
            <span className="agent-state-note">Canal ativo separado do observador</span>
          </div>
          <h2>WhatsApp Agente</h2>
          <p className="lead-copy">
            O numero secundario responde no proprio canal, com estado, memoria e historico isolados. O painel abaixo foi
            desenhado para operar rapido no desktop e continuar legivel no celular.
          </p>
          <div className="agent-hero-pills">
            <span className="agent-hero-pill">Sessao: {activeSession ? "aberta" : "aguardando"}</span>
            <span className="agent-hero-pill">Threads: {threads.length}</span>
            <span className="agent-hero-pill">Ativas: {activeThreadsCount}</span>
            <span className="agent-hero-pill">Mensagens: {totalMessagesCount}</span>
          </div>
          <div className="agent-command-actions">
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90 h-9 px-4 py-2" onClick={onConnect} disabled={isConnecting || viewState === "connected"} type="button">
              <RefreshCw size={15} className={isConnecting ? "spin" : ""} />
              {viewState === "connected" ? "Agente conectado" : isConnecting ? "Gerando QR..." : "Gerar novo QR"}
            </button>
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100 hover:text-zinc-900 h-9 px-4 py-2" onClick={onRefresh} type="button">
              <RefreshCw size={15} />
              Atualizar status
            </button>
            <button
              className={autoReplyEnabled ? "ac-danger-button" : "ac-success-button"}
              onClick={() => onToggleAutoReply(!autoReplyEnabled)}
              disabled={isSaving || !status?.connected}
              type="button"
            >
              <Bot size={15} />
              {autoReplyEnabled ? "Desativar respostas" : "Ativar respostas"}
            </button>
          </div>
        </div>

        <div className="agent-command-metrics">
          <AgentMetricPanel
            label="Numero do agente"
            value={connectedNumber}
            meta={status?.connected ? "Sessao conectada no canal secundario" : "Leia o QR para conectar"}
          />
          <AgentMetricPanel
            label="Escopo de resposta"
            value={replyScopeLabel}
            meta="Qualquer conversa direta individual pode receber resposta automatica"
          />
          <AgentMetricPanel
            label="Resposta automatica"
            value={replyModeLabel}
            meta={autoReplyEnabled ? "Groq responde no proprio WhatsApp agente" : "Fluxo em modo manual"}
          />
          <AgentMetricPanel
            label="Memoria aprendida"
            value={learnedCountLabel}
            meta={contactMemory ? "Itens relevantes guardados para este contato" : "Nada aprendido ainda"}
          />
        </div>
      </div>

      <div className="agent-workspace-grid">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm agent-connection-card">
          <div className="agent-card-heading">
            <SectionTitle title="Conexao e QR" icon={Bot} />
            <div className="agent-qr-badge">
              <Clock size={12} />
              {status?.connected ? "Sessao ativa" : status?.qr_expires_in_sec ? `Expira em ${status.qr_expires_in_sec}s` : "Sem QR ativo"}
            </div>
          </div>

          <div className="agent-connection-layout">
            <div className="agent-qr-column">
              <div className="qr-display-shell agent-qr-shell">
                {status?.qr_code ? (
                  <div className="qr-modern-frame">
                    <img className="qr-modern-image" src={status.qr_code} alt="QR Code do WhatsApp agente" />
                  </div>
                ) : (
                  <div className="qr-modern-empty">
                    <Bot size={28} />
                    <strong>QR indisponivel</strong>
                    <p>
                      {status?.connected
                        ? "A sessao ja esta conectada. Nao e necessario gerar um novo QR."
                        : "Gere uma nova sessao para exibir o QR do agente."}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="agent-connection-details">
              <p className="support-copy">
                O observador continua cuidando de memoria e ingestao. Este painel existe so para operar o canal ativo do
                agente sem misturar os dois papeis.
              </p>
              <div className="agent-status-grid">
                <StatusLine label="Gateway" value={status?.gateway_ready ? "Baileys online" : "Indisponivel"} tone="emerald" />
                <StatusLine label="Sessao" value={connectedNumber} tone="indigo" />
                <StatusLine label="Escopo de resposta" value={replyScopeLabel} tone="amber" />
                <StatusLine label="Ultima atividade" value={formatDateTime(status?.last_seen_at)} tone="zinc" />
              </div>
              <div className="agent-note-panel">
                <strong>Regra central</strong>
                <p>O agente responde qualquer conversa direta individual recebida neste numero. Grupos e mensagens do proprio numero continuam ignorados.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm agent-operations-card">
          <SectionTitle title="Operacao do agente" icon={Server} />
          <div className="agent-operations-grid">
            <div className="agent-summary-panel">
              <span>Sessao logica da conversa</span>
              <strong>{activeSession ? "Sessao aberta" : "Aguardando nova conversa"}</strong>
              <p>
                {activeSession
                  ? `Iniciada em ${sessionStartedLabel} e com ultima atividade em ${sessionLastActivityLabel}.`
                  : "Depois de 10 minutos sem conversa, o contexto reinicia e a proxima mensagem abre uma nova sessao."}
              </p>
            </div>
            <div className="agent-summary-panel">
              <span>Memoria propria do agente</span>
              <strong>{contactMemory ? "Resumo disponivel" : "Ainda sem perfil salvo"}</strong>
              <p>{memorySummary}</p>
            </div>
          </div>

          {memoryHighlights.length > 0 ? (
            <div className="agent-chip-cloud">
              {memoryHighlights.map((item, index) => (
                <span key={`${item}-${index}`} className="agent-memory-chip">{item}</span>
              ))}
            </div>
          ) : null}

          <div className="agent-danger-strip">
            <div>
              <strong>Zona de perigo</strong>
              <p>Resetar a sessao do agente apaga as chaves atuais e exige um novo QR.</p>
            </div>
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-red-500 text-zinc-50 hover:bg-red-500/90 h-9 px-4 py-2" onClick={onReset} disabled={isResetting} type="button">
              <XCircle size={15} />
              {isResetting ? "Resetando..." : "Resetar sessao do agente"}
            </button>
          </div>
        </div>
      </div>

      <div className="agent-inbox-grid">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm agent-list-card">
          <div className="agent-list-header agent-list-header-stack">
            <SectionTitle title="Conversas recentes" icon={MessageSquare} />
            <span>{visibleThreads.length} de {threads.length}</span>
          </div>
          <div className="agent-thread-search">
            <Search size={14} />
            <input
              className="flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50"
              onChange={(event) => setThreadSearch(event.target.value)}
              placeholder="Buscar por nome, telefone ou trecho"
              value={threadSearch}
              type="search"
            />
          </div>
          {threads.length === 0 ? (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Nenhuma conversa registrada ainda.</p>
            </div>
          ) : visibleThreads.length === 0 ? (
            <div className="empty-hint">
              <Search size={18} />
              <p>Nenhum contato bate com a busca atual.</p>
            </div>
          ) : (
            <div className="agent-thread-list">
              {visibleThreads.map((thread) => (
                <button
                  key={thread.id}
                  className={`agent-thread-row${thread.id === activeThread?.id ? " agent-thread-row-active" : ""}`}
                  onClick={() => onSelectThread(thread.id)}
                  type="button"
                >
                  <div className="agent-thread-main">
                    <strong>{thread.contact_name || thread.contact_phone || "Contato"}</strong>
                    <span>{thread.last_message_preview ?? "Sem mensagem recente"}</span>
                  </div>
                  <div className="agent-thread-meta">
                    <span>{thread.active_session_id ? "sessao aberta" : thread.status}</span>
                    <small>
                      {thread.session_started_at
                        ? `sessao ${formatDateTime(thread.session_started_at)}`
                        : thread.last_message_at
                          ? formatDateTime(thread.last_message_at)
                          : "Sem data"}
                    </small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm agent-detail-card">
          <div className="agent-detail-header">
            <div>
              <SectionTitle title="Historico do agente" icon={Bot} />
              <p className="support-copy">
                {activeThread
                  ? `Contato atual: ${activeThread.contact_name || activeThread.contact_phone || "Contato sem nome"}`
                  : "Selecione uma thread para abrir o historico completo do agente."}
              </p>
            </div>
            <div className="agent-detail-meta">
              <span>{activeThread?.active_session_id ? "Sessao em andamento" : "Sem sessao aberta"}</span>
              <strong>{activeThreadLastTouch ? formatDateTime(activeThreadLastTouch) : "Sem atividade"}</strong>
            </div>
          </div>

          {contactMemory ? (
            <div className="agent-memory-summary">
              <div className="agent-memory-summary-copy">
                <span>Memoria duravel desta relacao</span>
                <p>{memorySummary}</p>
              </div>
              {memoryHighlights.length > 0 ? (
                <div className="agent-chip-cloud">
                  {memoryHighlights.map((item, index) => (
                    <span key={`${item}-detail-${index}`} className="agent-memory-chip">{item}</span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {activeThread ? (
            <div className="agent-message-stack">
              {messages.length === 0 ? (
                <div className="empty-hint">
                  <MessageSquare size={18} />
                  <p>Sem mensagens ainda para esta conversa.</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`agent-message-bubble agent-message-${msg.role}`}>
                    <div className="agent-message-top">
                      <strong>{msg.role === "assistant" ? "Agente" : "Contato"}</strong>
                      <span>{formatDateTime(msg.message_timestamp)}</span>
                    </div>
                    <p>{msg.content}</p>
                    <small>{msg.processing_status}{msg.send_status ? ` | ${msg.send_status}` : ""}</small>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="empty-hint">
              <Bot size={18} />
              <p>Selecione um contato para ver as mensagens.</p>
            </div>
          )}
        </div>
      </div>

      {connectionError ? <InlineError title={`Falha do agente (${statusLabel})`} message={connectionError} /> : null}
      {messagesError ? <div className="bg-red-50 text-red-600 border border-red-200 rounded-lg p-4 mb-4"><strong>Falha nas mensagens do agente</strong><p>{messagesError}</p></div> : null}
    </div>
  );
}
