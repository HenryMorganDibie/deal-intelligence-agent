import { ImageResponse } from "next/og";

/* The link-preview card (X, LinkedIn, WhatsApp, Slack): the headline beside the latest deals that
 * several independent sources report, with live counts. Rebuilt hourly from the hosted API. */

export const runtime = "edge";
export const revalidate = 3600;
export const alt = "Deal Intelligence: deal signals you can audit, with the latest corroborated African deals";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/^https?:\/\//, "").replace(/\/$/, "")
  || "deal-intelligence-app.vercel.app";

const C = {
  bg: "#07080a",
  panel: "#0e1013",
  line: "rgba(255,255,255,0.09)",
  text: "#f2efe8",
  muted: "#9a9a96",
  faint: "#6b6b68",
  accent: "#6ee7c8",
};

type Deal = {
  target: string | null;
  deal_type: string | null;
  country: string | null;
  amount_usd: number | null;
  announced: string | null;
  independent_stories?: number | null;
  verification?: string | null;
  buyer?: string | null;
  investors?: string[] | null;
};

const TYPE: Record<string, string> = {
  equity_funding: "Equity funding",
  debt_financing: "Debt financing",
  acquisition: "Acquisition",
  fund_raise: "Fund close",
  exit: "Exit",
  ipo: "IPO",
  merger: "Merger",
};

const trim = (x: number, digits: number) => x.toFixed(digits).replace(/\.0+$/, "");
const usd = (v: number) =>
  v >= 1e9 ? `$${trim(v / 1e9, 1)}bn` : v >= 1e6 ? `$${trim(v / 1e6, v >= 1e8 ? 0 : 1)}m` : `$${Math.round(v / 1e3)}k`;
const count = (v: number) => v.toLocaleString("en-US");

async function json<T>(path: string): Promise<T | null> {
  if (!API_URL) return null;
  try {
    const r = await fetch(`${API_URL}${path}`, { next: { revalidate } });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

async function font(family: string, weight: number): Promise<ArrayBuffer | null> {
  try {
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family}:wght@${weight}`)).text();
    const src = css.match(/src: url\((.+?)\) format\('(opentype|truetype)'\)/)?.[1];
    return src ? await (await fetch(src)).arrayBuffer() : null;
  } catch {
    return null;
  }
}

/** Latest four deals of $5m or more with a country, preferring those several independent stories report. */
function pick(deals: Deal[]): Deal[] {
  const usable = deals.filter((d) => d.target && (d.amount_usd ?? 0) >= 5e6 && d.country && d.target.length <= 28);
  const corroborated = usable.filter((d) => (d.independent_stories ?? 1) >= 2);
  return [...corroborated, ...usable.filter((d) => !corroborated.includes(d))].slice(0, 4);
}

export default async function Image() {
  const [pulse, list, display, body] = await Promise.all([
    json<{ deals?: { total?: number }; measured?: { backtest_observations?: number; live_observations?: number } }>("/api/pulse"),
    json<{ deals?: Deal[] }>("/api/deals?limit=100"),
    font("Inter+Tight", 600),
    font("Inter", 400),
  ]);
  const deals = pick(list?.deals ?? []);
  const total = pulse?.deals?.total;
  const signals = (pulse?.measured?.backtest_observations ?? 0) + (pulse?.measured?.live_observations ?? 0);
  const stats: [string, string][] = [
    [total ? count(total) : "1,700+", "deals tracked"],
    [signals ? count(signals) : "6,900+", "backtested signals"],
    ["54", "African countries"],
  ];

  const fonts = [
    ...(display ? [{ name: "Display", data: display, weight: 600 as const, style: "normal" as const }] : []),
    ...(body ? [{ name: "Body", data: body, weight: 400 as const, style: "normal" as const }] : []),
  ];

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%", height: "100%", display: "flex", background: C.bg, color: C.text,
          fontFamily: "Body", padding: "56px 60px", position: "relative",
          backgroundImage: "radial-gradient(circle at 78% -10%, rgba(110,231,200,0.16), transparent 55%)",
        }}
      >
        {/* Left: brand, headline, live counts */}
        <div style={{ display: "flex", flexDirection: "column", width: 560, justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                width: 40, height: 40, borderRadius: 10, border: `1px solid ${C.line}`, background: C.panel,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M2 13h4l2.5-6 4 11 3-8 1.5 3H22" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div style={{ display: "flex", fontFamily: "Display", fontSize: 26, fontWeight: 600 }}>Deal Intelligence</div>
          </div>

          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", flexDirection: "column", fontFamily: "Display", fontSize: 70, fontWeight: 600, lineHeight: 1.02, letterSpacing: -2.5 }}>
              <span>Deal signals</span>
              <span>you can audit.</span>
            </div>
            <div style={{ display: "flex", marginTop: 22, fontSize: 24, lineHeight: 1.4, color: C.muted, width: 520 }}>
              Private-market deals, company signals and country risk across Africa and the US. Every number traces to a source.
            </div>
          </div>

          <div style={{ display: "flex", gap: 40, borderTop: `1px solid ${C.line}`, paddingTop: 22 }}>
            {stats.map(([k, v]) => (
              <div key={v} style={{ display: "flex", flexDirection: "column" }}>
                <div style={{ display: "flex", fontFamily: "Display", fontSize: 34, fontWeight: 600 }}>{k}</div>
                <div style={{ display: "flex", fontSize: 18, color: C.muted, marginTop: 2 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: the product, with real records */}
        <div
          style={{
            display: "flex", flexDirection: "column", marginLeft: "auto", width: 500, borderRadius: 18,
            border: `1px solid ${C.line}`, background: C.panel, overflow: "hidden",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", padding: "18px 22px", borderBottom: `1px solid ${C.line}` }}>
            <div style={{ display: "flex", gap: 7 }}>
              {[0, 1, 2].map((i) => (
                <div key={i} style={{ width: 10, height: 10, borderRadius: 5, background: "rgba(255,255,255,0.14)" }} />
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", fontSize: 14, letterSpacing: 2, color: C.muted }}>
              <div style={{ width: 7, height: 7, borderRadius: 4, background: C.accent }} />
              LATEST DEALS
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", padding: "6px 22px 0" }}>
            {deals.length ? (
              deals.map((d, i) => {
                const sources = d.independent_stories ?? 1;
                return (
                  <div
                    key={i}
                    style={{
                      display: "flex", alignItems: "center", padding: "17px 0",
                      borderBottom: i < deals.length - 1 ? `1px solid ${C.line}` : "none",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1 }}>
                      <div style={{ display: "flex", fontFamily: "Display", fontSize: 24, fontWeight: 600 }}>{d.target}</div>
                      <div style={{ display: "flex", fontSize: 17, color: C.muted, marginTop: 4 }}>
                        {`${TYPE[d.deal_type ?? ""] ?? "Deal"} · ${d.country}`}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                      <div style={{ display: "flex", fontFamily: "Display", fontSize: 24, fontWeight: 600 }}>{usd(d.amount_usd!)}</div>
                      <div
                        style={{
                          display: "flex", marginTop: 6, fontSize: 14, padding: "3px 10px", borderRadius: 999,
                          border: `1px solid ${sources >= 2 ? "rgba(110,231,200,0.45)" : C.line}`,
                          color: sources >= 2 ? C.accent : C.faint,
                        }}
                      >
                        {sources >= 2 ? `${sources} independent sources` : "single source"}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div style={{ display: "flex", padding: "40px 0", fontSize: 22, color: C.muted }}>
                PE, VC, debt and M&A across all 54 African countries, every source linked.
              </div>
            )}
          </div>

          <div
            style={{
              display: "flex", marginTop: "auto", padding: "16px 22px", borderTop: `1px solid ${C.line}`,
              fontSize: 16, color: C.faint,
            }}
          >
            {SITE_URL}
          </div>
        </div>
      </div>
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
