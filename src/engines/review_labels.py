"""Validation and file layout for independent-review labels entered through the labelling page.

The rules follow evaluation/review/GUIDELINES.md. A label is cleaned to the guide's fields and allowed
values; anything else is dropped or rejected, so the stored set can be committed and scored as-is.
"""
from __future__ import annotations

import re
from typing import Any, Optional

DEAL_TYPES = ("equity_funding", "debt_financing", "acquisition", "merger", "exit", "fund_raise", "ipo", "joint_venture")
STAGES = ("rumoured", "announced", "completed")
AMOUNT_KINDS = ("deal_size", "valuation", "market_size", "programme_or_pledge", "none")
COUNTRY_BASES = ("named_in_headline", "known_entity", "unclear")
CONFIDENCE = ("high", "low")
ITEM_ID = re.compile(r"^r\d{3}$")
PAIR_ID = re.compile(r"^p\d{3}$")
_ISO2 = re.compile(r"^[A-Z]{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class LabelError(ValueError):
    pass


def _text(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LabelError("text fields must be strings")
    value = " ".join(value.split())[:limit]
    return value or None


def _choice(value: Any, allowed: tuple[str, ...], field: str) -> Optional[str]:
    if value in (None, ""):
        return None
    if value not in allowed:
        raise LabelError(f"{field} must be one of {', '.join(allowed)}")
    return value


def _flag(value: Any, field: str) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    raise LabelError(f"{field} must be true, false or empty")


def _number(value: Any, field: str, high: float) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= high:
        raise LabelError(f"{field} must be a number between 0 and {high:g}")
    return float(value)


def _code(value: Any, pattern: re.Pattern, field: str) -> Optional[str]:
    if value in (None, ""):
        return None
    value = str(value).strip().upper()
    if not pattern.fullmatch(value):
        raise LabelError(f"{field} must be a {'two' if pattern is _ISO2 else 'three'}-letter code")
    return value


def clean_item(label: dict) -> dict:
    """A headline label reduced to the guide's fields; raises LabelError on a value the guide does not allow."""
    if not isinstance(label, dict):
        raise LabelError("a label must be an object")
    parties = label.get("other_parties") or []
    if not isinstance(parties, list) or len(parties) > 10:
        raise LabelError("other_parties must be a list of up to ten names")
    out = {
        "is_transaction": _flag(label.get("is_transaction"), "is_transaction"),
        "in_scope": _flag(label.get("in_scope"), "in_scope"),
        "scope_reason": _text(label.get("scope_reason"), 200) or "",
        "deal_type": _choice(label.get("deal_type"), DEAL_TYPES, "deal_type"),
        "stage": _choice(label.get("stage"), STAGES, "stage"),
        "target": _text(label.get("target"), 120),
        "acquirer_or_lead": _text(label.get("acquirer_or_lead"), 120),
        "other_parties": [p for p in (_text(x, 120) for x in parties) if p],
        "amount": _number(label.get("amount"), "amount", 1e13),
        "currency": _code(label.get("currency"), _CURRENCY, "currency"),
        "amount_kind": _choice(label.get("amount_kind"), AMOUNT_KINDS, "amount_kind"),
        "stake_pct": _number(label.get("stake_pct"), "stake_pct", 100),
        "country": _code(label.get("country"), _ISO2, "country"),
        "country_basis": _choice(label.get("country_basis"), COUNTRY_BASES, "country_basis"),
        "africa_wide": _flag(label.get("africa_wide"), "africa_wide"),
        "asset_location": _code(label.get("asset_location"), _ISO2, "asset_location"),
        "language": _text(label.get("language"), 8),
        "confidence": _choice(label.get("confidence"), CONFIDENCE, "confidence"),
        "note": _text(label.get("note"), 500) or "",
    }
    if out["is_transaction"] is False:
        out["deal_type"] = None                       # the guide: no deal type when not a transaction
    if (out["is_transaction"] is False or out["in_scope"] is False) and not out["scope_reason"]:
        raise LabelError("scope_reason is required when the headline is not a transaction or not in scope")
    return out


def clean_pair(label: dict) -> dict:
    if not isinstance(label, dict):
        raise LabelError("a label must be an object")
    return {"same_transaction": _flag(label.get("same_transaction"), "same_transaction"),
            "confidence": _choice(label.get("confidence"), CONFIDENCE, "confidence"),
            "note": _text(label.get("note"), 500) or ""}


FILES = {("a", "item"): "labels_a.jsonl", ("b", "item"): "labels_b.jsonl",
         ("a", "pair"): "pair_labels_a.jsonl", ("b", "pair"): "pair_labels_b.jsonl",
         ("adjudicator", "item"): "adjudicated_labels.jsonl", ("adjudicator", "pair"): "adjudicated_pair_labels.jsonl"}


# The judgements that must match for A and B to agree; other fields (notes, confidence, language) may differ.
CORE_ITEM = ("is_transaction", "in_scope", "deal_type", "target", "amount", "currency", "amount_kind", "country")
CORE_PAIR = ("same_transaction",)


def _norm(field: str, value: Any) -> Any:
    return " ".join(value.lower().split()) if field == "target" and isinstance(value, str) else value


def disagreements(a: dict, b: dict, kind: str) -> list[str]:
    """Core fields on which two labels differ; empty when they agree."""
    return [f for f in (CORE_ITEM if kind == "item" else CORE_PAIR) if _norm(f, a.get(f)) != _norm(f, b.get(f))]


def _done(label: Optional[dict], kind: str) -> bool:
    return bool(label) and label.get("is_transaction" if kind == "item" else "same_transaction") is not None


def to_files(rows: list[dict], items: list[str], pairs: list[str]) -> dict[str, list[dict]]:
    """Exported rows laid out as the review folder's label files, one row per sampled id in order.

    Annotator files always list every id (blank where not yet labelled), as the drawn templates do. The
    adjudicated files hold the final label for each id that has one: the adjudicator's where they ruled,
    otherwise A's label where A and B agree on every core judgement. Ids still in dispute are left out."""
    by_key = {(r["role"], r["kind"], r["item_id"]): r for r in rows}
    row = lambda role, kind, i: {"item_id": i, "annotator": by_key[(role, kind, i)]["annotator"],  # noqa: E731
                                 **by_key[(role, kind, i)]["label"]}
    out: dict[str, list[dict]] = {}
    for (role, kind), name in FILES.items():
        ids = items if kind == "item" else pairs
        if role != "adjudicator":
            blank = clean_item({}) if kind == "item" else clean_pair({})
            out[name] = [row(role, kind, i) if (role, kind, i) in by_key else {"item_id": i, "annotator": "", **blank}
                         for i in ids]
            continue
        final = []
        for i in ids:
            ruled = by_key.get(("adjudicator", kind, i))
            a, b = by_key.get(("a", kind, i)), by_key.get(("b", kind, i))
            if ruled and _done(ruled["label"], kind):
                final.append({**row("adjudicator", kind, i), "resolution": "adjudicated"})
            elif a and b and _done(a["label"], kind) and _done(b["label"], kind) and not disagreements(a["label"], b["label"], kind):
                final.append({**row("a", kind, i), "annotator": f"{a['annotator']}; {b['annotator']}", "resolution": "agreed"})
        out[name] = final
    return out
