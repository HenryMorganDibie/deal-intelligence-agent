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

/** Nigeria's 36 states and the FCT, as the election news is tagged. */
export const NG_STATES = [
  "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River", "Delta", "Ebonyi",
  "Edo", "Ekiti", "Enugu", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos",
  "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara", "FCT",
];

/** Incident types the alerts can filter on, with plain labels. */
export const INCIDENT_TYPES: [string, string][] = [
  ["violence", "Violence"], ["thuggery", "Thuggery"], ["abduction", "Abduction"], ["arson", "Arson"],
  ["ballot_snatching", "Ballot snatching"], ["vote_buying", "Vote buying"], ["intimidation", "Intimidation"],
  ["technology_failure", "BVAS or IReV failure"], ["logistics", "Logistics"], ["arrest", "Arrest"],
  ["hate_speech", "Hate speech"],
];
