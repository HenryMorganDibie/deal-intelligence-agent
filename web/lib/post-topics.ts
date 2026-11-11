import { usd } from "../components/app/ui";
import type { Deal } from "./market";
import { billYield, countryName, latestBills, pct, type Instruments, type Overview } from "./market-public";

/* What each post's page and preview card show. The same function feeds both, so the card always matches the page
 * and the post: the movers post previews the movers, the bill post the yields, the roundup the day's deals.
 * Figures come from the platform's snapshots; a one-day move beyond 30% is left out, as in the post drafts. */

export type TopicRow = { name: string; note?: string; value: string; tone?: "up" | "down" | "plain" };
export type Topic = { pill: string; title: string; intro: string; rows: TopicRow[]; more: { href: string; label: string } };

export const MARKET_TOPICS = ["movers", "currencies", "treasury-bills", "sectors"] as const;
export type MarketTopic = (typeof MARKET_TOPICS)[number];
const POSTABLE_MOVE = 0.3;

type Mover = { name: string; exchange: string; chg_1d: number | null };
type OverviewWithMovers = Overview & { gainers?: Mover[]; losers?: Mover[] };

export function marketTopic(topic: MarketTopic, overview: OverviewWithMovers | null, instruments: Instruments | null): Topic {
  const more = { href: "/markets", label: "All African markets today" };
  const where = new Map((overview?.exchanges ?? []).map((e) => [e.exchange, countryName(e.country) ?? e.name]));
  if (topic === "movers") {
    const ok = (r: Mover) => r.chg_1d != null && Math.abs(r.chg_1d) <= POSTABLE_MOVE;
    const up = (overview?.gainers ?? []).filter((r) => ok(r) && r.chg_1d! > 0).slice(0, 3);
    const down = (overview?.losers ?? []).filter((r) => ok(r) && r.chg_1d! < 0).slice(0, 3);
    return { pill: "Stock movers", title: "Biggest movers on African exchanges",
      intro: "The largest one-day rises and falls on the last trading day, across every exchange we track.",
      rows: [...up, ...down].map((r) => ({ name: r.name, note: where.get(r.exchange) ?? r.exchange.toUpperCase(),
        value: pct(r.chg_1d), tone: (r.chg_1d ?? 0) >= 0 ? "up" : "down" })), more };
  }
  if (topic === "currencies") {
    const rows = (overview?.currencies ?? []).filter((c) => c.ytd_vs_usd != null).sort((a, z) => z.ytd_vs_usd! - a.ytd_vs_usd!);
    const pick = [...rows.slice(0, 3), ...rows.slice(-3).reverse()];
    return { pill: "Currencies", title: "African currencies against the dollar this year",
      intro: "The strongest and weakest African currencies against the US dollar since 1 January.",
      rows: pick.map((c) => ({ name: c.currency, note: c.per_usd ? `${c.per_usd.toLocaleString("en-US", { maximumFractionDigits: 2 })} per US$` : undefined,
        value: pct(c.ytd_vs_usd), tone: (c.ytd_vs_usd ?? 0) >= 0 ? "up" : "down" })), more };
  }
  if (topic === "treasury-bills") {
    const bills = latestBills(instruments?.tbills).slice(0, 5);
    return { pill: "Treasury bills", title: "Latest Treasury bill auctions in Africa",
      intro: "The newest auction in each country, with the shortest tenor offered.",
      rows: bills.map((b) => ({ name: b.name, note: `${b.rows[0].tenor_label ?? `${b.rows[0].tenor_days} days`}, auction ${b.date}`,
        value: `${billYield(b.rows[0])!.toFixed(2)}%`, tone: "plain" })), more };
  }
  const sectors = (overview?.sectors ?? []).filter((s) => s.shares >= 10 && s.ytd_usd != null).sort((a, z) => z.ytd_usd! - a.ytd_usd!).slice(0, 5);
  return { pill: "Sectors", title: "African sectors this year, in US dollars",
    intro: "Sector returns across every African exchange since 1 January, in US dollars so currency moves count.",
    rows: sectors.map((s) => ({ name: s.sector, note: `${s.shares} shares${s.mcap_usd ? `, ${usd(s.mcap_usd)} market value` : ""}`,
      value: pct(s.ytd_usd), tone: (s.ytd_usd ?? 0) >= 0 ? "up" : "down" })), more };
}

// ── Deals ────────────────────────────────────────────────────────────────────

const TYPE: Record<string, string> = { equity_funding: "Funding", debt_financing: "Debt", acquisition: "Acquisition",
  fund_raise: "Fund close", exit: "Exit", ipo: "IPO", merger: "Merger", joint_venture: "Joint venture" };

export function shiftDay(day: string, days: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Largest disclosed first, one line per company. */
export function topDeals(deals: Deal[], n: number): Deal[] {
  const out: Deal[] = [];
  for (const d of [...deals].filter((x) => x.target).sort((a, z) => (z.amount_usd ?? 0) - (a.amount_usd ?? 0))) {
    const words = new Set(d.target!.toLowerCase().split(/\s+/));
    if (out.some((o) => { const w = new Set(o.target!.toLowerCase().split(/\s+/)); return [...words].every((x) => w.has(x)) || [...w].every((x) => words.has(x)); })) continue;
    out.push(d);
    if (out.length === n) break;
  }
  return out;
}

export const dealRow = (d: Deal): TopicRow => ({
  name: d.target!, note: [TYPE[d.deal_type] ?? "Deal", countryName(d.country)].filter(Boolean).join(" · "),
  value: d.amount_usd ? usd(d.amount_usd) : "undisclosed", tone: "plain",
});

export function roundupTopic(deals: Deal[], label: string): Topic {
  return { pill: "Deal roundup", title: `African deals, ${label}`, intro: "The largest deals tracked, one per company, each with its sources.",
    rows: topDeals(deals, 5).map(dealRow), more: { href: "/deals", label: "Latest African deals" } };
}

export function weekTopic(deals: Deal[], total: number, start: string, end: string): Topic & { stats: [string, string][] } {
  const disclosed = deals.reduce((s, d) => s + (d.amount_usd ?? 0), 0);
  const countries = new Map<string, number>();
  for (const d of deals) if (d.country) countries.set(d.country, (countries.get(d.country) ?? 0) + 1);
  const busiest = [...countries.entries()].sort((a, z) => z[1] - a[1])[0];
  const stats: [string, string][] = [[total.toLocaleString("en-US"), "deals tracked"]];
  if (disclosed) stats.push([usd(disclosed), "disclosed"]);
  if (busiest) stats.push([countryName(busiest[0]) ?? busiest[0], `busiest market (${busiest[1]})`]);
  return { pill: "Week in review", title: "The week in African deals", stats,
    intro: `Deals tracked from ${start} to ${end}, with the largest of the week.`,
    rows: topDeals(deals, 3).map(dealRow), more: { href: "/deals", label: "Latest African deals" } };
}
