"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "../../lib/market";
import { directoryHref, pct, price, tone, type Directory, type DirectoryRow } from "../../lib/markets-data";
import { usd, words } from "./ui";

// Name or ticker search over every company on record: listed shares and private companies.
export function MarketSearch({ placeholder = "Search any African company: listed or private, by name or ticker" }: { placeholder?: string }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DirectoryRow[] | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults(null);
      return;
    }
    let active = true;
    const t = setTimeout(() => {
      get<Directory>("/api/companies/directory", { q: term, limit: 10 })
        .then((r) => { if (active) setResults(r.rows); })
        .catch(() => { if (active) setResults([]); });
    }, 200);
    return () => { active = false; clearTimeout(t); };
  }, [q]);

  return (
    <div className="relative">
      <label className="sr-only" htmlFor="market-search">Search listed companies</label>
      <input
        id="market-search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="w-full rounded-xl border hairline bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-[color:var(--accent)]"
      />
      {results && (
        <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border hairline bg-[color:var(--bg)] shadow-xl">
          {results.length === 0 ? (
            <p className="p-3 text-sm text-[color:var(--muted)]">No company on record matches. Try another spelling, or <Link className="underline" href={`/app/companies?name=${encodeURIComponent(q)}`}>build a profile</Link> from public sources.</p>
          ) : (
            <ul>
              {results.map((r) => (
                <li key={`${r.kind}:${r.exchange ?? ""}:${r.symbol ?? r.name}`}>
                  <Link href={directoryHref(r)} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-white/[0.04]">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{r.name}</span>
                      <span className="text-xs text-[color:var(--dim)]">
                        {r.kind === "listed"
                          ? `${r.symbol} · ${r.exchange_name}${r.price == null ? " · no published price" : r.stale ? " · stale price" : r.delayed ? " · delayed intraday" : ""}`
                          : `Private · ${[r.country, r.sector, r.deal_count ? `${r.deal_count} deal${r.deal_count > 1 ? "s" : ""}` : null].filter(Boolean).join(" · ")}`}
                      </span>
                    </span>
                    <span className="shrink-0 text-right">
                      {r.kind === "listed" ? (
                        <>
                          <span className="block kbd">{r.price != null ? price(r.price, r.currency) : "n/a"}</span>
                          <span className={`text-xs ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</span>
                        </>
                      ) : (
                        <>
                          <span className="block kbd">{r.valuation_usd ? usd(r.valuation_usd) : usd((r.equity_raised_usd ?? 0) + (r.debt_raised_usd ?? 0))}</span>
                          <span className="text-xs text-[color:var(--dim)]">{r.valuation_usd ? "last valuation" : r.last_round ? words(r.last_round) : "raised"}</span>
                        </>
                      )}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
