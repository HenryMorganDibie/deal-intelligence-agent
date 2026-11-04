import asyncio
from datetime import date, timedelta

import httpx

from src.engines import feed_healing as fh

TODAY = date.today()
_RealClient = httpx.AsyncClient


def rss(day: date = TODAY, title: str = "Bank raises capital") -> str:
    stamp = day.strftime("%a, %d %b %Y 08:00:00 +0000")
    return (f'<?xml version="1.0"?><rss><channel><item><title>{title}</title><link>https://x.example/a</link>'
            f"<pubDate>{stamp}</pubDate></item></channel></rss>")


def client_for(routes: dict[str, tuple[int, str, str]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        match = routes.get(url) or next((v for k, v in routes.items()
                                         if k == "https://news.google.com/" and url.startswith(k)), None)
        if match:
            status, body, kind = match
            return httpx.Response(status, text=body, headers={"content-type": kind})
        return httpx.Response(404, text="missing", headers={"content-type": "text/html"})
    return _RealClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def run(coro):
    return asyncio.run(coro)


def test_homepage_advertised_feed_replaces_a_dead_one():
    home = '<html><head><link rel="alternate" type="application/rss+xml" href="/news/feed.xml"></head></html>'
    routes = {"https://outlet.example/news/feed.xml": (200, rss(), "application/rss+xml"),
              "https://outlet.example/": (200, home, "text/html")}

    async def go():
        async with client_for(routes) as c:
            return await fh.find_replacement(c, "Outlet", "https://outlet.example/old-feed", exclude=("https://outlet.example/old-feed",))
    url, items = run(go())
    assert url == "https://outlet.example/news/feed.xml" and items


def test_common_feed_path_is_tried_when_nothing_is_advertised():
    routes = {"https://www.outlet.example/rss.xml": (200, rss(), "application/rss+xml"),
              "https://www.outlet.example/": (200, "<html></html>", "text/html")}

    async def go():
        async with client_for(routes) as c:
            return await fh.find_replacement(c, "Outlet", "https://www.outlet.example/gone")
    assert run(go())[0] == "https://www.outlet.example/rss.xml"


def test_feed_advertised_on_another_site_is_never_used():
    home = '<html><link rel="alternate" type="application/rss+xml" href="https://other.example/feed"></html>'
    routes = {"https://other.example/feed": (200, rss(), "application/rss+xml"),
              "https://outlet.example/": (200, home, "text/html"),
              "https://news.google.com/": (200, rss(), "application/xml")}

    async def go():
        async with client_for(routes) as c:
            return await fh.find_replacement(c, "Outlet", "https://outlet.example/gone")
    url, _ = run(go())
    assert url.startswith("https://news.google.com/") and "site%3Aoutlet.example" in url


def test_site_news_is_the_last_resort_and_keeps_region():
    routes = {"https://news.google.com/": (200, rss(), "application/xml")}

    async def go():
        async with client_for(routes) as c:
            return await fh.find_replacement(c, "Punch Nigeria", "https://punchng.com/feed/")
    url, _ = run(go())
    assert "site%3Apunchng.com" in url and "gl=NG" in url and "when%3A2d" in url


def test_stale_feed_counts_as_dead():
    old = TODAY - timedelta(days=fh.STALE_AFTER_DAYS + 5)
    routes = {"https://outlet.example/feed/": (200, rss(old), "application/rss+xml")}

    async def go():
        async with client_for(routes) as c:
            return await fh.probe(c, "https://outlet.example/feed/")
    ok, items, reason = run(go())
    assert not ok and items and reason.startswith("stale since")


def test_effective_feeds_prefers_saved_replacements():
    feeds = {"A": "https://a.example/feed/", "B": "https://b.example/feed/"}
    overrides = {"B": {"url": "https://b.example/rss.xml", "since": "2026-11-01", "reason": "x"},
                 "C": {"url": "http://insecure.example/feed"}}
    assert fh.effective_feeds(feeds, overrides) == {"A": "https://a.example/feed/", "B": "https://b.example/rss.xml"}


def test_heal_all_drops_override_when_preferred_feed_recovers(monkeypatch):
    feeds = {"A": "https://a.example/feed/"}
    saved = {"A": {"url": "https://a.example/rss.xml", "since": "2026-10-01", "reason": "old"}}
    routes = {"https://a.example/feed/": (200, rss(), "application/rss+xml")}
    monkeypatch.setattr(fh.httpx, "AsyncClient", lambda **kw: client_for(routes))
    overrides, changes, unresolved, _ = run(fh.heal_all(feeds, saved))
    assert overrides == {} and changes and not unresolved


def test_heal_all_saves_a_replacement_for_a_dead_feed(monkeypatch):
    feeds = {"A": "https://a.example/old"}
    routes = {"https://a.example/feed/": (200, rss(), "application/rss+xml"),
              "https://a.example/": (200, "<html></html>", "text/html")}
    monkeypatch.setattr(fh.httpx, "AsyncClient", lambda **kw: client_for(routes))
    overrides, changes, unresolved, _ = run(fh.heal_all(feeds, {}))
    assert overrides["A"]["url"] == "https://a.example/feed/" and "404" in overrides["A"]["reason"]
    assert changes and not unresolved


def test_collector_reads_a_failed_outlet_from_its_replacement():
    from src.engines import market_feed
    routes = {"https://a.example/feed/": (200, rss(title="Acme acquires Beta"), "application/rss+xml"),
              "https://a.example/": (200, "<html></html>", "text/html")}

    async def go():
        async with client_for(routes) as c:
            return await market_feed._replace_failed_outlets(c, {"Outlet A": "https://a.example/old"}, {"Outlet A": False})
    (items,) = run(go())
    assert items and items[0]["feed"] == "Outlet A" and items[0]["publisher"] == "Outlet A"


def test_outlet_that_publishes_nothing_anywhere_is_dormant_not_an_error(monkeypatch):
    old = TODAY - timedelta(days=400)
    feeds = {"Quiet": "https://quiet.example/feed/"}
    routes = {"https://quiet.example/feed/": (200, rss(old), "application/rss+xml"),
              "https://quiet.example/": (200, "<html></html>", "text/html")}
    monkeypatch.setattr(fh.httpx, "AsyncClient", lambda **kw: client_for(routes))
    overrides, changes, unresolved, dormant = run(fh.heal_all(feeds, {}))
    assert overrides == {} and not unresolved and dormant and "stale since" in dormant[0]


def test_unreachable_outlet_with_no_replacement_is_an_error(monkeypatch):
    feeds = {"Gone": "https://gone.example/feed/"}
    monkeypatch.setattr(fh.httpx, "AsyncClient", lambda **kw: client_for({}))
    _, _, unresolved, dormant = run(fh.heal_all(feeds, {}))
    assert unresolved and not dormant


def test_quiet_newsletter_blocked_on_its_host_falls_back_to_site_news(monkeypatch):
    """Substack refuses data-centre addresses; a newsletter posting monthly has nothing in two weeks on Google News."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://news.google.com/"):
            body = rss() if f"when%3A{fh.CONFIRM_WINDOW_DAYS}d" in url else "<rss><channel></channel></rss>"
            return httpx.Response(200, text=body, headers={"content-type": "application/xml"})
        return httpx.Response(403, text="blocked", headers={"content-type": "text/html"})
    monkeypatch.setattr(fh.httpx, "AsyncClient", lambda **kw: _RealClient(transport=httpx.MockTransport(handler)))
    overrides, _, unresolved, _ = run(fh.heal_all({"The Big Deal": "https://thebigdeal.substack.com/feed"}, {}))
    assert not unresolved
    url = overrides["The Big Deal"]["url"]
    assert "site%3Athebigdeal.substack.com" in url and "when%3A2d" in url
