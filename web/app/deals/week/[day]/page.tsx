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
  const title = `The week in African deals, to ${dayLabel(params.day)}`;
  const description = "How many African deals were tracked this week, how much was disclosed, the busiest market and the largest deals.";
  const url = `/deals/week/${params.day}`;
  return { title: `${title} | Deal Intelligence`, description, alternates: { canonical: url }, robots: { index: false, follow: true },
    openGraph: { title, description, url, type: "article", siteName: "Deal Intelligence" },
    twitter: { card: "summary_large_image", title, description } };
}

export default async function WeekPage({ params }: { params: { day: string } }) {
  if (!dayLabel(params.day)) notFound();
  const { deals, total, start, end } = await weekWindow(params.day);
  const t = weekTopic(deals, total, start, end);
  return <TopicPage topic={t} day={dayLabel(params.day)} stats={t.stats} />;
}
