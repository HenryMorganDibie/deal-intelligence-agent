"use client";

import { useState, type ReactNode } from "react";
import { passwordChecks, passwordStrength, type PasswordContext } from "../../lib/password-policy";

export { safeNext } from "../../lib/safe-next";

export async function authAction<T = Record<string, unknown>>(body: Record<string, unknown>): Promise<{ ok: boolean; status: number; data: T & { error?: string } }> {
  try {
    const response = await fetch("/api/portfolio/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await response.json().catch(() => ({}))) as T & { error?: string };
    return { ok: response.ok, status: response.status, data };
  } catch {
    return { ok: false, status: 0, data: { error: "Could not reach the account service. Check your connection." } as T & { error?: string } };
  }
}

export function AuthCard({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`mx-auto ${wide ? "max-w-2xl" : "max-w-md"} rounded-2xl border border-[color:var(--line)] bg-[color:var(--panel)] p-6 sm:p-8`}>
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </div>
  );
}

export function Notice({ error, message }: { error?: string; message?: string }) {
  return (
    <>
      {error ? <p role="alert" className="mt-4 text-sm text-risk">{error}</p> : null}
      {message ? <p role="status" className="mt-4 text-sm text-[color:var(--muted)]">{message}</p> : null}
    </>
  );
}

export function PasswordInput({ id, label, value, onChange, autoComplete, invalid = false, describedBy }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean; describedBy?: string;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div>
      <label className="mb-2 block text-sm" htmlFor={id}>{label}</label>
      <div className="relative">
        <input id={id} className="field w-full pr-16" type={shown ? "text" : "password"} autoComplete={autoComplete} required
          maxLength={128} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={invalid || undefined}
          aria-describedby={describedBy} spellCheck={false} autoCapitalize="off" />
        <button type="button" onClick={() => setShown((s) => !s)} aria-pressed={shown} aria-controls={id}
          className="absolute inset-y-0 right-2 my-auto h-7 rounded px-2 text-xs text-[color:var(--muted)] hover:text-[color:var(--text)]">
          {shown ? "Hide" : "Show"}
        </button>
      </div>
    </div>
  );
}

const METER = ["bg-risk", "bg-risk", "bg-white/50", "bg-verified", "bg-verified"];

export function PasswordStrength({ password, ctx, id }: { password: string; ctx: PasswordContext; id: string }) {
  const checks = passwordChecks(password, ctx);
  const { score, label } = passwordStrength(password, ctx);
  return (
    <div id={id} className="mt-2" aria-live="polite">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={`h-1.5 flex-1 rounded-full ${password && i < Math.max(1, score) ? METER[score] : "bg-white/10"}`} />
          ))}
        </div>
        <span className="w-24 text-right text-xs text-[color:var(--muted)]">{label}</span>
      </div>
      <ul className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
        {checks.map((c) => (
          <li key={c.id} className={c.ok ? "text-verified" : "text-[color:var(--muted)]"}>
            <span aria-hidden="true">{c.ok ? "✓" : "○"}</span> {c.label}<span className="sr-only">{c.ok ? " (met)" : " (not met)"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MatchHint({ password, confirm }: { password: string; confirm: string }) {
  if (!confirm) return null;
  const match = password === confirm;
  return <p className={`mt-1 text-xs ${match ? "text-verified" : "text-risk"}`} aria-live="polite">{match ? "✓ Passwords match" : "Passwords do not match"}</p>;
}
