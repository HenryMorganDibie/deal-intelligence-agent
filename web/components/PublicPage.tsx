import type { ReactNode } from "react";
import { SiteFooter } from "./Closing";
import { SiteNav } from "./SiteNav";

export function PublicPage({ children }: { children: ReactNode }) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-[60] focus-visible:rounded-full focus-visible:bg-bone focus-visible:px-4 focus-visible:py-2 focus-visible:text-ink"
      >
        Skip to content
      </a>
      <SiteNav />
      <main id="main" className="min-h-screen">{children}</main>
      <SiteFooter />
    </>
  );
}
