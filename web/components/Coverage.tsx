import { Container, Heading, Reveal, Section } from "./primitives";

type Feed = { name: string; what: string; depth: string };

const US: Feed[] = [
  { name: "SEC EDGAR · 8-K", what: "Item codes expanded and mapped: bankruptcy, change of control, departures, restatements", depth: "Full window" },
  { name: "SEC EDGAR · Form 4", what: "Every filing read; only open-market purchases and $1M+ sales outside 10b5-1 plans kept", depth: "Full window" },
  { name: "SEC EDGAR · 10-K, 10-Q, 13D, proxy", what: "The company's own filings, fetched by its CIK", depth: "Full window" },
  { name: "Global press", what: "Google News and Yahoo Finance, credited to the real publisher", depth: "Full window" },
];

const AFRICA: Feed[] = [
  { name: "NGX · Nigeria", what: "The exchange's corporate-disclosure library, queried by symbol", depth: "Full window" },
  { name: "NSE Kenya", what: "Listed-company documents from the exchange's own library", depth: "Full window" },
  { name: "JSE SENS · South Africa", what: "Announcements by JSE code via Sharenet", depth: "Current day" },
  { name: "African press + private capital", what: "49 news feeds and 48 PE, DFI and regulator sources", depth: "Full window" },
];

function FeedList({ title, region, feeds }: { title: string; region: string; feeds: Feed[] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b hairline px-6 py-4">
        <h3 className="h3">{title}</h3>
        <span className="eyebrow">{region}</span>
      </div>
      <ul>
        {feeds.map((f, i) => (
          <li key={f.name} className={`grid gap-1 px-6 py-4 sm:grid-cols-[1fr_auto] sm:gap-6 ${i ? "border-t hairline" : ""}`}>
            <div>
              <p className="text-[0.9375rem] font-medium">{f.name}</p>
              <p className="mt-1 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">{f.what}</p>
            </div>
            <span
              className={`kbd self-start text-[0.6875rem] uppercase tracking-[0.12em] ${
                f.depth === "Full window" ? "text-verified" : "text-[color:var(--muted)]"
              }`}
            >
              {f.depth}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Coverage() {
  return (
    <Section id="coverage" labelledBy="coverage-title">
      <Container>
        <Heading
          index="05"
          eyebrow="Coverage"
          id="coverage-title"
          title={
            <>
              Built for US and African markets,{" "}
              <span className="text-[color:var(--muted)]">from the exchanges&apos; own records.</span>
            </>
          }
          lede="Official disclosures count as filings at full credibility. Anything found through news search stays news, credited to its publisher. Every source must fall inside the lookback window you ask for."
        />
        <div className="mt-14 grid gap-4 lg:grid-cols-2">
          <Reveal>
            <FeedList title="United States" region="SEC + press" feeds={US} />
          </Reveal>
          <Reveal delay={100}>
            <FeedList title="Africa" region="NGX · NSE · JSE" feeds={AFRICA} />
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
