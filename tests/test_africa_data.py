"""Countries, country risk, deals extraction and the market feed."""
from __future__ import annotations

from datetime import date
from urllib.parse import unquote

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
    assert r["indicators"]["fx_depreciation"] == {"value": 25.0, "year": 2024, "stale": False,
                                                  "label": "Annual change in official USD exchange rate (%)"}
    assert r["partial"] is False and r["missing_components"] == [] and r["stale_inputs"] == []


def test_redenomination_and_stale_inputs_are_not_scored():
    snap = _snapshot(**{
        "GOV_WGI_PV.EST": {"ZWE": {"2025": -1.0}},
        "GOV_WGI_GE.EST": {"ZWE": {"2025": -1.0}},
        "FP.CPI.TOTL.ZG": {"ZWE": {"2020": 557.2}},                     # five years old: listed, not scored
        "PA.NUS.FCRF": {"ZWE": {"2023": 5000.0, "2024": 3266.3, "2025": 26.6}},   # ZWL to ZiG
    })
    r = cr.assess(ac.get("ZW"), snap, fx=lambda _: None)
    risk = {c["name"]: c["risk"] for c in r["components"]}
    assert risk["currency"] is None and risk["inflation"] is None      # not "low risk" from a -99% "appreciation"
    assert r["redenominated"] == 2025 and r["partial"] is True
    assert "FP.CPI.TOTL.ZG" in r["stale_inputs"] and {"currency", "inflation"} <= set(r["missing_components"])
    assert cr.fx_series_after_break({"2023": 5000.0, "2024": 3266.3, "2025": 26.6}) == ({"2025": 26.6}, 2025)



def test_current_macro_signals_keep_monthly_period_and_ignore_annual_values(monkeypatch):
    monkeypatch.delenv("AFRICA_API_KEY", raising=False)
    country = ac.get("NG")

    def fake_fetch(_country):
        return {"data": {
            "generated_at": "2026-10-25T10:00:00Z",
            "observations": [
                {"metric_key": "inflation_cpi_latest_yoy_pct", "name": "Inflation (Latest YoY)",
                 "value": 15.4, "unit": "percent", "frequency": "monthly", "source": "nbs_ng",
                 "freshness": "current", "as_of_period": "2026-09", "retrieved_at": "2026-10-20T10:00:00Z"},
                {"metric_key": "policy_rate_pct", "name": "Policy Rate", "value": 27.0, "unit": "percent",
                 "frequency": "ad_hoc", "source": "cbn_ng", "freshness": "recent", "as_of_period": "2026-09-22"},
                {"metric_key": "NY.GDP.MKTP.KD.ZG", "name": "GDP growth", "value": 4.0,
                 "unit": "percent", "frequency": "annual", "source": "world_bank_wdi", "as_of_period": "2025"},
                {"metric_key": "irrelevant_signal", "name": "Other", "value": 99,
                 "frequency": "monthly", "source": "other"},
            ],
            "fx_rates": [{"base_currency": "USD", "quote_currency": "NGN", "rate": 1500.5,
                          "date": "2026-10-24", "source": "fx_usd_daily", "freshness": "current"}],
        }}

    result = cr.current_macro_signals(country, fetch=fake_fetch)
    assert result["status"] == "available"
    assert [row["metric_key"] for row in result["observations"]] == [
        "fx_usd_daily", "inflation_cpi_latest_yoy_pct", "policy_rate_pct"
    ]
    inflation = next(row for row in result["observations"] if row["metric_key"] == "inflation_cpi_latest_yoy_pct")
    assert inflation["value"] == 15.4 and inflation["as_of_period"] == "2026-09"
    assert inflation["frequency"] == "monthly" and inflation["source"] == "nbs_ng"


def test_current_macro_signals_are_optional_without_api_key(monkeypatch):
    monkeypatch.delenv("AFRICA_API_KEY", raising=False)
    monkeypatch.setattr(cr, "load_current_signals_snapshot", lambda path=None: {})   # before the first refresh
    result = cr.current_macro_signals(ac.get("NG"))
    assert result["status"] == "not_configured"
    assert result["observations"] == []
    assert "GitHub Actions" in result["message"]
    assert "AFRICA_API_KEY" not in result["message"]



def test_current_macro_signals_load_from_committed_snapshot_without_api_key(tmp_path, monkeypatch):
    import json

    snapshot = {
        "generated_at": "2026-10-26T00:00:00Z",
        "countries": {
            "NG": {
                "status": "available",
                "source": "Africa API",
                "source_url": "https://africa-api.com/docs/signals",
                "generated_at": "2026-10-26T00:00:00Z",
                "observations": [{"metric_key": "policy_rate_pct", "value": 27.0,
                                  "frequency": "ad_hoc", "source": "cbn_ng", "as_of_period": "2026-09-22"}],
            }
        },
    }
    path = tmp_path / "current_macro_signals.json"
    path.write_text(json.dumps(snapshot))
    monkeypatch.setattr(cr, "CURRENT_SIGNALS_PATH", path)
    monkeypatch.setattr(cr, "_CURRENT_SIGNALS_SNAPSHOT", None)
    monkeypatch.delenv("AFRICA_API_KEY", raising=False)

    result = cr.current_macro_signals(ac.get("NG"))
    assert result["status"] == "available"
    assert result["observations"][0]["value"] == 27.0
    assert result["observations"][0]["source"] == "cbn_ng"

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


def test_undisclosed_minority_investment_is_not_rejected_as_generic_backing():
    deal = dl.extract_deal(
        "AfricInvest backs Spoon Consulting",
        "AfricInvest Small Cap Fund has made a minority equity investment in "
        "Spoon Consulting, a Mauritius-based AI-first consulting company.",
        published="2026-09-03",
        publisher="AVCA",
        url="https://www.avca.africa/news-insights/member-news/africinvest-backs-spoon-consulting/",
    )

    assert deal is not None
    assert deal["deal_type"] == "equity_funding"
    assert deal["target"] == "Spoon Consulting"
    assert deal["buyer"] == "AfricInvest"
    assert deal["country"] == "MU"
    assert deal["announced"] == "2026-09-03"
    assert deal["amount"] is None and deal["amount_usd"] is None


def test_public_sector_investment_solicitation_is_not_a_deal():
    assert _deal("FG Seeks Private Investment in Livestock, Leather and Fodder Production") is None
    # A company looking for capital is not the same as a public solicitation.
    assert _deal("Kuda raises $20m Series B to expand in Nigeria") is not None


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
<pubDate>Mon, 12 Oct 2026 08:00:00 GMT</pubDate><source url="https://bog.gov.gh">Bank of Ghana</source></item>
</channel></rss>"""


def test_parse_feed_and_extract_deals_and_events():
    items = mf.parse_feed(RSS, default_publisher="Feed")
    assert items[0]["title"] == "Egypt's MoneyHash raises $5.2 million in pre-Series A"
    assert items[0]["publisher"] == "TechCabal" and items[0]["date"] == "2026-10-13"
    assert items[0]["publisher_url"] == "https://techcabal.com"
    assert items[1]["publisher"] == "Bank of Ghana" and items[1]["snippet"] == ""
    assert items[1]["publisher_url"] == "https://bog.gov.gh"
    deals = mf.to_deals(items)
    assert [d["target"] for d in deals] == ["MoneyHash"]
    assert deals[0]["sources"][0]["publisher_url"] == "https://techcabal.com"
    events = mf.to_events(items)
    assert [(e["signal_type"], e["country"]) for e in events] == [("regulatory_action", "GH")]
    assert events[0]["publisher_url"] == "https://bog.gov.gh"


def test_event_country_uses_story_location_over_search_hint():
    items = [{"title": "IEBC officials face Sh2 million fine, five years in jail over ungazetted polling stations",
              "country_hint": "ET"}]

    events = mf.to_events(items)

    assert len(events) == 1
    assert events[0]["country"] == "KE"
    assert events[0]["countries"] == ["KE"]


def test_country_deal_queries_include_undisclosed_equity_and_backing_terms():
    queries = [
        unquote(url)
        for url, label, country in mf.country_queries(events=False)
        if country and country.iso2 == "MU" and "(en)" in label
    ]

    assert queries
    assert any("backs" in query and "backed" in query and
               '"minority stake"' in query and '"equity investment"' in query
               for query in queries)


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


def test_parse_question_company_region_and_calendar_dates():
    today = date(2026, 10, 16)
    company = rs.parse_question("Moniepoint raised money in Nigeria in 2025", today)
    assert company["companies"] == ["Moniepoint"]
    assert company["countries"] == ["NG"]
    assert (company["since"], company["until"]) == ("2025-01-01", "2025-12-31")

    region = rs.parse_question("Which DFIs are most active in West Africa?", today)
    west_africa = [c.iso2 for c in ac.COUNTRIES if c.region == "Western Africa"]
    assert region["countries"] == west_africa
    assert region["investor_kinds"] == ["dfi"]
    assert region["companies"] == []

    ytd = rs.parse_question("What acquisitions happened in Kenyan banking this year?", today)
    assert (ytd["since"], ytd["until"]) == ("2026-01-01", "2026-10-16")
    last_year = rs.parse_question("What happened in Ghana last year?", today)
    assert (last_year["since"], last_year["until"]) == ("2025-01-01", "2025-12-31")


def test_parse_question_ignores_instruction_words_and_prefers_explicit_year():
    question = ("Who acquired Paystack, when was the acquisition announced in 2020? "
                "Provide source URLs and distinguish confirmed facts from evidence.")
    parsed = rs.parse_question(question, date(2026, 10, 16))

    assert parsed["companies"] == ["Paystack"]
    assert not {"url", "urls", "source", "sources", "evidence"} & set(parsed["terms"])
    assert (parsed["since"], parsed["until"]) == ("2020-01-01", "2020-12-31")


def test_parse_question_keeps_company_name_before_trailing_country_name():
    parsed = rs.parse_question("Who acquired AON Holdings Botswana in 2020?", date(2026, 10, 16))

    assert parsed["countries"] == ["BW"]
    assert parsed["companies"] == ["AON Holdings"]
    assert parsed["since"] == "2020-01-01"


def test_parse_question_does_not_turn_accented_country_name_into_company_names():
    parsed = rs.parse_question("What acquisitions were announced in Côte d’Ivoire in 2020?",
                               date(2026, 10, 16))

    assert parsed["countries"] == ["CI"]
    assert parsed["companies"] == []


def test_parse_question_understands_spelled_out_relative_periods():
    today = date(2026, 10, 16)
    six_months = rs.parse_question("What funding was announced in the last six months?", today)
    ninety_days = rs.parse_question("What changed in the past 90 days?", today)
    last_year = rs.parse_question("What acquisitions happened last year?", today)

    assert six_months["since"] == "2026-04-19" and six_months["until"] is None
    assert ninety_days["since"] == "2026-07-18" and ninety_days["until"] is None
    assert (last_year["since"], last_year["until"]) == ("2025-01-01", "2025-12-31")


def test_research_broadens_undated_search_when_recent_results_miss_intent():
    class Client:
        urls = []

        def get(self, url):
            self.urls.append(url)
            if len(self.urls) == 1:
                body = ("<rss><channel><item><title>Paystack launches new checkout</title>"
                        "<link>https://news.google.com/rss/articles/recent</link>"
                        "<pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item></channel></rss>")
            else:
                body = ("<rss><channel><item><title>Stripe buys Nigeria's Paystack</title>"
                        "<link>https://news.google.com/rss/articles/acquisition</link>"
                        "<pubDate>Thu, 15 Oct 2020 08:00:00 GMT</pubDate></item></channel></rss>")
            return type("Response", (), {"text": body, "raise_for_status": lambda self: None})()

    client = Client()
    items = rs._news_items("Paystack acquired", None, client=client)

    assert len(client.urls) == 2
    assert "when%3A90d" in client.urls[0]
    assert "when%3A90d" not in client.urls[1]
    assert items[0]["title"] == "Stripe buys Nigeria's Paystack"
    assert items[0]["date"] == "2020-10-15"


def test_research_prompt_who_acquired_paystack_and_when_synthesizes_evidence():
    question = "Who acquired Paystack, and when?"
    evidence = [
        {"title": "Nigerian fintech startup Brass acquired by Paystack-led consortium",
         "date": "2024-05-29", "url": "https://example.com/brass"},
        {"title": "Nigerian fintech startup Paystack acquired by Stripe in landmark moment",
         "snippet": "Paystack acquired by Stripe.", "date": "2020-10-15", "publisher": "Reuters",
         "url": "https://www.reuters.com/world/africa/stripe-buys-paystack-2020-10-15/"},
    ]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))

    assert result["parsed"]["companies"] == ["Paystack"]
    assert "Reports identify Stripe as the acquirer of Paystack" in result["answer"]
    assert "2020-10-15" in result["answer"] and "[1]" in result["answer"]
    assert "Reports identify Paystack as the acquirer" not in result["answer"]
    assert all("Brass" not in item["title"] for item in result["evidence"])


def test_research_prompt_paystack_2020_uses_article_url_and_synthesizes():
    question = "Who acquired Paystack in 2020? Provide source URLs."
    evidence = [{
        "title": "Stripe buys Nigeria's Paystack",
        "snippet": "Stripe announced its acquisition of Paystack.",
        "date": "2020-10-15",
        "publisher": "Reuters",
        "url": "https://www.reuters.com/world/africa/stripe-buys-paystack-2020-10-15/",
        "publisher_url": "https://www.reuters.com",
    }]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))

    assert result["parsed"]["companies"] == ["Paystack"]
    assert (result["parsed"]["since"], result["parsed"]["until"]) == ("2020-01-01", "2020-12-31")
    assert "Reports identify Stripe as the acquirer of Paystack" in result["answer"]
    assert result["evidence"][0]["url"] == evidence[0]["url"]
    assert evidence[0]["publisher_url"] not in result["answer"]


def test_research_marks_reported_acquisition_value_unconfirmed():
    question = "Who acquired Paystack in 2020, and what was the transaction value?"
    evidence = [{
        "title": "Paystack acquired by Stripe for a reported $200 million",
        "date": "2020-10-15",
        "url": "https://example.com/paystack-acquisition",
    }]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))

    assert "Stripe" in result["answer"]
    assert "reports $200 million" in result["answer"]
    assert "does not confirm it as the publicly disclosed deal value" in result["answer"]


def test_research_prompt_nigerian_fintech_last_six_months_filters_and_summarizes():
    question = "What funding did Nigerian fintech companies announce in the last six months?"
    evidence = [
        {"title": "Nigerian fintech raises $20 million", "date": "2026-05-01", "url": "https://example.com/new"},
        {"title": "Nigerian fintech raises $10 million", "date": "2026-01-01", "url": "https://example.com/old"},
    ]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))
    news_titles = [item["title"] for item in result["evidence"] if item["kind"] == "news"]

    assert result["parsed"]["countries"] == ["NG"] and result["parsed"]["sectors"] == ["fintech"]
    assert result["parsed"]["since"] == "2026-04-19"
    assert news_titles == ["Nigerian fintech raises $20 million"]
    assert "Funding-related reports in the requested period" in result["answer"]
    assert "[1]" in result["answer"]


def test_research_flutterwave_series_e_audit_does_not_call_valuation_amount_raised():
    question = ("Audit Flutterwave's reported $3.2 billion Series E. Separate amount raised from "
                "valuation and cite evidence for each field.")
    parsed = rs.parse_question(question, date(2026, 10, 16))
    evidence = [
        {"title": "Flutterwave lands Series E, pushes valuation to $3.2 billion",
         "date": "2026-06-17", "url": "https://news.google.com/rss/articles/techpoint-series-e"},
        {"title": "Flutterwave raises Series E funding at $3.2bn valuation; Ripple participates",
         "date": "2026-06-17", "url": "https://news.google.com/rss/articles/disrupt-series-e"},
    ]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))

    assert parsed["companies"] == ["Flutterwave"]
    assert "Amount raised: unknown" in result["answer"]
    assert "Valuation: $3.2" in result["answer"]
    assert "[1]" in result["answer"] and "[2]" in result["answer"]
    assert all("news.google.com/rss/articles/" in item["url"] for item in result["evidence"]
               if item["kind"] == "news")


def test_research_flutterwave_series_e_audit_separates_explicit_amount_and_valuation():
    question = "Audit Flutterwave Series E: separate amount raised from valuation."
    evidence = [{
        "title": "Flutterwave raised $250 million in Series E at a $3.2 billion valuation",
        "date": "2026-06-17",
        "url": "https://news.google.com/rss/articles/flutterwave-series-e",
    }]

    result = rs.research(question, news=lambda *_: evidence, today=date(2026, 10, 16))

    assert "Amount raised: $250 million [1]" in result["answer"]
    assert "Valuation: $3.2 billion [1]" in result["answer"]


def test_research_keeps_explicit_company_and_event_date_scope():
    deals = [
        _deal("Nigeria’s Moniepoint raises $110m Series C", published="2025-04-01"),
        _deal("Nigeria’s Paystack raises $100m Series C", published="2025-05-01"),
        _deal("Nigeria’s Moniepoint raises $200m Series D", published="2026-04-01"),
    ]
    _, evidence = rs.retrieve("Moniepoint raised money in Nigeria in 2025", deals, live_news=False,
                              today=date(2026, 10, 16))
    assert [item["title"] for item in evidence if item["kind"] == "deal"] == [
        "Nigeria’s Moniepoint raises $110m Series C"
    ]

    events = [
        {"headline": "Nigeria bank reports a loss", "signal_type": "earnings_surprise", "day": "2025-06-01",
         "country": "NG", "countries": ["NG"]},
        {"headline": "Nigeria bank reports a profit", "signal_type": "earnings_surprise", "day": "2026-06-01",
         "country": "NG", "countries": ["NG"]},
    ]
    _, evidence = rs.retrieve("What happened in Nigeria in 2025?", events=events, live_news=False,
                              today=date(2026, 10, 16))
    assert [item["title"] for item in evidence if item["kind"] == "event"] == [
        "Nigeria bank reports a loss"
    ]


def test_research_live_news_uses_requested_date_scope():
    class Client:
        url = ""

        def get(self, url):
            self.url = url
            return type("Response", (), {"text": "<rss/>", "raise_for_status": lambda self: None})()

    client = Client()
    rs._news_items("fintech", "NG", client=client, since="2025-01-01", until="2025-12-31")
    assert "after%3A2025-01-01" in client.url
    assert "before%3A2025-12-31" in client.url
    assert "when%3A90d" not in client.url


def test_research_live_news_runs_when_local_evidence_exceeds_limit_and_is_preserved():
    briefs = [{"company": "Moniepoint", "severity": "medium", "brief": {"detected_signals": []}}
              for _ in range(35)]
    news_items = [{"title": f"Moniepoint update {i}", "snippet": "A relevant company update.",
                   "date": "2026-10-10", "url": f"https://example.com/{i}", "publisher": "Example"}
                  for i in range(8)]
    calls = []

    def search(query, country):
        calls.append((query, country))
        return news_items

    _, evidence = rs.retrieve("Moniepoint", briefs=briefs, news=search)

    assert len(briefs) >= 30
    assert calls and calls[0][0] == "Moniepoint"
    assert len(evidence) == 30
    assert sum(item["kind"] == "news" for item in evidence) == 8
    assert sum(item["kind"] == "brief" for item in evidence) == 22
    assert [item["n"] for item in evidence] == list(range(1, 31))


def test_research_live_news_keeps_only_date_valid_results():
    news_items = [
        {"title": "Old Moniepoint update", "date": "2024-12-31"},
        {"title": "Undated Moniepoint update", "date": None},
        {"title": "In-scope Moniepoint update", "date": "2025-06-01"},
    ]

    _, evidence = rs.retrieve("What happened to Moniepoint in 2025?", news=lambda *_: news_items,
                              today=date(2026, 10, 16))

    assert [item["title"] for item in evidence if item["kind"] == "news"] == [
        "In-scope Moniepoint update"
    ]


def test_research_queries_include_country_for_all_54_countries():
    for country in ac.COUNTRIES:
        question = f"What funding rounds were announced in {country.name} in 2024?"
        captured = []
        parsed, _ = rs.retrieve(
            question,
            today=date(2026, 10, 16),
            news=lambda query, code: captured.append((query, code)) or [],
        )

        assert country.iso2 in parsed["countries"], country.name
        assert captured[0][1] == country.iso2, country.name
        assert country.name.lower() in captured[0][0].lower(), country.name


def test_research_query_does_not_duplicate_accented_country_fragments_as_keywords():
    captured = []
    rs.retrieve(
        "What acquisitions were announced in Côte d’Ivoire in 2020?",
        today=date(2026, 10, 16),
        news=lambda query, code: captured.append((query, code)) or [],
    )

    assert captured[0][1] == "CI"
    assert captured[0][0].count("Ivoire") == 1


@pytest.mark.parametrize(("code", "expected_term"), [
    ("SN", "lève levée de fonds"),
    ("AO", "capta rodada financiamento"),
    ("DZ", "تمويل استثمار"),
    ("GQ", "financiación inversión"),
])
def test_research_news_query_adds_country_language_terms(code, expected_term):
    class Client:
        urls = []

        def get(self, url):
            self.urls.append(url)
            return type("Response", (), {"text": "<rss/>", "raise_for_status": lambda self: None})()

    client = Client()
    rs._news_items("funding rounds announced", code, client=client, since="2024-01-01", until="2024-12-31")
    queries = [unquote(url) for url in client.urls]

    assert all(ac.get(code).name in query for query in queries)
    assert any(expected_term.split()[0] in query and " OR " in query for query in queries)


def test_research_retries_historical_search_without_date_operators_when_empty():
    class Client:
        urls = []

        def get(self, url):
            decoded_url = unquote(url)
            self.urls.append(decoded_url)
            if "after:" in decoded_url:
                body = "<rss/>"
            else:
                body = (
                    "<rss><channel><item><title>Financement d'une entreprise en Guinée</title>"
                    "<link>https://news.google.com/rss/articles/historical</link>"
                    "<pubDate>Mon, 15 Jul 2024 08:00:00 GMT</pubDate>"
                    "</item></channel></rss>"
                )
            return type("Response", (), {"text": body, "raise_for_status": lambda self: None})()

    client = Client()
    items = rs._news_items("Guinée funding", "GN", client=client, since="2024-01-01", until="2024-12-31")

    assert items and items[0]["date"] == "2024-07-15"
    assert any("after:2024-01-01" in url for url in client.urls)
    assert any("after:" not in url and "Guinée" in url for url in client.urls)


@pytest.mark.parametrize("headline", [
    "Une entreprise au Sénégal lève des fonds pour son expansion",
    "Empresa em Angola capta fundos para expansão",
    "تعلن شركة في الجزائر عن تمويل جديد",
])
def test_research_recognizes_non_english_funding_announcements(headline):
    assert rs._FUNDING_ANNOUNCEMENT.search(headline)


@pytest.mark.parametrize("headline", [
    "La startup Eyone lève 1 million de dollars",
    "Sénégal : Socium lève 3,2 milliards FCFA pour révolutionner la tech",
    "BHub capta R$ 74 milhões em rodada de financiamento",
    "Startup raises seed funding for a renewable-energy project",
])
def test_research_accepts_company_equity_announcements_in_local_languages(headline):
    assert rs._is_equity_funding_announcement(headline)


@pytest.mark.parametrize("headline", [
    "L’État du Sénégal lève des obligations sur le marché régional",
    "L’Etat du Sénégal lève 300 millions de dollars à l’international via JP Morgan",
    "Le Sénégal lève 300 millions de dollars après que le FMI a suspendu ses versements",
    "Sénégal : lancement des travaux du port de Ndayane, 1 milliard de dollars d’investissement",
    "Le Sénégal lève 44 milliards de FCFA sur le marché financier de l’UMOA",
    "Algeria Lands $455 Million Deal With Italy’s BF for Regenerative Ag Development",
    "الجزائر ستعزز تمويل القطاع الزراعي في العام 2025",
    "Sénégal : démenti d’une levée de fonds infructueuse",
    "Financiamento islâmico para compra de carros",
    "Afreximbank anuncia mais financiamento alocado à indústria criativa",
    "Afreximbank anuncia financiamento alocado a empresas",
    "تمويل الأحزاب السياسية يعود إلى الواجهة",
    "Axian Energy obtient un financement de 84 millions d’euros pour un projet solaire",
])
def test_research_rejects_denials_and_non_equity_funding_as_equity_rounds(headline):
    assert not rs._is_equity_funding_announcement(headline)


def test_research_country_matching_does_not_confuse_company_nationality_with_deal_location():
    assert not rs._news_matches_country(
        {"title": "Ivorian banking group takes control of a Gabonese bank"}, "CI")
    assert rs._news_matches_country(
        {"title": "DPO expands through acquisition of licenses in Côte d'Ivoire"}, "CI")


def test_research_does_not_treat_film_awards_acquisition_as_corporate_m_and_a():
    assert not rs._is_acquisition_announcement(
        "Neon Buys Ivory Coast Awards Contender Night of the Kings")


def test_research_ranks_intent_matching_articles_ahead_of_newer_noise():
    query = "Côte d'Ivoire acquisition announced"
    items = [
        {"title": "Côte d'Ivoire opens a new factory", "date": "2020-12-16",
         "url": "https://example.com/no-acquisition"},
        {"title": "DPO expands through the acquisition of licenses in Côte d'Ivoire",
         "date": "2020-01-27", "url": "https://example.com/acquisition"},
    ]

    ranked = rs._rank_news(query, items)

    assert ranked[0]["url"] == "https://example.com/acquisition"


def test_research_country_filter_excludes_other_country_results_and_keeps_localized_match():
    evidence = [
        {"title": "Ghana fintech raises funding for regional expansion", "date": "2024-05-01",
         "url": "https://example.com/ghana"},
        {"title": "Une entreprise au Sénégal lève des fonds pour son expansion", "date": "2024-06-01",
         "url": "https://example.com/senegal"},
    ]

    result = rs.research(
        "What funding did companies announce in Senegal in 2024?",
        news=lambda *_: evidence,
        today=date(2026, 10, 16),
    )

    news_titles = [item["title"] for item in result["evidence"] if item["kind"] == "news"]
    assert news_titles == ["Une entreprise au Sénégal lève des fonds pour son expansion"]


def test_research_country_filter_applies_to_generic_corporate_events():
    evidence = [
        {"title": "Corporate conference held in the United States", "date": "2024-05-01",
         "url": "https://example.com/us"},
        {"title": "Tanzanian company announces a board change", "date": "2024-06-01",
         "url": "https://example.com/tanzania"},
    ]

    result = rs.research(
        "What major corporate events affected companies in Tanzania in 2024?",
        news=lambda *_: evidence,
        today=date(2026, 10, 16),
    )

    news_titles = [item["title"] for item in result["evidence"] if item["kind"] == "news"]
    assert news_titles == ["Tanzanian company announces a board change"]


def test_research_generic_acquisition_query_keeps_only_acquisition_headlines():
    evidence = [
        {"title": "Le Groupe DPO élargit sa présence avec l’acquisition de licences en Côte d'Ivoire",
         "date": "2020-01-27", "url": "https://example.com/acquisition"},
        {"title": "Côte d'Ivoire : les entreprises annoncent leurs résultats annuels",
         "date": "2020-01-28", "url": "https://example.com/results"},
    ]

    result = rs.research(
        "What acquisitions were announced in Côte d’Ivoire in 2020?",
        news=lambda *_: evidence,
        today=date(2026, 10, 16),
    )

    news_titles = [item["title"] for item in result["evidence"] if item["kind"] == "news"]
    assert result["parsed"]["companies"] == []
    assert news_titles == [evidence[0]["title"]]


def test_research_uses_article_url_instead_of_publisher_homepage():
    news_items = [{
        "title": "Stripe buys Paystack",
        "snippet": "Stripe announced the acquisition.",
        "date": "2020-10-15",
        "publisher": "Reuters",
        "publisher_url": "https://www.reuters.com/",
        "url": "https://news.google.com/rss/articles/example",
    }]

    _, evidence = rs.retrieve("When did Stripe acquire Paystack in 2020?", news=lambda *_: news_items,
                              today=date(2026, 10, 16))

    news = next(item for item in evidence if item["kind"] == "news")
    assert news["url"] == "https://news.google.com/rss/articles/example"


def test_research_resolves_google_news_link_to_verified_publisher_article():
    class Client:
        def get(self, url):
            if "rss/search" in url:
                body = (
                    "<rss><channel><item><title>Stripe buys Paystack</title>"
                    "<link>https://news.google.com/rss/articles/example</link>"
                    "<source url=\"https://www.reuters.com\">Reuters</source>"
                    "<pubDate>Thu, 15 Oct 2020 08:00:00 GMT</pubDate></item></channel></rss>"
                )
                return type("Response", (), {
                    "text": body,
                    "raise_for_status": lambda self: None,
                })()
            assert url == "https://news.google.com/rss/articles/example"
            return type("Response", (), {
                "url": "https://www.reuters.com/world/africa/stripe-buys-paystack/",
                "raise_for_status": lambda self: None,
            })()

    items = rs._news_items("Paystack acquisition", None, client=Client(),
                           since="2020-01-01", until="2020-12-31")

    assert items[0]["url"] == "https://www.reuters.com/world/africa/stripe-buys-paystack/"
    assert items[0]["publisher_url"] == "https://www.reuters.com"


@pytest.mark.parametrize("destination", [
    "https://consent.google.com/ml",
    "https://www.reuters.com/",
    "https://unrelated.example.com/article",
])
def test_research_keeps_google_news_url_when_publisher_article_is_unverified(destination):
    google_url = "https://news.google.com/rss/articles/example"

    class Client:
        def get(self, url):
            if "rss/search" in url:
                body = (
                    "<rss><channel><item><title>Stripe buys Paystack</title>"
                    f"<link>{google_url}</link>"
                    "<source url=\"https://www.reuters.com\">Reuters</source>"
                    "<pubDate>Thu, 15 Oct 2020 08:00:00 GMT</pubDate></item></channel></rss>"
                )
                return type("Response", (), {
                    "text": body,
                    "raise_for_status": lambda self: None,
                })()
            return type("Response", (), {
                "url": destination,
                "raise_for_status": lambda self: None,
            })()

    items = rs._news_items("Paystack acquisition", None, client=Client(),
                           since="2020-01-01", until="2020-12-31")

    assert items[0]["url"] == google_url


def test_research_keeps_google_news_url_when_article_resolution_fails():
    google_url = "https://news.google.com/rss/articles/example"

    class Client:
        def get(self, url):
            if "rss/search" in url:
                body = (
                    "<rss><channel><item><title>Stripe buys Paystack</title>"
                    f"<link>{google_url}</link>"
                    "<source url=\"https://www.reuters.com\">Reuters</source>"
                    "<pubDate>Thu, 15 Oct 2020 08:00:00 GMT</pubDate></item></channel></rss>"
                )
                return type("Response", (), {
                    "text": body,
                    "raise_for_status": lambda self: None,
                })()
            raise rs.httpx.ConnectError("Google News resolution unavailable")

    items = rs._news_items("Paystack acquisition", None, client=Client(),
                           since="2020-01-01", until="2020-12-31")

    assert items[0]["url"] == google_url


def test_research_rss_failure_is_logged_and_does_not_crash(monkeypatch, caplog):
    class FailingClient:
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            raise TimeoutError("RSS request timed out")

    monkeypatch.setattr(rs.httpx, "Client", FailingClient)
    with caplog.at_level("ERROR"):
        result = rs.research("Recent Moniepoint updates")

    assert result["mode"] == "deterministic"
    assert result["evidence"] == []
    assert "research news RSS fetch or parse failed" in caplog.text


def test_research_rss_success_with_no_feed_items_is_distinguished(caplog):
    class Client:
        def get(self, url):
            return type("Response", (), {"text": "<rss/>", "raise_for_status": lambda self: None})()

    with caplog.at_level("INFO"):
        assert rs._news_items("Moniepoint", None, client=Client()) == []

    assert "research news RSS search completed with no feed items" in caplog.text


def test_research_evidence_coverage_reports_counts_and_latest_source_dates():
    coverage = rs.evidence_coverage([
        {"kind": "deal", "date": "2025-01-10"},
        {"kind": "deal", "date": "2025-04-12"},
        {"kind": "news", "date": "2025-03-01"},
        {"kind": "news", "date": None},
    ])

    assert coverage == [
        {"kind": "deal", "items": 2, "latest_source_date": "2025-04-12"},
        {"kind": "news", "items": 2, "latest_source_date": "2025-03-01"},
    ]


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
        return "## Cloud9 update\n\n**Cloud9** raised $500,000 [2].\n\n- Kenya's currency risk is low [4]."
    r = rs.research("Kenya fintech funding and currency risk", deals, [], live_news=False, llm=fake_llm)
    kinds = [i["kind"] for i in r["evidence"]]
    assert kinds[:2] == ["statistics", "deal"] and "country_risk" in kinds and "currency_risk" in kinds
    assert "[2] (deal" in seen["user"] and "ONLY the numbered evidence" in rs.SYSTEM
    assert r["mode"] == "llm" and r["validation"]["grounded_share"] == 1.0
    assert "##" not in r["answer"] and "**" not in r["answer"]
    assert not any(line.lstrip().startswith(("-", "*")) for line in r["answer"].splitlines())
    assert "Cloud9 raised $500,000 [2]." in r["answer"]


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
    assert any(item["kind"] == "deal" and "Cloud9" in item["title"] for item in r["evidence"])


# ── Monitoring, coverage ──────────────────────────────────────────────────────

from src.engines import coverage as cov  # noqa: E402
from src.engines import watch  # noqa: E402


def test_watchlist_matching_and_rss():
    wl = {"id": "w1", "name": "Kenya banks", "companies": ["Paramount Bank", "Safaricom"], "countries": ["GH"],
          "signal_types": [], "include_deals": True}
    events = mf.to_events([{"title": "Ghana bank fined by Bank of Ghana for breaches", "date": "2026-10-12"},
                           {"title": "Safaricom CEO resigns with immediate effect", "date": "2026-10-13"}])
    deals = [_deal("Zenith Bank Completes Acquisition Of Kenya’s Paramount Bank", publisher="Proshare", url="https://x/1")]
    alerts = watch.matches(wl, events, deals)
    assert [(a["kind"], a["why"]) for a in alerts] == [
        ("event", ["company: Safaricom"]), ("event", ["country: GH"]), ("deal", ["company: Paramount Bank"])]
    assert watch.matches({**wl, "signal_types": ["leadership_change"]}, events, [])[0]["title"].startswith("Safaricom")
    feed = watch.rss(wl, alerts, "https://app/watch/w1")
    assert feed.count("<item>") == 3 and "Kenya banks | Deal Intelligence" in feed


@pytest.mark.parametrize("url,ok", [("https://hooks.slack.com/services/x", True), ("http://example.com", False),
                                    ("https://localhost/x", False), ("https://10.0.0.1/x", False),
                                    ("https://192.168.1.4/hook", False), (None, True)])
def test_webhook_urls_must_be_public_https(url, ok):
    assert watch.valid_webhook(url) is ok


def test_coverage_matrix_covers_54_countries_with_tiers():
    m = cov.matrix([_deal("Wave lève 90 millions de dollars au Sénégal")])
    assert m["summary"]["countries"] == 54 and set(m["summary"]["by_tier"]) <= {"A", "B", "C"}
    rows = {r["iso2"]: r for r in m["countries"]}
    assert rows["NG"]["tier"] == "A" and rows["ZA"]["tier"] == "B" and rows["TD"]["tier"] == "C"
    assert rows["SN"]["deals"] == 1 and rows["SN"]["news"]["national_edition"]


def test_coverage_by_year_counts_depth_per_announcement_year():
    ds = [{"announced": "2011-03-02", "amount_usd": 5e6, "countries": ["NG", "GH"]},
          {"announced": "2011-07-09", "countries": ["NG"]},
          {"announced": "2024-01-15", "amount_usd": 2e6, "country": "KE"},
          {"announced": None}]
    assert cov.by_year(ds) == [
        {"year": 2011, "deals": 2, "with_amount": 1, "value_usd": 5000000, "countries": 2},
        {"year": 2024, "deals": 1, "with_amount": 1, "value_usd": 2000000, "countries": 1},
    ]


@pytest.mark.parametrize("title", [
    "La Côte d’Ivoire lève 454,205 milliards de FCFA sur le marché financier de l’UMOA",
    "Le Burkina lève 49,500 milliards de FCFA sur le marché financier de l’UMOA",
    "Airtel Money gets $7 billion price tag as investors prepare to sell shares in African fintech",
    "Afreximbank raises CARICOM financing cap to $5 billion",
    "Tinubu Backs Flutterwave's Nigeria Listing as $3B Fintech Giant",
])
def test_sovereigns_valuations_and_endorsements_are_not_deals(title):
    assert _deal(title) is None


def test_french_decimal_comma_and_ipo_offer_size():
    assert dl.parse_amounts("454,205 milliards de FCFA") == [(pytest.approx(454.205e9), "XOF")]
    assert dl.parse_amounts("$1,200 million") == [(pytest.approx(1.2e9), "USD")]
    d = _deal("Air Côte d’Ivoire obtient un financement de 47,913 milliards FCFA de la BADEA")
    assert d["deal_type"] == "debt_financing" and d["amount"] == pytest.approx(47.913e9)
    assert _deal("Dangote Plans Landmark Multi-Exchange Listing Of $20bn Refinery Across Africa")["amount_usd"] is None
    assert _deal("MTN Nigeria plans $1bn IPO on NGX")["amount_usd"] == 1e9


def test_transaction_amount_beats_project_cost_and_pledges():
    d = _deal("AFC backs Dangote’s $7 billion fertiliser expansion with $600 million loan in Nigeria")
    assert (d["deal_type"], d["buyer"], d["target"], d["amount_usd"]) == ("debt_financing", "AFC", "Dangote", 600e6)
    d = _deal("Guinée équatoriale : Vista Bank rachète Société Générale et promet 10 milliards USD d’investissements")
    assert (d["buyer"], d["target"], d["amount_usd"]) == ("Vista Bank", "Société Générale", None)
    assert _deal("Dangote raises Ethiopia fertilizer investment capital to $4b") is None


@pytest.mark.parametrize("title,expected", [
    ("BOAD Approves $49.5M Loan for Air Côte d'Ivoire’s Airbus Purchase", ("debt_financing", "Air Côte d'Ivoire", "BOAD")),
    ("Holcim To Sell Nigerian Operations To Chinese Company Huaxin Cement", ("exit", "Holcim Nigeria", "Huaxin Cement")),
    ("Nedbank Wins Regulatory Approval To Take Majority Stake In Kenya’s NCBA", ("acquisition", "NCBA", "Nedbank")),
    ("ARM-Harith Achieves US$76m First Close For Climate Transition Fund in Nigeria", ("fund_raise", "ARM-Harith", None)),
    ("Mines : L'indien A2MP lève 171 milliards de FCFA pour financer ses projets au Gabon", ("equity_funding", "A2MP", None)),
])
def test_counterparty_resolution(title, expected):
    d = _deal(title)
    assert (d["deal_type"], d["target"], d["buyer"]) == expected


@pytest.mark.parametrize("title", [
    "Namibian Air Force acquires Shaanxi Y-9 transport aircraft from China",
    "Three New ETFs Listed on the Johannesburg Stock Exchange in South Africa",
    "Nigeria’s Biggest Bank Raises $228 Million in Rights Offer",
])
def test_state_purchases_and_unnamed_parties_are_dropped(title):
    assert _deal(title) is None


@pytest.mark.parametrize("title,expected", [
    ("Ethiopia: MIDROC Investment Group and International Finance Corporation Sign USD 80 Million Loan",
     ("debt_financing", "MIDROC Investment Group", "International Finance Corporation")),
    ("Afreximbank signs US$100 million facility with Ecobank Ghana", ("debt_financing", "Ecobank Ghana", "Afreximbank")),
    ("LoftyInc Capital raises $43m to invest in seed and Series A startups across Africa", ("fund_raise", "LoftyInc Capital", None)),
])
def test_lender_borrower_and_fund_purpose(title, expected):
    d = _deal(title)
    assert (d["deal_type"], d["target"], d["buyer"]) == expected


@pytest.mark.parametrize("title", [
    "Kani Releasing Acquires North America Rights To Japanese Title in Namibia",
    "WeWire Acquires Treasury License in Mauritius to Scale Cross-Border Trade Tools",
    "To Grow Africa’s AI Economy, Microsoft Invests $300 Million In Datacenters",
    "Brazzaville lève 700 millions de dollars sur les marchés internationaux",
    "Afreximbank signs US$500 million term loan facility with the Central Bank of Tunisia",
])
def test_rights_capex_and_sovereign_finance_are_not_deals(title):
    assert _deal(title) is None


def test_research_filters_and_labels_investor_types():
    deals = [_deal("Kenya's ARC Ride raises $5m from Proparco"),
             _deal("Kenyan neobank Cloud9 raises $500,000 from crypto accelerator Alliance")]
    p, items = rs.retrieve("Which development finance institutions invested in Kenya?", deals, [], live_news=False)
    assert p["investor_kinds"] == ["dfi"]
    texts = [i["text"] for i in items if i["kind"] == "deal"]
    assert len(texts) == 1 and "Proparco (development finance institution)" in texts[0]
    assert any(i["kind"] == "investor" and i["title"] == "Proparco activity" for i in items)

    regional = [_deal("Senegal's ARC Ride raises $5m from Proparco"),
                _deal("Kenya's ARC Ride raises $5m from Proparco")]
    p, items = rs.retrieve("Which DFIs are most active in West Africa?", regional, [], live_news=False)
    assert p["countries"] == [c.iso2 for c in ac.COUNTRIES if c.region == "Western Africa"]
    assert [i["title"] for i in items if i["kind"] == "deal"] == [
        "Senegal's ARC Ride raises $5m from Proparco"
    ]


# ── Measured outcomes: calibration and expected moves come from data ─────────

from src.engines import measured as ms  # noqa: E402


def _pred(st, sev, confirmed=None, correct=None, move=None, alpha=None):
    return {"signal_type": st, "severity": sev, "event_confirmed": confirmed, "direction_correct": correct,
            "abnormal_return_10d_pct": move, "alpha": alpha}


def test_measured_tables_count_only_what_happened():
    preds = ([_pred("m_and_a_activity", "low", c, move=m) for c, m in [(True, 2.0), (False, -1.0), (False, -3.0)]]
             + [_pred("insider_activity", "high", correct=k, move=1.0) for k in (True, False)])
    t = ms.build(preds)
    ma = t["signals"]["m_and_a_activity"]["type"]
    assert ma["confirmation"] == {"labelled": 3, "confirmed": 1, "rate": 0.3333}
    assert ma["moves"]["median"] == -1.0 and ma["moves"]["n"] == 3
    assert t["signals"]["insider_activity"]["type"]["direction"] == {"labelled": 2, "correct": 1, "rate": 0.5}
    assert t["overall_confirmation"]["rate"] == 0.3333


def test_no_history_means_no_invented_move():
    ms.set_tables({"signals": {}, "overall_confirmation": {"labelled": 0, "confirmed": 0, "rate": None}})
    try:
        assert ms.expected_move("credit_risk", "high") is None
        assert ms.confirmation_rate("credit_risk", "high")["n"] == 0
    finally:
        ms.set_tables(None)


def test_signed_ranges_and_legacy_briefs():
    assert ms.signed_range("negative", 8.0, 20.0) == (-20.0, -8.0)        # stored before measured moves
    assert ms.signed_range("negative", -3.0, 1.0) == (-3.0, 1.0)
    assert ms.magnitude_error(-5.0, "negative", -6.0, -2.0) == 1.0
    assert ms.describe_move(-2.8, 1.3, -1.3, 53) == "-2.8% to +1.3% (median -1.3%, n=53)"


def test_committed_tables_have_no_hand_typed_rows():
    t = ms.load()
    assert t["source"].startswith("walk-forward historical backtest")
    for entry in t["signals"].values():
        moves = entry["type"]["moves"]
        assert moves is None or moves["n"] >= 1


def test_alpha_validation_reports_bands_and_correlation():
    from src.engines.historical_backtest import alpha_validation, spearman
    preds = [_pred("m_and_a_activity", "low", confirmed=a > 60, move=1.0, alpha=a) for a in range(40, 85, 5)]
    v = alpha_validation(preds)
    assert v["bands"]["high"]["precision"] == 1.0 and v["bands"]["low"]["precision"] == 0.0
    assert v["verdict"] == "confirmations rose with alpha across all three thirds"
    peaked = [_pred("m_and_a_activity", "low", confirmed=55 <= a < 70, move=1.0, alpha=a) for a in range(40, 85, 5)]
    assert alpha_validation(peaked)["verdict"] == "higher alpha did not go with more confirmations"
    middle = [_pred("m_and_a_activity", "low", confirmed=a >= 55 and a != 75, move=1.0, alpha=a) for a in range(40, 85, 5)]
    assert alpha_validation(middle)["verdict"] == "the lowest alpha third confirmed least; the top third did not beat the middle"
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0 and spearman([1, 2, 3], [3, 2, 1]) == -1.0


def test_live_outcomes_move_the_measured_tables():
    preds = [_pred("leadership_change", "high", c, move=m) for c, m in [(True, -2.0), (False, 1.0)] * 6]
    ms.set_tables(ms.build(preds))
    try:
        before = ms.confirmation_rate("leadership_change", "high")
        assert ms.load()["live_observations"] == 0
        live = [{"signal_type": "leadership_change", "severity_at_detection": "high", "event_confirmed": True,
                 "direction_correct": None, "abnormal_return_10d_pct": -5.0}] * 12
        ms.set_live(live + [{"signal_type": "leadership_change", "severity_at_detection": "high"}])  # unlabelled: ignored
        t = ms.load()
        assert t["backtest_observations"] == 12 and t["live_observations"] == 12
        after = ms.confirmation_rate("leadership_change", "high")
        assert after["n"] == 24 and after["rate"] > before["rate"]
        assert ms.expected_move("leadership_change", "high")["median"] < -2.0
        ms.set_live(None)
        assert ms.confirmation_rate("leadership_change", "high") == before
    finally:
        ms.set_live(None)
        ms.set_tables(None)


def test_committed_tables_keep_their_observations():
    t = ms.load()
    assert len(t.get("observations", [])) == t["backtest_observations"] > 0


from datetime import timedelta  # noqa: E402

from src.engines import pulse  # noqa: E402


def test_pulse_counts_only_stored_records():
    d = [
        {"id": "a", "deal_type": "acquisition", "announced": "2026-10-10", "amount_usd": 5e6, "country": "KE",
         "countries": ["KE"], "headline": "A buys B", "sources": [{"publisher": "X"}], "investors": []},
        {"id": "b", "deal_type": "equity_funding", "announced": "2026-10-01", "amount_usd": None, "country": "NG",
         "countries": ["NG"], "headline": "C raises", "sources": [], "investors": []},
        {"id": "c", "deal_type": "acquisition", "announced": "2025-01-01", "amount_usd": 9e9, "country": "ZA",
         "countries": ["ZA"], "headline": "old", "sources": [], "investors": []},
    ]
    e = [{"id": "e1", "day": "2026-10-12", "signal_type": "credit_risk", "country": "GH", "headline": "h"},
         {"id": "e2", "day": "2026-09-01", "signal_type": "credit_risk", "country": "GH", "headline": "old"}]
    p = pulse.build(d, e, {"backtest_observations": 1}, today=date(2026, 10, 14))
    assert p["deals"]["total"] == 3 and p["deals"]["countries"] == 3
    assert p["deals"]["recent"] == 2 and p["deals"]["recent_disclosed_usd"] == 5_000_000
    assert p["deals"]["recent_disclosed_n"] == 1
    assert p["deals"]["largest"]["id"] == "a"
    assert [x["id"] for x in p["deals"]["latest"]] == ["a", "b"]
    assert p["deals"]["top_countries"][0]["name"] in {"Kenya", "Nigeria"}
    assert p["events"]["recent"] == 1 and p["events"]["latest"][0]["country"]["name"] == "Ghana"
    assert p["latest_record"] == "2026-10-12"


from src.engines import showcase  # noqa: E402


def test_showcase_rotates_through_every_company():
    seen = set()
    for k in range(2):
        seen.update(c[0] for c in showcase.todays_batch(date(2026, 10, 14) + timedelta(days=k)))
    assert seen == {c[0] for c in showcase.COMPANIES}


def test_showcase_summary_uses_the_reviewed_sources():
    brief = {
        "company_name": "Safaricom", "ticker": "SCOM.NR", "overall_severity": "high", "top_alpha_score": 71.2,
        "analyst_model": "openai/gpt-oss-120b", "requires_human_review": True,
        "filings_reviewed": [], "news_reviewed": [{"title": "Safaricom CEO resigns - Business Daily", "source": "Business Daily",
                                                   "url": "u1", "published_date": "2026-10-10"}],
        "signal_candidates_count": 2,
        "detected_signals": [
            {"signal_type": "leadership_change", "severity": "high", "source_urls": ["u1"], "evidence": ["raw text"],
             "alpha_score": {"score": 71.2, "source_credibility": 0.7, "expected_magnitude_pct_low": -3.0,
                             "expected_magnitude_pct_high": 1.0, "comparable_events_n": 40}},
            {"signal_type": "m_and_a_activity", "severity": "low", "source_urls": [], "evidence": ["x"], "alpha_score": {"score": 30}},
        ],
        "reasoning_trace": [{"step": "deterministic_engine", "data": {"off_target": 9, "unattributed": 1,
                                                                       "unattributed_titles": ["Airtel raises prices"]}}],
    }
    s = showcase.summarise(brief, brief_id="b1")
    assert s["market"] == "NSE Kenya" and s["llm_used"] and s["off_target"] == 9
# Unattributed headlines without a verifiable publication date must not be exposed.
    assert s["unattributed_title"] is None
    top = s["signals"][0]
    assert top["signal_type"] == "leadership_change"
    assert top["evidence"] == "Safaricom CEO resigns" and top["source"] == "Business Daily · 0.70 credibility"
    quiet = showcase.summarise({"company_name": "Boeing", "detected_signals": []}, brief_id="b2")
    assert showcase.pick([quiet, s])["id"] == "b1"
    assert showcase.pick([quiet])["id"] == "b2"
    assert showcase.pick([]) is None


def test_common_word_company_names_need_their_corporate_word():
    from src.engines.deterministic_engine import _company_matchers, _mentions_company
    m = _company_matchers("Equity Group", ticker="EQTY.NR")
    assert not _mentions_company("Star Equity Holdings Enters Into Merger Agreement to Acquire Harte Hanks", m)
    assert not _mentions_company("Yorkton Equity Group Inc. completes acquisition", m)
    assert not _mentions_company("Private equity fund closes at $300m", m)
    assert _mentions_company("Kenya’s Equity Bank posts record profit", m)
    assert _mentions_company("Kenyan lender Equity Group expands into Ethiopia", m)
    assert _mentions_company("EQTY shares rise", m)


def _news_candidate(text, publisher):
    from src.schemas.models import SignalCandidate, SignalType
    return SignalCandidate(signal_type=SignalType.MA_ACTIVITY, matched_patterns=["x"], source_text=text,
                           source_url=f"https://example.com/{abs(hash(text + publisher))}", source_type="news",
                           source_name=publisher, entity_mentions=[], corroboration_count=1, raw_score=0.5)


def test_syndicated_copies_are_one_source():
    from src.engines.deterministic_engine import _StoryClusters
    s = _StoryClusters()
    keys = {s.key(_news_candidate("Nimbus agrees to buy Orbit Towers in $2.2 billion deal", "Reuters")),
            s.key(_news_candidate("Nimbus agrees to buy Orbit Towers in $2.2 billion deal - Yahoo Finance", "Yahoo Finance")),
            s.key(_news_candidate("Nimbus agrees to buy Orbit Towers in $2.2bn deal", "MarketScreener")),
            s.key(_news_candidate("Telecom deal: Nimbus to acquire Orbit (Reuters) - the group said on Monday", "Investing.com"))}
    assert len(keys) == 1 and s.duplicates == 3


def test_independent_reports_still_corroborate():
    from src.engines.deterministic_engine import _StoryClusters
    s = _StoryClusters()
    keys = {s.key(_news_candidate("Nimbus agrees to buy Orbit Towers in $2.2 billion deal", "Reuters")),
            s.key(_news_candidate("Orbit board backs takeover by South Africa's Nimbus after strategic review", "TechCabal")),
            s.key(_news_candidate("Nigeria's competition regulator to review Nimbus-Orbit merger filing", "BusinessDay"))}
    assert len(keys) == 3 and s.duplicates == 0


from src.engines import evaluation_report as er  # noqa: E402
from src.engines import provenance as pv  # noqa: E402


def test_wilson_interval_matches_reference_values():
    w = er.wilson(42, 82)
    assert w["value"] == 0.512 and w["low"] == 0.406 and w["high"] == 0.617
    assert er.wilson(0, 0) is None
    assert er.wilson(0, 11)["low"] == 0.0 and er.wilson(11, 11)["high"] == 1.0


def test_report_keeps_confirmation_and_returns_apart():
    preds = [
        {"signal_type": "leadership_change", "market": "us", "event_confirmed": True, "confirmed_by_official_filing": True,
         "direction": "negative", "abnormal_return_10d_pct": -2.0, "direction_correct": True, "alpha": 70},
        {"signal_type": "leadership_change", "market": "us", "event_confirmed": False, "confirmed_by_official_filing": False,
         "direction": "negative", "abnormal_return_10d_pct": 3.0, "direction_correct": False, "alpha": 40},
        {"signal_type": "earnings_surprise", "market": "africa", "event_confirmed": None, "confirmed_by_official_filing": None,
         "direction": "positive", "abnormal_return_10d_pct": 1.0, "direction_correct": True, "alpha": 60},
    ]
    row = er._market_rows(preds[:2], {"base_rate": 0.25, "events": 4, "caught": 1}, "leadership_change", 100)
    ec, mr = row["event_confirmation"], row["market_reaction"]
    assert ec["precision"]["k"] == 1 and ec["precision"]["n"] == 2 and ec["base_rate"]["hits"] == 25
    assert ec["lift"]["value"] == 2.0 and ec["recall"]["n"] == 4
    assert mr["moves_n"] == 2 and mr["mean_move_in_predicted_direction_pct"]["value"] == -0.5   # +2 and -3, signed
    price_only = er._market_rows(preds[2:], {}, "earnings_surprise")
    assert price_only["event_confirmation"] is None and price_only["market_reaction"]["moves_n"] == 1


def _prov_deal(sources, **kw):
    base = {"id": "x", "deal_type": "equity_funding", "stage": "completed", "target": "Zuripay", "buyer": "Kestrel Ventures",
            "investors": ["Kestrel Ventures"], "amount": 110_000_000.0, "currency": "USD", "amount_usd": 110_000_000.0,
            "stake_pct": None, "country": "NG", "sector": "fintech", "announced": "2024-10-29", "sources": sources}
    return {**base, **kw}


def test_provenance_corroboration_needs_independent_stories():
    two = [{"publisher": "TechCabal", "date": "2024-10-29", "url": "u1",
            "title": "Zuripay raises $110 million led by Kestrel Ventures"},
           {"publisher": "BusinessDay", "date": "2024-10-30", "url": "u2",
            "title": "Nigeria's Zuripay secures $110 million from Kestrel Ventures"}]
    v = pv.verify(_prov_deal(two))
    fields = {f["field"]: f for f in v["fields"]}
    assert v["independent_stories"] == 2 and v["tier"] == "corroborated"
    assert fields["Amount (as reported)"]["status"] == "corroborated"
    assert fields["Sector"]["status"] == "classified"
    copies = [{"publisher": "Reuters", "date": "2024-10-29", "url": "u1", "title": "Zuripay raises $110 million led by Kestrel Ventures"},
              {"publisher": "Yahoo Finance", "date": "2024-10-29", "url": "u3",
               "title": "Zuripay raises $110 million led by Kestrel Ventures - Reuters"}]
    v = pv.verify(_prov_deal(copies))
    assert v["independent_stories"] == 1 and v["syndicated_copies"] == 1 and v["tier"] == "single source"
    assert {f["field"]: f for f in v["fields"]}["Amount (as reported)"]["status"] == "reported"


def test_provenance_flags_disagreement_and_unconfirmed_completion():
    srcs = [{"publisher": "A", "date": "2025-01-02", "url": "u1", "title": "Halo acquires Linea for $63 million"},
            {"publisher": "B", "date": "2025-01-05", "url": "u2", "title": "Halo Telecom acquires Linea in $80 million deal"}]
    d = _prov_deal(srcs, deal_type="acquisition", stage="completed", target="Linea", buyer="Halo", investors=[],
              amount=63_000_000.0, amount_usd=63_000_000.0)
    fields = {f["field"]: f for f in pv.verify(d)["fields"]}
    assert fields["Amount (as reported)"]["status"] == "uncertain"
    assert fields["Stage"]["status"] == "uncertain"


def test_party_strings_are_split_or_dropped():
    from src.engines import investors as inv
    assert inv.split_names("IFC and Proparco") == [inv.canonical("IFC"), inv.canonical("Proparco")]
    assert inv.split_names("Tolaram Welcomes IFC") == []
    assert inv.split_names("Other Investors") == []
    assert inv.split_names("Procter & Gamble") == ["Procter & Gamble"]
    assert inv.canonical("NATCO Pharma") == inv.canonical("Natco Pharma")


# Fictional companies only: unit tests of code paths, not claims about real firms.
@pytest.mark.parametrize("company,title,expected", [
    ("Acme Telecom", "Acme Telecom denies receiving takeover approach", set()),
    ("Acme Holdings", "Acme Holdings CEO will not resign, board says", set()),
    ("Kora Bank", "Kora Bank denies merger talks but confirms CFO exit", {"leadership_change"}),
    ("Zuri Retail", "Zuri Retail posts results; it also said its chief executive will step down", {"leadership_change"}),
    ("Nimbus Group", "Nimbus Nigeria CFO resigns", set()),
    ("Kora Bank", "Securities regulator fines Kora Bank $6 million over reporting failures", {"regulatory_action"}),
    ("Kora Bank", "S&P downgrades Kora Bank to CCC+ on liquidity strain", {"credit_risk"}),
])
def test_headline_attribution(company, title, expected):
    from src.engines.deterministic_engine import _company_matchers, _mentions_company, match_rules_for_target
    m = _company_matchers(company)
    got = {t.value for t, _, s in match_rules_for_target(title, m) if s * 0.7 >= 0.2} if _mentions_company(title, m) else set()
    assert got == expected


@pytest.mark.parametrize("company,title,expected", [
    ("Paramount Global", "Four Paramount Global board members to exit amid merger talks", {"leadership_change"}),
    ("Naspers", "Phuthi Mahanyele-Dabengwa joins Naspers board", {"leadership_change"}),
    ("Atlas Group", "Shailesh Jejurikar elected Atlas Group president and CEO", {"leadership_change"}),
    ("UBA", "Tony Elumelu increases stake in UBA to 10.63%", {"insider_activity"}),
    ("Shoprite", "Shoprite sells major shopping mall in South Africa", {"m_and_a_activity"}),
])
def test_headline_event_patterns_cover_board_changes_stakes_and_asset_sales(company, title, expected):
    from src.engines.deterministic_engine import _company_matchers, match_rules_for_target
    matchers = _company_matchers(company)
    got = {signal_type.value for signal_type, _, _ in match_rules_for_target(title, matchers)}
    assert got == expected


def test_headline_event_patterns_do_not_transfer_other_companies_events():
    from src.engines.deterministic_engine import _company_matchers, match_rules_for_target
    matchers = _company_matchers("Acme")
    title = "Rival board members exit after Acme deal collapses"
    assert match_rules_for_target(title, matchers) == []


def test_shard_plan_splits_only_unfinished_companies():
    import json
    from datetime import date
    from src.engines import historical_backtest as hb
    universe = [(f"Fictional Co {i}", f"FIC{i}", "us") for i in range(7)]
    run_dir = hb.RUNS_DIR / "2024-01-15_2025-06-15"
    run_dir.mkdir(parents=True, exist_ok=True)
    hb._checkpoint(run_dir, "FIC0").write_text(json.dumps({"detection_version": hb.detection_version()}))
    plan = hb.plan_shards(date(2024, 1, 15), date(2025, 6, 15), universe, 4)
    assert plan["remaining"] == 6
    shards = [s["tickers"].split(",") for s in plan["shards"]]
    assert sorted(t for s in shards for t in s) == [f"FIC{i}" for i in range(1, 7)]
    assert len(shards) == 4 and max(map(len, shards)) - min(map(len, shards)) <= 1
    assert hb.plan_shards(date(2024, 1, 15), date(2025, 6, 15), universe[:1], 4)["shards"] == []


def test_monthly_run_continues_the_unfinished_period_and_publishes_only_improvements():
    import json
    from datetime import date
    from src.engines import historical_backtest as hb
    universe = [(f"Fictional Co {i}", f"FIC{i}", "us") for i in range(4)]
    start, end = date(2024, 1, 15), date(2025, 6, 15)
    run_dir = hb.RUNS_DIR / f"{start}_{end}"
    run_dir.mkdir(parents=True, exist_ok=True)
    hb.SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    hb.SUMMARY_PATH.write_text(json.dumps({"start": "2024-01-15", "end": "2025-06-15", "companies": 2,
                                           "missing_companies": 2}))
    assert hb.current_period(date(2025, 11, 2)) == (start, end, 30)          # recent: keep filling it
    assert hb.current_period(date(2026, 11, 2)) == (*hb.rolling_period(date(2026, 11, 2)), 0)  # stale: move on

    for t in ("FIC0", "FIC1"):
        hb._checkpoint(run_dir, t).write_text(json.dumps({"covered": True}))
    assert hb.publish_decision(start, end, universe)[0] is False          # no more than is published
    hb._checkpoint(run_dir, "FIC2").write_text(json.dumps({"covered": True}))
    assert hb.publish_decision(start, end, universe)[0] is True           # more companies than published
    other = date(2024, 2, 15), date(2025, 7, 15)
    assert hb.publish_decision(*other, universe)[0] is False               # a partial newer period with less coverage
    other_dir = hb.RUNS_DIR / f"{other[0]}_{other[1]}"
    other_dir.mkdir(parents=True, exist_ok=True)
    for t in ("FIC0", "FIC1"):
        hb._checkpoint(other_dir, t).write_text(json.dumps({"covered": True}))
    assert hb.publish_decision(*other, universe)[0] is True                # newer, as much coverage as published
    hb._checkpoint(run_dir, "FIC3").write_text(json.dumps({"covered": False}))
    assert hb.publish_decision(start, end, universe)[0] is True           # complete

    hb.SUMMARY_PATH.write_text(json.dumps({"start": "2024-01-15", "end": "2025-06-15", "missing_companies": 0}))
    assert hb.current_period(date(2026, 11, 2)) == (*hb.rolling_period(date(2026, 11, 2)), 0)


def test_country_profile_summarises_the_whole_history_not_the_latest_page():
    from datetime import date
    from src.engines import country_profile

    src = lambda pub: {"publisher": pub, "url": f"https://{pub}.example/a", "title": "t"}
    ds = [{"id": f"d{y}", "country": "NG", "announced": f"{y}-03-01", "deal_type": "acquisition",
           "sector": "banking", "amount_usd": 10e6 * (y - 2009), "sources": [src("a")]} for y in range(2010, 2026)]
    ds += [{"id": "big", "countries": ["NG", "GH"], "announced": "2026-09-01", "deal_type": "equity_funding",
            "amount_usd": 900e6, "sources": [src("a"), src("b")]},
           {"id": "ke", "country": "KE", "announced": "2026-09-01", "amount_usd": 5e9}]
    es = [{"id": "e1", "country": "NG", "day": "2011-05-02", "signal_type": "regulatory_action"},
          {"id": "e2", "countries": ["NG"], "day": "2026-01-02", "signal_type": "m_and_a_activity"}]
    p = country_profile.build("NG", ds, es, today=date(2026, 10, 21))
    assert p["first_year"] == 2010 and p["last_year"] == 2026 and p["deals"] == 17 and p["events"] == 2
    assert {r["year"]: r["events"] for r in p["by_year"]}[2011] == 1      # events are dated by "day"
    early = country_profile.build("NG", ds[5:], es, today=date(2026, 10, 21))
    assert early["first_year"] == 2015 and early["by_year"][0]["year"] == 2011   # an event-only year is charted, not the start
    assert p["largest_deals"][0]["id"] == "big" and all(d["id"] != "ke" for d in p["largest_deals"])
    assert p["deal_types"][0] == {"label": "acquisition", "deals": 16, "disclosed_value_usd": 1_360_000_000}
    assert p["sectors"][-1]["label"] == "unclassified"
    months = p["by_month_last_12"]
    assert len(months) == 12 and months[0]["month"] == "2025-11" and months[-1] == {"month": "2026-10", "deals": 0, "partial": True}
    assert {m["month"]: m["deals"] for m in months}["2026-09"] == 1 and p["deals_last_12m"] == 1
    assert [r["year"] for r in p["by_year"]] == list(range(2010, 2027)) and p["by_year"][-1]["partial"]
    assert p["cross_border_deals"] == 1 and p["cross_border_value_usd"] == 900_000_000


def test_market_cap_is_a_valuation_and_sovereign_or_sector_backing_is_not_a_deal():
    from src.engines.deals import extract_deal

    tingo = extract_deal("Nigerian founder Dozy Mmobuosi’s Tingo moves to raise $500 million, market cap soars above $7.6 billion",
                         published="2022-02-22")
    assert tingo["amount_usd"] == 500e6 and tingo["reported_valuation_usd"] == 7.6e9
    for headline in ("China Invests $16 Billion in Nigeria's Oil Sector",
                     "Saudi Arabia backs Nigeria’s economic reforms with $5bn bilateral trade facility",
                     "Norway Invests US$ 307 Million in Kenya's E-Mobility Sector"):
        assert extract_deal(headline, published="2024-01-01") is None, headline
    # A state-owned lender with a named borrower is still a deal.
    assert extract_deal("Kenya's M-Kopa raises $250m in debt and equity", published="2024-01-01")["target"] == "M-Kopa"


def test_finished_companies_get_missing_prices_filled_without_a_rerun(tmp_path, monkeypatch):
    import json
    from datetime import date
    from src.engines import historical_backtest as hb
    monkeypatch.setattr(hb, "CACHE_DIR", tmp_path / "cache")
    calls = []

    def moves(symbol, iso):
        calls.append(symbol)
        return {"FIC0": {"5d": 1.0, "10d": 3.0, "30d": 2.0}, "SPY": {"5d": 0.5, "10d": 1.0, "30d": 1.0}}.get(
            symbol, {"5d": None, "10d": None, "30d": None})
    monkeypatch.setattr("src.engines.outcome_labeller.default_price_moves", moves)

    pred = {"ticker": "FIC0", "as_of": "2025-01-15", "direction": "negative", "event_confirmed": True,
            "price_change_10d_pct": None, "abnormal_return_10d_pct": None, "direction_correct": None}
    stale = {"covered": True, "detection_version": hb.detection_version(), "predictions": [pred, {**pred, "ticker": "NOPX"}]}
    path = tmp_path / "c.json"
    path.write_text(json.dumps(stale))
    assert hb._checkpoint_state(path) == "prices" and hb._checkpoint_needs_run(path)

    out = hb._refresh_prices(stale, date(2026, 10, 21))
    filled, empty = out["predictions"]
    assert filled["price_change_10d_pct"] == 3.0 and filled["abnormal_return_10d_pct"] == 2.0
    assert filled["direction_correct"] is False and filled["event_confirmed"] is True   # labels kept
    assert empty["price_change_10d_pct"] is None
    path.write_text(json.dumps(out))
    assert hb._checkpoint_state(path) == "done"

    hb._price_moves("NOPX", "2025-01-15")                    # an empty lookup is not cached: tried again
    assert calls.count("NOPX") == 2
    hb._price_moves("FIC0", "2025-01-15")                    # a found one is
    assert calls.count("FIC0") == 1


def test_published_period_is_republished_when_more_predictions_have_returns():
    import json
    from datetime import date
    from src.engines import historical_backtest as hb
    universe = [(f"Fictional Co {i}", f"PXF{i}", "us") for i in range(3)]
    start, end = date(2023, 1, 15), date(2024, 6, 15)
    run_dir = hb.RUNS_DIR / f"{start}_{end}"
    run_dir.mkdir(parents=True, exist_ok=True)
    hb.SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    hb.SUMMARY_PATH.write_text(json.dumps({"start": "2023-01-15", "end": "2024-06-15", "companies": 2,
                                           "missing_companies": 1, "predictions_with_returns": 0}))
    bare = {"covered": True, "prices_version": hb.PRICES_VERSION, "detection_version": hb.detection_version(),
            "predictions": [{"price_change_10d_pct": None}]}
    for t in ("PXF0", "PXF1"):
        hb._checkpoint(run_dir, t).write_text(json.dumps(bare))
    assert hb.publish_decision(start, end, universe)[0] is False
    hb._checkpoint(run_dir, "PXF0").write_text(json.dumps({**bare, "predictions": [{"price_change_10d_pct": 1.5}]}))
    assert hb.publish_decision(start, end, universe)[0] is True


def test_market_profiles_state_whole_units_session_dates_and_inclusive_windows():
    from datetime import date
    from src.engines import company_profile as cp, pulse

    assert cp._ngx_session_date("October 26, 2026, 11:50 pm") == "2026-10-26"      # Monday evening: that day
    assert cp._ngx_session_date("October 26, 2026, 9:15 am") == "2026-10-23"       # before the open: Friday
    assert cp._ngx_session_date("October 25, 2026, 3:00 pm") == "2026-10-23"       # Sunday: Friday
    assert cp._ngx_session_date("not a date") is None
    assert cp._statement_currency("₦'million") == "NGN" and cp._statement_currency("US$ million") == "USD"
    assert cp._scaled_unit("NGN", "₦'million") == "NGN (converted from ₦'million)"

    today = date(2026, 10, 26)
    events = [{"id": "in", "day": "2026-10-20"}, {"id": "out", "day": "2026-10-19"}]
    deals = [{"id": "d1", "announced": "2026-09-27"}, {"id": "d0", "announced": "2026-09-26"}]
    p = pulse.build(deals, events, {}, today=today)
    assert p["events"]["recent"] == 1 and p["deals"]["recent"] == 1


def test_yahoo_quotes_are_dated_and_in_the_statement_currency(monkeypatch):
    from src.engines import company_profile as cp, financials as fin
    monkeypatch.setattr(fin, "yahoo_financials", lambda t: {
        "info": {"currency": "ZAc", "regularMarketPrice": 67723.0, "marketCap": 1.1e15, "regularMarketTime": 1793059200,
                 "longName": "Naspers Limited"},
        "annual": {"2026-03-31": {"revenue": 7.0e9}}, "checks": [], "unit": "ZAR"})
    m = cp._yahoo_section("NPN.JO")["market"]
    assert m["price"] == 677.23 and m["currency"] == "ZAR" and m["quoted_currency"] == "ZAc"
    assert m["market_cap"] == 1.1e15 and m["as_at"] == "2026-10-27"


def test_committed_macro_snapshot_serves_every_country():
    snapshot = cr.load_current_signals_snapshot()
    countries = snapshot.get("countries", {})
    assert snapshot.get("generated_at") and len(countries) == len(ac.COUNTRIES)
    assert all(v.get("observations") for v in countries.values())


def test_cash_flow_reconciliation_catches_a_dropped_bracket():
    from src.engines.financials import verify
    item = lambda cur, prior=None: {"current": cur, "prior": prior, "line": ""}    # noqa: E731
    dangote = {"operating_cash_flow": item(1710762), "investing_cash_flow": item(620354),
               "financing_cash_flow": item(-2076566), "cash": item(362586, 131716)}
    check = lambda items: next(c for c in verify(items) if c["check"].startswith("operating + investing"))  # noqa: E731
    assert check(dangote)["passed"]                                  # as filed: the gap is exchange-rate effects
    flipped = {**dangote, "financing_cash_flow": item(2076566)}
    assert not check(flipped)["passed"]


def test_nse_price_list_rows_match_names_initials_and_tickers():
    from src.engines.financials import nse_price_for
    prices = {"as_of": "2026-10-26", "rows": [
        {"name": "Safaricom Ltd Ord 0.05", "isin": "KE1000001402", "price": 33.0},
        {"name": "Kenya Commercial Bank Ltd Ord 1.00", "isin": "KE0000000315", "price": 85.25},
        {"name": "Kenya Power Lighting  Co Plc Ord 20.00", "isin": "KE0000000349", "price": 21.7}]}
    assert nse_price_for("Safaricom PLC", prices)["price"] == 33.0
    assert nse_price_for("KCB Group", prices, "KCB.NR")["price"] == 85.25
    assert nse_price_for("Kenya Power", prices)["price"] == 21.7
    assert nse_price_for("Unknown Holdings", prices, "ZZZ.NR") is None


def test_current_signals_flag_out_of_date_inconsistent_and_retained_figures():
    from datetime import date
    stored = {"generated_at": "2026-10-20T10:00:00Z", "observations": [
        {"metric_key": "fx_usd_daily", "value": 585.6, "frequency": "daily", "as_of_period": "2026-10-24", "freshness": "current"},
        {"metric_key": "official_exchange_rate_latest_lcu_per_usd", "value": 2191.7, "frequency": "monthly",
         "as_of_period": "2026-01", "freshness": "historical"},
        {"metric_key": "policy_rate_pct", "value": 4.5, "frequency": "unspecified", "as_of_period": "2025-12-15",
         "freshness": "historical"}]}
    r = cr.annotate_current_signals(ac.get("CG"), stored, "2026-10-26T11:30:00Z", today=date(2026, 10, 26))
    daily, official, policy = r["observations"]
    assert daily["label"] == "Exchange rate, daily" and not daily["out_of_date"]
    assert official["inconsistent"] and official["out_of_date"]          # 2,192 against a peg of about 585
    assert not policy["out_of_date"]                                    # in force since the last decision
    assert r["retained"] and r["retained_since"] == "2026-10-20T10:00:00Z"


def test_merger_filings_parse_dates_and_parties_and_confirm_named_companies():
    from src.engines import merger_filings as mf
    assert mf.parties_from_title("Summary-of-Merger-Transaction-TCCC_CCBA") == ["TCCC", "CCBA"]
    assert mf.parties_from_title("Website Notice - Uber International Technologies and Delivery Hero") == [
        "Uber International Technologies", "Delivery Hero"]
    assert mf.date_in_name("Notice-TaylorHolcim-Merger-20210817") == "2021-08-17"
    assert mf.date_in_name("Summary-of-Merger-Transaction-RailCo_GPR-leasing-Africa-23.9.19") == "2019-09-23"
    assert mf.date_in_text("notification received on 12th March, 2025 of the merger") == "2025-03-12"
    assert mf.date_from_case_number("202 6Mar0004") == "2026-03-15"
    text = ("1. Case number: 2026Jan0023 – Harvestime (Pty) Ltd and The Vegetable Business of McCain Foods "
            "(South Africa) (Pty) Ltd 2. Case number: 2026Feb0036 - Tsebo Solutions Group Proprietary Limited "
            "and UCT Foods Services (RF) Proprietary Limited")
    entries = mf.sa_gazette_entries(text, "https://example.org/list.pdf")
    assert [e["date"] for e in entries] == ["2026-01-15", "2026-02-15"]
    assert entries[1]["parties"][0] == "Tsebo Solutions Group Proprietary Limited"
    filings = entries + [{"id": "comesa:1", "authority": mf.COMESA, "title": "Sanlam-Decision", "parties": ["Sanlam"],
                          "date": "2025-07-01", "excerpt": "Sanlam Limited and Allianz SE", "url": "u"},
                         {"id": "comesa:2", "authority": mf.COMESA, "title": "Undated", "parties": ["Sanlam"], "date": None}]
    hits = mf.events_for("Sanlam Ltd", "SLM.JO", filings=filings)
    assert len(hits) == 1 and hits[0]["official"] and hits[0]["signal_types"] == ["m_and_a_activity"]
    assert mf.events_for("Tsebo Solutions Group", None, filings=filings)[0]["date"] == "2026-02-15"
    assert mf.events_for("Dangote Cement", "DANGCEM.LG", filings=filings) == []
    # A namesake is not the company; separate parties are not one name; a re-posted notice counts once.
    others = [{"authority": mf.COMESA, "title": "Paramount Aerospace Holdings", "date": "2025-08-15",
               "parties": ["Paramount Aerospace Holdings Proprietary Limited"], "excerpt": ""},
              {"authority": mf.COMESA, "title": "Website Notice - MTN and IHS", "date": "2026-05-28",
               "parties": ["MTN", "IHS"], "excerpt": ""},
              {"authority": mf.COMESA, "title": "Website-Notice-MTN-and-IHS", "date": "2026-05-28",
               "parties": ["MTN", "IHS"], "excerpt": ""}]
    assert mf.events_for("Paramount Global", "PARA", filings=others) == []
    assert len(mf.events_for("MTN Group", "MTN.JO", filings=others)) == 1


def test_sens_log_parses_feed_appends_new_only_and_confirms_completed_events(tmp_path):
    from datetime import date
    from src.engines import sens_log as sl
    page = ('<tr><td>09:00 - 27 Oct 2026 MTN 09:00 - 27 Oct 2026 |</td><td>'
            '<a href="/v3/sens_display.php?tdate=20261027090000&amp;seq=17&amp;scode=">MTN MTN GROUP LIMITED - '
            'Fulfilment of conditions precedent</a> Price: 1 | Move: 0</td></tr>'
            '<tr><td>08:00 - 26 Oct 2026 08:00 - 26 Oct 2026</td><td>'
            '<a href="/v3/sens_display.php?tdate=20261026080000&amp;seq=3&amp;scode=">ANGLO AMERICAN PLC - '
            'Cautionary announcement regarding the acquisition of X</a></td></tr>')
    entries = sl.parse_feed(page)
    assert [e["id"] for e in entries] == ["20261026-3", "20261027-17"]
    assert entries[1]["code"] == "MTN" and entries[1]["issuer"] == "MTN GROUP LIMITED"
    assert entries[0]["code"] is None and entries[0]["issuer"] == "ANGLO AMERICAN PLC"

    class Client:
        def get(self, url):
            class R:
                text = page
                def raise_for_status(self):
                    pass
            return R()
    log = tmp_path / "sens.jsonl"
    assert sl.capture(log, Client()) == {"added": 2, "total": 2}
    assert sl.capture(log, Client()) == {"added": 0, "total": 2}
    held = sl.load(log)
    assert sl.covered_since(held) == date(2026, 10, 26)
    hits = sl.events_for("MTN Group", "MTN.JO", entries=held)
    assert hits[0]["signal_types"] == ["m_and_a_activity"] and hits[0]["official"]
    assert sl.events_for("Anglo American", "AGL.JO", entries=held) == []      # cautionary: talks, not the event
    assert sl.classify_headline("Directorate Change") == {"leadership_change"}
    assert sl.classify_headline("Dealings in Securities by a Director") == {"insider_activity"}
    assert sl.classify_headline("Trading Statement") == {"earnings_surprise"}


def test_research_reports_absent_investor_kind_and_ranks_superlatives_by_size():
    deals = [_deal("Nigeria’s Daya raises $2.4m for stablecoin payments", published="2026-06-24"),
             _deal("Nigerian Fintech Stabyl Raises $2.7M to Solve FX Liquidity", published="2026-06-14"),
             _deal("Nigerian fintech Cardtonic secures $0.5m seed", published="2026-08-01")]
    _, evidence = rs.retrieve("Which private equity firms invested in Nigerian fintech this year?", deals,
                              live_news=False, today=date(2026, 10, 27))
    # No registered PE investor is itself the answer; the matching deals are still the evidence.
    assert "None of the 3 deals in scope involves an investor registered as private equity" in evidence[0]["text"]
    assert sum(item["kind"] == "deal" for item in evidence) == 3
    _, evidence = rs.retrieve("Biggest Nigerian fintech deals this year", deals, live_news=False,
                              today=date(2026, 10, 27))
    assert [item["title"] for item in evidence if item["kind"] == "deal"][0].startswith("Nigerian Fintech Stabyl")
    assert "Largest disclosed: Nigerian Fintech Stabyl" in evidence[0]["text"]


def test_deal_extractor_rejects_non_transactions_and_reads_bank_backing_as_lending():
    for title in ["NLC Announces Compulsory Land Acquisition In Two Counties For Major Road Projects in Kenya",
                  "Watford Snap Up Zimbabwe International Jordan Zemura From Udinese",
                  "Kenyan CEO In Court For Forging Signature To Secure $150k Loan",
                  "Nigeria's McDowell’s Acquires New Name, Mr. Dowell’s"]:
        assert dl.extract_deal(title, published="2026-10-20") is None, title
    loan = dl.extract_deal("SBM Bank Kenya Backs Beyond Continents Logistics With $4.44Mn for Fleet", published="2026-10-20")
    assert loan["deal_type"] == "debt_financing" and loan["buyer"] == "SBM Bank Kenya"
    # A bank that invests (an equity stake) is still equity.
    stake = dl.extract_deal("Siinqee Bank Invests ETB 50 Million in Ethiopia’s Stock Exchange", published="2026-10-20")
    assert stake["deal_type"] == "equity_funding"


def test_follow_up_reports_of_an_agreed_deal_extract_place_and_upgrade_the_rumour():
    rumour = dl.extract_deal("South Africa's MTN In Talks To Buy Remaining Stake In IHS Towers", published="2026-02-09")
    rumour["sources"] = [{"url": "u0"}]
    assert rumour["stage"] == "rumoured"
    for title in ["Coast clears for MTN Group’s $6.2b IHS Towers’ acquisition",
                  "MTN Moves Closer to $6.2 Billion IHS Acquisition After Shareholder Approval",
                  "IHS shareholders approve MTN merger in major telecom infrastructure deal",
                  "MTN agrees to buy IHS Towers for $6.2 billion"]:
        d = dl.extract_deal(title, published="2026-08-05")
        assert d and d["deal_type"] == "acquisition" and d["countries"] == ["ZA"], title   # MTN places it
        assert dl.same_transaction(d, rumour), title
    agreed = dl.extract_deal("MTN agrees to buy IHS Towers for $6.2 billion", published="2026-08-05")
    agreed["sources"] = [{"url": "u1"}]
    merged = dl.merge(rumour, agreed)
    assert (merged["stage"], merged["amount_usd"], merged["announced"], merged["first_reported"]) == (
        "announced", 6.2e9, "2026-08-05", "2026-02-09")
    assert merged["headline"] == "MTN agrees to buy IHS Towers for $6.2 billion"
    # A non-African deal is still not placed in Africa.
    assert dl.extract_deal("Microsoft acquires Activision for $69bn", published="2026-08-05") is None


def test_charitable_fundraising_and_unnamed_parties_are_not_deals():
    for title in ["Group raises $1b to tackle child malnutrition in Nigeria, others",
                  "U.S. invests in Ghana’s Upper West Region to tackle poverty among subsistence farmers",
                  "Nigerian group raises $5m Series A"]:
        assert dl.extract_deal(title, published="2026-10-27") is None, title
    # A company tackling a market gap is still a deal.
    assert dl.extract_deal("Kenyan fintech Pezesha raises $11m to tackle SME credit gap",
                           published="2026-10-27")["target"] == "Pezesha"



def test_checkpoint_made_by_other_detection_code_is_rerun(tmp_path):
    import json
    from src.engines import historical_backtest as hb
    path = tmp_path / "c.json"
    done = {"covered": True, "prices_version": hb.PRICES_VERSION, "detection_version": hb.detection_version(),
            "predictions": []}
    path.write_text(json.dumps(done))
    assert hb._checkpoint_state(path) == "done"
    path.write_text(json.dumps({**done, "detection_version": "older-rules"}))
    assert hb._checkpoint_state(path) == "run"
    path.write_text(json.dumps({k: v for k, v in done.items() if k != "detection_version"}))
    assert hb._checkpoint_state(path) == "run"              # made before versions were recorded


def test_equipment_purchases_and_crime_stories_are_not_deals_but_brands_are():
    for title in ["Kisubi Hospital acquires Uganda's first next-generation MRI scanner",
                  "Drug Trafficker Acquires Scanner to Test Security in Kenya",
                  "Liberia's LTA Acquires New Equipment for Internet Exchange Point"]:
        assert dl.extract_deal(title, published="2026-10-27") is None, title
    assert dl.extract_deal("Kenya’s Peach Cars Raises $11M to Build Africa’s Most Trusted Used Car Marketplace",
                           published="2026-10-27")["target"] == "Peach Cars"
    assert dl.extract_deal("Stucky Motors buys Swazi Truck in Eswatini", published="2026-10-27")["target"] == "Swazi Truck"



def test_brief_engine_reads_sens_wording_and_research_cites_logged_sens(tmp_path, monkeypatch):
    import json
    from src.engines import research as rs, sens_log
    from src.engines.deterministic_engine import DeterministicSignalEngine
    from src.schemas.models import AgentState, AnalysisRequest, SECFiling
    state = AgentState(request=AnalysisRequest(company_name="MTN Group", ticker="MTN.JO"))
    state.filings = [SECFiling(accession_number="SENS-1", form_type="JSE SENS", filing_date="2026-10-26",
                               company_name="MTN GROUP LIMITED", cik="JSE", document_url="https://example.com/s1",
                               description="MTN: MTN GROUP LIMITED - Directorate Change")]
    found = {c.signal_type.value for c in DeterministicSignalEngine().run(state).signal_candidates}
    assert "leadership_change" in found

    log = tmp_path / "sens.jsonl"
    log.write_text(json.dumps({"id": "20261026-5", "date": "2026-10-26", "time": "09:00", "issuer": "MTN GROUP LIMITED",
                               "code": "MTN", "headline": "Firm intention announcement",
                               "url": "https://example.com/sens"}) + "\n")
    monkeypatch.setattr(sens_log, "LOG_PATH", log)
    monkeypatch.setattr(sens_log, "_LOG", None)
    _, evidence = rs.retrieve("What is MTN Group doing in 2026?", live_news=False, today=date(2026, 10, 27))
    sens = [e for e in evidence if e["kind"] == "exchange_disclosure"]
    assert sens and "Firm intention announcement" in sens[0]["text"] and "m and a activity" in sens[0]["text"]
    assert sens[0]["source_quality"] == "Official / primary"


def test_research_recognises_companies_whose_names_contain_sector_words():
    cases = {"What is MTN Group doing in 2026?": (["MTN Group"], []), "Safaricom deals this year": (["Safaricom"], []),
             "Dangote Cement acquisitions": (["Dangote Cement"], []), "Airtel Africa IPO": (["Airtel Africa"], []),
             "MTN fintech deals": (["MTN"], ["fintech"]), "Fintech deals in Nigeria": ([], ["fintech"])}
    for question, (companies, sectors) in cases.items():
        p = rs.parse_question(question, date(2026, 10, 27))
        assert (p["companies"], p["sectors"]) == (companies, sectors), question
