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
  const title = `African deals, ${dayLabel(params.day)}`;
  const description = "The largest African deals tracked in the last day, one per company, each with its sources.";
  const url = `/deals/roundup/${params.day}`;
  return { title: `${title} | Deal Intelligence`, description, alternates: { canonical: url }, robots: { index: false, follow: true },
    openGraph: { title, description, url, type: "article", siteName: "Deal Intelligence" },
    twitter: { card: "summary_large_image", title, description } };
}

export default async function RoundupPage({ params }: { params: { day: string } }) {
  if (!dayLabel(params.day)) notFound();
  const { deals, label } = await roundupWindow(params.day);
  return <TopicPage topic={roundupTopic(deals, label)} day={dayLabel(params.day)} />;
}
