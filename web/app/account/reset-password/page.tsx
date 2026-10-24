"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Container } from "../../../components/primitives";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function updatePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (password.length < 10 || password.length > 128) {
      setError("Use a password between 10 and 128 characters.");
      return;
    }
    if (password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "update-password", password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Could not update your password.");
      setMessage("Your password has been updated.");
      window.setTimeout(() => router.replace("/app/markets/portfolio/cloud"), 800);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Container className="py-10 lg:py-16">
      <div className="mx-auto max-w-xl rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)] p-6 sm:p-8">
        <Link href="/account" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Back to account</Link>
        <h1 className="mt-5 text-2xl font-semibold">Choose a new password</h1>
        <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">Choose a password between 10 and 128 characters. Your reset link must still be valid.</p>
        <form className="mt-6 space-y-4" onSubmit={updatePassword}>
          <div>
            <label className="mb-2 block text-sm" htmlFor="new-password">New password</label>
            <input id="new-password" className="field w-full" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          <div>
            <label className="mb-2 block text-sm" htmlFor="confirm-password">Confirm new password</label>
            <input id="confirm-password" className="field w-full" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Updating…" : "Update password"}</button>
        </form>
        {error ? <p role="alert" className="mt-4 text-sm text-red-400">{error}</p> : null}
        {message ? <p role="status" className="mt-4 text-sm text-[color:var(--muted)]">{message}</p> : null}
      </div>
    </Container>
  );
}
