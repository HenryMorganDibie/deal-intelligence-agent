import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPage } from "../../../../components/TopicPage";
import { roundupWindow } from "../../../../lib/deal-windows";
import { dayLabel } from "../../../../lib/og";
import { roundupTopic } from "../../../../lib/post-topics";

/** The daily roundup post's page: the largest deals of the window, one per company. */
export const revalidate = 3600;

export async function generateMetadata({ params }: { params: { day: string } }): Promise<Metadata> {
  if (!dayLabel(params.day)) return { title: "Not found | Deal Intelligence", robots: { index: false } };
  return { title: `African deals, ${dayLabel(params.day)} | Deal Intelligence`,
    description: "The largest African deals tracked in the last day, one per company, each with its sources.",
    alternates: { canonical: `/deals/roundup/${params.day}` }, robots: { index: false, follow: true } };
}

export default async function RoundupPage({ params }: { params: { day: string } }) {
  if (!dayLabel(params.day)) notFound();
  const { deals, label } = await roundupWindow(params.day);
  return <TopicPage topic={roundupTopic(deals, label)} day={dayLabel(params.day)} />;
}
