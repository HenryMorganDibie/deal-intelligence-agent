// Company comparison: the figures that can be set side by side across countries. Amounts are converted to US dollars
// at the snapshot's official rate; ratios are computed from each company's own reported statements, so they need no
// conversion. Nothing is estimated: a figure the sources do not support stays null.

export type StatementItem = { current: number; prior?: number };
export type CompareProfile = {
  name: string;
  ticker: string | null;
  country: string | null;
  country_name: string | null;
  exchange: string | null;
  identity?: { sector?: string | null; industry?: string | null } | null;
  market?: { price?: number | null; currency?: string | null; market_cap?: number | null; as_at?: string | null; change_pct?: number | null; high_52w?: number | null; low_52w?: number | null; source?: string | null; stale?: boolean; age_days?: number; delayed?: boolean; quote_time?: string | null } | null;
  multiples?: Record<string, number> | null;
  financials?: {
    source: string; source_url?: string; currency?: string; unit?: string; verified: boolean;
    period: { end: string; months: number | null; label?: string } | null;
    items?: Record<string, StatementItem>; checks?: { check: string; passed: boolean }[];
  } | null;
  private_markets?: { deal_count: number; total_raised_usd: number | null; equity_raised_usd?: number | null;
    debt_raised_usd?: number | null; last_round: string | null } | null;
  valuation?: { latest_mark: { valuation_usd: number; basis: string; announced: string } | null } | null;
  fx?: { per_usd: Record<string, number>; as_of?: string | null } | null;
  official_records?: { kind: string; authority: string; date: string | null; amount_usd?: number | null; title?: string }[];
  financials_note?: string | null;
};

/** What the directory knows about the company picked from search: dollar market cap and returns for a listing,
 * rounds and valuation for a private company. */
export type DirectoryFacts = {
  kind: "listed" | "private";
  exchange?: string; exchange_name?: string; symbol?: string; sector?: string | null;
  chg_1d?: number | null; ytd_usd?: number | null; mcap_usd?: number | null; pe?: number | null;
  deal_count?: number; equity_raised_usd?: number | null; debt_raised_usd?: number | null;
  last_round?: string | null; last_deal_date?: string | null; valuation_usd?: number | null; valuation_date?: string | null;
};

export type Entry = { profile: CompareProfile; facts: DirectoryFacts | null };

const item = (p: CompareProfile, key: string) => p.financials?.items?.[key];
const cur = (p: CompareProfile, key: string) => {
  const v = item(p, key)?.current;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
};

/** A statement amount in US dollars at the snapshot's rate, or null when the currency or its rate is unknown. */
export function toUsd(p: CompareProfile, amount: number | null, currency?: string | null): number | null {
  if (amount == null) return null;
  const ccy = (currency ?? p.financials?.currency ?? "").toUpperCase();
  const rate = ccy ? p.fx?.per_usd?.[ccy] : undefined;
  return rate && rate > 0 ? amount / rate : null;
}

function usdShort(v: number): string {
  return v >= 1e9 ? `$${(v / 1e9).toFixed(1)}bn` : v >= 1e6 ? `$${Math.round(v / 1e6)}m` : `$${Math.round(v / 1e3)}k`;
}

const ratio = (a: number | null, b: number | null) => (a != null && b != null && b !== 0 ? a / b : null);

/** Format a traded share price in the currency supplied by its exchange. */
function quotePrice(e: Entry, field: "price" | "high_52w" | "low_52w"): string | null {
  const market = e.profile.market;
  const value = market?.[field];
  const currency = market?.currency;
  if (typeof value !== "number" || !Number.isFinite(value) || !currency) return null;
  try {
    return new Intl.NumberFormat("en-NG", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString("en-NG", { maximumFractionDigits: 2 })}`;
  }
}

/** The quote's provenance and freshness, kept separate from financial-statement dates. */
function quoteNote(e: Entry): string | null {
  const market = e.profile.market;
  if (!market) return null;
  const parts = [market.source || "Exchange market data", market.as_at ? `as of ${String(market.as_at).slice(0, 10)}` : null];
  if (market.delayed) parts.push("delayed");
  if (market.stale) parts.push(`stale${typeof market.age_days === "number" ? ` (${market.age_days} days old)` : ""}`);
  return parts.filter(Boolean).join(" · ");
}

/** True when the statements cover a full year, so profit can be set against a market value. */
export function fullYear(p: CompareProfile): boolean {
  const months = p.financials?.period?.months;
  return months == null || months === 12;
}

export function marketCapUsd(e: Entry): number | null {
  if (e.facts?.mcap_usd) return e.facts.mcap_usd;
  return toUsd(e.profile, e.profile.market?.market_cap ?? null, e.profile.market?.currency);
}

export type Direction = "higher" | "lower" | null;
export type Metric = {
  key: string;
  label: string;
  group: string;
  kind: "usd" | "pct" | "x" | "text" | "count";
  better: Direction;                       // which way leads; null where neither is better
  value: (e: Entry) => number | string | null;
  local?: (e: Entry) => string | null;     // the amount as reported, shown under its dollar value
  note?: string;
};

const reported = (key: string) => (e: Entry) => {
  const v = cur(e.profile, key);
  const ccy = e.profile.financials?.currency;
  return v == null ? null : `${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(v)} ${ccy ?? ""}`.trim();
};

export const METRICS: Metric[] = [
  { key: "where", label: "Country · exchange", group: "Company", kind: "text", better: null,
    value: (e) => {
      const country = e.profile.country_name || e.profile.country;
      const exchange = e.facts?.exchange_name || e.profile.exchange;
      // An exchange labelled by its country ("Nigeria") is not repeated after it.
      return [country, exchange && exchange !== country ? exchange : null].filter(Boolean).join(" · ") || null;
    } },
  { key: "sector", label: "Sector", group: "Company", kind: "text", better: null,
    value: (e) => e.profile.identity?.sector || e.facts?.sector || null },

  { key: "licence", label: "Licensed by", group: "Company", kind: "text", better: null,
    value: (e) => {
      const l = (e.profile.official_records ?? []).find((r) => r.kind === "licence");
      return l ? `${l.authority}${l.title ? ` (${l.title.replace(/^Licensed: /, "")})` : ""}` : null;
    } },

  { key: "price", label: "Last traded price", group: "Market", kind: "price", better: null,
    value: (e) => quotePrice(e, "price"), local: quoteNote },
  { key: "chg_1d", label: "Daily change", group: "Market", kind: "pct", better: "higher",
    value: (e) => e.facts?.chg_1d ?? (typeof e.profile.market?.change_pct === "number" ? e.profile.market.change_pct / 100 : null),
    local: quoteNote },
  { key: "high_52w", label: "52-week high", group: "Market", kind: "price", better: null,
    value: (e) => quotePrice(e, "high_52w"), local: quoteNote },
  { key: "low_52w", label: "52-week low", group: "Market", kind: "price", better: null,
    value: (e) => quotePrice(e, "low_52w"), local: quoteNote },
  { key: "mcap", label: "Market capitalisation", group: "Market", kind: "usd", better: null, value: marketCapUsd },
  { key: "chg_1d", label: "Today", group: "Market", kind: "pct", better: "higher", value: (e) => e.facts?.chg_1d ?? null },
  { key: "ytd", label: "Year to date, in US dollars", group: "Market", kind: "pct", better: "higher", value: (e) => e.facts?.ytd_usd ?? null },
  { key: "pe", label: "Price / earnings", group: "Market", kind: "x", better: "lower",
    note: "Market cap over the latest full-year profit after tax, both in US dollars; loss-makers are left out.",
    value: (e) => {
      const yahoo = e.profile.multiples?.trailingPE;
      if (yahoo && yahoo > 0) return yahoo;
      const profit = fullYear(e.profile) ? toUsd(e.profile, cur(e.profile, "profit_after_tax")) : null;
      const pe = profit && profit > 0 ? ratio(marketCapUsd(e), profit) : null;
      return pe ?? (e.facts?.pe && e.facts.pe > 0 ? e.facts.pe : null);
    } },
  { key: "pb", label: "Price / book", group: "Market", kind: "x", better: "lower",
    value: (e) => {
      const yahoo = e.profile.multiples?.priceToBook;
      if (yahoo && yahoo > 0) return yahoo;
      const equity = toUsd(e.profile, cur(e.profile, "total_equity"));
      return equity && equity > 0 ? ratio(marketCapUsd(e), equity) : null;
    } },
  { key: "dy", label: "Dividend yield", group: "Market", kind: "pct", better: "higher", value: (e) => e.profile.multiples?.dividendYield ?? null },

  { key: "revenue", label: "Revenue", group: "Results", kind: "usd", better: "higher",
    value: (e) => toUsd(e.profile, cur(e.profile, "revenue")), local: reported("revenue") },
  { key: "growth", label: "Revenue growth", group: "Results", kind: "pct", better: "higher",
    value: (e) => {
      const r = item(e.profile, "revenue");
      return r && r.prior && r.prior > 0 ? r.current / r.prior - 1 : null;
    } },
  { key: "pat", label: "Profit after tax", group: "Results", kind: "usd", better: "higher",
    value: (e) => toUsd(e.profile, cur(e.profile, "profit_after_tax")), local: reported("profit_after_tax") },
  { key: "op_margin", label: "Operating margin", group: "Results", kind: "pct", better: "higher",
    value: (e) => ratio(cur(e.profile, "operating_profit"), cur(e.profile, "revenue")) },
  { key: "net_margin", label: "Net margin", group: "Results", kind: "pct", better: "higher",
    value: (e) => ratio(cur(e.profile, "profit_after_tax"), cur(e.profile, "revenue")) },
  { key: "roe", label: "Return on equity", group: "Results", kind: "pct", better: "higher",
    note: "Profit after tax over closing equity, for a full year.",
    value: (e) => {
      const equity = cur(e.profile, "total_equity");
      return fullYear(e.profile) && equity && equity > 0 ? ratio(cur(e.profile, "profit_after_tax"), equity) : null;
    } },
  { key: "roa", label: "Return on assets", group: "Results", kind: "pct", better: "higher",
    value: (e) => (fullYear(e.profile) ? ratio(cur(e.profile, "profit_after_tax"), cur(e.profile, "total_assets")) : null) },

  { key: "assets", label: "Total assets", group: "Balance sheet", kind: "usd", better: null,
    value: (e) => toUsd(e.profile, cur(e.profile, "total_assets")), local: reported("total_assets") },
  { key: "equity", label: "Total equity", group: "Balance sheet", kind: "usd", better: null,
    value: (e) => toUsd(e.profile, cur(e.profile, "total_equity")), local: reported("total_equity") },
  { key: "de", label: "Debt / equity", group: "Balance sheet", kind: "x", better: "lower",
    value: (e) => {
      const equity = cur(e.profile, "total_equity");
      return equity && equity > 0 ? ratio(cur(e.profile, "total_debt"), equity) : null;
    } },
  { key: "ocf", label: "Operating cash flow", group: "Balance sheet", kind: "usd", better: "higher",
    value: (e) => toUsd(e.profile, cur(e.profile, "operating_cash_flow")), local: reported("operating_cash_flow") },

  { key: "valuation", label: "Latest valuation", group: "Private markets", kind: "usd", better: null,
    value: (e) => e.profile.valuation?.latest_mark?.valuation_usd ?? e.facts?.valuation_usd ?? null,
    local: (e) => {
      const m = e.profile.valuation?.latest_mark;
      return m ? `${m.basis}, ${m.announced}` : e.facts?.valuation_date ?? null;
    } },
  { key: "raised", label: "Capital raised (disclosed)", group: "Private markets", kind: "usd", better: null,
    value: (e) => e.profile.private_markets?.total_raised_usd
      ?? (((e.facts?.equity_raised_usd ?? 0) + (e.facts?.debt_raised_usd ?? 0)) || null) },
  { key: "last_round", label: "Latest round", group: "Private markets", kind: "text", better: null,
    value: (e) => {
      const round = e.profile.private_markets?.last_round ?? e.facts?.last_round;
      return round ? `${round.replace(/_/g, " ")}${e.facts?.last_deal_date ? `, ${e.facts.last_deal_date.slice(0, 10)}` : ""}` : null;
    } },
  { key: "dfi", label: "Development-finance investments", group: "Private markets", kind: "text", better: null,
    note: "Investments disclosed by IFC, British International Investment, FMO, the EIB, the African Development Bank and the US DFC.",
    value: (e) => {
      const recs = (e.profile.official_records ?? []).filter((r) => r.kind === "dfi_investment");
      if (!recs.length) return null;
      const total = recs.reduce((a, r) => a + (r.amount_usd ?? 0), 0);
      const backers = [...new Set(recs.map((r) => r.authority))];
      return `${recs.length} from ${backers.length === 1 ? backers[0] : `${backers.length} institutions`}${total ? `, ${usdShort(total)} disclosed` : ""}`;
    } },
  { key: "debt", label: "Debt raised on FMDQ", group: "Private markets", kind: "text", better: null,
    note: "Commercial paper and bonds announced by FMDQ Exchange, Nigeria's debt market.",
    value: (e) => {
      const recs = (e.profile.official_records ?? []).filter((r) => r.kind === "debt_issue");
      if (!recs.length) return null;
      const latest = recs.map((r) => r.date).filter(Boolean).sort().pop();
      return `${recs.length} issue${recs.length === 1 ? "" : "s"}${latest ? `, latest ${latest}` : ""}`;
    } },
  { key: "backers", label: "In investors' portfolios", group: "Private markets", kind: "text", better: null,
    note: "Firms that list the company on their own portfolio page.",
    value: (e) => {
      const firms = (e.profile.official_records ?? []).filter((r) => r.kind === "portfolio").map((r) => r.authority);
      return firms.length ? firms.join(", ") : null;
    } },
  { key: "mergers", label: "Merger decisions", group: "Private markets", kind: "count", better: null,
    value: (e) => (e.profile.official_records ?? []).filter((r) => r.kind === "merger_filing").length || null },
  { key: "deals", label: "Deals on record", group: "Private markets", kind: "count", better: null,
    value: (e) => (e.profile.private_markets?.deal_count || e.facts?.deal_count || null) },

  { key: "period", label: "Statements for", group: "Sources", kind: "text", better: null,
    value: (e) => {
      const f = e.profile.financials;
      if (!f?.period?.end) return null;
      return `${f.period.months ? `${f.period.months} months to ` : ""}${f.period.end}`;
    } },
  { key: "checks", label: "Accounting checks", group: "Sources", kind: "text", better: null,
    value: (e) => {
      const f = e.profile.financials;
      if (!f) return null;
      if (f.checks?.some((c) => !c.passed)) return "Exceptions found";
      return f.verified ? "Passed" : "Not fully verified";
    } },
  { key: "source", label: "Statement source", group: "Sources", kind: "text", better: null, value: (e) => e.profile.financials?.source ?? null },
];

export const GROUPS = ["Company", "Market", "Results", "Balance sheet", "Private markets", "Sources"];

/** The entries that lead a metric (highest or lowest as it reads), only when at least two have a value. */
export function leaders(metric: Metric, entries: Entry[]): Set<number> {
  if (!metric.better) return new Set();
  const values = entries.map((e) => metric.value(e)).map((v) => (typeof v === "number" && Number.isFinite(v) ? v : null));
  const known = values.filter((v): v is number => v != null);
  if (known.length < 2) return new Set();
  const best = metric.better === "higher" ? Math.max(...known) : Math.min(...known);
  if (known.every((v) => v === best)) return new Set();
  return new Set(values.flatMap((v, i) => (v === best ? [i] : [])));
}

/** Rows worth showing: at least one entry has a value. */
export function visibleMetrics(entries: Entry[]): Metric[] {
  return METRICS.filter((m) => entries.some((e) => {
    const v = m.value(e);
    return v != null && v !== "";
  }));
}

/** Where the comparison should be read with care. */
export function caveats(entries: Entry[]): string[] {
  const out: string[] = [];
  const unconverted = entries.filter((e) => e.profile.financials?.items && e.profile.financials.currency
    && !e.profile.fx?.per_usd?.[e.profile.financials.currency.toUpperCase()]);
  if (unconverted.length) out.push(`No dollar rate for ${unconverted.map((e) => e.profile.name).join(", ")}: its amounts are not converted.`);
  const ends = entries.map((e) => Date.parse(e.profile.financials?.period?.end ?? "")).filter(Number.isFinite);
  if (ends.length > 1) {
    const spread = Math.round((Math.max(...ends) - Math.min(...ends)) / 86400000);
    if (spread > 180) out.push(`Statement periods are ${spread} days apart, so results cover different years.`);
  }
  const partial = entries.filter((e) => e.profile.financials?.period?.months && e.profile.financials.period.months !== 12);
  if (partial.length) out.push(`${partial.map((e) => e.profile.name).join(", ")}: interim statements, so returns and P/E are not shown.`);
  const listed = entries.some((e) => e.facts?.kind === "listed" || e.profile.market?.price != null);
  const priv = entries.some((e) => e.facts?.kind === "private" || (e.profile.private_markets?.deal_count ?? 0) > 0);
  if (listed && priv) out.push("Listed market caps and private valuations are set on different bases (a traded price against a round's terms).");
  return out;
}

/** The comparison as a shareable query value: a listing as exchange:symbol~name, a private company as
 * p:name|country, comma-separated. */
export type EntryRef = { name: string; country?: string | null; exchange?: string; symbol?: string };

export function encodeEntries(entries: EntryRef[]): string {
  const clean = (v: string) => v.replace(/[,|~]/g, " ").replace(/\s+/g, " ").trim();
  return entries.map((e) => (e.exchange && e.symbol
    ? `${e.exchange}:${e.symbol}~${clean(e.name)}`
    : `p:${clean(e.name)}${e.country ? `|${clean(e.country)}` : ""}`)).join(",");
}

export function decodeEntries(value: string | null): EntryRef[] {
  if (!value) return [];
  return value.split(",").slice(0, 4).flatMap((part): EntryRef[] => {
    const t = part.trim();
    if (t.startsWith("p:")) {
      const [name, country] = t.slice(2).split("|");
      return name?.trim() ? [{ name: name.trim().slice(0, 120), country: country?.trim() || null }] : [];
    }
    const m = /^([a-z]{2,6}):([A-Za-z0-9.&\- ]{1,20})~(.{1,120})$/.exec(t);
    return m ? [{ exchange: m[1], symbol: m[2], name: m[3].trim() }] : [];
  });
}
