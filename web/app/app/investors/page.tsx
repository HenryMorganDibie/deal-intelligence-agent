"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, Pagination, Table, Td, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { SECTORS, get, type InvestorRow } from "../../../lib/market";

type Fund = { id: string; fund_or_manager: string; stage: string; amount_usd: number | null; lps: string[]; announced: string | null; headline: string };
const ROLES = ["", "investor", "lender", "acquirer", "seller", "lp", "gp"];
const KINDS = ["", "dfi", "multilateral", "private_equity", "private_credit", "venture_capital", "growth", "impact",
  "sovereign", "pension", "bank", "foundation", "corporate_venture", "accelerator", "investment_firm", "corporate"];
const STAGES = ["", "pre-seed", "seed", "series a", "series b", "series c", "series d", "growth", "bridge"];
type Tab = "investors" | "funds";
const TABS: [Tab, string][] = [["investors", "Investors"], ["funds", "Fund raises"]];
const MIN_SIZES: [string, string][] = [["", "Any round size"], ["1000000", "$1m+"], ["5000000", "$5m+"], ["20000000", "$20m+"],
  ["100000000", "$100m+"]];

export default function InvestorsPage() {
  // The open tab follows the address (#funds), so a link can open it directly.
  const [tab, setTab] = useState<Tab>("investors");
  const pick = (id: Tab) => {
    setTab(id);
    try { window.history.replaceState(null, "", `#${id}`); } catch { /* ignore */ }
  };
  useEffect(() => {
    const follow = () => {
      const h = window.location.hash.replace("#", "");
      if (TABS.some(([id]) => id === h)) setTab(h as Tab);
    };
    follow();
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, []);
  const [role, setRole] = useState("");
  const [kind, setKind] = useState("");
  const [sector, setSector] = useState("");
  const [country, setCountry] = useState("");
  const [stage, setStage] = useState("");
  const [since, setSince] = useState("");
  const [minUsd, setMinUsd] = useState("");
  const [leadOnly, setLeadOnly] = useState(false);
  const [dealsInScope, setDealsInScope] = useState<number | null>(null);
  const [rows, setRows] = useState<InvestorRow[] | null>(null);
  const [funds, setFunds] = useState<Fund[] | null>(null);
  const [investorTotal, setInvestorTotal] = useState(0);
  const [investorOffset, setInvestorOffset] = useState(0);
  const [investorLimit, setInvestorLimit] = useState(50);
  const [fundTotal, setFundTotal] = useState(0);
  const [fundOffset, setFundOffset] = useState(0);
  const [fundLimit, setFundLimit] = useState(50);
  const [error, setError] = useState<string | null>(null);
  const [fundsError, setFundsError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== "investors") return;
    let active = true;
    const load = () => {
      setError(null);
      get<{ investors: InvestorRow[]; total_matching: number; deals_in_scope: number }>("/api/investors", {
        role, kind, sector: sector || undefined, country: country.trim() || undefined, stage: stage || undefined,
        since: since || undefined, min_usd: minUsd || undefined, lead_only: leadOnly ? "true" : undefined,
        limit: investorLimit, offset: investorOffset,
      })
        .then((r) => { if (active) { setRows(r.investors); setInvestorTotal(r.total_matching); setDealsInScope(r.deals_in_scope); } })
        .catch((err) => {
          if (!active) return;
          setError(err instanceof ApiError ? err.message : "Could not load investors.");
        });
    };
    setRows(null);
    load();
    const interval = window.setInterval(load, 5 * 60 * 1000);
    window.addEventListener("focus", load);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", load);
    };
  }, [tab, role, kind, sector, country, stage, since, minUsd, leadOnly, investorOffset, investorLimit]);

  useEffect(() => {
    if (tab !== "funds") return;
    let active = true;
    const load = () => {
      setFundsError(null);
      get<{ funds: Fund[]; total_matching: number }>("/api/funds", { limit: fundLimit, offset: fundOffset })
        .then((r) => { if (active) { setFunds(r.funds); setFundTotal(r.total_matching); } })
        .catch((err) => {
          if (!active) return;
          setFundsError(err instanceof ApiError ? err.message : "Could not load fund raises.");
        });
    };
    load();
    const interval = window.setInterval(load, 5 * 60 * 1000);
    window.addEventListener("focus", load);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", load);
    };
  }, [tab, fundOffset, fundLimit]);

  return (
    <Container className="py-10 lg:py-14">
      <header className="mb-6">
        <h1 className="h2 text-[1.75rem] sm:text-[2rem]">Investors</h1>
        <p className="mt-1.5 max-w-3xl text-[0.875rem] text-[color:var(--muted)]">
          {tab === "investors"
            ? "Everyone on the other side of a deal: investors, lenders, acquirers, sellers, LPs and fund managers."
            : "Funds raised and closed by managers investing in Africa, with their anchors and LPs where named."}
        </p>
      </header>

      <div role="tablist" aria-label="Investors" className="-mx-1 mb-6 flex gap-6 overflow-x-auto border-b hairline px-1">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => pick(id)}
                  className={`-mb-px shrink-0 border-b-2 pb-2.5 text-[0.9375rem] transition-colors ${
                    tab === id ? "border-[color:var(--text)] text-[color:var(--text)]" : "border-transparent text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {label}
            {id === "investors" && rows !== null && <span className="ml-1.5 text-[0.8125rem] text-[color:var(--dim)]">{investorTotal.toLocaleString()}</span>}
            {id === "funds" && funds !== null && <span className="ml-1.5 text-[0.8125rem] text-[color:var(--dim)]">{fundTotal.toLocaleString()}</span>}
          </button>
        ))}
      </div>

      {tab === "investors" && (<>
      <div className="flex flex-wrap gap-3">
        <select value={role} onChange={(e) => { setRole(e.target.value); setInvestorOffset(0); }} className="field w-auto" aria-label="Role">
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r ? `Role: ${r.toUpperCase().length <= 2 ? r.toUpperCase() : words(r)}` : "All roles"}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(e) => { setKind(e.target.value); setInvestorOffset(0); }} className="field w-auto" aria-label="Investor type">
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k ? words(k) : "All investor types"}
            </option>
          ))}
        </select>
        <select value={sector} onChange={(e) => { setSector(e.target.value); setInvestorOffset(0); }} className="field w-auto" aria-label="Sector">
          <option value="">All sectors</option>
          {SECTORS.map((x) => <option key={x} value={x}>{words(x)}</option>)}
        </select>
        <input value={country} onChange={(e) => { setCountry(e.target.value); setInvestorOffset(0); }} placeholder="Country (e.g. Kenya)"
          className="field w-auto" aria-label="Country" />
        <select value={stage} onChange={(e) => { setStage(e.target.value); setInvestorOffset(0); }} className="field w-auto" aria-label="Round stage">
          {STAGES.map((x) => <option key={x} value={x}>{x ? words(x) : "Any stage"}</option>)}
        </select>
        <select value={minUsd} onChange={(e) => { setMinUsd(e.target.value); setInvestorOffset(0); }} className="field w-auto" aria-label="Round size">
          {MIN_SIZES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <input type="date" value={since} onChange={(e) => { setSince(e.target.value); setInvestorOffset(0); }} className="field w-auto"
          aria-label="Deals since" title="Only deals announced on or after this date" />
        <label className="flex items-center gap-2 text-[0.875rem] text-[color:var(--muted)]">
          <input type="checkbox" checked={leadOnly} onChange={(e) => { setLeadOnly(e.target.checked); setInvestorOffset(0); }} />
          Led a round
        </label>
      </div>
      {dealsInScope !== null && (
        <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
          Ranked on {dealsInScope.toLocaleString()} matching deal{dealsInScope === 1 ? "" : "s"}. Leads and round stages come from the article where it names them.
        </p>
      )}
      {error && <ErrorNote message={error} />}
      <div className="mt-6">
        {rows === null ? (
          <Loading />
        ) : (
          <>
          <Table head={["Name", "Type", "Deals", "Led", "Roles", "Typical round", "Value of deals involved", "Countries", "Last seen"]}>
            {rows.map((r) => (
              <tr key={r.name}>
                <Td>
                  <Link href={`/investors/${encodeURIComponent(r.name)}`} className="hover:underline">
                    {r.name}
                  </Link>
                  {r.hq && <span className="block text-[0.75rem] text-[color:var(--dim)]">{r.hq}</span>}
                </Td>
                <Td>
                  {words(r.type) || "n/a"}
                  {r.type_inferred && (
                    <span className="block text-[0.75rem] text-[color:var(--dim)]" title="Not in the curated investor registry; inferred from the name">inferred</span>
                  )}
                </Td>
                <Td>{r.deal_count}</Td>
                <Td>{r.lead_count ? r.lead_count : ""}</Td>
                <Td className="text-[color:var(--muted)]">{Object.entries(r.roles).map(([k, v]) => `${k} ${v}`).join(", ")}</Td>
                <Td className="whitespace-nowrap">
                  <span title="Median disclosed size of the rounds this party joined, not its own cheque">{usd(r.typical_round_usd)}</span>
                </Td>
                <Td className="whitespace-nowrap">
                  <span title="Total disclosed size of the deals this party took part in, not its own contribution">{usd(r.disclosed_usd)}</span>
                </Td>
                <Td className="text-[color:var(--muted)]">{Object.keys(r.countries).slice(0, 5).join(", ")}</Td>
                <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{r.last_seen ?? ""}</Td>
              </tr>
            ))}
          </Table>
          <Pagination total={investorTotal} offset={investorOffset} limit={investorLimit} onPageChange={setInvestorOffset} onPageSizeChange={(n) => { setInvestorLimit(n); setInvestorOffset(0); }} />
          </>
        )}
      </div>
      </>)}

      {tab === "funds" && (<>
      {fundsError && <ErrorNote message={fundsError} />}
      <div>
        {funds === null ? (
          <Loading />
        ) : (
          funds.length ? (
            <>
            <Table head={["Date", "Fund or manager", "Stage", "Size", "LPs / anchors"]}>
              {funds.map((f) => (
                <tr key={f.id}>
                  <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{f.announced ?? ""}</Td>
                  <Td>
                    <Link href={`/deals/${f.id}`} className="hover:underline">
                      {f.fund_or_manager}
                    </Link>
                    <span className="block text-[0.75rem] text-[color:var(--dim)]">{f.headline}</span>
                  </Td>
                  <Td>{words(f.stage)}</Td>
                  <Td className="whitespace-nowrap">{usd(f.amount_usd)}</Td>
                  <Td className="text-[color:var(--muted)]">{f.lps.join(", ") || "Not disclosed"}</Td>
                </tr>
              ))}
            </Table>
            <Pagination total={fundTotal} offset={fundOffset} limit={fundLimit} onPageChange={setFundOffset} onPageSizeChange={(n) => { setFundLimit(n); setFundOffset(0); }} />
            </>
          ) : <p className="text-sm text-[color:var(--muted)]">No fund raises or closes recorded.</p>
        )}
      </div>
      </>)}
    </Container>
  );
}
