type ViewState = any;
import { StatusLine, InlineError, formatDateTime } from '../../connection-dashboard';
import { AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Clock, Database, Fingerprint, MessageSquare, Pause, Play, RefreshCw, Send, Server, Settings, Smartphone, Terminal, Users, X, XCircle, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import type { ObserverStatus} from '@/lib/api';

export default function ObserverTab({
  status,
  statusLabel,
  viewState,
  isSubmitting,
  isResetting,
  connectionError,
  onConnect,
  onReset,
}: {
  status: ObserverStatus | null;
  statusLabel: string;
  viewState: any;
  isSubmitting: boolean;
  isResetting: boolean;
  connectionError: string | null;
  onConnect: () => void;
  onReset: () => void;
}) {
  return (
    <div className="page-stack observer-page">
      <div className="observer-grid-modern">
        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm observer-qr-card">
          <SectionTitle title="Conexão WhatsApp" icon={Smartphone} />
          <p className="support-copy">Escaneie o QR para conectar o observador. A captura é restrita a contatos diretos úteis.</p>

          <div className="qr-display-shell">
            {status?.qr_code ? (
              <div className="qr-modern-frame">
                <img className="qr-modern-image" src={status.qr_code} alt="QR Code do WhatsApp observador" />
              </div>
            ) : (
              <div className="qr-modern-empty">
                <Smartphone size={28} />
                <strong>QR indisponível</strong>
                <p>
                  {status?.connected
                    ? "A sessão já está conectada. Não é necessário gerar um novo QR."
                    : "Gere uma nova sessão para exibir o QR do observador."}
                </p>
              </div>
            )}
            <div className="qr-expiry-tag">
              <Clock size={12} />
              {status?.connected ? "Sessão ativa" : status?.qr_expires_in_sec ? `Expira em ${status.qr_expires_in_sec}s` : "Sem QR ativo"}
            </div>
          </div>

          <div className="observer-actions">
            <button className="ac-primary-button" onClick={onConnect} disabled={isSubmitting || viewState === "connected"} type="button">
              <RefreshCw size={15} className={isSubmitting ? "spin" : ""} />
              {viewState === "connected" ? "Observador conectado" : isSubmitting ? "Gerando QR..." : "Gerar Novo QR"}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm observer-status-card">
          <SectionTitle title="Status da Instância" icon={Server} />

          <div className="status-line-list">
            <StatusLine label="Gateway" value={status?.gateway_ready ? "Baileys online" : "Indisponível"} tone="emerald" />
            <StatusLine label="Sessão" value={status?.owner_number ?? "Aguardando leitura"} tone="indigo" />
            <StatusLine label="Ingestão" value={status?.ingestion_ready ? "Pronta" : "Pendente"} tone="amber" />
            <StatusLine label="Última sincronização" value={formatDateTime(status?.last_seen_at)} tone="zinc" />
          </div>

          <div className="danger-box">
            <h4>
              <AlertCircle size={16} />
              Zona de perigo
            </h4>
            <p>Resetar a sessão apaga as chaves atuais e força uma nova leitura do QR Code.</p>
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50 bg-red-500 text-zinc-50 hover:bg-red-500/90 h-9 px-4 py-2" onClick={onReset} disabled={isResetting} type="button">
              <XCircle size={15} />
              {isResetting ? "Resetando..." : "Resetar Sessão Completa"}
            </button>
          </div>
        </div>
      </div>

      {connectionError ? <InlineError title={`Falha do observador (${statusLabel})`} message={connectionError} /> : null}
    </div>
  );
}
