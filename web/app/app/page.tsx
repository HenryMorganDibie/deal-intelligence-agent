"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { SeverityBadge } from "../../components/app/BriefView";
import { Container } from "../../components/primitives";
import { analyse, ApiError } from "../../lib/api";
import { formatDate } from "../../lib/brief";
import { addToHistory, readHistory, removeFromHistory, type HistoryItem } from "../../lib/history";
import { get } from "../../lib/market";

const EXAMPLES = [
  { company: "Intel", ticker: "INTC" },
  { company: "Boeing", ticker: "BA" },
  { company: "Naspers", ticker: "NPN.JO" },
  { company: "GTBank", ticker: "GTCO.LG" },
];

type RecentMarketBrief = { id: string; title: string; created_at: string; scope_label: string; period_start: string; period_end: string; transaction_count: string | number };

const STAGES = [
  "Collecting SEC filings, exchange disclosures and news",
  "Running the deterministic rule engine",
  "Attributing events to their subject",
  "Scoring and calibrating",
  "Writing the brief",
];

function Running({ company }: { company: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, []);
  const stage = Math.min(STAGES.length - 1, Math.floor(seconds / 9));
  return (
    <div className="panel relative overflow-hidden p-5" role="status" aria-live="polite">
      <div className="scan" aria-hidden />
      <p className="kbd text-[0.8125rem] text-[color:var(--muted)]">
        <span className="text-verified">$</span> analyse --company {JSON.stringify(company)}
        <span className="ml-3 text-[color:var(--dim)]">{seconds}s</span>
      </p>
      <ol className="mt-4 space-y-1.5">
        {STAGES.map((s, i) => (
          <li key={s} className={`kbd text-[0.75rem] transition-opacity ${i <= stage ? "opacity-100" : "opacity-25"}`}>
            <span className={i < stage ? "text-verified" : "text-[color:var(--muted)]"}>{i < stage ? "✓" : "·"}</span>{" "}
            <span className="text-[color:var(--text)]">{s}</span>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-[0.8125rem] text-[color:var(--dim)]">
        Usually 20 to 90 seconds, depending on how much the company has filed.
      </p>
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [company, setCompany] = useState("");
  const [ticker, setTicker] = useState("");
  const [country, setCountry] = useState("");
  const [lookback, setLookback] = useState(90);
  const [compliance, setCompliance] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<HistoryItem[] | null>(null);
  const [marketBriefs, setMarketBriefs] = useState<RecentMarketBrief[] | null>(null);
  const [hiddenMarketBriefIds, setHiddenMarketBriefIds] = useState<string[]>([]);

  useEffect(() => {
    setRows(readHistory());
    try {
      const hidden = JSON.parse(window.localStorage.getItem("deal-intel:hidden-market-briefs") || "[]");
      if (Array.isArray(hidden)) setHiddenMarketBriefIds(hidden.filter((id): id is string => typeof id === "string"));
    } catch {
      // If browser storage is unavailable, the recent list remains fully visible.
    }
    get<{ briefs: RecentMarketBrief[] }>("/api/market-briefs")
      .then((result) => setMarketBriefs(result.briefs ?? []))
      .catch(() => setMarketBriefs([]));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!company.trim() || running) return;
    setError(null);
    setRunning(company.trim());
    try {
      const result = await analyse({
        company: company.trim(),
        ...(ticker.trim() ? { ticker: ticker.trim() } : {}),
        ...(country.trim() ? { country: country.trim().toUpperCase() } : {}),
        lookback_days: lookback,
        compliance,
      });
      addToHistory({ ...result, created_at: new Date().toISOString() });
      router.push(`/app/briefs/${result.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The analysis failed. Try again in a minute.");
      setRunning(null);
    }
  }

  const visibleMarketBriefs = (marketBriefs ?? []).filter((brief) => !hiddenMarketBriefIds.includes(brief.id));

  return (
    <Container className="py-10 lg:py-14">
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
      <section aria-labelledby="new-title" className="panel min-w-0 p-5 sm:p-6">
        <p className="eyebrow">Company analysis</p>
        <h1 id="new-title" className="h2 mt-3 text-xl">
          Analyse a company.
        </h1>
        <p className="mt-3 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
          US companies are matched to SEC EDGAR by name or ticker. For African listings, add the exchange suffix: .JO
          (JSE), .LG (NGX) or .NR (NSE Kenya). For any of the 54 African countries, add the country code so news is
          searched in that country&apos;s own edition and languages.
        </p>

        {running ? (
          <div className="mt-7">
            <Running company={running} />
          </div>
        ) : (
          <form onSubmit={submit} className="mt-7 space-y-4">
            <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
              <label className="block">
                <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Company</span>
                <input
                  required
                  maxLength={120}
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Intel"
                  className="field"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Ticker (optional)</span>
                <input
                  maxLength={20}
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="INTC"
                  className="field kbd"
                />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block">
                <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Country (optional)</span>
                <input
                  maxLength={3}
                  value={country}
                  onChange={(e) => setCountry(e.target.value.toUpperCase())}
                  placeholder="SN"
                  className="field kbd"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">Lookback</span>
                <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))} className="field">
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                  <option value={180}>180 days</option>
                  <option value={365}>1 year</option>
                </select>
              </label>
              <label className="flex items-end gap-3 pb-3">
                <input
                  type="checkbox"
                  checked={compliance}
                  onChange={(e) => setCompliance(e.target.checked)}
                  className="h-4 w-4 accent-[#6ee7c8]"
                />
                <span className="text-[0.875rem] text-[color:var(--muted)]">Compliance mode (stricter)</span>
              </label>
            </div>
            <button type="submit" className="btn btn-primary w-full sm:w-auto">
              Run analysis
            </button>
            {error && (
              <p className="text-sm text-risk" role="alert">
                {error}
              </p>
            )}
          </form>
        )}

        <div className="mt-8">
          <p className="eyebrow">Try</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.ticker}
                type="button"
                disabled={!!running}
                onClick={() => {
                  setCompany(ex.company);
                  setTicker(ex.ticker);
                }}
                className="rounded-full border hairline px-3 py-1.5 text-[0.8125rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)] disabled:opacity-40"
              >
                {ex.company} <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{ex.ticker}</span>
              </button>
            ))}
          </div>
          <p className="mt-6 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
            Free to use. Up to 1,000 analyses a day per visitor, subject to service capacity. No account needed.
          </p>
        </div>
        <div className="mt-8">
          <div className="flex items-baseline justify-between">
            <h2 id="history-title" className="eyebrow">Your company briefs</h2>
            {rows && rows.length > 0 && <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{rows.length}</span>}
          </div>
          <div className="mt-3 border-t hairline">
            {rows === null ? (
              <p className="py-6 text-sm text-[color:var(--dim)]">Loading...</p>
            ) : rows.length === 0 ? (
              <p className="py-6 text-sm text-[color:var(--muted)]">
                No company briefs yet. Run a company analysis and it will appear here. This list is kept in your browser only.
              </p>
            ) : (
              <ul>
                {rows.map((r) => (
                  <li key={r.id} className="flex items-center gap-2 border-b hairline">
                    <Link
                      href={`/app/briefs/${r.id}`}
                      className="flex min-w-0 flex-1 items-center gap-4 rounded-lg py-4 pl-1 pr-2 transition-colors hover:bg-white/[0.03]"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">
                          {r.company}
                          {r.ticker && <span className="kbd ml-2 text-[0.75rem] text-[color:var(--dim)]">{r.ticker}</span>}
                        </p>
                        <p className="mt-0.5 text-[0.8125rem] text-[color:var(--muted)]">
                          {r.signal_count} signal{r.signal_count === 1 ? "" : "s"} · {formatDate(r.created_at)}
                        </p>
                      </div>
                      {r.severity && <SeverityBadge severity={r.severity} />}
                    </Link>
                    <button
                      type="button"
                      aria-label={`Remove ${r.company} from your briefs`}
                      title="Remove from your briefs"
                      onClick={() => {
                        removeFromHistory(r.id);
                        setRows(rows.filter((item) => item.id !== r.id));
                      }}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[color:var(--dim)] transition-colors hover:bg-white/[0.06] hover:text-[color:var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--text)]"
                    >
                      <span aria-hidden="true" className="text-lg leading-none">×</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
      <section aria-labelledby="market-intelligence-title" className="panel min-w-0 p-5 sm:p-6">
        <p className="eyebrow">Market intelligence</p>
        <h2 id="market-intelligence-title" className="h2 mt-3 text-xl">Deals &amp; M&amp;A across Africa</h2>
        <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">
          Create an analyst-ready market report with dated transactions, disclosed-value metrics, comparable activity and linked source evidence.
        </p>
        <Link href="/app/market-briefs/new" className="btn btn-primary mt-4 inline-flex">
          Create market brief
        </Link>
        <div className="mt-8">
          <div className="flex items-baseline justify-between">
            <p className="eyebrow">Recent market briefs</p>
            <Link href="/app/market-briefs/new" className="text-xs text-[color:var(--muted)] hover:text-[color:var(--text)]">New brief →</Link>
          </div>
          <div className="mt-3 border-t hairline">
            {marketBriefs === null ? <p className="py-3 text-sm text-[color:var(--dim)]">Loading market briefs…</p> :
             visibleMarketBriefs.length === 0 ? <p className="py-3 text-sm text-[color:var(--muted)]">{marketBriefs.length ? "No visible market briefs. Removed items stay saved and can still be opened with their original links." : "Your generated market briefs will appear here."}</p> :
             <ul>{visibleMarketBriefs.slice(0, 5).map((brief) => (
               <li key={brief.id} className="flex items-center gap-2 border-b hairline">
                 <Link href={"/app/market-briefs/" + encodeURIComponent(brief.id)} className="min-w-0 flex-1 py-3 transition-colors hover:text-[color:var(--text)]">
                   <p className="font-medium">{brief.title}</p>
                   <p className="mt-1 text-xs text-[color:var(--muted)]">{brief.scope_label} · {brief.transaction_count} records</p>
                   <p className="mt-1 text-xs text-[color:var(--dim)]">{formatDate(brief.created_at)}</p>
                 </Link>
                 <button
                   type="button"
                   aria-label={"Remove " + brief.title + " from recent market briefs"}
                   title="Remove from your recent list"
                   onClick={() => {
                     const next = [...new Set([...hiddenMarketBriefIds, brief.id])];
                     setHiddenMarketBriefIds(next);
                     try { window.localStorage.setItem("deal-intel:hidden-market-briefs", JSON.stringify(next)); } catch {}
                   }}
                   className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[color:var(--dim)] transition-colors hover:bg-white/[0.06] hover:text-[color:var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--text)]"
                 >
                   <span aria-hidden="true" className="text-lg leading-none">×</span>
                 </button>
               </li>
             ))}</ul>}
          </div>
        </div>
      </section>
      </div>

    </Container>
  );
}
