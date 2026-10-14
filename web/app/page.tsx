import { Attribution } from "../components/Attribution";
import { Behaviours } from "../components/Behaviours";
import { FinalCta, SiteFooter } from "../components/Closing";
import { Coverage } from "../components/Coverage";
import { Example } from "../components/Example";
import { Faq } from "../components/Faq";
import { Hero } from "../components/Hero";
import { Limits } from "../components/Limits";
import { MarketPulse } from "../components/MarketPulse";
import { Pipeline } from "../components/Pipeline";
import { Platform } from "../components/Platform";
import { Problem } from "../components/Problem";
import { Scoring } from "../components/Scoring";
import { Signals } from "../components/Signals";
import { SiteNav } from "../components/SiteNav";
import { SourceMarquee } from "../components/SourceMarquee";
import { Trust } from "../components/Trust";
import { getPulse, getShowcase } from "../lib/pulse";

// Re-render from the live feed every 30 minutes (see lib/pulse.ts).
export const revalidate = 1800;

export default async function LandingPage() {
  const [pulse, showcase] = await Promise.all([getPulse(), getShowcase()]);
  return (
    <div className="relative">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-full focus:bg-bone focus:px-4 focus:py-2 focus:text-ink"
      >
        Skip to content
      </a>
      <SiteNav />
      <main id="main">
        <Hero pulse={pulse} brief={showcase?.hero ?? null} />
        <SourceMarquee />
        <Platform pulse={pulse} />
        <MarketPulse pulse={pulse} />
        <Problem />
        <Pipeline />
        <Attribution />
        <Signals />
        <Coverage />
        <Scoring pulse={pulse} />
        <Example brief={showcase?.example ?? showcase?.hero ?? null} />
        <Trust />
        <Limits />
        <Faq />
        <FinalCta />
      </main>
      <SiteFooter />
      <Behaviours />
    </div>
  );
}
