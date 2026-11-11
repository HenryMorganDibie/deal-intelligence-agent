import { ImageResponse } from "next/og";
import { API_CONFIGURED, apiHeaders, apiUrl } from "../../../lib/api-base";

/* The link-preview card for one deal (X, LinkedIn, WhatsApp, Slack): what happened, to whom, for how much, where,
 * and how many sources report it, from the stored record only. A crawler always gets an image: every fetch has a
 * short timeout and a missing deal falls back to the brand card. */

export const runtime = "edge";
export const revalidate = 86400;                // a published deal rarely changes; one refresh a day
export const alt = "A deal on Deal Intelligence, with its parties, amount and sources";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SITE = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/^https?:\/\//, "").replace(/\/$/, "") || "deal-intelligence.app";
const C = { bg: "#07080a", panel: "#0e1013", line: "rgba(255,255,255,0.10)", text: "#f2efe8", muted: "#9a9a96", faint: "#6b6b68", accent: "#6ee7c8" };

type Deal = {
  deal_type: string | null; target: string | null; buyer: string | null; seller: string | null; investors: string[] | null;
  amount_usd: number | null; stake_pct: number | null; round: string | null; country: string | null; announced: string | null;
  headline: string; sources: unknown[] | null;
};
type Verification = { status?: string; independent_stories?: number } | undefined;

const TYPE: Record<string, string> = {
  equity_funding: "Equity funding", debt_financing: "Debt financing", acquisition: "Acquisition", fund_raise: "Fund close",
  exit: "Exit", ipo: "IPO", merger: "Merger", joint_venture: "Joint venture",
};

const trim = (x: number, d: number) => x.toFixed(d).replace(/\.0+$/, "");
const usd = (v: number) => (v >= 1e9 ? `$${trim(v / 1e9, 1)}bn` : v >= 1e6 ? `$${trim(v / 1e6, v >= 1e8 ? 0 : 1)}m` : `$${Math.round(v / 1e3)}k`);

function countryName(code: string | null): string | null {
  if (!code) return null;
  if (code === "CD") return "DR Congo";
  if (code === "CG") return "Republic of the Congo";
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

function dateText(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return isNaN(d.getTime()) ? null : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** The parties line under the company: who backed, bought or sold. */
function parties(d: Deal): string | null {
  const names = (d.investors ?? []).filter(Boolean).slice(0, 3);
  switch (d.deal_type) {
    case "equity_funding":
      return names.length ? `Backed by ${names.join(", ")}` : d.round ? `${d.round} round` : null;
    case "debt_financing":
      return names.length ? `Lender${names.length > 1 ? "s" : ""}: ${names.join(", ")}` : null;
    case "acquisition":
    case "merger":
      return d.buyer ? `${d.deal_type === "merger" ? "Merging with" : "Acquired by"} ${d.buyer}${d.stake_pct && d.stake_pct < 100 ? `, ${trim(d.stake_pct, 1)}% stake` : ""}` : null;
    case "exit":
      return d.seller ? `Sold by ${d.seller}${d.buyer ? ` to ${d.buyer}` : ""}` : null;
    case "fund_raise":
      return names.length ? `Investors include ${names.join(", ")}` : null;
    default:
      return null;
  }
}

async function load(id: string): Promise<{ deal: Deal; verification?: Verification } | null> {
  if (!API_CONFIGURED) return null;
  try {
    const r = await fetch(apiUrl(`/api/deals/${encodeURIComponent(id)}?comparables=false`), { headers: apiHeaders(), next: { revalidate }, signal: AbortSignal.timeout(2500) });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

async function font(family: string, weight: number): Promise<ArrayBuffer | null> {
  try {
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family}:wght@${weight}`, { signal: AbortSignal.timeout(1500) })).text();
    const src = css.match(/src: url\((.+?)\) format\('(opentype|truetype)'\)/)?.[1];
    return src ? await (await fetch(src, { signal: AbortSignal.timeout(1500) })).arrayBuffer() : null;
  } catch {
    return null;
  }
}

export default async function Image({ params }: { params: { id: string } }) {
  const [data, display, body] = await Promise.all([load(params.id), font("Inter+Tight", 600), font("Inter", 400)]);
  const d = data?.deal;
  const fonts = [
    ...(display ? [{ name: "Display", data: display, weight: 600 as const, style: "normal" as const }] : []),
    ...(body ? [{ name: "Body", data: body, weight: 400 as const, style: "normal" as const }] : []),
  ];
  const name = d?.target ?? d?.headline ?? "African deal flow, every source linked";
  const nameSize = name.length > 34 ? 52 : name.length > 22 ? 64 : 78;
  const where = countryName(d?.country ?? null);
  const kind = d ? TYPE[d.deal_type ?? ""] ?? "Deal" : "Deal Intelligence";
  const who = d ? parties(d) : "Private-market deals across all 54 African countries";
  const stories = data?.verification?.independent_stories ?? (d?.sources?.length ?? 0);
  const when = dateText(d?.announced ?? null);

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: C.bg, color: C.text,
        fontFamily: "Body", padding: "54px 64px", backgroundImage: "radial-gradient(circle at 85% -10%, rgba(110,231,200,0.18), transparent 55%)" }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, border: `1px solid ${C.line}`, background: C.panel, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M2 13h4l2.5-6 4 11 3-8 1.5 3H22" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div style={{ display: "flex", marginLeft: 14, fontFamily: "Display", fontSize: 26, fontWeight: 600 }}>Deal Intelligence</div>
          <div style={{ display: "flex", marginLeft: "auto", fontSize: 20, padding: "8px 18px", borderRadius: 999,
            border: "1px solid rgba(110,231,200,0.45)", color: C.accent, letterSpacing: 1 }}>
            {`${kind.toUpperCase()}${where ? ` · ${where.toUpperCase()}` : ""}`}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", marginTop: "auto", marginBottom: "auto" }}>
          <div style={{ display: "flex", fontFamily: "Display", fontSize: nameSize, fontWeight: 600, lineHeight: 1.05, letterSpacing: -2 }}>{name}</div>
          {d?.amount_usd ? (
            <div style={{ display: "flex", marginTop: 18, fontFamily: "Display", fontSize: 92, fontWeight: 600, color: C.accent, letterSpacing: -3 }}>
              {usd(d.amount_usd)}
            </div>
          ) : null}
          {who ? <div style={{ display: "flex", marginTop: 16, fontSize: 30, color: C.muted }}>{who}</div> : null}
        </div>

        <div style={{ display: "flex", alignItems: "center", borderTop: `1px solid ${C.line}`, paddingTop: 22, fontSize: 22, color: C.muted }}>
          {when ? <div style={{ display: "flex" }}>{`Reported ${when}`}</div> : null}
          {d ? (
            <div style={{ display: "flex", marginLeft: when ? 28 : 0, color: stories >= 2 ? C.accent : C.muted }}>
              {stories >= 2 ? `${stories} independent sources` : "Single source, linked"}
            </div>
          ) : null}
          <div style={{ display: "flex", marginLeft: "auto", color: C.faint }}>{SITE}</div>
        </div>
      </div>
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
