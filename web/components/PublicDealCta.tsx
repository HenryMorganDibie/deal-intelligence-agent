"use client";

import Link from "next/link";
import { usePlan } from "../lib/plan";

/** The public deal page's call to action: a signed-in visitor goes straight to the deal in the app; anyone else is
 * offered an account. (The page itself is cached for everyone, so this is decided in the browser.) */
export function PublicDealCta({ id }: { id: string }) {
  const plan = usePlan();
  const next = encodeURIComponent(`/app/deals/${id}`);
  if (plan) {
    return (
      <div className="mt-5 flex flex-wrap gap-3">
        <Link href={`/app/deals/${id}`} className="btn btn-primary">Open in the app</Link>
      </div>
    );
  }
  return (
    <div className="mt-5 flex flex-wrap gap-3">
      <Link href={`/account?mode=sign-up&next=${next}`} className="btn btn-primary">Create a free account</Link>
      <Link href={`/account?next=${next}`} className="btn btn-ghost">Sign in</Link>
    </div>
  );
}
