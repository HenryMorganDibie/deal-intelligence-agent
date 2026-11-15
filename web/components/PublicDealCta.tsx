"use client";

import Link from "next/link";

/** The public deal page CTA stays independent of auth state; the account page routes signed-in visitors onward. */
export function PublicDealCta({ id }: { id: string }) {
  const next = encodeURIComponent(`/deals/${id}`);
  return (
    <div className="mt-5 flex flex-wrap gap-3">
      <Link href={`/account?next=${next}`} className="btn btn-primary">Continue to deal</Link>
      <Link href={`/account?mode=sign-up&next=${next}`} className="btn btn-ghost">Create a free account</Link>
    </div>
  );
}
