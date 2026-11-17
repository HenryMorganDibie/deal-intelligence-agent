"use client";

import { useState } from "react";

export const PRICE_MOVE_OPTIONS: [number | null, string][] = [[null, "Off"], [5, "5% or more"], [10, "10% or more"], [15, "15% or more"], [20, "20% or more"]];

// Price-move alerts: tell the subscriber when a listed company the watchlist follows closes up or down by at least
// the chosen percentage in a day. They go out through the watchlist's own email and channel.
export function WatchlistPriceMoves({ watchlistId, initial }: { watchlistId: string; initial: number | null }) {
  const [pct, setPct] = useState<number | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function change(next: number | null) {
    setBusy(true); setError("");
    try {
      const r = await fetch(`/api/watchlists/${encodeURIComponent(watchlistId)}/price-moves`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pct: next }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || "Price alerts could not be updated.");
      setPct(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-5 rounded-lg border hairline p-4" aria-label="Price-move alerts">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="eyebrow">Price moves</h2>
          <p className="mt-1 text-sm text-[color:var(--muted)]" role="status">
            {pct
              ? <>On: an alert when a listed company here closes up or down {pct}% or more in a day, on any of the 25 exchanges we cover.</>
              : <>Off. Turn on to hear when a listed company here moves sharply in a day.</>}
          </p>
        </div>
        <select aria-label="Daily move that triggers an alert" className="field h-9 w-auto py-1" value={pct ?? ""} disabled={busy}
                onChange={(e) => void change(e.target.value ? Number(e.target.value) : null)}>
          {PRICE_MOVE_OPTIONS.map(([v, label]) => <option key={label} value={v ?? ""}>{label}</option>)}
        </select>
      </div>
      {error && <p className="mt-2 text-sm text-risk" role="alert">{error}</p>}
    </section>
  );
}
