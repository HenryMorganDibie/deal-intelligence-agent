"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../../lib/api-base";

type Plan = {
  plan: string; label: string; price_month_ngn: number | null; price_year_ngn: number | null;
  price_month_usd: number | null; price_year_usd: number | null; monthly_requests: number; ai_monthly: number;
  alerts_max: number; max_keys: number; exports: boolean;
};
type Site = {
  announcement: { on?: boolean; text?: string; link?: string | null; tone?: "info" | "warning" };
  signups: { open?: boolean; message?: string | null };
  ai: { on?: boolean; message?: string | null };
};
type Settings = { site: Site; currencies: string[]; plans: Plan[] };
type Deal = {
  id: string; announced: string | null; deal_type: string; stage: string | null; target: string | null; buyer: string | null;
  seller: string | null; amount_usd: number | null; country: string | null; headline: string | null; excluded?: string | null;
  reviewed_on?: string | null;
};

const PLAN_COLUMNS: [keyof Plan & string, string][] = [
  ["price_month_ngn", "₦ a month"], ["price_year_ngn", "₦ a year"], ["price_month_usd", "$ a month"], ["price_year_usd", "$ a year"],
  ["monthly_requests", "API requests"], ["ai_monthly", "Briefs"], ["alerts_max", "Alerts"], ["max_keys", "API keys"],
];
const DEAL_TYPES = ["acquisition", "merger", "equity_funding", "debt_financing", "fund_raise", "ipo", "exit"];

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const r = await fetch(apiUrl(path), { method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { detail?: string }).detail || "That did not work.");
  return data as T;
}

/** The owner's controls that used to need a code change: site switches, plans and prices, currencies, deal fixes. */
export function SettingsPanel({ adminKey }: { adminKey: string }) {
  const [s, setS] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    try { setS(await post<Settings>("/api/admin/settings", { key: adminKey })); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { if (adminKey) void load(); }, [adminKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn: () => Promise<unknown>, done: string) {
    setNote(null);
    try { await fn(); setNote({ ok: true, text: done }); await load(); }
    catch (e) { setNote({ ok: false, text: (e as Error).message }); }
  }

  if (error) return <p className="mt-3 text-sm text-risk">{error}</p>;
  if (!s) return <p className="mt-3 text-sm text-[color:var(--muted)]">Loading settings…</p>;

  return (
    <div className="space-y-10">
      {note && <p role="status" className={`text-sm ${note.ok ? "text-verified" : "text-risk"}`}>{note.text}</p>}
      <SiteSwitches site={s.site} adminKey={adminKey} act={act} />
      <PlansEditor plans={s.plans} usd={s.currencies.includes("USD")} adminKey={adminKey} act={act} />
      <DealFixer adminKey={adminKey} />
    </div>
  );
}

function Section({ title, about, children }: { title: string; about: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 max-w-3xl text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">{about}</p>
      <div className="mt-3">{children}</div>
    </section>
  );
}

const input = "w-full rounded-lg border hairline bg-transparent px-3 py-2 text-sm";
const smallBtn = "rounded-md border hairline px-3 py-1.5 text-[0.8125rem] hover:bg-white/[0.06]";

function SiteSwitches({ site, adminKey, act }: {
  site: Site; adminKey: string;
  act: (fn: () => Promise<unknown>, done: string) => Promise<void>;
}) {
  const [text, setText] = useState(site.announcement.text ?? "");
  const [link, setLink] = useState(site.announcement.link ?? "");
  const [tone, setTone] = useState(site.announcement.tone ?? "info");
  const [signupMsg, setSignupMsg] = useState(site.signups.message ?? "");
  const [aiMsg, setAiMsg] = useState(site.ai.message ?? "");
  const set = (key: string, value: Record<string, unknown>, done: string) =>
    act(() => post("/api/admin/settings/site", { key: adminKey, setting: key, value }), done);
  const bannerOn = site.announcement.on === true, signupsOpen = site.signups.open !== false, aiOn = site.ai.on !== false;

  return (
    <Section title="Site switches" about="Take effect within a minute, everywhere. Each switch shows its current state.">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="panel p-4">
          <p className="font-medium">Announcement banner <span className={bannerOn ? "text-verified" : "text-[color:var(--dim)]"}>· {bannerOn ? "showing" : "off"}</span></p>
          <p className="mt-1 text-[0.75rem] text-[color:var(--muted)]">Shown at the foot of every page until the reader dismisses it.</p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={240} rows={3} placeholder="e.g. Nigeria election results are live: follow every state."
            aria-label="Announcement text" className={`${input} mt-2`} />
          <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Link (optional), e.g. /markets" aria-label="Announcement link" className={`${input} mt-2`} />
          <select value={tone} onChange={(e) => setTone(e.target.value as "info" | "warning")} aria-label="Tone" className={`${input} mt-2`}>
            <option value="info">Information</option><option value="warning">Warning (outage, delay)</option>
          </select>
          <div className="mt-3 flex gap-2">
            <button type="button" className={smallBtn} onClick={() => set("announcement", { on: true, text, link, tone }, "Banner is showing.")}>{bannerOn ? "Update" : "Show"}</button>
            {bannerOn && <button type="button" className={smallBtn} onClick={() => set("announcement", { on: false, text, link, tone }, "Banner is off.")}>Turn off</button>}
          </div>
        </div>

        <div className="panel p-4">
          <p className="font-medium">New sign-ups <span className={signupsOpen ? "text-verified" : "text-risk"}>· {signupsOpen ? "open" : "paused"}</span></p>
          <p className="mt-1 text-[0.75rem] text-[color:var(--muted)]">Pausing stops new email sign-ups; existing accounts sign in as usual. Attempts appear under Sign-in trouble.</p>
          <input value={signupMsg} onChange={(e) => setSignupMsg(e.target.value)} maxLength={240} placeholder="Message while paused (optional)"
            aria-label="Sign-up pause message" className={`${input} mt-2`} />
          <div className="mt-3">
            <button type="button" className={smallBtn} onClick={() => set("signups", { open: !signupsOpen, message: signupMsg },
              signupsOpen ? "New sign-ups are paused." : "New sign-ups are open.")}>{signupsOpen ? "Pause sign-ups" : "Open sign-ups"}</button>
          </div>
        </div>

        <div className="panel p-4">
          <p className="font-medium">AI briefs and research <span className={aiOn ? "text-verified" : "text-risk"}>· {aiOn ? "on" : "paused"}</span></p>
          <p className="mt-1 text-[0.75rem] text-[color:var(--muted)]">Pause if model costs spike or a provider is down. Browsing, markets, alerts and the API keep working.</p>
          <input value={aiMsg} onChange={(e) => setAiMsg(e.target.value)} maxLength={240} placeholder="Message while paused (optional)"
            aria-label="AI pause message" className={`${input} mt-2`} />
          <div className="mt-3">
            <button type="button" className={smallBtn} onClick={() => set("ai", { on: !aiOn, message: aiMsg },
              aiOn ? "AI briefs are paused." : "AI briefs are on.")}>{aiOn ? "Pause AI briefs" : "Turn AI briefs on"}</button>
          </div>
        </div>
      </div>
    </Section>
  );
}

function PlansEditor({ plans, usd, adminKey, act }: {
  plans: Plan[]; usd: boolean; adminKey: string; act: (fn: () => Promise<unknown>, done: string) => Promise<void>;
}) {
  const [edits, setEdits] = useState<Record<string, Record<string, string | boolean>>>({});
  const value = (p: Plan, k: string) => (edits[p.plan]?.[k] ?? (p[k as keyof Plan] ?? "")) as string | boolean;
  const change = (plan: string, k: string, v: string | boolean) => setEdits((e) => ({ ...e, [plan]: { ...e[plan], [k]: v } }));

  return (
    <Section title="Plans and prices"
      about="Prices are whole naira or dollars. People already subscribed keep the price they signed up at; new checkouts use the new price. Limits apply to everyone on the plan straight away, and the pricing page quotes the new numbers. Institutional is priced per firm: leave its prices empty and set each firm's limits under Accounts → Limits.">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="text-[color:var(--muted)]">
            <tr><th className="py-2 pr-2 font-normal">Plan</th>{PLAN_COLUMNS.map(([, l]) => <th key={l} className="py-2 pr-2 font-normal">{l}</th>)}
              <th className="py-2 pr-2 font-normal">CSV</th><th /></tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.plan} className="border-t hairline">
                <td className="py-2 pr-2 font-medium">{p.label}</td>
                {PLAN_COLUMNS.map(([k, l]) => (
                  <td key={k} className="py-2 pr-2">
                    <input inputMode="numeric" aria-label={`${p.label} ${l}`} value={String(value(p, k))}
                      onChange={(e) => change(p.plan, k, e.target.value.replace(/[^0-9]/g, ""))}
                      className="w-24 rounded-md border hairline bg-transparent px-2 py-1" />
                  </td>
                ))}
                <td className="py-2 pr-2">
                  <input type="checkbox" aria-label={`${p.label} CSV export`} checked={Boolean(value(p, "exports"))}
                    onChange={(e) => change(p.plan, "exports", e.target.checked)} />
                </td>
                <td className="py-2 text-right">
                  <button type="button" disabled={!edits[p.plan]} className={smallBtn}
                    onClick={() => act(() => post("/api/admin/settings/plan", { key: adminKey, plan: p.plan, fields: edits[p.plan] })
                      .then(() => setEdits((e) => { const n = { ...e }; delete n[p.plan]; return n; })), `${p.label} saved.`)}>
                    Save
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span>Dollar checkout: <b className={usd ? "text-verified" : ""}>{usd ? "offered" : "naira only"}</b></span>
        <button type="button" className={smallBtn} onClick={() => act(() => post("/api/admin/settings/currencies", { key: adminKey, usd: !usd }),
          usd ? "Checkout is naira only." : "Dollar checkout is offered.")}>{usd ? "Stop dollar checkout" : "Offer dollar checkout"}</button>
        <span className="text-[0.75rem] text-[color:var(--dim)]">Turn on only once your Paystack account accepts dollar payments.</span>
      </div>
    </Section>
  );
}

function DealFixer({ adminKey }: { adminKey: string }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Deal[] | null>(null);
  const [open, setOpen] = useState<Deal | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  async function find() {
    setError(""); setNote("");
    try { setRows(await post<Deal[]>("/api/admin/deals/find", { key: adminKey, q })); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <Section title="Fix a deal"
      about="Find a deal by words in its headline, target or buyer, or by its id, then correct it or hide it. Your correction is marked as reviewed, so the daily pipeline never overwrites it. A hidden deal can be found by its id and shown again.">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void find(); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Swoop seed, or 921cff0a634d633d" aria-label="Find a deal" className={input} />
        <button type="submit" className="btn btn-primary">Find</button>
      </form>
      {error && <p className="mt-2 text-sm text-risk">{error}</p>}
      {note && <p role="status" className="mt-2 text-sm text-verified">{note}</p>}
      {rows && (rows.length === 0 ? <p className="mt-3 text-sm text-[color:var(--muted)]">No deals match.</p> : (
        <ul className="mt-3 divide-y divide-white/[0.06] border-y hairline">
          {rows.map((d) => (
            <li key={d.id} className="flex flex-wrap items-start justify-between gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{d.target || "No target"} <span className="font-normal text-[color:var(--dim)]">· {d.deal_type.replace(/_/g, " ")} · {d.announced} · {d.country ?? "no country"}
                  {d.amount_usd ? ` · $${Math.round(d.amount_usd).toLocaleString("en-US")}` : ""}</span>
                  {d.excluded && <span className="ml-2 text-risk">hidden</span>}{d.reviewed_on && <span className="ml-2 text-verified">reviewed</span>}</p>
                <p className="truncate text-[0.75rem] text-[color:var(--muted)]">{d.headline}</p>
              </div>
              <button type="button" className={smallBtn} onClick={() => setOpen(d)}>Edit</button>
            </li>
          ))}
        </ul>
      ))}
      {open && <DealEditor deal={open} adminKey={adminKey} onClose={() => setOpen(null)}
        onSaved={(d, text) => { setOpen(null); setNote(text); setRows((r) => r?.map((x) => (x.id === d.id ? d : x)) ?? null); }} />}
    </Section>
  );
}

function DealEditor({ deal, adminKey, onClose, onSaved }: {
  deal: Deal; adminKey: string; onClose: () => void; onSaved: (d: Deal, text: string) => void;
}) {
  const [f, setF] = useState({
    target: deal.target ?? "", buyer: deal.buyer ?? "", seller: deal.seller ?? "",
    amount_usd: deal.amount_usd ? String(Math.round(deal.amount_usd)) : "", deal_type: deal.deal_type,
    stage: deal.stage ?? "completed", country: deal.country ?? "",
  });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(extra: Record<string, unknown>, text: string) {
    setBusy(true); setError("");
    const changed: Record<string, unknown> = {};
    const original: Record<string, string> = {
      target: deal.target ?? "", buyer: deal.buyer ?? "", seller: deal.seller ?? "",
      amount_usd: deal.amount_usd ? String(Math.round(deal.amount_usd)) : "", deal_type: deal.deal_type,
      stage: deal.stage ?? "completed", country: deal.country ?? "",
    };
    for (const [k, v] of Object.entries(f)) if (v !== original[k]) changed[k] = v;
    try {
      const d = await post<Deal>("/api/admin/deals/update", { key: adminKey, id: deal.id, set: changed, ...extra });
      onSaved(d, text);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const field = (k: keyof typeof f, label: string) => (
    <label className="block text-sm"><span className="font-medium">{label}</span>
      <input value={f[k]} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} aria-label={label} className={`${input} mt-1`} /></label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="deal-edit-title" className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border hairline bg-[color:var(--bg)] p-6 shadow-2xl">
        <h3 id="deal-edit-title" className="text-lg font-semibold">Fix deal {deal.id}</h3>
        <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{deal.headline}</p>
        <div className="mt-4 space-y-3">
          {field("target", "Target (company the deal is about)")}
          {field("buyer", "Buyer or lead investor")}
          {field("seller", "Seller")}
          {field("amount_usd", "Amount in US dollars (empty if undisclosed)")}
          <label className="block text-sm"><span className="font-medium">Type</span>
            <select value={f.deal_type} onChange={(e) => setF((x) => ({ ...x, deal_type: e.target.value }))} aria-label="Type" className={`${input} mt-1`}>
              {DEAL_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select></label>
          <label className="block text-sm"><span className="font-medium">Stage</span>
            <select value={f.stage} onChange={(e) => setF((x) => ({ ...x, stage: e.target.value }))} aria-label="Stage" className={`${input} mt-1`}>
              <option value="rumoured">Rumoured (talks)</option><option value="announced">Announced (agreed)</option><option value="completed">Completed</option>
            </select></label>
          {field("country", "Country (two-letter code, e.g. NG, KE)")}
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-risk">{error}</p>}
        <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
          {deal.excluded ? (
            <button type="button" disabled={busy} className="mr-auto rounded-md px-3 py-2 text-sm text-verified" onClick={() => save({ unhide: true }, "The deal is visible again.")}>Show again</button>
          ) : (
            <span className="mr-auto flex items-center gap-2">
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why hide it?" aria-label="Reason to hide" className="w-40 rounded-md border hairline bg-transparent px-2 py-1.5 text-sm" />
              <button type="button" disabled={busy} className="rounded-md px-2 py-1.5 text-sm text-risk" onClick={() => save({ hide: reason || "hidden by owner" }, "The deal is hidden.")}>Hide</button>
            </span>
          )}
          <button type="button" onClick={onClose} className="btn btn-ghost">Cancel</button>
          <button type="button" disabled={busy} onClick={() => save({}, "Deal corrected.")} className="btn btn-primary">{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}
