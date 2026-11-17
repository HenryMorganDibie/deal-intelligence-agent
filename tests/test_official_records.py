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
