#!/usr/bin/env python3
"""Select and archive Corporate of the Week from the full company universe and dated event feed."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

DEFAULT_API = "https://deal-intelligence-api.vercel.app"
DEFAULT_OUTPUT = Path("web/data/corporate-of-week.json")
TYPE_WEIGHT = {
    "acquisition": 12, "merger": 12, "exit": 11, "ipo": 11,
    "equity_funding": 10, "debt_financing": 8, "joint_venture": 7,
    "fund_raise": 7, "other": 4,
}
GENERIC_TARGETS = {
    "africa", "african", "company", "startup", "startups", "firm", "group",
    "fund", "consortium", "government", "unknown", "undisclosed", "generic",
    # Common scraped headline fragments, not company names.
    "million", "millions", "president", "président", "presidente", "violators", "une",
    "startup", "bank", "company limited", "private limited",
}

# News stories dominated by transactions, politics, or sports are not corporate
# operating signals for this section, even when a parser labels them as leadership.
NON_CORPORATE_HEADLINE = re.compile(
    r"\b(?:merger|merges|merged|fusion|acquisition|acquires|acquired|takeover|buyout|"
    r"stake in|exit plans|raises? (?:usd|\$|€|£|\d)|funding round|"
    r"political party|\bpdp\b|\bfc\b|football|liga|league president|"
    r"mourns|election campaign)\b",
    re.IGNORECASE,
)


def normalise(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def request_json(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "DealIntelligence-CorporateOfWeek/1.0"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"API returned HTTP {response.status} for {url}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"API returned an unexpected payload for {url}")
    return payload


def within_period(value: str | None, start: date, end: date) -> bool:
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return False
    return start <= parsed <= end


def matched_events(company: str, events: list[dict]) -> list[dict]:
    key = normalise(company)
    if len(key) < 3:
        return []
    return [
        event for event in events
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", normalise(event.get("headline")))
    ]


_STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "as", "by", "with", "its", "from", "after", "new"}


def source_matches_deal(company: str, headline: str, source_title: str | None) -> bool:
    """Only count a source as corroboration when its title substantively matches this transaction."""
    title = normalise(source_title)
    company_key = normalise(company)
    if not title or not company_key or not re.search(r"(?<![a-z0-9])" + re.escape(company_key) + r"(?![a-z0-9])", title):
        return False
    headline_tokens = {token for token in normalise(headline).split() if token not in _STOPWORDS and len(token) > 1}
    source_tokens = {token for token in title.split() if token not in _STOPWORDS and len(token) > 1}
    if not headline_tokens or not source_tokens:
        return False
    similarity = len(headline_tokens & source_tokens) / max(1, len(headline_tokens | source_tokens))
    return similarity >= 0.30


def matching_deal_sources(company: str, deal: dict) -> list[dict]:
    headline = str(deal.get("headline") or "")
    matching = []
    for source in deal.get("sources") or []:
        title = source.get("title") or headline
        if source.get("url") and source_matches_deal(company, headline, title):
            matching.append(source)
    return matching


def score_deal(deal: dict, related_events: list[dict], end: date) -> tuple[float, list[str]]:
    reasons: list[str] = []
    kind = str(deal.get("deal_type") or "other")
    score = float(TYPE_WEIGHT.get(kind, TYPE_WEIGHT["other"]))
    reasons.append(f"Transaction category: {kind.replace('_', ' ')}")

    try:
        amount = float(deal["amount_usd"]) if deal.get("amount_usd") is not None else None
    except (TypeError, ValueError):
        amount = None
    if amount and amount > 0:
        amount_points = min(18.0, max(0.0, math.log10(amount / 1_000_000 + 1) * 5))
        score += amount_points
        reasons.append(f"Disclosed transaction size contributes {amount_points:.1f}/18 significance points")

    direct_sources = matching_deal_sources(str(deal.get("target") or ""), deal)
    try:
        reported_stories = max(1, int(deal.get("independent_stories") or len(deal.get("sources") or []) or 1))
    except (TypeError, ValueError):
        reported_stories = 1
    stories = min(reported_stories, len(direct_sources)) if direct_sources else 0
    corroboration_points = min(18.0, max(0.0, (stories - 1) * 6.0))
    score += corroboration_points
    if stories >= 2:
        reasons.append(f"Corroborated by {stories} independent stories matching the transaction headline")
    elif stories == 1:
        reasons.append("Only one source link directly matches the transaction headline; broader company coverage is not counted as corroboration")
    else:
        reasons.append("No source title directly corroborates this transaction headline; no corroboration points awarded")

    announced = str(deal.get("announced") or "")[:10]
    age = max(0, (end - date.fromisoformat(announced)).days) if announced else 7
    recency_points = max(0.0, 10.0 - age * (10.0 / 7.0))
    score += recency_points
    reasons.append(f"Recency: {age} day(s) before the selection period ended")

    if related_events:
        strongest = max(float(event.get("rule_score") or 0) for event in related_events)
        score += min(15.0, strongest * 15.0) + min(6.0, (len(related_events) - 1) * 3.0)
        reasons.append(f"{len(related_events)} related corporate-event signal(s) found in the same period")
    else:
        reasons.append("No matching corporate-event record was found; no event corroboration points awarded")

    if any(source.get("url") for source in deal.get("sources") or []):
        score += 5.0
        reasons.append("At least one inspectable source link is available")
    return round(score, 2), reasons


def _headline_overlap(left: str, right: str) -> bool:
    left_norm, right_norm = normalise(left), normalise(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    left_tokens = {token for token in left_norm.split() if token not in _STOPWORDS and len(token) > 2}
    right_tokens = {token for token in right_norm.split() if token not in _STOPWORDS and len(token) > 2}
    return bool(left_tokens and right_tokens) and len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens)) >= 0.65


def select_company(deals: list[dict], events: list[dict], start: date, end: date) -> dict:
    """Select companies with notable non-transaction events, not another copy of the deal feed."""
    company_names: dict[str, str] = {}
    company_deals: dict[str, list[dict]] = {}
    for deal in deals:
        company = str(deal.get("target") or "").strip()
        key = normalise(company)
        if not company or len(key) < 3 or key in GENERIC_TARGETS:
            continue
        company_names.setdefault(key, company)
        company_deals.setdefault(key, []).append(deal)

    period_events = [
        event for event in events
        if within_period(event.get("day"), start, end)
        and str(event.get("signal_type") or "").casefold() not in {"ma_activity", "m_and_a_activity", "m&a", "merger", "acquisition"}
        and event.get("url")
        and not NON_CORPORATE_HEADLINE.search(str(event.get("headline") or ""))
    ]
    ranked = []
    for key, company in company_names.items():
        relevant = [
            event for event in matched_events(company, period_events)
            if not any(_headline_overlap(str(event.get("headline") or ""), str(deal.get("headline") or ""))
                       for deal in company_deals.get(key, []))
        ]
        if not relevant:
            continue
        relevant.sort(
            key=lambda event: (
                str(event.get("day") or "")[:10],
                float(event.get("rule_score") or 0),
                float(event.get("credibility") or 0),
            ),
            reverse=True,
        )
        featured = relevant[0]
        signal = str(featured.get("signal_type") or "corporate_event")
        event_day = str(featured.get("day") or "")[:10] or None
        publishers = {str(event.get("publisher") or "").casefold() for event in relevant if event.get("publisher")}
        age = max(0, (end - date.fromisoformat(event_day)).days) if event_day else 7
        score = round(
            10.0
            + min(30.0, float(featured.get("rule_score") or 0) * 30.0)
            + min(15.0, float(featured.get("credibility") or 0) * 15.0)
            + max(0.0, 10.0 - age * (10.0 / 7.0))
            + min(10.0, max(0, len(publishers) - 1) * 5.0),
            2,
        )
        sources = []
        seen_urls = set()
        for event in relevant:
            url = event.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append({
                "publisher": event.get("publisher") or "Source",
                "title": event.get("headline") or company,
                "url": url,
                "date": event.get("day"),
                "kind": "corporate_event",
            })
        ranked.append({
            "company": company,
            "company_url": "/app/companies?name=" + quote(company),
            "headline": featured.get("headline") or f"{company}: corporate event",
            "deal_type": signal,
            "amount_usd": None,
            "country": featured.get("country"),
            "sector": featured.get("sector"),
            "announced": event_day,
            "score": score,
            "independent_stories": len(publishers),
            "transaction_records": 0,
            "related_events": len(relevant),
            "reasons": [
                f"Corporate signal: {signal.replace('_', ' ')}",
                f"Event rule confidence: {float(featured.get('rule_score') or 0):.2f}",
                f"{len(relevant)} distinct source-linked corporate event(s) found in the period",
                "Selected from corporate-event monitoring, not the transaction headline feed",
            ],
            "sources": sources[:8],
            "method": (
                "Deterministic ranking of dated, source-linked non-transaction corporate events. "
                "M&A signals and headlines substantially duplicating the deal feed are excluded. "
                "The score is an editorial ranking aid, not a probability or investment recommendation."
            ),
        })
    if not ranked:
        raise RuntimeError(
            f"No eligible, source-linked non-transaction corporate event found between {start} and {end}; "
            "refusing to duplicate the deal feed or publish unsupported entries."
        )
    ranked.sort(
        key=lambda row: (
            str(row.get("announced") or "")[:10],
            row["score"],
            row["independent_stories"],
            row["company"].casefold(),
        ),
        reverse=True,
    )
    # A single news story may name both a parent and subsidiary as separate targets.
    # Keep only one card for substantially identical headlines or overlapping source URLs.
    unique_ranked = []
    for row in ranked:
        row_urls = {source.get("url") for source in row["sources"] if source.get("url")}
        if any(
            normalise(row["headline"]) == normalise(prior["headline"])
            or bool(row_urls & {source.get("url") for source in prior["sources"] if source.get("url")})
            for prior in unique_ranked
        ):
            continue
        unique_ranked.append(row)
    if not unique_ranked:
        raise RuntimeError(
            f"No distinct, source-linked non-transaction corporate event found between {start} and {end}; "
            "refusing to duplicate the deal feed or publish unsupported entries."
        )
    selected_at = datetime.now(timezone.utc).isoformat()
    companies = [
        {
            **row,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "selected_at": selected_at,
            "selection_version": 3,
        }
        for row in unique_ranked[:5]
    ]
    winner = companies[0]
    return {
        **winner,
        "companies": companies,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "selected_at": selected_at,
        "selection_version": 3,
        "runner_ups": [
            {"company": row["company"], "score": row["score"], "reasons": row["reasons"][:3]}
            for row in unique_ranked[5:8]
        ],
    }

def build(api_base: str, output: Path, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    # Build the company universe from the full historical deal index, not only this
    # week's transactions. Otherwise companies with relevant leadership, earnings,
    # regulatory, or distress events but no fresh deal are silently excluded.
    deals: list[dict] = []
    offset = 0
    page_size = 100
    total_matching: int | None = None
    while total_matching is None or offset < total_matching:
        deals_payload = request_json(
            f"{api_base.rstrip('/')}/api/deals?{urlencode({'limit': page_size, 'offset': offset})}"
        )
        page = deals_payload.get("deals")
        if not isinstance(page, list):
            raise RuntimeError("API response did not contain the expected deals list")
        if total_matching is None:
            try:
                total_matching = int(deals_payload.get("total_matching", len(page)))
            except (TypeError, ValueError):
                total_matching = len(page)
        deals.extend(page)
        if not page or len(page) < page_size:
            break
        offset += len(page)

    events_payload = request_json(
        f"{api_base.rstrip('/')}/api/events?{urlencode({'since': start.isoformat(), 'limit': 500})}"
    )
    events = events_payload.get("events")
    if not isinstance(events, list):
        raise RuntimeError("API response did not contain the expected events list")
    selected = select_company(deals, events, start, end)

    previous = {"current": None, "history": []}
    if output.exists():
        try:
            loaded = json.loads(output.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                previous = loaded
        except (OSError, ValueError):
            raise RuntimeError(f"Existing archive at {output} is unreadable; refusing to overwrite it")
    history = [row for row in previous.get("history", []) if row.get("period_end") != selected["period_end"]]
    history.append(selected)
    history.sort(key=lambda row: row.get("period_end") or "")
    result = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current": selected,
        "history": history[-104:],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=DEFAULT_API)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        selected = build(args.api_base, args.output)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        print(f"Corporate of the Week update failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "companies": [row["company"] for row in selected.get("companies", [selected])],
        "period_start": selected["period_start"],
        "period_end": selected["period_end"],
        "company_count": len(selected.get("companies", [selected])),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
