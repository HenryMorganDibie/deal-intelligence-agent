import { ImageResponse } from "next/og";
import { roundupWindow } from "../../../../lib/deal-windows";
import { Frame, OG_SIZE, Row, SITE, dayLabel, ogFonts } from "../../../../lib/og";
import { roundupTopic } from "../../../../lib/post-topics";

export const runtime = "edge";
export const revalidate = 3600;
export const alt = "The day's largest African deals on Deal Intelligence";
export const size = OG_SIZE;
export const contentType = "image/png";

export default async function Image({ params }: { params: { day: string } }) {
  const [{ deals, label }, fonts] = await Promise.all([roundupWindow(params.day, 2500), ogFonts()]);
  const t = roundupTopic(deals, label);
  const day = dayLabel(params.day);
  return new ImageResponse(
    (
      <Frame pill={`Deal roundup${day ? ` · ${day}` : ""}`} title={t.title} foot={`${SITE}/deals`}
        body={<div style={{ display: "flex", flexDirection: "column" }}>{t.rows.slice(0, 5).map((r) => <Row key={r.name} {...r} max={40} />)}</div>} />
    ),
    { ...size, ...(fonts.length ? { fonts } : {}) },
  );
}
