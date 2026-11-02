import { createHash } from "node:crypto";

/**
 * Whether a password appears in a known data breach, using Have I Been Pwned's range API with k-anonymity: only the
 * first five characters of its SHA-1 hash leave the server, never the password or the full hash. Returns null when
 * the service cannot be reached, so an outage never blocks sign-up (the other password rules still apply).
 */
export async function passwordBreached(password: string): Promise<boolean | null> {
  const hash = createHash("sha1").update(password, "utf8").digest("hex").toUpperCase();
  const prefix = hash.slice(0, 5);
  const suffix = hash.slice(5);
  try {
    const response = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`, {
      headers: { "Add-Padding": "true", "User-Agent": "DealIntelligence-account-security" },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return null;
    const body = await response.text();
    return body.split("\n").some((line) => {
      const [candidate, count] = line.trim().split(":");
      return candidate === suffix && Number(count) > 0;
    });
  } catch {
    return null;
  }
}
