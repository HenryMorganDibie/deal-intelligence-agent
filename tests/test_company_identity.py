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
    assert len(prompts) == len([g for g in gov.GROUPS if any(gov.section_pages(_pages(), k) for k in g)])   # a pass per group with pages
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


def test_a_fact_cited_on_the_wrong_page_is_kept_on_the_one_page_that_has_it():
    raw = {"board": [{"name": "Mr. Karl Toriola", "role": "Chief Executive Officer", "page": "118"}],      # printed page
           "shareholders": [{"name": "MTN International (Mauritius) Limited", "percent": "73.39", "page": 2}]}
    out = gov.verify(raw, _pages(), allowed=[2, 9, 10])
    assert out["board"] == [{"name": "Mr. Karl Toriola", "page": 2, "role": "Chief Executive Officer"}]
    assert out["shareholders"][0]["page"] == 9
    # Not on any page read: still dropped.
    assert gov.verify({"board": [{"name": "Invented Person", "page": 2}]}, _pages(), allowed=[2, 9, 10]) == {}


def test_corporate_page_beats_agm_notice_and_tables_run_onto_the_next_page():
    agm = "Notice of Annual General Meeting. Proxies ... the Office of the Registrars, Coronation Registrars Ltd ... auditors"
    corp = ("Corporate Information. Registration information RC Number 208767 Registered office Leadway Marble House "
            "Registrars Coronation Registrars Limited")
    holders = "Substantial interest in shares: the following held more than 5%"
    table = "Dangote Industries Ltd. % 86.65 Stanbic IBTC Nominees Ltd 5.47"
    pages = [agm, corp, "x " * 200, holders, table]
    assert gov.section_pages(pages, "corporate")[0] == 2
    assert gov.section_pages(pages, "shareholders")[:2] == [4, 5]
    raw = {"rc_number": "RC 208767", "rc_page": "214", "registrar": "Coronation Registrars Limited",
           "corporate_page": 214, "shareholders": [{"name": "Dangote Industries Ltd.", "percent": "86.65", "page": 101}]}
    out = gov.verify(raw, pages, allowed=[1, 2, 4, 5])
    assert out["rc_number"] == "208767" and out["registrar"] == "Coronation Registrars Limited"
    assert out["shareholders"] == [{"name": "Dangote Industries Ltd.", "page": 5, "percent": 86.65}]
    assert gov.verify({"rc_number": "1925/001431/06", "rc_page": 1}, ["Registration number: 1925/001431/06"], [1])["rc_number"] == "1925/001431/06"
    assert gov.verify({"rc_number": "2087", "rc_page": 1}, ["RC 208767"], [1]) == {}       # part of a number: no


def test_corporate_facts_written_as_objects_with_their_own_pages_are_read():
    raw = {"auditor": {"name": "Ernst & Young Nigeria", "page": 2}, "company_secretary": "Uto Ukpanah",
           "company_secretary_page": "p 2", "registrar": {"name": "Coronation Registrars Limited", "page": 99},
           "rc_number": {"number": "395010", "page": 2}}
    out = gov.verify(raw, _pages(), allowed=[2, 9, 10])
    assert out["auditor"] == "Ernst & Young Nigeria" and out["company_secretary"] == "Uto Ukpanah"
    assert out["registrar"] == "Coronation Registrars Limited"          # cited a page not read; found on p2
    assert out["rc_number"] == "395010"
    assert gov.GROUPS[0] == ("corporate",)                               # corporate details read on their own


def test_truncated_answer_keeps_completed_items():
    from src.engines import governance as g
    cut = '{"subsidiaries": [{"name": "Dangote Cement Zambia Limited", "percent": "99.96", "page": 166}, {"name": "Dang'
    assert g._json(cut) == {"subsidiaries": [{"name": "Dangote Cement Zambia Limited", "percent": "99.96", "page": 166}]}
    assert g._json("no json here") == {}


def test_compact_directors_list_outranks_profile_pages():
    from src.engines import governance as g
    compact = "Directors and professional advisers\nDirectors\n" + "\n".join(
        f"Person {i} Non-Executive Director" for i in range(12))
    profile = "Board of Directors\n" + "Mr A is a director and chairman of the board. " * 10
    assert g._score("board", compact) > g._score("board", profile)


def test_rereading_a_report_never_loses_confirmed_facts():
    from src.engines import governance as g
    old = {"source_url": "u", "checker": 2, "board": [{"name": f"Director {chr(65 + i)}"} for i in range(11)], "auditor": "KPMG", "auditor_page": 213,
           "committees": [{"name": "Audit"}], "pages_read": [92]}
    new = {"source_url": "u", "board": [{"name": "a"}] * 4, "subsidiaries": [{"name": "s"}] * 48, "pages_read": [166]}
    m = g.merge_reads(new, old)
    assert len(m["board"]) == 11 and len(m["subsidiaries"]) == 1 and m["committees"] == [{"name": "Audit"}]
    assert m["auditor"] == "KPMG" and m["auditor_page"] == 213 and m["pages_read"] == [92, 166]
    other = {**new, "source_url": "newer-report"}
    assert g.merge_reads(other, old) is other          # a new report replaces the old one's facts
    assert g.merge_reads(None, old) is None


def test_board_initials_merge_into_the_full_name():
    from src.engines import governance as g
    board = [{"name": "Koos Bekker"}, {"name": "JP Bekker"}, {"name": "Fabricio Bloisi"}, {"name": "F Bloisi"},
             {"name": "Aliko Dangote"}, {"name": "Mariya Aliko Dangote"}, {"name": "A Smith"}]
    names = [d["name"] for d in g.dedupe_board(board)]
    assert names == ["Koos Bekker", "Fabricio Bloisi", "Aliko Dangote", "Mariya Aliko Dangote", "A Smith"]


def test_profile_style_board_pages_and_shareholder_analysis_are_found():
    from src.engines import governance as g
    profiles = "Our board and management\n" + "\n".join(
        f"Person {i}\n60, female, South African\nIndependent non-executive director\nDate of first appointment"
        for i in range(6))
    assert g._score("board", profiles) > g._score("board", "Board of directors met four times.")
    analysis = "Analysis of shareholders\nPublic Investment Corporation 22.53 172 387 018"
    assert g._score("shareholders", analysis) > 0


def test_departed_directors_and_layout_board_check():
    from src.engines import governance as g
    footnoted = ("Directors\nAliko Dangote, GCON* Chairman\nEmmanuel Ikazoboh** Independent Non-Executive Director\n"
                 "Arvind Pathak Group Managing Director\n* Retired effective 25 July 2025\n"
                 "** Appointed Chairman effective 25th July 2025\n")
    assert g.departed("Aliko Dangote", footnoted) and not g.departed("Emmanuel Ikazoboh", footnoted)
    assert not g.departed("Arvind Pathak", footnoted)
    profiles = ("Steve Pacak\n71, male, South African\nNon-executive director\nDate of first appointment:\n"
                "15 January 2015\nDeceased:\n20 April 2026\nMark Sorour\n64, male, South African\n"
                "Non-executive director\nDate of first appointment:\n15 January 2015\n"
                "Fabricio Bloisi Nico Marais\nChief executive Financial director\n")
    assert g.departed("Steve Pacak", profiles) and not g.departed("Mark Sorour", profiles)
    assert g.board_from_layout(profiles) == ["Steve Pacak", "Mark Sorour"]


def test_values_must_appear_as_printed_and_lose_page_tags():
    from src.engines import governance as g
    page = "Independent auditor\nDeloitte & Touche\n5 Magwa Crescent\nRegistered office\n40 Heerengracht"
    assert g._phrase_on_page("Deloitte & Touche", page)
    assert not g._phrase_on_page("Deloitte & Touche South Africa (Deloitte)", page)
    assert g._clean("40 Heerengracht, Cape Town [p 150]") == "40 Heerengracht, Cape Town"
    assert g._page_number("[p 103]") == 103


def test_combined_reads_keep_every_confirmed_entry_once():
    from src.engines import governance as g
    a = {"auditor": "KPMG", "committees": [{"name": "Audit Committee", "members": [], "page": 87}],
         "shareholders": [{"name": "Dangote Industries Limited", "percent": 86.65, "page": 101}]}
    b = {"auditor": "KPMG Professional Services",
         "committees": [{"name": "Audit Committee", "members": ["A", "B"], "page": 103},
                        {"name": "Finance Committee", "members": [], "page": 87}],
         "shareholders": [{"name": "Stanbic IBTC Nominees Ltd", "percent": 5.47, "page": 102}]}
    m = g.combine_reads([a, b])
    assert m["auditor"] == "KPMG"
    assert [c["name"] for c in m["committees"]] == ["Audit Committee", "Finance Committee"]
    assert m["committees"][0]["members"] == ["A", "B"]
    assert len(m["shareholders"]) == 2


def test_list_entries_are_read_whatever_the_model_called_or_tagged_them():
    from src.engines import governance as g
    pages = ["", "Substantial interest\nDangote Industries Ltd. Stanbic IBTC Nominees Ltd\n% 86.65 5.47"]
    raw = {"shareholders": [{"name": "Dangote Industries Ltd.", "percent": "86.65 [p 2]", "page": "[p 2]"},
                            {"shareholder": "Stanbic IBTC Nominees Ltd", "percentage": "5.47%", "page": 2}]}
    out = g.verify(raw, pages, [2])
    assert [(r["name"], r["percent"]) for r in out["shareholders"]] == [
        ("Dangote Industries Ltd.", 86.65), ("Stanbic IBTC Nominees Ltd", 5.47)]


def test_registration_number_with_a_copied_page_tag_is_still_read():
    from src.engines import governance as g
    pages = ["Naspers\n(Registration number: 1925/001431/06)"]
    assert g.verify({"rc_number": "1925/001431/06 [p 1]", "rc_page": 1}, pages, [1])["rc_number"] == "1925/001431/06"


def test_a_percentage_must_be_printed_beside_its_name():
    from src.engines import governance as g
    diagram = "Prosus N.V. Heemstede\nBeleggings\nLimited\nMedia24\n\n\n\n100%\n100%\n43.42% Prosus N.V.\n"
    table = "Dangote Cement Zambia Limited Cement production Zambia 99.96% 99.96%\n"
    out = g.verify({"subsidiaries": [{"name": "Media24", "percent": "100", "page": 1},
                                     {"name": "Dangote Cement Zambia Limited", "percent": "99.96", "page": 2}]},
                   ["", diagram, table][1:], [1, 2])
    rows = {r["name"]: r.get("percent") for r in out["subsidiaries"]}
    assert rows == {"Media24": None, "Dangote Cement Zambia Limited": 99.96}
    shares = "Date Details Dangote Industries Ltd. Stanbic IBTC Nominees Ltd\nAs of 31st Dec. 2025\nUnits 1 2\n% 86.65 5.47"
    sh = g.verify({"shareholders": [{"name": "Stanbic IBTC Nominees Ltd", "percent": "5.47", "page": 1}]}, [shares], [1])
    assert sh["shareholders"][0]["percent"] == 5.47


def test_diagram_percentages_are_not_attached_to_a_subsidiary():
    from src.engines import governance as g
    page = "100% 100% 100% OXL\nGlobal B.V.\nVarious\n43.42% Prosus N.V.\nDangote Cement Senegal S.A * Cement production Senegal 89.99% 99.99%"
    assert not g._percent_near("OXL Global B.V.", "100", page, 0)
    assert g._percent_near("Prosus N.V.", "43.42", page, 0)
    assert g._percent_near("Dangote Cement Senegal S.A", "89.99", page, 0)


def test_subsidiary_boards_are_not_the_company_board():
    from src.engines import governance as g
    sub = "Board of Directors - Guaranty Trust Fund Managers Limited\nMr. A. Bee\nChairman\n"
    own = "Board of Directors - Guaranty Trust Holding Company Plc\nMrs. C. N. Echeozo\nChairman\n"
    assert g._other_board(sub, "Guaranty Trust Holding Company Plc")
    assert not g._other_board(own, "Guaranty Trust Holding Company Plc")
    assert g._other_board("Board of Directors - GTBank Limited\n", "Guaranty Trust Holding Company Plc")
    assert not g._other_board("Board of Directors - GTCO Plc\n", "Guaranty Trust Holding Company Plc")
    assert not g._other_board("Corporate Information\nBOARD OF DIRECTORS:\nMr. Olusegun Layode\n", "McNichols Plc")


def test_board_and_holder_clean_up():
    from src.engines import governance as g
    board = [{"name": n} for n in ("Mrs. C. N. Echeozo", "Mrs. C. Echeozo", "Monsieur Alioune NDIAYE",
                                   "Cabinet Secretary, The National Treasury", "Cabinet Secretary, The National",
                                   "Aliko Dangote", "Mariya Aliko Dangote")]
    names = [d["name"] for d in g.dedupe_board(board)]
    assert "Mrs. C. Echeozo" not in names and "Mrs. C. N. Echeozo" in names
    assert "Aliko Dangote" in names and "Mariya Aliko Dangote" in names
    assert g._key("Monsieur Alioune NDIAYE") == g._key("Alioune Ndiaye")
    assert g._GENERIC_HOLDER.search("Institutionnels et fonds") and g._GENERIC_HOLDER.search("public investors")
    assert not g._GENERIC_HOLDER.search("Orange MEA")
    assert not g._GENERIC_HOLDER.search("Public Investment Corporation")
    assert g._GENERIC_HOLDER.search("Grand public")


def test_percentages_beside_accented_names_are_found():
    from src.engines import governance as g
    line = "Societe Des Produits Nestlé S.A 1 0.00 561,280,306 70.81"
    assert g._percent_near("Societe Des Produits Nestlé S.A", "70.81", line, 10)


def test_joint_auditors_and_signature_pages():
    from src.engines import governance as g
    page = "Dakar, le 31 mars 2026\nLES COMMISSAIRES AUX COMPTES\nDELOITTE SENEGAL\nTAFSIR NDOYE\nGARECGO\n"
    assert g._score("corporate", page) >= 5 or g._score("corporate", "Commissaires aux comptes\n" + page) >= 5
    out = g.verify({"auditor": "Deloitte Senegal and GARECGO", "auditor_page": 1}, [page], [1])
    assert out["auditor"] == "Deloitte Senegal and GARECGO"
    assert "auditor" not in g.verify({"auditor": "Deloitte Senegal and KPMG", "auditor_page": 1}, [page], [1])


def test_multi_page_citations_icon_memberships_partners_and_labelled_stakes():
    from src.engines import governance as g
    assert g._page_number("[p 76, 77]") == 76 and g._page_number("p 76-77") == 76
    page = "Committees\nGroup audit committee\nGroup risk committee\n" + "\n".join(f"Director {c}" for c in "ABCDEF")
    everyone = [f"Director {c}" for c in "ABCDEF"]
    out = g.verify({"committees": [{"name": "Group audit committee", "members": everyone, "page": 1},
                                   {"name": "Group risk committee", "members": everyone, "page": 1}]}, [page], [1])
    assert [c["members"] for c in out["committees"]] == [[], []]
    sig = "LES COMMISSAIRES AUX COMPTES\nDELOITTE SENEGAL\nTAFSIR IBNOU NDOYE\nASSOCIE\nGARECGO\nEL HADJI GUEYE\nASSOCIE\n"
    raw = {"auditor": [{"name": "DELOITTE SENEGAL", "auditor_page": 1}, {"name": "TAFSIR IBNOU NDOYE"},
                       {"name": "GARECGO"}, {"name": "EL HADJI GUEYE"}]}
    assert g.verify(raw, [sig], [1])["auditor"] == "DELOITTE SENEGAL and GARECGO"
    profile = "Our Largest Shareholders\nArise B.V\n" + "Arise is an investment company.\n" * 20 + "Ownership: 12.76%\n"
    assert g._percent_near("Arise B.V", "12.76", profile, 10)
