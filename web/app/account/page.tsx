"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Container } from "../../components/primitives";

type User = { id: string; email?: string | null };

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [busy, setBusy] = useState(false);
  const [recoveryBusy, setRecoveryBusy] = useState(false);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") === "oauth_unavailable") {
      setError("Google sign-in is temporarily unavailable. Please try again.");
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    fetch("/api/portfolio/auth", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (active && response.ok && payload.user) setUser(payload.user as User);
        if (active && response.status === 503) setError(payload.error || "Account service is unavailable.");
      })
      .catch(() => { if (active) setError("Could not reach the account service."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function signOut() {
    await fetch("/api/portfolio/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "sign-out" }),
    }).catch(() => undefined);
    setUser(null);
    setMessage("You have signed out.");
  }

  async function submitEmailAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);
    try {
      const response = await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: creatingAccount ? "sign-up" : "sign-in", email, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Authentication failed.");
      if (payload.needsEmailConfirmation) {
        setMessage(payload.message || "Check your email to confirm your account.");
        return;
      }
      if (payload.user) {
        setUser(payload.user as User);
        router.replace("/app/markets/portfolio/cloud");
      } else {
        setMessage("Check your email for the next step.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  async function requestRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setRecoveryBusy(true);
    try {
      const response = await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "recover-password", email: recoveryEmail }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Could not request a password reset.");
      setMessage("If an account exists for that email, a password-reset link will arrive shortly. Check your inbox and spam folder.");
      setShowRecovery(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not request a password reset.");
    } finally {
      setRecoveryBusy(false);
    }
  }

  return (
    <Container className="py-10 lg:py-16">
      <div className="mx-auto max-w-xl rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)] p-6 sm:p-8">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Back to Markets</Link>
        <h1 className="mt-5 text-2xl font-semibold">Your Deal Intelligence account</h1>
        <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
          Sign in to save Markets portfolios across devices or collaborate in an organization workspace. Public research pages remain available without an account.
        </p>

        {loading ? <p className="mt-6 text-sm text-[color:var(--muted)]">Checking your session…</p> : null}
        {user ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm">Signed in as <strong>{user.email || user.id}</strong>.</p>
            <Link className="btn btn-primary inline-flex" href="/app/markets/portfolio/cloud">Open cloud portfolios</Link>
            <button className="btn btn-secondary ml-2" type="button" onClick={signOut}>Sign out</button>
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <a className="btn btn-primary inline-flex w-full justify-center" href="/api/portfolio/auth/google">Continue with Google</a>
            <div className="flex items-center gap-3 text-xs text-[color:var(--muted)]"><span className="h-px flex-1 bg-[color:var(--border)]" />or use email<span className="h-px flex-1 bg-[color:var(--border)]" /></div>
            <form className="space-y-4" onSubmit={submitEmailAuth}>
              <div>
                <label className="mb-2 block text-sm" htmlFor="account-email">Email</label>
                <input id="account-email" className="field w-full" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
              <div>
                <label className="mb-2 block text-sm" htmlFor="account-password">Password</label>
                <input id="account-password" className="field w-full" type="password" autoComplete={creatingAccount ? "new-password" : "current-password"} required minLength={10} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
              </div>
              <button className="btn btn-secondary w-full justify-center" type="submit" disabled={busy}>{busy ? "Please wait…" : creatingAccount ? "Create account" : "Sign in with email"}</button>
            </form>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <button type="button" className="underline underline-offset-4" onClick={() => { setCreatingAccount((value) => !value); setError(""); setMessage(""); }}>
                {creatingAccount ? "Already have an account? Sign in" : "Create an account"}
              </button>
              {!creatingAccount ? <button type="button" className="underline underline-offset-4" onClick={() => { setShowRecovery((value) => !value); setRecoveryEmail(email); setError(""); setMessage(""); }}>Forgot password?</button> : null}
            </div>
            {showRecovery ? (
              <form className="space-y-3 rounded-xl border border-[color:var(--border)] p-4" onSubmit={requestRecovery}>
                <label className="block text-sm" htmlFor="recovery-email">Send reset link to</label>
                <input id="recovery-email" className="field w-full" type="email" autoComplete="email" required maxLength={254} value={recoveryEmail} onChange={(event) => setRecoveryEmail(event.target.value)} />
                <button className="btn btn-secondary" type="submit" disabled={recoveryBusy}>{recoveryBusy ? "Sending…" : "Send password-reset link"}</button>
              </form>
            ) : null}
            <p className="text-xs text-[color:var(--muted)]">Use a password between 10 and 128 characters. Email sign-up may require confirmation before you can sign in.</p>
          </div>
        )}

        {error ? <p role="alert" className="mt-4 text-sm text-red-400">{error}</p> : null}
        {message ? <p role="status" className="mt-4 text-sm text-[color:var(--muted)]">{message}</p> : null}
      </div>
    </Container>
  );
}
