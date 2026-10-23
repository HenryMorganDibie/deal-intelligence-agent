"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, usd, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { apiUrl, del, get, post } from "../../../../lib/market";

type Alert = { kind: string; id: string; day: string | null; title: string; signal_type?: string; deal_type?: string; amount_usd?: number | null; url?: string; publisher?: string; why: string[]; source_count?: number; independent_stories?: number | null; verification?: string | null; sources?: { publisher?: string | null; url?: string | null; date?: string | null; title?: string | null }[] };
type Quality = { alert_count: number; with_source_evidence: number; source_evidence_coverage_pct: number | null; with_two_or_more_independent_stories: number; with_verification_label: number; accuracy_estimate: null; note: string };
type Watchlist = { id: string; name: string; companies: string[]; countries: string[]; signal_types: string[]; include_deals: boolean; webhook_url: string | null; last_delivered_at: string | null };
type ReviewState = "unreviewed" | "reviewed" | "dismissed";
type ReviewMap = Record<string, ReviewState>;
const REVIEW_KEY = "deal-intel:alert-review:";

function readReview(id: string): ReviewMap {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(REVIEW_KEY + id) ?? "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value as ReviewMap : {};
  } catch {
    return {};
  }
}

export default function WatchlistPage({ params }: { params: { id: string } }) {
  const [data, setData] = useState<{ watchlist: Watchlist; alerts: Alert[]; quality?: Quality } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");
  const [review, setReview] = useState<ReviewMap>({});

  useEffect(() => {
    setReview({});
    get<{ watchlist: Watchlist; alerts: Alert[]; quality?: Quality }>(`/api/watchlists/${encodeURIComponent(params.id)}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the watchlist."));
    get<{ reviews: { alert_key: string; state: ReviewState }[] }>(`/api/watchlists/${encodeURIComponent(params.id)}/reviews`)
      .then((result) => {
        const next: ReviewMap = {};
        for (const item of result.reviews ?? []) {
          if (item.state === "reviewed" || item.state === "dismissed") next[item.alert_key] = item.state;
        }
        setReview(next);
      })
      .catch(() => setActionError("Review state could not be loaded. Check that the alert-review database migration has been applied."));
  }, [params.id]);

  async function setAlertState(key: string, state: ReviewState) {
    const previous = review[key] ?? "unreviewed";
    const next = { ...review };
    if (state === "unreviewed") delete next[key];
    else next[key] = state;
    setReview(next);
    try {
      await post(`/api/watchlists/${encodeURIComponent(params.id)}/reviews`, { alert_key: key, state });
      setActionError(null);
    } catch (err) {
      const restored = { ...next };
      if (previous === "unreviewed") delete restored[key];
      else restored[key] = previous;
      setReview(restored);
      setActionError(err instanceof ApiError ? err.message : "Could not save this review action. Please retry.");
    }
  }

  async function remove() {
    if (!confirm("Delete this watchlist? Its feed and webhook stop working.")) return;
    try {
      setActionError(null);
      await del(`/api/watchlists/${encodeURIComponent(params.id)}`);
      try {
        const rows: unknown = JSON.parse(localStorage.getItem("deal-intel:watchlists") ?? "[]");
        if (Array.isArray(rows)) localStorage.setItem("deal-intel:watchlists", JSON.stringify(rows.filter((r: { id?: string }) => r.id !== params.id)));
        localStorage.removeItem(REVIEW_KEY + params.id);
      } catch {
        // The server-side deletion succeeded; local browser cleanup is best-effort.
      }
      window.location.href = "/app/watchlists";
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not delete the watchlist.");
    }
  }

  async function copyFeed(feed: string) {
    try {
      await navigator.clipboard.writeText(feed);
      setCopied(true);
      setActionError(null);
    } catch {
      setCopied(false);
      setActionError("Could not copy the RSS link. Copy it from the address field after opening the feed.");
    }
  }

  const filteredAlerts = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLocaleLowerCase();
    return data.alerts.filter((a) => {
      const key = a.kind + ":" + a.id;
      const status = review[key] ?? "unreviewed";
      if (statusFilter === "active" && status === "dismissed") return false;
      if (statusFilter === "unreviewed" && status !== "unreviewed") return false;
      if (statusFilter === "reviewed" && status !== "reviewed") return false;
      if (statusFilter === "dismissed" && status !== "dismissed") return false;
      if (kindFilter !== "all" && a.kind !== kindFilter) return false;
      if (q && ![a.title, a.publisher, a.signal_type, a.deal_type, ...(a.why ?? [])].some((v) => (v ?? "").toLocaleLowerCase().includes(q))) return false;
      return true;
    });
  }, [data, query, kindFilter, statusFilter, review]);

  if (error) return <Container className="py-14"><ErrorNote message={error} /></Container>;
  if (!data) return <Container className="py-14"><Loading /></Container>;
  const { watchlist: w, alerts } = data;
  const feed = apiUrl(`/api/watchlists/${w.id}/feed.xml`);
  const reviewedCount = alerts.filter((a) => review[a.kind + ":" + a.id] === "reviewed").length;
  const dismissedCount = alerts.filter((a) => review[a.kind + ":" + a.id] === "dismissed").length;
  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <Link href="/app/watchlists" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">← Watchlists</Link>
      <div className="mt-4">
        <PageHeader eyebrow="Watchlist" title={w.name}>
          Companies: {w.companies.join(", ") || "none"}. Countries: {w.countries.join(", ") || "none"}. Event types:{" "}
          {w.signal_types.length ? w.signal_types.map(words).join(", ") : "all"}. Deals {w.include_deals ? "included" : "excluded"}.
          {w.webhook_url ? ` Webhook delivery${w.last_delivered_at ? `, last sent ${w.last_delivered_at.slice(0, 10)}` : ""}.` : ""}
        </PageHeader>
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn btn-ghost" onClick={() => copyFeed(feed)}>{copied ? "RSS link copied" : "Copy RSS feed link"}</button>
        <a href={feed} target="_blank" rel="noreferrer" className="btn btn-ghost">Open feed</a>
        <button type="button" onClick={remove} className="btn btn-ghost text-risk">Delete</button>
      </div>
      {actionError && <ErrorNote message={actionError} />}

      <section className="mt-10" aria-labelledby="alerts-heading">
        <div>
          <h2 id="alerts-heading" className="eyebrow">Alerts, last 90 days ({alerts.length})</h2>
          <p className="mt-1 text-xs text-[color:var(--dim)]">{reviewedCount} reviewed · {dismissedCount} dismissed · {alerts.length - reviewedCount - dismissedCount} unreviewed</p>
          {data.quality && <p className="mt-2 text-xs text-[color:var(--dim)]">Source evidence: {data.quality.with_source_evidence}/{data.quality.alert_count}{data.quality.source_evidence_coverage_pct === null ? "" : ` (${data.quality.source_evidence_coverage_pct}%)`} · {data.quality.with_two_or_more_independent_stories} with 2+ independent stories. These are evidence-coverage counts, not an accuracy score.</p>}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-[color:var(--muted)]">Search alerts
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Company, publisher, match reason" className="field mt-1" />
          </label>
          <label className="text-xs text-[color:var(--muted)]">Event source
            <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className="field mt-1">
              <option value="all">All alerts</option><option value="event">Corporate events</option><option value="deal">Deals</option>
            </select>
          </label>
          <label className="text-xs text-[color:var(--muted)]">Review status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="field mt-1">
              <option value="active">Active (hide dismissed)</option><option value="unreviewed">Unreviewed</option><option value="reviewed">Reviewed</option><option value="dismissed">Dismissed</option><option value="all">All statuses</option>
            </select>
          </label>
        </div>
        <ul className="mt-4 space-y-3">
          {alerts.length === 0 && <li className="text-sm text-[color:var(--muted)]">No matches yet. New events arrive with each daily run.</li>}
          {alerts.length > 0 && filteredAlerts.length === 0 && <li className="text-sm text-[color:var(--muted)]">No alerts match these filters.</li>}
          {filteredAlerts.map((a) => {
            const key = a.kind + ":" + a.id;
            const state = review[key] ?? "unreviewed";
            return (
              <li key={key} className={`border-b hairline pb-3 text-[0.875rem] ${state === "dismissed" ? "opacity-60" : ""}`}>
                <div className="flex flex-wrap items-center gap-2 text-[0.75rem] text-[color:var(--dim)]">
                  <span className="kbd">{a.day || "Date unavailable"}</span>
                  <Pill value={a.signal_type ?? a.deal_type} />
                  {a.amount_usd ? <span>{usd(a.amount_usd)}</span> : null}
                  <span>matched on {a.why.join("; ")}</span>
                  {typeof a.source_count === "number" && <span>{a.source_count} source{a.source_count === 1 ? "" : "s"}</span>}
                  {a.verification && <span className="rounded-full border hairline px-2 py-0.5">{a.verification}</span>}
                  {state !== "unreviewed" && <span className="rounded-full border hairline px-2 py-0.5">{state}</span>}
                </div>
                <p className="mt-1">
                  {a.kind === "deal" ? (
                    <Link href={`/app/deals/${encodeURIComponent(a.id)}`} className="hover:underline">{a.title}</Link>
                  ) : a.url ? (
                    <a href={a.url} target="_blank" rel="noreferrer" className="hover:underline">{a.title}</a>
                  ) : <span>{a.title}</span>}
                  {a.publisher && <span className="text-[color:var(--dim)]"> · {a.publisher}</span>}
                </p>
                {a.sources && a.sources.filter((source) => source.url && source.url !== a.url).length > 0 && (
                  <p className="mt-1 text-xs text-[color:var(--dim)]">
                    Other sources: {a.sources.filter((source) => source.url && source.url !== a.url).map((source, i) => (
                      <span key={source.url}>
                        {i > 0 ? " · " : ""}
                        <a href={source.url!} target="_blank" rel="noreferrer" className="underline">{source.publisher || source.title || "Source"}</a>
                      </span>
                    ))}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="btn btn-ghost text-xs" onClick={() => setAlertState(key, state === "reviewed" ? "unreviewed" : "reviewed")}>{state === "reviewed" ? "Mark unreviewed" : "Mark reviewed"}</button>
                  <button type="button" className="btn btn-ghost text-xs" onClick={() => setAlertState(key, state === "dismissed" ? "unreviewed" : "dismissed")}>{state === "dismissed" ? "Restore alert" : "Dismiss"}</button>
                </div>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-xs text-[color:var(--dim)]">Review and dismissal states are saved against this watchlist and follow its private link across browsers. They do not delete the underlying event or suppress RSS/webhook delivery.</p>
      </section>
    </Container>
  );
}
