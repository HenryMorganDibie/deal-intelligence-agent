"""Listed securities are named for what they are, and companies are counted once however their names are written."""
import pytest

from src.engines import company_directory as cd
from src.engines import markets as m

ROWS = [("jse", "INL", "Investec Group"), ("jse", "INP", "Investec Group"), ("jse", "INPR", "Investec Ltd"),
        ("jse", "INPP", "Investec Plc"), ("jse", "INPPR", "Investec Plc"), ("nsx", "IVD", "Investec Limited"),
        ("jse", "CPI", "Capitec Limited"), ("jse", "CPIP", "Capitec Limited"), ("jse", "ASETNC", "FirstRand Bank Limited"),
        ("jse", "AMC002", "The Standard Bank of South Africa Limited"), ("jse", "ADXOPP", "UBS AMC ADX Opportunity"),
        ("jse", "STX40", "Satrix 40 ETF"), ("luse", "REIZ", "Real Estate Investments Zambia"),
        ("luse", "REIZUSD", "Real Estate Investments Zambia"), ("nse", "KPLC-P4", "Kenya Power and Lighting Co. Plc 4% Preferential"),
        ("jse", "N91", "Ninety One Group"), ("jse", "NY1", "Ninety One Group"), ("jse", "FTA", "Fairvest Limited"),
        ("jse", "SHP", "Shoprite Holdings Ltd")]


@pytest.fixture
def rows():
    out = [{"exchange": e, "symbol": s, "name": n} for e, s, n in ROWS]
    m._classify_securities(out)
    m._mark_cross_listings(out)
    return {r["symbol"]: r for r in out}


def test_dual_listed_companies_are_named_apart(rows):
    assert (rows["INL"]["name"], rows["INP"]["name"]) == ("Investec Ltd", "Investec plc")
    assert (rows["NY1"]["name"], rows["N91"]["name"]) == ("Ninety One Ltd", "Ninety One plc")
    assert rows["INL"]["security"] == rows["INP"]["security"] == "ordinary"


def test_each_security_type_is_recognised(rows):
    assert {s: rows[s]["security"] for s in ("INPR", "INPP", "INPPR", "CPIP", "KPLC-P4")} == dict.fromkeys(
        ("INPR", "INPP", "INPPR", "CPIP", "KPLC-P4"), "preference")
    assert rows["CPIP"]["name"] == "Capitec preference shares" and rows["CPIP"]["listed_name"] == "Capitec Limited"
    assert {rows[s]["security"] for s in ("ASETNC", "AMC002", "ADXOPP")} == {"note"}
    assert rows["STX40"]["security"] == "fund" and rows["REIZUSD"]["security"] == "usd_line"
    assert rows["FTA"]["security"] == "share_class" and rows["SHP"]["security"] == "ordinary"


def test_a_cross_listing_points_to_the_primary_and_preference_shares_are_not_listings(rows):
    assert rows["IVD"]["secondary_of"] == "jse"
    assert "secondary_of" not in rows["INPR"]


def test_the_screen_shows_ordinary_shares_unless_asked():
    snap = {"quotes": {"jse": [{"symbol": s, "name": n, "price": 1.0, "date": "2026-11-10"} for e, s, n in ROWS if e == "jse"]}, "fx": {}}
    from datetime import date
    shares = m.screener(snap, today=date(2026, 11, 10))
    assert {r["symbol"] for r in shares["rows"]} == {"INL", "INP", "CPI", "N91", "NY1", "FTA", "SHP"}
    prefs = m.screener(snap, today=date(2026, 11, 10), securities="preference")
    assert {r["symbol"] for r in prefs["rows"]} == {"INPR", "INPP", "INPPR", "CPIP"}
    assert m.screener(snap, today=date(2026, 11, 10), securities="all")["total"] == len([1 for e, *_ in ROWS if e == "jse"])


@pytest.mark.parametrize("a, b", [("Kasapreko", "Kasapreko PLC"), ("Moniepoint", "Moniepoint Inc"), ("Fido", "FIDO"),
                                  ("NCBA", "NCBA Group"), ("Bank of Kigali", "Bank of Kigali Plc"),
                                  ("Johnvents", "Johnvents Group"), ("Chi Limited", "Chi Ltd")])
def test_one_company_however_written(a, b):
    assert cd.company_key(a) == cd.company_key(b)


@pytest.mark.parametrize("a, b", [("MTN Nigeria", "MTN Group"), ("Guinness Ghana", "Guinness Nigeria"),
                                  ("National Bank of Egypt", "National Bank of Kenya")])
def test_different_companies_stay_apart(a, b):
    assert cd.company_key(a) != cd.company_key(b)


def test_the_most_used_spelling_names_the_company():
    deals = [{"deal_type": "equity_funding", "target": t, "announced": d, "country": "GH"}
             for t, d in [("Kasapreko", "2024-01-01"), ("Kasapreko PLC", "2025-01-01"), ("Kasapreko", "2023-01-01")]]
    rows = cd.private_companies(deals)
    assert len(rows) == 1 and rows[0]["name"] == "Kasapreko" and rows[0]["deal_count"] == 3
