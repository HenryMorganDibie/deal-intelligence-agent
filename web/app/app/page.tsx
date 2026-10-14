"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { SeverityBadge } from "../../components/app/BriefView";
import { Container } from "../../components/primitives";
import { analyse, ApiError } from "../../lib/api";
import { formatDate } from "../../lib/brief";
import { addToHistory, readHistory, type HistoryItem } from "../../lib/history";

const EXAMPLES = [
  { company: "Intel", ticker: "INTC" },
  { company: "Boeing", ticker: "BA" },
  { company: "Naspers", ticker: "NPN.JO" },
  { company: "GTBank", ticker: "GTCO.LG" },
];

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

  useEffect(() => {
    setRows(readHistory());
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

  return (
    <Container className="grid gap-10 py-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-14 lg:py-14">
      <section aria-labelledby="new-title" className="min-w-0">
        <p className="eyebrow">New brief</p>
        <h1 id="new-title" className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">
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
            Free to use. Up to 10 analyses a day per visitor. No account needed.
          </p>
        </div>
      </section>

      <section aria-labelledby="history-title" className="min-w-0">
        <div className="flex items-baseline justify-between">
          <h2 id="history-title" className="eyebrow">
            Your briefs
          </h2>
          {rows && rows.length > 0 && <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{rows.length}</span>}
        </div>
        <div className="mt-3 border-t hairline">
          {rows === null ? (
            <p className="py-6 text-sm text-[color:var(--dim)]">Loading...</p>
          ) : rows.length === 0 ? (
            <p className="py-6 text-sm text-[color:var(--muted)]">
              No briefs yet. Run your first analysis and it will appear here. This list is kept in your
              browser only.
            </p>
          ) : (
            <ul>
              {rows.map((r) => (
                <li key={r.id} className="border-b hairline">
                  <Link
                    href={`/app/briefs/${r.id}`}
                    className="-mx-3 flex items-center gap-4 rounded-lg px-3 py-4 transition-colors hover:bg-white/[0.03]"
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
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </Container>
  );
}
