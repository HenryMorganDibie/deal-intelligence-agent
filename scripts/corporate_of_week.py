#!/usr/bin/env python3
"""Select and archive an evidence-backed Corporate of the Week from live deal records."""
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
    "fund", "consortium", "government", "unknown", "undisclosed",
}


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

    try:
        stories = max(1, int(deal.get("independent_stories") or len(deal.get("sources") or []) or 1))
    except (TypeError, ValueError):
        stories = 1
    corroboration_points = min(18.0, max(0.0, (stories - 1) * 6.0))
    score += corroboration_points
    reasons.append(
        f"Corroborated by {stories} independent stories" if stories >= 2
        else "Single-source reporting; corroboration is not assumed"
    )

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


def select_company(deals: list[dict], events: list[dict], start: date, end: date) -> dict:
    by_company: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    for deal in deals:
        company = str(deal.get("target") or "").strip()
        key = normalise(company)
        if not company or len(key) < 3 or key in GENERIC_TARGETS:
            continue
        if not within_period(deal.get("announced"), start, end):
            continue
        if not any(isinstance(source, dict) and source.get("url") for source in deal.get("sources") or []):
            continue
        by_company.setdefault(key, []).append(deal)
        names.setdefault(key, company)

    period_events = [event for event in events if within_period(event.get("day"), start, end)]
    ranked = []
    for key, company_deals in by_company.items():
        company = names[key]
        related = matched_events(company, period_events)
        scored = []
        for deal in company_deals:
            score, reasons = score_deal(deal, related, end)
            scored.append((score, deal, reasons))
        scored.sort(key=lambda row: (row[0], str(row[1].get("announced") or "")), reverse=True)
        best_score, best_deal, reasons = scored[0]
        score = round(best_score + min(10.0, (len(scored) - 1) * 3.0), 2)
        if len(scored) > 1:
            reasons.append(f"{len(scored)} reported transaction records involving this company in the period")

        sources = []
        seen_urls = set()
        for _, deal, _ in scored:
            for source in deal.get("sources") or []:
                url = source.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append({
                        "publisher": source.get("publisher") or "Source",
                        "title": source.get("title") or deal.get("headline") or company,
                        "url": url, "date": source.get("date") or deal.get("announced"), "kind": "deal",
                    })
        for event in related:
            url = event.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    "publisher": event.get("publisher") or "Source",
                    "title": event.get("headline") or company,
                    "url": url, "date": event.get("day"), "kind": "corporate_event",
                })
        try:
            stories = max([int(d.get("independent_stories") or len(d.get("sources") or []) or 1) for d in company_deals])
        except (TypeError, ValueError):
            stories = 1
        ranked.append({
            "company": company,
            "company_url": "/app/companies?name=" + quote(company),
            "headline": best_deal.get("headline") or f"{company}: reported {str(best_deal.get('deal_type') or 'corporate').replace('_', ' ')} activity",
            "deal_type": best_deal.get("deal_type") or "other",
            "amount_usd": best_deal.get("amount_usd"),
            "country": best_deal.get("country"),
            "sector": best_deal.get("sector"),
            "announced": best_deal.get("announced"),
            "score": score,
            "independent_stories": stories,
            "transaction_records": len(scored),
            "related_events": len(related),
            "reasons": reasons,
            "sources": sources[:8],
            "method": (
                "Deterministic ranking of eligible companies with a dated transaction and at least one inspectable source. "
                "Factors: transaction category, disclosed size, independent reporting, recency, matching corporate-event "
                "signals, and source availability. The score is a ranking aid, not a probability or investment recommendation."
            ),
        })
    if not ranked:
        raise RuntimeError(
            f"No eligible, source-linked company transaction found between {start} and {end}; "
            "refusing to publish an unsupported feature."
        )
    ranked.sort(
        key=lambda row: (row["score"], row["independent_stories"], row["transaction_records"], row["company"].casefold()),
        reverse=True,
    )
    winner = ranked[0]
    return {
        **winner,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "selection_version": 1,
        "runner_ups": [
            {"company": row["company"], "score": row["score"], "reasons": row["reasons"][:3]}
            for row in ranked[1:4]
        ],
    }


def build(api_base: str, output: Path, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    params = urlencode({"since": start.isoformat(), "until": end.isoformat(), "limit": 100})
    deals_payload = request_json(f"{api_base.rstrip('/')}/api/deals?{params}")
    events_payload = request_json(
        f"{api_base.rstrip('/')}/api/events?{urlencode({'since': start.isoformat(), 'limit': 500})}"
    )
    deals = deals_payload.get("deals")
    events = events_payload.get("events")
    if not isinstance(deals, list) or not isinstance(events, list):
        raise RuntimeError("API response did not contain the expected deals/events lists")
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
        "company": selected["company"],
        "period_start": selected["period_start"],
        "period_end": selected["period_end"],
        "score": selected["score"],
        "source_count": len(selected["sources"]),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
