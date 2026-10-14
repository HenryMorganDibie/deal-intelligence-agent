/**
 * Public site configuration.
 *
 * The site links only to its own pages, plus a direct email route for demos and pilots.
 */

function env(value: string | undefined): string | undefined {
  const v = value?.trim();
  return v ? v : undefined;
}

export const SITE = {
  title: "Deal Intelligence | Deal signals you can audit",
  description:
    "Deal intelligence for African and US markets: company signals, private-market deals, investors, financial statements and country risk across all 54 African countries. Rules find the facts; an LLM explains them and can never invent one.",
  url: env(process.env.NEXT_PUBLIC_SITE_URL),
} as const;

export const LINKS = {
  methodology: "/methodology",
  limitations: "/methodology#limits",
  evaluation: "/app/evaluation",
  contact: "/contact",
} as const;

export const CONTACT_EMAIL = env(process.env.NEXT_PUBLIC_CONTACT_EMAIL) ?? "henrymorgandibie@gmail.com";

/** A mailto link with a subject and a short template, so a request arrives with what is needed to answer it. */
export function mailto(subject: string, body: string): string {
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

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
