"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, usd, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { apiUrl, del, get } from "../../../../lib/market";

type Alert = { kind: string; id: string; day: string | null; title: string; signal_type?: string; deal_type?: string; amount_usd?: number | null; url?: string; publisher?: string; why: string[] };
type Watchlist = { id: string; name: string; companies: string[]; countries: string[]; signal_types: string[]; include_deals: boolean; webhook_url: string | null; last_delivered_at: string | null };

export default function WatchlistPage({ params }: { params: { id: string } }) {
  const [data, setData] = useState<{ watchlist: Watchlist; alerts: Alert[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    get<{ watchlist: Watchlist; alerts: Alert[] }>(`/api/watchlists/${encodeURIComponent(params.id)}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the watchlist."));
  }, [params.id]);

  async function remove() {
    if (!confirm("Delete this watchlist? Its feed and webhook stop working.")) return;
    await del(`/api/watchlists/${encodeURIComponent(params.id)}`);
    try {
      const rows = JSON.parse(localStorage.getItem("deal-intel:watchlists") ?? "[]");
      localStorage.setItem("deal-intel:watchlists", JSON.stringify(rows.filter((r: { id: string }) => r.id !== params.id)));
    } catch {
      /* ignore */
    }
    window.location.href = "/app/watchlists";
  }

  if (error) return <Container className="py-14"><ErrorNote message={error} /></Container>;
  if (!data) return <Container className="py-14"><Loading /></Container>;
  const { watchlist: w, alerts } = data;
  const feed = apiUrl(`/api/watchlists/${w.id}/feed.xml`);
  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <Link href="/app/watchlists" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">
        ← Watchlists
      </Link>
      <div className="mt-4">
        <PageHeader eyebrow="Watchlist" title={w.name}>
          Companies: {w.companies.join(", ") || "none"}. Countries: {w.countries.join(", ") || "none"}. Event types:{" "}
          {w.signal_types.length ? w.signal_types.map(words).join(", ") : "all"}. Deals {w.include_deals ? "included" : "excluded"}.
          {w.webhook_url ? ` Webhook delivery${w.last_delivered_at ? `, last sent ${w.last_delivered_at.slice(0, 10)}` : ""}.` : ""}
        </PageHeader>
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            navigator.clipboard.writeText(feed).then(() => setCopied(true));
          }}
        >
          {copied ? "RSS link copied" : "Copy RSS feed link"}
        </button>
        <a href={feed} target="_blank" rel="noreferrer" className="btn btn-ghost">
          Open feed
        </a>
        <button type="button" onClick={remove} className="btn btn-ghost text-risk">
          Delete
        </button>
      </div>

      <h2 className="eyebrow mt-10">Alerts, last 90 days ({alerts.length})</h2>
      <ul className="mt-3 space-y-3">
        {alerts.length === 0 && <li className="text-sm text-[color:var(--muted)]">No matches yet. New events arrive with each daily run.</li>}
        {alerts.map((a) => (
          <li key={a.kind + a.id} className="border-b hairline pb-3 text-[0.875rem]">
            <div className="flex flex-wrap items-center gap-2 text-[0.75rem] text-[color:var(--dim)]">
              <span className="kbd">{a.day}</span>
              <Pill value={a.signal_type ?? a.deal_type} />
              {a.amount_usd ? <span>{usd(a.amount_usd)}</span> : null}
              <span>matched on {a.why.join("; ")}</span>
            </div>
            <p className="mt-1">
              {a.kind === "deal" ? (
                <Link href={`/app/deals/${a.id}`} className="hover:underline">
                  {a.title}
                </Link>
              ) : (
                <a href={a.url} target="_blank" rel="noreferrer" className="hover:underline">
                  {a.title}
                </a>
              )}{" "}
              {a.publisher && <span className="text-[color:var(--dim)]">{a.publisher}</span>}
            </p>
          </li>
        ))}
      </ul>
    </Container>
  );
}
