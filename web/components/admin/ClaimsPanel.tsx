"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../../lib/api-base";

type Claim = {
  id: string; company: string; name_key: string; email: string; email_domain: string; site_domain: string | null;
  status: "published" | "pending" | "removed"; facts: Record<string, string | number>; updated_at: string;
};

const NEXT: Record<Claim["status"], Claim["status"][]> = {
  pending: ["published", "removed"], published: ["removed"], removed: ["published"],
};

/** Company-submitted facts: published ones (email at the company's website domain) can be removed, held ones (no
 * website known to check against) published or removed. */
export function ClaimsPanel({ adminKey }: { adminKey: string }) {
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch(apiUrl("/api/admin/claims"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: adminKey }) })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "Submissions unavailable");
        return (await r.json()) as Claim[];
      })
      .then((c) => { if (live) setClaims(c); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [adminKey]);

  async function setStatus(c: Claim, status: Claim["status"]) {
    setBusy(c.id);
    setError(null);
    try {
      const r = await fetch(apiUrl("/api/admin/claims/status"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: adminKey, id: c.id, status }),
      });
      if (!r.ok) throw new Error("The submission could not be updated");
      setClaims((cur) => (cur ?? []).map((x) => (x.id === c.id ? { ...x, status } : x)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const pending = (claims ?? []).filter((c) => c.status === "pending").length;
  return (
    <section className="mt-8">
      <h2 className="font-semibold">Company submissions{pending ? ` · ${pending} waiting for review` : ""}</h2>
      <p className="mt-1 text-sm text-[color:var(--muted)]">
        Published automatically when the submitter&apos;s email is at the company&apos;s website domain; held here when no website is known.
        Shown on profiles as submitted by the company, not verified.
      </p>
      {error && <p className="mt-2 text-sm text-risk" role="alert">{error}</p>}
      {claims === null ? (
        !error && <p className="mt-3 text-sm text-[color:var(--muted)]">Loading…</p>
      ) : claims.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">No submissions yet.</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-xl border hairline">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="text-xs text-[color:var(--dim)]">
              <tr><th className="px-3 py-2 font-normal">Company</th><th className="px-3 py-2 font-normal">Submitted by</th>
                <th className="px-3 py-2 font-normal">Details</th><th className="px-3 py-2 font-normal">Status</th><th className="px-3 py-2" /></tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.id} className="border-t hairline align-top">
                  <td className="px-3 py-2">{c.company}<span className="block text-xs text-[color:var(--dim)]">site: {c.site_domain ?? "none known"}</span></td>
                  <td className="px-3 py-2">{c.email}<span className="block text-xs text-[color:var(--dim)]">{c.updated_at.slice(0, 10)}</span></td>
                  <td className="px-3 py-2 text-xs text-[color:var(--muted)]">
                    {Object.entries(c.facts).map(([k, v]) => <span key={k} className="block">{k.replace(/_/g, " ")}: {String(v)}</span>)}
                  </td>
                  <td className="px-3 py-2">{c.status}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {NEXT[c.status].map((s) => (
                      <button key={s} type="button" disabled={busy === c.id} onClick={() => setStatus(c, s)}
                        className="mr-2 text-xs underline-offset-4 hover:underline">{s === "published" ? "Publish" : "Remove"}</button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
