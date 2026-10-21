"""Full-history market profile of one country, from every deal and event record held for it.

The country page used to summarise only the latest records it fetched; this computes the same views
(flow, sectors, deal types, corroboration, largest deals) over the whole record since history begins.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import median
from typing import Iterable, Optional


def _year(value: Optional[str]) -> Optional[int]:
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        y = int(value[:4])
        return y if 1900 <= y <= 2100 else None
    return None


def _belongs(record: dict, iso2: str) -> bool:
    return iso2 in (record.get("countries") or [record.get("country")])


def build(iso2: str, deals: Iterable[dict], events: Iterable[dict], today: Optional[date] = None) -> dict:
    from src.engines import provenance

    today = today or date.today()
    country_deals = [d for d in deals if _belongs(d, iso2)]
    country_events = [e for e in events if _belongs(e, iso2)]

    amounts = [float(d["amount_usd"]) for d in country_deals if (d.get("amount_usd") or 0) > 0]
    corroborated = sum(1 for d in country_deals if len(provenance.stories(d.get("sources") or [])) >= 2)

    by_year: dict[int, dict] = defaultdict(lambda: {"deals": 0, "with_amount": 0, "disclosed_value_usd": 0.0, "events": 0})
    for d in country_deals:
        y = _year(d.get("announced"))
        if y is None:
            continue
        row = by_year[y]
        row["deals"] += 1
        if (d.get("amount_usd") or 0) > 0:
            row["with_amount"] += 1
            row["disclosed_value_usd"] += float(d["amount_usd"])
    for e in country_events:
        y = _year(e.get("day"))
        if y is not None:
            by_year[y]["events"] += 1

    def mix(key: str) -> list[dict]:
        counts: Counter = Counter()
        values: Counter = Counter()
        for d in country_deals:
            label = (d.get(key) or "").strip() or "unclassified"
            counts[label] += 1
            values[label] += float(d.get("amount_usd") or 0)
        return [{"label": label, "deals": n, "disclosed_value_usd": round(values[label])}
                for label, n in counts.most_common()]

    cutoff = date(today.year - 1, today.month, 1).isoformat()
    recent = [d for d in country_deals if (d.get("announced") or "") >= cutoff]
    months: Counter = Counter((d.get("announced") or "")[:7] for d in recent)

    largest = sorted((d for d in country_deals if (d.get("amount_usd") or 0) > 0),
                     key=lambda d: float(d["amount_usd"]), reverse=True)[:10]
    years = sorted(by_year)
    deal_years = [y for y in years if by_year[y]["deals"]]
    return {
        "first_year": deal_years[0] if deal_years else None,       # of the deal record; events may start earlier
        "last_year": deal_years[-1] if deal_years else None,
        "deals": len(country_deals),
        "events": len(country_events),
        "deals_with_amount": len(amounts),
        "disclosed_value_usd": round(sum(amounts)),
        "median_disclosed_usd": round(median(amounts)) if amounts else None,
        "corroborated_deals": corroborated,
        "single_source_deals": len(country_deals) - corroborated,
        "by_year": [{"year": y, **{k: (round(v) if isinstance(v, float) else v) for k, v in by_year[y].items()}}
                    for y in years],
        "by_month_last_12": [{"month": m, "deals": n} for m, n in sorted(months.items()) if m],
        "sectors": mix("sector"),
        "deal_types": mix("deal_type"),
        "event_types": [{"label": label, "events": n} for label, n in
                        Counter((e.get("signal_type") or "unclassified") for e in country_events).most_common()],
        "largest_deals": [{k: d.get(k) for k in ("id", "headline", "target", "buyer", "deal_type", "sector",
                                                  "amount_usd", "announced")} for d in largest],
    }
