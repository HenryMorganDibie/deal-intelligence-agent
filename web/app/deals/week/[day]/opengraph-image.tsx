import { ImageResponse } from "next/og";
import { weekWindow } from "../../../../lib/deal-windows";
import { C, Frame, OG_SIZE, Row, SITE, ogFonts } from "../../../../lib/og";
import { weekTopic } from "../../../../lib/post-topics";

export const runtime = "edge";
export const revalidate = 3600;
export const alt = "The week in African deals on Deal Intelligence";
export const size = OG_SIZE;
export const contentType = "image/png";

export default async function Image({ params }: { params: { day: string } }) {
  const [{ deals, total, start, end }, fonts] = await Promise.all([weekWindow(params.day, 2500), ogFonts()]);
  const t = weekTopic(deals, total, start, end);
  return new ImageResponse(
    (
      <Frame pill={`Week in review · ${start} to ${end}`} title={t.title} foot={`${SITE}/deals`}
        body={
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", gap: 20 }}>
              {t.stats.map(([v, k]) => (
                <div key={k} style={{ display: "flex", flexDirection: "column", flexGrow: 1, padding: "14px 20px", borderRadius: 14,
                  border: `1px solid ${C.line}`, background: C.panel }}>
                  <div style={{ display: "flex", fontFamily: "Display", fontSize: 40, fontWeight: 600, color: C.accent }}>{v}</div>
                  <div style={{ display: "flex", fontSize: 19, color: C.muted }}>{k}</div>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", flexDirection: "column", marginTop: 10 }}>
              {t.rows.slice(0, 3).map((r) => <Row key={r.name} {...r} max={40} />)}
            </div>
          </div>
        } />
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
