import type { ReactNode } from "react";
import { SiteFooter } from "./Closing";
import { SiteNav } from "./SiteNav";

export function PublicPage({ children }: { children: ReactNode }) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-full focus:bg-bone focus:px-4 focus:py-2 focus:text-ink"
      >
        Skip to content
      </a>
      <SiteNav />
      <main id="main" className="min-h-screen">{children}</main>
      <SiteFooter />
    </>
  );
}
