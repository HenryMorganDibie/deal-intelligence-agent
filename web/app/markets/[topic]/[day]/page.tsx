import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPage } from "../../../../components/TopicPage";
import { loadMarkets } from "../../../../lib/market-public";
import { dayLabel } from "../../../../lib/og";
import { MARKET_TOPICS, marketTopic, type MarketTopic } from "../../../../lib/post-topics";

/** One market post's page (movers, currencies, Treasury bills, sectors), dated so each day's link has its own card. */
export const revalidate = 3600;

type Params = { params: { topic: string; day: string } };

function valid(p: Params["params"]): p is { topic: MarketTopic; day: string } {
  return (MARKET_TOPICS as readonly string[]).includes(p.topic) && dayLabel(p.day) !== null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  if (!valid(params)) return { title: "Not found | Deal Intelligence", robots: { index: false } };
  const t = marketTopic(params.topic, null, null);
  return {
    title: `${t.title}, ${dayLabel(params.day)} | Deal Intelligence`,
    description: t.intro,
    alternates: { canonical: `/markets/${params.topic}/${params.day}` },
    robots: { index: false, follow: true },
  };
}

export default async function MarketTopicPage({ params }: Params) {
  if (!valid(params)) notFound();
  const { overview, instruments } = await loadMarkets();
  return <TopicPage topic={marketTopic(params.topic, overview, instruments)} day={dayLabel(params.day)} />;
}
