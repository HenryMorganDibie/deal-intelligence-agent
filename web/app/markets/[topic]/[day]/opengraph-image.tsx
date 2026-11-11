import { ImageResponse } from "next/og";
import { loadMarkets } from "../../../../lib/market-public";
import { Frame, OG_SIZE, Row, SITE, dayLabel, ogFonts } from "../../../../lib/og";
import { MARKET_TOPICS, marketTopic, type MarketTopic } from "../../../../lib/post-topics";

export const runtime = "edge";
export const revalidate = 3600;
export const alt = "An African markets post on Deal Intelligence";
export const size = OG_SIZE;
export const contentType = "image/png";

export default async function Image({ params }: { params: { topic: string; day: string } }) {
  const topic = ((MARKET_TOPICS as readonly string[]).includes(params.topic) ? params.topic : "sectors") as MarketTopic;
  const [{ overview, instruments }, fonts] = await Promise.all([loadMarkets(2500), ogFonts()]);
  const t = marketTopic(topic, overview, instruments);
  const day = dayLabel(params.day);
  const rows = t.rows.slice(0, topic === "movers" || topic === "currencies" ? 6 : 4);
  return new ImageResponse(
    (
      <Frame pill={`${t.pill}${day ? ` · ${day}` : ""}`} title={t.title} foot={`${SITE}/markets`}
        body={rows.length ? (
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between" }}>
            {rows.map((r) => (
              <div key={`${r.name}${r.value}`} style={{ display: "flex", width: rows.length > 5 ? 520 : 1072 }}>
                <div style={{ display: "flex", flexDirection: "column", width: "100%" }}><Row {...r} max={rows.length > 5 ? 22 : 44} /></div>
              </div>
            ))}
          </div>
        ) : <div style={{ display: "flex", fontSize: 28 }}>Prices, sectors, currencies and Treasury bills across Africa.</div>} />
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
