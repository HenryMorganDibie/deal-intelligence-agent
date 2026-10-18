"""Reliability checks for analyst research source handling."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

import httpx

from src.engines import research


def test_source_assessment_distinguishes_primary_and_unrated_sources():
    label, note = research._source_assessment(
        "news", "https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm", "Federal Reserve"
    )
    assert label == "Official / primary"
    assert "official" in note.lower()

    label, note = research._source_assessment("news", "https://unknown-example.test/story", "Unknown Example")
    assert label == "Unrated publisher"
    assert "not independently rated" in note


def test_missing_direct_link_is_not_misrepresented_as_verified():
    label, note = research._source_assessment("news", None, "Unknown Publisher")
    assert label == "No direct source link"
    assert "cannot be independently checked" in note


def test_generic_research_search_is_not_forced_to_africa_and_can_use_primary_sources():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
      <title>Federal Reserve announces interest rate decision</title>
      <link>https://news.google.com/rss/articles/example</link>
      <description>Federal Reserve publishes its latest policy decision.</description>
      <source url="https://www.federalreserve.gov/">Federal Reserve</source>
      <pubDate>Sun, 18 Oct 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>"""

    class FakeClient:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            if "news.google.com/rss/search" in url:
                return httpx.Response(200, text=rss, request=httpx.Request("GET", url))
            destination = "https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm"
            return httpx.Response(200, text="official source", request=httpx.Request("GET", destination))

    client = FakeClient()
    results = research._news_items("Federal Reserve interest rate decision", None, client=client)
    search_urls = [u for u in client.urls if "news.google.com/rss/search" in u]
    assert search_urls
    decoded_query = unquote(urlparse(search_urls[0]).query)
    assert "Africa" not in decoded_query
    assert results
    assert results[0]["publisher"] == "Federal Reserve"



def test_primary_publisher_url_is_used_for_source_ranking():
    items = [
        {
            "title": "Federal Reserve policy update",
            "snippet": "Interest rate decision",
            "url": "https://news.google.com/rss/articles/aggregator",
            "publisher_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm",
            "publisher": "Federal Reserve",
            "date": "2026-10-18",
        },
        {
            "title": "Interest rate decision commentary",
            "snippet": "Analyst view of rates",
            "url": "https://unknown-example.test/story",
            "publisher_url": "https://unknown-example.test/story",
            "publisher": "Unknown Example",
            "date": "2026-10-18",
        },
    ]
    ranked = research._rank_news("Federal Reserve interest rate decision", items)
    assert ranked[0]["publisher"] == "Federal Reserve"


def test_citation_validator_warns_when_claim_and_source_look_unrelated():
    items = [
        {"n": 1, "title": "Federal Reserve holds interest rates", "text": "The central bank published its monetary policy decision."},
        {"n": 2, "title": "Kenya banking sector outlook", "text": "Banks reported changes in lending and deposits."},
    ]
    answer = "The Federal Reserve held interest rates steady after reviewing inflation and employment conditions [2]."
    result = research.validate_citations(answer, len(items), items=items)
    assert result["uncited_sentences"] == []
    assert result["weakly_supported_sentences"]
    assert result["weakly_supported_sentences"][0]["cited_items"] == [2]
    assert "text" in result["weakly_supported_sentences"][0]


def test_citation_validator_does_not_warn_for_overlapping_evidence():
    items = [
        {"n": 1, "title": "Federal Reserve holds interest rates", "text": "The central bank reviewed inflation and employment conditions."},
    ]
    answer = "The Federal Reserve held interest rates after reviewing inflation and employment conditions [1]."
    result = research.validate_citations(answer, len(items), items=items)
    assert result["weakly_supported_sentences"] == []


def test_research_prompt_handles_undated_evidence_and_conflicting_sources():
    assert "Treat missing publication dates as unknown" in research.SYSTEM
    assert "credible sources conflict" in research.SYSTEM
    block = research._evidence_block([
        {"n": 1, "kind": "news", "source": "Publisher", "date": None,
         "title": "Company financing", "text": "The company announced financing."}
    ])
    assert "undated" in block
