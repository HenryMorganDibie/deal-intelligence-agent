/**
 * Public site configuration.
 *
 * Every link points at something that exists today (the public repository and
 * its documents). Destinations that are not published yet are read from the
 * environment and render as "Soon" rather than pointing at a page that 404s.
 */

function env(value: string | undefined): string | undefined {
  const v = value?.trim();
  return v ? v : undefined;
}

const REPO = "https://github.com/HenryMorganDibie/deal-intelligence-agent";

export const SITE = {
  title: "Deal Intelligence Agent | Deal signals you can audit",
  description:
    "An open-source deal intelligence system for US and African markets. A deterministic rule engine finds the signals in SEC filings, exchange disclosures and the financial press; an LLM explains them and can never invent one.",
  url: env(process.env.NEXT_PUBLIC_SITE_URL),
} as const;

export const LINKS = {
  github: REPO,
  readme: `${REPO}#readme`,
  architecture: `${REPO}/blob/main/ARCHITECTURE.md`,
  limitations: `${REPO}/blob/main/ARCHITECTURE.md#honest-limitations`,
  issues: `${REPO}/issues`,
  contact: env(process.env.NEXT_PUBLIC_CONTACT_URL),
} as const;
