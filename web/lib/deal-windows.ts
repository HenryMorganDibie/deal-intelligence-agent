import type { Deal } from "./market";
import { apiHeaders, apiUrl } from "./api-base";
import { shiftDay } from "./post-topics";

/* The deal windows the daily posts use: the roundup covers the day before and the day itself, widened to three
 * days when quiet (as the email drafts do); the week is the seven days before the given day. */

async function search(since: string, until: string, ms?: number): Promise<{ deals: Deal[]; total: number }> {
  try {
    const r = await fetch(apiUrl(`/api/deals?since=${since}&until=${until}&limit=100`), {
      headers: apiHeaders(), next: { revalidate: 3600 }, ...(ms ? { signal: AbortSignal.timeout(ms) } : {}) });
    if (!r.ok) return { deals: [], total: 0 };
    const j = (await r.json()) as { deals?: Deal[]; total_matching?: number };
    return { deals: j.deals ?? [], total: j.total_matching ?? (j.deals ?? []).length };
  } catch {
    return { deals: [], total: 0 };
  }
}

export async function roundupWindow(day: string, ms?: number): Promise<{ deals: Deal[]; label: string }> {
  const daily = await search(shiftDay(day, -1), day, ms);
  if (daily.deals.filter((d) => d.target).length >= 2) return { deals: daily.deals, label: "the last 24 hours" };
  return { deals: (await search(shiftDay(day, -3), day, ms)).deals, label: "the last three days" };
}

export async function weekWindow(day: string, ms?: number) {
  const start = shiftDay(day, -7), end = shiftDay(day, -1);
  const { deals, total } = await search(start, end, ms);
  return { deals, total, start, end };
}
