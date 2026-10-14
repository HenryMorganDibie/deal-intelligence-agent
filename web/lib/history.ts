import type { Severity } from "./brief";

/**
 * The visitor's own list of briefs, kept in this browser only (there are no
 * accounts). Briefs themselves live on the server and stay reachable by link.
 */
export type HistoryItem = {
  id: string;
  company: string;
  ticker: string | null;
  severity: Severity | null;
  signal_count: number;
  created_at: string;
};

const KEY = "deal-intel:briefs";
const MAX = 100;

export function readHistory(): HistoryItem[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const items = raw ? (JSON.parse(raw) as HistoryItem[]) : [];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

function write(items: HistoryItem[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX)));
  } catch {
    // Storage unavailable (private mode, quota): the list simply is not kept.
  }
}

export function addToHistory(item: HistoryItem) {
  write([item, ...readHistory().filter((h) => h.id !== item.id)]);
}

export function removeFromHistory(id: string) {
  write(readHistory().filter((h) => h.id !== id));
}
