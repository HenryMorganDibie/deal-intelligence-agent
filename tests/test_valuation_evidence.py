"""Valuation inputs are checked against evidence, not accepted on the strength of a URL."""
from datetime import date

from src.engines import valuation_evidence as ve

TODAY = date(2026, 10, 28)
LISTING = {"exchange": "ngx", "exchange_name": "Nigerian Exchange", "price": 1341.9, "currency": "NGN",
           "date": "2026-10-27", "shares": 16.87e9}
DOC = ("Dangote Cement Plc Audited results for the year ended 31 December 2025. Cash and cash equivalents "
       "412,345,000 Total borrowings 1,250,600 ... Free cash flow 845.2")


def _inputs(**kw):
    base = {"company": "Dangote Cement", "method": "dcf", "currency": "NGN", "period": "2025-12-31",
            "source": "https://doclib.ngxgroup.com/Financial_NewsDocs/dangcem-fy2025.pdf", "price": 1341.9,
            "price_date": "2026-10-27", "shares": 16.9e9, "fcf": 845.2e9, "cash": 412.345e9, "debt": 1250.6e9}
    return {**base, **kw}


def test_figures_found_in_an_official_filing_and_a_matching_exchange_close_allow_a_verdict():
    r = ve.check(_inputs(), LISTING, fetch=lambda url: (DOC, "ok"), today=TODAY)
    assert r["document"]["standing"] == "official" and r["document"]["names_company"] and r["document"]["states_period"]
    assert {r["fields"][k]["status"] for k in ("fcf", "cash", "debt")} == {"found"}    # millions and thousands
    assert r["fields"]["price"]["status"] == "verified" and r["fields"]["shares"]["status"] == "verified"
    assert r["verdict_allowed"] and r["grade"] == "B"


def test_any_url_is_not_enough():
    r = ve.check(_inputs(source="https://example.com/"), LISTING, fetch=lambda url: ("Example Domain", "ok"), today=TODAY)
    assert r["fields"]["fcf"]["status"] == "not_found" and not r["verdict_allowed"]
    assert any("neither an exchange" in reason for reason in r["reasons"])


def test_wrong_price_shares_or_currency_are_mismatches():
    r = ve.check(_inputs(price=1066.7, shares=10e9, currency="USD"), LISTING, fetch=lambda url: (DOC, "ok"), today=TODAY)
    assert {k for k, f in r["fields"].items() if f["status"] == "mismatch"} == {"price", "shares", "currency"}
    assert r["grade"] == "D" and not r["verdict_allowed"]


def test_parsed_filing_figures_verify_inputs_and_stale_prices_block_the_verdict():
    filing = {"source_url": _inputs()["source"], "verified": True,
              "items": {"cash": {"current": 412.345e9}, "total_debt": {"current": 1250.6e9}, "fcff": {"current": 845.2e9}}}
    r = ve.check(_inputs(), LISTING, filing, fetch=lambda url: (None, "http_403"), today=TODAY)
    assert r["grade"] == "A" and r["fields"]["cash"]["status"] == "verified"
    stale = ve.check(_inputs(price_date="2026-09-01"), {**LISTING, "date": "2026-09-01"}, filing,
                     fetch=lambda url: (None, "http_403"), today=TODAY)
    assert stale["freshness"]["price_stale"] and not stale["verdict_allowed"]


def test_company_site_standing_and_unsafe_urls():
    assert ve.source_standing("https://investors.mtn.com/report.pdf", "www.mtn.com") == "company"
    assert ve.source_standing("https://www.sec.gov/Archives/x.htm") == "official"
    assert ve.fetch_text("http://127.0.0.1/secret") == (None, "blocked")
    assert ve.fetch_text("http://localhost/x") == (None, "blocked")


def test_small_numbers_are_not_matched_by_accident():
    assert ve.figure_in_text(12.0, "Note 12 and page 12") is None
    assert ve.figure_in_text(1_250_600_000, "Total borrowings 1,250,600") == "1,250,600"


def test_evidence_endpoint_uses_the_listing_and_profile(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm
    from src.engines import markets

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._markets_cache.clear()
    markets.save_local({"quotes": {"ngx": [{"symbol": "DANGCEM", "name": "Dangote Cement", "price": 1341.9,
                                            "date": "2026-10-27", "mcap": 22.6e12, "shares": 16.87e9}]},
                        "indices": [], "fx": {}})

    async def fake_company(**kw):
        return {"financials": None, "identity": {}}
    monkeypatch.setattr(hm, "company", fake_company)
    monkeypatch.setattr(ve, "fetch_text", lambda url, client=None: (DOC, "ok"))
    body = {k: v for k, v in _inputs().items()}
    body.update(exchange="ngx", symbol="DANGCEM")
    r = TestClient(api.app).post("/api/valuation/evidence", json=body).json()
    assert r["fields"]["price"]["status"] == "verified" and r["grade"] == "B"


STATEMENT = """Dangote Cement Plc
Consolidated statement of financial position as at 31 December 2025
In millions of Naira    2025    2024
Revenue 4,200,000 3,580,000
Total assets 6,100,000 5,400,000
Total liabilities 3,900,000 3,500,000
Total equity 2,200,000 1,900,000
Cash and cash equivalents 412,345 389,100
Borrowings 1,250,600 1,100,200
Free cash flow 845,200 700,000
"""


def test_a_cited_statement_is_parsed_and_its_current_column_verifies_inputs():
    r = ve.check(_inputs(), LISTING, fetch=lambda url: (STATEMENT, "ok"), today=TODAY)
    assert r["document"]["read_as_statement"]
    assert r["fields"]["cash"]["status"] == "verified" and r["fields"]["debt"]["status"] == "verified"
    assert r["fields"]["fcf"]["status"] == "found"                  # on its labelled line; not a parsed item
    # The prior-year column is not the current figure.
    prior = ve.check(_inputs(cash=389.1e9), LISTING, fetch=lambda url: (STATEMENT, "ok"), today=TODAY)
    assert prior["fields"]["cash"]["status"] == "mismatch" and not prior["verdict_allowed"]


def test_a_number_under_another_line_item_does_not_count():
    doc = ("Dangote Cement Plc annual report for the year ended 31 December 2025\n"
           "Other operating income 412,345\nTotal borrowings 1,250,600\nFree cash flow 845.2\n")
    r = ve.check(_inputs(), LISTING, fetch=lambda url: (doc, "ok"), today=TODAY)
    assert r["fields"]["cash"]["status"] == "found_unlabelled"
    assert r["fields"]["debt"]["status"] == "found" and not r["verdict_allowed"]
    assert any("not under their line item" in reason for reason in r["reasons"])


def test_free_cash_flow_is_derived_and_borrowing_parts_are_summed():
    stmt = """Dangote Cement Plc
Statement of financial position and cash flows for the year ended 31 December 2025
In millions of Naira    2025    2024
Total assets 6,100,000 5,400,000
Total liabilities 3,900,000 3,500,000
Total equity 2,200,000 1,900,000
Cash and cash equivalents 412,345 389,100
Borrowings - non-current 1,000,600 900,200
Borrowings - current 250,000 200,000
Net cash generated from operating activities 1,100,000 950,000
Purchase of property, plant and equipment (254,800) (210,000)
"""
    r = ve.check(_inputs(), LISTING, fetch=lambda url: (stmt, "ok"), today=TODAY)
    assert r["fields"]["debt"]["status"] == "verified"                    # 1,000,600 + 250,000
    assert r["fields"]["fcf"]["status"] == "verified" and "less capital expenditure" in r["fields"]["fcf"]["note"]
    assert r["grade"] == "A" and r["verdict_allowed"]
    other = ve.check(_inputs(fcf=900e9), LISTING, fetch=lambda url: (stmt, "ok"), today=TODAY)
    assert other["fields"]["fcf"]["status"] == "differs_from_statement" and not other["verdict_allowed"]
