from src.engines.watch import (delivery_idempotency_key, matches, matches_event, matches_deal,
                               quality_metrics, rss, webhook_payload, alert_fingerprint)


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



def test_duplicate_records_merge_reasons_and_expose_only_known_evidence():
    event = {
        "id": "event-1",
        "day": "2026-10-20",
        "headline": "Acme expands in Ghana",
        "signal_type": "funding",
        "country": "GH",
        "url": "https://example.com/story",
        "publisher": "Example",
        "sources": [
            {"publisher": "Example", "url": "https://example.com/story"},
            {"publisher": "Wire", "url": "https://wire.example/story"},
        ],
        "independent_stories": 2,
        "verification": "corroborated",
    }
    alerts = matches(
        {"companies": ["Acme"], "countries": ["GH"]},
        [event, {**event, "country": "NG"}],
        [],
    )
    assert len(alerts) == 1
    assert alerts[0]["why"] == ["company: Acme", "country: GH"]
    assert alerts[0]["source_count"] == 2
    assert alerts[0]["independent_stories"] == 2
    assert alerts[0]["verification"] == "corroborated"
    assert len(alerts[0]["sources"]) == 2


def test_quality_metrics_are_coverage_not_an_accuracy_claim():
    metrics = quality_metrics([
        {"url": "https://example.com", "independent_stories": 2, "verification": "corroborated"},
        {"url": None, "sources": [], "independent_stories": None, "verification": None},
    ])
    assert metrics["alert_count"] == 2
    assert metrics["source_evidence_coverage_pct"] == 50.0
    assert metrics["with_two_or_more_independent_stories"] == 1
    assert metrics["accuracy_estimate"] is None


def test_delivery_idempotency_key_is_stable_and_order_independent():
    a = [{"kind": "event", "id": "e2"}, {"kind": "deal", "id": "d1"}]
    b = list(reversed(a))
    assert delivery_idempotency_key("watch-1", a) == delivery_idempotency_key("watch-1", b)
    assert delivery_idempotency_key("watch-2", a) != delivery_idempotency_key("watch-1", a)



def test_material_changes_get_new_fingerprints_but_retries_are_stable():
    original = {
        "kind": "deal", "id": "deal-1", "day": "2026-10-20",
        "title": "Acme raises funding", "deal_type": "fundraising",
        "amount_usd": 1000000, "source_count": 1, "why": ["company: Acme"],
    }
    revised = {**original, "amount_usd": 1500000}
    assert alert_fingerprint(original) == alert_fingerprint(dict(original))
    assert alert_fingerprint(original) != alert_fingerprint(revised)
    assert delivery_idempotency_key("watch-1", [original]) != delivery_idempotency_key("watch-1", [revised])



def test_cross_source_event_duplicates_merge_by_exact_headline_date_type_and_country():
    first = {
        "id": "event-a", "day": "2026-10-20", "headline": "Acme secures new funding",
        "signal_type": "funding", "country": "GH", "url": "https://news-one.example/story",
        "publisher": "News One",
    }
    second = {
        "id": "event-b", "day": "2026-10-20", "headline": "Acme secures new funding",
        "signal_type": "funding", "country": "GH", "url": "https://news-two.example/story",
        "publisher": "News Two",
    }
    alerts = matches({"companies": ["Acme"], "countries": ["GH"]}, [first, second], [])
    assert len(alerts) == 1
    assert alerts[0]["id"] == "event-a"
    assert alerts[0]["source_count"] == 2
    assert {source["publisher"] for source in alerts[0]["sources"]} == {"News One", "News Two"}


def test_canonical_url_dedup_ignores_tracking_parameters():
    first = {
        "id": "event-a", "day": "2026-10-20", "headline": "Acme funding",
        "signal_type": "funding", "country": "GH", "url": "https://www.example.com/story?utm_source=a",
        "publisher": "Example",
    }
    second = {
        "id": "event-b", "day": "2026-10-20", "headline": "Different syndicated title",
        "signal_type": "funding", "country": "GH", "url": "https://example.com/story?utm_source=b",
        "publisher": "Example",
    }
    alerts = matches({"companies": ["Acme"], "countries": ["GH"]}, [first, second], [])
    assert len(alerts) == 1
    assert alerts[0]["source_count"] == 1
