import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPage } from "../../../../components/TopicPage";
import { weekWindow } from "../../../../lib/deal-windows";
import { dayLabel } from "../../../../lib/og";
import { weekTopic } from "../../../../lib/post-topics";

/** The Monday week-in-review post's page: the week's count, disclosed total, busiest market and largest deals. */
export const revalidate = 3600;

export async function generateMetadata({ params }: { params: { day: string } }): Promise<Metadata> {
  if (!dayLabel(params.day)) return { title: "Not found | Deal Intelligence", robots: { index: false } };
  return { title: `The week in African deals, to ${dayLabel(params.day)} | Deal Intelligence`,
    description: "How many African deals were tracked this week, how much was disclosed, the busiest market and the largest deals.",
    alternates: { canonical: `/deals/week/${params.day}` }, robots: { index: false, follow: true } };
}

export default async function WeekPage({ params }: { params: { day: string } }) {
  if (!dayLabel(params.day)) notFound();
  const { deals, total, start, end } = await weekWindow(params.day);
  const t = weekTopic(deals, total, start, end);
  return <TopicPage topic={t} day={dayLabel(params.day)} stats={t.stats} />;
}
