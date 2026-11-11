"use client";

import { useEffect, useState } from "react";

/** What the signed-in account's plan allows, read once per page load; null until known or when signed out. */
export type PlanLimits = { plan: string; ai_monthly: number; ai_used: number; alerts_max: number; alerts_used: number; exports: boolean };

let cached: Promise<PlanLimits | null> | null = null;

function load(): Promise<PlanLimits | null> {
  cached ??= fetch("/api/account/plan", { cache: "no-store" })
    .then((r) => (r.ok ? (r.json() as Promise<PlanLimits>) : null))
    .catch(() => null);
  return cached;
}

export function usePlan(): PlanLimits | null {
  const [plan, setPlan] = useState<PlanLimits | null>(null);
  useEffect(() => {
    let live = true;
    void load().then((p) => live && setPlan(p));
    return () => { live = false; };
  }, []);
  return plan;
}

/** Notes, for the owner's conversion figures, that the account opened the plans and from where. Never blocks. */
export function noteSeePlans(source: string): void {
  try {
    const body = JSON.stringify({ event: "see_plans", source: source.toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 40) });
    void fetch("/api/data/plan-event", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true })
      .catch(() => null);
  } catch {
    /* analytics never gets in the way */
  }
}
