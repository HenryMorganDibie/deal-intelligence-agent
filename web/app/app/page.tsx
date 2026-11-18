"use client";

import { ErrorNote } from "../../components/app/ui";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { SeverityBadge } from "../../components/app/BriefView";
import { Container } from "../../components/primitives";
import { analyse, ApiError } from "../../lib/api";
import { formatDate } from "../../lib/brief";
import { addToHistory, readHistory, removeFromHistory, type HistoryItem } from "../../lib/history";
import { AFRICAN_COUNTRIES } from "../../lib/countries";
import { get } from "../../lib/market";

const EXAMPLES = [
  { company: "MTN Nigeria", ticker: "MTNN.LG", country: "NG" },
  { company: "Safaricom", ticker: "SCOM.NR", country: "KE" },
  { company: "Naspers", ticker: "NPN.JO", country: "ZA" },
  { company: "Jumia", ticker: "JMIA", country: "" },
];

// Ready-made market briefs: each opens the market brief form already filled in.
const MARKET_STARTS = [
  { label: "Nigeria, last 90 days", query: "country=NG&lookback_days=90" },
  { label: "Kenya fintech", query: "country=KE&sector=fintech&lookback_days=90" },
  { label: "Egypt, last 30 days", query: "country=EG&lookback_days=30" },
  { label: "Africa energy deals", query: "sector=energy&lookback_days=90" },
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
        ...(country ? { country } : {}),
        lookback_days: lookback,
        compliance,
      });
      addToHistory({ ...result, created_at: new Date().toISOString() });
      router.push(`/briefs/${result.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The analysis failed. Try again in a minute.");
      setRunning(null);
    }
  }

  const visibleMarketBriefs = (marketBriefs ?? []).filter((brief) => !hiddenMarketBriefIds.includes(brief.id));
  const fieldLabel = "mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]";
  const hint = "mt-1.5 block text-xs leading-relaxed text-[color:var(--dim)]";
  const chip = "rounded-full border hairline px-3 py-1.5 text-[0.8125rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)] disabled:opacity-40";
  const removeButton = "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[color:var(--dim)] transition-colors hover:bg-white/[0.06] hover:text-[color:var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--text)]";

  return (
    <Container className="py-10 lg:py-14">
      <header className="max-w-2xl">
        <p className="eyebrow">Briefs</p>
        <h1 className="h2 mt-3 text-[1.75rem] sm:text-[2.25rem]">Sourced reports, written for you.</h1>
        <p className="mt-3 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
          Ask about one company or a whole market. Each brief takes a minute or two, and every fact links to its source.
        </p>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-2 lg:gap-8">
        <section aria-labelledby="company-title" className="panel flex min-w-0 flex-col p-5 sm:p-6">
          <p className="eyebrow">One company</p>
          <h2 id="company-title" className="h2 mt-2 text-xl">Company brief</h2>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
            What matters about a company right now: filings, news, deals and risk signals, scored and sourced.
          </p>

          {running ? (
            <div className="mt-6"><Running company={running} /></div>
          ) : (
            <form onSubmit={submit} className="mt-6 space-y-4">
              <label className="block">
                <span className={fieldLabel}>Company</span>
                <input required maxLength={120} value={company} onChange={(e) => setCompany(e.target.value)}
                  placeholder="e.g. MTN Nigeria" className="field" />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className={fieldLabel}>Country</span>
                  <select value={country} onChange={(e) => setCountry(e.target.value)} className="field" aria-label="Country">
                    <option value="">Any (or listed in the US)</option>
                    {AFRICAN_COUNTRIES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                  </select>
                  <span className={hint}>News is searched in that country&apos;s own outlets and languages.</span>
                </label>
                <label className="block">
                  <span className={fieldLabel}>Period</span>
                  <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))} className="field">
                    <option value={30}>Last 30 days</option>
                    <option value={90}>Last 90 days</option>
                    <option value={180}>Last 6 months</option>
                    <option value={365}>Last year</option>
                  </select>
                </label>
              </div>
              <details className="group rounded-xl border hairline px-4 py-3">
                <summary className="cursor-pointer select-none text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">
                  More options
                </summary>
                <div className="mt-4 space-y-4">
                  <label className="block">
                    <span className={fieldLabel}>Ticker, for listed shares</span>
                    <input maxLength={20} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      placeholder="e.g. MTNN.LG" className="field kbd" />
                    <span className={hint}>Add the exchange: .LG Lagos, .NR Nairobi, .JO Johannesburg. US listings such as Jumia need no suffix.</span>
                  </label>
                  <label className="flex items-start gap-3">
                    <input type="checkbox" checked={compliance} onChange={(e) => setCompliance(e.target.checked)}
                      className="mt-0.5 h-4 w-4 accent-verified" />
                    <span>
                      <span className="block text-[0.875rem]">Only high-confidence signals</span>
                      <span className={hint}>Leaves out weaker signals, for a client file or compliance record.</span>
                    </span>
                  </label>
                </div>
              </details>
              <button type="submit" className="btn btn-primary w-full sm:w-auto">Write company brief</button>
              {error && <ErrorNote message={error} />}
            </form>
          )}

          <div className="mt-6">
            <p className="text-[0.75rem] text-[color:var(--dim)]">Try</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex.ticker} type="button" disabled={!!running} className={chip}
                  onClick={() => { setCompany(ex.company); setTicker(ex.ticker); setCountry(ex.country); }}>
                  {ex.company}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section aria-labelledby="market-title" className="panel flex min-w-0 flex-col p-5 sm:p-6">
          <p className="eyebrow">A whole market</p>
          <h2 id="market-title" className="h2 mt-2 text-xl">Market brief</h2>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
            Deal activity in any African country or sector, ready for a pitch, an investment committee or a client newsletter:
            key deals, values, comparables and who is investing.
          </p>
          <ul className="mt-6 space-y-2.5 text-[0.875rem] text-[color:var(--muted)]">
            {["Deal counts and disclosed values for the period", "The key transactions, marked as confirmed or single-source",
              "Comparable deals and the most active investors", "A written analysis with numbered citations"].map((item) => (
              <li key={item} className="flex gap-2.5"><span aria-hidden className="text-verified">✓</span>{item}</li>
            ))}
          </ul>
          <Link href="/market-briefs/new" className="btn btn-primary mt-6 w-full sm:w-auto sm:self-start">Create market brief</Link>
          <div className="mt-6">
            <p className="text-[0.75rem] text-[color:var(--dim)]">Start from</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {MARKET_STARTS.map((m) => (
                <Link key={m.label} href={`/market-briefs/new?${m.query}`} className={chip}>{m.label}</Link>
              ))}
            </div>
          </div>
        </section>
      </div>

      <section aria-labelledby="yours-title" className="mt-12">
        <h2 id="yours-title" className="eyebrow">Your briefs</h2>
        <div className="mt-4 grid gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="flex items-baseline justify-between">
              <h3 className="text-[0.9375rem] font-medium">Company briefs</h3>
              {rows && rows.length > 0 && <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{rows.length}</span>}
            </div>
            <div className="mt-3 border-t hairline">
              {rows === null ? (
                <p className="py-5 text-sm text-[color:var(--dim)]">Loading…</p>
              ) : rows.length === 0 ? (
                <p className="py-5 text-sm text-[color:var(--muted)]">None yet. Company briefs you write are listed here, on this device.</p>
              ) : (
                <ul>
                  {rows.map((r) => (
                    <li key={r.id} className="flex items-center gap-2 border-b hairline">
                      <Link href={`/briefs/${r.id}`} className="flex min-w-0 flex-1 items-center gap-4 rounded-lg py-3.5 pl-1 pr-2 transition-colors hover:bg-white/[0.03]">
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
                      <button type="button" aria-label={`Remove ${r.company} from your briefs`} title="Remove from your briefs" className={removeButton}
                        onClick={() => { removeFromHistory(r.id); setRows(rows.filter((item) => item.id !== r.id)); }}>
                        <span aria-hidden="true" className="text-lg leading-none">×</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <div className="min-w-0">
            <h3 className="text-[0.9375rem] font-medium">Market briefs</h3>
            <div className="mt-3 border-t hairline">
              {marketBriefs === null ? <p className="py-5 text-sm text-[color:var(--dim)]">Loading…</p> :
               visibleMarketBriefs.length === 0 ? <p className="py-5 text-sm text-[color:var(--muted)]">{marketBriefs.length ? "No visible market briefs. Removed items stay saved and can still be opened with their original links." : "None yet. Market briefs you create are saved to your account and listed here."}</p> :
               <ul>{visibleMarketBriefs.slice(0, 5).map((brief) => (
                 <li key={brief.id} className="flex items-center gap-2 border-b hairline">
                   <Link href={"/market-briefs/" + encodeURIComponent(brief.id)} className="min-w-0 flex-1 rounded-lg py-3.5 pl-1 pr-2 transition-colors hover:bg-white/[0.03]">
                     <p className="truncate font-medium">{brief.title}</p>
                     <p className="mt-0.5 text-[0.8125rem] text-[color:var(--muted)]">{brief.scope_label} · {brief.transaction_count} records · {formatDate(brief.created_at)}</p>
                   </Link>
                   <button type="button" aria-label={"Remove " + brief.title + " from recent market briefs"} title="Remove from your recent list" className={removeButton}
                     onClick={() => {
                       const next = [...new Set([...hiddenMarketBriefIds, brief.id])];
                       setHiddenMarketBriefIds(next);
                       try { window.localStorage.setItem("deal-intel:hidden-market-briefs", JSON.stringify(next)); } catch {}
                     }}>
                     <span aria-hidden="true" className="text-lg leading-none">×</span>
                   </button>
                 </li>
               ))}</ul>}
            </div>
          </div>
        </div>
      </section>

      <p className="mt-10 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
        The free plan includes 30 briefs and research runs a month (up to 15 a day). <Link href="/account/billing" className="underline underline-offset-2 hover:text-[color:var(--text)]">Pro and Team</Link> include more, with no daily limit.
      </p>
    </Container>
  );
}
