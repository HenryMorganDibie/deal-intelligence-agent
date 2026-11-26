import { createElement as h } from "react";
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
  const cardStyle = {
    display: "flex", flexDirection: "column", justifyContent: "center",
    width: count > 2 ? 510 : 520, minHeight: 150, padding: "24px 28px",
    border: "1px solid #263743", borderRadius: 18, background: "#101a22",
  };
  const cards = companies.map((company, index) => h("div", {
    key: `${company.exchange ?? "private"}-${company.symbol ?? company.name}-${index}`,
    style: cardStyle,
  },
    h("div", { style: { fontSize: 34, fontWeight: 700, lineHeight: 1.15 } }, company.name),
    h("div", { style: { display: "flex", gap: 12, marginTop: 13, color: "#54d6bd", fontSize: 19 } },
      company.symbol ? h("span", null, company.symbol.toUpperCase()) : h("span", null, "PRIVATE COMPANY"),
      company.exchange ? h("span", { style: { color: "#9aa9b4" } }, `· ${company.exchange.toUpperCase()}`) : null,
      company.country ? h("span", { style: { color: "#9aa9b4" } }, `· ${company.country}`) : null,
    ),
  ));

  const tree = h("div", {
    style: {
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      justifyContent: "space-between", padding: "58px 68px", background: "#080d12",
      color: "#f5f7f8", fontFamily: "Arial, sans-serif",
    },
  },
    h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between" } },
      h("div", { style: { display: "flex", alignItems: "center", gap: 14 } },
        h("div", { style: { width: 12, height: 36, borderRadius: 8, background: "#54d6bd" } }),
        h("span", { style: { fontSize: 25, fontWeight: 700, letterSpacing: 2 } }, "DEAL INTELLIGENCE"),
      ),
      h("span", { style: { color: "#9aa9b4", fontSize: 19, letterSpacing: 2 } }, "COMPANY COMPARISON"),
    ),
    h("div", { style: { display: "flex", flexDirection: "column", gap: 24 } },
      h("div", { style: { fontSize: 22, color: "#9aa9b4" } }, "A clearer view of the companies behind the numbers."),
      h("div", { style: { display: "flex", gap: 18, flexWrap: "wrap" } }, ...cards),
    ),
    h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid #263743", paddingTop: 22 } },
      h("span", { style: { color: "#9aa9b4", fontSize: 19 } }, "Financials · Market data · Valuation · Company intelligence"),
      h("span", { style: { color: "#54d6bd", fontSize: 20, fontWeight: 700 } }, "deal-intelligence.app"),
    ),
  );

  return new ImageResponse(tree, { ...size });
}
