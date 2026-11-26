import { test } from "node:test";
import * as assert from "node:assert/strict";
import { METRICS, caveats, decodeEntries, encodeEntries, leaders, toUsd, visibleMetrics, type Entry } from "../lib/compare";

const m = (key: string) => METRICS.find((x) => x.key === key)!;

const safaricom: Entry = {
  profile: {
    name: "Safaricom PLC", ticker: "SCOM", country: "KE", country_name: "Kenya", exchange: "NSE Kenya",
    market: { price: 35, currency: "KES", as_at: "2026-11-13" },
    financials: {
      source: "NSE Kenya filing", currency: "KES", verified: true, period: { end: "2026-03-31", months: 12 },
      items: { revenue: { current: 380e9, prior: 350e9 }, operating_profit: { current: 130e9 }, profit_after_tax: { current: 80e9 },
        total_assets: { current: 600e9 }, total_equity: { current: 200e9 }, total_debt: { current: 100e9 } },
    },
    fx: { per_usd: { KES: 129.2 } },
  },
  facts: { kind: "listed", exchange: "nse", symbol: "SCOM", mcap_usd: 10.9e9, ytd_usd: 0.31, chg_1d: 0 },
};

const dangote: Entry = {
  profile: {
    name: "Dangote Cement", ticker: "DANGCEM", country: "NG", country_name: "Nigeria", exchange: "NGX",
    financials: {
      source: "NGX filing", currency: "NGN", verified: true, period: { end: "2025-06-30", months: 12 },
      items: { revenue: { current: 3.5e12, prior: 2.2e12 }, profit_after_tax: { current: 0.5e12 }, total_equity: { current: 2e12 },
        total_debt: { current: 1.6e12 } },
    },
    fx: { per_usd: { NGN: 1352 } },
  },
  facts: { kind: "listed", exchange: "ngx", symbol: "DANGCEM", mcap_usd: 5.4e9, ytd_usd: 0.12 },
};

const privateCo: Entry = {
  profile: { name: "Moniepoint", ticker: null, country: "NG", country_name: "Nigeria", exchange: null,
    private_markets: { deal_count: 4, total_raised_usd: 290e6, last_round: "series_c" },
    valuation: { latest_mark: { valuation_usd: 1e9, basis: "reported post-money", announced: "2024-10-29" } } },
  facts: { kind: "private", deal_count: 4 },
};

test("amounts in different currencies are put in dollars at the snapshot rate", () => {
  assert.equal(Math.round(m("revenue").value(safaricom) as number / 1e6), 2941);      // KES 380bn at 129.2
  assert.equal(Math.round(m("revenue").value(dangote) as number / 1e6), 2589);        // NGN 3.5tn at 1,352
  assert.equal(toUsd({ ...safaricom.profile, fx: null }, 100), null);                  // no rate: not converted
});

test("listed-company comparisons show the local share price, daily move and dated 52-week range", () => {
  const quote: Entry = {
    ...safaricom,
    profile: { ...safaricom.profile, market: {
      price: 1656.8, currency: "NGN", as_at: "2026-11-26", change_pct: 1.25,
      high_52w: 1800, low_52w: 900, range_as_at: "2026-11-25", range_source: "NGX trading summary",
      source: "NGX daily price list", stale: true, age_days: 8, delayed: true,
    } },
    facts: null,
  };
  assert.match(String(m("price").value(quote)), /1,656\.80/);
  assert.equal(m("chg_1d").value(quote), 0.0125);
  assert.match(String(m("high_52w").value(quote)), /1,800/);
  assert.match(String(m("low_52w").value(quote)), /900/);
  assert.match(m("price").local!(quote)!, /NGX daily price list/);
  assert.match(m("price").local!(quote)!, /stale/);
  assert.match(m("high_52w").local!(quote)!, /NGX trading summary/);
});

test("ratios come from the company's own statements", () => {
  assert.equal(m("net_margin").value(safaricom), 80 / 380);
  assert.equal(m("roe").value(safaricom), 0.4);
  assert.equal(m("de").value(dangote), 0.8);
  assert.equal((m("growth").value(dangote) as number).toFixed(3), "0.591");
  // P/E from dollar market cap over dollar profit: 10.9bn / (80bn / 129.2)
  assert.equal((m("pe").value(safaricom) as number).toFixed(2), (10.9e9 / (80e9 / 129.2)).toFixed(2));
});

test("no P/E or return on equity from interim results, and none for a loss-maker", () => {
  const interim = { ...safaricom, profile: { ...safaricom.profile, financials: { ...safaricom.profile.financials!, period: { end: "2026-09-30", months: 6 } } } };
  assert.equal(m("pe").value(interim), null);
  assert.equal(m("roe").value(interim), null);
  const loss = { ...safaricom, profile: { ...safaricom.profile, financials: { ...safaricom.profile.financials!,
    items: { ...safaricom.profile.financials!.items!, profit_after_tax: { current: -5e9 } } } } };
  assert.equal(m("pe").value(loss), null);
});

test("the leader is marked only where a direction applies and values differ", () => {
  assert.deepEqual([...leaders(m("ytd"), [safaricom, dangote])], [0]);
  assert.deepEqual([...leaders(m("de"), [safaricom, dangote])], [0]);                  // lower debt / equity leads
  assert.equal(leaders(m("mcap"), [safaricom, dangote]).size, 0);                       // size is not "better"
  assert.equal(leaders(m("ytd"), [safaricom, privateCo]).size, 0);                      // one value: nothing to compare
});

test("rows nobody has are hidden; private-market rows appear for a private company", () => {
  const keys = visibleMetrics([safaricom, dangote]).map((x) => x.key);
  assert.ok(keys.includes("roe") && !keys.includes("valuation") && !keys.includes("dy"));
  const withPrivate = visibleMetrics([safaricom, privateCo]).map((x) => x.key);
  assert.ok(withPrivate.includes("valuation") && withPrivate.includes("last_round"));
});

test("caveats name what to read with care", () => {
  const notes = caveats([safaricom, dangote, privateCo]);
  assert.ok(notes.some((n) => n.includes("days apart")));
  assert.ok(notes.some((n) => n.includes("different bases")));
});

test("a comparison round-trips through its link, separators in names removed", () => {
  const link = encodeEntries([{ name: "Safaricom PLC", exchange: "nse", symbol: "SCOM" }, { name: "Acme, Ltd", country: "NG" }]);
  assert.equal(link, "nse:SCOM~Safaricom PLC,p:Acme Ltd|NG");
  assert.deepEqual(decodeEntries(link), [{ exchange: "nse", symbol: "SCOM", name: "Safaricom PLC" }, { name: "Acme Ltd", country: "NG" }]);
  assert.deepEqual(decodeEntries("javascript:alert(1)"), []);
});

test("development-finance investments and merger decisions are summarised", () => {
  const withRecords: Entry = { ...privateCo, profile: { ...privateCo.profile, official_records: [
    { kind: "dfi_investment", authority: "British International Investment", date: "2022-01-21", amount_usd: null },
    { kind: "dfi_investment", authority: "IFC", date: "2023-05-01", amount_usd: 50e6 },
    { kind: "merger_filing", authority: "COMESA Competition Commission", date: "2024-02-01" },
  ] } };
  assert.equal(m("dfi").value(withRecords), "2 from 2 institutions, $50m disclosed");
  assert.equal(m("mergers").value(withRecords), 1);
  assert.equal(m("dfi").value(safaricom), null);
});
