from src.engines import dfi_disclosures as dfi
from src.engines import official_records

ROWS = [
    {"aid": "XM-DAC-903-1", "title": "Equity Bank Ltd", "description": "Senior loan to Equity Bank Limited in Kenya.",
     "day_start": 15467, "commitment": 180000000, "country_code": "KE", "status_code": 2},
    {"aid": "XM-DAC-903-1", "title": "Equity Bank Ltd", "description": "Senior loan to Equity Bank Limited in Kenya.",
     "day_start": 15467, "commitment": 180000000, "country_code": "UG", "status_code": 2},
    {"aid": "XM-DAC-903-2", "title": "Ethos Private Equity Fund V", "description": "A private equity fund in South Africa.",
     "day_start": 13152, "commitment": 30000000, "country_code": "ZA"},
    {"aid": "GB-COH-03877777-9", "title": "Moniepoint Inc.", "description": "Equity in a Nigerian payments company.",
     "day_start": 18894, "commitment": 0, "country_code": "NG"},
    {"aid": "XM-DAC-46002-5", "title": "Ethiopia - Peasant Agricultural Development",
     "description": "Support to rural family farms; the Bank will finance inputs.", "day_start": 5970, "commitment": 1e7,
     "country_code": "ET"},
]


def _records():
    parsed = dfi.parse_rows(ROWS[:3], "IFC")
    parsed.update(dfi.parse_rows(ROWS[3:4], "British International Investment"))
    parsed.update(dfi.parse_rows(ROWS[4:], "African Development Bank"))
    return list(parsed.values())


def test_an_activity_listed_per_country_becomes_one_record():
    recs = {r["id"]: r for r in _records()}
    eq = recs["XM-DAC-903-1"]
    assert eq["countries"] == ["KE", "UG"] and eq["amount_usd"] == 180000000 and eq["date"] == "2012-05-07"
    assert recs["GB-COH-03877777-9"]["amount_usd"] is None        # a zero commitment means not disclosed


def test_the_full_name_must_appear_not_a_shared_word():
    recs = _records()
    titles = [r["title"] for r in dfi.records_for("Equity Bank Ltd", records=recs)]
    assert titles == ["Equity Bank Ltd"]                           # not "Ethos Private Equity Fund V"
    assert dfi.records_for("Family Bank", records=recs) == []      # "family farms ... the Bank" is not Family Bank
    assert dfi.records_for("Moniepoint", records=recs)[0]["authority"] == "British International Investment"
    assert dfi.records_for("Kenya", records=recs) == [] and dfi.records_for("Bank", records=recs) == []


def test_official_records_merge_sources_newest_first(monkeypatch):
    monkeypatch.setattr(official_records, "SOURCES", (
        lambda c, t: [{"kind": "merger_filing", "authority": "COMESA", "title": "A", "date": "2020-01-01", "url": "u1"}],
        lambda c, t: [{"kind": "dfi_investment", "authority": "IFC", "title": "B", "date": "2024-01-01", "url": "u2"},
                      {"kind": "dfi_investment", "authority": "IFC", "title": "B", "date": "2024-01-01", "url": "u2"}],
        lambda c, t: (_ for _ in ()).throw(RuntimeError("source down")),
    ))
    out = official_records.records_for("Acme")
    assert [r["title"] for r in out] == ["B", "A"]                 # deduplicated, newest first, failure ignored


def test_fmdq_announcements_name_the_issuer_and_amount():
    from src.engines import debt_filings as debt
    cases = {
        "Ojaja Pan Africa Limited Quotes ₦25.53 Billion Commercial Paper on FMDQ Exchange": "Ojaja Pan Africa Limited",
        "FMDQ Exchange Admits the Babban Gona Farmers Services Nigeria Limited Commercial Paper Programme on its Platform":
            "Babban Gona Farmers Services",
        "FMDQ Approves Registration of The Wema Bank ₦50.00 Billion Commercial Paper Programme": "Wema Bank",
        "FMDQ Admits N3.15 Billion LAPO MFB SPV PLC Bond to its Platform": "LAPO MFB SPV",
        "NBET Finance Company PLC Lists Landmark ₦728.98 Billion Series 2 Fixed Rate Bonds": "NBET Finance Company PLC",
        "Nigerian Breweries PLC Registers ₦100.00 billion Commercial Paper Programme on FMDQ": "Nigerian Breweries PLC",
        "Lagos State Champions Sustainability with ₦244.82 Billion Green and Fixed Rate Bonds": None,
        "SEC Approves FMDQ Bond Listing and Quotation Rules": None,
    }
    for title, issuer in cases.items():
        assert debt.issuer_of(title) == issuer, title
    assert debt.amount_ngn("Quotes ₦25.53 Billion Commercial Paper") == 25.53e9
    assert debt.instrument_of("Lists ₦26.70 Billion Bond") == "Bond"


def test_fmdq_issues_match_the_company_not_a_namesake():
    from src.engines import debt_filings as debt
    recs = debt.parse_posts([
        {"id": 1, "date": "2026-07-28T10:00:00", "link": "https://fmdqgroup.com/a",
         "title": {"rendered": "FMDQ Exchange Lists LAPO MFB SPV PLC ₦4.46 Billion Bond for Microfinance Sector Expansion"}},
        {"id": 2, "date": "2020-06-05T10:00:00", "link": "https://fmdqgroup.com/b",
         "title": {"rendered": "Dangote Cement PLC Quotes ₦100.00 Billion Commercial Paper on FMDQ Exchange"}},
    ])
    lapo = debt.records_for("LAPO Microfinance Bank", records=recs)
    assert [(r["kind"], r["detail"]) for r in lapo] == [("debt_issue", "Bond of ₦4.46bn")]
    assert debt.records_for("Dangote Industries Limited", records=recs) == []     # Dangote Cement is a different issuer
    assert len(debt.records_for("Dangote Cement Plc", records=recs)) == 1


def test_licence_registers_parse_and_match():
    from src.engines import licensed_institutions as lic
    ng = lic.parse_cbn([{"name": "Lapo MFB"}, {"name": "OPAY MFB LIMITED"}, {"name": "x"}], "Microfinance bank")
    assert [r["name"] for r in ng] == ["Lapo MFB", "Opay MFB Limited"]        # shouted names tidied; acronyms kept
    page = ('<tr id="table_87_row_2" data-row-index="2"><td>Agricultural Development Bank Plc</td><td>Accra</td>'
            '<td>233-302</td><td>http://www.agricbank.com</td><td>customercare@agricbank.com</td></tr>')
    gh = lic.parse_bog(page, "Bank")
    assert gh == [{"name": "Agricultural Development Bank Plc", "country": "GH", "regulator": "Bank of Ghana",
                   "licence": "Bank", "website": "http://www.agricbank.com"}]
    rows = ng + gh
    assert lic.lookup("LAPO Microfinance Bank Limited", rows=rows)["licence"] == "Microfinance bank"
    assert lic.lookup("Agricultural Development Bank", "GH", rows=rows)["website"] == "http://www.agricbank.com"
    assert lic.lookup("Agricultural Development Bank", "NG", rows=rows) is None
    assert lic.lookup("Moniepoint", rows=rows) is None
