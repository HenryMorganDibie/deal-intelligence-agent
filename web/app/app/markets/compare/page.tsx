"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { MarketsTitle } from "../../../../components/app/MarketsNav";
import { Container } from "../../../../components/primitives";
import { ApiError } from "../../../../lib/api";
import { ErrorNote } from "../../../../components/app/ui";
import { get } from "../../../../lib/market";
import type { Directory, DirectoryRow } from "../../../../lib/markets-data";
import {
  GROUPS, caveats, decodeEntries, encodeEntries, leaders, visibleMetrics,
  type CompareProfile, type DirectoryFacts, type Entry, type EntryRef, type Metric,
} from "../../../../lib/compare";

const MAX = 4;
// Anonymous visitors to the shared Nigerian-stocks preview can see only this fixed basket.
const PUBLIC_PREVIEW_REFS: EntryRef[] = [
  { name: "Guaranty Trust Holding Company Plc", exchange: "ngx", symbol: "GTCO" },
  { name: "First HoldCo Plc", exchange: "ngx", symbol: "FIRSTHOLDCO" },
  { name: "Zenith Bank Plc", exchange: "ngx", symbol: "ZENITHBANK" },
];
const MOVES = new Set(["chg_1d", "ytd", "growth"]);   // changes, shown with a sign; levels (margins, yields) without
type Row = Entry & { ref: EntryRef };

function usd(v: number): string {
  const a = Math.abs(v);
  return a >= 1e12 ? `$${(v / 1e12).toFixed(2)}tn` : a >= 1e9 ? `$${(v / 1e9).toFixed(a >= 1e10 ? 1 : 2)}bn`
    : a >= 1e6 ? `$${(v / 1e6).toFixed(a >= 1e8 ? 0 : 1)}m` : `$${Math.round(v).toLocaleString("en")}`;
}

function show(metric: Metric, v: number | string | null): string {
  if (v == null || v === "") return "–";
  if (typeof v === "string") return v;
  if (metric.kind === "usd") return usd(v);
  if (metric.kind === "pct") return `${v > 0 && MOVES.has(metric.key) ? "+" : ""}${(v * 100).toFixed(1)}%`;
  if (metric.kind === "x") return `${v.toFixed(1)}×`;
  return v.toLocaleString("en");
}

function refOf(r: DirectoryRow): EntryRef {
  return r.kind === "listed" && r.exchange && r.symbol
    ? { name: r.name, exchange: r.exchange, symbol: r.symbol, country: r.country }
    : { name: r.name, country: r.country };
}

function factsOf(r: DirectoryRow): DirectoryFacts {
  return { kind: r.kind, exchange: r.exchange, exchange_name: r.exchange_name, symbol: r.symbol, sector: r.sector,
    chg_1d: r.chg_1d, ytd_usd: r.ytd_usd, mcap_usd: r.mcap_usd, pe: r.pe, deal_count: r.deal_count,
    equity_raised_usd: r.equity_raised_usd, debt_raised_usd: r.debt_raised_usd, last_round: r.last_round,
    last_deal_date: r.last_deal_date, valuation_usd: r.valuation_usd, valuation_date: r.valuation_date };
}

const sameRef = (a: EntryRef, b: EntryRef) => (a.exchange && a.symbol
  ? a.exchange === b.exchange && a.symbol === b.symbol
  : !b.symbol && a.name.trim().toLowerCase() === b.name.trim().toLowerCase());

/** The profile for a reference, and the directory's facts for it (found by name when not passed in). */
async function load(ref: EntryRef, facts?: DirectoryFacts | null): Promise<Row> {
  const params: Record<string, string> = { name: ref.name };
  if (ref.exchange && ref.symbol) Object.assign(params, { exchange: ref.exchange, symbol: ref.symbol });
  else if (ref.country) params.country = ref.country;
  const [profile, found] = await Promise.all([
    get<CompareProfile>("/api/companies/profile", params),
    facts !== undefined ? Promise.resolve(null)
      : get<Directory>("/api/companies/directory", { q: ref.name, limit: 10 }).catch(() => null),
  ]);
  const match = found?.rows.find((r) => sameRef(ref, refOf(r)));
  return { ref, profile, facts: facts ?? (match ? factsOf(match) : null) };
}

export default function MarketsComparePage({ publicPreview = false }: { publicPreview?: boolean }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<DirectoryRow[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const restored = useRef(false);

  // A shared link (?c=...) restores its comparison once.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const refs = publicPreview
      ? PUBLIC_PREVIEW_REFS
      : decodeEntries(new URLSearchParams(window.location.search).get("c"));
    if (!refs.length) return;
    setBusy(true);
    Promise.allSettled(refs.map((r) => load(r)))
      .then((results) => setRows(results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []))))
      .finally(() => setBusy(false));
  }, []);

  // Keep the address in step, so the page can be bookmarked or shared.
  useEffect(() => {
    if (!restored.current) return;
    const url = new URL(window.location.href);
    if (rows.length) url.searchParams.set("c", encodeEntries(rows.map((r) => r.ref)));
    else url.searchParams.delete("c");
    window.history.replaceState(null, "", url.toString());
  }, [rows]);

  // Suggestions from every company on record, listed and private.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setSuggestions([]); return; }
    let live = true;
    const t = window.setTimeout(() => {
      get<Directory>("/api/companies/directory", { q, limit: 8 })
        .then((d) => { if (live) setSuggestions(d.rows); })
        .catch(() => { if (live) setSuggestions([]); });
    }, 200);
    return () => { live = false; window.clearTimeout(t); };
  }, [query]);

  async function add(ref: EntryRef, facts: DirectoryFacts | null | undefined) {
    setError(null);
    if (rows.length >= MAX) { setError("Compare up to four at a time. Remove one first."); return; }
    if (rows.some((r) => sameRef(r.ref, ref))) { setError(`${ref.name} is already in the comparison.`); return; }
    setBusy(true);
    setOpen(false);
    try {
      const row = await load(ref, facts);
      setRows((cur) => [...cur, row].slice(0, MAX));
      setQuery("");
      setSuggestions([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not load ${ref.name}.`);
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    const first = suggestions[0];
    // Enter takes the top suggestion when it is plainly the company typed; otherwise the name as typed.
    if (first && first.name.toLowerCase().startsWith(q.toLowerCase())) add(refOf(first), factsOf(first));
    else add({ name: q }, undefined);
  }

  async function share() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard unavailable: the address bar still holds the link */ }
  }

  const entries: Entry[] = rows;
  const metrics = visibleMetrics(entries);
  const notes = caveats(entries);
  const fxDate = rows.map((r) => r.profile.fx?.as_of).find(Boolean);

  return (
    <Container className="pb-10 pt-6 lg:pb-14">
      <MarketsTitle title="Compare companies">
        Up to four listed or private companies side by side, every amount in US dollars and every ratio worked out from the company&apos;s own statements.
      </MarketsTitle>

      {!publicPreview && <section className="panel p-5 sm:p-6" aria-labelledby="compare-add">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="compare-add" className="h3 text-lg">Add a company</h2>
          <p className="text-xs text-[color:var(--dim)]">{rows.length} of {MAX}</p>
        </div>
        <form onSubmit={submit} className="relative mt-3 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <label htmlFor="compare-q" className="sr-only">Company name or ticker</label>
            <input id="compare-q" className="field w-full" value={query} autoComplete="off" maxLength={120}
              placeholder="Search listed and private companies, e.g. Safaricom, Dangote Cement, Moniepoint"
              role="combobox" aria-expanded={open && suggestions.length > 0} aria-controls="compare-suggestions"
              onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
              onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 150)} />
            {open && suggestions.length > 0 && (
              <ul id="compare-suggestions" role="listbox"
                className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded-xl border hairline bg-raised/[0.98] p-1 shadow-xl">
                {suggestions.map((s) => (
                  <li key={`${s.kind}:${s.exchange ?? ""}:${s.symbol ?? s.name}`} role="option" aria-selected="false">
                    <button type="button" className="flex w-full items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/[0.05]"
                      onMouseDown={(e) => e.preventDefault()} onClick={() => add(refOf(s), factsOf(s))}>
                      <span className="min-w-0 truncate">{s.name}</span>
                      <span className="shrink-0 text-xs text-[color:var(--dim)]">
                        {s.kind === "listed" ? `${s.symbol} · ${s.exchange_name ?? s.exchange?.toUpperCase()}` : `Private${s.country ? ` · ${s.country}` : ""}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy || rows.length >= MAX || !query.trim()}>
            {busy ? "Loading…" : "Add"}
          </button>
        </form>
        {error && <div className="mt-3"><ErrorNote message={error} /></div>}
      </section>

      {rows.length === 0 ? (
        <section className="mt-6 rounded-xl border border-dashed hairline p-8 text-center">
          <h2 className="text-base font-medium">{busy ? "Loading the comparison…" : "Pick two or more companies."}</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-[color:var(--muted)]">
            Listed shares show market value, returns and valuation multiples; any company with filed statements shows margins,
            returns on capital and leverage; private companies show their rounds and valuations.
          </p>
        </section>
      ) : (
        <>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-[color:var(--dim)]">
              Amounts in US dollars at the official rate{fxDate ? ` of ${String(fxDate).slice(5, 16)}` : ""}; as reported underneath. ▲ marks the leader on a measure where higher or lower is better.
            </p>
            <button type="button" className="btn btn-ghost h-9 text-sm" onClick={share}>{copied ? "Link copied" : "Copy link to this comparison"}</button>
          </div>

          {notes.length > 0 && (
            <aside className="mt-3 rounded-xl border hairline p-4" aria-label="Read with care">
              <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-[color:var(--muted)]">
                {notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </aside>
          )}

          <div className="mt-4 overflow-x-auto rounded-xl border hairline">
            <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b hairline">
                  <th scope="col" className="sticky left-0 z-10 w-48 bg-[color:var(--panel)] px-3 py-3 text-xs font-normal text-[color:var(--dim)]">Measure</th>
                  {rows.map((r) => (
                    <th scope="col" key={encodeEntries([r.ref])} className="min-w-44 px-3 py-3 align-top font-normal">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="break-words font-semibold">{r.profile.name}</p>
                          <p className="text-xs text-[color:var(--dim)]">
                            {r.facts?.kind === "private" || (!r.ref.symbol && !r.profile.market) ? "Private" : [r.ref.symbol ?? r.profile.ticker, r.facts?.exchange_name ?? r.profile.exchange].filter(Boolean).join(" · ")}
                          </p>
                        </div>
                        <button type="button" className="text-xs text-[color:var(--muted)] hover:text-[color:var(--text)]" aria-label={`Remove ${r.profile.name}`}
                          onClick={() => setRows((cur) => cur.filter((x) => x !== r))}>✕</button>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              {GROUPS.map((group) => {
                const inGroup = metrics.filter((m) => m.group === group);
                if (!inGroup.length) return null;
                return (
                  <tbody key={group}>
                    <tr><th colSpan={rows.length + 1} scope="colgroup" className="bg-white/[0.02] px-3 pb-1.5 pt-4 text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-[color:var(--dim)]">{group}</th></tr>
                    {inGroup.map((m) => {
                      const lead = leaders(m, entries);
                      return (
                        <tr key={m.key} className="border-b hairline last:border-0">
                          <th scope="row" className="sticky left-0 z-10 bg-[color:var(--panel)] px-3 py-2.5 text-xs font-normal text-[color:var(--muted)]" title={m.note}>
                            {m.label}{m.note ? <span className="text-[color:var(--dim)]"> ⓘ</span> : null}
                          </th>
                          {rows.map((r, i) => {
                            const v = m.value(r);
                            const local = m.local?.(r);
                            return (
                              <td key={encodeEntries([r.ref])} className={`kbd px-3 py-2.5 align-top ${m.kind === "text" ? "font-sans text-xs" : ""} ${lead.has(i) ? "font-semibold text-verified" : ""}`}>
                                {lead.has(i) ? "▲ " : ""}{show(m, v)}
                                {local && v != null && <span className="block text-[0.6875rem] font-normal text-[color:var(--dim)]">{local}</span>}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                );
              })}
            </table>
          </div>

          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs">
            {rows.map((r) => (
              <span key={encodeEntries([r.ref])} className="text-[color:var(--muted)]">
                {r.profile.name}:{" "}
                <Link href={`/companies?name=${encodeURIComponent(r.profile.name)}${r.ref.exchange && r.ref.symbol ? `&exchange=${r.ref.exchange}&symbol=${encodeURIComponent(r.ref.symbol)}` : ""}`} className="underline-offset-4 hover:underline">profile</Link>
                {" · "}
                <Link href={`/markets/valuation?company=${encodeURIComponent(r.profile.name)}${r.profile.ticker ? `&ticker=${encodeURIComponent(r.profile.ticker)}` : ""}`} className="underline-offset-4 hover:underline">value it</Link>
                {r.profile.financials?.source_url && <>{" · "}<a href={r.profile.financials.source_url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">statements ↗</a></>}
              </span>
            ))}
          </div>
        </>
      )}

      <p className="mt-8 text-xs leading-relaxed text-[color:var(--dim)]">
        A side-by-side view, not a ranking or a recommendation. Ratios come from each company&apos;s latest reported statements and
        are left blank where a figure is missing; a lower multiple alone doesn&apos;t make a company cheaper, and sectors differ
        (bank margins and leverage don&apos;t compare with a cement maker&apos;s).
      </p>
    </Container>
  );
}
