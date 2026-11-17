"use client";

import { useState, type FormEvent } from "react";

export type CompanySubmitted = {
  facts: { employees?: string; revenue_usd?: string; founded?: number; total_raised_usd?: number;
    latest_round?: string; headquarters?: string; description?: string };
  email_domain: string;
  updated_at: string;
};

const EMPLOYEES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"];
const REVENUE = ["under 1m", "1m-5m", "5m-20m", "20m-100m", "over 100m"];
const LABELS: Record<string, string> = {
  employees: "Employees", revenue_usd: "Revenue (US$)", founded: "Founded", total_raised_usd: "Total raised (US$)",
  latest_round: "Latest round", headquarters: "Headquarters",
};

function shown(key: string, v: string | number): string {
  if (key === "total_raised_usd" && typeof v === "number") {
    return v >= 1e9 ? `$${(v / 1e9).toFixed(1)}bn` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}m` : `$${Math.round(v).toLocaleString("en")}`;
  }
  return String(v);
}

/** What someone at the company has added, labelled as theirs and unverified, and the form to add or update it. */
export function CompanySubmittedSection({ company, claimKey, submitted }: {
  company: string; claimKey?: string; submitted?: CompanySubmitted | null;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [form, setForm] = useState({
    employees: submitted?.facts.employees ?? "", revenue_usd: submitted?.facts.revenue_usd ?? "",
    founded: submitted?.facts.founded ? String(submitted.facts.founded) : "",
    total_raised_usd: submitted?.facts.total_raised_usd ? String(submitted.facts.total_raised_usd) : "",
    latest_round: submitted?.facts.latest_round ?? "", headquarters: submitted?.facts.headquarters ?? "",
    description: submitted?.facts.description ?? "",
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claimKey) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await fetch("/api/company-claims", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name_key: claimKey, company, facts: form }),
      });
      const body = (await r.json()) as { status?: string; error?: string };
      if (!r.ok) throw new Error(body.error || "The details could not be saved.");
      setResult({ ok: true, text: body.status === "published"
        ? "Published. It shows on this page as submitted by the company within a few hours."
        : body.status === "removed" ? "Saved, but an earlier submission from this account was removed, so it will not show."
        : "Saved for review: we have no website on record to check your email against." });
      setOpen(false);
    } catch (err) {
      setResult({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const facts = submitted ? Object.entries(submitted.facts).filter(([k]) => k !== "description" && LABELS[k]) : [];
  return (
    <section>
      <h3 className="eyebrow">From the company</h3>
      {submitted ? (
        <div className="mt-3 rounded-xl border hairline p-4">
          <p className="text-xs text-[color:var(--dim)]">
            Submitted by someone with an @{submitted.email_domain} email on {submitted.updated_at.slice(0, 10)}. Not verified by us.
          </p>
          {submitted.facts.description && <p className="mt-2 max-w-3xl text-sm leading-relaxed">{submitted.facts.description}</p>}
          {facts.length > 0 && (
            <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              {facts.map(([k, v]) => (
                <div key={k}><dt className="text-xs text-[color:var(--dim)]">{LABELS[k]}</dt><dd>{shown(k, v as string | number)}</dd></div>
              ))}
            </dl>
          )}
        </div>
      ) : (
        <p className="mt-2 text-sm text-[color:var(--muted)]">Nothing submitted by the company yet.</p>
      )}
      {claimKey && (
        <button type="button" className="mt-3 text-sm underline-offset-4 hover:underline" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Close" : submitted ? "Work here? Update these details" : "Work here? Add details about this company"}
        </button>
      )}
      {result && <p className={`mt-2 text-sm ${result.ok ? "text-verified" : "text-risk"}`} role="status">{result.text}</p>}
      {open && (
        <form onSubmit={submit} className="mt-3 grid gap-3 rounded-xl border hairline p-4 sm:grid-cols-2">
          <p className="text-xs leading-relaxed text-[color:var(--muted)] sm:col-span-2">
            Signed in with an email at the company&apos;s own website domain, your details are published straight away, marked as
            the company&apos;s own and not verified. Personal email addresses (Gmail, Yahoo, Outlook) cannot submit.
          </p>
          <label className="text-xs text-[color:var(--muted)]">Employees
            <select className="field mt-1 w-full" value={form.employees} onChange={set("employees")}>
              <option value="">Not given</option>{EMPLOYEES.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label className="text-xs text-[color:var(--muted)]">Annual revenue (US$)
            <select className="field mt-1 w-full" value={form.revenue_usd} onChange={set("revenue_usd")}>
              <option value="">Not given</option>{REVENUE.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label className="text-xs text-[color:var(--muted)]">Founded (year)
            <input className="field mt-1 w-full" inputMode="numeric" maxLength={4} value={form.founded} onChange={set("founded")} placeholder="2016" />
          </label>
          <label className="text-xs text-[color:var(--muted)]">Total raised (US$)
            <input className="field mt-1 w-full" inputMode="numeric" maxLength={15} value={form.total_raised_usd} onChange={set("total_raised_usd")} placeholder="12000000" />
          </label>
          <label className="text-xs text-[color:var(--muted)]">Latest round
            <input className="field mt-1 w-full" maxLength={60} value={form.latest_round} onChange={set("latest_round")} placeholder="Series A, 2025" />
          </label>
          <label className="text-xs text-[color:var(--muted)]">Headquarters
            <input className="field mt-1 w-full" maxLength={80} value={form.headquarters} onChange={set("headquarters")} placeholder="Lagos" />
          </label>
          <label className="text-xs text-[color:var(--muted)] sm:col-span-2">What the company does
            <textarea className="field mt-1 min-h-[5rem] w-full" maxLength={600} value={form.description} onChange={set("description")} />
          </label>
          <div className="sm:col-span-2"><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Submit"}</button></div>
        </form>
      )}
    </section>
  );
}
