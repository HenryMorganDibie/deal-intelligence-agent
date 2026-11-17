// The link between the browser-stored portfolio and the alerts watchlist made from it. Only the watchlist id and the
// company names last sent to it are kept here; quantities and prices never leave the portfolio.

export const ALERTS_LINK_KEY = "deal-intelligence-markets-alerts-link-v1";

export type AlertsLink = { watchlistId: string; synced: string[] };

const key = (name: string) => name.trim().toLowerCase();

/** Holding names once each, in portfolio order, ignoring case and blanks. */
export function uniqueNames(names: readonly string[]): string[] {
  const seen = new Map<string, string>();
  for (const n of names) {
    const t = n.trim();
    if (t && !seen.has(key(t))) seen.set(key(t), t);
  }
  return [...seen.values()];
}

/** What the watchlist needs so that it follows the current holdings: names to add and names the portfolio added
 * earlier but no longer holds. Names typed into the watchlist by hand are never in `synced`, so never removed. */
export function alertsDiff(current: readonly string[], synced: readonly string[]): { add: string[]; remove: string[] } {
  const now = uniqueNames(current);
  const before = uniqueNames(synced);
  const nowKeys = new Set(now.map(key));
  const beforeKeys = new Set(before.map(key));
  return { add: now.filter((n) => !beforeKeys.has(key(n))), remove: before.filter((n) => !nowKeys.has(key(n))) };
}

export function parseAlertsLink(raw: string | null): AlertsLink | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<AlertsLink>;
    if (typeof v.watchlistId !== "string" || !/^[0-9a-f-]{36}$/i.test(v.watchlistId)) return null;
    if (!Array.isArray(v.synced) || !v.synced.every((s) => typeof s === "string")) return null;
    return { watchlistId: v.watchlistId, synced: v.synced };
  } catch {
    return null;
  }
}

export function readAlertsLink(): AlertsLink | null {
  try { return parseAlertsLink(window.localStorage.getItem(ALERTS_LINK_KEY)); } catch { return null; }
}

export function writeAlertsLink(link: AlertsLink | null): void {
  try {
    if (link) window.localStorage.setItem(ALERTS_LINK_KEY, JSON.stringify(link));
    else window.localStorage.removeItem(ALERTS_LINK_KEY);
  } catch { /* storage blocked: the link is a convenience, alerts still work */ }
}
