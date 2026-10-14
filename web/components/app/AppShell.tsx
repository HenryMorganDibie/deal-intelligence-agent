"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LINKS } from "../../lib/site";
import { Container, GitHubMark, LogoMark } from "../primitives";

const NAV: [string, string][] = [
  ["/app", "Briefs"],
  ["/app/research", "Research"],
  ["/app/deals", "Deals"],
  ["/app/investors", "Investors"],
  ["/app/companies", "Companies"],
  ["/app/countries", "Countries"],
  ["/app/watchlists", "Alerts"],
  ["/app/coverage", "Coverage"],
  ["/app/evaluation", "Evaluation"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
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
          <a href={LINKS.github} target="_blank" rel="noreferrer" className="btn btn-ghost h-8 shrink-0 px-3 text-[0.8125rem]">
            <GitHubMark />
            <span className="hidden sm:inline">Open source</span>
          </a>
        </Container>
      </header>
      <main id="main">{children}</main>
    </>
  );
}
