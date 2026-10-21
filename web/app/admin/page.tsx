"use client";

import { useEffect, useState } from "react";
import { browserVisitorId } from "../../lib/tracking";

type Row = { views: number; visitors: number; users: number };
type ActionRow = { action: string; completions: number; clients: number };
type PageActivity = { feature: string; browsers: number; page_views: number };
type BehavioralDeal = {
  deal_id: string;
  unique_impression_visitors: number;
  unique_openers: number;
  impressions: number;
  opens: number;
  active_days: number;
  click_through_rate: number | null;
};
type BehavioralBrief = { brief_id: string; unique_visitors: number; active_days: number };
type BehavioralSignals = {
  since: string;
  days: number;
  totals: Record<string, number>;
  top_deals: BehavioralDeal[];
  top_briefs: BehavioralBrief[];
  status?: string;
};
type FeedbackItem = {
  id: string;
  created_at: string;
  result_type: string;
  result_id: string;
  category: string;
  note: string;
  reviewed_at: string | null;
};
type Stats = {
  since: string;
  totals: Row & { returning_users: number };
  days: (Row & { day: string })[];
  pages: { path: string; views: number; visitors: number }[];
  actions?: ActionRow[];
  app_page_activity?: PageActivity[];
};

const API = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

/** Owner-only usage page. Opening it marks this browser as the owner's, so its visits are not counted. */
export default function Admin() {
  const [key, setKey] = useState("");
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [error, setError] = useState("");

  async function load(k: string, d: number) {
    setError("");
    try {
      const r = await fetch(`${API}/api/admin/stats`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k, days: d, visitor: browserVisitorId() }),
      });
      if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "Stats unavailable");
      setStats(await r.json());
      localStorage.setItem("di_admin", k);
      const feedbackResponse = await fetch(`${API}/api/admin/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k }),
      });
      if (!feedbackResponse.ok) throw new Error("Feedback queue unavailable");
      setFeedback((await feedbackResponse.json()).items);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function markFeedbackReviewed(id: string) {
    try {
      const response = await fetch(`${API}/api/admin/feedback/${encodeURIComponent(id)}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      if (!response.ok) throw new Error("Could not update feedback status.");
      setFeedback((rows) => rows.map((row) => row.id === id ? { ...row, reviewed_at: new Date().toISOString() } : row));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    try {
      localStorage.setItem("di_owner", "1");
      const k = localStorage.getItem("di_admin");
      if (k) {
        setKey(k);
        load(k, days);
      }
    } catch {
      /* storage blocked */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const t = stats?.totals;
  const actionLabels: Record<string, string> = {
    brief_completed: "Company briefs completed",
    research_completed: "Research answers completed",
    country_report_completed: "Country reports completed",
    sector_report_completed: "Sector reports completed",
    deals_loaded: "Deal data loaded",
    investors_loaded: "Investor and fund data loaded",
    events_loaded: "Event data loaded",
    risk_data_loaded: "Country, currency and risk data loaded",
    company_data_loaded: "Company profiles and valuations loaded",
    watchlists_used: "Watchlist actions completed",
    brief_opened: "Saved briefs opened",
    performance_data_loaded: "Performance data loaded",
    deal_search_submitted: "Deal searches submitted",
    deal_opened: "Deal detail opens",
    research_submitted: "Research questions submitted",
    market_brief_opened: "Market briefs opened",
    deal_impression: "Deal result impressions",
  };
  const actions = stats?.actions ?? [];
  const appPageActivity = stats?.app_page_activity ?? [];
  const actionCounts = Object.fromEntries(actions.map((row) => [row.action, row.completions]));
  const actionsAvailable = Boolean(stats?.actions && stats.app_page_activity);
  const completedResearch = (actionCounts.research_completed ?? 0)
    + (actionCounts.country_report_completed ?? 0)
    + (actionCounts.sector_report_completed ?? 0);
  const successfulFeatures = actions
    .filter((row) => !["brief_completed", "research_completed", "country_report_completed", "sector_report_completed"].includes(row.action))
    .reduce((sum, row) => sum + row.completions, 0) ?? 0;
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 text-[0.9375rem]">
      <meta name="robots" content="noindex" />
      <h1 className="text-2xl font-semibold">Usage</h1>
      <p className="mt-1 text-[color:var(--muted)]">Only you can see this. This browser is excluded from the counts.</p>

      <form
        className="mt-6 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          load(key, days);
        }}
      >
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Admin key"
          className="min-w-0 flex-1 rounded-lg border hairline bg-transparent px-3 py-2"
        />
        <select
          value={days}
          onChange={(e) => {
            const d = Number(e.target.value);
            setDays(d);
            if (key) load(key, d);
          }}
          className="rounded-lg border hairline bg-transparent px-3 py-2"
        >
          {[1, 7, 30, 90, 365].map((d) => (
            <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>
          ))}
        </select>
        <button className="rounded-lg bg-white/90 px-4 py-2 font-medium text-black">Show</button>
      </form>
      {error && <p className="mt-3 text-risk">{error}</p>}

      {t && stats && (
        <>
          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              [t.visitors, "unique browsers"],
              [actionsAvailable ? actionCounts.brief_completed ?? 0 : null, "company briefs completed"],
              [actionsAvailable ? completedResearch : null, "research answers & reports completed"],
              [actionsAvailable ? successfulFeatures : null, "successful app feature uses"],
            ].map(([n, label]) => (
              <div key={label as string} className="panel p-4">
                <div className="text-2xl font-semibold">{n === null ? "—" : (n as number).toLocaleString("en-US")}</div>
                <div className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{label}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
            Since {stats.since}. Unique browsers are anonymous browser IDs, not verified people. This dashboard excludes this browser. Analysis and research runs are keyed by a salted IP hash, so runs from this network are also excluded; that can include other people using the same network.
          </p>

          <h2 className="mt-8 font-semibold">Successful app actions</h2>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
            Briefs and research count each completed run. Other feature uses count at most once per browser and feature per UTC day, so repeated filters do not inflate them. Historical run client IDs are salted IP hashes; newer feature tracking uses anonymous browser IDs, so they cannot be joined across periods. Prompts, filters and company names are not stored with feature usage events.
            {!actionsAvailable && " These metrics will appear after the product-actions database migration is applied."}
          </p>
          <table className="mt-2 w-full text-left">
            <thead className="text-[color:var(--muted)]">
              <tr><th className="py-1 font-normal">Action</th><th className="font-normal">Successful uses</th><th className="font-normal">Distinct clients</th></tr>
            </thead>
            <tbody>
              {actionsAvailable ? Object.entries(actionLabels).map(([action, label]) => {
                const row = actions.find((item) => item.action === action);
                return (
                  <tr key={action} className="border-t hairline">
                    <td className="py-1.5">{label}</td>
                    <td>{row?.completions ?? 0}</td>
                    <td>{row?.clients ?? 0}</td>
                  </tr>
                );
              }) : <tr><td className="py-1.5" colSpan={3}>Usage action metrics are not available yet.</td></tr>}
            </tbody>
          </table>

          <h2 className="mt-8 font-semibold">Behavioural relevance signals</h2>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
            These signals help rank relevant results; they are not evidence that a deal is accurate or verified. Deal ranking uses a maximum 3% adjustment and requires a minimum audience before engagement can affect order.
          </p>
          {stats.behavioral_signals ? (
            <>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["deal_search_submitted", "Searches"],
                  ["deal_impression", "Impressions"],
                  ["deal_opened", "Deal opens"],
                  ["market_brief_opened", "Brief opens"],
                ].map(([action, label]) => (
                  <div key={action} className="panel p-3">
                    <div className="text-xl font-semibold">
                      {(stats.behavioral_signals?.totals?.[action] ?? 0).toLocaleString("en-US")}
                    </div>
                    <div className="mt-1 text-xs text-[color:var(--muted)]">{label}</div>
                  </div>
                ))}
              </div>
              <h3 className="mt-5 text-sm font-medium">Deals with eligible engagement data</h3>
              {stats.behavioral_signals.top_deals.length ? (
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-[color:var(--muted)]">
                      <tr><th className="py-1 font-normal">Deal ID</th><th className="font-normal">Impressions</th><th className="font-normal">Unique openers</th><th className="font-normal">Observed CTR</th></tr>
                    </thead>
                    <tbody>
                      {stats.behavioral_signals.top_deals.slice(0, 10).map((deal) => (
                        <tr key={deal.deal_id} className="border-t hairline">
                          <td className="max-w-48 truncate py-1.5" title={deal.deal_id}>{deal.deal_id}</td>
                          <td>{deal.impressions.toLocaleString("en-US")}</td>
                          <td>{deal.unique_openers.toLocaleString("en-US")}</td>
                          <td>{deal.click_through_rate == null ? "—" : String((deal.click_through_rate * 100).toFixed(1)) + "%"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="mt-2 text-sm text-[color:var(--dim)]">No deals have enough impression data yet to report an eligible engagement signal.</p>}
              <h3 className="mt-5 text-sm font-medium">Market briefs with repeat readership</h3>
              {stats.behavioral_signals.top_briefs.length ? (
                <ul className="mt-2 space-y-1 text-sm">
                  {stats.behavioral_signals.top_briefs.slice(0, 10).map((brief) => (
                    <li key={brief.brief_id} className="flex flex-wrap justify-between gap-2 border-t hairline py-2">
                      <span className="max-w-56 truncate" title={brief.brief_id}>{brief.brief_id}</span>
                      <span className="text-[color:var(--muted)]">{brief.unique_visitors} browsers · {brief.active_days} active days</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-2 text-sm text-[color:var(--dim)]">No repeat-reader brief signals yet.</p>}
            </>
          ) : <p className="mt-2 text-sm text-[color:var(--dim)]">Behavioural signals are not available from the API yet.</p>}

          <h2 className="mt-8 font-semibold">Result reports for review</h2>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
            User reports are leads for analyst review, not verified corrections. Do not use them as accuracy labels until checked against sources.
          </p>
          {feedback.length === 0 ? (
            <p className="mt-2 text-sm text-[color:var(--dim)]">No reports have been submitted.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {feedback.map((item) => (
                <li key={item.id} className="panel flex flex-wrap items-start justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {item.category.replaceAll("_", " ")} · {item.result_type.replaceAll("_", " ")}
                      <span className="ml-2 text-xs text-[color:var(--dim)]">{new Date(item.created_at).toLocaleString()}</span>
                    </p>
                    <p className="mt-1 break-all text-xs text-[color:var(--dim)]">Result {item.result_id}</p>
                    {item.note && <p className="mt-2 whitespace-pre-wrap text-sm">{item.note}</p>}
                    <p className="mt-2 text-xs text-[color:var(--muted)]">{item.reviewed_at ? "Reviewed" : "Awaiting review"}</p>
                  </div>
                  {!item.reviewed_at && (
                    <button type="button" onClick={() => markFeedbackReviewed(item.id)} className="btn btn-ghost h-8 px-3 text-xs">
                      Mark reviewed
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <h2 className="mt-8 font-semibold">App page visits (context only)</h2>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
            Page views show which area was opened, not whether its request succeeded. Successful-action tracking began with this release.
          </p>
          <table className="mt-2 w-full text-left">
            <thead className="text-[color:var(--muted)]">
              <tr><th className="py-1 font-normal">Feature</th><th className="font-normal">Browsers</th><th className="font-normal">Page views</th></tr>
            </thead>
            <tbody>
              {appPageActivity.map((row) => (
                <tr key={row.feature} className="border-t hairline">
                  <td className="py-1.5">{row.feature}</td><td>{row.browsers}</td><td>{row.page_views}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 className="mt-8 font-semibold">By day</h2>
          <table className="mt-2 w-full text-left">
            <thead className="text-[color:var(--muted)]">
              <tr><th className="py-1 font-normal">Day</th><th className="font-normal">Unique browsers</th><th className="font-normal">Opened /app</th><th className="font-normal">Views</th></tr>
            </thead>
            <tbody>
              {stats.days.map((d) => (
                <tr key={d.day} className="border-t hairline"><td className="py-1.5 kbd">{d.day}</td><td>{d.visitors}</td><td>{d.users}</td><td>{d.views}</td></tr>
              ))}
            </tbody>
          </table>

          <h2 className="mt-8 font-semibold">Top pages</h2>
          <table className="mt-2 w-full text-left">
            <tbody>
              {stats.pages.map((p) => (
                <tr key={p.path} className="border-t hairline"><td className="py-1.5 kbd">{p.path}</td><td>{p.visitors} browsers</td><td>{p.views} views</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
