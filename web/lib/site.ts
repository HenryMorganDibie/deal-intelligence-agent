/**
 * Public site configuration.
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

export const CONTACT_EMAIL = env(process.env.NEXT_PUBLIC_CONTACT_EMAIL) ?? "info@deal-intelligence.app";
