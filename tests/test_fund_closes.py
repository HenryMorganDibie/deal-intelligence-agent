"""Fund-close reports: one close reported by the manager, the fund and its investors, often weeks apart."""

from src.engines import deals as d  # noqa: E402
def r(target, day, usd, head, cs=(), cur="USD", amt=None):
    return {"deal_type": "fund_raise", "target": target, "announced": day, "amount_usd": usd, "amount": amt if amt else usd,
            "currency": cur, "countries": list(cs), "headline": head}
same = {
 "Ninety One a": (r("Africa Credit Opps Fund","2026-08-18",404e6,"Ninety One secures $404m for Africa Credit Opps Fund 3 at final close"),
                  r("Ninety One","2026-08-18",404e6,"Ninety One makes final close of Africa credit fund at $404m",["ZA","BJ"])),
 "Ninety One b": (r("Ninety One","2026-08-18",404e6,"Ninety One makes final close of Africa credit fund at $404m",["ZA","BJ"]),
                  r("Ninety One","2026-10-13",404e6,"Ninety One Reaches Final Close of $404M Africa Credit Fund")),
 "Ninety One c": (r("Ninety One Africa Credit Opportunities Fund","2026-08-18",None,"Ninety One Africa Credit Opportunities Fund 3 reaches final close"),
                  r("Ninety One","2026-08-18",404e6,"Ninety One makes final close of Africa credit fund at $404m",["ZA","BJ"])),
 "CFM a": (r("CFM","2026-08-06",180e6,"CFM raises over USD 180m at first close of South Africa H2 fund | Hydrogen News",["ZA"]),
           r("Climate Fund Managers","2026-08-06",167.7e6,"Scaling up green transition in Southern Africa under Global Gateway: Climate Fund Managers reaches first close of SA-H2 Fund at ZAR 3 billion",["ZA"],"ZAR",3e9)),
 "CFM b": (r("Climate Fund Managers","2026-08-06",167.7e6,"Scaling up green transition in Southern Africa under Global Gateway: Climate Fund Managers reaches first close of SA-H2 Fund at ZAR 3 billion",["ZA"],"ZAR",3e9),
           r("SA-H2 Fund","2026-08-19",182e6,"SA-H2 Fund reaches $182m first close to scale green hydrogen investment in Southern Africa")),
 "CFM c": (r("Climate Fund Managers","2026-08-06",167.7e6,"Scaling up green transition in Southern Africa under Global Gateway: Climate Fund Managers reaches first close of SA-H2 Fund at ZAR 3 billion",["ZA"],"ZAR",3e9),
           r("Climate Fund Managers","2026-10-01",167.7e6,"Scaling Up Green Transition In Southern Africa: Climate Fund Managers Reaches First Close Of SA-H2 Fund at ZAR 3 billion",[],"ZAR",3e9)),
 "DPI a": (r("DPI","2026-02-26",None,"DPI makes first close on Africa fund targeting $1bn — article includes a paywall"),
           r("Development Partners International","2026-02-25",None,"Development Partners International reaches first close on fourth Africa fund")),
 "DPI b": (r("DPI","2026-02-23",None,"Proparco joins first close of DPI’s ADP IV fund"),
           r("DPI","2026-02-26",None,"DPI makes first close on Africa fund targeting $1bn — article includes a paywall")),
 "Enko": (r("Enko Capital","2025-10-21",100e6,"Africa-Focused Enko Capital Raises $100 Million In Fund's First Close"),
          r("Enko Capital","2025-10-20",100e6,"Enko Capital reaches $100m first close for Africa-focused credit fund — article includes a paywall")),
 "BluePeak": (r("BluePeak","2025-05-20",None,"In brief: BluePeak reaches first close for second African fund"),
              r("BluePeak Private Capital Fund II","2025-05-13",None,"First close for BluePeak Private Capital Fund II")),
 "Aqua-Spark": (r("Aqua-Spark","2026-03-12",45.98e6,"Aqua-Spark reaches €42.3m first close on African aquaculture fund — article includes a paywall",[],"EUR",42.3e6),
                r("Aqua-Spark Africa","2026-03-12",None,"AgriFood Signals: First close for Aqua-Spark Africa fund, Anchr nabs funds for AI in food distribution")),
 "Africa50": (r("Africa50 Infrastructure Acceleration Fund","2024-01-10",222.5e6,"An African First - Africa50 Infrastructure Acceleration Fund reaches first close with $222.5 million - securing strong support from mostly African institutional investors"),
              r("Africa50 Infrastructure Acceleration Fund","2025-09-27",222.5e6,"An African First - Africa50 Infrastructure Acceleration Fund reaches first close with $222.5 million - securing strong support from mostly African institutional investors")),
 "Kuramo": (r("Kuramo Africa Opportunity Fund IV","2026-07-07",None,"Kuramo Africa Opportunity Fund IV reaches first close"),
            r("Kuramo Capital","2026-07-21",31.6e6,"Kuramo Capital lands NGN 48B first close for Africa fund from Nigerian pensions",["NG"],"NGN",48e9)),
}
apart = {
 "TLG first vs second": (r("TLG Capital","2025-05-02",None,"TLG Capital fund reaches first close"), r("TLG Capital","2026-06-30",120e6,"TLG Capital fund reaches $120m second close")),
 "AHL first vs second": (r("AHL Venture Partners","2026-05-26",30.5e6,"AHL Venture Partners reaches first close for Africa credit fund"), r("AHL Venture Partners","2026-09-03",45.5e6,"AHL Venture Partners reaches $45.5m second close")),
 "Adenia fund V vs new": (r("Adenia Partners","2023-01-31",300e6,"Adenia Partners announces $300 million first close for fund V"), r("Adenia Partners","2026-03-19",180e6,"Adenia Partners completes $180m first close for African SME-focused fund — article includes a paywall")),
 "Africa50 first vs nears final": (r("Africa50 Infrastructure Acceleration Fund","2025-09-27",222.5e6,"An African First - Africa50 Infrastructure Acceleration Fund reaches first close with $222.5 million"), r("Africa50 Acceleration Fund","2026-03-06",None,"Africa50 Acceleration Fund nears final close under Sérgio Pimenta’s leadership")),
 "CFM CI2 vs SA-H2": (r("Climate Fund Managers","2022-12-05",855e6,"Climate Fund Managers announces second close of CI2 at $855m"), r("Climate Fund Managers","2026-08-06",167.7e6,"Climate Fund Managers reaches first close of SA-H2 Fund at ZAR 3 billion",["ZA"])),
 "ARM-Harith vs CardinalStone": (r("ARM-Harith","2026-06-08",76e6,"ARM-Harith secures $76 million first close for climate transition fund",["NG"]), r("CardinalStone","2026-08-24",76e6,"CardinalStone secures $76 million in first close for second West African Growth Fund")),
 "Janngo": (r("Janngo Capital","2022-09-14",None,"Janngo Capital hits first close for $63-million fund",["SN"]), r("Janngo Capital","2024-10-30",78e6,"Janngo Capital fund reaches final close at $78m")),
}

import pytest  # noqa: E402

from src import hosted_market as hm  # noqa: E402


@pytest.mark.parametrize("name", list(same))
def test_reports_of_one_close_match(name):
    a, b = same[name]
    assert d.strong_same_report(a, b) and d.strong_same_report(b, a)


@pytest.mark.parametrize("name", list(apart))
def test_different_closes_stay_apart(name):
    a, b = apart[name]
    assert not d.strong_same_report(a, b) and not d.strong_same_report(b, a)


@pytest.mark.parametrize("target, headline, expected", [
    ("Million", "Africa-Focused Enko Capital Raises $100 Million In Fund's First Close", "Enko Capital"),
    ("First", "First close for BluePeak Private Capital Fund II", "BluePeak Private Capital Fund II"),
    ("South", "South Africa: Second close for HAVAÍC's African Innovation Fund 3", "HAVAÍC"),
    ("Seals", "Botswana Tech Fund Seals First Close With £5M From Lansdown Family Office", "Botswana Tech Fund"),
    ("AgriFood", "AgriFood Signals: First close for Aqua-Spark Africa fund, Anchr nabs funds", "Aqua-Spark Africa"),
    ("Aruwa Capital Exceeds Targeted", "Aruwa Capital Exceeds Targeted $20m, Achieves Final Close On Fund 1", "Aruwa Capital"),
    ("VC Breega", "Paris-based VC Breega hits first close of $75M Africa fund", "Breega"),
])
def test_fund_manager_names_are_recovered(target, headline, expected):
    assert d.fund_raise_fix({"deal_type": "fund_raise", "target": target, "headline": headline})["target"] == expected


def test_an_investor_is_not_the_manager_and_a_target_size_is_not_money_raised():
    fix = d.fund_raise_fix({"deal_type": "fund_raise", "target": "Proparco", "headline": "Proparco joins first close of DPI’s ADP IV fund"})
    assert fix == {"target": "DPI", "investors": ["Proparco"]}
    fix = d.fund_raise_fix({"deal_type": "fund_raise", "target": "DPI", "amount": 1e9, "currency": "USD", "amount_usd": 1e9,
                            "headline": "DPI makes first close on Africa fund targeting $1bn"})
    assert fix["amount_usd"] is None and fix["fund_target_usd"] == 1e9
    assert "excluded" in d.fund_raise_fix({"deal_type": "fund_raise", "target": "Impact",
                                           "headline": "Impact investor completes first close of new fund"})
    assert d.fund_raise_fix({"deal_type": "fund_raise", "target": "Glint",
                             "headline": "Glint secures first close of its second venture fund"}) is None


def test_merged_closes_show_the_manager_and_keep_the_fund_name():
    a, b = same["CFM a"]
    rows = [{**a, "id": "cfm", "sources": [{"url": "u1"}]}, {**b, "id": "climate", "sources": [{"url": "u2"}]}]
    out: dict = {}
    hm._merge_stored_duplicates(rows, out)
    kept = next(v for v in out.values() if not v.get("merged_into"))
    assert kept["target"] == "Climate Fund Managers" and sum(1 for v in out.values() if v.get("merged_into")) == 1
    assert hm._fund_house_name("Africa Credit Opps Fund", "Ninety One") == {"target": "Ninety One", "fund_name": "Africa Credit Opps Fund"}
    assert hm._fund_house_name("Aqua-Spark", "Aqua-Spark Africa")["target"] == "Aqua-Spark"
    assert hm._fund_house_name("CFM", "Climate Fund Managers")["target"] == "Climate Fund Managers"


@pytest.mark.parametrize("lp, fund", [
    (r("Tanmiya Capital", "2026-10-28", 37.5e6, "EIB invests $37.5m in Tanmiya Capital Fund II to support Egyptian SMEs"),
     r("Tanmiya Capital", "2026-10-26", 130e6, "Tanmiya Capital closes second Egypt growth fund at $130m, backed by $37.5m EIB commitment")),
    (r("Novastar fund", "2026-04-29", 5e6, "Proparco commits $5m to Novastar fund"),
     r("Novastar Ventures", "2026-03-31", 147e6, "Novastar Ventures closes $147 million fund for African startups")),
    (r("Adenia Entrepreneurial Fund I", "2026-03-27", 16.3e6, "DEG commits €15m to Adenia Entrepreneurial Fund I", cur="EUR", amt=15e6),
     r("Adenia Partners", "2026-03-19", 180e6, "Adenia Partners completes $180m first close for African SME-focused fund")),
    (r("Acumen Resilient Agriculture Fund II", "2026-07-27", 12e6, "Acumen Resilient Agriculture Fund II secures $12m from Proparco"),
     r("Acumen", "2026-07-16", 90e6, "Acumen Raises USD 90 M For Africa Climate-Resilient Agriculture Fund")),
])
def test_an_lp_commitment_folds_into_the_fund_raise(lp, fund):
    assert d.strong_same_report(lp, fund) and d.strong_same_report(fund, lp)


def test_two_funds_of_one_house_stay_apart():
    a = r("AfricInvest", "2022-05-26", 411e6, "AfricInvest secures $411 million for its AfricInvest Fund IV")
    b = r("AfricInvest", "2022-07-19", 119.6e6, "AfricInvest and Cathay Innovation reach final close of Pan-African fund at €110M", cur="EUR", amt=110e6)
    assert not d.strong_same_report(a, b)
