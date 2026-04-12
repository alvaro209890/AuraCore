"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
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
  BadgeCheck,
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
import { ConnectionDashboard } from "./connection-dashboard";

type GatePhase = "booting" | "signed_out" | "resolving" | "needs_profile" | "ready" | "error";
type AuthTab = "login" | "register";

type AvailabilityState =
  | { state: "idle"; message: string | null }
  | { state: "checking"; message: string | null }
  | { state: "available"; message: string }
  | { state: "unavailable"; message: string };

const USERNAME_PATTERN = /^[a-z0-9_]{3,32}$/;

export function AuthGate() {
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
      setLoginPassword("");
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
    return (
      <div className="auth-workspace-shell">
        <ConnectionDashboard />
        <aside className="auth-account-dock">
          <div className="auth-account-dock-eyebrow">Conta ativa</div>
          <strong>@{account.username}</strong>
          <span>{account.email}</span>
          <button className="auth-dock-button" type="button" onClick={() => void handleLogout()}>
            Sair
          </button>
        </aside>
      </div>
    );
  }

  if (phase === "booting" || phase === "resolving") {
    return <LoadingScreen label={phase === "booting" ? "Preparando autenticacao..." : "Sincronizando sua conta..."} />;
  }

  if (phase === "needs_profile") {
    return (
      <AuthLayout
        title="Finalizar cadastro"
        subtitle="Sua conta do Firebase ja existe. Falta reservar um nome de usuario e criar o workspace isolado no backend."
        error={sessionError}
        rightPanel={
          <form className="auth-card auth-form" onSubmit={(event) => void handleFinishProvisioning(event)}>
            <label className="auth-field">
              <span>Nome de usuario</span>
              <div className="auth-input-shell">
                <UserRound size={18} />
                <input
                  value={usernameDraft}
                  onChange={(event) => setUsernameDraft(event.target.value)}
                  placeholder="seu_usuario"
                  autoComplete="nickname"
                />
              </div>
            </label>
            <AvailabilityHint availability={availability} />
            <button className="auth-primary-button" type="submit" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
              Criar workspace local
            </button>
            <button className="auth-secondary-button" type="button" onClick={() => void handleLogout()} disabled={submitting}>
              Sair desta conta
            </button>
          </form>
        }
      />
    );
  }

  if (phase === "error") {
    return (
      <AuthLayout
        title="Nao foi possivel validar a sessao"
        subtitle="A autenticacao Firebase foi concluida, mas o backend nao conseguiu sincronizar o perfil desta conta agora."
        error={sessionError}
        rightPanel={
          <div className="auth-card auth-form auth-stack">
            <button className="auth-primary-button" type="button" onClick={() => void resolveSession(firebaseAuth.currentUser)}>
              Tentar novamente
            </button>
            <button className="auth-secondary-button" type="button" onClick={() => void handleLogout()}>
              Sair
            </button>
          </div>
        }
      />
    );
  }

  return (
    <AuthLayout
      title="AuraCore"
      subtitle="Login e cadastro com Firebase Auth antes de entrar no app. Cada conta ganha seu proprio banco, memoria e sessoes do WhatsApp."
      error={sessionError}
      rightPanel={
        <div className="auth-card auth-form">
          <div className="auth-tabs" role="tablist" aria-label="Escolha como entrar">
            <button
              className={`auth-tab-button${activeTab === "login" ? " auth-tab-button-active" : ""}`}
              type="button"
              onClick={() => startTransition(() => setActiveTab("login"))}
            >
              Entrar
            </button>
            <button
              className={`auth-tab-button${activeTab === "register" ? " auth-tab-button-active" : ""}`}
              type="button"
              onClick={() => startTransition(() => setActiveTab("register"))}
            >
              Criar conta
            </button>
          </div>

          {activeTab === "login" ? (
            <form className="auth-stack" onSubmit={(event) => void handleLoginSubmit(event)}>
              <label className="auth-field">
                <span>Email</span>
                <div className="auth-input-shell">
                  <Mail size={18} />
                  <input
                    value={loginEmail}
                    onChange={(event) => setLoginEmail(event.target.value)}
                    type="email"
                    placeholder="voce@exemplo.com"
                    autoComplete="email"
                  />
                </div>
              </label>
              <label className="auth-field">
                <span>Senha</span>
                <div className="auth-input-shell">
                  <LockKeyhole size={18} />
                  <input
                    value={loginPassword}
                    onChange={(event) => setLoginPassword(event.target.value)}
                    type="password"
                    placeholder="Sua senha"
                    autoComplete="current-password"
                  />
                </div>
              </label>
              <button className="auth-primary-button" type="submit" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
                Entrar no app
              </button>
            </form>
          ) : (
            <form className="auth-stack" onSubmit={(event) => void handleRegisterSubmit(event)}>
              <label className="auth-field">
                <span>Nome de usuario</span>
                <div className="auth-input-shell">
                  <UserRound size={18} />
                  <input
                    value={usernameDraft}
                    onChange={(event) => setUsernameDraft(event.target.value)}
                    placeholder="seu_usuario"
                    autoComplete="nickname"
                  />
                </div>
              </label>
              <AvailabilityHint availability={availability} />
              <label className="auth-field">
                <span>Email</span>
                <div className="auth-input-shell">
                  <Mail size={18} />
                  <input
                    value={registerEmail}
                    onChange={(event) => setRegisterEmail(event.target.value)}
                    type="email"
                    placeholder="voce@exemplo.com"
                    autoComplete="email"
                  />
                </div>
              </label>
              <label className="auth-field">
                <span>Senha</span>
                <div className="auth-input-shell">
                  <LockKeyhole size={18} />
                  <input
                    value={registerPassword}
                    onChange={(event) => setRegisterPassword(event.target.value)}
                    type="password"
                    placeholder="Minimo de 6 caracteres"
                    autoComplete="new-password"
                  />
                </div>
              </label>
              <label className="auth-field">
                <span>Confirmar senha</span>
                <div className="auth-input-shell">
                  <ShieldCheck size={18} />
                  <input
                    value={registerPasswordConfirm}
                    onChange={(event) => setRegisterPasswordConfirm(event.target.value)}
                    type="password"
                    placeholder="Repita a senha"
                    autoComplete="new-password"
                  />
                </div>
              </label>
              <button className="auth-primary-button" type="submit" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
                Criar conta e entrar
              </button>
            </form>
          )}
        </div>
      }
    />
  );
}

function AuthLayout({
  title,
  subtitle,
  error,
  rightPanel,
}: {
  title: string;
  subtitle: string;
  error: string | null;
  rightPanel: ReactNode;
}) {
  return (
    <main className="auth-page-shell">
      <section className="auth-page-hero">
        <div className="auth-orb auth-orb-a" />
        <div className="auth-orb auth-orb-b" />
        <div className="auth-hero-copy">
          <div className="auth-hero-badge">
            <Sparkles size={16} />
            Firebase Auth + backend local isolado
          </div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
          <div className="auth-feature-list">
            <FeaturePill icon={<BadgeCheck size={16} />} text="Banco SQLite por usuario" />
            <FeaturePill icon={<ShieldCheck size={16} />} text="Username e email unicos" />
            <FeaturePill icon={<LockKeyhole size={16} />} text="Entrada protegida antes do dashboard" />
          </div>
        </div>
      </section>
      <section className="auth-page-panel">
        {error ? <div className="auth-error-banner">{error}</div> : null}
        {rightPanel}
      </section>
    </main>
  );
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="auth-page-shell auth-page-shell-loading">
      <div className="auth-loading-card">
        <LoaderCircle className="spin" size={24} />
        <strong>{label}</strong>
        <span>Conectando Firebase, token e backend local do AuraCore.</span>
      </div>
    </main>
  );
}

function FeaturePill({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="auth-feature-pill">
      {icon}
      <span>{text}</span>
    </div>
  );
}

function AvailabilityHint({ availability }: { availability: AvailabilityState }) {
  if (!availability.message) {
    return null;
  }
  return (
    <p
      className={`auth-availability-hint ${
        availability.state === "available" ? "auth-availability-hint-ok" : "auth-availability-hint-warn"
      }`}
    >
      {availability.message}
    </p>
  );
}

function normalizeUsername(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
}

function formatUiError(error: unknown): string {
  const authCode = typeof error === "object" && error !== null && "code" in error ? String(error.code) : null;
  const authMessage = typeof error === "object" && error !== null && "message" in error ? String(error.message) : null;
  if (authCode) {
    switch (authCode) {
      case "auth/email-already-in-use":
        return "Esse email ja esta em uso no Firebase.";
      case "auth/invalid-email":
        return "Email invalido.";
      case "auth/invalid-credential":
      case "auth/wrong-password":
      case "auth/user-not-found":
        return "Email ou senha invalidos.";
      case "auth/weak-password":
        return "Escolha uma senha mais forte.";
      case "auth/too-many-requests":
        return "Muitas tentativas. Aguarde um pouco e tente novamente.";
      default:
        return authMessage || "Falha ao autenticar com o Firebase.";
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Falha inesperada ao autenticar.";
}
