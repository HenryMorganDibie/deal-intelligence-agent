"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Container } from "../../components/primitives";

type User = { id: string; email?: string | null };

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

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

  return (
    <Container className="py-10 lg:py-16">
      <div className="mx-auto max-w-xl rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)] p-6 sm:p-8">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Back to Markets</Link>
        <h1 className="mt-5 text-2xl font-semibold">Your Deal Intelligence account</h1>
        <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
          Sign in with Google to save Markets portfolios across devices or collaborate in an organization workspace. Public research pages remain available without an account.
        </p>

        {loading ? <p className="mt-6 text-sm text-[color:var(--muted)]">Checking your session…</p> : null}
        {user ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm">Signed in as <strong>{user.email || user.id}</strong>.</p>
            <Link className="btn btn-primary inline-flex" href="/app/markets/portfolio/cloud">Open cloud portfolios</Link>
            <button className="btn btn-secondary ml-2" type="button" onClick={signOut}>Sign out</button>
          </div>
        ) : (
          <div className="mt-6">
            <a className="btn btn-primary inline-flex w-full justify-center" href="/api/portfolio/auth/google">Continue with Google</a>
            <p className="mt-3 text-xs text-[color:var(--muted)]">Your Google account is used to sign in. You can continue browsing public research without an account.</p>
          </div>
        )}

        {error ? <p role="alert" className="mt-4 text-sm text-red-400">{error}</p> : null}
        {message ? <p role="status" className="mt-4 text-sm text-[color:var(--muted)]">{message}</p> : null}
      </div>
    </Container>
  );
}
