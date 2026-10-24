"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LINKS } from "../../lib/site";
import { Container, LogoMark } from "../primitives";

const NAV: [string, string][] = [
  ["/app", "Briefs"],
  ["/app/research", "Research"],
  ["/app/deals", "Deals"],
  ["/app/investors", "Investors"],
  ["/app/companies", "Companies"],
  ["/app/countries", "Countries"],
  ["/app/watchlists", "Alerts"],
];

const QUALITY_LINKS: [string, string][] = [
  ["/app/coverage", "Coverage"],
  ["/app/evaluation", "Evaluation"],
  [LINKS.methodology, "Methodology"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const qualityActive = QUALITY_LINKS.some(([href]) =>
    href === "/app" ? pathname === href : pathname.startsWith(href),
  );

  return (
    <>
      <header className="sticky top-0 z-40 border-b hairline bg-[rgba(7,8,10,0.85)] backdrop-blur-xl">
        <Container className="flex h-14 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-6">
            <Link href="/" className="flex shrink-0 items-center gap-2.5 text-[0.9375rem] font-medium tracking-tight">
              <LogoMark />
              <span className="hidden sm:inline">Deal Intelligence</span>
            </Link>
            <nav aria-label="App" className="-mx-1 flex min-w-0 gap-4 overflow-x-auto px-1 [scrollbar-width:none]">
              {NAV.map(([href, label]) => {
                const active = href === "/app" ? pathname === "/app" || pathname.startsWith("/app/briefs") : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`whitespace-nowrap text-sm transition-colors ${
                      active ? "text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <details className="relative shrink-0">
            <summary
              className={`btn btn-ghost flex h-8 cursor-pointer list-none items-center gap-2 px-3 text-[0.8125rem] [&::-webkit-details-marker]:hidden ${
                qualityActive ? "text-[color:var(--text)]" : ""
              }`}
              aria-label="Open Data and Quality menu"
            >
              Data &amp; Quality
              <span aria-hidden="true" className="text-xs">⌄</span>
            </summary>
            <nav
              aria-label="Data and quality"
              className="absolute right-0 top-full mt-2 w-52 rounded-xl border hairline bg-[rgba(12,14,17,0.98)] p-2 shadow-xl"
            >
              {QUALITY_LINKS.map(([href, label]) => {
                const active = pathname === href || (href !== "/methodology" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-white/[0.06] text-[color:var(--text)]"
                        : "text-[color:var(--muted)] hover:bg-white/[0.04] hover:text-[color:var(--text)]"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </details>
        </Container>
      </header>
      <main id="main">{children}</main>
    </>
  );
}
