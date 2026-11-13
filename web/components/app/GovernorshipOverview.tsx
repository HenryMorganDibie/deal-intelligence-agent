"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../lib/api";
import { get } from "../../lib/market";
import { govSlug } from "../../lib/governorship";
import { partyColour } from "../../lib/parties";
import { Container } from "../primitives";
import { ProBadge } from "./PlanLinks";
import { ErrorNote } from "./ui";
import { StateTileMap } from "./StateTileMap";

type Race = {
  state: string; election: string; lgas: number; reported: number; declared: number; complete: boolean;
  leader: { name: string; party: string | null; share: number } | null; margin: number | null;
  spread: { states_at_25: number; needed: number; met: boolean; of?: number } | null;
  won_2023: { name: string; party: string; share: number | null } | null; candidates: number;
};
type Data = { polling_day: string; races: Race[]; reported_states: number; complete_states: number };

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

/** All 28 governorship races on one page: a map by party, and each state's count, leader and 2023 winner. */
export function GovernorshipOverview() {
  const router = useRouter();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<{ status?: number; text: string } | null>(null);
  const load = useCallback(async () => {
    try { setData(await get<Data>("/api/elections/live/governorship")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? { status: e.status, text: e.message } : { text: "Results could not be loaded." }); }
  }, []);
  useEffect(() => {
    void load();
    const t = setInterval(() => { if (document.visibilityState === "visible") void load(); }, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const days = data ? Math.ceil((Date.parse(`${data.polling_day}T00:00:00Z`) - Date.now()) / 86_400_000) : 0;
  const leaders = Object.fromEntries((data?.races ?? []).map((r) => [r.state, r.leader?.party ?? null]));
  const past = Object.fromEntries((data?.races ?? []).filter((r) => r.won_2023).map((r) => [r.state, r.won_2023!.party]));

  return (
    <Container className="max-w-6xl py-10">
      <header>
        <p className="text-[0.8125rem] text-[color:var(--dim)]"><Link href="/app/elections/nigeria" className="underline-offset-2 hover:text-[color:var(--text)] hover:underline">Nigeria</Link></p>
        <h1 className="h2 mt-1 text-[1.75rem] sm:text-[2rem]">Governorship elections<span className="text-[color:var(--muted)]"> · 6 February 2027</span></h1>
        <p className="mt-2 max-w-3xl text-[0.8125rem] text-[color:var(--dim)]">
          28 states elect a governor on the same day. Each is decided by its own count, declared LGA by LGA at the state collation centre: the most votes and at least 25% in two-thirds of the state&apos;s LGAs.
          Anambra, Bayelsa, Edo, Ekiti, Imo, Kogi, Ondo and Osun vote off-cycle.
          {data && days > 0 && <span> {days} days to go.</span>}
        </p>
      </header>

      {error?.status === 403 ? (
        <p className="mt-8 inline-flex flex-wrap items-center gap-1 text-sm text-[color:var(--muted)]">Live results come with the Pro plan and above<ProBadge source="live_results" /></p>
      ) : error ? <div className="mt-8"><ErrorNote message={error.text} /></div> : !data ? (
        <p className="mt-8 text-sm text-[color:var(--dim)]" role="status">Loading…</p>
      ) : (
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,24rem)_1fr]">
          <div>
            <StateTileMap winners={leaders} baseline={past} baselineYear={2023} colour={partyColour}
                          onPick={(st) => { if (data.races.some((r) => r.state === st)) router.push(`/app/elections/nigeria/governorship/${govSlug(st)}`); }} />
            <p className="mt-1 text-[0.75rem] text-[color:var(--dim)]">Solid: leading party once counting starts. Empty squares vote off-cycle. Click a state to open its race.</p>
            <p className="mt-4 text-[0.8125rem] text-[color:var(--muted)]">{data.reported_states} of 28 states counting · {data.complete_states} complete</p>
          </div>
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-[0.8125rem]">
              <thead className="text-[color:var(--dim)]">
                <tr><th className="py-2 pr-3 font-normal">State</th><th className="py-2 pr-3 font-normal">LGAs in</th><th className="py-2 pr-3 font-normal">Leading</th><th className="py-2 pr-3 font-normal">25% rule</th><th className="py-2 font-normal">2023 winner</th></tr>
              </thead>
              <tbody className="divide-y divide-white/[0.07] border-t hairline">
                {data.races.map((r) => (
                  <tr key={r.state} className="cursor-pointer hover:bg-white/[0.03]" onClick={() => router.push(`/app/elections/nigeria/governorship/${govSlug(r.state)}`)}>
                    <td className="py-2 pr-3"><Link href={`/app/elections/nigeria/governorship/${govSlug(r.state)}`} className="text-[color:var(--text)] hover:underline">{r.state}</Link></td>
                    <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{r.reported}/{r.lgas}{r.complete ? " ✓" : ""}</td>
                    <td className="py-2 pr-3">{r.leader
                      ? <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: partyColour(r.leader.party) }} />{r.leader.name}<span className="text-[color:var(--dim)]"> · {r.leader.party} {pct(r.leader.share)}</span></span>
                      : <span className="text-[color:var(--dim)]">{r.candidates} candidates</span>}</td>
                    <td className={`py-2 pr-3 ${r.spread?.met ? "text-verified" : "text-[color:var(--dim)]"}`}>{r.spread ? (r.spread.met ? "Met" : `${r.spread.states_at_25}/${r.spread.needed}`) : "–"}</td>
                    <td className="py-2 text-[color:var(--muted)]">{r.won_2023 ? <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: partyColour(r.won_2023.party) }} />{r.won_2023.name.split(" ").slice(-1)[0]} · {r.won_2023.party}</span> : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Container>
  );
}
