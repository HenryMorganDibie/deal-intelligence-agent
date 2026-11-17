"""Credit risk events: rating actions, missed payments, bad loans and insolvency as African news reports them."""
from src.engines import market_feed as mf
from src.engines.deterministic_engine import _match_rules
from src.engines.event_filters import is_corporate_event

CREDIT = {"credit_risk", "distressed_asset", "debt_restructuring"}


def credit_type(title):
    hits = [s.value for s, _, _ in _match_rules(title) if s.value in CREDIT]
    return hits[0] if hits and is_corporate_event(title, hits[0]) else None


KEEP = [
    ("Moody's downgrades Senegal deeper into junk", "credit_risk"),
    ("Despite IMF bailout deal, Moody’s pushes Senegal’s rating deeper into junk", "credit_risk"),
    ("Fitch downgrades Ecobank Transnational to B-", "credit_risk"),
    ("Fitch places Access Bank on Rating Watch Negative", "credit_risk"),
    ("Union Bank non-performing loans rise to 8%", "credit_risk"),
    ("Ghana Cocoa Board misses coupon payment on loan", "credit_risk"),
    ("Concor enters business rescue", "distressed_asset"),
    ("The South African company that built the highest bridge in Africa is now in business rescue", "distressed_asset"),
]
DROP = [
    "Agusto Affirms Abbey Bank’s Ratings on Strong Liquidity Position",
    "Optimus Bank secures Agusto rating upgrade",
    "Moody’s Spares France Downgrade as Debt Risks Mount",
    "S&P lifts Ford outlook to stable on cost cuts and cash flow recovery",
    "Moody’s says South Africa’s budget update is credit positive",
    "Business rescue — lifeline or delay tactic for struggling companies?",
    "Kuru approved Arik Air receivership without AMCON board approval, witness tells court",
]


def test_african_credit_events_are_caught():
    for title, kind in KEEP:
        assert credit_type(title) == kind, title


def test_affirmations_upgrades_commentary_and_court_reports_are_not():
    for title in DROP:
        assert credit_type(title) is None, title


def test_business_rescue_is_placed_in_south_africa():
    ev = mf.to_events([{"title": "200-year-old retailer dumped by Woolworths enters business rescue", "snippet": "",
                        "publisher": "", "date": "2026-11-10"}])
    assert ev and ev[0]["signal_type"] == "distressed_asset" and "ZA" in (ev[0].get("countries") or [ev[0].get("country")])


def test_political_disputes_over_an_insolvency_are_not_credit_events():
    for title in ["Keyamo tackles Atiku over Nigeria Airways liquidation",
                  "Keyamo Accuses Atiku Of Hypocrisy Over Nigeria Airways Liquidation, Unpaid Workers’ Entitlements",
                  "Fani-Kayode Defends Obasanjo Over Nigeria Airways Liquidation",
                  "FT Group Petitions Tinubu, NDIC Over 30-Year Bank Liquidation Surplus, Dividends"]:
        assert credit_type(title) is None, title


def test_state_companies_are_placed_in_their_country():
    ev = mf.to_events([{"title": "KETRACO Faces Liquidation Petition Over Unpaid KSh 10b Award to Spanish Firm",
                        "snippet": "", "publisher": "", "date": "2026-10-15"}])
    assert ev and ev[0]["signal_type"] == "distressed_asset" and "KE" in (ev[0].get("countries") or [])
