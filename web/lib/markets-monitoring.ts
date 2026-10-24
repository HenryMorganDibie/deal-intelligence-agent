export type MonitoringHolding = {
  id: string;
  name: string;
  ticker: string;
  country?: string;
};

export type MonitoringEvent = {
  id: string;
  day: string | null;
  headline: string;
  publisher: string | null;
  url: string | null;
  signal_type: string | null;
  direction: string | null;
  country: string | null;
  sector: string | null;
};

export type PortfolioEventMatch = {
  event: MonitoringEvent;
  holdings: { id: string; name: string; ticker: string; reason: "ticker" | "company name" }[];
};

function normalise(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function hasExactToken(haystack: string, token: string): boolean {
  if (!token) return false;
  return ` ${normalise(haystack)} `.includes(` ${token} `);
}

function tickerAppears(headline: string, ticker: string): boolean {
  const symbol = ticker.trim().toUpperCase();
  if (symbol.length < 3 || !/^[A-Z0-9.-]+$/.test(symbol)) return false;
  const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^A-Z0-9])${escaped}($|[^A-Z0-9])`, "i").test(headline);
}

export function matchPortfolioEvents(
  holdings: readonly MonitoringHolding[],
  events: readonly MonitoringEvent[],
): PortfolioEventMatch[] {
  const matches: PortfolioEventMatch[] = [];
  for (const event of events) {
    const related = new Map<string, { id: string; name: string; ticker: string; reason: "ticker" | "company name" }>();
    for (const holding of holdings) {
      const tickerMatch = tickerAppears(event.headline, holding.ticker);
      const company = normalise(holding.name);
      const headline = normalise(event.headline);
      const nameMatch = company.length >= 7 && hasExactToken(headline, company);
      if (tickerMatch || nameMatch) {
        related.set(holding.id, {
          id: holding.id,
          name: holding.name,
          ticker: holding.ticker,
          reason: tickerMatch ? "ticker" : "company name",
        });
      }
    }
    if (related.size) {
      matches.push({ event, holdings: [...related.values()] });
    }
  }
  return matches.sort((a, b) => {
    const dateA = a.event.day ? Date.parse(a.event.day) : 0;
    const dateB = b.event.day ? Date.parse(b.event.day) : 0;
    return dateB - dateA;
  });
}
