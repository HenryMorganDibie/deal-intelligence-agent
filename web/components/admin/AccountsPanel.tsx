"use client";

import { useEffect, useMemo, useState } from "react";

type Account = {
  email: string;
  username: string | null;
  display_name: string | null;
  created_at: string;
  confirmed: boolean;
  last_sign_in_at: string | null;
  last_seen_at: string | null;
  active_days: number;
  providers: string[];
  two_factor: boolean;
  email_alerts: number;
  plan?: string;
  api_used?: number;
  api_keys?: number;
  suspended?: boolean;
  suspension_reason?: string | null;
  subscription_status?: string | null;
};
type LogEntry = { at: string; action: "suspended" | "reinstated" | "deleted" | "anonymised"; account: string; reason: string };
type Pending = { kind: "suspend" | "reinstate" | "delete"; account: Account };
type Plan = { id: string; label: string; monthly_requests: number };
type AccountStats = {
  since: string;
  days: number;
  totals: Record<string, number>;
  daily: { day: string; signups: number; active: number }[];
  accounts: Account[];
  plans?: Plan[];
};

import { apiUrl } from "../../lib/api-base";

function when(value: string | null): string {
  if (!value) return "never";
  const t = new Date(value);
  const days = Math.floor((Date.now() - t.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 31) return `${days} days ago`;
  return t.toISOString().slice(0, 10);
}

/** Who has an account and who is using the app. Activity is recorded at most once per 30 minutes per account. */
type Trouble = {
  email: string | null; attempts: number; first_at: string; last_at: string; actions: string[];
  last_reason: string; reasons: string[]; has_account: boolean; confirmed: boolean; signed_in_since: boolean;
};

export function AccountsPanel({ adminKey, days }: { adminKey: string; days: number }) {
  const [data, setData] = useState<AccountStats | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "never" | "unconfirmed" | "suspended">("all");
  const [pending, setPending] = useState<Pending | null>(null);
  const [log, setLog] = useState<LogEntry[] | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [planNote, setPlanNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [trouble, setTrouble] = useState<Trouble[] | null>(null);
  const [troubleError, setTroubleError] = useState("");
  const [helping, setHelping] = useState<string | null>(null);

  /** Send a password-reset link or the confirmation email again, through the site's own sender. */
  async function help(email: string, action: "reset" | "confirm") {
    setHelping(email + action);
    setPlanNote(null);
    try {
      const r = await fetch(apiUrl("/api/admin/accounts/help"), {
        method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
        body: JSON.stringify({ key: adminKey, email, action }),
      });
      const body = (await r.json().catch(() => ({}))) as { detail?: string; sent?: string };
      if (!r.ok) throw new Error(body.detail || "The email could not be sent.");
      setPlanNote({ ok: true, text: `Sent ${email} a ${body.sent}.` });
    } catch (e) {
      setPlanNote({ ok: false, text: (e as Error).message });
    } finally {
      setHelping(null);
    }
  }

  useEffect(() => {
    if (!adminKey) return;
    fetch(apiUrl("/api/admin/auth-trouble"), {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify({ key: adminKey, days: 14 }),
    })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error((body as { detail?: string }).detail || "Sign-in trouble is unavailable.");
        setTrouble(body as Trouble[]);
      })
      .catch((e: Error) => setTroubleError(e.message));
  }, [adminKey]);

  async function changePlan(account: Account, plan: string) {
    const label = data?.plans?.find((p) => p.id === plan)?.label ?? plan;
    if (!window.confirm(`Move ${account.email} to the ${label} plan? Their monthly API allowance changes straight away.`)) return;
    setSaving(account.email);
    setPlanNote(null);
    try {
      const r = await fetch(apiUrl("/api/admin/plan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: adminKey, email: account.email, plan }),
        cache: "no-store",
      });
      if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : r.status === 404 ? "That account or plan no longer exists" : "The plan could not be changed");
      setData((d) => d && { ...d, accounts: d.accounts.map((a) => (a.email === account.email ? { ...a, plan } : a)) });
      setPlanNote({ ok: true, text: `${account.email} is now on ${label}.` });
    } catch (e) {
      setPlanNote({ ok: false, text: (e as Error).message });
    } finally {
      setSaving(null);
    }
  }

  const loadLog = () => {
    fetch(apiUrl("/api/admin/accounts/log"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: adminKey }), cache: "no-store",
    }).then(async (r) => setLog(r.ok ? ((await r.json()) as LogEntry[]) : [])).catch(() => setLog([]));
  };
  useEffect(() => { if (adminKey) loadLog(); }, [adminKey]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Apply a suspension, reinstatement or deletion confirmed in the dialog, and update the table in place. */
  async function moderate(p: Pending, reason: string, confirm: string): Promise<string | null> {
    const del = p.kind === "delete";
    const r = await fetch(apiUrl(del ? "/api/admin/accounts/delete" : "/api/admin/accounts/suspend"), {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify(del ? { key: adminKey, email: p.account.email, confirm, reason }
        : { key: adminKey, email: p.account.email, suspend: p.kind === "suspend", reason }),
    });
    const body = (await r.json().catch(() => ({}))) as { detail?: string; warning?: string | null; renewal?: string | null; result?: string };
    if (!r.ok) return body.detail || (r.status === 401 ? "Wrong key" : "That did not work. Nothing was changed.");
    const email = p.account.email;
    setData((d) => d && {
      ...d,
      accounts: del ? d.accounts.filter((a) => a.email !== email)
        : d.accounts.map((a) => (a.email === email ? { ...a, suspended: p.kind === "suspend", suspension_reason: p.kind === "suspend" ? reason : null } : a)),
    });
    const renewal = body.renewal === "cancelled" ? " Their Paystack renewal was cancelled." : "";
    setPlanNote({
      ok: !body.warning,
      text: body.warning ?? (del ? `${email} was ${body.result === "anonymised" ? "erased (kept as an anonymous record because it owns shared portfolio data)" : "deleted"}.${renewal}`
        : p.kind === "suspend" ? `${email} is suspended.${renewal}` : `${email} is reinstated.`),
    });
    setPending(null);
    loadLog();
    return null;
  }

  useEffect(() => {
    if (!adminKey) return;
    setError("");
    fetch(apiUrl("/api/admin/accounts"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: adminKey, days }),
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "Account statistics unavailable");
        setData((await r.json()) as AccountStats);
      })
      .catch((e: Error) => setError(e.message));
  }, [adminKey, days]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.accounts ?? []).filter((a) => {
      if (filter === "active" && a.active_days === 0) return false;
      if (filter === "never" && a.last_seen_at) return false;
      if (filter === "unconfirmed" && a.confirmed) return false;
      if (filter === "suspended" && !a.suspended) return false;
      return !q || [a.email, a.username, a.display_name].some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [data, query, filter]);

  if (error) return <p className="mt-3 text-risk">{error}</p>;
  if (!data) return <p className="mt-3 text-[color:var(--muted)]">Loading accounts…</p>;
  const t = data.totals;
  const period = data.days === 1 ? "today" : `in the last ${data.days} days`;
  const maxDaily = Math.max(1, ...data.daily.map((d) => Math.max(d.signups, d.active)));

  return (
    <section aria-labelledby="accounts-heading">
      <h2 id="accounts-heading" className="mt-8 font-semibold">Accounts</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          [t.accounts, "accounts"],
          [t.active_in_period, `used the app ${period}`],
          [t.returning_in_period, `came back on 2+ days ${period}`],
          [t.new_in_period, `new accounts ${period}`],
        ].map(([n, label]) => (
          <div key={label as string} className="panel p-4">
            <div className="text-2xl font-semibold">{(n as number).toLocaleString("en-US")}</div>
            <div className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{label}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
        {t.active_7d} active in the last 7 days · {t.never_used} never opened the app · {t.unconfirmed} unconfirmed email ·{" "}
        {t.with_username} chose a username · {t.google} use Google · {t.two_factor} use two-factor sign-in · {t.paid ?? 0} on a paid plan · {t.api_users ?? 0} with API keys{t.suspended ? ` · ${t.suspended} suspended` : ""}. An account counts
        as active on a day when it opened the app that day.
      </p>

      {data.daily.length > 1 && (
        <div className="mt-4" aria-label="Sign-ups and active accounts per day">
          <div className="flex h-20 items-end gap-px">
            {data.daily.map((d) => (
              <div key={d.day} className="flex h-full flex-1 items-end gap-px" title={`${d.day}: ${d.signups} sign-ups, ${d.active} active`}>
                <div className="flex-1 rounded-t-sm bg-white/70" style={{ height: `${(d.active / maxDaily) * 100}%` }} />
                <div className="flex-1 rounded-t-sm bg-verified" style={{ height: `${(d.signups / maxDaily) * 100}%` }} />
              </div>
            ))}
          </div>
          <p className="mt-1 text-[0.75rem] text-[color:var(--muted)]">
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-white/70" />active accounts
            <span className="ml-3 mr-1 inline-block h-2 w-2 rounded-sm bg-verified" />sign-ups · {data.since} to today (UTC)
          </p>
        </div>
      )}

      {planNote && <p role="status" className={`mt-4 text-sm ${planNote.ok ? "text-verified" : "text-risk"}`}>{planNote.text}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search email, username or name"
          aria-label="Search accounts" className="min-w-0 flex-1 rounded-lg border hairline bg-transparent px-3 py-2" />
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="Filter accounts"
          className="rounded-lg border hairline bg-transparent px-3 py-2">
          <option value="all">All accounts</option>
          <option value="active">Used the app {period}</option>
          <option value="never">Never opened the app</option>
          <option value="unconfirmed">Email not confirmed</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead className="text-[color:var(--muted)]">
            <tr>
              <th className="py-2 pr-3 font-normal">Account</th>
              <th className="py-2 pr-3 font-normal">Joined</th>
              <th className="py-2 pr-3 font-normal">Last used</th>
              <th className="py-2 pr-3 font-normal">Active days</th>
              <th className="py-2 pr-3 font-normal">Plan</th>
              <th className="py-2 pr-3 font-normal">Details</th>
              <th className="py-2 font-normal"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.email} className={`border-t hairline align-top ${a.suspended ? "bg-risk/[0.04]" : ""}`}>
                <td className="py-2 pr-3">
                  <div className="font-medium">
                    {a.display_name || a.username || a.email.split("@")[0]}
                    {a.suspended && <span className="ml-2 rounded-full border border-risk/40 px-2 py-0.5 text-[0.6875rem] font-normal text-risk">Suspended</span>}
                  </div>
                  {a.suspended && a.suspension_reason && <div className="text-[0.75rem] text-risk">{a.suspension_reason}</div>}
                  <div className="text-[0.8125rem] text-[color:var(--muted)]">{a.username ? `@${a.username} · ` : ""}{a.email}</div>
                </td>
                <td className="py-2 pr-3 whitespace-nowrap">{a.created_at.slice(0, 10)}</td>
                <td className="py-2 pr-3 whitespace-nowrap">{when(a.last_seen_at)}</td>
                <td className="py-2 pr-3">{a.active_days}</td>
                <td className="py-2 pr-3">
                  <select
                    value={a.plan ?? "free"}
                    onChange={(e) => changePlan(a, e.target.value)}
                    disabled={saving === a.email || !data.plans}
                    aria-label={`Plan for ${a.email}`}
                    className="rounded-md border hairline bg-transparent px-2 py-1 text-[0.8125rem]"
                  >
                    {(data.plans ?? [{ id: "free", label: "Free", monthly_requests: 30 }]).map((p) => (
                      <option key={p.id} value={p.id}>{p.label}</option>
                    ))}
                  </select>
                  <div className="mt-1 whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">
                    {(a.api_used ?? 0).toLocaleString("en-US")} API calls this month{a.api_keys ? ` · ${a.api_keys} key${a.api_keys === 1 ? "" : "s"}` : ""}
                  </div>
                </td>
                <td className="py-2 pr-3 text-[0.8125rem] text-[color:var(--muted)]">
                  {[a.providers.includes("google") ? "Google" : "Email & password",
                    a.confirmed ? null : "email not confirmed",
                    a.username ? null : "no username yet",
                    a.two_factor ? "two-factor" : null,
                    a.email_alerts ? `${a.email_alerts} watchlist email${a.email_alerts === 1 ? "" : "s"}` : null,
                  ].filter(Boolean).join(" · ")}
                </td>
                <td className="py-2 whitespace-nowrap text-right">
                  {!a.confirmed && (
                    <button type="button" disabled={helping !== null} onClick={() => help(a.email, "confirm")}
                      className="mr-1.5 rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">Resend confirmation</button>
                  )}
                  <button type="button" disabled={helping !== null} onClick={() => help(a.email, "reset")}
                    title="Email this person a link to set a new password"
                    className="mr-1.5 rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">Send reset link</button>
                  <button type="button" onClick={() => setPending({ kind: a.suspended ? "reinstate" : "suspend", account: a })}
                    className="rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">
                    {a.suspended ? "Reinstate" : "Suspend"}
                  </button>
                  <button type="button" onClick={() => setPending({ kind: "delete", account: a })}
                    className="ml-1.5 rounded-md border border-risk/40 px-2 py-1 text-[0.75rem] text-risk hover:bg-risk/[0.08]">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={7} className="py-3 text-[color:var(--muted)]">No accounts match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
        Activity is recorded from this release onward, so earlier use shows as &ldquo;never&rdquo;. Email addresses are shown
        only here, to you, and are never cached.
      </p>

      <h3 className="mt-8 font-semibold">Sign-in trouble</h3>
      <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
        Failed sign-ups, sign-ins and password resets in the last 14 days, by address, so you can reach out. Someone who
        never managed to create an account appears only here. Passwords are never recorded; entries are kept for 30 days.
      </p>
      {troubleError ? <p className="mt-2 text-sm text-risk">{troubleError}</p> : !trouble ? (
        <p className="mt-2 text-sm text-[color:var(--muted)]">Loading…</p>
      ) : trouble.length === 0 ? (
        <p className="mt-2 text-sm text-[color:var(--muted)]">No failed attempts in the last 14 days.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-[color:var(--muted)]">
              <tr>
                <th className="py-2 pr-3 font-normal">Address</th>
                <th className="py-2 pr-3 font-normal">Last attempt</th>
                <th className="py-2 pr-3 font-normal">Attempts</th>
                <th className="py-2 pr-3 font-normal">What went wrong last</th>
                <th className="py-2 pr-3 font-normal">Now</th>
                <th className="py-2 font-normal"><span className="sr-only">Help</span></th>
              </tr>
            </thead>
            <tbody>
              {trouble.map((t) => (
                <tr key={(t.email ?? "unknown") + t.last_at} className="border-t hairline align-top">
                  <td className="py-2 pr-3">{t.email ?? <span className="text-[color:var(--muted)]">no valid address</span>}
                    <div className="text-[0.75rem] text-[color:var(--muted)]">{t.actions.join(", ")}</div></td>
                  <td className="py-2 pr-3 whitespace-nowrap">{when(t.last_at)}</td>
                  <td className="py-2 pr-3">{t.attempts}</td>
                  <td className="py-2 pr-3 text-[0.8125rem]">{t.last_reason}</td>
                  <td className="py-2 pr-3 text-[0.8125rem]">
                    {t.signed_in_since ? <span className="text-verified">Signed in since</span>
                      : t.has_account ? (t.confirmed ? "Has an account" : "Account, email not confirmed")
                      : <span className="text-risk">No account</span>}
                  </td>
                  <td className="py-2 whitespace-nowrap text-right">
                    {t.email && t.has_account && !t.signed_in_since && (
                      <button type="button" disabled={helping !== null} onClick={() => help(t.email!, t.confirmed ? "reset" : "confirm")}
                        className="mr-1.5 rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">
                        {t.confirmed ? "Send reset link" : "Resend confirmation"}</button>
                    )}
                    {t.email && !t.signed_in_since && (
                      <a href={`mailto:${t.email}?subject=${encodeURIComponent("Signing up to Deal Intelligence")}`}
                        className="rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">Email them</a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="mt-8 font-semibold">Suspensions and deletions</h3>
      {log === null ? <p className="mt-2 text-sm text-[color:var(--muted)]">Loading…</p>
        : log.length === 0 ? <p className="mt-2 text-sm text-[color:var(--muted)]">No account has been suspended or deleted.</p> : (
          <ul className="mt-2 space-y-1 text-sm">
            {log.map((e, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className="text-[color:var(--muted)]">{e.at.slice(0, 16).replace("T", " ")}</span>
                <span className={e.action === "reinstated" ? "text-verified" : "text-risk"}>{e.action}</span>
                <span>{e.account}</span>
                {e.reason && <span className="text-[color:var(--muted)]">· {e.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      {pending && <ModerationDialog pending={pending} onCancel={() => setPending(null)} onConfirm={moderate} />}
    </section>
  );
}

const RENEWING = ["active", "attention"];

/** The confirmation step for a suspension, reinstatement or deletion: what happens, an optional reason, and for a
 * deletion the account's email typed again. */
function ModerationDialog({ pending, onCancel, onConfirm }: {
  pending: Pending; onCancel: () => void; onConfirm: (p: Pending, reason: string, confirm: string) => Promise<string | null>;
}) {
  const { kind, account } = pending;
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const renewing = RENEWING.includes(account.subscription_status ?? "");
  const canGo = kind !== "delete" || confirm.trim().toLowerCase() === account.email.toLowerCase();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  async function go() {
    setBusy(true);
    setProblem("");
    const err = await onConfirm(pending, reason.trim(), confirm.trim());
    if (err) { setProblem(err); setBusy(false); }
  }

  const title = kind === "suspend" ? "Suspend this account?" : kind === "reinstate" ? "Reinstate this account?" : "Delete this account permanently?";
  const effects = kind === "suspend" ? [
    "They are signed out everywhere and cannot sign in (within an hour on a page already open).",
    "Their API keys stop working and their alert emails, webhooks and election alerts pause.",
    renewing ? "Their Paystack subscription stops renewing, so they are not charged again." : null,
    "Nothing is deleted: reinstating restores everything except a cancelled subscription.",
  ] : kind === "reinstate" ? [
    "They can sign in again; their API keys and alerts resume.",
    "A subscription cancelled at suspension stays cancelled: they subscribe again from Plan and billing.",
  ] : [
    "Their profile, watchlists, alerts, API keys, saved data and company submissions are erased.",
    renewing ? "Their Paystack subscription is cancelled first; nothing is deleted if that fails." : null,
    "If they created a shared cloud portfolio or organisation, the account is anonymised instead so that shared data keeps working.",
    "This cannot be undone. They can sign up again later as a new account.",
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="moderation-title" className="w-full max-w-md rounded-2xl border hairline bg-[color:var(--bg)] p-6 shadow-2xl">
        <h3 id="moderation-title" className="text-lg font-semibold">{title}</h3>
        <p className="mt-1 break-all text-sm text-[color:var(--muted)]">{account.email}</p>
        <ul className="mt-4 list-disc space-y-1.5 pl-5 text-sm text-[color:var(--muted)]">
          {effects.filter(Boolean).map((e) => <li key={e as string}>{e}</li>)}
        </ul>
        {kind !== "reinstate" && (
          <label className="mt-4 block text-sm">Reason (for your log; not sent to them)
            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="e.g. scraping, chargeback, asked to be removed"
              className="mt-1 w-full rounded-lg border hairline bg-transparent px-3 py-2" />
          </label>
        )}
        {kind === "delete" && (
          <label className="mt-3 block text-sm">Type <span className="font-medium">{account.email}</span> to confirm
            <input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" spellCheck={false} aria-label="Type the email to confirm"
              className="mt-1 w-full rounded-lg border border-risk/40 bg-transparent px-3 py-2" />
          </label>
        )}
        {problem && <p role="alert" className="mt-3 text-sm text-risk">{problem}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={busy} className="rounded-lg border hairline px-3 py-2 text-sm">Cancel</button>
          <button type="button" onClick={go} disabled={busy || !canGo}
            className={`rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${kind === "reinstate" ? "bg-verified text-black" : "bg-risk text-white"}`}>
            {busy ? "Working…" : kind === "suspend" ? "Suspend account" : kind === "reinstate" ? "Reinstate account" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
