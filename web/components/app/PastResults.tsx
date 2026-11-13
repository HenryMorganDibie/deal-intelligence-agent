"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../lib/api";
import { get } from "../../lib/market";
import { Segmented } from "./Chip";

type Row = { party: string; candidate: string | null; votes: number; share: number | null };
type YearResult = { year: number; state: string; total_valid: number | null; results: Row[]; others?: number };
type Data = {
  national: Record<string, { declared: Record<string, number>; registered?: number; valid?: number; state_sums_differ?: Record<string, number> }>;
  states: Record<string, YearResult[]>;
  candidates: Record<string, Record<string, string>>;
};

const YEARS = [2023, 2019, 2015];
const PARTY_COLOURS: Record<string, string> = { APC: "#6ee7c8", PDP: "#f5b955", LP: "#8fb4ff", NNPP: "#b0a089" };
const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null | undefined) => (x == null ? "–" : x.toLocaleString("en-GB"));

/** Nigeria's presidential results by state in 2015, 2019 and 2023, as INEC declared them: the baseline for 2027. */
export function PastResults({ selected }: { selected?: string | null }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState(2023);
  const [state, setState] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setData(await get<Data>("/api/elections/history")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Past results could not be loaded."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (selected) setState(selected); }, [selected]);

  if (error) return <p className="mt-3 text-sm text-[color:var(--muted)]">{error}</p>;
  if (!data) return null;
  const nat = data.national[String(year)];
  const names = data.candidates[String(year)] ?? {};
  const states = Object.entries(data.states).map(([s, ys]) => [s, ys.find((y) => y.year === year)!] as const)
    .sort((a, b) => a[0].localeCompare(b[0]));
  const picked = state ? data.states[state] : null;

  return (
    <section id="past-results">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[0.875rem] text-[color:var(--muted)]">Presidential results by state, as INEC declared them</p>
        <Segmented label="Year" value={String(year)} onChange={(v) => setYear(Number(v))}
                   options={YEARS.map((y) => [String(y), String(y)] as [string, string])} />
      </div>

      <div className="panel mt-3 p-5">
        <p className="text-[0.8125rem] text-[color:var(--muted)]">National, {year}{nat.registered ? ` · ${num(nat.registered)} registered` : ""}</p>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2">
          {Object.entries(nat.declared).filter(([p]) => p !== "others").sort((a, b) => b[1] - a[1]).map(([p, v]) => (
            <li key={p} className="flex items-center justify-between gap-2 text-[0.875rem]">
              <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: PARTY_COLOURS[p] ?? "#999" }} />{names[p] ?? p} <span className="text-[color:var(--dim)]">{p}</span></span>
              <span className="kbd">{num(v)}</span>
            </li>
          ))}
        </ul>
        {nat.state_sums_differ && (
          <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
            State figures sum to {Object.entries(nat.state_sums_differ).map(([p, d]) => `${d > 0 ? "+" : ""}${num(d)} for ${p}`).join(" and ")} against INEC&apos;s national totals.
          </p>
        )}
      </div>

      {picked && (
        <div className="panel mt-3 p-5">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-[0.875rem] text-[color:var(--text)]">{state} across three elections</p>
            <button type="button" onClick={() => setState(null)} className="text-[0.75rem] underline text-[color:var(--muted)]">Close</button>
          </div>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {picked.map((y) => (
              <div key={y.year}>
                <p className="text-[0.75rem] text-[color:var(--dim)]">{y.year}</p>
                <ul className="mt-1 space-y-0.5 text-[0.8125rem]">
                  {y.results.map((r) => (
                    <li key={r.party} className="flex justify-between gap-2"><span>{r.candidate ?? r.party} <span className="text-[color:var(--dim)]">{r.party}</span></span><span className="kbd text-[color:var(--muted)]">{num(r.votes)}{r.share != null ? ` · ${pct(r.share)}` : ""}</span></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-[0.8125rem]">
          <thead className="text-[color:var(--dim)]">
            <tr><th className="py-2 pr-3 font-normal">State</th><th className="py-2 pr-3 font-normal">Winner</th><th className="py-2 pr-3 font-normal">Votes</th><th className="py-2 pr-3 font-normal">Share</th><th className="py-2 font-normal">Runner-up</th></tr>
          </thead>
          <tbody className="divide-y divide-white/[0.07] border-t hairline">
            {states.map(([s, y]) => {
              const [w, r] = y.results;
              return (
                <tr key={s} className="cursor-pointer hover:bg-white/[0.02]" onClick={() => setState(s)}>
                  <td className="py-1.5 pr-3 underline-offset-2 hover:underline">{s}</td>
                  <td className="py-1.5 pr-3"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: PARTY_COLOURS[w.party] ?? "#999" }} />{w.candidate ?? w.party} <span className="text-[color:var(--dim)]">{w.party}</span></span></td>
                  <td className="kbd py-1.5 pr-3">{num(w.votes)}</td>
                  <td className="kbd py-1.5 pr-3">{pct(w.share)}</td>
                  <td className="py-1.5 text-[color:var(--muted)]">{r ? `${r.candidate ?? r.party} ${pct(r.share) !== "–" ? pct(r.share) : num(r.votes)}` : "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[0.75rem] text-[color:var(--dim)]">
        Click a state for its three elections side by side. 2015 and 2019 add up exactly to INEC&apos;s national totals; 2023&apos;s
        state figures come from BBC&apos;s record of INEC&apos;s announcements. CSV download through the API.
      </p>
    </section>
  );
}
