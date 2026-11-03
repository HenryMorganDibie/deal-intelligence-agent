"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type State = { enabled: boolean; email: string | null; emailConfirmed: boolean };

// Email alerts for the signed-in account. Alerts go only to the account's verified address.
export function WatchlistEmailAlerts({ watchlistId, frequency }: { watchlistId: string; frequency: "daily" | "weekly" }) {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endpoint = `/api/watchlists/${encodeURIComponent(watchlistId)}/email`;

  useEffect(() => {
    fetch(endpoint, { cache: "no-store" })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || "Email alert settings could not be loaded.");
        setState(body as State);
      })
      .catch((e: Error) => setError(e.message));
  }, [endpoint]);

  async function toggle() {
    if (!state) return;
    setBusy(true); setError("");
    try {
      const r = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !state.enabled }) });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || "Email alerts could not be updated.");
      setState({ ...state, enabled: Boolean(body.enabled) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cadence = frequency === "weekly" ? "a weekly digest on Fridays (UTC)" : "an email after each ingestion run that finds new matches";
  return (
    <section className="mt-5 rounded-lg border hairline p-4" aria-label="Email alerts">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="eyebrow">Email alerts</h2>
          {state ? (
            <p className="mt-1 text-sm text-[color:var(--muted)]" role="status">
              {state.enabled
                ? <>On: {cadence}, sent to <strong className="text-[color:var(--text)]">{state.email}</strong>.</>
                : state.emailConfirmed
                  ? <>Off. Turn on to receive new matches at <strong className="text-[color:var(--text)]">{state.email}</strong>.</>
                  : <>Confirm your email address to receive alerts by email.</>}
            </p>
          ) : !error ? <p className="mt-1 text-sm text-[color:var(--dim)]">Loading…</p> : null}
        </div>
        {state && (state.emailConfirmed || state.enabled) ? (
          <button type="button" className={state.enabled ? "btn btn-ghost" : "btn btn-primary"} onClick={toggle} disabled={busy} aria-pressed={state.enabled}>
            {busy ? "Saving…" : state.enabled ? "Turn off email alerts" : "Email me new matches"}
          </button>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-sm text-risk" role="alert">{error}</p> : null}
      <p className="mt-2 text-xs text-[color:var(--dim)]">Every email has a one-click unsubscribe link. <Link className="underline underline-offset-4" href="/account">Manage your account</Link>.</p>
    </section>
  );
}
