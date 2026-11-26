import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "GTCO, First HoldCo and Zenith Bank compared on Deal Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const C = {
  bg: "#080b0d",
  panel: "#101619",
  line: "rgba(255,255,255,0.12)",
  text: "#f4f5f2",
  muted: "#a4b0ad",
  accent: "#6ee7c8",
  accentSoft: "rgba(110,231,200,0.12)",
};

export default function Image() {
  const companies = [
    { name: "GTCO", ticker: "GTCO", descriptor: "Guaranty Trust Holding" },
    { name: "First HoldCo", ticker: "FIRSTHOLDCO", descriptor: "First HoldCo Plc" },
    { name: "Zenith Bank", ticker: "ZENITHBANK", descriptor: "Zenith Bank Plc" },
  ];

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: C.bg,
          color: C.text,
          padding: "54px 64px",
          fontFamily: "Arial, sans-serif",
          backgroundImage: "radial-gradient(circle at 85% 0%, rgba(110,231,200,0.15), transparent 42%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 12, background: C.accentSoft, border: "1px solid rgba(110,231,200,0.35)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="25" height="25" viewBox="0 0 24 24" fill="none">
              <path d="M2 13h4l2.5-6 4 11 3-8 1.5 3H22" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div style={{ display: "flex", fontSize: 25, fontWeight: 700, letterSpacing: -0.5 }}>Deal Intelligence</div>
          <div style={{ display: "flex", marginLeft: "auto", fontSize: 15, color: C.accent, letterSpacing: 2, fontWeight: 700 }}>NIGERIAN EQUITIES</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", marginTop: 56 }}>
          <div style={{ display: "flex", color: C.accent, fontSize: 17, fontWeight: 700, letterSpacing: 3 }}>COMPANY COMPARISON</div>
          <div style={{ display: "flex", fontSize: 56, fontWeight: 700, letterSpacing: -2, marginTop: 14, lineHeight: 1.08 }}>
            Compare Nigeria's leading banks.
          </div>
          <div style={{ display: "flex", color: C.muted, fontSize: 23, marginTop: 15 }}>
            Market performance, financials and company intelligence.
          </div>
        </div>

        <div style={{ display: "flex", gap: 16, marginTop: 42 }}>
          {companies.map((company, index) => (
            <div key={company.ticker} style={{ display: "flex", flexDirection: "column", flex: 1, height: 145, border: `1px solid ${C.line}`, borderRadius: 16, background: C.panel, padding: "22px 22px" }}>
              <div style={{ display: "flex", color: C.muted, fontSize: 14, letterSpacing: 1.5 }}>0{index + 1} / LISTED COMPANY</div>
              <div style={{ display: "flex", fontSize: 28, fontWeight: 700, marginTop: 16 }}>{company.name}</div>
              <div style={{ display: "flex", color: C.accent, fontSize: 15, marginTop: 8 }}>{company.ticker}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", marginTop: "auto", borderTop: `1px solid ${C.line}`, paddingTop: 20, color: C.muted, fontSize: 17 }}>
          Evidence-led company research
          <div style={{ display: "flex", marginLeft: "auto", color: C.text, fontWeight: 700 }}>deal-intelligence.app</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
