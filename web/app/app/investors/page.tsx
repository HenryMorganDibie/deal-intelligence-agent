"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Table, Td, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get, type InvestorRow } from "../../../lib/market";

type Fund = { id: string; fund_or_manager: string; stage: string; amount_usd: number | null; lps: string[]; announced: string | null; headline: string };
const ROLES = ["", "investor", "lender", "acquirer", "seller", "lp", "gp"];
const KINDS = ["", "dfi", "multilateral", "private_equity", "venture_capital", "growth", "sovereign", "pension", "bank", "accelerator"];

export default function InvestorsPage() {
  const [role, setRole] = useState("");
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState<InvestorRow[] | null>(null);
  const [funds, setFunds] = useState<Fund[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fundsError, setFundsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      setError(null);
      get<{ investors: InvestorRow[] }>("/api/investors", { role, kind, limit: 200 })
        .then((r) => { if (active) setRows(r.investors); })
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
  }, [role, kind]);

  useEffect(() => {
    let active = true;
    const load = () => {
      setFundsError(null);
      get<{ funds: Fund[] }>("/api/funds", { limit: 500 })
        .then((r) => { if (active) setFunds(r.funds); })
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
  }, []);

  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Investors and funds" title="Who is investing, lending, buying and raising.">
        Every party to a deal gets a role: equity investor, lender, acquirer, seller, limited partner (LP) or fund manager
        (GP). Known development finance institutions, private equity and venture firms are matched across their name
        variants.
      </PageHeader>
      <div className="flex flex-wrap gap-3">
        <select value={role} onChange={(e) => setRole(e.target.value)} className="field w-auto" aria-label="Role">
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r ? `Role: ${r.toUpperCase().length <= 2 ? r.toUpperCase() : words(r)}` : "All roles"}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="field w-auto" aria-label="Investor type">
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k ? words(k) : "All investor types"}
            </option>
          ))}
        </select>
      </div>
      {error && <ErrorNote message={error} />}
      <div className="mt-6">
        {rows === null ? (
          <Loading />
        ) : (
          <Table head={["Name", "Type", "Deals", "Roles", "Disclosed value", "Countries", "Last seen"]}>
            {rows.map((r) => (
              <tr key={r.name}>
                <Td>
                  <Link href={`/app/investors/${encodeURIComponent(r.name)}`} className="hover:underline">
                    {r.name}
                  </Link>
                  {r.hq && <span className="block text-[0.75rem] text-[color:var(--dim)]">{r.hq}</span>}
                </Td>
                <Td>{words(r.type) || "n/a"}</Td>
                <Td>{r.deal_count}</Td>
                <Td className="text-[color:var(--muted)]">{Object.entries(r.roles).map(([k, v]) => `${k} ${v}`).join(", ")}</Td>
                <Td className="whitespace-nowrap">{usd(r.disclosed_usd)}</Td>
                <Td className="text-[color:var(--muted)]">{Object.keys(r.countries).slice(0, 5).join(", ")}</Td>
                <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{r.last_seen ?? ""}</Td>
              </tr>
            ))}
          </Table>
        )}
      </div>

      <h2 className="eyebrow mt-12">Fund raises and closes (GP activity)</h2>
      {fundsError && <ErrorNote message={fundsError} />}
      <div className="mt-4">
        {funds === null ? (
          <Loading />
        ) : (
          funds.length ? (
            <Table head={["Date", "Fund or manager", "Stage", "Size", "LPs / anchors"]}>
              {funds.map((f) => (
                <tr key={f.id}>
                  <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{f.announced ?? ""}</Td>
                  <Td>
                    <Link href={`/app/deals/${f.id}`} className="hover:underline">
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
          ) : <p className="text-sm text-[color:var(--muted)]">No fund raises or closes recorded.</p>
        )}
      </div>
    </Container>
  );
}
