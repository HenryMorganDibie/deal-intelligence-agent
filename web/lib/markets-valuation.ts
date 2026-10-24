export function validHttpUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

export function validPastDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value &&
    parsed.getTime() <= Date.now();
}

export function calculateDcfPerShare(
  fcf: number,
  growthPct: number,
  discountPct: number,
  terminalPct: number,
  cash: number,
  debt: number,
  shares: number,
): number | null {
  if (![fcf, growthPct, discountPct, terminalPct, cash, debt, shares].every(Number.isFinite) ||
      fcf <= 0 || shares <= 0 || cash < 0 || debt < 0 ||
      growthPct <= -100 || growthPct > 100 ||
      discountPct <= 0 || discountPct > 60 ||
      terminalPct < -5 || terminalPct > 8 ||
      discountPct <= terminalPct) return null;

  const growth = growthPct / 100;
  const discount = discountPct / 100;
  const terminal = terminalPct / 100;
  let enterpriseValue = 0;
  let projected = fcf;
  for (let year = 1; year <= 5; year += 1) {
    projected *= 1 + growth;
    enterpriseValue += projected / Math.pow(1 + discount, year);
  }
  const terminalValue = projected * (1 + terminal) / (discount - terminal);
  enterpriseValue += terminalValue / Math.pow(1 + discount, 5);
  const equityValue = enterpriseValue + cash - debt;
  const perShare = equityValue / shares;
  return Number.isFinite(perShare) ? perShare : null;
}

export function calculateDdmPerShare(
  dividendPerShare: number,
  growthPct: number,
  discountPct: number,
  terminalPct: number,
): number | null {
  if (![dividendPerShare, growthPct, discountPct, terminalPct].every(Number.isFinite) ||
      dividendPerShare <= 0 || growthPct <= -100 || growthPct > 100 ||
      discountPct <= 0 || discountPct > 60 ||
      terminalPct < -5 || terminalPct > 8 ||
      discountPct <= terminalPct) return null;

  const growth = growthPct / 100;
  const discount = discountPct / 100;
  const terminal = terminalPct / 100;
  let projectedDividend = dividendPerShare;
  let value = 0;
  for (let year = 1; year <= 5; year += 1) {
    projectedDividend *= 1 + growth;
    value += projectedDividend / Math.pow(1 + discount, year);
  }
  const terminalValue = projectedDividend * (1 + terminal) / (discount - terminal);
  value += terminalValue / Math.pow(1 + discount, 5);
  return Number.isFinite(value) ? value : null;
}
