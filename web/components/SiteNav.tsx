"use client";

import { useEffect, useState } from "react";
import { LINKS } from "../lib/site";
import { Container, GitHubMark, LogoMark } from "./primitives";

const NAV = [
  { href: "#platform", label: "Platform" },
  { href: "#pipeline", label: "How it works" },
  { href: "#attribution", label: "Attribution" },
  { href: "#coverage", label: "Coverage" },
  { href: "#example", label: "Example" },
  { href: "#limits", label: "Limits" },
];

export function SiteNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        scrolled || open ? "border-b hairline bg-[rgba(7,8,10,0.78)] backdrop-blur-xl" : "border-b border-transparent"
      }`}
    >
      <Container className="flex h-16 items-center justify-between">
        <a href="#top" className="flex items-center gap-2.5 text-[0.9375rem] font-medium tracking-tight">
          <LogoMark />
          <span>Deal Intelligence</span>
        </a>

        <nav aria-label="Primary" className="hidden items-center gap-7 md:flex">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="text-sm text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)]">
              {n.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <a href={LINKS.github} className="btn btn-ghost hidden h-9 px-3.5 text-sm sm:inline-flex" target="_blank" rel="noreferrer">
            <GitHubMark />
            GitHub
          </a>
          <a href="/app" className="btn btn-primary hidden h-9 px-3.5 text-sm sm:inline-flex">
            Open app
          </a>
          <button
            type="button"
            className="btn btn-ghost h-9 w-9 p-0 md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4" fill="none">
              {open ? (
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              ) : (
                <path d="M2.5 5h11M2.5 11h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
      </Container>

      {open && (
        <nav id="mobile-nav" aria-label="Mobile" className="border-t hairline md:hidden">
          <Container className="flex flex-col py-3">
            {NAV.map((n) => (
              <a
                key={n.href}
                href={n.href}
                onClick={() => setOpen(false)}
                className="py-3 text-[0.9375rem] text-[color:var(--muted)] hover:text-[color:var(--text)]"
              >
                {n.label}
              </a>
            ))}
            <div className="mt-2 flex gap-2 pb-2">
              <a href={LINKS.github} className="btn btn-ghost h-10 flex-1 text-sm" target="_blank" rel="noreferrer">
                <GitHubMark /> GitHub
              </a>
              <a href="/app" className="btn btn-primary h-10 flex-1 text-sm">
                Open app
              </a>
            </div>
          </Container>
        </nav>
      )}
    </header>
  );
}
