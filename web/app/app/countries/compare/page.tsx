"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";
import { AFRICAN_COUNTRIES } from "../../../../lib/countries";

type Row = {
  iso2: string; name: string; currency: string; risk_score: number | null; risk_tier: string | null; deals_12m: number;
  rank: number | null; median_size_usd: number | null; disclosed_share: number | null; top_sector: string | null;
  foreign_investor_share: number | null; top_foreign_origin: string | null; market_ytd_usd: number | null;
  market_cap_usd: number | null; policy_rate: number | null; tbill: number | null; stablecoin_premium: number | null;
  currency_depreciation_last_year_pct: number | null; gdp_growth: number | null; inflation: number | null; debt_to_gdp: number | null;
};

const pct = (v: number | null, digits = 1) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`);
const plain = (v: number | null, unit = "") => (v === null || v === undefined ? "n/a" : `${v}${unit}`);
const usd = (v: number | null) => (!v ? "n/a" : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}bn` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}m` : `$${Math.round(v).toLocaleString("en-US")}`);

const LINES: [string, (r: Row) => string][] = [
  ["Country risk", (r) => (r.risk_score !== null ? `${r.risk_score} · ${r.risk_tier}` : "n/a")],
  ["Deals, last 12 months", (r) => `${r.deals_12m}${r.rank ? ` (rank ${r.rank})` : ""}`],
  ["Median deal (disclosed)", (r) => usd(r.median_size_usd)],
  ["Deals with an amount", (r) => pct(r.disclosed_share, 0)],
  ["Top sector", (r) => r.top_sector ?? "n/a"],
  ["Foreign investor share", (r) => pct(r.foreign_investor_share, 0)],
  ["Top foreign investor origin", (r) => r.top_foreign_origin ?? "n/a"],
  ["Stock market value", (r) => usd(r.market_cap_usd)],
  ["Stock market this year ($)", (r) => pct(r.market_ytd_usd)],
  ["Policy rate", (r) => plain(r.policy_rate, "%")],
  ["Shortest Treasury bill", (r) => plain(r.tbill, "%")],
  ["Stablecoin premium", (r) => pct(r.stablecoin_premium)],
  ["Currency, last full year vs $", (r) => (r.currency_depreciation_last_year_pct !== null ? `${r.currency_depreciation_last_year_pct}% weaker` : "n/a")],
  ["GDP growth, this year (IMF)", (r) => plain(r.gdp_growth, "%")],
  ["Inflation, this year (IMF)", (r) => plain(r.inflation, "%")],
  ["Government debt, % of GDP (IMF)", (r) => plain(r.debt_to_gdp, "%")],
];

/** Two to four African countries side by side, on everything a country page shows. */
export default function CompareCountriesPage() {
  const [codes, setCodes] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = (new URLSearchParams(window.location.search).get("codes") || "").toUpperCase().split(",").filter((c) => /^[A-Z]{2}$/.test(c));
    setCodes(q.length ? q.slice(0, 4) : ["NG", "KE"]);
  }, []);

  useEffect(() => {
    window.history.replaceState(null, "", `?codes=${codes.join(",")}`);
    if (codes.length < 2) { setRows(null); return; }
    setLoading(true); setError("");
    get<{ countries: Row[] }>(`/api/countries/compare?codes=${codes.join(",")}`)
      .then((r) => setRows(r.countries))
      .catch((e) => setError(e instanceof ApiError ? e.message : "The comparison could not be loaded."))
      .finally(() => setLoading(false));
  }, [codes]);

  return (
    <Container className="max-w-6xl py-10 lg:py-14">
      <Link href="/countries" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">← All countries</Link>
      <div className="mt-4">
        <PageHeader eyebrow="Countries" title="Compare countries">
          Up to four countries side by side: risk, deal flow, who invests, the stock market, rates, the currency and the IMF outlook.
        </PageHeader>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {codes.map((c) => (
          <span key={c} className="flex items-center gap-1 rounded-full border hairline px-3 py-1 text-sm">
            {AFRICAN_COUNTRIES.find(([k]) => k === c)?.[1] ?? c}
            <button type="button" aria-label={`Remove ${c}`} className="text-[color:var(--muted)] hover:text-risk" onClick={() => setCodes((x) => x.filter((k) => k !== c))}>✕</button>
          </span>
        ))}
        {codes.length < 4 && (
          <select value="" onChange={(e) => e.target.value && setCodes((x) => [...x, e.target.value])} aria-label="Add a country"
            className="rounded-lg border hairline bg-transparent px-3 py-1.5 text-sm">
            <option value="">Add a country…</option>
            {AFRICAN_COUNTRIES.filter(([k]) => !codes.includes(k)).map(([k, n]) => <option key={k} value={k}>{n}</option>)}
          </select>
        )}
      </div>
      {codes.length < 2 && <p className="mt-6 text-sm text-[color:var(--muted)]">Choose at least two countries.</p>}
      {error && <ErrorNote message={error} />}
      {loading && <Loading />}
      {rows && !loading && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b hairline">
                <th className="py-2 pr-3 font-normal text-[color:var(--muted)]" />
                {rows.map((r) => <th key={r.iso2} className="py-2 pr-3"><Link className="hover:underline" href={`/countries/${r.iso2}`}>{r.name}</Link></th>)}
              </tr>
            </thead>
            <tbody>
              {LINES.map(([label, fn]) => (
                <tr key={label} className="border-b hairline">
                  <td className="py-2 pr-3 text-[color:var(--muted)]">{label}</td>
                  {rows.map((r) => <td key={r.iso2} className="py-2 pr-3">{fn(r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[0.75rem] leading-relaxed text-[color:var(--dim)]">
            Deal figures cover the last 12 months of records found in published news and filings. Investor origin counts deals whose
            investors&apos; home countries are known. IMF figures for this year are projections.
          </p>
        </div>
      )}
    </Container>
  );
}
