"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Database,
  LoaderCircle,
  MessageCircleMore,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Unplug,
} from "lucide-react";

import {
  connectGlobalAgent,
  getGlobalAgentStatus,
  resetGlobalAgent,
  type GlobalAgentStatus,
} from "@/lib/api";

const DISCONNECTED_POLL_MS = 4000;
const CONNECTED_POLL_MS = 10000;

export function GlobalAgentDashboard() {
  const [agentStatus, setAgentStatus] = useState<GlobalAgentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<"connect" | "reset" | "refresh" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bootstrapAgent();
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refreshAgentStatus();
    }, agentStatus?.connected ? CONNECTED_POLL_MS : DISCONNECTED_POLL_MS);

    return () => window.clearInterval(interval);
  }, [agentStatus?.connected]);

  const agentNumberLabel = agentStatus?.owner_number ?? "Ainda sem numero conectado";
  const mappedAccountsLabel = `${agentStatus?.mapped_accounts_count ?? 0} contas mapeadas`;
  const connectionLabel = useMemo(() => {
    if (!agentStatus) {
      return "Carregando";
    }
    if (agentStatus.connected) {
      return "Agente online";
    }
    if (agentStatus.qr_code) {
      return "QR pronto para leitura";
    }
    return agentStatus.state === "connecting" ? "Preparando QR" : "Sessao desligada";
  }, [agentStatus]);

  async function bootstrapAgent(): Promise<void> {
    setLoading(true);
    try {
      const nextStatus = await connectGlobalAgent();
      setAgentStatus(nextStatus);
      setError(null);
    } catch (nextError) {
      setError(formatUiError(nextError));
      try {
        const fallbackStatus = await getGlobalAgentStatus();
        setAgentStatus(fallbackStatus);
      } catch {
        // Keep the original error state if even the fallback fails.
      }
    } finally {
      setLoading(false);
    }
  }

  async function refreshAgentStatus(): Promise<void> {
    setBusyAction((current) => current ?? "refresh");
    try {
      const nextStatus = await getGlobalAgentStatus();
      setAgentStatus(nextStatus);
      setError(null);
    } catch (nextError) {
      setError(formatUiError(nextError));
    } finally {
      setBusyAction((current) => (current === "refresh" ? null : current));
    }
  }

  async function handleConnect(): Promise<void> {
    setBusyAction("connect");
    try {
      const nextStatus = await connectGlobalAgent();
      setAgentStatus(nextStatus);
      setError(null);
    } catch (nextError) {
      setError(formatUiError(nextError));
    } finally {
      setBusyAction(null);
    }
  }

  async function handleReset(): Promise<void> {
    setBusyAction("reset");
    try {
      const nextStatus = await resetGlobalAgent();
      setAgentStatus(nextStatus);
      setError(null);
    } catch (nextError) {
      setError(formatUiError(nextError));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <main className="agent-dashboard-shell">
      <section className="agent-dashboard-stage">
        <header className="agent-dashboard-topbar">
          <div>
            <div className="agent-auth-pill">
              <Bot size={16} />
              Canal global do agente
            </div>
            <h1>Agent Hub</h1>
            <p>Esta pagina abre direto no QR. O mesmo numero atende todas as contas e o backend resolve o banco correto pelo numero do observador salvo em cada workspace.</p>
          </div>
        </header>

        {error ? (
          <div className="agent-inline-error">
            <AlertCircle size={16} />
            {error}
          </div>
        ) : null}

        {loading ? (
          <section className="agent-loading-card">
            <LoaderCircle className="spin" size={22} />
            <strong>Preparando o QR do agente global...</strong>
          </section>
        ) : (
          <>
            <section className="agent-dashboard-grid">
              <article className="agent-panel agent-panel-highlight">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">Sessao global</span>
                    <h2>{connectionLabel}</h2>
                  </div>
                  <span className={`agent-state-pill${agentStatus?.connected ? " live" : ""}`}>
                    {agentStatus?.connected ? "Online" : "Offline"}
                  </span>
                </div>

                <div className="agent-metrics-grid">
                  <MetricCard icon={MessageCircleMore} label="Numero do agente" value={agentNumberLabel} />
                  <MetricCard icon={ShieldCheck} label="Roteamento" value="observer_owner_phone" />
                  <MetricCard icon={Database} label="Contas mapeadas" value={mappedAccountsLabel} />
                  <MetricCard icon={Smartphone} label="Persistencia" value="Banco local fora das pastas dos usuarios" />
                </div>

                <div className="agent-action-row">
                  <button className="agent-primary-button" disabled={busyAction === "connect"} onClick={() => void handleConnect()} type="button">
                    {busyAction === "connect" ? <LoaderCircle className="spin" size={18} /> : <QrCode size={18} />}
                    Atualizar QR
                  </button>
                  <button className="agent-danger-button" disabled={busyAction === "reset"} onClick={() => void handleReset()} type="button">
                    {busyAction === "reset" ? <LoaderCircle className="spin" size={18} /> : <Unplug size={18} />}
                    Resetar sessao
                  </button>
                  <button className="agent-ghost-button" disabled={busyAction === "refresh"} onClick={() => void refreshAgentStatus()} type="button">
                    {busyAction === "refresh" ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}
                    Atualizar status
                  </button>
                </div>
              </article>

              <article className="agent-panel">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">QR do agente</span>
                    <h2>Leitura instantanea</h2>
                  </div>
                </div>

                <div className="agent-qr-shell">
                  {agentStatus?.qr_code ? (
                    <img className="agent-qr-image" src={agentStatus.qr_code} alt="QR do agente global" />
                  ) : (
                    <div className="agent-empty-qr">
                      <QrCode size={28} />
                      <span>{agentStatus?.connected ? "A sessao ja esta online." : "O gateway esta gerando um novo QR agora."}</span>
                    </div>
                  )}
                </div>
              </article>
            </section>

            <section className="agent-dashboard-grid agent-dashboard-grid-secondary">
              <article className="agent-panel">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">Como funciona</span>
                    <h2>Resolucao por numero do observador</h2>
                  </div>
                </div>
                <div className="agent-rule-list">
                  <RuleRow
                    ok
                    title="Numero unico do agente"
                    detail="Este WhatsApp recebe todas as mensagens diretas no mesmo canal global."
                  />
                  <RuleRow
                    ok
                    title="Chave de roteamento"
                    detail="Quando o backend identifica o numero do observador de uma conta, ele localiza o workspace correto e consulta apenas aquele banco."
                  />
                  <RuleRow
                    ok
                    title="Persistencia separada"
                    detail="A sessao global do agente fica em um banco local fora das pastas dos usuarios, sem misturar credenciais com os workspaces individuais."
                  />
                </div>
              </article>

              <article className="agent-panel">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">Status bruto</span>
                    <h2>Leitura rapida</h2>
                  </div>
                </div>
                <div className="agent-status-list">
                  <StatusLine label="Estado do agente" value={agentStatus?.state ?? "desconhecido"} />
                  <StatusLine label="Gateway pronto" value={agentStatus?.gateway_ready ? "sim" : "nao"} />
                  <StatusLine label="Ultimo erro" value={agentStatus?.last_error ?? "nenhum"} />
                  <StatusLine label="Modo de roteamento" value="observer_owner_phone" />
                  <StatusLine label="Contas mapeadas" value={mappedAccountsLabel} />
                </div>
              </article>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Bot;
  label: string;
  value: string;
}) {
  return (
    <div className="agent-metric-card">
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RuleRow({
  ok,
  title,
  detail,
}: {
  ok: boolean;
  title: string;
  detail: string;
}) {
  return (
    <div className="agent-rule-row">
      {ok ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function StatusLine({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="agent-status-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatUiError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Nao foi possivel carregar o Agent Hub.";
}
