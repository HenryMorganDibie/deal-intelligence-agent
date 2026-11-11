"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { PricingTable } from "../../../components/billing/PricingTable";
import { FALLBACK_CATALOG, naira, type CatalogPlan } from "../../../lib/pricing";

type Billing = {
  plan: string;
  source: string | null;
  email: string | null;
  subscription: { plan: string; interval: string | null; status: string; next_payment_at: string | null; manageable: boolean } | null;
  catalog: CatalogPlan[] | null;
};

const STATUS: Record<string, string> = {
  active: "Active",
  non_renewing: "Cancelled; access continues until the end of the paid period",
  attention: "Payment failed; Paystack will retry. Update your card to keep access.",
  cancelled: "Ended",
};

async function post(body: Record<string, unknown>) {
  const r = await fetch("/api/account/billing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = (await r.json().catch(() => ({}))) as { authorization_url?: string; link?: string; error?: string };
  return { ok: r.ok, data };
}

export default function BillingPage() {
  const router = useRouter();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [returning, setReturning] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch("/api/account/billing", { cache: "no-store" });
    if (r.status === 401) { router.replace(`/account?next=${encodeURIComponent("/account/billing")}`); return null; }
    if (!r.ok) { setError("Your plan could not be loaded. Try again shortly."); return null; }
    const data = (await r.json()) as Billing;
    setBilling(data);
    return data;
  }, [router]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const back = q.get("checkout") === "done";
    setReturning(back);
    load().then(async (first) => {
      // Paystack confirms a payment to the server a few seconds after the customer returns; check a few times.
      if (!back || !first || first.plan !== "free") { setReturning(false); return; }
      for (let i = 0; i < 6; i++) {
        await new Promise((ok) => setTimeout(ok, 2500));
        const b = await load();
        if (b && b.plan !== "free") break;
      }
      setReturning(false);
    });
  }, [load]);

  async function choose(plan: "pro" | "team", interval: "monthly" | "annually") {
    setError(""); setBusy(plan);
    const { ok, data } = await post({ action: "checkout", plan, interval });
    if (ok && data.authorization_url) { window.location.href = data.authorization_url; return; }
    setBusy(null);
    setError(data.error || "Payment could not be started. Try again shortly.");
  }

  async function manage() {
    setError(""); setBusy("manage");
    const { ok, data } = await post({ action: "manage" });
    if (ok && data.link) { window.location.href = data.link; return; }
    setBusy(null);
    setError(data.error || "Your subscription could not be opened. Try again shortly.");
  }

  const catalog = billing?.catalog?.length ? billing.catalog : FALLBACK_CATALOG;
  const current = catalog.find((p) => p.id === billing?.plan);
  const sub = billing?.subscription;
  const paying = sub && sub.status !== "cancelled";
  return (
    <Container className="max-w-6xl py-24 sm:py-28">
      <Link href="/app/deals" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">← Back to the app</Link>
      <h1 className="h2 mt-4">Plan and billing</h1>
      {billing && (
        <div className="panel mt-6 p-6">
          <p className="eyebrow">Current plan</p>
          <p className="mt-2 font-display text-2xl font-semibold">{current?.label ?? billing.plan}</p>
          {sub && (
            <p className="mt-2 text-sm text-[color:var(--muted)]">
              {STATUS[sub.status] ?? sub.status}
              {sub.interval ? ` · billed ${sub.interval === "annually" ? "yearly" : "monthly"}` : ""}
              {sub.next_payment_at && sub.status === "active" ? ` · renews ${new Date(sub.next_payment_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}` : ""}
              {current && sub.interval && current.price_month_ngn ? ` · ${naira((sub.interval === "annually" ? current.price_year_ngn : current.price_month_ngn) ?? 0)}` : ""}
            </p>
          )}
          {billing.source === "manual" && <p className="mt-2 text-sm text-[color:var(--muted)]">Set up for you by our team.</p>}
          {returning && <p className="mt-3 text-sm text-verified">Payment received. Activating your plan…</p>}
          {paying && sub?.manageable && (
            <button type="button" onClick={manage} disabled={!!busy} className="btn btn-ghost mt-4 disabled:opacity-60">
              {busy === "manage" ? "Opening Paystack…" : "Manage subscription (cancel or change card)"}
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-4 rounded-[10px] border border-risk/25 bg-risk/[0.05] p-3 text-sm text-risk">{error}</p>}
      {billing && !paying && billing.source !== "manual" && (
        <div className="mt-10">
          <PricingTable catalog={catalog} current={billing.plan} onChoose={choose} busy={busy} />
          <p className="mt-6 text-center text-xs text-[color:var(--dim)]">
            Paid securely through Paystack in naira. Subscribe now and keep this founding price while your subscription stays active.
          </p>
        </div>
      )}
      {!billing && !error && <p className="mt-6 text-sm text-[color:var(--muted)]">Loading your plan…</p>}
    </Container>
  );
}
