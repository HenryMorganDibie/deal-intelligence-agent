import type { Overview } from "../lib/markets-data";
import { ArrowRight, Container } from "./primitives";

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "n/a";
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}
function tone(v: number | null | undefined): string {
  return v == null || v === 0 ? "text-[color:var(--muted)]" : v > 0 ? "text-verified" : "text-risk";
}
function usd(v: number | null | undefined): string {
  if (!v) return "n/a";
  return v >= 1e12 ? `$${(v / 1e12).toFixed(2)}tn` : v >= 1e9 ? `$${(v / 1e9).toFixed(v >= 1e10 ? 0 : 1)}bn` : `$${(v / 1e6).toFixed(0)}m`;
}

/** Every African exchange in one view: index moves, dollar returns and today's movers, from the daily snapshot. */
export function MarketsToday({ data }: { data: { overview: Overview; companies: { listed: number; private: number } | null } | null }) {
  if (!data || !data.overview.exchanges.length) return null;
  const { overview, companies } = data;
  const tiles = overview.exchanges.filter((t) => !t.stale).slice(0, 8);
  const cap = overview.exchanges.reduce((s, t) => s + (t.mcap_usd ?? 0), 0);
  const day = overview.captured_at ? new Date(overview.captured_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : null;
  const stats = [
    { value: (companies ? companies.listed + companies.private : overview.coverage.shares).toLocaleString(), label: companies ? `companies on record: ${companies.listed.toLocaleString()} listed, ${companies.private.toLocaleString()} private` : "listed shares tracked" },
    { value: String(overview.coverage.exchanges), label: "African exchanges, priced every trading day" },
    { value: usd(cap), label: "market capitalisation covered, in dollars" },
  ];
  return (
    <section id="markets" aria-labelledby="markets-title" className="border-t hairline py-14 sm:py-16">
      <Container>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <p className="eyebrow">Markets · Daily close{day ? ` · ${day}` : ""}</p>
            <h2 id="markets-title" className="h2 mt-3">Every African stock market, in one place.</h2>
            <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">
              Index moves, returns in local currency and in dollars, and the day&apos;s movers across the continent,
              beside the private companies and deals behind them. End-of-day prices from the exchanges&apos; own lists.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/app/markets" className="btn btn-primary">Open markets <ArrowRight /></a>
            <a href="/app/markets/screener" className="btn btn-ghost">Screen companies <ArrowRight /></a>
          </div>
        </div>
        <dl className="mt-7 grid grid-cols-1 gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] sm:grid-cols-3">
          {stats.map((s) => (
            <div key={s.label} className="bg-[color:var(--bg)] p-5">
              <dt className="sr-only">{s.label}</dt>
              <dd>
                <span className="block font-display text-2xl font-semibold tracking-tight">{s.value}</span>
                <span className="mt-1 block text-[0.8125rem] leading-snug text-[color:var(--muted)]">{s.label}</span>
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {tiles.map((t, i) => {
            const ytd = t.ytd_usd ?? t.ytd_median_usd;
            return (
              <a key={t.exchange} href={`/app/markets/screener?exchange=${t.exchange}`} className={`panel p-4 transition hover:bg-white/[0.03] ${i >= 4 ? "hidden sm:block" : ""}`}>
                <p className="truncate text-sm font-medium">{t.name}</p>
                <div className="mt-2 flex items-baseline justify-between gap-2">
                  <span className="text-xs text-[color:var(--dim)]">{t.index?.name ?? t.exchange.toUpperCase()}</span>
                  <span className={`kbd text-sm ${tone(t.index?.chg_1d)}`}>{pct(t.index?.chg_1d, 2)}</span>
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
                  <span className="text-[color:var(--dim)]">YTD in USD</span>
                  <span className={`kbd ${tone(ytd)}`}>{pct(ytd)}</span>
                </div>
              </a>
            );
          })}
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {([["Top gainers today", overview.gainers], ["Top losers today", overview.losers]] as const).map(([title, rows]) => (
            <div key={title} className="panel min-w-0 p-5">
              <h3 className="h3">{title}</h3>
              <ul className="mt-3 divide-y divide-[color:var(--line)]">
                {rows.slice(0, 4).map((r) => (
                  <li key={`${r.exchange}:${r.symbol}`} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <a className="block min-w-0 flex-1 truncate hover:underline" href={`/app/companies?${new URLSearchParams({ name: r.name, exchange: r.exchange, symbol: r.symbol })}`}>
                      {r.name} <span className="text-xs text-[color:var(--dim)]">{r.exchange.toUpperCase()}</span>
                    </a>
                    <span className={`kbd shrink-0 ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
          End-of-day closes, not live quotes, and not investment advice. Stale prices are excluded from returns and movers.
        </p>
      </Container>
    </section>
  );
}
