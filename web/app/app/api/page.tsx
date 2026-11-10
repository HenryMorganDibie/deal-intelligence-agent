"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Field, Loading, PageHeader } from "../../../components/app/ui";
import { PUBLIC_API_BASE, mailto } from "../../../lib/site";

type Key = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null };
type Access = {
  plan: { id: string; label: string; monthly_requests: number; max_keys: number };
  usage: { period: string; used: number; remaining: number; resets_at: string };
  keys: Key[];
  plans: { id: string; label: string; monthly_requests: number }[];
};

const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "Never";

async function call<T>(method: "GET" | "POST" | "DELETE", body?: unknown): Promise<T> {
  const r = await fetch("/api/account/api-keys", {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string }).error || "Something went wrong. Try again.");
  return data as T;
}

/** An email to the owner with what is needed to decide on an upgrade; approved from the admin page. */
function proRequestHref(): string {
  const body = [
    "Hello,",
    "",
    "I would like Pro API access for Deal Intelligence during early access.",
    "",
    "Account email: ",
    "Name and organisation: ",
    "What I will use it for (team, Slack/Teams integration, research, product): ",
    "Expected requests a month: ",
    "",
    "Thank you.",
  ].join("\n");
  return mailto("Pro API access request", body);
}

export default function ApiAccessPage() {
  const [access, setAccess] = useState<Access | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ name: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setAccess(await call<Access>("GET"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setCopied(false);
    try {
      const k = await call<{ name: string; key: string }>("POST", { name: name.trim() });
      setCreated(k);
      setName("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(k: Key) {
    if (!window.confirm(`Revoke "${k.name}"? Anything using this key stops working straight away.`)) return;
    setError("");
    try {
      await call("DELETE", { id: k.id });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const pct = access ? Math.min(100, Math.round((access.usage.used / Math.max(access.plan.monthly_requests, 1)) * 100)) : 0;
  const atKeyLimit = access ? access.keys.length >= access.plan.max_keys : false;

  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <PageHeader eyebrow="API access" title="Use Deal Intelligence from your own tools.">
        Pull deals, corporate events, investors, countries and market prices into your code, spreadsheets or internal
        bots. Watchlist alerts can go straight to Slack, Teams, Discord or Google Chat from the{" "}
        <Link href="/app/watchlists" className="underline">Alerts</Link> page. Full reference on the{" "}
        <Link href="/developers" className="underline">developer docs</Link>.
      </PageHeader>

      <p className="mb-6 rounded-xl border border-verified/30 bg-verified/[0.06] px-4 py-3 text-[0.875rem] leading-relaxed" role="note">
        <span className="font-medium text-[color:var(--text)]">Free during early access.</span>{" "}
        <span className="text-[color:var(--muted)]">Paid plans are coming soon, and everyone who joins before then gets founding-member pricing, kept for as long as they stay subscribed.</span>
      </p>

      {!access && !error && <Loading />}
      {error && <ErrorNote message={error} />}

      {access && (
        <>
          <section className="panel p-5 sm:p-6" aria-labelledby="usage-title">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 id="usage-title" className="h3">{access.plan.label} plan</h2>
              <p className="text-sm text-[color:var(--muted)]">Resets {day(access.usage.resets_at)}</p>
            </div>
            <p className="mt-3 text-[0.9375rem]">
              <span className="text-2xl font-semibold tabular-nums">{access.usage.used.toLocaleString()}</span>
              <span className="text-[color:var(--muted)]"> of {access.plan.monthly_requests.toLocaleString()} requests used this month</span>
            </p>
            <div className="mt-3 h-2 rounded-full bg-white/[0.06]" role="progressbar" aria-valuenow={access.usage.used}
              aria-valuemin={0} aria-valuemax={access.plan.monthly_requests} aria-label="Requests used this month">
              <div className={`h-2 rounded-full ${pct >= 90 ? "bg-risk" : "bg-verified"}`} style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-4 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
              Plans: {access.plans.map((p) => `${p.label} ${p.monthly_requests.toLocaleString()}`).join(" · ")} requests a month.
            </p>
            {access.plan.id === "free" && (
              <div className="mt-4 flex flex-col gap-3 border-t hairline pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-[0.875rem] text-[color:var(--muted)]">
                  Need more than 30 requests a month for a team, an integration or research? Pro is free during early access.
                </p>
                <a className="btn btn-primary h-10 shrink-0 px-4 text-sm" href={proRequestHref()}>Request Pro access</a>
              </div>
            )}
          </section>

          {created && (
            <section className="mt-6 rounded-xl border border-verified/40 bg-verified/[0.06] p-5" role="status" aria-live="polite">
              <h2 className="h3">Copy your new key now</h2>
              <p className="mt-2 text-sm text-[color:var(--muted)]">
                This is the only time &ldquo;{created.name}&rdquo; is shown in full. Store it somewhere safe, such as your
                tool&apos;s secret settings. Never put it in a web page or share it in chat.
              </p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <code className="kbd field flex items-center overflow-x-auto whitespace-nowrap">{created.key}</code>
                <button type="button" className="btn btn-primary shrink-0" onClick={() => copy(created.key)}>
                  {copied ? "Copied" : "Copy key"}
                </button>
              </div>
              <button type="button" className="mt-3 text-sm underline" onClick={() => setCreated(null)}>I have saved it</button>
            </section>
          )}

          <section className="mt-10" aria-labelledby="keys-title">
            <h2 id="keys-title" className="eyebrow">Your keys</h2>
            <ul className="mt-3 divide-y divide-white/[0.07] border-y hairline">
              {access.keys.length === 0 && <li className="py-4 text-sm text-[color:var(--muted)]">No keys yet.</li>}
              {access.keys.map((k) => (
                <li key={k.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-[0.9375rem]">{k.name}</p>
                    <p className="kbd text-[0.75rem] text-[color:var(--dim)]">
                      {k.prefix}… · created {day(k.created_at)} · last used {day(k.last_used_at)}
                    </p>
                  </div>
                  <button type="button" className="btn btn-ghost h-9 px-3 text-sm" onClick={() => revoke(k)}>Revoke</button>
                </li>
              ))}
            </ul>
            <form onSubmit={create} className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1">
                <Field label="New key name">
                  <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="Slack bot, Excel, Zapier..."
                    className="field" disabled={atKeyLimit} />
                </Field>
              </div>
              <button type="submit" className="btn btn-primary" disabled={busy || !name.trim() || atKeyLimit}>
                {busy ? "Creating..." : "Create key"}
              </button>
            </form>
            {atKeyLimit && <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">Your plan allows {access.plan.max_keys} keys. Revoke one to create another.</p>}
          </section>

          <section className="mt-10" aria-labelledby="quick-title">
            <h2 id="quick-title" className="eyebrow">Quick start</h2>
            <pre className="kbd mt-3 overflow-x-auto rounded-lg border hairline bg-white/[0.02] p-4 text-[0.8125rem] leading-relaxed">{`curl ${PUBLIC_API_BASE}/deals?country=NG&limit=5 \\
  -H "Authorization: Bearer YOUR_KEY"`}</pre>
            <p className="mt-3 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
              Every request with a key counts toward the monthly allowance, except <span className="kbd">/v1/usage</span>.
              Usage is shared by all of your keys. Each response carries <span className="kbd">X-RateLimit-Remaining</span>.
            </p>
          </section>
        </>
      )}
    </Container>
  );
}
