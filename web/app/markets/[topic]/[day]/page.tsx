import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPage } from "../../../../components/TopicPage";
import { loadMarkets } from "../../../../lib/market-public";
import { dayLabel } from "../../../../lib/og";
import { MARKET_TOPICS, marketTopic, type MarketTopic } from "../../../../lib/post-topics";

/** One market post's page (movers, currencies, Treasury bills, sectors, election watch), dated so each day's link has its own card. */
export const revalidate = 3600;

type Params = { params: Promise<{ topic: string; day: string }> };

function valid(p: { topic: string; day: string }): p is { topic: MarketTopic; day: string } {
  return (MARKET_TOPICS as readonly string[]).includes(p.topic) && dayLabel(p.day) !== null;
}

export async function generateMetadata(props: Params): Promise<Metadata> {
  const params = await props.params;
  if (!valid(params)) return { title: "Not found | Deal Intelligence", robots: { index: false } };
  const t = marketTopic(params.topic, null, null, params.day);
  const title = `${t.title}, ${dayLabel(params.day)}`;
  const url = `/markets/${params.topic}/${params.day}`;
  return {
    title: `${title} | Deal Intelligence`,
    description: t.intro,
    alternates: { canonical: url },
    openGraph: { title, description: t.intro, url, type: "article", siteName: "Deal Intelligence" },
    twitter: { card: "summary_large_image", title, description: t.intro },
    robots: { index: false, follow: true },
  };
}

export default async function MarketTopicPage(props: Params) {
  const params = await props.params;
  if (!valid(params)) notFound();
  const { overview, instruments } = await loadMarkets();
  return <TopicPage topic={marketTopic(params.topic, overview, instruments, params.day)} day={dayLabel(params.day)} />;
}
