"use client";

import Link from "next/link";
import { noteSeePlans } from "../../lib/plan";

/** "See plans" after a limit message; the click is noted for the owner's conversion figures. */
export function SeePlansLink({ source }: { source: string }) {
  return (
    <Link href="/account/billing" onClick={() => noteSeePlans(source)}
      className="font-medium text-verified underline-offset-4 hover:underline">See plans →</Link>
  );
}

/** A small "Pro" label beside a feature a free account cannot use yet; opens the plans. */
export function ProBadge({ source, label = "Pro" }: { source: string; label?: string }) {
  return (
    <Link href="/account/billing" onClick={() => noteSeePlans(source)} title="Included in Pro. See plans."
      className="ml-2 inline-flex items-center rounded-full border border-verified/40 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-verified hover:bg-verified/10">
      {label}
    </Link>
  );
}
