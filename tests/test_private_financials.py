"""Private companies' financial statements: their own published accounts and UK Companies House filings."""
import httpx

from src.engines import companies_house as ch

IXBRL = """<html><body>
<ix:header><ix:resources>
<xbrli:context id="cy"><xbrli:entity/><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="py"><xbrli:entity/><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="cy_i"><xbrli:entity/><xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="seg"><xbrli:entity><xbrli:segment><xbrldi:explicitMember>x</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
</ix:resources></ix:header>
<td><ix:nonFraction name="uk-core:TurnoverRevenue" contextRef="cy" unitRef="GBP" scale="3" format="ixt:numdotdecimal">12,500</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:TurnoverRevenue" contextRef="py" unitRef="GBP" scale="3">8,000</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:ProfitLossOnOrdinaryActivitiesBeforeTax" contextRef="cy" unitRef="GBP" scale="3" sign="-">1,200</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:ProfitLoss" contextRef="cy" unitRef="GBP" scale="3" sign="-">1,200</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:Equity" contextRef="cy_i" unitRef="GBP" scale="3">3,400</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:Equity" contextRef="seg" unitRef="GBP" scale="3">99</ix:nonFraction></td>
<td><ix:nonFraction name="uk-core:CashBankOnHand" contextRef="cy_i" unitRef="GBP">-</ix:nonFraction></td>
<p>The group operates a digital bank in Nigeria.</p>
</body></html>"""


def test_ixbrl_accounts_are_read_with_scale_sign_and_prior_year():
    parsed = ch.parse_ixbrl(IXBRL)
    assert parsed["period"]["end"] == "2024-12-31"
    items = parsed["items"]
    assert items["revenue"]["current"] == 12_500_000 and items["revenue"]["prior"] == 8_000_000
    assert items["profit_before_tax"]["current"] == -1_200_000
    assert items["total_equity"]["current"] == 3_400_000             # the share-class segment is not the total
    assert items["cash"]["current"] == 0.0                            # a dash is a nil figure


def _api(search_items, filings=None, doc=IXBRL):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/search/companies":
            return httpx.Response(200, json={"items": search_items})
        if path.endswith("/filing-history"):
            return httpx.Response(200, json={"items": filings or [
                {"date": "2025-09-30", "action_date": "2024-12-31", "description": "accounts-with-accounts-type-full",
                 "links": {"document_metadata": "https://doc.example/document/abc"}}]})
        if path == "/document/abc":
            return httpx.Response(200, json={"resources": {"application/xhtml+xml": {}, "application/pdf": {}}})
        if path == "/document/abc/content":
            assert request.headers["accept"] == "application/xhtml+xml"
            return httpx.Response(200, text=doc)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_accounts_without_an_african_link_are_rejected():
    one = [{"title": "NAKED LTD", "company_number": "13690510", "company_status": "active"}]
    unrelated = IXBRL.replace("The group operates a digital bank in Nigeria.", "A clothing retailer in Leeds.")
    assert ch.accounts_for("Naked", client=_api(one, doc=unrelated), country="ZA") is None
    assert ch.accounts_for("Naked", client=_api(one), country="NG") is not None


def test_a_uk_named_company_is_labelled_a_subsidiary_and_exact_names_win():
    sub = [{"title": "FLUTTERWAVE UK LIMITED", "company_number": "10593971", "company_status": "active"}]
    acc = ch.accounts_for("Flutterwave", client=_api(sub), country="NG")
    assert acc["relation"] == "UK subsidiary"
    both = [{"title": "ACME UK LTD", "company_number": "1", "company_status": "active"},
            {"title": "ACME LTD", "company_number": "2", "company_status": "active"}]
    assert ch.find_company("Acme", _api(both))["company_number"] == "2"


def test_exact_unique_active_match_only():
    one = [{"title": "KUDA TECHNOLOGIES LTD", "company_number": "11223344", "company_status": "active"}]
    assert ch.find_company("Kuda Technologies", _api(one))["company_number"] == "11223344"
    similar = [{"title": "KUDA TECHNOLOGIES SERVICES LTD", "company_number": "1", "company_status": "active"}]
    assert ch.find_company("Kuda Technologies", _api(similar)) is None             # a different company
    dissolved = [{"title": "KUDA TECHNOLOGIES LTD", "company_number": "2", "company_status": "dissolved"}]
    assert ch.find_company("Kuda Technologies", _api(dissolved)) is None
    two = [{"title": "SPIRO LIMITED", "company_number": "3", "company_status": "active"},
           {"title": "SPIRO LTD", "company_number": "4", "company_status": "active"}]
    assert ch.find_company("Spiro", _api(two)) is None                              # ambiguous: show nothing


def test_accounts_for_returns_the_profile_shape():
    one = [{"title": "KUDA TECHNOLOGIES LTD", "company_number": "11223344", "company_status": "active"}]
    acc = ch.accounts_for("Kuda Technologies", client=_api(one), country="NG")
    assert acc["company_number"] == "11223344" and acc["currency"] == "GBP" and acc["filed"] == "2025-09-30"
    assert acc["items"]["revenue"]["current"] == 12_500_000
    assert "company/11223344/filing-history" in acc["source_url"]


def test_pdf_only_filings_are_skipped():
    def handler(request):
        if request.url.path == "/search/companies":
            return httpx.Response(200, json={"items": [{"title": "ACME LTD", "company_number": "9", "company_status": "active"}]})
        if request.url.path.endswith("/filing-history"):
            return httpx.Response(200, json={"items": [{"date": "2025-01-01", "links": {"document_metadata": "https://doc.example/document/p"}}]})
        return httpx.Response(200, json={"resources": {"application/pdf": {}}})
    assert ch.accounts_for("Acme", client=httpx.Client(transport=httpx.MockTransport(handler))) is None


def test_profile_prefers_the_company_s_own_statements_then_uk_accounts():
    from src.hosted_market import private_financials
    own = {"items": {"revenue": {"current": 5.0}, "total_assets": {"current": 9.0}}, "period": {"end": "2024-12-31"}}
    uk = {"items": {"revenue": {"current": 1.0}, "cash": {"current": 2.0}}, "company_name": "ACME LTD", "company_number": "9"}
    assert private_financials({"financials": own, "uk_accounts": uk})["source"].startswith("Statements published")
    assert "Companies House (ACME LTD, 9)" in private_financials({"uk_accounts": uk})["source"]
    assert private_financials({}) is None


def test_statement_pdfs_are_preferred_to_the_annual_report():
    from src import company_web as cw
    pages = [{"links": ["https://x.com/docs/annual-report-2024.pdf", "https://x.com/docs/audited-financial-statements-2024.pdf",
                        "https://x.com/docs/financial-statements-2023.pdf", "https://x.com/docs/agm-notice-2025.pdf"]}]
    assert cw.find_statements(pages) == "https://x.com/docs/audited-financial-statements-2024.pdf"
    assert cw.find_statements([{"links": ["https://x.com/annual-report-2024.pdf"]}]) == "https://x.com/annual-report-2024.pdf"


def test_newer_statement_wins():
    from src.company_live import _newer_statement
    old = {"period": {"end": "2023-12-31"}, "checks": [{"passed": True}]}
    new = {"period": {"end": "2024-12-31"}, "checks": []}
    assert _newer_statement(new, old) and not _newer_statement(old, new) and _newer_statement(old, None)
