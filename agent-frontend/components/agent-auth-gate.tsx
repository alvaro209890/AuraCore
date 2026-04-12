"use client";

import { useDeferredValue, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  createUserWithEmailAndPassword,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
  type User,
} from "firebase/auth";
import {
  ArrowRight,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

import {
  type AuthenticatedAccount,
  checkUsernameAvailability,
  getAuthMe,
  registerAuthenticatedAccount,
} from "@/lib/api";
import { ensureFirebaseAnalytics, firebaseAuth } from "@/lib/firebase";
import { GlobalAgentDashboard } from "./global-agent-dashboard";

type GatePhase = "booting" | "signed_out" | "resolving" | "needs_profile" | "ready" | "error";
type AuthTab = "login" | "register";

type AvailabilityState =
  | { state: "idle"; message: string | null }
  | { state: "checking"; message: string | null }
  | { state: "available"; message: string }
  | { state: "unavailable"; message: string };

const USERNAME_PATTERN = /^[a-z0-9_]{3,32}$/;

export function AgentAuthGate() {
  const [phase, setPhase] = useState<GatePhase>("booting");
  const [activeTab, setActiveTab] = useState<AuthTab>("login");
  const [account, setAccount] = useState<AuthenticatedAccount | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerPasswordConfirm, setRegisterPasswordConfirm] = useState("");
  const [usernameDraft, setUsernameDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [availability, setAvailability] = useState<AvailabilityState>({ state: "idle", message: null });

  const deferredUsernameDraft = useDeferredValue(usernameDraft);
  const normalizedUsernameDraft = useMemo(() => normalizeUsername(usernameDraft), [usernameDraft]);

  useEffect(() => {
    void ensureFirebaseAnalytics();
    const unsubscribe = onIdTokenChanged(firebaseAuth, (user) => {
      void resolveSession(user);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const username = deferredUsernameDraft.trim().toLowerCase();
    if (!(activeTab === "register" || phase === "needs_profile")) {
      return;
    }
    if (!username) {
      setAvailability({ state: "idle", message: null });
      return;
    }
    if (!USERNAME_PATTERN.test(username)) {
      setAvailability({
        state: "unavailable",
        message: "Use 3-32 caracteres com letras minusculas, numeros ou underscore.",
      });
      return;
    }

    let cancelled = false;
    setAvailability({ state: "checking", message: "Verificando disponibilidade..." });
    const timer = window.setTimeout(async () => {
      try {
        const result = await checkUsernameAvailability(username);
        if (cancelled) {
          return;
        }
        if (result.available) {
          setAvailability({ state: "available", message: `@${result.normalized_username} esta disponivel.` });
          return;
        }
        setAvailability({
          state: "unavailable",
          message: result.reason ?? "Esse nome de usuario ja esta em uso.",
        });
      } catch (error) {
        if (!cancelled) {
          setAvailability({
            state: "unavailable",
            message: formatUiError(error),
          });
        }
      }
    }, 260);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeTab, deferredUsernameDraft, phase]);

  async function resolveSession(user: User | null): Promise<void> {
    if (!user) {
      setAccount(null);
      setSessionError(null);
      setPhase("signed_out");
      return;
    }

    setSessionError(null);
    setPhase("resolving");
    try {
      const profile = await getAuthMe();
      setAccount(profile);
      if (profile.provisioned) {
        setUsernameDraft(profile.username ?? "");
        setPhase("ready");
        return;
      }
      setUsernameDraft((current) => current || normalizeUsername(user.displayName || user.email?.split("@")[0] || ""));
      setPhase("needs_profile");
    } catch (error) {
      setSessionError(formatUiError(error));
      setPhase("error");
    }
  }

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setSessionError(null);
    try {
      await signInWithEmailAndPassword(firebaseAuth, loginEmail.trim(), loginPassword);
    } catch (error) {
      setSessionError(formatUiError(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRegisterSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const nextUsername = normalizedUsernameDraft;
    if (!USERNAME_PATTERN.test(nextUsername)) {
      setSessionError("Escolha um nome de usuario valido.");
      return;
    }
    if (!registerEmail.trim()) {
      setSessionError("Informe um email para criar a conta.");
      return;
    }
    if (registerPassword.length < 6) {
      setSessionError("A senha precisa ter pelo menos 6 caracteres.");
      return;
    }
    if (registerPassword !== registerPasswordConfirm) {
      setSessionError("As senhas nao conferem.");
      return;
    }

    setSubmitting(true);
    setSessionError(null);
    try {
      const credential = await createUserWithEmailAndPassword(firebaseAuth, registerEmail.trim(), registerPassword);
      await updateProfile(credential.user, { displayName: nextUsername });
      await credential.user.getIdToken(true);
      const created = await registerAuthenticatedAccount(nextUsername);
      setAccount(created);
      setPhase("ready");
      setLoginEmail(registerEmail.trim());
      setRegisterPassword("");
      setRegisterPasswordConfirm("");
    } catch (error) {
      setSessionError(formatUiError(error));
      if (firebaseAuth.currentUser) {
        setPhase("needs_profile");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFinishProvisioning(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const nextUsername = normalizedUsernameDraft;
    if (!USERNAME_PATTERN.test(nextUsername)) {
      setSessionError("Escolha um nome de usuario valido antes de continuar.");
      return;
    }
    setSubmitting(true);
    setSessionError(null);
    try {
      const created = await registerAuthenticatedAccount(nextUsername);
      setAccount(created);
      setPhase("ready");
    } catch (error) {
      setSessionError(formatUiError(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout(): Promise<void> {
    setSubmitting(true);
    try {
      await signOut(firebaseAuth);
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "ready" && account) {
    return <GlobalAgentDashboard account={account} onLogout={() => void handleLogout()} />;
  }

  if (phase === "booting" || phase === "resolving") {
    return <LoadingScreen label={phase === "booting" ? "Preparando autenticacao..." : "Sincronizando sua conta..."} />;
  }

  if (phase === "needs_profile") {
    return (
      <AuthScreen
        title="Finalizar cadastro"
        subtitle="Sua conta do Firebase existe, mas o AuraCore ainda precisa reservar o username e criar o workspace local."
        error={sessionError}
      >
        <form className="agent-auth-card agent-auth-form" onSubmit={(event) => void handleFinishProvisioning(event)}>
          <label className="agent-auth-field">
            <span>Nome de usuario</span>
            <div className="agent-auth-input-shell">
              <UserRound size={18} />
              <input
                autoComplete="username"
                value={usernameDraft}
                onChange={(event) => setUsernameDraft(event.target.value)}
                placeholder="nome_do_dono"
              />
            </div>
          </label>
          <AvailabilityHint availability={availability} />
          <button className="agent-primary-button" disabled={submitting || availability.state === "checking"} type="submit">
            {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
            Criar workspace
          </button>
        </form>
      </AuthScreen>
    );
  }

  return (
    <AuthScreen
      title="Agent Hub"
      subtitle="Painel separado para conectar o numero global do agente e atender todas as contas pelo mesmo canal."
      error={sessionError}
    >
      <div className="agent-auth-tabs">
        <button
          className={`agent-auth-tab${activeTab === "login" ? " active" : ""}`}
          onClick={() => setActiveTab("login")}
          type="button"
        >
          Entrar
        </button>
        <button
          className={`agent-auth-tab${activeTab === "register" ? " active" : ""}`}
          onClick={() => setActiveTab("register")}
          type="button"
        >
          Criar conta
        </button>
      </div>

      {activeTab === "login" ? (
        <form className="agent-auth-card agent-auth-form" onSubmit={(event) => void handleLoginSubmit(event)}>
          <label className="agent-auth-field">
            <span>Email</span>
            <div className="agent-auth-input-shell">
              <Mail size={18} />
              <input
                autoComplete="email"
                inputMode="email"
                value={loginEmail}
                onChange={(event) => setLoginEmail(event.target.value)}
                placeholder="voce@empresa.com"
                type="email"
              />
            </div>
          </label>

          <label className="agent-auth-field">
            <span>Senha</span>
            <div className="agent-auth-input-shell">
              <LockKeyhole size={18} />
              <input
                autoComplete="current-password"
                value={loginPassword}
                onChange={(event) => setLoginPassword(event.target.value)}
                placeholder="Sua senha"
                type="password"
              />
            </div>
          </label>

          <button className="agent-primary-button" disabled={submitting} type="submit">
            {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
            Entrar no Agent Hub
          </button>
        </form>
      ) : (
        <form className="agent-auth-card agent-auth-form" onSubmit={(event) => void handleRegisterSubmit(event)}>
          <label className="agent-auth-field">
            <span>Nome de usuario</span>
            <div className="agent-auth-input-shell">
              <UserRound size={18} />
              <input
                autoComplete="username"
                value={usernameDraft}
                onChange={(event) => setUsernameDraft(event.target.value)}
                placeholder="nome_do_dono"
              />
            </div>
          </label>
          <AvailabilityHint availability={availability} />

          <label className="agent-auth-field">
            <span>Email</span>
            <div className="agent-auth-input-shell">
              <Mail size={18} />
              <input
                autoComplete="email"
                inputMode="email"
                value={registerEmail}
                onChange={(event) => setRegisterEmail(event.target.value)}
                placeholder="voce@empresa.com"
                type="email"
              />
            </div>
          </label>

          <label className="agent-auth-field">
            <span>Senha</span>
            <div className="agent-auth-input-shell">
              <LockKeyhole size={18} />
              <input
                autoComplete="new-password"
                value={registerPassword}
                onChange={(event) => setRegisterPassword(event.target.value)}
                placeholder="Minimo 6 caracteres"
                type="password"
              />
            </div>
          </label>

          <label className="agent-auth-field">
            <span>Confirmar senha</span>
            <div className="agent-auth-input-shell">
              <ShieldCheck size={18} />
              <input
                autoComplete="new-password"
                value={registerPasswordConfirm}
                onChange={(event) => setRegisterPasswordConfirm(event.target.value)}
                placeholder="Repita a senha"
                type="password"
              />
            </div>
          </label>

          <button className="agent-primary-button" disabled={submitting || availability.state === "checking"} type="submit">
            {submitting ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
            Criar conta
          </button>
        </form>
      )}
    </AuthScreen>
  );
}

function AuthScreen({
  title,
  subtitle,
  error,
  children,
}: {
  title: string;
  subtitle: string;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <main className="agent-auth-screen">
      <section className="agent-auth-stage">
        <div className="agent-auth-hero">
          <div className="agent-auth-pill">
            <ShieldCheck size={16} />
            Firebase Auth + roteamento por observador
          </div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
          <div className="agent-auth-note-grid">
            <article>
              <strong>Numero global</strong>
              <span>Um unico WhatsApp do agente para todas as contas.</span>
            </article>
            <article>
              <strong>Resolucao segura</strong>
              <span>Quem manda a mensagem e identificado pelo numero do observador salvo na conta.</span>
            </article>
            <article>
              <strong>Banco isolado</strong>
              <span>Cada resposta continua lendo apenas o SQLite do usuario correspondente.</span>
            </article>
          </div>
        </div>

        <div className="agent-auth-panel">
          {error ? <div className="agent-inline-error">{error}</div> : null}
          {children}
        </div>
      </section>
    </main>
  );
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="agent-auth-screen">
      <section className="agent-loading-card">
        <LoaderCircle className="spin" size={22} />
        <strong>{label}</strong>
      </section>
    </main>
  );
}

function AvailabilityHint({ availability }: { availability: AvailabilityState }) {
  if (!availability.message) {
    return <div className="agent-auth-hint">Seu username define a pasta local e o banco do usuario.</div>;
  }
  return (
    <div className={`agent-auth-hint hint-${availability.state}`}>
      {availability.message}
    </div>
  );
}

function normalizeUsername(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
}

function formatUiError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Nao foi possivel concluir a autenticacao.";
}
