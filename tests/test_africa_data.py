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
