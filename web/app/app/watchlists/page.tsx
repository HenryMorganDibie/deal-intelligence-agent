"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ProBadge } from "../../../components/app/PlanLinks";
import { ElectionAlerts } from "../../../components/app/ElectionAlerts";
import { usePlan } from "../../../lib/plan";
import { CONTACT_EMAIL } from "../../../lib/site";
import { Container } from "../../../components/primitives";
import { ErrorNote, Field, PageHeader, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { SIGNAL_TYPES, post } from "../../../lib/market";
import { DESTINATION_LABEL, webhookDestination } from "../../../lib/webhooks";

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

// How many election alerts each plan can have running at once (messages are not capped). Mirrors ALLOWANCE in
// src/election_alerts.py.
const ELECTION_ALERT_PLANS: [string, string, number, string][] = [
  ["free", "Free", 0, "See the feature; alerts start with Pro"],
  ["pro", "Pro", 2, "Incident alerts, hourly, filtered by place, severity and type"],
  ["team", "Team", 5, "Pro, plus alerts on all election coverage and a start with the last 7 days"],
  ["institutional", "Institutional", 25, "Team, plus results and accreditation"],
];

export default function WatchlistsPage() {
  const plan = usePlan();
  // Free accounts keep a few alerts; the label appears once they are all in use.
  const alertsLocked = plan !== null && plan.alerts_used >= plan.alerts_max;
  const [saved, setSaved] = useState<Saved[]>([]);
  const [name, setName] = useState("");
  const [companies, setCompanies] = useState("");
  const [countries, setCountries] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [deals, setDeals] = useState(true);
  const [webhook, setWebhook] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  const [testing, setTesting] = useState(false);
  const [testNote, setTestNote] = useState<{ ok: boolean; text: string } | null>(null);
  const destination = webhookDestination(webhook);

  async function sendTest() {
    setTesting(true);
    setTestNote(null);
    try {
      const r = await post<{ delivered: boolean; label: string; status_code: number | null; error: string | null }>(
        "/api/webhooks/test", { url: webhook.trim(), name: name.trim() || "Your watchlist" });
      setTestNote(r.delivered
        ? { ok: true, text: `Test message sent to ${r.label}. Check the channel.` }
        : { ok: false, text: `${r.label} did not accept the message${r.status_code ? ` (HTTP ${r.status_code})` : ""}. Check the URL and that the webhook is still active.` });
    } catch (err) {
      setTestNote({ ok: false, text: err instanceof ApiError ? err.message : "The test message could not be sent." });
    } finally {
      setTesting(false);
    }
  }
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
        email-by-RSS service, or send new matches straight to a Slack, Teams, Discord or Google Chat channel, daily or as a weekly Friday digest. The
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
                  className="accent-verified"
                />
                {words(t)}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-3 text-[0.875rem] text-[color:var(--muted)]">
          <input type="checkbox" checked={deals} onChange={(e) => setDeals(e.target.checked)} className="h-4 w-4 accent-verified" />
          Include deals involving these companies or countries
        </label>
        <Field label="Send alerts to Slack, Teams, Discord, Google Chat or any webhook (optional)">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={webhook}
              onChange={(e) => { setWebhook(e.target.value); setTestNote(null); }}
              placeholder="Paste the channel's webhook URL"
              className="field kbd"
              aria-describedby="webhook-help"
            />
            <button type="button" onClick={sendTest} disabled={!destination || testing} className="btn btn-ghost shrink-0">
              {testing ? "Sending..." : "Send test message"}
            </button>
          </div>
          <p id="webhook-help" className="mt-2 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
            {destination
              ? <>Alerts will arrive formatted for <span className="text-[color:var(--text)]">{DESTINATION_LABEL[destination]}</span>.</>
              : <>Alerts are formatted for the tool automatically. <Link href="/developers#chat" className="underline">How to get a webhook URL</Link>.</>}
          </p>
          {testNote && <p role="status" className={`mt-1 text-[0.8125rem] ${testNote.ok ? "text-verified" : "text-risk"}`}>{testNote.text}</p>}
        </Field>
        <Field label="Webhook delivery cadence">
          <select value={frequency} onChange={(e) => setFrequency(e.target.value as "daily" | "weekly")} className="field">
            <option value="daily">Daily, after ingestion</option>
            <option value="weekly">Weekly digest, Friday UTC</option>
          </select>
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {busy ? "Creating..." : "Create watchlist"}
          </button>
          {alertsLocked && (
            <span className="inline-flex items-center text-sm text-[color:var(--muted)]">
              {plan?.alerts_max
                ? `All ${plan.alerts_max} alerts on your plan are in use. Pro has 100`
                : "Watchlist alerts are part of Pro"}<ProBadge source="watchlist_create" />
            </span>
          )}
        </div>
        {error && <ErrorNote message={error} />}
      </form>

      <section className="panel mt-12 p-5 sm:p-6" aria-labelledby="election-alerts-title">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="election-alerts-title" className="h3">Nigeria 2027 election alerts</h2>
          <span className="rounded-full border hairline px-2.5 py-0.5 text-[0.75rem] text-[color:var(--muted)]">Pro and above</span>
        </div>
        <p className="mt-3 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
          Election incidents pushed to your Slack, Teams, Discord or Google Chat channel, or any webhook, about an hour
          after they are reported: violence, thuggery, abductions, arson, ballot snatching, vote buying, intimidation, BVAS or
          IReV failures and logistics problems, each rated high, medium or low and placed to state and LGA.
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">
          <li>Filter by severity, state, LGA, incident type, candidate or party.</li>
          <li>One message per incident: when many outlets report the same incident, you get it once, with the number of reports.</li>
          <li>Messages are not capped; the allowance is how many alerts you can have running at once. Create them here or through the API.</li>
        </ul>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-[0.8125rem]">
            <thead className="text-[color:var(--dim)]">
              <tr><th className="py-1.5 pr-3 font-normal">Plan</th><th className="py-1.5 pr-3 font-normal">Alerts at once</th><th className="py-1.5 font-normal">Includes</th></tr>
            </thead>
            <tbody className="divide-y divide-white/[0.07] border-t hairline">
              {ELECTION_ALERT_PLANS.map(([key, label, count, includes]) => (
                <tr key={key} className={plan?.plan === key ? "text-[color:var(--text)]" : "text-[color:var(--muted)]"}>
                  <td className="py-1.5 pr-3">{label}{plan?.plan === key ? " (your plan)" : ""}</td>
                  <td className="kbd py-1.5 pr-3">{count}</td>
                  <td className="py-1.5">{includes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[0.875rem]">
          <Link href="/developers#elections" className="underline">API documentation</Link>
          <Link href="/pricing" className="underline">See plans</Link>
          <a href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Election alerts")}`} className="underline">Ask about Institutional access</a>
        </p>
        <ElectionAlerts />
      </section>

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
