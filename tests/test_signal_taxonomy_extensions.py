"""Regression tests for the strengthened eight-type signal taxonomy."""
import re

from src.engines.deterministic_engine import (
    SIGNAL_RULES,
    _classify_event_subtype,
    _extract_event_attributes,
)
from src.engines.deals import extract_deal
from src.schemas.models import SignalType


def matched_types(text: str) -> set[SignalType]:
    """Use the same compiled regex rules as production, without scoring side effects."""
    return {
        signal_type
        for signal_type, patterns, _score in SIGNAL_RULES
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    }


def test_ipo_exit_process_is_detected_without_adding_a_ninth_signal_type():
    assert SignalType.MA_ACTIVITY in matched_types(
        "The board approved IPO preparations and appointed advisers for the listing"
    )
    assert set(SignalType) == {
        SignalType.MA_ACTIVITY,
        SignalType.CREDIT_RISK,
        SignalType.DISTRESSED_ASSET,
        SignalType.EARNINGS_SURPRISE,
        SignalType.LEADERSHIP_CHANGE,
        SignalType.REGULATORY_ACTION,
        SignalType.DEBT_RESTRUCTURE,
        SignalType.INSIDER_ACTIVITY,
    }


def test_material_ipo_and_listing_decisions_map_to_regulatory_action():
    assert SignalType.REGULATORY_ACTION in matched_types(
        "The securities regulator approved the prospectus for the initial public offering"
    )
    assert SignalType.REGULATORY_ACTION in matched_types(
        "The exchange rejected the company's listing application"
    )


def test_ownership_changes_and_threshold_disclosures_map_to_insider_activity():
    assert SignalType.INSIDER_ACTIVITY in matched_types(
        "Investor discloses a change in beneficial ownership after acquiring a significant stake"
    )
    assert SignalType.INSIDER_ACTIVITY in matched_types(
        "Shareholder crosses the 10% disclosure threshold in voting rights"
    )


def test_refinancing_is_a_debt_event_not_automatically_a_credit_risk_signal():
    text = "The company refinances its existing bond facility"
    matches = matched_types(text)
    assert SignalType.DEBT_RESTRUCTURE in matches
    assert SignalType.CREDIT_RISK not in matches


def test_refinancing_with_explicit_credit_stress_can_trigger_both_types():
    matches = matched_types(
        "The company refinances its debt after a covenant breach and liquidity crisis"
    )
    assert SignalType.DEBT_RESTRUCTURE in matches
    assert SignalType.CREDIT_RISK in matches


def test_fundraising_and_debt_issuance_stay_in_the_transaction_feed_not_forced_into_risk_signals():
    equity = extract_deal(
        "Nigerian fintech Kora raises $20 million Series B funding round",
        published="2026-10-10",
        publisher="TechCabal",
        country_hint="NG",
    )
    debt = extract_deal(
        "Access Bank secures $300 million syndicated loan facility",
        published="2026-10-10",
        publisher="BusinessDay Nigeria",
        country_hint="NG",
    )
    assert equity is not None and equity["deal_type"] in {"equity_funding", "fund_raise"}
    assert debt is not None and debt["deal_type"] == "debt_financing"
    assert SignalType.INSIDER_ACTIVITY not in matched_types(
        "Nigerian fintech Kora raises $20 million Series B funding round"
    )


def test_specific_event_subtypes_are_retained_under_existing_canonical_types():
    assert _classify_event_subtype(
        SignalType.MA_ACTIVITY,
        "The board approved IPO preparations and appointed advisers for the listing",
    ) == "ipo_preparation"
    assert _classify_event_subtype(
        SignalType.INSIDER_ACTIVITY,
        "Investor discloses a change in beneficial ownership after acquiring a significant stake",
    ) == "beneficial_ownership_change"
    assert _classify_event_subtype(
        SignalType.DEBT_RESTRUCTURE,
        "The company refinances its existing bond facility",
    ) == "refinancing"
    assert _classify_event_subtype(
        SignalType.REGULATORY_ACTION,
        "The securities regulator approved the prospectus for the initial public offering",
    ) == "listing_approval"


def test_event_attributes_extract_only_facts_present_in_source_text():
    attributes = _extract_event_attributes(
        "The company secured a $250 million facility and sold a 12.5% stake; the new CEO confirmed the deal."
    )
    assert attributes["amount_mentions"]
    assert "12.5%" in attributes["percentage_mentions"]
    assert attributes["role_mentioned"].lower() == "ceo"
    assert "USD" not in attributes.get("currency_mentions", [])


def test_unclassified_event_subtype_is_explicit_not_guessed():
    assert _classify_event_subtype(
        SignalType.CREDIT_RISK,
        "The company reported a material financial development",
    ) == "unspecified"


def test_french_and_portuguese_subtypes_are_normalized_to_the_same_canonical_taxonomy():
    assert _classify_event_subtype(
        SignalType.DEBT_RESTRUCTURE,
        "La société annonce un refinancement de sa dette obligataire",
    ) == "refinancing"
    assert _classify_event_subtype(
        SignalType.INSIDER_ACTIVITY,
        "Franchissement de seuil et déclaration de participation",
    ) == "beneficial_ownership_change"
    assert _classify_event_subtype(
        SignalType.MA_ACTIVITY,
        "A empresa prepara uma oferta pública inicial e abertura de capital",
    ) == "ipo_preparation"
    assert _classify_event_subtype(
        SignalType.DEBT_RESTRUCTURE,
        "Banco fecha empréstimo sindicado para refinanciamento",
    ) == "refinancing"


def test_french_and_portuguese_headlines_trigger_canonical_signal_rules():
    french_ipo = matched_types(
        "La société prépare une introduction en bourse et son prospectus est approuvé"
    )
    assert SignalType.MA_ACTIVITY in french_ipo
    assert SignalType.REGULATORY_ACTION in french_ipo

    french_ownership = matched_types(
        "Franchissement de seuil et déclaration de participation au capital"
    )
    assert SignalType.INSIDER_ACTIVITY in french_ownership

    portuguese_debt = matched_types(
        "Banco anuncia refinanciamento da dívida através de empréstimo sindicado"
    )
    assert SignalType.DEBT_RESTRUCTURE in portuguese_debt
