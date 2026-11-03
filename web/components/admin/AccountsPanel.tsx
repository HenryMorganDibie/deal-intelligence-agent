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
};
type AccountStats = {
  since: string;
  days: number;
  totals: Record<string, number>;
  daily: { day: string; signups: number; active: number }[];
  accounts: Account[];
};

const API = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

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
export function AccountsPanel({ adminKey, days }: { adminKey: string; days: number }) {
  const [data, setData] = useState<AccountStats | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "never" | "unconfirmed">("all");

  useEffect(() => {
    if (!adminKey) return;
    setError("");
    fetch(`${API}/api/admin/accounts`, {
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
        {t.with_username} chose a username · {t.google} use Google · {t.two_factor} use two-factor sign-in. An account counts
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

      <div className="mt-4 flex flex-wrap gap-2">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search email, username or name"
          aria-label="Search accounts" className="min-w-0 flex-1 rounded-lg border hairline bg-transparent px-3 py-2" />
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="Filter accounts"
          className="rounded-lg border hairline bg-transparent px-3 py-2">
          <option value="all">All accounts</option>
          <option value="active">Used the app {period}</option>
          <option value="never">Never opened the app</option>
          <option value="unconfirmed">Email not confirmed</option>
        </select>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-[color:var(--muted)]">
            <tr>
              <th className="py-2 pr-3 font-normal">Account</th>
              <th className="py-2 pr-3 font-normal">Joined</th>
              <th className="py-2 pr-3 font-normal">Last used</th>
              <th className="py-2 pr-3 font-normal">Active days</th>
              <th className="py-2 font-normal">Details</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.email} className="border-t hairline align-top">
                <td className="py-2 pr-3">
                  <div className="font-medium">{a.display_name || a.username || a.email.split("@")[0]}</div>
                  <div className="text-[0.8125rem] text-[color:var(--muted)]">{a.username ? `@${a.username} · ` : ""}{a.email}</div>
                </td>
                <td className="py-2 pr-3 whitespace-nowrap">{a.created_at.slice(0, 10)}</td>
                <td className="py-2 pr-3 whitespace-nowrap">{when(a.last_seen_at)}</td>
                <td className="py-2 pr-3">{a.active_days}</td>
                <td className="py-2 text-[0.8125rem] text-[color:var(--muted)]">
                  {[a.providers.includes("google") ? "Google" : "Email & password",
                    a.confirmed ? null : "email not confirmed",
                    a.username ? null : "no username yet",
                    a.two_factor ? "two-factor" : null,
                    a.email_alerts ? `${a.email_alerts} watchlist email${a.email_alerts === 1 ? "" : "s"}` : null,
                  ].filter(Boolean).join(" · ")}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="py-3 text-[color:var(--muted)]">No accounts match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
        Activity is recorded from this release onward, so earlier use shows as &ldquo;never&rdquo;. Email addresses are shown
        only here, to you, and are never cached.
      </p>
    </section>
  );
}
