"""Company identity beyond the statements: executives and address (Yahoo), NSE Kenya listing details."""
from src.engines import company_profile as cp
from src.engines import financials as fin

NSE_PAGE = """
<div class="toggle default"><h3 class="toggle-title"><a href="#" class="toggle-heading"><i class="fa"></i>BANKING</a></h3>
<div><h6>KCB Group Ltd Ord 1.00</h6><p>Trading Symbol:KCB</p><p>ISIN CODE:KE0000000315</p></div></div>
<div class="toggle default"><h3 class="toggle-title"><a href="#" class="toggle-heading"><i class="fa"></i>TELECOMMUNICATION AND TECHNOLOGY</a></h3>
<div><h6>Safaricom PLC Ord 0.05</h6><p>Trading Symbol:SCOM</p><p>ISIN CODE:KE1000001402</p></div>
<div><h6>ALP Industrial Real Estate Investment Trust</h6><p>Trading Symbol: </p><p>ALP</p><p>ISIN CODE: </p><p>KE9900006322</p></div></div>
"""


def test_nse_listed_page_gives_symbol_isin_and_sector(monkeypatch):
    rows = fin.parse_nse_listed(NSE_PAGE)
    assert [(r["symbol"], r["isin"], r["sector"]) for r in rows] == [
        ("KCB", "KE0000000315", "Banking"), ("SCOM", "KE1000001402", "Telecommunication And Technology"),
        ("ALP", "KE9900006322", "Telecommunication And Technology")]
    monkeypatch.setitem(fin._nse_listed_cache, "value", rows)
    monkeypatch.setitem(fin._nse_listed_cache, "at", 1e12)
    assert fin.nse_listing("Safaricom", "SCOM.NR")["isin"] == "KE1000001402"
    assert fin.nse_listing("KCB Group", None)["symbol"] == "KCB"
    assert fin.nse_listing("Unknown Co", None) is None


def test_yahoo_identity_carries_address_and_named_executives():
    info = {"address1": "1 Main Road", "city": "Johannesburg", "zip": "2196", "country": "South Africa",
            "companyOfficers": [{"name": "Jane  Doe", "title": "Chief Executive Officer", "yearBorn": 1970},
                                {"name": "No Title"}, {"name": "John Roe", "title": "CFO & Director"}]}
    assert cp._yahoo_address(info) == "1 Main Road, Johannesburg, 2196, South Africa"
    assert cp._yahoo_officers(info) == [{"name": "Jane Doe", "title": "Chief Executive Officer", "year_born": 1970},
                                         {"name": "John Roe", "title": "CFO & Director"}]
    assert cp._yahoo_address({}) is None and cp._yahoo_officers({}) == []


# ── Governance from the annual statements ─────────────────────────────────────

from src.engines import governance as gov  # noqa: E402

MTN_P2 = """MTN Nigeria Communications Plc
Corporate information
Registered company number 395010
Directors Name Nationality Position
Dr. Ernest Ndukwe, OFR Nigerian Chairman
Mr. Karl Toriola Nigerian Chief Executive Officer
Mr. Muhammad K. Ahmad, OON Nigerian Independent Non-Executive
Director
Ms. Tsholofelo Molefe South African Non-Executive Director
Registered office 4 Aromire road,
Off Alfred Rewane
Ikoyi Lagos
Holding company MTN International (Mauritius) Limited
Independent auditor Ernst & Young Nigeria
Company secretary Uto Ukpanah
Registrar Coronation Registrars Limited"""
MTN_P9 = """Directors' report
Substantial interest in shares
As at 31 December 2025, MTN International (Mauritius) Limited with total interest of 73.39% shareholding (2024:
73.39%) held more than 5% of the issued share capital of the Company."""
SUBS = """18.1 Investments in subsidiaries
Dangote Fuels Zambia Limited Zambia 99.00% 99.00%
Birat Cement Pvt. Limited Cement production and distribution Nepal 100.00% 100.00%"""


def _pages():
    return ["contents"] + [MTN_P2] + ["x"] * 6 + [MTN_P9, SUBS]         # p2, p9, p10


def test_governance_facts_are_kept_only_when_found_on_their_page():
    raw = {
        "rc_number": "RC 395010", "rc_page": 2, "registered_office": "4 Aromire road, Off Alfred Rewane, Ikoyi Lagos",
        "office_page": 2, "company_secretary": "Uto Ukpanah", "auditor": "Ernst & Young Nigeria",
        "registrar": "Coronation Registrars Limited", "holding_company": "MTN International (Mauritius) Limited",
        "corporate_page": 2,
        "board": [{"name": "Dr. Ernest Ndukwe, OFR", "role": "Chairman", "nationality": "Nigerian", "page": 2},
                  {"name": "Mr. Karl Toriola", "role": "Chief Executive Officer", "page": 2},
                  {"name": "Ms. Tsholofelo Molefe", "role": "Non-Executive Director", "nationality": "South African", "page": 2},
                  {"name": "Invented Person", "role": "Chairman", "page": 2},                 # not on the page
                  {"name": "Mr. Karl Toriola", "role": "Managing Director", "page": 2}],     # duplicate
        "shareholders": [{"name": "MTN International (Mauritius) Limited", "percent": "73.39", "page": 9},
                         {"name": "MTN International (Mauritius) Limited", "percent": "75.00", "page": 9},
                         {"name": "Stanbic Nominees", "percent": "6.10", "page": 9}],
        "subsidiaries": [{"name": "Dangote Fuels Zambia Limited", "country": "Zambia", "percent": "99.00", "page": 10},
                         {"name": "Birat Cement Pvt. Limited", "country": "Nepal", "percent": "100.00", "page": 10},
                         {"name": "Birat Cement Pvt. Limited", "percent": "100", "page": 2}],          # wrong page
    }
    out = gov.verify(raw, _pages(), allowed=[2, 9, 10])
    assert out["rc_number"] == "395010" and out["company_secretary"] == "Uto Ukpanah"
    assert out["registered_office"].startswith("4 Aromire road") and out["holding_company"].startswith("MTN International")
    assert [b["name"] for b in out["board"]] == ["Dr. Ernest Ndukwe, OFR", "Mr. Karl Toriola", "Ms. Tsholofelo Molefe"]
    assert out["board"][0] == {"name": "Dr. Ernest Ndukwe, OFR", "page": 2, "role": "Chairman", "nationality": "Nigerian"}
    assert out["shareholders"] == [{"name": "MTN International (Mauritius) Limited", "page": 9, "percent": 73.39}]
    assert out["subsidiaries"] == [{"name": "Dangote Fuels Zambia Limited", "page": 10, "percent": 99.0, "country": "Zambia"},
                                   {"name": "Birat Cement Pvt. Limited", "page": 10, "percent": 100.0, "country": "Nepal"}]
    # A page that was not given to the reader cannot be cited.
    assert gov.verify({"rc_number": "395010", "rc_page": 2}, _pages(), allowed=[9]) == {}


def test_extract_reads_each_kind_of_fact_in_its_own_pass(monkeypatch):
    monkeypatch.setattr(gov, "page_texts", lambda data, max_pages=gov.MAX_PAGES: _pages())
    monkeypatch.setattr(gov, "is_scanned", lambda pages: False)        # the sample pages are short, not a scan
    prompts = []

    def model(system, user):
        prompts.append(user)
        if "[p 9]" in user and "[p 2]" not in user:            # the shareholders pass
            return '{"shareholders": [{"name": "MTN International (Mauritius) Limited", "percent": "73.39", "page": 9}]}'
        return 'Here it is: {"rc_number": "395010", "rc_page": 2}' if "[p 2]" in user else "{}"
    out = gov.extract(b"pdf", "MTN Nigeria", "2025 AFS", "https://doclib.example/mtn.pdf", "2026-02-26", call=model)
    assert len(prompts) == 3                                    # corporate/board/committees, shareholders, subsidiaries
    assert any("[p 10]" in p and "[p 2]" not in p for p in prompts)     # subsidiaries read on their own
    assert out["rc_number"] == "395010" and out["shareholders"][0]["percent"] == 73.39
    assert out["source_url"] == "https://doclib.example/mtn.pdf" and {2, 9} <= set(out["pages_read"])
    assert out["source"].startswith("Annual financial statements filed with the exchange")
    assert gov.extract(b"pdf", "MTN", "d", "u", call=lambda s, u: "not json") is None


def test_subsidiary_pages_are_chosen_by_their_ownership_percentages():
    pages = ["Auditor's report: impairment of investment in subsidiaries", "a", SUBS + "\nAbc Ltd Ghana 51.00%"]
    assert 3 in gov.select_pages(pages) and 1 not in gov.select_pages(pages)



def test_a_scanned_filing_is_read_by_ocr_only_where_ocr_is_allowed(monkeypatch):
    blank = [""] * 5
    monkeypatch.setattr(gov, "page_texts", lambda data, max_pages=gov.MAX_PAGES: blank)
    monkeypatch.setattr(gov, "ocr_pages", lambda data, **k: _pages())
    model = lambda s, u: '{"rc_number": "395010", "rc_page": 2}'          # noqa: E731
    assert gov.is_scanned(blank) and not gov.is_scanned(["x" * 500] * 3)
    assert gov.extract(b"pdf", "MTN", "d", "u", call=model) is None                  # the profile: no OCR there
    out = gov.extract(b"pdf", "MTN", "d", "u", call=model, allow_ocr=True)            # the scheduled job
    assert out["rc_number"] == "395010" and out["ocr"] is True
