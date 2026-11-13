"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const TABS: [string, string][] = [
  ["/app/markets", "Overview"],
  ["/app/markets/screener", "Screener"],
  ["/app/markets/investments", "Funds & fixed income"],
  ["/app/markets/compare", "Compare"],
  ["/app/markets/valuation", "Valuation"],
  ["/app/markets/portfolio", "Portfolio"],
  ["/app/markets/monitoring", "Monitoring"],
];

/** The Markets section's menu, the same on every Markets page. */
export function MarketsNav() {
  const path = usePathname() ?? "";
  const active = (href: string) => (href === "/app/markets" ? path === href : path.startsWith(href));
  return (
    <nav aria-label="Markets" className="-mx-1 flex gap-5 overflow-x-auto border-b hairline px-1">
      {TABS.map(([href, label]) => (
        <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`-mb-px shrink-0 border-b-2 pb-2.5 pt-1 text-[0.875rem] transition-colors ${
                active(href) ? "border-[color:var(--text)] text-[color:var(--text)]" : "border-transparent text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}

/** A Markets page's title and one line on what it does. */
export function MarketsTitle({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="h2 text-[1.5rem] sm:text-[1.75rem]">{title}</h1>
        {children && <p className="mt-1.5 max-w-3xl text-[0.875rem] text-[color:var(--muted)]">{children}</p>}
      </div>
      {actions}
    </header>
  );
}
