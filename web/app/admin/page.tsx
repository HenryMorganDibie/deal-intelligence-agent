"use client";

import { apiUrl } from "../../lib/api-base";
import { useEffect, useState, type ReactNode } from "react";
import { browserVisitorId } from "../../lib/tracking";
import { AccountsPanel } from "../../components/admin/AccountsPanel";
import { ClaimsPanel } from "../../components/admin/ClaimsPanel";
import { InvestorHomesPanel } from "../../components/admin/InvestorHomesPanel";

type Row = { views: number; visitors: number; users: number };
type ActionRow = { action: string; completions: number; clients: number };
type PageActivity = { feature: string; browsers: number; page_views: number };
type BehavioralDeal = {
  deal_id: string; unique_impression_visitors: number; unique_openers: number; impressions: number; opens: number;
  active_days: number; click_through_rate: number | null;
};
type BehavioralBrief = { brief_id: string; unique_visitors: number; active_days: number };
type BehavioralSignals = {
  since: string; days: number; totals: Record<string, number>; top_deals: BehavioralDeal[]; top_briefs: BehavioralBrief[];
  status?: string;
};
type FeedbackItem = {
  id: string; created_at: string; result_type: string; result_id: string; category: string; note: string;
  reviewed_at: string | null;
};
type SourceRow = { source: string; browsers: number; engaged_browsers: number; views: number };
type CampaignRow = { campaign: string; source: string | null; medium: string | null; browsers: number; engaged_browsers: number };
type Stats = {
  since: string;
  totals: Row & { returning_users: number; engaged_visitors?: number };
  sources?: SourceRow[];
  referrers?: { referrer: string; browsers: number }[];
  campaigns?: CampaignRow[];
  attribution_since?: string | null;
  days: (Row & { day: string })[];
  pages: { path: string; views: number; visitors: number }[];
  actions?: ActionRow[];
  app_page_activity?: PageActivity[];
  behavioral_signals?: BehavioralSignals;
  plan_funnel?: PlanFunnel;
};
type FunnelCount = { accounts: number; times: number };
type PlanFunnel = {
  status?: string; days?: number; accounts?: number; free_accounts?: number; new_accounts?: number;
  paying_accounts?: number; free_using_briefs?: number; events?: Record<string, FunnelCount>;
};

type Section = "overview" | "accounts" | "revenue" | "traffic" | "usage" | "moderation" | "review";
const SECTIONS: { id: Section; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z" },
  { id: "accounts", label: "Accounts", icon: "M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0zM4 21c1-4 4-6 8-6s7 2 8 6" },
  { id: "revenue", label: "Free to paid", icon: "M3 17l6-6 4 4 8-8M21 7v6h-6" },
  { id: "traffic", label: "Traffic", icon: "M3 3v18h18M7 15l4-4 3 3 5-6" },
  { id: "usage", label: "Product usage", icon: "M4 6h16M4 12h10M4 18h7" },
  { id: "moderation", label: "Moderation", icon: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" },
  { id: "review", label: "Data review", icon: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9" },
];
const ACTION_LABELS: Record<string, string> = {
  brief_completed: "Company briefs completed", research_completed: "Research answers completed",
  country_report_completed: "Country reports completed", sector_report_completed: "Sector reports completed",
  deals_loaded: "Deal data loaded", investors_loaded: "Investor and fund data loaded", events_loaded: "Event data loaded",
  risk_data_loaded: "Country, currency and risk data loaded", company_data_loaded: "Company profiles and valuations loaded",
  watchlists_used: "Watchlist actions completed", brief_opened: "Saved briefs opened",
  performance_data_loaded: "Performance data loaded", deal_search_submitted: "Deal searches submitted",
  deal_opened: "Deal detail opens", research_submitted: "Research questions submitted",
  market_brief_opened: "Market briefs opened", deal_impression: "Deal result impressions",
};
const RESEARCH_ACTIONS = ["research_completed", "country_report_completed", "sector_report_completed"];

const fmt = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("en-US"));

// ── Building blocks ──────────────────────────────────────────────────────────

function Icon({ d, className = "h-4 w-4" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function Header({ title, children, about }: { title: string; children?: ReactNode; about?: ReactNode }) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {children && <p className="mt-1 max-w-3xl text-sm text-[color:var(--muted)]">{children}</p>}
      {about && (
        <details className="mt-2 max-w-3xl text-[0.8125rem] text-[color:var(--muted)]">
          <summary className="cursor-pointer select-none text-xs text-[color:var(--dim)] hover:text-[color:var(--muted)]">About these numbers</summary>
          <div className="mt-2 space-y-2 leading-relaxed">{about}</div>
        </details>
      )}
    </div>
  );
}

function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border hairline bg-white/[0.015] ${className}`}>
      {title && <div className="border-b hairline px-4 py-3 text-sm font-medium">{title}</div>}
      <div className="p-4">{children}</div>
    </div>
  );
}

function Kpi({ value, label, hint, tone }: { value: number | null | undefined; label: string; hint?: string; tone?: "attention" }) {
  return (
    <div className="rounded-xl border hairline bg-white/[0.015] p-4">
      <div className={`text-[1.75rem] font-semibold leading-none tracking-tight ${tone === "attention" && value ? "text-amber-400" : ""}`}>{fmt(value)}</div>
      <div className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">{label}</div>
      {hint && <div className="mt-0.5 text-xs text-[color:var(--dim)]">{hint}</div>}
    </div>
  );
}

function DataTable({ head, rows, empty, numeric = [] }: { head: string[]; rows: ReactNode[][]; empty: string; numeric?: number[] }) {
  if (!rows.length) return <p className="text-sm text-[color:var(--dim)]">{empty}</p>;
  return (
    <div className="-mx-4 overflow-x-auto">
      {/* Only tables with four or more columns need a minimum width (they scroll on a phone); narrower ones fit any card. */}
      <table className={`w-full text-left text-sm ${head.length >= 4 ? "min-w-[28rem]" : ""}`}>
        <thead>
          <tr className="text-xs text-[color:var(--dim)]">
            {head.map((h, i) => <th key={h} className={`px-4 pb-2 font-normal ${numeric.includes(i) ? "text-right" : ""}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, j) => (
            <tr key={j} className="border-t hairline">
              {r.map((c, i) => <td key={i} className={`px-4 py-2 ${numeric.includes(i) ? "kbd text-right" : ""}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DailyBars({ days }: { days: Stats["days"] }) {
  if (days.length < 2) return <p className="text-sm text-[color:var(--dim)]">Not enough days in this period for a chart.</p>;
  const ordered = [...days].sort((a, b) => a.day.localeCompare(b.day));
  const max = Math.max(1, ...ordered.map((d) => d.visitors));
  return (
    <div>
      <div className="flex h-36 items-end gap-[2px]" role="img" aria-label="Unique browsers per day">
        {ordered.map((d) => (
          <div key={d.day} className="group relative flex h-full flex-1 items-end" title={`${d.day}: ${d.visitors} browsers, ${d.users} opened the app, ${d.views} views`}>
            <div className="w-full rounded-t bg-white/20 transition group-hover:bg-white/40" style={{ height: `${Math.max(2, (d.visitors / max) * 100)}%` }} />
            <div className="absolute bottom-0 w-full rounded-t bg-emerald-400/70" style={{ height: `${(d.users / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[0.6875rem] text-[color:var(--dim)]">
        <span>{ordered[0].day}</span>
        <span className="flex gap-3"><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-white/30" />browsers</span><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-emerald-400/70" />opened the app</span></span>
        <span>{ordered[ordered.length - 1].day}</span>
      </div>
    </div>
  );
}

// ── Sections ─────────────────────────────────────────────────────────────────

function Revenue({ funnel }: { funnel?: PlanFunnel }) {
  if (!funnel || funnel.status === "unavailable") return <p className="text-sm text-[color:var(--muted)]">Conversion figures are unavailable right now.</p>;
  const ev = funnel.events ?? {};
  const n = (k: string) => ev[k]?.accounts ?? 0;
  const hitLimit = n("limit_ai_month") + n("limit_ai_day") + n("limit_alert") + n("limit_export");
  const steps: [number, string][] = [
    [funnel.free_accounts ?? 0, "Free accounts"], [funnel.free_using_briefs ?? 0, "Using briefs"], [hitLimit, "Met a Pro limit"],
    [n("see_plans"), "Opened the plans"], [n("checkout_started"), "Started checkout"], [n("paid"), "Paid"],
  ];
  const top = Math.max(1, steps[0][0]);
  const limits: [string, string][] = [
    ["limit_ai_month", "Used the 30 monthly briefs"], ["limit_ai_day", "Used the 15 daily briefs"],
    ["limit_alert", "Used all their alerts"], ["limit_export", "Tried to download a CSV"],
  ];
  return (
    <>
      <Header title="Free to paid" about={<p>Last {funnel.days ?? 30} days, counted by account. If many free accounts use briefs but few meet a limit or open the plans, the free allowance is too generous; if many meet a limit and few pay, look at price or Pro&apos;s value.</p>}>
        From free sign-up to paying, over the period. {fmt(funnel.paying_accounts)} accounts pay now; {fmt(funnel.new_accounts)} are new.
      </Header>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Conversion funnel" className="lg:col-span-2">
          <ol className="space-y-3">
            {steps.map(([v, label], i) => (
              <li key={label}>
                <div className="flex justify-between text-sm"><span>{label}</span>
                  <span className="kbd text-[color:var(--muted)]">{fmt(v)}{i > 0 && steps[0][0] ? ` · ${((v / steps[0][0]) * 100).toFixed(1)}%` : ""}</span></div>
                <div className="mt-1 h-2 rounded-full bg-white/[0.05]"><div className="h-2 rounded-full bg-emerald-400/70" style={{ width: `${(v / top) * 100}%` }} /></div>
              </li>
            ))}
          </ol>
        </Card>
        <Card title="Limits reached">
          <DataTable head={["Limit", "Accounts", "Times"]} numeric={[1, 2]} empty="No limits reached."
            rows={limits.map(([k, label]) => [label, fmt(n(k)), fmt(ev[k]?.times ?? 0)])} />
        </Card>
      </div>
    </>
  );
}

function Traffic({ stats }: { stats: Stats }) {
  return (
    <>
      <Header title="Traffic" about={<>
        <p>Each browser counts once, under the source of its first attributed visit in the period: a campaign tag (utm_source) when the link carried one, otherwise the referring site. Only the site&apos;s domain is kept, never the page address.</p>
        <p>&ldquo;Direct or unknown&rdquo; covers typed addresses, bookmarks, apps that hide the referrer and visits before source tracking began{stats.attribution_since ? ` (${stats.attribution_since})` : ""}. Add <span className="kbd">?utm_source=linkedin&amp;utm_campaign=launch</span> to links you share to see each one here.</p>
      </>}>
        Where visitors came from and what they read, since {stats.since}.
      </Header>
      <div className="grid gap-4">
        <Card title="Daily visitors"><DailyBars days={stats.days} /></Card>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Sources">
            {stats.sources ? (
              <DataTable head={["Source", "Browsers", "Engaged", "Views"]} numeric={[1, 2, 3]} empty="No visits in this period."
                rows={stats.sources.map((r) => [r.source, fmt(r.browsers), fmt(r.engaged_browsers), fmt(r.views)])} />
            ) : <p className="text-sm text-[color:var(--dim)]">Source data is not available from the API yet.</p>}
          </Card>
          <Card title="Top pages">
            <DataTable head={["Page", "Browsers", "Views"]} numeric={[1, 2]} empty="No page views in this period."
              rows={stats.pages.map((p) => [<span key="p" className="kbd break-all">{p.path}</span>, fmt(p.visitors), fmt(p.views)])} />
          </Card>
          {stats.referrers && stats.referrers.length > 0 && (
            <Card title="Referring sites">
              <DataTable head={["Site", "Browsers"]} numeric={[1]} empty=""
                rows={stats.referrers.map((r) => [<span key="r" className="kbd break-all">{r.referrer}</span>, fmt(r.browsers)])} />
            </Card>
          )}
          {stats.campaigns && stats.campaigns.length > 0 && (
            <Card title="Campaigns">
              <DataTable head={["Campaign", "Source / medium", "Browsers", "Engaged"]} numeric={[2, 3]} empty=""
                rows={stats.campaigns.map((r) => [<span key="c" className="kbd">{r.campaign}</span>,
                  [r.source, r.medium].filter(Boolean).join(" / ") || "–", fmt(r.browsers), fmt(r.engaged_browsers)])} />
            </Card>
          )}
        </div>
        <Card title="By day">
          <DataTable head={["Day", "Unique browsers", "Opened /app", "Views"]} numeric={[1, 2, 3]} empty="No days in this period."
            rows={stats.days.map((d) => [<span key="d" className="kbd">{d.day}</span>, fmt(d.visitors), fmt(d.users), fmt(d.views)])} />
        </Card>
      </div>
    </>
  );
}

function Usage({ stats }: { stats: Stats }) {
  const actions = stats.actions ?? [];
  const available = Boolean(stats.actions && stats.app_page_activity);
  const b = stats.behavioral_signals;
  return (
    <>
      <Header title="Product usage" about={<>
        <p>Briefs and research count each completed run. Other feature uses count at most once per browser and feature per UTC day, so repeated filters do not inflate them. Historical run client IDs are salted IP hashes; newer feature tracking uses anonymous browser IDs, so they cannot be joined across periods. Prompts, filters and company names are not stored with feature usage events.</p>
        <p>Behavioural signals help rank relevant results; they are not evidence that a deal is accurate or verified. Deal ranking uses a maximum 3% adjustment and requires a minimum audience before engagement can affect order. Page visits show which area was opened, not whether its request succeeded.</p>
      </>}>
        What people completed in the app, and the engagement signals that inform ranking.
      </Header>
      <div className="grid gap-4">
        <Card title="Successful actions">
          {available ? (
            <DataTable head={["Action", "Successful uses", "Distinct clients"]} numeric={[1, 2]} empty=""
              rows={Object.entries(ACTION_LABELS).map(([action, label]) => {
                const row = actions.find((a) => a.action === action);
                return [label, fmt(row?.completions ?? 0), fmt(row?.clients ?? 0)];
              })} />
          ) : <p className="text-sm text-[color:var(--dim)]">Usage action metrics are not available yet.</p>}
        </Card>
        {b?.top_deals && b.top_briefs ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[["deal_search_submitted", "Searches"], ["deal_impression", "Deal impressions"], ["deal_opened", "Deal opens"],
                ["market_brief_opened", "Brief opens"]].map(([k, label]) => <Kpi key={k} value={b.totals?.[k] ?? 0} label={label} />)}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Deals with eligible engagement">
                <DataTable head={["Deal", "Impressions", "Openers", "CTR"]} numeric={[1, 2, 3]}
                  empty="No deals have enough impression data yet."
                  rows={b.top_deals.slice(0, 10).map((d) => [<span key="d" className="block max-w-48 truncate" title={d.deal_id}>{d.deal_id}</span>,
                    fmt(d.impressions), fmt(d.unique_openers), d.click_through_rate == null ? "–" : `${(d.click_through_rate * 100).toFixed(1)}%`])} />
              </Card>
              <Card title="Market briefs with repeat readers">
                <DataTable head={["Brief", "Browsers", "Active days"]} numeric={[1, 2]} empty="No repeat-reader brief signals yet."
                  rows={b.top_briefs.slice(0, 10).map((x) => [<span key="b" className="block max-w-56 truncate" title={x.brief_id}>{x.brief_id}</span>,
                    fmt(x.unique_visitors), fmt(x.active_days)])} />
              </Card>
            </div>
          </>
        ) : <Card><p className="text-sm text-[color:var(--dim)]">Behavioural signals are not available from the API yet.</p></Card>}
        <Card title="App areas opened">
          <DataTable head={["Area", "Browsers", "Page views"]} numeric={[1, 2]} empty="No app page visits in this period."
            rows={(stats.app_page_activity ?? []).map((r) => [r.feature, fmt(r.browsers), fmt(r.page_views)])} />
        </Card>
      </div>
    </>
  );
}

function Moderation({ adminKey, feedback, onReviewed }: { adminKey: string; feedback: FeedbackItem[]; onReviewed: (id: string) => void }) {
  const open = feedback.filter((f) => !f.reviewed_at);
  return (
    <>
      <Header title="Moderation">Company-submitted details and reports from users about results.</Header>
      <div className="grid gap-4">
        <Card><div className="-mt-8"><ClaimsPanel adminKey={adminKey} /></div></Card>
        <Card title={`Result reports${open.length ? ` · ${open.length} awaiting review` : ""}`}>
          <p className="mb-3 text-xs text-[color:var(--dim)]">Reports are leads for review, not verified corrections; check them against sources before acting.</p>
          {feedback.length === 0 ? <p className="text-sm text-[color:var(--dim)]">No reports have been submitted.</p> : (
            <ul className="divide-y divide-[color:var(--line)]">
              {feedback.map((item) => (
                <li key={item.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{item.category.replaceAll("_", " ")} · {item.result_type.replaceAll("_", " ")}
                      <span className="ml-2 text-xs font-normal text-[color:var(--dim)]">{new Date(item.created_at).toLocaleString()}</span></p>
                    <p className="mt-0.5 break-all text-xs text-[color:var(--dim)]">Result {item.result_id}</p>
                    {item.note && <p className="mt-2 whitespace-pre-wrap text-sm">{item.note}</p>}
                  </div>
                  {item.reviewed_at
                    ? <span className="rounded-full border hairline px-2 py-0.5 text-xs text-[color:var(--dim)]">Reviewed</span>
                    : <button type="button" onClick={() => onReviewed(item.id)} className="btn btn-ghost h-8 px-3 text-xs">Mark reviewed</button>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

function Review({ adminKey, onError }: { adminKey: string; onError: (e: string) => void }) {
  const [role, setRole] = useState<"a" | "b" | "adjudicator">("a");
  const [name, setName] = useState("");
  const [links, setLinks] = useState<{ role: string; name: string; url: string }[]>([]);
  async function create() {
    onError("");
    try {
      const r = await fetch(apiUrl("/api/admin/review/annotators"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: adminKey, role, name }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail ?? "Could not create the link");
      setLinks((rows) => [{ role: data.role, name: data.name, url: `${window.location.origin}${data.path}` }, ...rows]);
      setName("");
    } catch (e) {
      onError((e as Error).message);
    }
  }
  return (
    <>
      <Header title="Data review" about={<p>Annotators label the blind sample on the page the link opens; they never see the system&apos;s answers or each other&apos;s labels. The adjudicator sees only the items where A and B disagree. Labels are imported into the review folder every day, progress shows on the evaluation page, and the review is scored and published automatically once every headline and pair has a final label.</p>}>
        Private labelling links for the independent review: one per annotator (A and B) and one for the adjudicator. A link is shown once, so copy it now.
      </Header>
      <Card title="Create a link">
        <div className="flex flex-wrap gap-2">
          <select value={role} onChange={(e) => setRole(e.target.value as typeof role)} className="field w-auto">
            <option value="a">Annotator A</option><option value="b">Annotator B</option><option value="adjudicator">Adjudicator</option>
          </select>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name or initials" className="field min-w-0 flex-1" />
          <button type="button" onClick={create} disabled={!name.trim()} className="btn btn-primary disabled:opacity-50">Create link</button>
        </div>
        {links.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm">
            {links.map((l) => (
              <li key={l.url} className="rounded-lg border hairline p-3">
                <p className="text-[color:var(--muted)]">{l.role === "adjudicator" ? "Adjudicator" : `Annotator ${l.role.toUpperCase()}`}: {l.name}</p>
                <p className="kbd mt-1 break-all">{l.url}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Investor home countries" className="mt-6">
        <InvestorHomesPanel adminKey={adminKey} />
      </Card>
    </>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

/** The owner's console. Opening it marks this browser as the owner's, so its visits are not counted. */
export default function Admin() {
  const [key, setKey] = useState("");
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loadedKey, setLoadedKey] = useState("");
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [pendingClaims, setPendingClaims] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [section, setSection] = useState<Section>("overview");

  async function load(k: string, d: number) {
    setError("");
    setBusy(true);
    try {
      const r = await fetch(apiUrl("/api/admin/stats"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k, days: d, visitor: browserVisitorId() }),
      });
      if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "Stats unavailable");
      setStats(await r.json());
      setLoadedKey(k);
      try { localStorage.setItem("di_admin", k); } catch { /* storage blocked */ }
      const [fb, claims] = await Promise.all([
        fetch(apiUrl("/api/admin/feedback"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: k }) }),
        fetch(apiUrl("/api/admin/claims"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: k, status: "pending" }) })
          .catch(() => null),
      ]);
      if (!fb.ok) throw new Error("Feedback queue unavailable");
      setFeedback((await fb.json()).items);
      if (claims?.ok) setPendingClaims(((await claims.json()) as unknown[]).length);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function markReviewed(id: string) {
    try {
      const r = await fetch(apiUrl(`/api/admin/feedback/${encodeURIComponent(id)}/review`), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: loadedKey }),
      });
      if (!r.ok) throw new Error("Could not update feedback status.");
      setFeedback((rows) => rows.map((row) => (row.id === id ? { ...row, reviewed_at: new Date().toISOString() } : row)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function signOut() {
    try { localStorage.removeItem("di_admin"); } catch { /* storage blocked */ }
    setStats(null);
    setLoadedKey("");
    setKey("");
  }

  useEffect(() => {
    try {
      localStorage.setItem("di_owner", "1");
      const k = localStorage.getItem("di_admin");
      if (k) {
        setKey(k);
        load(k, days);
      }
    } catch { /* storage blocked */ }
    const fromHash = window.location.hash.replace("#", "") as Section;
    if (SECTIONS.some((s) => s.id === fromHash)) setSection(fromHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function go(s: Section) {
    setSection(s);
    window.history.replaceState(null, "", `#${s}`);
  }

  // ── Sign-in ──
  if (!stats) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <meta name="robots" content="noindex" />
        <form className="w-full max-w-sm rounded-2xl border hairline bg-white/[0.02] p-6 shadow-xl"
          onSubmit={(e) => { e.preventDefault(); load(key, days); }}>
          <div className="flex items-center gap-2 text-sm text-[color:var(--muted)]">
            <Icon d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" /> Deal Intelligence
          </div>
          <h1 className="mt-3 text-xl font-semibold tracking-tight">Admin console</h1>
          <p className="mt-1 text-sm text-[color:var(--muted)]">Owner access. This browser is excluded from visitor counts.</p>
          <label htmlFor="admin-key" className="mt-5 block text-xs text-[color:var(--muted)]">Admin key</label>
          <input id="admin-key" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Admin key"
            autoComplete="current-password" className="field mt-1 w-full" />
          {error && <p className="mt-3 text-sm text-risk" role="alert">{error}</p>}
          <button className="btn btn-primary mt-4 w-full" disabled={busy || !key}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </main>
    );
  }

  const t = stats.totals;
  const counts = Object.fromEntries((stats.actions ?? []).map((r) => [r.action, r.completions]));
  const actionsAvailable = Boolean(stats.actions && stats.app_page_activity);
  const research = RESEARCH_ACTIONS.reduce((a, k) => a + (counts[k] ?? 0), 0);
  const featureUses = (stats.actions ?? []).filter((r) => r.action !== "brief_completed" && !RESEARCH_ACTIONS.includes(r.action))
    .reduce((a, r) => a + r.completions, 0);
  const openReports = feedback.filter((f) => !f.reviewed_at).length;
  const badge: Partial<Record<Section, number>> = { moderation: pendingClaims + openReports };

  return (
    <div className="min-h-screen">
      <meta name="robots" content="noindex" />
      <header className="sticky top-0 z-30 border-b hairline bg-[color:var(--bg)]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <Icon d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" className="h-5 w-5 text-emerald-400" />
            <span className="font-semibold tracking-tight">Admin console</span>
            <span className="rounded-full border border-emerald-400/40 px-2 py-0.5 text-[0.6875rem] font-medium text-emerald-400">Super admin</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="admin-period" className="sr-only">Period</label>
            <select id="admin-period" value={days} className="field h-9 w-auto py-0 text-sm"
              onChange={(e) => { const d = Number(e.target.value); setDays(d); load(loadedKey, d); }}>
              {[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>)}
            </select>
            <button type="button" className="btn btn-ghost h-9 px-3 text-sm" onClick={() => load(loadedKey, days)} disabled={busy}>
              {busy ? "Refreshing…" : "Refresh"}
            </button>
            <button type="button" className="btn btn-ghost h-9 px-3 text-sm" onClick={signOut}>Sign out</button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-2 lg:hidden" aria-label="Admin sections">
          {SECTIONS.map((s) => (
            <button key={s.id} type="button" onClick={() => go(s.id)} aria-current={section === s.id ? "page" : undefined}
              className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${section === s.id ? "bg-white/10 font-medium" : "text-[color:var(--muted)]"}`}>
              {s.label}{badge[s.id] ? ` · ${badge[s.id]}` : ""}
            </button>
          ))}
        </nav>
      </header>

      <div className="mx-auto flex max-w-7xl gap-8 px-4 py-6">
        <aside className="hidden w-52 shrink-0 lg:block">
          <nav className="sticky top-20 space-y-0.5" aria-label="Admin sections">
            {SECTIONS.map((s) => (
              <button key={s.id} type="button" onClick={() => go(s.id)} aria-current={section === s.id ? "page" : undefined}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition ${section === s.id ? "bg-white/[0.07] font-medium" : "text-[color:var(--muted)] hover:bg-white/[0.04] hover:text-[color:var(--text)]"}`}>
                <Icon d={s.icon} />
                <span className="flex-1">{s.label}</span>
                {badge[s.id] ? <span className="rounded-full bg-amber-400/15 px-1.5 text-xs text-amber-400">{badge[s.id]}</span> : null}
              </button>
            ))}
            <p className="px-3 pt-4 text-xs text-[color:var(--dim)]">Data since {stats.since}</p>
          </nav>
        </aside>

        <main className="min-w-0 flex-1">
          {error && <p className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-risk" role="alert">{error}</p>}

          {section === "overview" && (
            <>
              <Header title="Overview" about={<p>Unique browsers are anonymous browser IDs, not verified people. Engaged browsers viewed two or more pages or used a feature; single-view browsers include crawlers and link previews. This console excludes this browser. Analysis and research runs are keyed by a salted IP hash, so runs from this network are also excluded, which can include other people using the same network.</p>}>
                {days === 1 ? "Today" : `The last ${days} days`}, since {stats.since}.
              </Header>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Kpi value={t.engaged_visitors ?? null} label="Engaged browsers" hint={`of ${fmt(t.visitors)} unique`} />
                <Kpi value={actionsAvailable ? counts.brief_completed ?? 0 : null} label="Company briefs completed" />
                <Kpi value={actionsAvailable ? research : null} label="Research answers and reports" />
                <Kpi value={actionsAvailable ? featureUses : null} label="Successful feature uses" />
                <Kpi value={stats.plan_funnel?.paying_accounts ?? null} label="Paying accounts" hint={`${fmt(stats.plan_funnel?.free_accounts)} on the free plan`} />
                <Kpi value={t.returning_users} label="Returning users" />
                <Kpi value={pendingClaims} label="Company submissions to review" tone="attention" />
                <Kpi value={openReports} label="Result reports to review" tone="attention" />
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-3">
                <Card title="Daily visitors" className="lg:col-span-2"><DailyBars days={stats.days} /></Card>
                <Card title="Top sources">
                  <DataTable head={["Source", "Browsers"]} numeric={[1]} empty="No visits in this period."
                    rows={(stats.sources ?? []).slice(0, 6).map((r) => [r.source, fmt(r.browsers)])} />
                </Card>
              </div>
              <div className="mt-4">
                <Card title="Top pages">
                  <DataTable head={["Page", "Browsers", "Views"]} numeric={[1, 2]} empty="No page views in this period."
                    rows={stats.pages.slice(0, 8).map((p) => [<span key="p" className="kbd break-all">{p.path}</span>, fmt(p.visitors), fmt(p.views)])} />
                </Card>
              </div>
            </>
          )}
          {section === "accounts" && <div className="-mt-8"><AccountsPanel adminKey={loadedKey} days={days} /></div>}
          {section === "revenue" && <Revenue funnel={stats.plan_funnel} />}
          {section === "traffic" && <Traffic stats={stats} />}
          {section === "usage" && <Usage stats={stats} />}
          {section === "moderation" && <Moderation adminKey={loadedKey} feedback={feedback} onReviewed={markReviewed} />}
          {section === "review" && <Review adminKey={loadedKey} onError={setError} />}
        </main>
      </div>
    </div>
  );
}
