from urllib.parse import urlparse

from src.tools.africa_tool import AFRICAN_NEWS_FEEDS

# Hosts whose feeds were removed or retired; their outlets are read another way now.
RETIRED = {"weekly.ahram.org.eg", "stears.co", "www.newtimes.co.rw"}


def test_feeds_are_https_and_unique():
    urls = list(AFRICAN_NEWS_FEEDS.values())
    assert all(u.startswith("https://") for u in urls)
    assert len(urls) == len(set(urls)), "two outlets share one feed URL"


def test_retired_feed_hosts_are_not_used():
    hosts = {urlparse(u).netloc for u in AFRICAN_NEWS_FEEDS.values()}
    assert not hosts & RETIRED


def test_site_news_queries_are_limited_to_the_outlet_and_recent():
    for name, url in AFRICAN_NEWS_FEEDS.items():
        if url.startswith("https://news.google.com/"):
            assert "site%3A" in url and "when%3A2d" in url, name
