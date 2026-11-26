import { ImageResponse } from "next/og";
import { decodeEntries } from "../../../../lib/compare";

export const runtime = "edge";
export const alt = "Company comparison on Deal Intelligence";
export const contentType = "image/png";
export const size = { width: 1200, height: 630 };

export async function GET(request: Request) {
  const url = new URL(request.url);
  const refs = decodeEntries(url.searchParams.get("c"));
  const companies = refs.length ? refs.slice(0, 4) : [{ name: "Listed and private companies", country: null }];
  const count = companies.length;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "58px 68px",
          background: "#080d12",
          color: "#f5f7f8",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 12, height: 36, borderRadius: 8, background: "#54d6bd" }} />
            <span style={{ fontSize: 25, fontWeight: 700, letterSpacing: 2 }}>DEAL INTELLIGENCE</span>
          </div>
          <span style={{ color: "#9aa9b4", fontSize: 19, letterSpacing: 2 }}>COMPANY COMPARISON</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ fontSize: 22, color: "#9aa9b4" }}>A clearer view of the companies behind the numbers.</div>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            {companies.map((company, index) => (
              <div
                key={`${company.exchange ?? "private"}-${company.symbol ?? company.name}-${index}`}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  width: count > 2 ? 510 : 520,
                  minHeight: 150,
                  padding: "24px 28px",
                  border: "1px solid #263743",
                  borderRadius: 18,
                  background: "#101a22",
                }}
              >
                <div style={{ fontSize: 34, fontWeight: 700, lineHeight: 1.15 }}>{company.name}</div>
                <div style={{ display: "flex", gap: 12, marginTop: 13, color: "#54d6bd", fontSize: 19 }}>
                  {company.symbol ? <span>{company.symbol.toUpperCase()}</span> : <span>PRIVATE COMPANY</span>}
                  {company.exchange ? <span style={{ color: "#9aa9b4" }}>· {company.exchange.toUpperCase()}</span> : null}
                  {company.country ? <span style={{ color: "#9aa9b4" }}>· {company.country}</span> : null}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid #263743", paddingTop: 22 }}>
          <span style={{ color: "#9aa9b4", fontSize: 19 }}>Financials · Market data · Valuation · Company intelligence</span>
          <span style={{ color: "#54d6bd", fontSize: 20, fontWeight: 700 }}>deal-intelligence.app</span>
        </div>
      </div>
    ),
    { ...size },
  );
}
