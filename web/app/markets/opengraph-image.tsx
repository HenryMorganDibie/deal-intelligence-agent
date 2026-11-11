import { ImageResponse } from "next/og";
import { billYield, latestBills, loadMarkets, pct } from "../../lib/market-public";

/* The link-preview card for the markets page: four headline figures from the day's snapshot. Rebuilt hourly; a
 * slow API still yields the brand card in time for a crawler. */

export const runtime = "edge";
export const revalidate = 3600;
export const alt = "African markets today on Deal Intelligence: exchanges, sectors, currencies and Treasury bills";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SITE = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/^https?:\/\//, "").replace(/\/$/, "") || "deal-intelligence.app";
const C = { bg: "#07080a", panel: "#0e1013", line: "rgba(255,255,255,0.10)", text: "#f2efe8", muted: "#9a9a96", faint: "#6b6b68", accent: "#6ee7c8" };

async function font(family: string, weight: number): Promise<ArrayBuffer | null> {
  try {
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family}:wght@${weight}`, { signal: AbortSignal.timeout(1500) })).text();
    const src = css.match(/src: url\((.+?)\) format\('(opentype|truetype)'\)/)?.[1];
    return src ? await (await fetch(src, { signal: AbortSignal.timeout(1500) })).arrayBuffer() : null;
  } catch {
    return null;
  }
}

export default async function Image() {
  const [{ overview, instruments }, display, body] = await Promise.all([loadMarkets(2500), font("Inter+Tight", 600), font("Inter", 400)]);
  const fonts = [
    ...(display ? [{ name: "Display", data: display, weight: 600 as const, style: "normal" as const }] : []),
    ...(body ? [{ name: "Body", data: body, weight: 400 as const, style: "normal" as const }] : []),
  ];
  const exchanges = (overview?.exchanges ?? []).filter((e) => !e.stale && e.as_of);
  const sectors = (overview?.sectors ?? []).filter((s) => s.shares >= 10 && s.ytd_usd != null).sort((a, z) => (z.ytd_usd ?? 0) - (a.ytd_usd ?? 0));
  const fx = (overview?.currencies ?? []).filter((c) => c.ytd_vs_usd != null).sort((a, z) => (z.ytd_vs_usd ?? 0) - (a.ytd_vs_usd ?? 0));
  const ngn = (overview?.currencies ?? []).find((c) => c.currency === "NGN");
  const bills = latestBills(instruments?.tbills);
  const topBill = bills.flatMap((b) => b.rows.slice(0, 1).map((r) => ({ name: b.name, y: billYield(r)!, tenor: r.tenor_label ?? `${r.tenor_days} days` })))
    .sort((a, z) => z.y - a.y)[0];

  const tiles: [string, string, string][] = [];
  if (sectors[0]) tiles.push([pct(sectors[0].ytd_usd), `${sectors[0].sector}`, "best sector this year, in US$"]);
  if (fx[0]) tiles.push([pct(fx[0].ytd_vs_usd), fx[0].currency, "strongest currency against the dollar"]);
  if (ngn?.per_usd) tiles.push([`₦${Math.round(ngn.per_usd).toLocaleString("en-US")}`, "Naira", "per US dollar"]);
  if (topBill) tiles.push([`${topBill.y.toFixed(2)}%`, topBill.name, `${topBill.tenor} Treasury bill, highest yield`]);

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
            {`MARKETS · ${exchanges.length || 24} EXCHANGES`}
          </div>
        </div>

        <div style={{ display: "flex", marginTop: 44, fontFamily: "Display", fontSize: 66, fontWeight: 600, letterSpacing: -2 }}>African markets today</div>

        <div style={{ display: "flex", flexWrap: "wrap", marginTop: 34, gap: 20 }}>
          {tiles.map(([big, label, note]) => (
            <div key={label} style={{ display: "flex", flexDirection: "column", width: 525, padding: "20px 24px", borderRadius: 16,
              border: `1px solid ${C.line}`, background: C.panel }}>
              <div style={{ display: "flex", alignItems: "baseline" }}>
                <div style={{ display: "flex", fontFamily: "Display", fontSize: 46, fontWeight: 600, color: C.accent }}>{big}</div>
                <div style={{ display: "flex", marginLeft: 14, fontFamily: "Display", fontSize: 28, fontWeight: 600 }}>{label}</div>
              </div>
              <div style={{ display: "flex", marginTop: 4, fontSize: 20, color: C.muted }}>{note}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", marginTop: "auto", fontSize: 20, color: C.faint }}>{`${SITE}/markets`}</div>
      </div>
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
