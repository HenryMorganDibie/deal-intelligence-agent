"""Deterministic helpers for improving research retrieval and evidence quality.

These checks are conservative triage aids, not substitutes for reading source documents.
"""
from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlparse

from src.data.africa_countries import get as get_country


_ACTIONS = {
    "acquisition": ("acquisition", "acquires", "acquired", "takeover", "merger", "buyout"),
    "equity_funding": ("funding", "raises", "raised", "series", "seed", "investment", "round"),
    "debt_financing": ("debt", "loan", "credit", "bond", "facility", "lending"),
    "fund_raise": ("fund close", "fundraise", "first close", "final close", "capital raise"),
    "ipo": ("ipo", "initial public offering", "listing"),
    "exit": ("exit", "divestment", "sold", "stake sale"),
}


def build_query_plan(question: str, parsed: dict, base_query: str, limit: int = 4) -> list[str]:
    """Build a small, diverse query plan from explicit entities and intent."""
    question = re.sub(r"\s+", " ", question).strip()
    queries: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" ,")
        if value and value.lower() not in {q.lower() for q in queries}:
            queries.append(value)

    add(base_query)
    companies = [str(x).strip() for x in parsed.get("companies", [])[:2] if str(x).strip()]
    countries = [get_country(str(x).strip()).name if get_country(str(x).strip()) else str(x).strip()
                 for x in parsed.get("countries", [])[:2] if str(x).strip()]
    deal_types = parsed.get("deal_types", [])
    action_terms = []
    for deal_type in deal_types:
        action_terms.extend(_ACTIONS.get(deal_type, ()))
    action = " OR ".join(f'"{term}"' for term in action_terms[:4])
    if companies:
        add(" ".join(companies) + (f" ({action})" if action else " company announcement official"))
        add(" ".join(companies) + " investor relations announcement filing")
    if countries and action:
        add(" ".join(countries) + f" ({action})")
    if not companies and not countries and len(queries) < limit:
        add(question + " official source")
    if countries and action and len(queries) > limit:
        queries = queries[:limit - 1] + [queries[-1]]
    return queries[:max(1, limit)]


def _amounts(text: str) -> list[tuple[str, float]]:
    """Return explicit currency-tagged amounts normalised to base currency units."""
    pattern = re.compile(
        r"(?P<currency>US\$|USD|\$|EUR|€|GBP|£|NGN|₦|KES|KSh|ZAR|R)\s*"
        r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>trillion|billion|million|mn|bn|m|k)?",
        re.IGNORECASE,
    )
    multipliers = {"k": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
                   "bn": 1e9, "billion": 1e9, "trillion": 1e12}
    out = []
    for match in pattern.finditer(text or ""):
        currency = match.group("currency").upper()
        currency = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "₦": "NGN",
                    "KSH": "KES", "R": "ZAR"}.get(currency, currency)
        value = float(match.group("number").replace(",", "")) * multipliers.get((match.group("unit") or "").lower(), 1)
        out.append((currency, value))
    return out


def detect_evidence_conflicts(items: list[dict], companies: list[str] | None = None) -> list[dict]:
    """Flag potentially conflicting explicit amounts for a named company.

    Only reports a conflict when at least two source items mention the same requested
    company and contain different explicit amounts in the same currency. This is a
    review queue, not an automatic decision about which report is correct.
    """
    companies = [c for c in (companies or []) if len(str(c).strip()) >= 3]
    if not companies:
        return []
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        haystack = f"{item.get('title', '')} {item.get('text', '')}"
        for company in companies:
            if company.casefold() in haystack.casefold():
                for currency, value in _amounts(haystack):
                    groups[f"{company.casefold()}::{currency}"].append({
                        "company": company, "currency": currency, "value": value,
                        "n": item.get("n"), "title": item.get("title", ""),
                        "url": item.get("url"), "source": item.get("source"),
                        "date": item.get("date"),
                    })
    groups = {key: [row for row in rows if sum(1 for other in rows if other.get("n") == row.get("n")) == 1] for key, rows in groups.items()}
    conflicts = []
    for key, rows in groups.items():
        distinct = sorted({round(row["value"], 2) for row in rows})
        if len(distinct) < 2:
            continue
        # Different stories may repeat the same figure. Emit only if distinct values
        # occur across separate evidence items.
        conflicts.append({
            "type": "reported_amount_disagreement",
            "company": rows[0]["company"],
            "currency": rows[0]["currency"],
            "values": [{"value": value, "evidence": [r["n"] for r in rows if round(r["value"], 2) == value]}
                       for value in distinct],
            "message": f"Sources report different explicit {rows[0]['currency']} amounts for {rows[0]['company']}; verify the transaction, currency, and whether figures describe funding, valuation, or a different stage.",
        })
    return conflicts


def research_limitations(parsed: dict, items: list[dict], conflicts: list[dict]) -> list[str]:
    """Describe observable limitations without claiming that search was exhaustive."""
    notes = []
    if not items:
        notes.append("No evidence items were retrieved; this is not proof that no relevant activity exists.")
    if items and not any(item.get("url") for item in items):
        notes.append("Retrieved evidence has no direct links, so the underlying claims cannot be independently checked here.")
    if any(not item.get("date") for item in items):
        notes.append("Some evidence has no publication date; recency could not be established for those items.")
    news_items = [item for item in items if item.get("kind") == "news"]
    if news_items and not any(item.get("content_status") == "article_text_retrieved" for item in news_items):
        notes.append("Live-news evidence contains snippets rather than retrieved publisher article text; material claims need direct source review.")
    if conflicts:
        notes.append("At least one company/amount disagreement needs human review before using the figure.")
    if parsed.get("since") or parsed.get("until"):
        notes.append("Date filtering excludes items with unknown dates; relevant undated coverage may therefore be missing.")
    notes.append("Search results are a bounded sample, not a guarantee of exhaustive market coverage.")
    return list(dict.fromkeys(notes))


def benchmark_metrics(
    expected_ids: list[str],
    retrieved_ids: list[str],
    relevant_claims: list[bool] | None = None,
    field_accuracy_labels: list[bool] | None = None,
    unknown_handling_labels: list[bool] | None = None,
    expected_conflict_ids: list[str] | None = None,
    detected_conflict_ids: list[str] | None = None,
) -> dict:
    """Calculate metrics only from independently reviewed labels."""
    expected = set(expected_ids)
    retrieved = set(retrieved_ids)
    hits = len(expected & retrieved)
    # Empty denominators are undefined, not perfect scores. If expected sources exist
    # but retrieval returns none, precision is set to zero to reflect a failed retrieval.
    precision = hits / len(retrieved) if retrieved else (0.0 if expected else None)
    recall = hits / len(expected) if expected else None

    def rate(values: list[bool] | None) -> float | None:
        if not values:
            return None
        if any(type(value) is not bool for value in values):
            raise ValueError("benchmark labels must be true/false booleans")
        return round(sum(values) / len(values), 4)

    expected_conflicts = set(expected_conflict_ids or [])
    detected_conflicts = set(detected_conflict_ids or [])
    conflict_metrics = None
    if expected_conflict_ids is not None and detected_conflict_ids is not None:
        conflict_hits = len(expected_conflicts & detected_conflicts)
        conflict_metrics = {
            "precision": round(conflict_hits / len(detected_conflicts), 4) if detected_conflicts else
                         (1.0 if not expected_conflicts else 0.0),
            "recall": round(conflict_hits / len(expected_conflicts), 4) if expected_conflicts else 1.0,
            "expected": len(expected_conflicts),
            "detected": len(detected_conflicts),
        }
    claims = relevant_claims or []
    return {
        "retrieval_precision": round(precision, 4),
        "retrieval_recall": round(recall, 4),
        "retrieved_relevant": hits,
        "expected_relevant": len(expected),
        "retrieved_count": len(retrieved),
        "claim_support_rate": rate(claims),
        "claim_count": len(claims),
        "field_accuracy_rate": rate(field_accuracy_labels),
        "field_count": len(field_accuracy_labels or []),
        "unknown_handling_rate": rate(unknown_handling_labels),
        "unknown_handling_count": len(unknown_handling_labels or []),
        "conflict_detection": conflict_metrics,
    }
