"use client";

import { useState } from "react";
import { PLAN_FEATURES, naira, type CatalogPlan } from "../../lib/pricing";
import { CONTACT_EMAIL } from "../../lib/site";

type Props = {
  catalog: CatalogPlan[];
  /** The account's current plan, on the billing page. */
  current?: string | null;
  /** On the billing page: start checkout. On the public page: undefined, and buttons link to sign-up. */
  onChoose?: (plan: "pro" | "team", interval: "monthly" | "annually") => void;
  busy?: string | null;
};

export function PricingTable({ catalog, current = null, onChoose, busy = null }: Props) {
  const [yearly, setYearly] = useState(false);
  const interval = yearly ? "annually" : "monthly";
  return (
    <div>
      <div className="mb-6 flex items-center justify-center gap-3 text-sm">
        <button type="button" onClick={() => setYearly(false)} className={`rounded-full px-3 py-1.5 ${!yearly ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>Monthly</button>
        <button type="button" onClick={() => setYearly(true)} className={`rounded-full px-3 py-1.5 ${yearly ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>
          Yearly <span className="text-verified">2 months free</span>
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {catalog.map((p) => {
          const price = yearly ? p.price_year_ngn : p.price_month_ngn;
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
                  <span className="font-display text-3xl font-semibold">₦0</span>
                ) : (
                  <>
                    <span className="font-display text-3xl font-semibold">{naira(price)}</span>
                    <span className="text-sm text-[color:var(--muted)]"> / {yearly ? "year" : "month"}</span>
                  </>
                )}
              </p>
              {yearly && p.price_month_ngn ? (
                <p className="mt-1 text-xs text-[color:var(--dim)]">{naira(Math.round((p.price_year_ngn ?? 0) / 12))} a month, billed yearly</p>
              ) : null}
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {info?.features.map((f) => <li key={f} className="flex gap-2"><span aria-hidden className="text-verified">✓</span>{f}</li>)}
              </ul>
              <div className="mt-6">
                {isCurrent ? (
                  <span className="btn btn-ghost w-full cursor-default">Your plan</span>
                ) : p.self_serve && (p.id === "pro" || p.id === "team") ? (
                  onChoose ? (
                    <button type="button" disabled={!!busy} onClick={() => onChoose(p.id as "pro" | "team", interval)}
                      className={`btn w-full ${highlight ? "btn-primary" : "btn-ghost"} disabled:opacity-60`}>
                      {busy === p.id ? "Opening Paystack…" : `Choose ${p.label}`}
                    </button>
                  ) : (
                    <a href={`/account?mode=sign-up&next=${encodeURIComponent(`/account/billing?plan=${p.id}&interval=${interval}`)}`}
                      className={`btn w-full ${highlight ? "btn-primary" : "btn-ghost"}`}>Get {p.label}</a>
                  )
                ) : p.id === "free" ? (
                  onChoose ? null : <a href="/account?mode=sign-up" className="btn btn-ghost w-full">Start free</a>
                ) : (
                  <a href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Deal Intelligence Institutional plan")}`} className="btn btn-ghost w-full">Talk to us</a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
