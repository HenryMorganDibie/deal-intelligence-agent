from src.engines.official_sources import audit_country, verify_url
from src.engines.provenance import verify


def test_official_source_requires_https_host_allowlist_match():
    assert verify_url("https://www.ngxgroup.com/market-data/", "NG")["status"] == "official_host_match"
    assert verify_url("http://www.ngxgroup.com/market-data/", "NG")["status"] == "invalid_or_non_https_url"
    assert verify_url("https://ngxgroup.com.attacker.example/fake", "NG")["status"] == "unverified_host"
    assert verify_url(None, "NG")["status"] == "missing_url"


def test_publisher_name_alone_does_not_make_a_source_official():
    deal = {
        "id": "test-deal", "country": "NG", "target": "Example", "deal_type": "equity_funding",
        "sources": [{"publisher": "NGX", "title": "Example raises funds", "url": "https://example.com/story", "date": "2026-01-01"}],
    }
    result = verify(deal)
    assert result["tier"] == "single source"
    assert result["official_source_verification"]["status"] == "no_official_host_verified"


def test_country_audit_exposes_missing_official_source_coverage():
    audit = audit_country("ER", [{"id": "d1", "country": "ER", "sources": [{"url": "https://example.com/a"}]}], [])
    assert audit["deal_records"] == 1
    assert audit["registered_country_hosts"] == 0
    assert audit["registry_status"] == "needs_host_review"



def test_official_source_audit_matches_country_names_and_iso_codes(monkeypatch):
    from src.engines import official_sources

    monkeypatch.setattr(
        official_sources,
        "verify_url",
        lambda url, country: {
            "status": "official_host_match" if url and "official.example" in url else "unverified_host",
            "host": "official.example" if url else None,
            "matched_registry": "country" if url else None,
        },
    )
    deals = [
        {"id": "one", "country": "Nigeria", "url": "https://official.example/deal"},
        {"id": "two", "countries": ["NG"], "url": "https://news.example/deal"},
        {"id": "three", "country": "Kenya", "url": "https://official.example/other"},
    ]
    events = [
        {"id": "event-one", "countries": ["Nigeria"], "url": "https://official.example/event"},
        {"id": "event-two", "country": "NG"},
    ]

    result = official_sources.audit_country("NG", deals, events)

    assert result["deal_records"] == 2
    assert result["event_records"] == 2
    assert result["deal_records_with_official_host"] == 1
    assert result["event_records_with_official_host"] == 1
    assert result["records_without_source_url"] == 1
    assert result["unverified_or_invalid_source_urls"] == 1


def test_official_registry_covers_all_supported_african_countries():
    from src.engines import official_sources
    from src.data.africa_countries import COUNTRIES

    missing = sorted(country.iso2 for country in COUNTRIES if country.iso2 not in official_sources.OFFICIAL_HOSTS_BY_COUNTRY)
    assert missing == []



def test_google_news_wrapper_is_not_misclassified_as_invalid_or_official():
    result = verify_url("https://news.google.com/rss/articles/CBMiExample", "NG")
    assert result["status"] == "news_wrapper_unresolved"
    assert result["host"] == "news.google.com"


def test_audit_separates_unverified_hosts_invalid_urls_and_news_wrappers():
    deals = [
        {"id": "official", "country": "NG", "sources": [{"url": "https://www.ngxgroup.com/market-data/"}]},
        {"id": "publisher", "country": "NG", "sources": [{"url": "https://example-news.test/article"}]},
        {"id": "wrapper", "country": "NG", "sources": [{"url": "https://news.google.com/rss/articles/CBMiExample"}]},
        {"id": "invalid", "country": "NG", "sources": [{"url": "http://example-news.test/article"}]},
        {"id": "missing", "country": "NG", "sources": []},
    ]
    result = audit_country("NG", deals, [])
    assert result["official_host_matched_links"] == 1
    assert result["unverified_publisher_source_urls"] == 1
    assert result["unresolved_news_wrapper_source_urls"] == 1
    assert result["invalid_or_non_https_source_urls"] == 1
    assert result["records_without_source_url"] == 1
    assert result["unverified_or_invalid_source_urls"] == 2



def test_google_news_wrapper_uses_rss_publisher_host_for_official_match():
    deals = [{
        "id": "official-source-wrapper", "country": "NG",
        "sources": [{
            "publisher": "Nigerian Exchange",
            "url": "https://news.google.com/rss/articles/CBMiExample",
            "publisher_url": "https://www.ngxgroup.com/",
        }],
    }]
    result = audit_country("NG", deals, [])
    assert result["official_host_matched_links"] == 1
    assert result["news_wrapper_publisher_hosts_checked"] == 1
    assert result["unresolved_news_wrapper_source_urls"] == 0


def test_recognised_news_publisher_is_not_counted_as_official_or_unknown():
    deals = [{
        "id": "news-source", "country": "NG",
        "sources": [{
            "publisher": "Nairametrics",
            "url": "https://nairametrics.com/2026/10/25/example/",
        }],
    }]
    result = audit_country("NG", deals, [])
    assert result["official_host_matched_links"] == 0
    assert result["recognised_news_publisher_source_urls"] == 1
    assert result["unverified_publisher_source_urls"] == 0
