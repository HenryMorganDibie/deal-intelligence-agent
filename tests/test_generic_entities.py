from datetime import date

from scripts.corporate_of_week import normalise, select_company
from src.engines.investors import split_names


def test_corporate_week_rejects_generic_and_accented_entities():
    assert normalise("Président") == "president"
    deals = [
        {"target": "Public", "headline": "Public debate over debt restructuring", "deal_type": "other"},
        {"target": "First", "headline": "First students stranded", "deal_type": "other"},
        {"target": "Président", "headline": "Président announces resignation", "deal_type": "other"},
        {"target": "Kenya Airways", "headline": "Kenya Airways names new chief executive", "deal_type": "other"},
    ]
    events = [
        {"headline": "Public debate over debt restructuring", "day": "2026-10-18",
         "signal_type": "leadership_change", "url": "https://example.com/public", "rule_score": 0.9, "credibility": 0.9},
        {"headline": "First students stranded after school trip", "day": "2026-10-18",
         "signal_type": "leadership_change", "url": "https://example.com/first", "rule_score": 0.9, "credibility": 0.9},
        {"headline": "Président announces resignation", "day": "2026-10-18",
         "signal_type": "leadership_change", "url": "https://example.com/president", "rule_score": 0.9, "credibility": 0.9},
        {"headline": "Kenya Airways appoints a new chief executive", "day": "2026-10-18",
         "signal_type": "leadership_change", "url": "https://example.com/kenya-airways", "rule_score": 0.9, "credibility": 0.9},
    ]
    result = select_company(deals, events, date(2026, 10, 12), date(2026, 10, 19))
    assert result["company"] == "Kenya Airways"
    assert all(row["company"].casefold() not in {"public", "first", "président"} for row in result["companies"])


def test_investor_profiles_reject_placeholder_parties():
    for placeholder in ("Public", "First", "Million", "Président", "Company", "Unknown", "Fund"):
        assert split_names(placeholder) == []
    assert split_names("International Finance Corporation") == ["International Finance Corporation"]
