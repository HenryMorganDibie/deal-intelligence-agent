// Material changes between saved valuation estimates for the same holding, shown on Markets > Portfolio.
// (Portfolio event alerts are handled by Watchlists, which matches each company under its known names.)

function normalise(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
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
