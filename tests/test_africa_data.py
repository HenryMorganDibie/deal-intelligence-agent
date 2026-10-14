"""Countries, country risk, deals extraction and the market feed."""
from __future__ import annotations

import pytest

from src.data import africa_countries as ac
from src.engines import country_risk as cr
from src.engines import deals as dl
from src.engines import market_feed as mf


# ── Country registry ──────────────────────────────────────────────────────────

def test_registry_has_all_54_countries_with_unique_codes():
    assert len(ac.COUNTRIES) == 54
    assert len({c.iso2 for c in ac.COUNTRIES}) == 54
    assert len({c.iso3 for c in ac.COUNTRIES}) == 54
    assert {c.region for c in ac.COUNTRIES} == {"Northern Africa", "Western Africa", "Middle Africa",
                                                 "Eastern Africa", "Southern Africa"}
    assert all(c.languages and c.currency and c.central_bank for c in ac.COUNTRIES)


@pytest.mark.parametrize("ticker,iso2", [("DANGCEM.LG", "NG"), ("NPN.JO", "ZA"), ("SCOM.NR", "KE"),
                                         ("COMI.CA", "EG"), ("SNTS.BV", "CI"), ("AAPL", None)])
def test_country_from_listing_suffix(ticker, iso2):
    c = ac.from_ticker(ticker)
    assert (c.iso2 if c else None) == iso2


def test_countries_in_text_prefers_longest_names_and_handles_languages():
    found = [c.iso2 for c in ac.countries_in_text(
        "South Sudanese and Nigerian firms in Guinea-Bissau, Niger, Afrique du Sud, Quénia and Côte d’Ivoire")]
    assert found == ["SS", "NG", "GW", "NE", "ZA", "KE", "CI"]


def test_news_url_uses_national_edition_or_language_edition():
    assert "gl=NG&ceid=NG:en" in ac.get("NG").news_url("Dangote")
    assert "ceid=FR:fr" in ac.get("ML").news_url("Sonatel")          # no Malian edition
    assert "ceid=PT:pt-150" in ac.get("AO").news_url("Sonangol")


def test_request_accepts_and_normalises_country():
    from src.schemas.models import AnalysisRequest
    assert AnalysisRequest(company_name="Sonatel", country="sen").country == "SN"
    with pytest.raises(ValueError):
        AnalysisRequest(company_name="X", country="FR")


def test_african_regulators_trigger_regulatory_action():
    from src.engines.deterministic_engine import _match_rules
    from src.schemas.models import SignalType
    for text in ("BCEAO sanctions Ecobank unit", "Bank of Ghana revokes licences of three lenders",
                 "CMSA investigation into Tanzanian broker"):
        assert any(t == SignalType.REGULATORY_ACTION for t, _, _ in _match_rules(text)), text
    assert not any(t == SignalType.REGULATORY_ACTION for t, _, _ in _match_rules("Bank of Ghana appoints governor"))


# ── Country risk ──────────────────────────────────────────────────────────────

def _snapshot(**series):
    return {"retrieved": "2026-10-14", "labels": {}, "series": series}


def test_country_risk_components_follow_documented_formulas():
    snap = _snapshot(**{
        "GOV_WGI_PV.EST": {"NGA": {"2024": -2.0}},
        "GOV_WGI_GE.EST": {"NGA": {"2024": 0.0}},
        "FP.CPI.TOTL.ZG": {"NGA": {"2024": 20.0}},
        "NY.GDP.MKTP.KD.ZG": {"NGA": {"2024": 0.0}},
        "PA.NUS.FCRF": {"NGA": {"2023": 100.0, "2024": 125.0}},
        "FI.RES.TOTL.MO": {"NGA": {"2024": 3.0}},
        "BN.CAB.XOKA.GD.ZS": {"NGA": {"2024": -5.0}},
        "DT.DOD.DECT.GN.ZS": {"NGA": {"2024": 40.0}},
    })
    r = cr.assess(ac.get("NG"), snap, fx=lambda _: 1500.0)
    risk = {c["name"]: c["risk"] for c in r["components"]}
    assert risk == {"political_stability": 90.0, "governance": 50.0, "inflation": 50.0, "currency": 50.0,
                    "external": 50.0, "growth": 50.0, "external_debt": 40.0}
    assert r["score"] == pytest.approx(0.2 * 90 + 0.2 * 50 + 0.15 * 50 + 0.15 * 50 + 0.1 * 50 + 0.1 * 50 + 0.1 * 40, abs=0.1)
    assert r["tier"] == "elevated" and r["coverage"] == 1.0 and r["spot_usd_rate"] == 1500.0
    assert r["indicators"]["fx_depreciation"] == {"value": 25.0, "year": 2024,
                                                  "label": "Annual change in official USD exchange rate (%)"}


def test_country_risk_reweights_over_available_components():
    snap = _snapshot(**{"FP.CPI.TOTL.ZG": {"KEN": {"2024": 4.0}}})
    r = cr.assess(ac.get("KE"), snap, fx=lambda _: None)
    assert r["score"] == 10.0 and r["coverage"] == 0.15


def test_committed_snapshot_covers_every_country():
    snap = cr.load_snapshot()
    pv = snap["series"]["GOV_WGI_PV.EST"]
    assert {c.iso3 for c in ac.COUNTRIES} <= set(pv)
    ranking = cr.ranking()
    assert len(ranking) == 54 and all(r["score"] is not None for r in ranking)


# ── Deals ─────────────────────────────────────────────────────────────────────

def _deal(title, **kw):
    return dl.extract_deal(title, published=kw.pop("published", "2026-10-01"), **kw)


@pytest.mark.parametrize("text,value,currency", [
    ("raises $25m", 25e6, "USD"), ("US$1.2bn deal", 1.2e9, "USD"), ("N50 billion", 50e9, "NGN"),
    ("₦8bn stake", 8e9, "NGN"), ("KSh 2 billion", 2e9, "KES"), ("R1.5bn", 1.5e9, "ZAR"),
    ("€10 million", 10e6, "EUR"), ("11,7 milliards de FCFA", 11.7e9, "XOF"), ("USD 13 M Series A", 13e6, "USD"),
])
def test_parse_amounts(text, value, currency):
    assert dl.parse_amounts(text)[0] == (pytest.approx(value), currency)


def test_parse_amounts_ignores_prices_and_words_ending_in_r():
    assert dl.parse_amounts("for 1.36 billion $") == [(pytest.approx(1.36e9), "USD")]
    assert dl.parse_amounts("shares at $12.50") == []


def test_funding_round_with_lead_investor_and_valuation():
    d = _deal("Nigeria’s Moniepoint raises $110m Series C at a $1bn valuation, led by Development Partners International")
    assert d["deal_type"] == "equity_funding" and d["stage"] == "completed"
    assert d["target"] == "Moniepoint" and d["buyer"] == "Development Partners International"
    assert d["amount_usd"] == 110e6 and d["reported_valuation_usd"] == 1e9
    assert d["round"] == "series c" and d["country"] == "NG"


def test_title_case_acquisition_and_possessives():
    d = _deal("Zenith Bank Completes Acquisition Of Kenya’s Paramount Bank")
    assert (d["deal_type"], d["stage"], d["buyer"], d["target"], d["country"]) == \
        ("acquisition", "completed", "Zenith Bank", "Paramount Bank", "KE")


def test_stake_purchase_gives_implied_valuation():
    d = _deal("United Capital acquires 5% stake in Nigerian Exchange Group for N10 billion")
    assert d["stake_pct"] == 5.0 and d["target"] == "Nigerian Exchange Group"
    assert d["implied_valuation_usd"] == pytest.approx(d["amount_usd"] / 0.05)


def test_passive_acquisition_and_backed_investor():
    d = _deal("Kenyan cross-border payments startup GTXN acquired by Luno")
    assert (d["target"], d["buyer"]) == ("GTXN", "Luno")
    d = _deal("IFC-Backed Ventures Platform Raises $84M for Nigerian startups")
    assert d["investors"] == ["IFC"]


def test_lender_and_borrower_roles():
    d = _deal("Bisedge secures €10 million loan from Finnfund to expand in Nigeria")
    assert (d["deal_type"], d["target"], d["buyer"]) == ("debt_financing", "Bisedge", "Finnfund")
    d = _deal("Afreximbank extends $500 million facility to Ghana Cocoa Board")
    assert (d["deal_type"], d["target"], d["buyer"]) == ("debt_financing", "Ghana Cocoa Board", "Afreximbank")


def test_fund_closes_and_lp_commitments():
    d = _deal("Ninety One Reaches Final Close of $404M Africa Credit Fund")
    assert (d["deal_type"], d["target"], d["amount_usd"]) == ("fund_raise", "Ninety One", 404e6)
    d = _deal("IFC discloses proposed $25m investment in Admaius’ Virunga Africa Fund II")
    assert d["deal_type"] == "fund_raise" and d["investors"] == ["IFC"]
    d = _deal("South Africa: PIC anchors first close for Mamor Capital Ventures")
    assert (d["target"], d["investors"]) == ("Mamor Capital Ventures", ["PIC"])


def test_french_and_portuguese_deals():
    d = _deal("Wave lève 90 millions de dollars au Sénégal")
    assert (d["deal_type"], d["target"], d["amount_usd"], d["country"]) == ("equity_funding", "Wave", 90e6, "SN")
    d = _deal("Unitel adquire 20% da Africell em Angola")
    assert (d["buyer"], d["target"], d["stake_pct"], d["country"]) == ("Unitel", "Africell", 20.0, "AO")
    d = _deal("Shelter Afrique lève 60 milliards FCFA sur le marché UEMOA")
    assert d["deal_type"] == "debt_financing"


def test_stage_from_wording():
    assert _deal("Orange In Talks To Acquire 70% Stake In Telecel Ghana")["stage"] == "rumoured"
    assert _deal("Attijariwafa Bank to acquire majority stake in Société Générale Ghana")["stage"] == "announced"
    assert _deal("Lighthouse Capital raising $50m to back mid-market businesses in Kenya")["stage"] == "announced"


@pytest.mark.parametrize("title", [
    "African startups raise $435m in August as Nigeria takes 84%",
    "World Bank raises Nigeria's growth forecast to 4.3%",
    "Governor Radda raises bursary by 100%, disburses N689.79m to students in Nigeria",
    "Fitch raises Nigeria’s outlook, flags debt, fiscal risks",
    "Chicago Stars FC Acquires Zambia National Team Forward Racheal Kundananji",
    "Somalia Reportedly Agrees to Acquire Pakistan’s JF-17 Fighter Jets",
    "Isuzu Motors South Africa invests R30 million in Gqeberha plant",
    "Vodacom Invests Over R1.8 Million in Soweto Schools in South Africa",
    "Burkina Faso : le Trésor lève 40 milliards FCFA sur le marché de l’UMOA",
    "Should Investors Back Nigerian Fintech After OPay Raises $50m?",
    "Scarlet Raises $50M to Accelerate AI Medical Device Certification",   # nothing places it in Africa
    "Mwanza backs Copper Queens to deliver against Uganda",
])
def test_non_deals_are_rejected(title):
    assert _deal(title) is None


def test_reports_of_one_transaction_merge():
    a = _deal("Standard Bank Group announces strategic investment in Nigeria's OPay", publisher="TechCabal", url="u1")
    b = _deal("Standard Bank buys $200M stake in Nigeria's OPay ahead of NYSE listing", publisher="Reuters", url="u2")
    assert a["id"] == b["id"]
    store = dl.merge_all([a, b])
    (d,) = store.values()
    assert d["amount_usd"] == 200e6 and d["deal_type"] == "equity_funding"
    assert [s["url"] for s in d["sources"]] == ["u1", "u2"]


def test_search_and_comparables():
    deals = [
        {"id": "1", "deal_type": "equity_funding", "sector": "fintech", "country": "NG", "countries": ["NG"],
         "amount_usd": 20e6, "announced": "2026-01-01", "target": "A", "investors": ["TLcom Capital"], "headline": "A"},
        {"id": "2", "deal_type": "equity_funding", "sector": "fintech", "country": "KE", "countries": ["KE"],
         "amount_usd": 30e6, "announced": "2026-02-01", "target": "B", "investors": [], "headline": "B",
         "implied_valuation_usd": 150e6},
        {"id": "3", "deal_type": "acquisition", "sector": "mining", "country": "ZA", "countries": ["ZA"],
         "amount_usd": 900e6, "announced": "2026-03-01", "target": "C", "investors": [], "headline": "C"},
    ]
    assert [d["id"] for d in dl.search(deals, country="NG")] == ["1"]
    assert [d["id"] for d in dl.search(deals, investor="tlcom")] == ["1"]
    assert [d["id"] for d in dl.search(deals, min_usd=25e6)] == ["3", "2"]
    comps = dl.comparables(deals, sector="fintech", country="NG", deal_type="equity_funding", amount_usd=25e6)
    assert [d["id"] for d in comps["deals"]] == ["1", "2"]
    assert comps["deals"][0]["similarity"] == 9 and "same country" in comps["deals"][0]["why"]
    assert comps["size_usd"]["median"] == 25e6 and comps["implied_valuation_usd"]["n"] == 1


# ── Market feed ───────────────────────────────────────────────────────────────

RSS = """<rss><channel>
<item><title>Egypt's MoneyHash raises $5.2 million in pre-Series A - TechCabal</title>
<link>https://example.com/a</link><pubDate>Tue, 13 Oct 2026 08:00:00 GMT</pubDate>
<source url="https://techcabal.com">TechCabal</source><description>&lt;b&gt;MoneyHash&lt;/b&gt; ...</description></item>
<item><title>Ghana bank fined by Bank of Ghana for breaches</title><link>https://example.com/b</link>
<pubDate>Mon, 12 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_feed_and_extract_deals_and_events():
    items = mf.parse_feed(RSS, default_publisher="Feed")
    assert items[0]["title"] == "Egypt's MoneyHash raises $5.2 million in pre-Series A"
    assert items[0]["publisher"] == "TechCabal" and items[0]["date"] == "2026-10-13"
    assert items[1]["publisher"] == "Feed" and items[1]["snippet"] == ""
    deals = mf.to_deals(items)
    assert [d["target"] for d in deals] == ["MoneyHash"]
    events = mf.to_events(items)
    assert [(e["signal_type"], e["country"]) for e in events] == [("regulatory_action", "GH")]


def test_country_queries_cover_every_country():
    labels = {c.iso2 for _, _, c in mf.country_queries()}
    assert labels == {c.iso2 for c in ac.COUNTRIES}


# ── Investors, funds, LPs and GPs ─────────────────────────────────────────────

from src.engines import investors as inv  # noqa: E402


def test_investor_aliases_resolve_to_registry_names():
    assert inv.canonical("World Bank’s IFC") == "International Finance Corporation"
    assert inv.canonical("CDC Group") == "British International Investment"
    assert inv.canonical("Bid Corp") == "Bid Corp"              # lower-case words are not acronyms
    assert inv.canonical("Standard Bank Group") == "Standard Bank"
    assert inv.canonical("MTN Group") == "MTN Group"


def test_profiles_roles_and_fund_activity():
    deals = [
        _deal("Nigeria’s Moniepoint raises $110m Series C, led by Development Partners International"),
        _deal("IFC-Backed Ventures Platform Raises $84M for Nigerian startups", published="2026-09-01"),
        _deal("IFC discloses proposed $25m investment in Admaius’ Virunga Africa Fund II"),
        _deal("Bisedge secures €10 million loan from Finnfund to expand in Nigeria"),
        _deal("Zenith Bank Completes Acquisition Of Kenya’s Paramount Bank"),
    ]
    p = inv.profile(deals, "IFC")
    assert p["name"] == "International Finance Corporation" and p["type"] == "dfi"
    assert p["roles"] == {"investor": 1, "lp": 1}
    assert inv.profile(deals, "DPI")["roles"] == {"investor": 1}
    assert inv.profile(deals, "Finnfund")["roles"] == {"lender": 1}
    assert inv.profile(deals, "Zenith Bank")["roles"] == {"acquirer": 1}
    assert [f["lps"] for f in inv.funds(deals)] == [["International Finance Corporation"]]
    top = inv.leaderboard(deals, kind="dfi")
    assert {r["name"] for r in top} == {"International Finance Corporation", "Finnfund"}


# ── Financial statements ──────────────────────────────────────────────────────

from src.engines import financials as fin  # noqa: E402

STATEMENT = """DANGOTE CEMENT PLC
CONSOLIDATED AND SEPARATE STATEMENTS OF PROFIT OR LOSS
FOR THE YEAR ENDED 31 DECEMBER 2025
 ₦'million  ₦'million  ₦'million  ₦'million
Revenue 5  4,306,704  3,580,550  2,956,515  2,192,695
Production cost of sales 7  (1,634,430)  (1,645,651)  (1,169,998)  (988,041)
Gross profit  2,672,274  1,934,899  1,786,517  1,204,654
Impairment of financial assets 30.6.1  (4,724) (726) (10,605)  (387)
Profit before tax  1,532,660  732,537  1,072,817  1,176,327
Income tax expense 12  (517,739)  (229,290)  (363,975)  (149,110)
Profit for the year  1,014,921  503,247  708,842  1,027,217
Earnings per share, basic and diluted (Naira) 13  59.86  29.74  42.31  61.32
Total assets  5,000,000  4,000,000  1  1
Total liabilities  3,000,000  2,500,000  1  1
Total equity  1,900,000  1,500,000  1  1
"""


def test_statement_parser_reads_group_columns_units_and_period():
    p = fin.parse_statement_text(STATEMENT)
    assert p["period"] == {"months": 12, "end": "2025-12-31", "label": "FOR THE YEAR ENDED 31 DECEMBER 2025"}
    assert p["multiplier"] == 1e6
    items = {k: (v["current"], v["prior"]) for k, v in p["items"].items()}
    assert items["revenue"] == (4306704, 3580550)                 # note reference "5" skipped
    assert items["cost_of_sales"] == (-1634430, -1645651)
    assert items["eps"] == (59.86, 29.74)
    assert "impairment" not in " ".join(items)


def test_statement_checks_and_per_figure_status():
    p = fin.parse_statement_text(STATEMENT)
    checks = {c["check"]: c["passed"] for c in fin.verify(p["items"])}
    assert checks["gross profit = revenue - cost of sales"] is True
    assert checks["profit after tax = profit before tax - income tax"] is True
    assert checks["total assets = total liabilities + total equity"] is False      # 4.9m vs 5.0m
    status = fin.item_status(p["items"], fin.verify(p["items"]))
    assert status["revenue"] == "verified" and status["profit_after_tax"] == "verified"
    assert status["total_assets"] == "inconsistent" and status["eps"] == "unchecked"


def test_small_bare_numbers_are_not_statement_figures():
    p = fin.parse_statement_text("Revenue 6 5\nRevenue 4,192,003 3,970,959")
    assert p["items"]["revenue"]["current"] == 4192003


def test_yahoo_cross_check_against_sec_filing():
    yahoo = {"annual": {"2025-12-31": {"revenue": 100.0, "profit_after_tax": -10.0}}}
    sec = {"revenue": {"2025-12-31": 101.0}, "profit_after_tax": {"2025-12-31": -12.0}}
    out = {r["field"]: r["match"] for r in fin.cross_check(yahoo, sec)}
    assert out == {"revenue": True, "profit_after_tax": False}


def test_private_market_summary_from_deals():
    from src.engines.company_profile import private_market_summary
    deals = [_deal("Nigeria’s Moniepoint raises $110m Series C at a $1bn valuation, led by Development Partners International"),
             _deal("Moniepoint acquires 78% stake in Kenya's Sumac Microfinance Bank", published="2026-11-02")]
    s = private_market_summary("Moniepoint", deals)
    assert s["deal_count"] == 2 and s["as_target"] == 1
    assert s["equity_raised_usd"] == 110e6 and s["last_round"] == "series c"
    assert s["valuations"][0]["usd"] == 1e9 and s["investors_and_lenders"] == ["Development Partners International"]


# ── Currency and sector risk, valuation view ──────────────────────────────────

from src.engines import market_risk as mr  # noqa: E402


def test_currency_risk_formula_and_peg_factor():
    snap = _snapshot(**{"PA.NUS.FCRF": {"NGA": {"2020": 100.0, "2025": 200.0, "2024": 150.0},
                                        "SEN": {"2024": 600.0, "2025": 660.0}}})
    ngn = mr.currency_risk("NGN", snap, fx=lambda _: 220.0)
    assert ngn["last_year_depreciation_pct"] == pytest.approx(33.33, abs=0.01)
    assert ngn["spot_vs_official_pct"] == 10.0 and ngn["regime"] == "floating or managed float"
    xof = mr.currency_risk("XOF", snap, fx=lambda _: None)
    assert xof["regime"] == "hard peg" and xof["last_year_depreciation_pct"] == 10.0
    raw = 0.4 * 20 + 0.35 * mr._clamp(10 / 30 * 100)                       # one change: no volatility
    assert xof["score"] == pytest.approx(round(raw / 0.75 * 0.4, 1), abs=0.1)
    assert len(mr.all_currencies()) == len({c.currency for c in ac.COUNTRIES})


def test_sector_risk_is_smoothed_adverse_share():
    from datetime import date
    events = [{"sector": "banking", "day": "2026-10-01", "signal_type": "credit_risk", "countries": ["NG"], "headline": "x"},
              {"sector": "banking", "day": "2026-10-02", "signal_type": "m_and_a_activity", "countries": ["NG"], "headline": "y"},
              {"sector": "banking", "day": "2025-01-01", "signal_type": "credit_risk", "countries": ["NG"], "headline": "old"}]
    deals = [{"sector": "banking", "announced": "2026-10-03", "countries": ["NG"], "amount_usd": 5e6}]
    r = mr.sector_risk("banking", events, deals, country="NG", today=date(2026, 10, 14))
    assert (r["adverse_events"], r["other_events"], r["deals"]) == (1, 1, 1)
    assert r["score"] == pytest.approx((1 + 2.5) / (3 + 5) * 100, abs=0.1) and r["low_sample"]


def test_valuation_view_uses_own_marks_and_comparables():
    deals = [_deal("Nigeria’s Moniepoint raises $110m Series C at a $1bn valuation"),
             _deal("Nigeria’s Paystack raises $100m Series C at a $900m valuation", published="2026-08-01")]
    v = mr.valuation_view("Moniepoint", deals)
    assert v["latest_mark"]["valuation_usd"] == 1e9 and v["latest_mark"]["basis"] == "reported"
    assert [d["target"] for d in v["comparables"]["deals"]] == ["Paystack"]


# ── Research ──────────────────────────────────────────────────────────────────

from src.engines import research as rs  # noqa: E402


def test_parse_question_scope():
    p = rs.parse_question("Which fintech startups in Kenya raised a Series A from IFC in 2025?")
    assert p["countries"] == ["KE"] and p["sectors"] == ["fintech"] and "equity_funding" in p["deal_types"]
    assert p["investors"] == ["International Finance Corporation"]
    assert (p["since"], p["until"]) == ("2025-01-01", "2025-12-31")


def test_citation_normalisation_and_validation():
    text = ("Cloud9 raised $500k in its latest round 【2】. The naira fell sharply last year [3, 4]. "
            "A made up claim cites a missing item [9]. Another claim without a source here.")
    v = rs.validate_citations(text, 4)
    assert v["invalid_citations_removed"] == [9] and v["cited_items"] == [2, 3, 4]
    assert v["uncited_sentences"] == ["A made up claim cites a missing item .", "Another claim without a source here."]
    assert v["grounded_share"] == 0.5


def test_research_retrieves_numbered_evidence_and_uses_llm_with_citations():
    deals = [_deal("Kenyan neobank Cloud9 raises $500,000 from crypto accelerator Alliance"),
             _deal("Nigeria’s Moniepoint raises $110m Series C, led by Development Partners International")]
    seen = {}

    def fake_llm(system, user, max_tokens):
        seen["user"] = user
        return "Cloud9 raised $500,000 [2]. Kenya's currency risk is low [4]."
    r = rs.research("Kenya fintech funding and currency risk", deals, [], live_news=False, llm=fake_llm)
    kinds = [i["kind"] for i in r["evidence"]]
    assert kinds[:2] == ["statistics", "deal"] and "country_risk" in kinds and "currency_risk" in kinds
    assert "[2] (deal" in seen["user"] and "ONLY the numbered evidence" in rs.SYSTEM
    assert r["mode"] == "llm" and r["validation"]["grounded_share"] == 1.0


def test_research_without_llm_is_deterministic(monkeypatch):
    deals = [_deal("Kenyan neobank Cloud9 raises $500,000 from crypto accelerator Alliance")]
    r = rs.research("Kenya fintech funding", deals, [], live_news=False)
    assert r["mode"] == "deterministic" and "Cloud9" in r["answer"] and "[1]" in r["answer"]


def test_country_report_sections():
    deals = [_deal("Kenyan neobank Cloud9 raises $500,000 from crypto accelerator Alliance")]
    r = rs.country_report("KE", deals, [], live_news=False)
    for heading in ("# Kenya", "## Executive summary", "## Country risk", "## Currency", "## Deal activity",
                    "## Most active investors", "## Sources"):
        assert heading in r["markdown"]
