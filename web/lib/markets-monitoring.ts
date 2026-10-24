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

export type ValuationChangeAlert = {
  company: string;
  ticker: string;
  country: string;
  method: "dcf" | "ddm";
  previousBasePerShare: number;
  currentBasePerShare: number;
  changePct: number;
  previousCalculatedAt: string;
  calculatedAt: string;
  previousStatementPeriod: string;
  statementPeriod: string;
  statementSourceUrl: string;
  quoteSourceUrl: string | null;
  quotePrice: number | null;
  currency: string;
};

export function calculateValuationChangeAlerts(
  snapshots: readonly import("./markets-portfolio").SavedValuationSnapshot[],
  thresholdPct = 10,
): ValuationChangeAlert[] {
  const byIssuer = new Map<string, import("./markets-portfolio").SavedValuationSnapshot[]>();
  for (const snapshot of snapshots) {
    const country = (snapshot.country ?? "").trim().toLowerCase();
    if (!country) continue;
    const identifier = snapshot.ticker.trim().toUpperCase() || normalise(snapshot.company);
    if (!identifier) continue;
    const key = `${country}|${identifier}`;
    const group = byIssuer.get(key) ?? [];
    group.push(snapshot);
    byIssuer.set(key, group);
  }

  const alerts: ValuationChangeAlert[] = [];
  for (const history of byIssuer.values()) {
    const ordered = [...history].sort((a, b) => Date.parse(a.calculatedAt) - Date.parse(b.calculatedAt));
    if (ordered.length < 2) continue;
    const previous = ordered[ordered.length - 2];
    const current = ordered[ordered.length - 1];
    if (previous.method !== current.method || previous.currency !== current.currency ||
        previous.basePerShare <= 0 || current.basePerShare <= 0) continue;
    const changePct = (current.basePerShare / previous.basePerShare - 1) * 100;
    if (!Number.isFinite(changePct) || Math.abs(changePct) < thresholdPct) continue;
    alerts.push({
      company: current.company,
      ticker: current.ticker,
      country: current.country ?? "",
      method: current.method,
      previousBasePerShare: previous.basePerShare,
      currentBasePerShare: current.basePerShare,
      changePct,
      previousCalculatedAt: previous.calculatedAt,
      calculatedAt: current.calculatedAt,
      previousStatementPeriod: previous.statementPeriod,
      statementPeriod: current.statementPeriod,
      statementSourceUrl: current.statementSourceUrl,
      quoteSourceUrl: current.quoteSourceUrl,
      quotePrice: current.quotePrice,
      currency: current.currency,
    });
  }
  return alerts.sort((a, b) => Date.parse(b.calculatedAt) - Date.parse(a.calculatedAt));
}
