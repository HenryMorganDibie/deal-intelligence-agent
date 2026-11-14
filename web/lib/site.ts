/**
 * Public site configuration.
 *
 * The site links only to its own pages. Requests go through the contact form (components/ContactForm.tsx), which
 * works without a mail app; the address is shown for anyone who prefers to write.
 */

function env(value: string | undefined): string | undefined {
  const v = value?.trim();
  return v ? v : undefined;
}

export const SITE = {
  title: "Deal Intelligence | Deal signals you can audit",
  description:
    "Deal intelligence for African markets: company signals, private-market deals, investors, financial statements and country risk across all 54 African countries. Rules find the facts; an LLM explains them and can never invent one.",
  url: env(process.env.NEXT_PUBLIC_SITE_URL),
} as const;

export const LINKS = {
  methodology: "/methodology",
  limitations: "/methodology#limits",
  evaluation: "/evaluation",
  contact: "/contact",
} as const;

export const CONTACT_EMAIL = env(process.env.NEXT_PUBLIC_CONTACT_EMAIL) ?? "info@deal-intelligence.app";


/** Topics of the contact form, with a hint for the message. Shared by the contact page (server) and the form. */
export type ContactTopic = "demo" | "pilot" | "data" | "institutional" | "election_alerts" | "election_coverage";

export const CONTACT_TOPICS: [ContactTopic, string, string][] = [
  ["demo", "Request a demonstration", "Markets or companies you would like to see, what you would use it for, and times that suit you (with time zone)."],
  ["pilot", "Discuss a pilot", "Your coverage universe (countries, sectors, companies), the data you rely on today, and what a successful pilot would show."],
  ["institutional", "Institutional plan or API volumes", "What you need (countries, elections, alerts, results, API volume) and when."],
  ["election_coverage", "Election coverage", "The country and election, and what you would want covered (incidents, news, results)."],
  ["data", "Methodology or data question", "Your question."],
];

export const REQUESTS = [
  {
    key: "demo",
    title: "Request a demonstration",
    body: "A 30-minute walkthrough on companies, countries or deals you choose, including how each figure is sourced and verified.",
    subject: "Deal Intelligence: demonstration request",
    template:
      "Name:\nOrganisation and role:\nMarkets or companies you would like to see:\nWhat you would use it for (deal sourcing, monitoring, research, risk):\nPreferred times (with time zone):\n",
  },
  {
    key: "pilot",
    title: "Discuss a pilot",
    body: "A scoped trial on your coverage universe: agreed companies, countries and deal types, success measures fixed in advance, and an evaluation report at the end.",
    subject: "Deal Intelligence: pilot discussion",
    template:
      "Name:\nOrganisation and role:\nCoverage universe (countries, sectors, companies):\nData you rely on today:\nWhat a successful pilot would show:\nTimeline:\n",
  },
  {
    key: "data",
    title: "Methodology or data questions",
    body: "Questions about the evaluation sets, labelling rules, coverage of a country, or access to the per-prediction files.",
    subject: "Deal Intelligence: methodology question",
    template: "Name:\nOrganisation:\nQuestion:\n",
  },
] as const;

/** Public base URL of the key-authenticated API, as customers call it. */
export const PUBLIC_API_BASE = `${(process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") || "https://api.deal-intelligence.app")}/v1`;
