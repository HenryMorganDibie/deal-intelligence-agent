/**
 * The one-line summary of a deal on the public deals page ("raised $5m from X", "acquired by Y").
 *
 * The wording follows the deal's stage, so a report of talks never reads as a done deal: "rumoured" is talks or
 * consideration, "announced" is agreed or under way, "completed" is closed.
 */
export type DealLineInput = {
  deal_type: string;
  stage: string | null;
  amount_usd: number | null;
  investors: string[];
  buyer: string | null;
  seller: string | null;
};

export function dealLine(d: DealLineInput, money: (v: number) => string): string {
  const amount = d.amount_usd ? money(d.amount_usd) : null;
  const who = d.investors.slice(0, 2).join(", ");
  const stage = d.stage === "rumoured" || d.stage === "completed" ? d.stage : "announced";
  const by = (name: string | null) => (name ? ` by ${name}` : "");
  const forAmount = amount ? ` for ${amount}` : "";
  switch (d.deal_type) {
    case "equity_funding":
      if (stage === "rumoured") return `in talks to raise ${amount ?? "funding"}${who ? ` from ${who}` : ""}`;
      return `raised ${amount ?? "new funding"}${who ? ` from ${who}` : ""}`;
    case "debt_financing":
      if (stage === "rumoured") return `seeking ${amount ? `${amount} in ` : ""}debt financing${who ? ` from ${who}` : ""}`;
      return `secured ${amount ? `${amount} in ` : ""}debt financing${who ? ` from ${who}` : ""}`;
    case "acquisition":
      if (stage === "rumoured") return `in talks to be acquired${by(d.buyer)}${forAmount}`;
      if (stage === "announced") return `to be acquired${by(d.buyer)}${forAmount}`;
      return `acquired${by(d.buyer)}${forAmount}`;
    case "exit":
      if (stage === "rumoured") return `stake could be sold${by(d.seller)}${forAmount}`;
      if (stage === "announced") return `stake to be sold${by(d.seller)}${forAmount}`;
      return `stake sold${by(d.seller)}${forAmount}`;
    case "fund_raise":
      if (stage === "completed") return `closed ${amount ? `${amount} ` : ""}in commitments`;
      return `raising ${amount ? `${amount} for ` : ""}a fund`;
    case "ipo":
      if (stage === "completed") return `listed${amount ? `, raising ${amount}` : ""}`;
      return `plans to list${amount ? `, raising ${amount}` : ""}`;
    default:
      return d.deal_type.replace(/_/g, " ");
  }
}
