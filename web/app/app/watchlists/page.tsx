"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Field, PageHeader, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { SIGNAL_TYPES, post } from "../../../lib/market";

const KEY = "deal-intel:watchlists";
type Saved = { id: string; name: string; created_at: string };

function readSaved(): Saved[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function writeSaved(rows: Saved[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(rows));
  } catch {
    /* storage unavailable: the link still works */
  }
}

export default function WatchlistsPage() {
  const [saved, setSaved] = useState<Saved[]>([]);
  const [name, setName] = useState("");
  const [companies, setCompanies] = useState("");
  const [countries, setCountries] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [deals, setDeals] = useState(true);
  const [webhook, setWebhook] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prefillNotice, setPrefillNotice] = useState<string | null>(null);

  useEffect(() => {
    setSaved(readSaved());
    const params = new URLSearchParams(window.location.search);
    const follow = params.get("follow");
    if (follow) {
      // "Follow this investor" from a profile: a local draft, sent only if the form is submitted.
      setName(`Deals involving ${follow}`);
      setCompanies(follow);
      setPrefillNotice(`${follow} was added to this draft. Alerts cover every deal it takes part in, under any of its known names.`);
      return;
    }
    if (params.get("from") !== "portfolio") return;
    try {
      const raw = window.sessionStorage.getItem("deal-intelligence:portfolio-watchlist-prefill");
      if (!raw) return;
      const parsed = JSON.parse(raw) as { name?: unknown; companies?: unknown };
      if (typeof parsed.name === "string") setName(parsed.name);
      if (Array.isArray(parsed.companies)) {
        const names = parsed.companies.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
        setCompanies(names.join("\n"));
        if (names.length) setPrefillNotice("Portfolio holdings were copied into this draft locally. They are sent to the watchlist service only if you submit this form.");
      }
      window.sessionStorage.removeItem("deal-intelligence:portfolio-watchlist-prefill");
    } catch {
      setError("The portfolio watchlist draft could not be loaded. You can enter company names manually.");
    }
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const webhookValue = webhook.trim();
    if (webhookValue) {
      try {
        const parsedWebhook = new URL(webhookValue);
        if (parsedWebhook.protocol !== "https:" || !parsedWebhook.hostname) {
          setError("Webhook URL must use HTTPS.");
          return;
        }
      } catch {
        setError("Enter a valid HTTPS webhook URL.");
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      const split = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
      const r = await post<{ id: string }>("/api/watchlists", {
        name: name.trim() || "Watchlist",
        companies: split(companies),
        countries: split(countries).map((c) => c.toUpperCase()),
        signal_types: types,
        include_deals: deals,
        webhook_url: webhook.trim() || null,
        delivery_frequency: frequency,
      });
      const rows = [{ id: r.id, name: name.trim() || "Watchlist", created_at: new Date().toISOString() }, ...readSaved()];
      writeSaved(rows);
      window.location.href = `/app/watchlists/${r.id}`;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The watchlist could not be created.");
      setBusy(false);
    }
  }

  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <PageHeader eyebrow="Monitoring and alerts" title="Watch companies and countries.">
        A watchlist matches every corporate event (M&A, credit, distress, leadership, regulatory, earnings, restructuring,
        insider) and every deal in the daily feed. Follow it on its page, subscribe to its RSS feed in any reader, Slack or
        email-by-RSS service, or give a webhook that receives new matches daily or as a weekly Friday digest. No account: the
        watchlist&apos;s link is its key, so keep it private.
      </PageHeader>

      {prefillNotice && <p className="mb-4 rounded-lg border hairline p-3 text-sm leading-relaxed text-[color:var(--muted)]" role="status">{prefillNotice}</p>}
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Nigerian banks" className="field" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Companies (comma or line separated)">
            <textarea value={companies} onChange={(e) => setCompanies(e.target.value)} rows={3} placeholder="Access Holdings, Zenith Bank, Dangote" className="field" />
          </Field>
          <Field label="Countries (ISO codes)">
            <textarea value={countries} onChange={(e) => setCountries(e.target.value)} rows={3} placeholder="NG, GH" className="field kbd uppercase" />
          </Field>
        </div>
        <fieldset>
          <legend className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Event types (none selected = all)</legend>
          <div className="flex flex-wrap gap-2">
            {SIGNAL_TYPES.map((t) => (
              <label key={t} className="flex items-center gap-2 rounded-full border hairline px-3 py-1.5 text-[0.8125rem]">
                <input
                  type="checkbox"
                  checked={types.includes(t)}
                  onChange={(e) => setTypes(e.target.checked ? [...types, t] : types.filter((x) => x !== t))}
                  className="accent-[#6ee7c8]"
                />
                {words(t)}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-3 text-[0.875rem] text-[color:var(--muted)]">
          <input type="checkbox" checked={deals} onChange={(e) => setDeals(e.target.checked)} className="h-4 w-4 accent-[#6ee7c8]" />
          Include deals involving these companies or countries
        </label>
        <Field label="Webhook URL (optional, https)">
          <input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://hooks.slack.com/..." className="field kbd" />
        </Field>
        <Field label="Webhook delivery cadence">
          <select value={frequency} onChange={(e) => setFrequency(e.target.value as "daily" | "weekly")} className="field">
            <option value="daily">Daily, after ingestion</option>
            <option value="weekly">Weekly digest, Friday UTC</option>
          </select>
        </Field>
        <button type="submit" disabled={busy} className="btn btn-primary">
          {busy ? "Creating..." : "Create watchlist"}
        </button>
        {error && <ErrorNote message={error} />}
      </form>

      <h2 className="eyebrow mt-12">Your watchlists</h2>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">Kept in this browser. Bookmark a watchlist&apos;s page to open it elsewhere.</p>
      <ul className="mt-3 space-y-2">
        {saved.length === 0 && <li className="text-sm text-[color:var(--muted)]">None yet.</li>}
        {saved.map((w) => (
          <li key={w.id} className="flex items-center justify-between border-b hairline pb-2 text-[0.875rem]">
            <Link href={`/app/watchlists/${w.id}`} className="hover:underline">
              {w.name}
            </Link>
            <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{w.created_at.slice(0, 10)}</span>
          </li>
        ))}
      </ul>
    </Container>
  );
}
