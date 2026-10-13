import { Attribution } from "../components/Attribution";
import { Behaviours } from "../components/Behaviours";
import { FinalCta, SiteFooter } from "../components/Closing";
import { Coverage } from "../components/Coverage";
import { Example } from "../components/Example";
import { Faq } from "../components/Faq";
import { Hero } from "../components/Hero";
import { Limits } from "../components/Limits";
import { Pipeline } from "../components/Pipeline";
import { Problem } from "../components/Problem";
import { Quickstart } from "../components/Quickstart";
import { Scoring } from "../components/Scoring";
import { Signals } from "../components/Signals";
import { SiteNav } from "../components/SiteNav";
import { SourceMarquee } from "../components/SourceMarquee";
import { Trust } from "../components/Trust";

export default function LandingPage() {
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
        <Hero />
        <SourceMarquee />
        <Problem />
        <Pipeline />
        <Attribution />
        <Signals />
        <Coverage />
        <Scoring />
        <Example />
        <Trust />
        <Limits />
        <Quickstart />
        <Faq />
        <FinalCta />
      </main>
      <SiteFooter />
      <Behaviours />
    </div>
  );
}
