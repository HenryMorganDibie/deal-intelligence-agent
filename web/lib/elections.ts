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

/** Upcoming national elections in Africa, for the Alerts page. Official dates only (Angola: month expected). Checked
 * 13 November 2026 against electoral commissions' timetables as compiled by PollsAfrica and Wikipedia's list of
 * 2027 elections. `key` matches an election we monitor (src/election_alerts.py ELECTIONS, built from
 * src/data/election_profiles.py); others are on request.
 * Past entries drop off by themselves. */
export type UpcomingElection = { country: string; kind: string; date: string; label: string; key?: string };
export const UPCOMING_AFRICA: UpcomingElection[] = [
  { country: "Cabo Verde", kind: "Presidential", date: "2026-11-15", label: "15 November 2026" },
  { country: "The Gambia", kind: "Presidential", date: "2026-12-05", label: "5 December 2026", key: "gm-2026" },
  { country: "South Sudan", kind: "General", date: "2026-12-22", label: "22 December 2026", key: "ss-2026" },
  { country: "Nigeria", kind: "General (presidential and National Assembly)", date: "2027-01-16", label: "16 January 2027", key: "ng-2027" },
  { country: "Nigeria", kind: "Governorship and state assembly", date: "2027-02-06", label: "6 February 2027", key: "ng-2027" },
  { country: "The Gambia", kind: "Parliamentary", date: "2027-04-10", label: "10 April 2027", key: "gm-2026" },
  { country: "Kenya", kind: "General", date: "2027-08-10", label: "10 August 2027", key: "ke-2027" },
  { country: "Angola", kind: "General", date: "2027-08-31", label: "August 2027 (expected)" },
];
