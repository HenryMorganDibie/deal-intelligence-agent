"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "../../lib/market";
import { companyHref, pct, price, tone, type Quote } from "../../lib/markets-data";

// Name or ticker search over every listed share in the latest snapshot.
export function MarketSearch({ placeholder = "Search 1,200+ listed companies by name or ticker" }: { placeholder?: string }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Quote[] | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults(null);
      return;
    }
    let active = true;
    const t = setTimeout(() => {
      get<{ results: Quote[] }>("/api/markets/search", { q: term, limit: 8 })
        .then((r) => { if (active) setResults(r.results); })
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
            <p className="p-3 text-sm text-[color:var(--muted)]">No listed company matches. Private companies are in <Link className="underline" href={`/app/deals?q=${encodeURIComponent(q)}`}>deals</Link>.</p>
          ) : (
            <ul>
              {results.map((r) => (
                <li key={`${r.exchange}:${r.symbol}`}>
                  <Link href={companyHref(r)} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-white/[0.04]">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{r.name}</span>
                      <span className="text-xs text-[color:var(--dim)]">{r.symbol} · {r.exchange_name}{r.stale ? " · stale price" : ""}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block kbd">{price(r.price, r.currency)}</span>
                      <span className={`text-xs ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</span>
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
