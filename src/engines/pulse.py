"""
Market pulse: what the deal and event flow looks like right now, for the public site.

Recomputed from the stored deals and events (refreshed daily by the ingest cron) and the
measured outcome tables (refreshed hourly from live outcomes), so the landing and
methodology pages describe the current state of the data rather than a fixed snapshot.
Every figure is a count or sum over stored records; nothing is estimated.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, timedelta
from typing import Iterable, Optional

from src.data import africa_countries as ac
from src.engines import investors as investors_mod

WINDOW_DAYS = 30
_FLOW_KIND = {"equity_funding": "equity", "debt_financing": "debt", "acquisition": "m_and_a", "merger": "m_and_a",
              "exit": "m_and_a", "fund_raise": "funds", "ipo": "listings"}
EVENT_DAYS = 7


def _country(code: Optional[str]) -> Optional[dict]:
    c = ac.get(code) if code else None
    return {"code": c.iso2, "name": c.name} if c else None


def _deal_card(d: dict) -> dict:
    src = (d.get("sources") or [{}])[0]
    return {"id": d["id"], "deal_type": d.get("deal_type"), "target": d.get("target"), "buyer": d.get("buyer"),
            "investors": (d.get("investors") or [])[:3], "amount_usd": d.get("amount_usd"),
            "country": _country(d.get("country")), "sector": d.get("sector"), "announced": d.get("announced"),
            "headline": d.get("headline"), "publisher": src.get("publisher")}


def _event_card(e: dict) -> dict:
    return {"id": e.get("id"), "signal_type": e.get("signal_type"), "direction": e.get("direction"),
            "country": _country(e.get("country")), "day": e.get("day"), "headline": e.get("headline"),
            "headline_en": e.get("headline_en"),
            "publisher": e.get("publisher"), "url": e.get("url")}


def build(deals: Iterable[dict], events: Iterable[dict], measured: dict, today: Optional[date] = None) -> dict:
    today = today or date.today()
    deals, events = list(deals), list(events)
    # Inclusive of today: a 30-day window is today and the 29 days before it.
    since = (today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    week = (today - timedelta(days=EVENT_DAYS - 1)).isoformat()
    recent = [d for d in deals if (d.get("announced") or "") >= since]
    recent.sort(key=lambda d: (d.get("announced") or "", d.get("amount_usd") or 0), reverse=True)
    recent_events = sorted((e for e in events if (e.get("day") or "") >= week),
                           key=lambda e: (e.get("day") or "", e.get("rule_score") or 0), reverse=True)

    def countries(rows: list[dict]) -> set[str]:
        return {c for d in rows for c in (d.get("countries") or [d.get("country")]) if c}

    by_country = Counter(c for d in recent for c in (d.get("countries") or [d.get("country")]) if c)
    disclosed = sorted((d["amount_usd"] for d in recent if d.get("amount_usd")), reverse=True)
    # A sum over reported amounts is dominated by a few large raises (a development bank's bond, a credit line);
    # the median, the top three's share and the split by type say what the flow is made of.
    value_by_type: Counter = Counter()
    for d in recent:
        if d.get("amount_usd"):
            value_by_type[_FLOW_KIND.get(d.get("deal_type"), "other")] += d["amount_usd"]
    largest = max(recent, key=lambda d: d.get("amount_usd") or 0, default=None)
    # Registry-matched investors only: unmatched names include extraction noise.
    active = [i for i in investors_mod.leaderboard(recent, limit=200) if i.get("type")][:5] if recent else []
    dates = [d.get("announced") for d in deals if d.get("announced")] + [e.get("day") for e in events if e.get("day")]
    return {
        "as_of": today.isoformat(),
        "latest_record": max(dates) if dates else None,
        "deals": {
            "total": len(deals), "countries": len(countries(deals)),
            "since": since, "window_days": WINDOW_DAYS, "recent": len(recent), "recent_countries": len(countries(recent)),
            "recent_disclosed_usd": round(sum(disclosed)), "recent_disclosed_n": len(disclosed),
            "recent_disclosed_median_usd": round(statistics.median(disclosed)) if disclosed else None,
            "recent_top3_share": round(sum(disclosed[:3]) / sum(disclosed), 3) if disclosed else None,
            "recent_value_by_kind": {k: round(v) for k, v in value_by_type.most_common()},
            "by_type": dict(Counter(d.get("deal_type") or "other" for d in recent).most_common()),
            "top_countries": [{**_country(c), "deals": n} for c, n in by_country.most_common(6) if _country(c)],
            "largest": _deal_card(largest) if largest and largest.get("amount_usd") else None,
            "latest": [_deal_card(d) for d in recent[:6]],
            "active_investors": [{"name": i["name"], "type": i.get("type"), "deals": i["deal_count"]}
                                 for i in active],
        },
        "events": {
            "total": len(events), "window_days": EVENT_DAYS, "recent": len(recent_events),
            "by_type": dict(Counter(e.get("signal_type") or "other" for e in recent_events).most_common()),
            "latest": [_event_card(e) for e in recent_events[:6]],
        },
        "measured": measured,
    }
