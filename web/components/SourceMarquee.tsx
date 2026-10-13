import { Container } from "./primitives";

const SOURCES = [
  "SEC EDGAR",
  "Form 8-K item codes",
  "Form 4 open-market trades",
  "Schedule 13D",
  "NGX disclosures",
  "NSE Kenya documents",
  "JSE SENS",
  "Reuters",
  "Bloomberg",
  "Financial Times",
  "BusinessDay Nigeria",
  "Moneyweb",
  "Nation Africa",
  "TechCabal",
  "AVCA",
  "IFC",
  "49 African news feeds",
  "48 private-capital sources",
];

export function SourceMarquee() {
  const row = [...SOURCES, ...SOURCES];
  return (
    <div className="border-y hairline bg-[color:var(--raised)] py-5">
      <Container>
        <p className="eyebrow mb-4 text-center">Read every run, credited by publisher</p>
      </Container>
      <div className="marquee overflow-hidden" aria-label="Data sources">
        <ul className="marquee-track flex w-max gap-10 whitespace-nowrap">
          {row.map((s, i) => (
            <li key={`${s}-${i}`} aria-hidden={i >= SOURCES.length} className="kbd text-[0.8125rem] text-[color:var(--muted)]">
              <span className="mr-10 text-white/15">/</span>
              {s}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
