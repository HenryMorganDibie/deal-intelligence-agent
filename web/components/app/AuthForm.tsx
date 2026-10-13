"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { isAuthConfigured, safeNext, startOAuth, supabase, type OAuthProvider } from "../../lib/supabase";
import { GitHubMark } from "../primitives";

const PROVIDERS: Array<{ id: OAuthProvider; label: string }> = [
  { id: "github", label: "Continue with GitHub" },
  { id: "google", label: "Continue with Google" },
];

function GoogleMark() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4">
      <path fill="#EA4335" d="M8 6.5v3.1h4.3c-.2 1-1.3 3-4.3 3a4.6 4.6 0 010-9.2c1.4 0 2.4.6 2.9 1.1l2-1.9A7.2 7.2 0 008 .8a7.2 7.2 0 100 14.4c4.2 0 6.9-2.9 6.9-7 0-.5 0-.8-.1-1.2H8z" />
    </svg>
  );
}

/** GitHub, Google, or email and password. `next` is where the user lands afterwards. */
export function AuthForm({ next }: { next: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!isAuthConfigured) {
    return (
      <p className="panel p-4 text-sm text-[color:var(--muted)]" role="status">
        Sign-in is not configured on this deployment yet.
      </p>
    );
  }

  async function oauth(provider: OAuthProvider) {
    setError(null);
    setNotice(null);
    setPending(provider);
    try {
      await startOAuth(provider, next);
    } catch (err) {
      setPending(null);
      const msg = err instanceof Error ? err.message : "";
      setError(
        /provider is not enabled/i.test(msg)
          ? `${provider === "github" ? "GitHub" : "Google"} sign-in is not enabled yet. Use email and password instead.`
          : "We couldn't start sign-in. Please try again.",
      );
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setPending("email");
    const auth = supabase().auth;
    try {
      if (mode === "signin") {
        const { error: err } = await auth.signInWithPassword({ email, password });
        if (err) throw err;
        router.replace(safeNext(next));
        return;
      }
      const emailRedirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext(next))}`;
      const { data, error: err } = await auth.signUp({ email, password, options: { emailRedirectTo } });
      if (err) throw err;
      if (data.session) {
        router.replace(safeNext(next));
        return;
      }
      setNotice("Check your inbox for a confirmation link, then come back and sign in.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setError(
        /invalid login credentials/i.test(msg)
          ? "That email and password do not match an account."
          : /email not confirmed/i.test(msg)
            ? "Confirm your email first. The link is in your inbox."
            : /already registered/i.test(msg)
              ? "An account with that email already exists. Sign in instead."
              : msg || "Something went wrong. Please try again.",
      );
    } finally {
      setPending((p) => (p === "email" ? null : p));
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2.5">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => oauth(p.id)}
            disabled={pending !== null}
            className="btn btn-ghost w-full disabled:opacity-50"
          >
            {p.id === "github" ? <GitHubMark /> : <GoogleMark />}
            {pending === p.id ? "Redirecting..." : p.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3" aria-hidden>
        <span className="h-px flex-1 bg-white/10" />
        <span className="eyebrow">or</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Password</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field"
          />
        </label>
        <button type="submit" disabled={pending !== null} className="btn btn-primary w-full disabled:opacity-50">
          {pending === "email" ? "Working..." : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </form>

      {error && (
        <p className="text-sm text-risk" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="text-sm text-verified" role="status">
          {notice}
        </p>
      )}

      <p className="text-center text-sm text-[color:var(--muted)]">
        {mode === "signin" ? "New here? " : "Already have an account? "}
        <button
          type="button"
          className="text-[color:var(--text)] underline decoration-white/30 underline-offset-4 hover:decoration-white"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
            setNotice(null);
          }}
        >
          {mode === "signin" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
