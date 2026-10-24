"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ApiError } from "../../../../lib/api";
import { ErrorNote, PageHeader } from "../../../../components/app/ui";
import { get } from "../../../../lib/market";

type FinancialItem = { current: number; prior?: number };
type Financials = {
  source: string;
  source_url?: string;
  period: { end: string; months: number | null; label?: string } | null;
  currency?: string;
  unit?: string;
  items?: Record<string, FinancialItem>;
  checks?: { check: string; passed: boolean }[];
  verified: boolean;
};
type Profile = {
  name: string;
  ticker: string | null;
  country: string | null;
  country_name: string | null;
  exchange: string | null;
  sources?: string[];
  identity?: { sector?: string | null; industry?: string | null; business?: string } | null;
  market?: { price?: number | null; currency?: string | null; market_cap?: number | null; source?: string; as_at?: string | null } | null;
  multiples?: Record<string, number> | null;
  financials?: Financials | null;
  private_markets?: { deal_count: number; total_raised_usd: number | null; last_round: string | null } | null;
  valuation?: { latest_mark: { valuation_usd: number; basis: string; announced: string } | null } | null;
};
type Draft = { name: string; ticker: string; country: string };

const EMPTY_DRAFT: Draft = { name: "", ticker: "", country: "" };
const MAX_PROFILES = 4;

function compact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function money(value: number | null | undefined, currency: string | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  if (!currency) return `${value.toLocaleString("en", { maximumFractionDigits: 2 })} · currency not reported`;
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2, notation: Math.abs(value) >= 1e12 ? "compact" : "standard" }).format(value);
  } catch {
    return `${value.toLocaleString("en", { maximumFractionDigits: 2 })} ${currency}`;
  }
}

function multiple(value: number | null | undefined, key: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  if (key === "dividendYield") return `${(value * 100).toFixed(2)}%`;
  return value.toLocaleString("en", { maximumFractionDigits: 2 });
}

function statementValue(profile: Profile, key: string): string {
  const financials = profile.financials;
  const value = financials?.items?.[key]?.current;
  if (value == null || !Number.isFinite(value)) return "Not available";
  const amount = value.toLocaleString("en", { maximumFractionDigits: 2 });
  const currency = financials?.currency ? ` ${financials.currency}` : "";
  const unit = financials?.unit ? ` · ${financials.unit}` : "";
  return `${amount}${currency}${unit}`;
}

function dateAgeLabel(value: string | null | undefined, staleAfterDays: number): string {
  if (!value) return "Date not reported";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date not reported";
  const age = Math.floor((Date.now() - parsed.getTime()) / 86400000);
  if (age < 0) return "Date appears to be in the future";
  return age > staleAfterDays ? `${value.slice(0, 10)} · ${age} days old` : value.slice(0, 10);
}

function financialQuality(profile: Profile): string {
  const financials = profile.financials;
  if (!financials) return "No structured financial statements";
  if (financials.checks?.some((check) => !check.passed)) return "Accounting checks have exceptions";
  return financials.verified ? "Available accounting checks passed" : "Not fully verified";
}

const METRICS: { label: string; value: (profile: Profile) => string }[] = [
  { label: "Country / exchange", value: (p) => [p.country_name || p.country, p.exchange].filter(Boolean).join(" · ") || "Not available" },
  { label: "Sector / industry", value: (p) => [p.identity?.sector, p.identity?.industry].filter(Boolean).join(" · ") || "Not available" },
  { label: "Share price", value: (p) => money(p.market?.price, p.market?.currency ?? p.financials?.currency) },
  { label: "Market capitalisation", value: (p) => money(p.market?.market_cap, p.market?.currency) },
  { label: "Price quote date", value: (p) => dateAgeLabel(p.market?.as_at, 7) },
  { label: "Trailing P/E", value: (p) => multiple(p.multiples?.trailingPE, "trailingPE") },
  { label: "Forward P/E", value: (p) => multiple(p.multiples?.forwardPE, "forwardPE") },
  { label: "Price / book", value: (p) => multiple(p.multiples?.priceToBook, "priceToBook") },
  { label: "EV / revenue", value: (p) => multiple(p.multiples?.enterpriseToRevenue, "enterpriseToRevenue") },
  { label: "EV / EBITDA", value: (p) => multiple(p.multiples?.enterpriseToEbitda, "enterpriseToEbitda") },
  { label: "Dividend yield", value: (p) => multiple(p.multiples?.dividendYield, "dividendYield") },
  { label: "Beta", value: (p) => multiple(p.multiples?.beta, "beta") },
  { label: "Revenue (reported)", value: (p) => statementValue(p, "revenue") },
  { label: "Profit after tax (reported)", value: (p) => statementValue(p, "profit_after_tax") },
  { label: "Total assets (reported)", value: (p) => statementValue(p, "total_assets") },
  { label: "Total debt (reported)", value: (p) => statementValue(p, "total_debt") },
  { label: "Total equity (reported)", value: (p) => statementValue(p, "total_equity") },
  { label: "Free cash flow (reported)", value: (p) => statementValue(p, "free_cash_flow") },
  { label: "Financial statement period", value: (p) => p.financials?.period?.end || "Not available" },
  { label: "Statement freshness", value: (p) => dateAgeLabel(p.financials?.period?.end, 548) },
  { label: "Accounting checks", value: financialQuality },
  { label: "Financial statement source", value: (p) => p.financials?.source || "Not available" },
  { label: "Latest private-market valuation mark (USD)", value: (p) => {
      const mark = p.valuation?.latest_mark;
      return mark ? `${money(mark.valuation_usd, "USD")} · ${mark.basis} · ${mark.announced}` : "Not available";
    } },
  { label: "Disclosed private-market capital raised (USD)", value: (p) => money(p.private_markets?.total_raised_usd, "USD") },
  { label: "Private-market deal records", value: (p) => p.private_markets ? p.private_markets.deal_count.toLocaleString() : "Not available" },
];

function countercaseQuestion(profile: Profile): string {
  return `Independently challenge the investment case for ${profile.name}${profile.ticker ? ` (${profile.ticker})` : ""}. Use current primary sources to check financial statement quality and freshness, debt and dilution, valuation assumptions, dividend or cash-flow sustainability, and country, currency, sector and regulatory risks. Separate confirmed facts, inference and unknowns; identify the strongest counterarguments and what evidence would change the conclusion. Do not just confirm the current narrative.`.slice(0, 500);
}

export default function MarketsComparePage() {
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function addCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!draft.name.trim()) {
      setError("Enter a company or investment name.");
      return;
    }
    if (profiles.length >= MAX_PROFILES) {
      setError("Compare up to four companies at a time. Remove one before adding another.");
      return;
    }
    const key = draft.name.trim().toLowerCase();
    const ticker = draft.ticker.trim().toLowerCase();
    if (profiles.some((profile) => profile.name.trim().toLowerCase() === key || (ticker && profile.ticker?.trim().toLowerCase() === ticker))) {
      setError("That company or ticker is already in the comparison.");
      return;
    }
    setBusy(true);
    try {
      const profile = await get<Profile>("/api/companies/profile", {
        name: draft.name.trim(),
        ticker: draft.ticker.trim(),
        country: draft.country.trim(),
      });
      setProfiles((current) => [...current, profile].slice(0, MAX_PROFILES));
      setDraft(EMPTY_DRAFT);
      setMessage(`Added ${profile.name}. Missing fields remain unavailable rather than being estimated.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this company profile.");
    } finally {
      setBusy(false);
    }
  }

  function removeProfile(profile: Profile) {
    setProfiles((current) => current.filter((item) => !(item.name === profile.name && item.ticker === profile.ticker)));
    setMessage(`Removed ${profile.name} from the comparison.`);
  }

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Compare opportunities" title="Compare the evidence, not just the price.">
        Compare up to four African companies using the company profiles and financial data already available in Deal Intelligence. Missing figures stay missing, and each profile shows its own reporting currency, statement period, source and quote freshness. A lower multiple alone does not prove a company is cheaper or a better investment.
      </PageHeader>

      <div className="mb-6 flex flex-wrap gap-3">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">← Markets overview</Link>
        <Link href="/app/companies" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Explore company profiles →</Link>
      </div>

      <section className="panel p-5 sm:p-6" aria-labelledby="compare-add-title">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Build a comparison</p>
            <h2 id="compare-add-title" className="h3 mt-2 text-xl">Add an investment</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">Use the company name first. Ticker and country help resolve ambiguous names. You can compare listed and private-market profiles, but their valuation fields are not directly equivalent.</p>
          </div>
          <p className="text-xs text-[color:var(--dim)]">{profiles.length} / {MAX_PROFILES} profiles</p>
        </div>
        {error && <div className="mt-4"><ErrorNote message={error} /></div>}
        {message && <p className="mt-3 text-xs leading-relaxed text-[color:var(--muted)]" role="status">{message}</p>}
        <form onSubmit={addCompany} className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="compare-name">Company / investment name *</label>
            <input id="compare-name" className="field" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} required maxLength={120} placeholder="e.g. Safaricom" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="compare-ticker">Ticker (optional)</label>
            <input id="compare-ticker" className="field" value={draft.ticker} onChange={(event) => setDraft((current) => ({ ...current, ticker: event.target.value }))} maxLength={40} placeholder="e.g. SCOM" />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="compare-country">Country (optional)</label>
            <input id="compare-country" className="field" value={draft.country} onChange={(event) => setDraft((current) => ({ ...current, country: event.target.value }))} maxLength={80} placeholder="e.g. Kenya" />
          </div>
          <div className="flex items-end">
            <button className="btn btn-primary w-full" type="submit" disabled={busy || profiles.length >= MAX_PROFILES}>{busy ? "Loading profile…" : "Add to comparison"}</button>
          </div>
        </form>
      </section>

      {profiles.length === 0 ? (
        <section className="mt-6 rounded-xl border border-dashed hairline p-8 text-center">
          <h2 className="text-base font-medium">Your comparison starts here.</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-[color:var(--muted)]">Add at least two companies to compare what the available data supports. One company is enough to inspect source and freshness metadata.</p>
        </section>
      ) : (
        <>
          <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Companies in comparison">
            {profiles.map((profile) => (
              <article key={`${profile.name}|${profile.ticker ?? ""}`} className="panel min-w-0 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="break-words text-base font-semibold">{profile.name}</h2>
                    <p className="mt-1 text-xs text-[color:var(--muted)]">{[profile.ticker, profile.country_name || profile.country, profile.exchange].filter(Boolean).join(" · ") || "Market identity not fully reported"}</p>
                  </div>
                  <button type="button" className="shrink-0 text-xs text-[color:var(--muted)] underline-offset-4 hover:underline" onClick={() => removeProfile(profile)} aria-label={`Remove ${profile.name}`}>Remove</button>
                </div>
                <div className="mt-3 space-y-2 border-t hairline pt-3 text-xs">
                  <p><span className="text-[color:var(--dim)]">Quote:</span> {money(profile.market?.price, profile.market?.currency ?? profile.financials?.currency)}</p>
                  <p><span className="text-[color:var(--dim)]">Quote date:</span> {dateAgeLabel(profile.market?.as_at, 7)}</p>
                  <p><span className="text-[color:var(--dim)]">Financials:</span> {financialQuality(profile)}</p>
                  <p><span className="text-[color:var(--dim)]">Statement period:</span> {profile.financials?.period?.end || "Not available"}</p>
                </div>
                <div className="mt-4 flex flex-wrap gap-x-3 gap-y-2 text-xs">
                  <Link href={`/app/companies?name=${encodeURIComponent(profile.name)}${profile.ticker ? `&ticker=${encodeURIComponent(profile.ticker)}` : ""}`} className="underline-offset-4 hover:underline">Profile</Link>
                  <Link href={`/app/markets/valuation?company=${encodeURIComponent(profile.name)}${profile.ticker ? `&ticker=${encodeURIComponent(profile.ticker)}` : ""}`} className="underline-offset-4 hover:underline">Valuation</Link>
                  <Link href={`/app/research?question=${encodeURIComponent(countercaseQuestion(profile))}`} className="underline-offset-4 hover:underline">Research countercase</Link>
                  {profile.financials?.source_url && <a href={profile.financials.source_url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">Statement source ↗</a>}
                </div>
              </article>
            ))}
          </section>

          <section className="mt-8" aria-labelledby="comparison-matrix-title">
            <div className="mb-4">
              <p className="eyebrow">Comparison matrix</p>
              <h2 id="comparison-matrix-title" className="h3 mt-2 text-xl">What the available evidence says</h2>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">Raw financial amounts use each company&apos;s reported currency and units; they are not normalised across currencies, fiscal periods or accounting bases. Ratios may still be unsuitable for cross-sector comparisons. Not available means the source profile did not provide a usable value.</p>
            </div>
            <div className="overflow-x-auto rounded-xl border hairline">
              <table className="w-full min-w-[58rem] border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b hairline text-[color:var(--dim)]">
                    <th scope="col" className="sticky left-0 bg-[color:var(--panel)] px-3 py-3 font-normal">Metric</th>
                    {profiles.map((profile) => <th scope="col" key={`${profile.name}|${profile.ticker ?? ""}`} className="min-w-44 px-3 py-3 font-normal">{profile.name}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((metric) => (
                    <tr key={metric.label} className="border-b hairline last:border-0">
                      <th scope="row" className="sticky left-0 bg-[color:var(--panel)] px-3 py-3 font-normal text-[color:var(--muted)]">{metric.label}</th>
                      {profiles.map((profile) => <td key={`${profile.name}|${profile.ticker ?? ""}`} className="px-3 py-3 align-top">{metric.value(profile)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <div className="mt-8 rounded-xl border hairline p-4 text-xs leading-relaxed text-[color:var(--dim)]">
        This is a source-aware comparison aid, not a ranking engine or recommendation. Public-market prices, private-market transaction marks and disclosed capital raised represent different things. Do not compare raw amounts across currencies or units without normalising them first; missing, stale or inconsistent data should lower confidence rather than be silently filled in.
      </div>
    </Container>
  );
}
