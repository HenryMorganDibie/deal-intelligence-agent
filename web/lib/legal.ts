/**
 * The business details the legal pages and footers show, from the environment so they are set once in Vercel.
 *
 * NEXT_PUBLIC_BUSINESS_POSTAL_ADDRESS: where the business receives post (a P.O. box is acceptable). Shown on the
 *   Terms, Privacy and Copyright pages; the API's BUSINESS_POSTAL_ADDRESS carries the same value into alert emails.
 * NEXT_PUBLIC_DMCA_AGENT_NAME / _EMAIL / _PHONE: the copyright agent designated with the US Copyright Office. The
 *   agent may be named by role; the email falls back to the general contact address.
 */
import { CONTACT_EMAIL } from "./site";

function env(value: string | undefined): string | undefined {
  const v = value?.replace(/\s+/g, " ").trim();
  return v ? v : undefined;
}

export const MINIMUM_AGE = 18;
export const LEGAL_UPDATED = "17 November 2026";
/** Recorded with each new account, so the terms an account agreed to can be traced. */
export const TERMS_VERSION = "2026-11-17";

export const BUSINESS = {
  name: "Deal Intelligence",
  postalAddress: env(process.env.NEXT_PUBLIC_BUSINESS_POSTAL_ADDRESS),
  email: CONTACT_EMAIL,
} as const;

export const DMCA_AGENT = {
  name: env(process.env.NEXT_PUBLIC_DMCA_AGENT_NAME) ?? "Copyright Agent, Deal Intelligence",
  email: env(process.env.NEXT_PUBLIC_DMCA_EMAIL) ?? CONTACT_EMAIL,
  phone: env(process.env.NEXT_PUBLIC_DMCA_PHONE),
  postalAddress: env(process.env.NEXT_PUBLIC_BUSINESS_POSTAL_ADDRESS),
} as const;

/** The renewal terms shown beside every subscribe button: price, period, how to cancel and what happens then. */
export function renewalTerms(price: string, yearly: boolean): string {
  return `Renews automatically every ${yearly ? "year" : "month"} at ${price} until you cancel. Cancel any time in Plan and billing; you keep access until the end of the period you paid for.`;
}
