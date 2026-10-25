from __future__ import annotations

import pytest

from evaluation.signals.score import SIGNAL_TYPES, _predict, _score, _validate_labels, _wilson
from src.schemas.models import SignalType


def test_wilson_reports_sample_size_and_interval():
    result = _wilson(8, 10)
    assert result["k"] == 8
    assert result["n"] == 10
    assert result["value"] == 0.8
    assert result["ci95"][0] < 0.8 < result["ci95"][1]
    assert _wilson(0, 0)["value"] is None


def test_predict_uses_the_supplied_rule_set_and_canonical_value():
    rules = [(SignalType.MA_ACTIVITY, [r"\bacquisition\b"], 0.8)]
    assert _predict("The acquisition was announced", rules) == {"m_and_a_activity"}
    assert _predict("The company hired a new CFO", rules) == set()


def test_validation_requires_all_items_and_known_signal_types():
    items = [{"item_id": "s000"}]
    valid = [{"item_id": "s000", "signal_types": ["credit_risk"], "confidence": "high", "market": "africa"}]
    assert _validate_labels(items, valid)["s000"]["signal_types"] == ["credit_risk"]
    with pytest.raises(SystemExit):
        _validate_labels(items, [])
    invalid = [{"item_id": "s000", "signal_types": ["new_ninth_type"], "confidence": "high", "market": "africa"}]
    with pytest.raises(SystemExit):
        _validate_labels(items, invalid)


def test_score_reports_per_type_false_positives_and_misses():
    items = [
        {"item_id": "s000", "title": "Acquisition announced", "snippet": "", "publisher": "Wire", "date": "2026-10-01"},
        {"item_id": "s001", "title": "The company refinanced its loan", "snippet": "", "publisher": "Wire", "date": "2026-10-02"},
    ]
    labels = {
        "s000": {"signal_types": ["m_and_a_activity"], "confidence": "high", "market": "africa"},
        "s001": {"signal_types": ["credit_risk"], "confidence": "high", "market": "africa"},
    }
    rules = [(SignalType.MA_ACTIVITY, [r"\bacquisition\b"], 0.8)]
    result = _score(items, labels, rules)
    assert result["by_signal_type"]["m_and_a_activity"]["tp"] == 1
    assert result["by_signal_type"]["credit_risk"]["fn"] == 1
    assert result["by_signal_type"]["credit_risk"]["fp"] == 0
    assert result["by_market"]["africa"]["items"] == 2
    assert set(result["by_signal_type"]) == set(SIGNAL_TYPES)
