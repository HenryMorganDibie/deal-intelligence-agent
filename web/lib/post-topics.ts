import { usd } from "../components/app/ui";
import type { Deal } from "./market";
import { electionOn } from "./elections";
import { billYield, countryName, latestBills, pct, type Instruments, type Overview } from "./market-public";

/* What each post's page and preview card show. The same function feeds both, so the card always matches the page
 * and the post: the movers post previews the movers, the bill post the yields, the roundup the day's deals.
 * Figures come from the platform's snapshots; a one-day move beyond 30% is left out, as in the post drafts. */

export type TopicRow = { name: string; note?: string; value: string; tone?: "up" | "down" | "plain" };
/** kicker: a line above the figures that ties the day to an event, such as the countdown to an election. */
export type Topic = { pill: string; title: string; intro: string; rows: TopicRow[]; more: { href: string; label: string }; kicker?: string };

export const MARKET_TOPICS = ["movers", "currencies", "treasury-bills", "sectors", "election"] as const;
export type MarketTopic = (typeof MARKET_TOPICS)[number];
const POSTABLE_MOVE = 0.3;

type Mover = { name: string; exchange: string; chg_1d: number | null };
type OverviewWithMovers = Overview & { gainers?: Mover[]; losers?: Mover[] };

/** A currency's move in words, so a rise is never read as the dollar rising. */
const againstUsd = (v: number) => Math.abs(v) < 0.0005 ? "flat against the dollar" : `${v > 0 ? "up" : "down"} ${pct(v, false)} against the dollar`;
const tenor = (label: string | undefined, days: number | undefined) => {
  const l = label ?? `${days} days`;
  return l.endsWith(" days") ? `${l.slice(0, -5)}-day` : l;
};
const shortDay = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

/** `day` is the post's date (YYYY-MM-DD): it fixes the election countdown, so a dated link keeps its own card. */
export function marketTopic(topic: MarketTopic, overview: OverviewWithMovers | null, instruments: Instruments | null, day?: string): Topic {
  const t = topicFor(topic, overview, instruments, day);
  const el = electionOn(day);
  return el && topic !== "election" && topic !== "sectors" ? { ...t, kicker: `${el.hook} (${el.when})` } : t;
}

function topicFor(topic: MarketTopic, overview: OverviewWithMovers | null, instruments: Instruments | null, day?: string): Topic {
  const more = { href: "/markets", label: "All African markets today" };
  if (topic === "election") {
    const el = electionOn(day);
    const name = el?.name ?? "Nigeria";
    const rows: TopicRow[] = [];
    if (el) {
      const fx = overview?.currencies?.find((c) => c.currency === el.currency && c.per_usd);
      if (fx) rows.push({ name: el.currency === "NGN" ? "Naira" : el.currency,
        note: fx.ytd_vs_usd != null ? `${againstUsd(fx.ytd_vs_usd)} this year` : undefined,
        value: `${fx.per_usd!.toLocaleString("en-US", { maximumFractionDigits: 2 })} per US$`,
        tone: (fx.ytd_vs_usd ?? 0) >= 0 ? "up" : "down" });
      const ex = overview?.exchanges?.find((e) => e.exchange === el.exchange && !e.stale && e.ytd_local != null);
      if (ex) rows.push({ name: `${el.exchange.toUpperCase()} this year`, note: ex.ytd_usd != null ? `${pct(ex.ytd_usd)} in US dollars` : undefined,
        value: pct(ex.ytd_local), tone: (ex.ytd_local ?? 0) >= 0 ? "up" : "down" });
      const bill = latestBills(instruments?.tbills?.filter((b) => b.country === el.country || b.country_name === el.name))[0];
      if (bill) rows.push({ name: `${tenor(bill.rows[0].tenor_label, bill.rows[0].tenor_days)} Treasury bill`,
        note: `Auction ${shortDay(bill.date)}`, value: `${billYield(bill.rows[0])!.toFixed(2)}%`, tone: "plain" });
      const rate = instruments?.policy_rates?.find((r) => r.rate != null && (r.country === el.country || r.country_name === el.name));
      if (rate) rows.push({ name: "Policy rate", note: rate.date ? `As of ${shortDay(rate.date)}` : undefined, value: `${rate.rate}%`, tone: "plain" });
    }
    return { pill: "Election watch",
      title: el ? `${name} election watch: ${el.countdown}` : `${name} election watch`,
      intro: el ? `Polling day is ${el.when}. The currency, shares, Treasury bills and policy rate investors watch as ${name} votes, from the platform's daily figures.`
        : `The currency, shares, Treasury bills and policy rate investors watch around ${name}'s election.`,
      rows, more };
  }
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
  // Deals the checks hold back, or with no named company, are not shown on a post's card or page.
  const usable = deals.filter((x) => x.target && !x.target.toLowerCase().startsWith("undisclosed") && !(x.review_flags ?? []).length);
  for (const d of [...usable].sort((a, z) => (z.amount_usd ?? 0) - (a.amount_usd ?? 0))) {
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

export function weekTopic(all: Deal[], total: number, start: string, end: string): Topic & { stats: [string, string][] } {
  // Counted as the email counts them: deals the checks hold back are left out. A window larger than one page keeps
  // the API's total.
  const deals = all.filter((d) => !(d.review_flags ?? []).length);
  total = total > all.length ? total : deals.length;
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
