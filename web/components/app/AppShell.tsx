"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { LINKS } from "../../lib/site";
import { Container, LogoMark } from "../primitives";
import { AccountMenu } from "./AccountMenu";
import { ThemeToggle } from "../ThemeToggle";

// Deals first: it is where "Open app" lands and what a first visit should see. Briefs and research, which run
// the language model, follow the live data.
const NAV: [string, string][] = [
  ["/app/deals", "Deals"],
  ["/app/markets", "Markets"],
  ["/app/investors", "Investors"],
  ["/app/companies", "Companies"],
  ["/app/countries", "Countries"],
  ["/app", "Briefs"],
  ["/app/research", "Research"],
  ["/app/watchlists", "Alerts"],
];

// Line icons for the phone tab bar (24px grid, drawn with currentColor).
const ICONS: Record<string, ReactNode> = {
  "/app": <><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 13h6M10 17h6" /></>,
  "/app/research": <><circle cx="11" cy="11" r="6" /><path d="m20 20-4.5-4.5" /></>,
  "/app/markets": <><path d="M4 19h16" /><path d="m5 15 4-4 3 3 6-7" /><path d="M15 7h3v3" /></>,
  "/app/deals": <><path d="M7 7h11l-3-3M17 17H6l3 3" /></>,
  "/app/investors": <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 5.5a3 3 0 0 1 0 5.5M17.5 14a5.5 5.5 0 0 1 3 5" /></>,
  "/app/companies": <><path d="M4 21V5l8-2v18M12 9l8 2v10M3 21h18" /><path d="M7.5 8h1M7.5 12h1M7.5 16h1M15.5 14h1M15.5 17.5h1" /></>,
  "/app/countries": <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
  "/app/watchlists": <><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
};

const isActive = (pathname: string, href: string) =>
  href === "/app" ? pathname === "/app" || pathname.startsWith("/app/briefs") : pathname.startsWith(href);

/** Phone navigation: a bottom tab bar within thumb reach that slides sideways to show every section. */
function MobileTabs({ pathname }: { pathname: string }) {
  const bar = useRef<HTMLUListElement>(null);
  useEffect(() => {
    // Keep the current section in view when it sits beyond the visible tabs.
    bar.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [pathname]);
  return (
    <nav
      aria-label="App sections"
      className="fixed inset-x-0 bottom-0 z-40 border-t hairline bg-ink/[0.97] backdrop-blur-xl md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="relative">
        <ul ref={bar} className="flex snap-x snap-mandatory overflow-x-auto overscroll-x-contain px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {NAV.map(([href, label]) => {
            const active = isActive(pathname, href);
            return (
              <li key={href} className="shrink-0 snap-start">
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex h-16 w-[5.4rem] flex-col items-center justify-center gap-1 text-[0.6875rem] transition-colors ${
                    active ? "text-[color:var(--text)]" : "text-[color:var(--muted)]"
                  }`}
                >
                  <span className={`grid h-7 w-12 place-items-center rounded-full transition-colors ${active ? "bg-verified/15 text-verified" : ""}`}>
                    <svg aria-hidden viewBox="0 0 24 24" className="h-[1.3rem] w-[1.3rem]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      {ICONS[href]}
                    </svg>
                  </span>
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
        {/* A soft edge says there is more to slide to. */}
        <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-ink to-transparent" />
      </div>
    </nav>
  );
}

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
      <header className="sticky top-0 z-40 border-b hairline bg-ink/85 backdrop-blur-xl">
        <Container className="flex h-14 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-6">
            <Link href="/" className="flex shrink-0 items-center gap-2.5 text-[0.9375rem] font-medium tracking-tight">
              <LogoMark />
              <span className="hidden sm:inline">Deal Intelligence</span>
            </Link>
            <nav aria-label="App" className="-mx-1 hidden min-w-0 gap-4 overflow-x-auto px-1 [scrollbar-width:none] md:flex">
              {NAV.map(([href, label]) => {
                const active = isActive(pathname, href);
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
          <div className="flex shrink-0 items-center gap-2">
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
                className="absolute right-0 top-full mt-2 w-52 rounded-xl border hairline bg-raised/[0.98] p-2 shadow-xl"
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
            <ThemeToggle />
            <AccountMenu />
          </div>
        </Container>
      </header>
      <main id="main" className="pb-[calc(4rem+env(safe-area-inset-bottom))] md:pb-0">{children}</main>
      <MobileTabs pathname={pathname} />
    </>
  );
}
