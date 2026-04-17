import { AlertCircle, BadgeCheck, BarChart3, Brain, CheckCircle2, ChevronRight, Database, Fingerprint, LockKeyhole, MessageSquare, Pause, Play, RefreshCw, Send, Settings, ShieldCheck, Terminal, Users, X, Zap } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import type { AuthenticatedAccount } from '@/lib/api';

export default function AccountTab({
  account,
  onLogout,
}: {
  account: AuthenticatedAccount;
  onLogout: () => void;
}) {
  return (
    <div className="ac-tab-content">
      <SectionTitle title="Minha Conta" icon={Fingerprint} />
      
      <div className="auth-account-dock" style={{ 
        position: 'relative', 
        bottom: 'auto', 
        right: 'auto', 
        width: '100%', 
        maxWidth: '460px', 
        margin: '24px 0',
        padding: '32px'
      }}>
        <div className="auth-account-dock-eyebrow" style={{ fontSize: '0.8rem', letterSpacing: '0.15em' }}>CONTA ATIVA</div>
        <strong style={{ fontSize: '2rem', marginTop: '8px', display: 'block' }}>@{account?.username || 'usuario'}</strong>
        <span style={{ fontSize: '1.1rem', opacity: 0.7, display: 'block', marginTop: '4px' }}>{account?.email || 'email-nao-disponivel'}</span>
        
        <div style={{ marginTop: '32px' }}>
          <button 
            className="auth-dock-button" 
            type="button" 
            onClick={onLogout} 
            style={{ 
              width: 'auto', 
              padding: '14px 48px',
              fontSize: '1rem',
              fontWeight: '500'
            }}
          >
            Sair desta conta
          </button>
        </div>
      </div>

      <div className="ac-manual-grid" style={{ marginTop: '32px' }}>
        <div className="ac-manual-card" style={{ padding: '24px' }}>
          <SectionTitle title="Segurança e Isolamento" icon={LockKeyhole} />
          <p style={{ color: 'var(--muted)', fontSize: '0.95rem', lineHeight: '1.7', marginTop: '12px' }}>
            Seu AuraCore utiliza uma arquitetura de <strong>workspace isolado</strong>. 
            Isso significa que todas as suas mensagens do WhatsApp, aprendizados de memória, 
            estatísticas e projetos estão salvos em um banco de dados SQLite local, 
            vinculado exclusivamente à sua conta Firebase <strong>@{account?.username || 'usuario'}</strong>.
          </p>
          <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
            <div className="auth-feature-pill" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
              <BadgeCheck size={14} />
              <span>Banco de dados exclusivo</span>
            </div>
            <div className="auth-feature-pill" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
              <ShieldCheck size={14} />
              <span>Sessão criptografada</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}