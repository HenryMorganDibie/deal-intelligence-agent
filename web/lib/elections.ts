/* Elections investors watch for a change in policy, the currency and deal timing. Mirrors ELECTIONS in
 * src/engines/market_briefing.py, so a post and the page it links to count down the same way. INEC's revised
 * timetable: presidential and National Assembly on 16 January 2027, governorship on 6 February. */

export type Election = { country: string; name: string; kind: string; day: string; currency: string; exchange: string };
export const ELECTIONS: Election[] = [
  { country: "NG", name: "Nigeria", kind: "general election", day: "2027-01-16", currency: "NGN", exchange: "ngx" },
];
const LEAD_DAYS = 120;
const AFTER_DAYS = 30;

export type ElectionNow = Election & { days: number; when: string; hook: string; countdown: string };

/** The election in its window around `day` (YYYY-MM-DD), with the same wording as the posts, or null. */
export function electionOn(day: string | null | undefined): ElectionNow | null {
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  for (const e of ELECTIONS) {
    const days = Math.round((Date.parse(`${e.day}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / 86_400_000);
    if (Number.isNaN(days) || days > LEAD_DAYS || days < -AFTER_DAYS) continue;
    const when = new Date(`${e.day}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    const hook = days > 1 ? `${days} days to ${e.name}'s ${e.kind}` : days === 1 ? `${e.name}'s ${e.kind} is tomorrow`
      : days === 0 ? `${e.name} votes today` : `${-days} day${days < -1 ? "s" : ""} after ${e.name}'s ${e.kind}`;
    const countdown = days > 1 ? `${days} days to go` : days === 1 ? "polling day tomorrow" : days === 0 ? "polling day"
      : `${-days} day${days < -1 ? "s" : ""} after the vote`;
    return { ...e, days, when, hook, countdown };
  }
  return null;
}
