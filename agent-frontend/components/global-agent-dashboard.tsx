"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Database,
  LoaderCircle,
  LogOut,
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
  getObserverStatus,
  resetGlobalAgent,
  type AuthenticatedAccount,
  type GlobalAgentStatus,
  type ObserverStatus,
} from "@/lib/api";

type DashboardProps = {
  account: AuthenticatedAccount;
  onLogout: () => void;
};

const DISCONNECTED_POLL_MS = 4000;
const CONNECTED_POLL_MS = 10000;

export function GlobalAgentDashboard({ account, onLogout }: DashboardProps) {
  const [agentStatus, setAgentStatus] = useState<GlobalAgentStatus | null>(null);
  const [observerStatus, setObserverStatus] = useState<ObserverStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<"connect" | "reset" | "refresh" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDashboard(true);
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadDashboard(false);
    }, agentStatus?.connected ? CONNECTED_POLL_MS : DISCONNECTED_POLL_MS);

    return () => window.clearInterval(interval);
  }, [agentStatus?.connected]);

  const routingPhone = observerStatus?.owner_number ?? agentStatus?.current_user_observer_phone ?? null;
  const routingReady = Boolean(agentStatus?.connected && observerStatus?.connected && routingPhone);
  const agentNumberLabel = agentStatus?.owner_number ?? "Ainda sem numero conectado";
  const observerNumberLabel = routingPhone ?? "Conecte o observador no app principal";
  const connectionLabel = useMemo(() => {
    if (!agentStatus) {
      return "Carregando";
    }
    if (agentStatus.connected) {
      return "Agente online";
    }
    return agentStatus.state === "connecting" ? "Aguardando leitura do QR" : "Sessao desligada";
  }, [agentStatus]);

  async function loadDashboard(initial: boolean): Promise<void> {
    if (initial) {
      setLoading(true);
    }
    if (!initial) {
      setBusyAction((current) => current ?? "refresh");
    }
    try {
      const [nextAgentStatus, nextObserverStatus] = await Promise.all([
        getGlobalAgentStatus(),
        getObserverStatus(false),
      ]);
      setAgentStatus(nextAgentStatus);
      setObserverStatus(nextObserverStatus);
      setError(null);
    } catch (nextError) {
      setError(formatUiError(nextError));
    } finally {
      if (initial) {
        setLoading(false);
      }
      if (!initial) {
        setBusyAction((current) => (current === "refresh" ? null : current));
      }
    }
  }

  async function handleConnect(): Promise<void> {
    setBusyAction("connect");
    try {
      const nextStatus = await connectGlobalAgent();
      setAgentStatus(nextStatus);
      setError(null);
      await loadDashboard(false);
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
      await loadDashboard(false);
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
            <p>O mesmo numero atende todas as contas. O backend resolve a conta certa pelo numero do observador conectado em cada workspace.</p>
          </div>

          <div className="agent-user-box">
            <span>@{account.username ?? "sem-username"}</span>
            <strong>{account.email}</strong>
            <button className="agent-ghost-button" onClick={onLogout} type="button">
              <LogOut size={16} />
              Sair
            </button>
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
            <strong>Carregando status do agente global...</strong>
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
                  <MetricCard icon={Smartphone} label="Seu numero observador" value={observerNumberLabel} />
                  <MetricCard icon={ShieldCheck} label="Roteamento" value={routingReady ? "Pronto" : "Pendente"} />
                  <MetricCard icon={Database} label="Modo" value="observer_owner_phone" />
                </div>

                <div className="agent-action-row">
                  <button className="agent-primary-button" disabled={busyAction === "connect"} onClick={() => void handleConnect()} type="button">
                    {busyAction === "connect" ? <LoaderCircle className="spin" size={18} /> : <QrCode size={18} />}
                    {agentStatus?.connected ? "Gerar novo QR" : "Conectar agente"}
                  </button>
                  <button className="agent-danger-button" disabled={busyAction === "reset"} onClick={() => void handleReset()} type="button">
                    {busyAction === "reset" ? <LoaderCircle className="spin" size={18} /> : <Unplug size={18} />}
                    Resetar sessao
                  </button>
                  <button className="agent-ghost-button" disabled={busyAction === "refresh"} onClick={() => void loadDashboard(false)} type="button">
                    {busyAction === "refresh" ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}
                    Atualizar
                  </button>
                </div>
              </article>

              <article className="agent-panel">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">QR do agente</span>
                    <h2>Conexao do numero unico</h2>
                  </div>
                </div>

                <div className="agent-qr-shell">
                  {agentStatus?.qr_code ? (
                    <img className="agent-qr-image" src={agentStatus.qr_code} alt="QR do agente global" />
                  ) : (
                    <div className="agent-empty-qr">
                      <QrCode size={28} />
                      <span>{agentStatus?.connected ? "A sessao ja esta online." : "Gere uma sessao para exibir o QR."}</span>
                    </div>
                  )}
                </div>
              </article>
            </section>

            <section className="agent-dashboard-grid agent-dashboard-grid-secondary">
              <article className="agent-panel">
                <div className="agent-panel-head">
                  <div>
                    <span className="agent-section-kicker">Resolucao da conta</span>
                    <h2>Como o backend encontra o banco certo</h2>
                  </div>
                </div>
                <div className="agent-rule-list">
                  <RuleRow
                    ok={Boolean(observerStatus?.connected)}
                    title="Observador da conta"
                    detail={observerStatus?.connected
                      ? `Conectado no numero ${observerStatus.owner_number ?? "desconhecido"}.`
                      : "Esta conta ainda precisa conectar o observador no app principal."}
                  />
                  <RuleRow
                    ok={Boolean(routingPhone)}
                    title="Numero usado como chave"
                    detail={routingPhone
                      ? `O numero ${routingPhone} fica salvo no registro local e serve para achar o workspace desta conta.`
                      : "Sem numero do observador salvo ainda, o agente nao consegue resolver a conta."}
                  />
                  <RuleRow
                    ok={Boolean(agentStatus?.connected && routingPhone)}
                    title="Consulta isolada"
                    detail="Quando esse mesmo numero falar com o agente global, o backend consulta apenas o SQLite deste usuario."
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
                  <StatusLine label="Observer da conta" value={observerStatus?.connected ? "online" : "offline"} />
                  <StatusLine label="Modo de roteamento" value="observer_owner_phone" />
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
