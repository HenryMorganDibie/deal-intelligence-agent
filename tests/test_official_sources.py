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
