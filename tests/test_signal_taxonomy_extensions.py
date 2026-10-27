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



def test_mna_covers_divestitures_and_withdrawn_transactions():
    assert SignalType.MA_ACTIVITY in matched_types("The group agreed to sell its insurance subsidiary")
    assert SignalType.MA_ACTIVITY in matched_types("The acquisition was withdrawn after due diligence")


def test_credit_risk_covers_cash_runway_and_missed_payments_without_refinancing_false_positive():
    assert SignalType.CREDIT_RISK in matched_types("The startup has a cash runway of less than 4 months")
    assert SignalType.CREDIT_RISK in matched_types("The issuer missed its bond coupon payment")
    assert SignalType.CREDIT_RISK not in matched_types("The company refinanced its existing loan on improved terms")


def test_distressed_asset_covers_administration_and_creditor_liquidation():
    assert SignalType.DISTRESSED_ASSET in matched_types("The company was placed under administration by its creditors")
    assert SignalType.DISTRESSED_ASSET in matched_types("Creditors filed for compulsory liquidation")


def test_earnings_covers_guidance_withdrawal_and_estimate_surprises():
    assert SignalType.EARNINGS_SURPRISE in matched_types("The company withdrew its full-year earnings guidance")
    assert SignalType.EARNINGS_SURPRISE in matched_types("Revenue beat analyst estimates by 12 percent")


def test_leadership_covers_founder_and_c_suite_departures():
    assert SignalType.LEADERSHIP_CHANGE in matched_types("The founder stepped down as executive chair")
    assert SignalType.LEADERSHIP_CHANGE in matched_types("The chief financial officer resigned with immediate effect")


def test_regulatory_covers_license_status_and_competition_blocking():
    assert SignalType.REGULATORY_ACTION in matched_types("The regulator said the operating licence has been suspended")
    assert SignalType.REGULATORY_ACTION in matched_types("The competition authority blocked the proposed acquisition")


def test_debt_restructuring_covers_covenant_waivers_and_amend_extend():
    assert SignalType.DEBT_RESTRUCTURE in matched_types("Lenders granted a covenant waiver under an amend-and-extend agreement")


def test_insider_activity_covers_founder_stake_disposals():
    assert SignalType.INSIDER_ACTIVITY in matched_types("The founder sold a 20% stake in the company")


def test_routine_debt_issuance_and_ordinary_company_updates_are_not_distress_signals():
    routine_bond = matched_types("The company issued a $300 million bond to fund its expansion")
    assert SignalType.DEBT_RESTRUCTURE not in routine_bond
    assert SignalType.CREDIT_RISK not in routine_bond
    assert SignalType.DISTRESSED_ASSET not in routine_bond
    assert SignalType.DISTRESSED_ASSET not in matched_types("The company opened a new subsidiary in Ghana")


def test_new_event_variants_receive_specific_subtypes():
    cases = [
        (SignalType.MA_ACTIVITY, "The group agreed to sell its insurance subsidiary", "divestiture"),
        (SignalType.CREDIT_RISK, "The startup has a cash runway of less than 4 months", "cash_runway"),
        (SignalType.DISTRESSED_ASSET, "The company was placed under administration", "receivership_or_administration"),
        (SignalType.EARNINGS_SURPRISE, "The company withdrew its full-year earnings guidance", "guidance_revision"),
        (SignalType.LEADERSHIP_CHANGE, "The founder stepped down from the company", "founder_departure"),
        (SignalType.REGULATORY_ACTION, "The operating licence has been suspended", "licence_action"),
        (SignalType.DEBT_RESTRUCTURE, "Lenders granted a covenant waiver", "covenant_waiver"),
        (SignalType.INSIDER_ACTIVITY, "The founder sold a 20% stake in the company", "stake_disposal"),
    ]
    for signal_type, text, expected in cases:
        assert _classify_event_subtype(signal_type, text) == expected


def test_deal_sub_signals_are_named_within_the_eight_types():
    cases = {
        "Competition Commission approves Heineken's acquisition of Distell with conditions": "merger_control_filing",
        "COMESA Competition Commission clears Vodacom deal for Safaricom stake": "merger_control_filing",
        "Access Holdings launches N351bn rights issue to meet CBN recapitalisation": "capital_raise",
        "Zenith Bank plans to raise $500 million in equity": "capital_raise",
        "Seplat mandates banks for $650m Eurobond": "capital_raise",
        "Shell exploring sale of its Nigerian onshore business": "strategic_review",
        "Diageo puts its stake in Guinness Nigeria up for sale": "strategic_review",
        "MultiChoice weighs spin-off of Showmax": "strategic_review",
        "Procter & Gamble exits Nigerian market": "market_exit",
    }
    for text, subtype in cases.items():
        assert SignalType.MA_ACTIVITY in matched_types(text), text
        assert _classify_event_subtype(SignalType.MA_ACTIVITY, text) == subtype, text
    assert _classify_event_subtype(SignalType.CREDIT_RISK, "Auditor resigns from Tongaat Hulett citing irregularities") == "auditor_change"
    assert SignalType.CREDIT_RISK in matched_types("NGX suspends 13 companies for failure to file audited financial statements")
    for text in ("Unilever posts strong results as sales rise", "Messi exits the pitch"):
        assert SignalType.MA_ACTIVITY not in matched_types(text), text
