"use client";

import { useEffect, useState } from "react";
import type { NairaRate } from "../../lib/catalog";
import { PLAN_FEATURES, approxDollars, defaultCurrency, money, priceOf, type CatalogPlan, type Currency } from "../../lib/pricing";

type Props = {
  catalog: CatalogPlan[];
  /** The account's current plan, on the billing page. */
  current?: string | null;
  /** On the billing page: start checkout. On the public page: undefined, and buttons link to sign-up. */
  onChoose?: (plan: "pro" | "team", interval: "monthly" | "annually", currency: Currency) => void;
  busy?: string | null;
  /** Current naira rate, for the approximate dollar figure shown under naira prices. */
  rate?: NairaRate | null;
};

export function PricingTable({ catalog, current = null, onChoose, busy = null, rate = null }: Props) {
  const [yearly, setYearly] = useState(false);
  const offered: Currency[] = catalog[0]?.currencies?.length ? catalog[0].currencies : ["NGN"];
  const offeredKey = offered.join(",");
  const [currency, setCurrency] = useState<Currency>("NGN");
  useEffect(() => setCurrency(defaultCurrency(offeredKey.split(",") as Currency[])), [offeredKey]);
  const interval = yearly ? "annually" : "monthly";
  return (
    <div>
      <div className="mb-6 flex items-center justify-center gap-3 text-sm">
        <button type="button" onClick={() => setYearly(false)} className={`rounded-full px-3 py-1.5 ${!yearly ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>Monthly</button>
        <button type="button" onClick={() => setYearly(true)} className={`rounded-full px-3 py-1.5 ${yearly ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>
          Yearly <span className="text-verified">2 months free</span>
        </button>
        {offered.length > 1 && (
          <span className="ml-2 inline-flex rounded-full border hairline p-0.5" role="group" aria-label="Currency">
            {offered.map((c) => (
              <button key={c} type="button" onClick={() => setCurrency(c)} aria-pressed={currency === c}
                className={`rounded-full px-3 py-1 ${currency === c ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>
                {c === "NGN" ? "₦ Naira" : "$ Dollars"}
              </button>
            ))}
          </span>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {catalog.map((p) => {
          const price = priceOf(p, currency, yearly);
          const info = PLAN_FEATURES[p.id];
          const isCurrent = current === p.id;
          const highlight = p.id === "pro";
          return (
            <div key={p.id} className={`panel flex flex-col p-6 ${highlight ? "ring-1 ring-verified/40" : ""}`}>
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg font-semibold">{p.label}</h3>
                {highlight && <span className="tag text-verified">Most popular</span>}
              </div>
              <p className="mt-1 text-sm text-[color:var(--muted)]">{info?.blurb}</p>
              <p className="mt-5">
                {price === null ? (
                  <span className="font-display text-2xl font-semibold">Contact us</span>
                ) : price === 0 ? (
                  <span className="font-display text-3xl font-semibold">{money(0, currency)}</span>
                ) : (
                  <>
                    <span className="font-display text-3xl font-semibold">{money(price, currency)}</span>
                    <span className="text-sm text-[color:var(--muted)]"> / {yearly ? "year" : "month"}</span>
                  </>
                )}
              </p>
              {currency === "NGN" && price && rate ? (
                <p className="mt-1 text-xs text-[color:var(--muted)]">
                  {approxDollars(price, rate.perUsd)} {yearly ? "a year" : "a month"} at ₦{rate.perUsd.toLocaleString("en-US", { maximumFractionDigits: 2 })} per $1
                  {rate.asOf ? ` (${new Date(rate.asOf).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })})` : ""}.
                  {" "}Billed in naira; your bank converts it.
                </p>
              ) : null}
              {yearly && price ? (
                <p className="mt-1 text-xs text-[color:var(--dim)]">{money(Math.round((price / 12) * 100) / 100, currency)} a month, billed yearly</p>
              ) : null}
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {info?.features.map((f) => <li key={f} className="flex gap-2"><span aria-hidden className="text-verified">✓</span>{f}</li>)}
              </ul>
              <div className="mt-6">
                {isCurrent ? (
                  <span className="btn btn-ghost w-full cursor-default">Your plan</span>
                ) : p.self_serve && (p.id === "pro" || p.id === "team") ? (
                  onChoose ? (
                    <button type="button" disabled={!!busy} onClick={() => onChoose(p.id as "pro" | "team", interval, currency)}
                      className={`btn w-full ${highlight ? "btn-primary" : "btn-ghost"} disabled:opacity-60`}>
                      {busy === p.id ? "Opening Paystack…" : `Choose ${p.label}`}
                    </button>
                  ) : (
                    <a href={`/account?mode=sign-up&next=${encodeURIComponent(`/account/billing?plan=${p.id}&interval=${interval}&currency=${currency}`)}`}
                      className={`btn w-full ${highlight ? "btn-primary" : "btn-ghost"}`}>Get {p.label}</a>
                  )
                ) : p.id === "free" ? (
                  onChoose ? null : <a href="/account?mode=sign-up" className="btn btn-ghost w-full">Start free</a>
                ) : (
                  <a href="/contact?topic=institutional#form" className="btn btn-ghost w-full">Talk to us</a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
