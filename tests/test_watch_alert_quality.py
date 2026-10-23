from src.engines.watch import matches, matches_event, matches_deal, rss, webhook_payload


def test_event_match_respects_signal_type_and_country():
    event = {
        "id": "event-1",
        "day": "2026-10-20",
        "headline": "Zenith Bank announces leadership change",
        "signal_type": "leadership",
        "country": "NG",
        "url": "https://example.com/story",
        "publisher": "Example",
    }
    watchlist = {"companies": ["Zenith Bank"], "countries": ["NG"], "signal_types": ["leadership"]}
    reasons = matches_event(event, watchlist)
    assert "company: Zenith Bank" in reasons
    assert "country: NG" in reasons
    assert matches_event(event, {**watchlist, "signal_types": ["funding"]}) == []


def test_deal_matching_can_be_disabled():
    deal = {
        "id": "deal-1",
        "announced": "2026-10-20",
        "headline": "Acquisition announced",
        "target": "Example Company",
        "country": "GH",
    }
    assert matches_deal(deal, {"companies": ["Example Company"], "countries": ["GH"], "include_deals": False}) == []


def test_matches_excludes_items_older_than_since_and_sorts_newest_first():
    events = [
        {"id": "old", "day": "2026-01-01", "headline": "Acme event", "signal_type": "funding", "country": "NG"},
        {"id": "new", "day": "2026-10-01", "headline": "Acme event", "signal_type": "funding", "country": "NG"},
    ]
    alerts = matches({"companies": ["Acme"]}, events, [], since="2026-09-01")
    assert [alert["id"] for alert in alerts] == ["new"]


def test_rss_escapes_untrusted_titles_and_uses_stable_guid():
    alert = {
        "kind": "event",
        "id": "event-<1>",
        "day": "2026-10-20",
        "title": "Company <script>alert(1)</script>",
        "signal_type": "funding",
        "url": "https://example.com/story?a=1&b=2",
        "why": ["company: Example"],
    }
    feed = rss({"name": "Watch & learn"}, [alert], "https://example.com/watch")
    assert "<script>" not in feed
    assert "&lt;script&gt;" in feed
    assert "event:event-&lt;1&gt;" in feed
    assert "Watch &amp; learn" in feed


def test_webhook_payload_has_watchlist_identity_and_alerts():
    alert = {"kind": "event", "id": "event-1", "title": "Example", "why": []}
    payload = webhook_payload({"id": "wl-1", "name": "Nigeria",}, [alert], "https://example.com/watch")
    assert payload["watchlist"] == {"id": "wl-1", "name": "Nigeria", "url": "https://example.com/watch"}
    assert payload["alerts"] == [alert]
    assert payload["generated_at"]
