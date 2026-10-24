"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Container } from "../../components/primitives";

type User = { id: string; email?: string | null };

export default function AccountPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: mode, email, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 202 && payload.needsEmailConfirmation) {
        setMessage(payload.message || "Check your email to confirm your account, then sign in.");
      } else if (!response.ok) {
        setError(payload.error || "Could not complete authentication.");
      } else {
        router.push("/app/markets/portfolio/cloud");
        router.refresh();
      }
    } catch {
      setError("Could not reach the account service.");
    } finally {
      setSubmitting(false);
    }
  }

  async function signOut() {
    await fetch("/api/portfolio/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "sign-out" }),
    }).catch(() => undefined);
    setUser(null);
    setMessage("You have signed out.");
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
          <form className="mt-6 space-y-4" onSubmit={submit}>
            <label className="block text-sm">
              Email
              <input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label className="block text-sm">
              Password
              <input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="password" autoComplete={mode === "sign-up" ? "new-password" : "current-password"} minLength={10} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
              <span className="mt-1 block text-xs text-[color:var(--muted)]">Use at least 10 characters.</span>
            </label>
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "Please wait…" : mode === "sign-in" ? "Sign in" : "Create account"}</button>
              <button className="btn btn-secondary" type="button" disabled={submitting} onClick={() => { setMode(mode === "sign-in" ? "sign-up" : "sign-in"); setError(""); setMessage(""); }}>
                {mode === "sign-in" ? "Create an account" : "I already have an account"}
              </button>
            </div>
          </form>
        )}

        {error ? <p role="alert" className="mt-4 text-sm text-red-400">{error}</p> : null}
        {message ? <p role="status" className="mt-4 text-sm text-[color:var(--muted)]">{message}</p> : null}
      </div>
    </Container>
  );
}
